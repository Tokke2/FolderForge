"""Uppdatera endast från publicerade stabila GitHub-releaser, aldrig en gren.

Hämtning sker i bakgrunden. Förberedd kod installeras vid nästa start,
före GUI-start, följt av omstart för att läsa in de nya modulerna. Användardata och Git lämnas orörda.
"""
from __future__ import annotations

import io
import hashlib
import subprocess
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead
from datetime import datetime
import math
import zipfile

REPOSITORY = "Tokke2/FolderForge"
INTERVAL = 12 * 60 * 60
MAX_DOWNLOAD = 32 * 1024 * 1024
FILES = frozenset({"folder.pyw", "settings.py", "historik.py", "logg.py", "updater.py", "cache_cleanup.py", "Starta-FolderForge.ps1", "Starta-FolderForge.vbs"})
logger = logging.getLogger(__name__)
_check_lock = threading.Lock()


def version(value):
    """Acceptera numeriska stabila taggar (v5.1, 5.1.0), inte prereleaser."""
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+(?:\.\d+)*", value):
        return None
    parts = tuple(map(int, value.lstrip("v").split(".")))
    return parts + (0,) * max(0, 4 - len(parts))


def read_state(base):
    try:
        result = json.loads((base / "data/update-state.json").read_text("utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(base, state):
    path = base / "data/update-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="update-state-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def fetch(url, limit, progress=None):
    """Begränsad strömhämtning; återförsök bara vid övergående nätverksfel."""
    request = Request(url, headers={"User-Agent": "FolderForge-updater", "Accept": "application/vnd.github+json"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                try:
                    total = int(response.headers.get("Content-Length", 0)) or None
                except (ValueError, TypeError):
                    total = None
                if total and total > limit:
                    raise ValueError("Uppdateringen är för stor")
                chunks, received = [], 0
                if progress:
                    progress(0, total)
                while True:
                    chunk = response.read(min(64 * 1024, limit + 1 - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > limit:
                        raise ValueError("Uppdateringen är för stor")
                    chunks.append(chunk)
                    if progress:
                        progress(received, total)
                if total is not None and received != total:
                    raise URLError("Ofullständig hämtning")
                return b"".join(chunks)
        except (HTTPError, URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
            transient = not isinstance(exc, HTTPError) or exc.code in {429, 500, 502, 503, 504}
            if not transient or attempt == 2:
                raise
            delay = 0.5 * (2 ** attempt)
            if isinstance(exc, HTTPError):
                try:
                    delay = min(5.0, max(delay, float(exc.headers.get("Retry-After", delay))))
                except (TypeError, ValueError, AttributeError):
                    pass
            logger.warning("Tillfälligt fel från GitHub; nytt försök %s/3", attempt + 2)
            time.sleep(delay)


def unpack(data, destination):
    """Extrahera endast kända appfiler, aldrig data/, .git eller sökvägar utanför."""
    found = set()
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            parts = PurePosixPath(member.filename).parts
            if len(parts) < 2 or ".." in parts or "\\" in member.filename:
                continue
            relative = PurePosixPath(*parts[1:])
            name = str(relative)
            allowed = name in FILES or (len(relative.parts) == 2 and relative.parts[0] == "Icon"
                       and relative.suffix.lower() in {".png", ".ico"})
            if not allowed or member.is_dir():
                continue
            if name in found:
                raise ValueError("Dubblerad appfil i release")
            total += member.file_size
            if total > MAX_DOWNLOAD:
                raise ValueError("Uppackad release är för stor")
            content = archive.read(member)
            if relative.suffix in {".py", ".pyw"}:
                compile(content, name, "exec")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            found.add(name)
    if not FILES.issubset(found):
        raise ValueError("Releasen saknar obligatoriska appfiler")


def content_manifest(root):
    """SHA-256 för exakt de appfiler och ikoner som får installeras."""
    return {str(file.relative_to(root).as_posix()): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in root.rglob("*") if file.is_file()
            and (str(file.relative_to(root).as_posix()) in FILES
                 or (len(file.relative_to(root).parts) == 2
                     and file.relative_to(root).parts[0] == "Icon"
                     and file.suffix.lower() in {".png", ".ico"}))}


def matches_manifest(root, manifest):
    if not isinstance(manifest, dict) or not FILES.issubset(manifest):
        return False
    try:
        for name, digest in manifest.items():
            relative = PurePosixPath(name)
            if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                    or not (name in FILES or (len(relative.parts) == 2 and relative.parts[0] == "Icon"
                                              and relative.suffix.lower() in {".png", ".ico"}))):
                return False
            file = root / name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def recover_pending(base, state):
    previous = base / "data/update-pending-previous"
    pending = base / "data/update-pending"
    hashes = state.get("pending_hashes")
    if previous.exists() and matches_manifest(previous, hashes) and not matches_manifest(pending, hashes):
        if pending.exists():
            shutil.rmtree(pending)
        os.replace(previous, pending)


def _check_once(base, current_version, now=None, *, force=False):
    now = time.time() if now is None else now
    state = read_state(base)
    recover_pending(base, state)
    last = state.get("last_check", 0)
    unfinished = state.get("status") in {"checking", "resolving", "comparing", "downloading", "verifying"}
    if not force and not unfinished and isinstance(last, (int, float)) and 0 <= now - last < INTERVAL:
        return
    # Även nätverksfel begränsas till två försök per dygn, även efter omstart.
    state["last_check"] = now
    state["status"] = "checking"
    if force:
        state.pop("restart_blocked", None)
        state.pop("installation_error", None)
    state.pop("error", None)
    state.pop("downloaded", None)
    state.pop("download_total", None)
    write_state(base, state)
    release = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/releases/latest", 1024 * 1024))
    tag = release.get("tag_name", "")
    candidate = version(tag)
    state["latest"] = tag if candidate else ""
    notes = release.get("body")
    state["release_notes"] = notes[:12000] if isinstance(notes, str) else "Ingen ändringslista publicerad."
    installed = max(version(current_version) or (0,) * 4,
                    version(state.get("installed", "")) or (0,) * 4)
    if release.get("draft") or release.get("prerelease") or candidate is None or candidate < installed:
        state["status"] = "checked"
        write_state(base, state)
        return
    # Lös releasens tagg till ett bestämt commit-ID, även för annoterade taggar.
    # target_commitish/updated_at säger inte säkert vilken kod taggen pekar på.
    state["status"] = "resolving"
    write_state(base, state)
    commit = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/commits/{tag}", 1024 * 1024))
    revision = commit.get("sha", "")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Releasen saknar ett giltigt commit-ID")
    state["latest_revision"] = revision
    state["status"] = "comparing"
    write_state(base, state)
    if (candidate == installed and state.get("installed_revision") == revision
            and version(state.get("installed", "")) == candidate
            and matches_manifest(base, state.get("installed_hashes"))):
        state["status"] = "checked"
        write_state(base, state)
        return
    if (state.get("pending") == tag and state.get("pending_revision") == revision
            and matches_manifest(base / "data/update-pending", state.get("pending_hashes"))):
        state["status"] = "checked"
        write_state(base, state)
        return
    # Hämta exakt den kontrollerade revisionen även om taggen flyttas under tiden.
    state["status"] = "downloading"
    write_state(base, state)
    last_progress = [0.0]

    def progress(received, total):
        state["downloaded"], state["download_total"] = received, total
        clock = time.monotonic()
        if received == 0 or received == total or clock - last_progress[0] >= 0.25:
            write_state(base, state)
            last_progress[0] = clock

    data = fetch(f"https://api.github.com/repos/{REPOSITORY}/zipball/{revision}", MAX_DOWNLOAD, progress=progress)
    state["status"] = "verifying"
    state["downloaded"] = len(data)
    write_state(base, state)
    with tempfile.TemporaryDirectory(dir=base / "data") as temporary:
        staged = Path(temporary)
        unpack(data, staged)
        # Äldre installationer saknar commit-ID. Jämför faktiska appfiler en
        # gång i stället för att anta att samma versionsnummer betyder samma kod.
        hashes = content_manifest(staged)
        same_content = matches_manifest(base, hashes)
        if same_content:
            state["installed"] = tag
            state["installed_revision"] = revision
            state["installed_hashes"] = hashes
            state["status"] = "checked"
            # En tidigare hämtad revision får inte installeras över aktuell kod.
            state.pop("pending", None)
            state.pop("pending_revision", None)
            state.pop("pending_notes", None)
            state.pop("pending_hashes", None)
            write_state(base, state)
            return
        pending = base / "data/update-pending"
        previous = base / "data/update-pending-previous"
        if previous.exists():
            shutil.rmtree(previous)
        if pending.exists():
            os.replace(pending, previous)
        try:
            os.replace(staged, pending)
        except OSError:
            if previous.exists():
                os.replace(previous, pending)
            raise
    state.pop("restart_blocked", None)
    state.pop("installation_error", None)
    state["pending"] = tag
    state["pending_revision"] = revision
    state["pending_hashes"] = hashes
    state["pending_notes"] = state["release_notes"]
    state["status"] = "checked"
    write_state(base, state)
    if previous.exists():
        try:
            shutil.rmtree(previous)
        except OSError:
            logger.warning("Kunde inte rensa tidigare uppdateringspaket", exc_info=True)
    logger.info("Release %s hämtad; installeras vid nästa start", tag)


def _checked_once(base, current_version, now=None, *, force=False):
    try:
        _check_once(base, current_version, now, force=force)
    except Exception as exc:
        state = read_state(base)
        if (isinstance(exc, HTTPError) and exc.code == 404
                and exc.url.endswith("/releases/latest")):
            state["status"] = "no_release"
            state.pop("latest", None)
            state.pop("error", None)
            write_state(base, state)
            return
        state["status"] = "error"
        if isinstance(exc, HTTPError):
            if exc.code in {403, 429}:
                detail = "GitHub nekade kontrollen eller begränsar antalet anrop. Försök igen senare."
            else:
                detail = f"GitHub svarade med HTTP {exc.code}. Försök igen eller öppna felloggen."
        elif isinstance(exc, URLError):
            detail = f"Kunde inte nå GitHub: {exc.reason}"
        else:
            detail = str(exc)
        state["error"] = detail[:300]
        write_state(base, state)
        raise


def check_once(base, current_version, now=None, *, force=False):
    """Manuell kontroll får kringgå intervallet, men aldrig starta parallell hämtning."""
    if not _check_lock.acquire(blocking=False):
        return False
    try:
        _checked_once(base, current_version, now, force=force)
        return True
    finally:
        _check_lock.release()


def pending_ready_for_restart(base):
    state = read_state(base)
    return bool(not _check_lock.locked() and not state.get("restart_blocked")
                and version(state.get("pending", ""))
                and matches_manifest(base / "data/update-pending", state.get("pending_hashes")))


def mark_installation_failed(base, error):
    state = read_state(base)
    state.update(status="error", error=f"Installation misslyckades: {error}"[:300],
                 installation_error=str(error)[:300], restart_blocked=True)
    write_state(base, state)


def get_update_activity(base):
    """Lättviktig UI-modell, utan nätverk eller filhashning."""
    state = read_state(base)
    received, total = state.get("downloaded", 0), state.get("download_total")
    progress = None
    if isinstance(received, (int, float)) and isinstance(total, (int, float)) and total > 0:
        progress = max(0.0, min(1.0, received / total))
    ready = bool(version(state.get("pending", "")) and (base / "data/update-pending").is_dir())
    return {"busy": _check_lock.locked(), "ready": ready, "progress": progress,
            "phase": state.get("status", "idle"), "error": state.get("error") or (state.get("installation_error", "") if state.get("restart_blocked") else ""), "restart_blocked": bool(state.get("restart_blocked"))}


def get_update_status(base, current_version):
    """Lokala visningsvärden; ingen nätverkstrafik från GUI-tråden."""
    state = read_state(base)
    installed = state.get("installed", "")
    if not version(installed) or version(installed) < (version(current_version) or (0,) * 4):
        installed = current_version
    last = state.get("last_check")
    checked = "Aldrig"
    if isinstance(last, (int, float)) and not isinstance(last, bool) and math.isfinite(last) and last > 0:
        try:
            checked = datetime.fromtimestamp(last).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        except (ValueError, OverflowError, OSError):
            pass
    status = {
        "checking": "Söker senaste stabila release…",
        "resolving": "Kontrollerar releasens commit-ID…",
        "comparing": "Jämför appfiler och ikoner…",
        "downloading": "Hämtar uppdatering…",
        "verifying": "Verifierar hämtade filer…",
        "checked": "Kontroll klar – ingen ny uppdatering att installera.",
        "no_release": "Ingen stabil release är publicerad.",
        "error": "Kontrollen misslyckades. Nytt försök enligt schemat.",
    }.get(state.get("status"), "Ingen kontroll har slutförts ännu.")
    pending = state.get("pending", "")
    if (state.get("status") not in {"checking", "resolving", "comparing", "downloading", "verifying", "error"}
            and version(pending) and (base / "data/update-pending").is_dir()):
        status = f"{pending} är hämtad. Appen startar om automatiskt när öppna dialoger är stängda."
    if state.get("restart_blocked"):
        status = "Automatisk omstart pausad efter installationsfel. Sök uppdatering nu för att försöka igen."
    received, total = state.get("downloaded", 0), state.get("download_total")
    download = "Ingen hämtning"
    if isinstance(received, (int, float)) and received > 0:
        download = f"{received / 1024:.0f} KiB"
        if isinstance(total, (int, float)) and total > 0:
            download += f" / {total / 1024:.0f} KiB ({min(100, int(received * 100 / total))} %)"
    return {
        "Installerad version": installed,
        "Hämtning": download,
        "Installerat bygg-ID": str(state.get("installed_revision") or "Okänt")[:12],
        "Senaste bygg-ID": str(state.get("latest_revision") or "Okänt")[:12],
        "Väntande bygg-ID": str(state.get("pending_revision") or "Inget")[:12],
        "Senaste kontrollförsök": checked,
        "Senast hittade release": state.get("latest") or "Okänd",
        "Status": status,
        "Ändringar i hämtad uppdatering": (state.get("pending_notes") or "Ingen ändringslista publicerad.")
            if version(pending) and (base / "data/update-pending").is_dir() else "Ingen hämtad uppdatering väntar.",
        "Senaste fel": state.get("error") or state.get("installation_error") or "Inget registrerat",
        "Kontrollintervall": "Var 12:e timme när appen körs",
        "Källa": f"GitHub Releases: {REPOSITORY} (endast stabila)",
    }


def start_updates(base, current_version):
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                check_once(base, current_version)
            except Exception:
                logger.warning("Release-uppdatering misslyckades; appen fortsätter", exc_info=True)
            # Kontrollera förfallotiden utan att göra extra nätverksanrop.
            stop.wait(60)

    threading.Thread(target=worker, name="release-updater", daemon=True).start()
    return stop


def apply_pending(base):
    """Installera före GUI-start. Spara backup och återställ vid skrivfel."""
    state = read_state(base)
    recover_pending(base, state)
    pending = base / "data/update-pending"
    if not version(state.get("pending", "")) or not pending.is_dir():
        return False
    hashes = state.get("pending_hashes")
    if hashes is not None and not matches_manifest(pending, hashes):
        raise ValueError("Hämtade appfiler har ändrats eller saknas; hämta uppdateringen igen")
    sources = [pending / name for name in FILES]
    if not all(path.is_file() for path in sources):
        return False
    sources += list((pending / "Icon").glob("*.png")) + list((pending / "Icon").glob("*.ico"))
    backup = base / "data/update-backup"
    if backup.exists():
        shutil.rmtree(backup)
    changed = []
    try:
        for source in sources:
            relative = source.relative_to(pending)
            target = base / relative
            saved = backup / relative
            existed = target.exists()
            if existed:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".update-tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
            changed.append((target, saved, existed))
        installed_hashes = state.pop("pending_hashes", None) or content_manifest(pending)
        state["installed_hashes"] = installed_hashes
        state.pop("restart_blocked", None)
        state.pop("installation_error", None)
        state.pop("error", None)
        state["status"] = "checked"
        state.pop("pending_notes", None)
        state["installed"] = state.pop("pending")
        revision = state.pop("pending_revision", None)
        if revision:
            state["installed_revision"] = revision
        else:
            state.pop("installed_revision", None)
        write_state(base, state)
    except Exception:
        for target, saved, existed in reversed(changed):
            if existed:
                shutil.copy2(saved, target)
            else:
                target.unlink(missing_ok=True)
        raise
    shutil.rmtree(pending)
    return True


# Windows-startprogram med egen ikon (delas med autostart).
def launcher_source(interpreter: Path, script: Path):
    def literal(value):
        return '@"' + str(value).replace('"', '""') + '"'

    return r'''
using System;
using System.Diagnostics;
using System.Text;
using System.Linq;
using System.Windows.Forms;
[assembly: System.Reflection.AssemblyTitle("FolderForge")]
[assembly: System.Reflection.AssemblyProduct("FolderForge")]
class FolderForgeLauncher {
    static string Quote(string value) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char ch in value) {
            if (ch == '\\') { slashes++; continue; }
            if (ch == '"') {
                result.Append('\\', slashes * 2 + 1).Append(ch);
            } else {
                result.Append('\\', slashes).Append(ch);
            }
            slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }
    [STAThread]
    static int Main(string[] args) {
        bool selftest = args.Contains("--selftest");
        if (!selftest && !args.Contains("--tray")) args = args.Concat(new[] { "--tray" }).ToArray();
        try {
            var info = new ProcessStartInfo();
            if (selftest) {
                info.FileName = INTERPRETER;
                info.Arguments = Quote(SCRIPT) + " " + String.Join(" ", args.Select(Quote).ToArray());
            } else {
                info.FileName = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
                string bootstrap = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(SCRIPT), "Starta-FolderForge.ps1");
                string encoded = Convert.ToBase64String(Encoding.UTF8.GetBytes(String.Join("\0", args)));
                info.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + Quote(bootstrap)
                    + " -PreferredPython " + Quote(INTERPRETER) + " -Arguments64 " + Quote(encoded);
            }
            info.WorkingDirectory = System.IO.Path.GetDirectoryName(SCRIPT);
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = selftest;
            info.RedirectStandardError = selftest;
            using (var process = Process.Start(info)) {
                if (selftest) {
                    Console.Write(process.StandardOutput.ReadToEnd());
                    Console.Error.Write(process.StandardError.ReadToEnd());
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            return 0;
        } catch (Exception error) {
            try {
                string logDir = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(SCRIPT), "logs");
                System.IO.Directory.CreateDirectory(logDir);
                System.IO.File.AppendAllText(System.IO.Path.Combine(logDir, "folderforge-errors.log"),
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " ERROR [launcher] " + error.ToString() + Environment.NewLine);
            } catch { }
            if (selftest) Console.Error.WriteLine(error.Message);
            else MessageBox.Show(error.Message, "FolderForge kunde inte starta");
            return 1;
        }
    }
}
'''.replace('INTERPRETER', literal(interpreter)).replace('SCRIPT', literal(script))


def ensure_launcher(base: Path, interpreter: Path, icon: Path, *, runner=None, compiler=None):
    """Compile a real .exe with our icon; never fall back to .pyw autostart."""
    base, interpreter, icon = base.resolve(), interpreter.resolve(), icon.resolve()
    if not interpreter.name.lower().startswith('pythonw'):
        interpreter = interpreter.with_name('pythonw.exe')
    if not interpreter.is_file():
        raise OSError('pythonw.exe saknas. Installera Windows-Python med GUI-stöd.')
    script = base / 'folder.pyw'
    if not script.is_file() or not icon.is_file():
        raise OSError('Appfil eller FolderForge-ikon saknas.')
    ensure_runtime_bootstrap(base)
    source = launcher_source(interpreter, script)
    fingerprint = hashlib.sha256(source.encode('utf-8') + icon.read_bytes()).hexdigest()
    folder = base / 'data/launcher'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'FolderForge.exe'
    manifest = folder / 'build.json'
    try:
        if target.is_file() and json.loads(manifest.read_text('utf-8')).get('fingerprint') == fingerprint:
            return target
    except (OSError, ValueError, AttributeError):
        pass
    if compiler is None:
        windows = Path(os.environ.get('WINDIR', r'C:\Windows'))
        compiler = next((windows / 'Microsoft.NET' / kind / 'v4.0.30319/csc.exe'
                         for kind in ('Framework64', 'Framework')
                         if (windows / 'Microsoft.NET' / kind / 'v4.0.30319/csc.exe').is_file()), None)
    if compiler is None:
        raise OSError('Windows .NET C#-kompilator saknas. Ingen Python-genväg registrerades som reserv.')
    run = runner or subprocess.run
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        temporary = Path(temporary)
        cs, output = temporary / 'Launcher.cs', temporary / 'FolderForge.exe'
        cs.write_text(source, encoding='utf-8-sig')
        result = run([str(compiler), '/nologo', '/target:winexe', '/optimize+',
                      '/reference:System.Windows.Forms.dll', '/reference:System.Core.dll',
                      f'/win32icon:{icon}', f'/out:{output}', str(cs)],
                     capture_output=True, text=True, timeout=60,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0 or not output.is_file():
            raise OSError('Kunde inte bygga FolderForge.exe: ' + str(result.stderr or result.stdout)[:500])
        os.replace(output, target)
    pending = manifest.with_suffix('.tmp')
    pending.write_text(json.dumps({'fingerprint': fingerprint}), encoding='utf-8')
    os.replace(pending, manifest)
    return target

# Hälsokontrollen måste köras från Tk-loopen, aldrig från en fristående tråd.
def _health_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.health-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def service_instance_health(lock_dir, script):
    folder = Path(lock_dir)
    pid = os.getpid()
    _health_write(folder / 'folderforge-health.json',
                  dict(pid=pid, script=str(Path(script).resolve()), updated=time.time()))
    for request in list(folder.glob('folderforge-probe-*.request'))[:32]:
        try:
            age = time.time() - request.stat().st_mtime
            if age > 60 or request.is_symlink() or request.stat().st_size > 2048:
                request.unlink(missing_ok=True)
                request.with_suffix('.reply').unlink(missing_ok=True)
                continue
            data = json.loads(request.read_text(encoding='utf-8'))
            if data.get('pid') == pid and data.get('nonce') == request.stem.removeprefix('folderforge-probe-'):
                _health_write(request.with_suffix('.reply'), dict(pid=pid, nonce=data['nonce']))
        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
            continue
    for reply in list(folder.glob('folderforge-probe-*.reply'))[:32]:
        try:
            if time.time() - reply.stat().st_mtime > 60:
                reply.unlink(missing_ok=True)
        except OSError:
            pass


def probe_instance(lock_dir, pid, timeout=8):
    """Ett färskt, unikt eko krävs. Gammal heartbeat räknas inte som ett svar."""
    import uuid
    if not isinstance(pid, int) or pid <= 0:
        return False
    nonce = uuid.uuid4().hex
    request = Path(lock_dir) / ('folderforge-probe-' + nonce + '.request')
    reply = request.with_suffix('.reply')
    try:
        _health_write(request, dict(pid=pid, nonce=nonce))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = json.loads(reply.read_text(encoding='utf-8'))
                if result.get('pid') == pid and result.get('nonce') == nonce:
                    return True
            except (OSError, ValueError, AttributeError):
                pass
            time.sleep(0.1)
        return False
    finally:
        request.unlink(missing_ok=True)
        reply.unlink(missing_ok=True)


def clear_instance_health(lock_dir):
    path = Path(lock_dir) / 'folderforge-health.json'
    try:
        if json.loads(path.read_text(encoding='utf-8')).get('pid') == os.getpid():
            path.unlink(missing_ok=True)
    except (OSError, ValueError, AttributeError):
        pass


def _verified_process_identity(info, argv, script, created, image):
    """Konservativ kontroll: exakt skript, riktig Python-process och samma starttid."""
    import ntpath
    def canonical(value):
        return ntpath.normcase(ntpath.normpath(str(value)))
    if not isinstance(info, dict) or len(argv) < 2:
        return False
    if not re.fullmatch(r'pythonw?(?:\d+(?:\.\d+)*)?\.exe', ntpath.basename(image), re.I):
        return False
    if canonical(argv[1]) != canonical(script):
        return False
    if canonical(info.get('ExecutablePath', '')) != canonical(image):
        return False
    try:
        return int(info['Created']) // 10 == created // 10
    except (KeyError, TypeError, ValueError):
        return False


class VerifiedFolderForgeProcess:
    """Windows-handtaget binder kontroll och avslut till samma process, inte bara PID."""
    def __init__(self, pid, script):
        if os.name != 'nt' or not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
            raise ValueError('Säker processidentifiering saknas; ingen process avslutas.')
        import ctypes
        from ctypes import wintypes
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.handle = self.api.OpenProcess(0x1000 | 0x100000 | 0x0001, False, pid)
        if not self.handle:
            raise OSError('Kunde inte öppna just denna process för säker identifiering.')
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.api.GetProcessTimes(self.handle, *[ctypes.byref(t) for t in times]):
                raise OSError('Kunde inte verifiera processens starttid.')
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            size = wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(size.value)
            if not self.api.QueryFullProcessImageNameW(self.handle, 0, image, ctypes.byref(size)):
                raise OSError('Kunde inte verifiera processens programfil.')
            command = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                       f"Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' | "
                       "Select-Object ProcessId,CommandLine,ExecutablePath,@{n='Created';e={$_.CreationDate.ToUniversalTime().ToFileTimeUtc().ToString()}} | ConvertTo-Json -Compress")
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                    capture_output=True, text=True, encoding='utf-8-sig', timeout=6,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
            info = json.loads(result.stdout)
            shell = ctypes.WinDLL('shell32', use_last_error=True)
            shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
            shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
            count = ctypes.c_int()
            pointer = shell.CommandLineToArgvW(info.get('CommandLine') or '', ctypes.byref(count))
            if not pointer:
                raise ValueError('Kommandoraden kunde inte identifieras.')
            self.api.LocalFree.argtypes = [ctypes.c_void_p]
            try:
                argv = [pointer[index] for index in range(count.value)]
            finally:
                self.api.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))
            if info.get('ProcessId') != pid or not _verified_process_identity(info, argv, script, created, image.value):
                raise ValueError('Processen kunde inte säkert identifieras som just denna FolderForge-installation.')
            if self.api.WaitForSingleObject(self.handle, 0) != 0x102:
                raise ValueError('Processen har redan avslutats eller kunde inte kontrolleras.')
        except Exception:
            self.close()
            raise

    def terminate_and_wait(self):
        state = self.api.WaitForSingleObject(self.handle, 0)
        if state == 0:
            return
        if state != 0x102 or not self.api.TerminateProcess(self.handle, 1):
            raise OSError('Processen avslutades inte. Ingen ny instans startas.')
        if self.api.WaitForSingleObject(self.handle, 5000) != 0:
            raise TimeoutError('Processen har ännu inte avslutats. Ingen ny instans startas.')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def recover_unresponsive_instance(lock, script):
    """Andra starter förblir dolda om Tk svarar. Aldrig automatiskt tvångsavslut."""
    try:
        pid = lock.read_owner_pid()
        deadline = time.monotonic() + 2
        while not pid and time.monotonic() < deadline:
            time.sleep(0.1)
            pid = lock.read_owner_pid()
        responding = probe_instance(lock.lock_dir, pid)
        current_owner = lock.read_owner_pid()
        if not responding and current_owner and current_owner != pid:
            pid = current_owner
            responding = probe_instance(lock.lock_dir, pid, timeout=2)
        if responding:
            logger.info('Befintlig FolderForge-instans svarar (pid=%s); ny start avslutas dold', pid)
            return False
        logger.warning('Hälsokontrollen fick inget svar (pid=%s); kan vara upptagen eller ha hängt sig', pid)
        if os.name != 'nt':
            return False
        import ctypes
        dialog = ctypes.WinDLL('user32', use_last_error=True).MessageBoxW
        dialog.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        process = None
        try:
            process = VerifiedFolderForgeProcess(pid, script)
            text = (f'FolderForge (PID {pid}) svarar inte på hälsokontrollen. Den kan vara tillfälligt upptagen eller vara en äldre version utan hälsokontroll.\n\n'
                    'Vill du tvinga just denna verifierade instans att avslutas och starta om minimerat? '
                    'Osparad inmatning kan gå förlorad och pågående arbete kan avbrytas. Andra Python-program avslutas inte.')
            if dialog(None, text, 'FolderForge — återställning', 0x134) != 6:
                return False
            if probe_instance(lock.lock_dir, pid, timeout=2):
                dialog(None, 'Appen svarar igen. Ingen process avslutades.', 'FolderForge', 0x40)
                return False
            process.terminate_and_wait()
        except Exception as exc:
            logger.exception('Säker återstart av befintlig instans avbröts')
            dialog(None, str(exc) + '\nIngen annan process avslutas. Använd Avsluta i FolderForges tray-meny om möjligt.',
                   'FolderForge — återstart avbruten', 0x30)
            return False
        finally:
            if process:
                process.close()
        # OS-låset måste fortfarande vinnas; ta aldrig bort ett aktivt lås manuellt.
        if not lock.acquire() or not lock.is_primary:
            dialog(None, 'En annan instans hann starta. Ingen extra instans startas.', 'FolderForge', 0x40)
            return False
        logger.info('Verifierad instans avslutad efter användarens godkännande; startar om minimerat')
        return True
    except Exception:
        logger.exception('Kunde inte utföra hälsokontroll; ingen process avslutas')
        return False


# Bootstrap scripts are embedded so older installers that stage only the original
# Python files can still upgrade safely to the new startup flow.
def ensure_runtime_bootstrap(base):
    base = Path(base)
    for name, content in RUNTIME_BOOTSTRAP_FILES.items():
        target = base / name
        encoding = 'utf-8-sig' if name.endswith('.ps1') else 'utf-8'
        payload = content.encode(encoding)
        if target.is_file() and target.read_bytes() == payload:
            continue
        fd, temporary = tempfile.mkstemp(prefix='.bootstrap-', dir=base)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return base / 'Starta-FolderForge.ps1'


def launch_runtime_bootstrap(base, interpreter, arguments):
    import base64
    script = ensure_runtime_bootstrap(base)
    encoded = base64.b64encode('\0'.join(arguments).encode('utf-8')).decode('ascii')
    windows = Path(os.environ.get('WINDIR', r'C:\Windows'))
    powershell = windows / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                      '-File', str(script), '-PreferredPython', str(interpreter), '-Arguments64', encoded],
                     cwd=str(base), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)


RUNTIME_BOOTSTRAP_FILES = {
'Starta-FolderForge.ps1': r'''param([string]$PreferredPython = '', [string]$Arguments64 = '', [switch]$MaintenanceOnly)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Logs = Join-Path $Root 'logs'
$Data = Join-Path $Root 'data'
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
try {
    [IO.Directory]::CreateDirectory($Logs) | Out-Null
    [IO.Directory]::CreateDirectory($Data) | Out-Null
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    if (-not $MaintenanceOnly) { [Windows.Forms.MessageBox]::Show('FolderForge needs a writable app folder. ' + $_.Exception.Message, 'FolderForge') | Out-Null }
    exit 1
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Write-RuntimeLog([string]$Level, [string]$Message) {
    $Line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " $Level [runtime:0] [bootstrap] $Message"
    try {
        [IO.File]::AppendAllText((Join-Path $Logs 'folderforge.log'), $Line + [Environment]::NewLine, $Utf8NoBom)
        if ($Level -in @('WARNING','ERROR')) {
            [IO.File]::AppendAllText((Join-Path $Logs 'folderforge-errors.log'), $Line + [Environment]::NewLine, $Utf8NoBom)
        }
    } catch { }
}
function Write-CommandFailure([string]$Stage, $Result) {
    $Detail = ([string]$Result.Err).Trim()
    if (-not $Detail) { $Detail = ([string]$Result.Out).Trim() }
    if ($Detail.Length -gt 4000) { $Detail = $Detail.Substring($Detail.Length - 4000) }
    Write-RuntimeLog WARNING ($Stage + ' failed (' + $Result.Code + '): ' + $Detail)
}
function Quote-Argument([string]$Value) {
    # CommandLineToArgvW-compatible quoting, including trailing backslashes.
    return '"' + ([regex]::Replace($Value, '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}
function Invoke-Hidden([string]$File, [string[]]$Arguments) {
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $File
    $Info.Arguments = (($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Info.WorkingDirectory = $Root
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.EnvironmentVariables.Remove('PYTHONHOME')
    $Info.EnvironmentVariables.Remove('PYTHONPATH')
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $Info.StandardErrorEncoding = [Text.Encoding]::UTF8
    $Process = [Diagnostics.Process]::Start($Info)
    try {
        $Out = $Process.StandardOutput.ReadToEndAsync()
        $Err = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        return [pscustomobject]@{ Code = $Process.ExitCode; Out = $Out.Result; Err = $Err.Result }
    } finally { $Process.Dispose() }
}
function Get-PythonInfo([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $null }
    if ($Executable -match '\\Microsoft\\WindowsApps\\') { return $null } # Store alias is not an installation.
    if ([IO.Path]::GetFileName($Executable) -match '^pythonw') { $Executable = Join-Path (Split-Path $Executable) 'python.exe' }
    try {
        $Code = 'import sys,json; print(json.dumps(dict(version=list(sys.version_info[:3]), stable=sys.version_info.releaselevel=="final", base=sys.base_prefix, executable=getattr(sys,"_base_executable",sys.executable))))'
        $Result = Invoke-Hidden $Executable @('-I','-c',$Code)
        if ($Result.Code -ne 0) { return $null }
        $Info = $Result.Out.Trim() | ConvertFrom-Json
        if ($Info.version.Count -ne 3) { return $null }
        $Info | Add-Member -NotePropertyName Console -NotePropertyValue $Executable
        return $Info
    } catch { return $null }
}
function Test-AppRunning {
    foreach ($Name in @('Global\FolderForge_SingleInstance_Mutex','Local\FolderForge_SingleInstance_Mutex')) {
        try {
            $Mutex = [Threading.Mutex]::OpenExisting($Name)
            $Mutex.Dispose()
            return $true
        } catch [Threading.WaitHandleCannotBeOpenedException] { }
    }
    return $false
}
function Read-RuntimeState {
    $Path = Join-Path $Data 'python-runtime.json'
    if (Test-Path -LiteralPath $Path) {
        try { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json } catch { }
    }
    return $null
}
function Save-RuntimeState($State) {
    $Path = Join-Path $Data 'python-runtime.json'
    $Temp = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($Temp, ($State | ConvertTo-Json), [Text.Encoding]::UTF8)
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($Temp, $Path, $null) }
        else { [IO.File]::Move($Temp, $Path) }
    } finally { if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp } }
}
function Test-Environment([string]$Console) {
    $Code = 'import tkinter,customtkinter,PIL,pystray,pynput,win32api,tkinterdnd2; import importlib.metadata; print("OK")'
    $Check = Invoke-Hidden $Console @('-c',$Code)
    if ($Check.Code -ne 0) { Write-CommandFailure 'Environment imports' $Check; return $false }
    $Check = Invoke-Hidden $Console @('-m','pip','--isolated','check','--disable-pip-version-check')
    if ($Check.Code -ne 0) {
        Write-CommandFailure 'Shared environment dependency conflicts' $Check
        $script:RuntimeDependencyConflicts = $true
    }
    return $true # Unrelated shared-package conflicts must not block valid app imports.
}
function Get-LatestStableSeries {
    # Discover current stable CPython from the public winget manifests; no hard-coded release.
    $Headers = @{ 'User-Agent' = 'FolderForge'; 'Accept' = 'application/vnd.github+json' }
    $Url = 'https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/p/Python/Python/3'
    $Folders = Invoke-RestMethod -Uri $Url -Headers $Headers -TimeoutSec 20
    $Series = @($Folders |
        Where-Object { $_.name -match '^\d+$' } | Sort-Object { [int]$_.name } -Descending)
    foreach ($Item in $Series) {
        $Releases = Invoke-RestMethod -Uri $Item.url -Headers $Headers -TimeoutSec 20
        $Versions = @($Releases |
            Where-Object { $_.name -match '^3\.\d+\.\d+$' })
        if ($Versions.Count -gt 0) { return ('3.' + $Item.name) }
    }
    throw 'No stable Python release could be verified. No installation was attempted.'
}
function Get-WeeklyBoundary([datetime]$Now) {
    # Local clock, Monday 08:00; before that time belongs to the preceding week.
    $Days = (([int]$Now.DayOfWeek + 6) % 7)
    $Boundary = $Now.Date.AddDays(-$Days).AddHours(8)
    if ($Now -lt $Boundary) { $Boundary = $Boundary.AddDays(-7) }
    return $Boundary
}
function Test-PythonBusy {
    try { return @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'").Count -gt 0 }
    catch { Write-RuntimeLog WARNING 'Could not verify that shared Python is idle; maintenance deferred.'; return $true }
}
function Ensure-WeeklyTask($State) {
    try {
        $Digest = [Security.Cryptography.SHA256]::Create()
        try { $RootId = ([BitConverter]::ToString($Digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant())))).Replace('-','').Substring(0,12) }
        finally { $Digest.Dispose() }
        $Name = 'FolderForge Python weekly ' + $RootId
        $Hash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
        $Existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        if ($Existing -and $State.WeeklyTaskHash -eq $Hash) { return }
        $WindowlessHost = Join-Path ([Environment]::GetFolderPath('System')) 'wscript.exe'
        $Arguments = (Quote-Argument (Join-Path $Root 'Starta-FolderForge.vbs')) + ' --maintenance'
        $Action = New-ScheduledTaskAction -Execute $WindowlessHost -Argument $Arguments -WorkingDirectory $Root
        $Trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At '08:00'
        $Principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
        $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 12 -RestartInterval (New-TimeSpan -Minutes 15)
        Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
        $State.WeeklyTaskHash = $Hash
        Write-RuntimeLog INFO 'Shared Python/package maintenance scheduled Mondays at 08:00 local time; missed runs start when available.'
    } catch { Write-RuntimeLog WARNING ('Could not register weekly task; overdue checks run at next app start. ' + $_.Exception.Message) }
}
$Maintenance = New-Object Threading.Mutex($false, 'Local\FolderForge_RuntimeMaintenance')
$Held = $false
$ExitCode = 0
try {
    try { $Held = $Maintenance.WaitOne(300000) } catch [Threading.AbandonedMutexException] { $Held = $true }
    if (-not $Held) { throw 'Another runtime check is still active. Try starting again later.' }
    Push-Location $Root
    $Loaded = Read-RuntimeState
    $State = @{}
    if ($Loaded) { foreach ($Property in $Loaded.PSObject.Properties) { $State[$Property.Name] = $Property.Value } }
    $Now = Get-Date
    if (-not $State.WeeklyEnabledAt) { $State.WeeklyEnabledAt = $Now.ToString('o') }
    Ensure-WeeklyTask $State
    Save-RuntimeState $State
    $Boundary = Get-WeeklyBoundary $Now
    $Due = $Boundary -ge ([datetime]$State.WeeklyEnabledAt) -and
        (-not $State.LastAttemptPeriod -or ([datetime]$State.LastAttemptPeriod) -lt $Boundary)
    $LegacyConsole = [string]$State.Console
    if ($MaintenanceOnly -and -not $Due) {
        Write-RuntimeLog INFO 'Weekly maintenance already handled or not yet due; scheduled run skipped.'
        exit 0
    }
    $Candidates = New-Object 'Collections.Generic.List[string]'
    $Registry = @()
    if ($State -and $State.Console) { $Candidates.Add([string]$State.Console) }
    if ($PreferredPython) { $Candidates.Add($PreferredPython) }
    foreach ($Hive in @('HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore','HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        if (Test-Path $Hive) {
            foreach ($Key in Get-ChildItem $Hive) {
                $Install = Get-Item ($Key.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
                if ($Install) {
                    $Home = [string]$Install.GetValue('')
                    if ($Home) {
                        $Scope = if ($Hive.StartsWith('HKCU:')) { 'user' } else { 'machine' }
                        $Registry += [pscustomobject]@{ Home = $Home.TrimEnd('\'); Scope = $Scope }
                        $Candidates.Add((Join-Path $Home 'python.exe'))
                    }
                }
            }
        }
    }
    foreach ($Name in @('python.exe','python3.exe','pythonw.exe')) {
        foreach ($Command in @(Get-Command $Name -All -ErrorAction SilentlyContinue)) { $Candidates.Add($Command.Source) }
    }
    # Resolve real Microsoft Store runtimes without executing an uninstalled Store alias.
    if (Get-Command 'Get-AppxPackage' -ErrorAction SilentlyContinue) {
        foreach ($Store in @(Get-AppxPackage -Name 'PythonSoftwareFoundation.Python.3*' -ErrorAction SilentlyContinue)) {
            if ($Store.InstallLocation) { $Candidates.Add((Join-Path $Store.InstallLocation 'python.exe')) }
        }
    }
    $Py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($Py) {
        $Listed = Invoke-Hidden $Py.Source @('-0p')
        foreach ($Line in ($Listed.Out -split "`n")) {
            if ($Line -match '([A-Za-z]:\\.*pythonw?\.exe)\s*$') { $Candidates.Add($Matches[1].Trim()) }
        }
    }
    $Info = $null
    $Detected = @()
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        $Found = Get-PythonInfo $Candidate
        if ($Found) { $Detected += $Found }
    }
    $Supported = @($Detected | Where-Object { $_.stable -and [version]($_.version[0..1] -join '.') -ge [version]'3.11' })
    if ($Supported.Count -gt 0) { $Info = $Supported[0] }
    elseif ($Detected.Count -gt 0) { $Info = $Detected[0] }
    $InstalledNow = $false
    $Winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    $Running = Test-AppRunning
    if (-not $Info) {
        $ExistingCandidates = @($Candidates | Where-Object { $_ -notmatch '\\Microsoft\\WindowsApps\\' -and (Test-Path -LiteralPath $_ -PathType Leaf) })
        if ($Registry.Count -gt 0 -or $ExistingCandidates.Count -gt 0) { throw 'Python is registered but cannot be used. Repair that installation; no second Python was installed.' }
        if ($Running) { throw 'FolderForge is already running; runtime changes were deferred.' }
        if (-not $Winget) { throw 'Python is missing and Windows App Installer (winget) is unavailable. Install App Installer, then retry.' }
        if (Test-PythonBusy) { throw 'A Python process exists but its installation could not be identified safely. No additional Python was installed.' }
        if ($MaintenanceOnly -and $Due) {
            $State.LastAttemptPeriod = $Boundary.ToString('o')
            $State.LastAttemptAt = (Get-Date).ToString('o')
            $State.LastResult = 'running'
            Save-RuntimeState $State
        }
        $Series = Get-LatestStableSeries
        Write-RuntimeLog INFO "Python is missing. Installing stable Python $Series once."
        $Installed = Invoke-Hidden $Winget.Source @('install','--id',"Python.Python.$Series",'--exact','--source','winget','--scope','user','--silent','--disable-interactivity','--accept-source-agreements','--accept-package-agreements')
        if ($Installed.Code -ne 0) { Write-CommandFailure 'Python installation' $Installed; throw "Python installation failed ($($Installed.Code))." }
        $Home = (Get-Item "HKCU:\Software\Python\PythonCore\$Series\InstallPath").GetValue('')
        $Info = Get-PythonInfo (Join-Path $Home 'python.exe')
        if (-not $Info) { throw 'The new Python installation could not be verified.' }
        $InstalledNow = $true
    }
    if (-not $Info.stable) { throw 'Only a prerelease Python was found. No additional Python was installed. Select a stable existing installation.' }
    $Series = "$($Info.version[0]).$($Info.version[1])"
    if ([version]$Series -lt [version]'3.11') { throw "Existing Python $Series is too old. No parallel Python was installed. Upgrade it explicitly to Python 3.11+ first." }
    # Use the actual shared base interpreter, never the old app virtual environment.
    $Console = [string]$Info.executable
    if (-not $Running) {
        $State.Console = $Console
        $State.Base = [string]$Info.base
        $State.Version = ($Info.version -join '.')
        Save-RuntimeState $State
    }
    if ($Running) {
        Write-RuntimeLog INFO 'FolderForge is running. Package changes deferred; no maintenance attempt recorded.'
        if ($MaintenanceOnly) { $ExitCode = 2 }
        else {
            # A secondary start may use the still-running legacy environment only to
            # reach the existing instance's health/recovery flow during migration.
            if ($LegacyConsole -and (Test-Path -LiteralPath $LegacyConsole)) { $Console = $LegacyConsole }
        }
    } else {
        if ($Due) {
            if (Test-PythonBusy) {
                Write-RuntimeLog INFO 'Shared Python is in use. Weekly maintenance deferred without stopping programs.'
                if ($MaintenanceOnly) { $ExitCode = 2 }
            } else {
                # Record before network/mutation: repeated starts or offline failures
                # must not perform repeated update rounds during the same week.
                $State.LastAttemptPeriod = $Boundary.ToString('o')
                $State.LastAttemptAt = (Get-Date).ToString('o')
                $State.LastResult = 'running'
                Save-RuntimeState $State
                Write-RuntimeLog INFO 'Weekly shared Python/package maintenance started.'
                if (-not $InstalledNow) {
                    $Official = @($Registry | Where-Object { $_.Home -eq ([string]$Info.base).TrimEnd('\') })
                    if ($Winget -and $Official.Count -gt 0) {
                        $Upgrade = Invoke-Hidden $Winget.Source @('upgrade','--id',"Python.Python.$Series",'--exact','--source','winget','--scope',$Official[0].Scope,'--silent','--disable-interactivity','--accept-source-agreements','--accept-package-agreements')
                        $ExitHex = '{0:X8}' -f ([long]$Upgrade.Code -band 4294967295)
                        if ($Upgrade.Code -eq 0) { Write-RuntimeLog INFO 'Existing shared Python installation updated.' }
                        elseif ($ExitHex -in @('8A15002B','8A15004F')) { Write-RuntimeLog INFO 'Shared Python is already current in its existing series.' }
                        else { Write-CommandFailure 'Python upgrade' $Upgrade; Write-RuntimeLog WARNING 'Existing Python retained. No install fallback.' }
                    } else { Write-RuntimeLog WARNING 'Existing Python cannot be upgraded safely with winget; no other Python is installed.' }
                }
                $Code = 'import sys,json; sys.path.insert(0,sys.argv[1]); import settings; print(json.dumps(sorted(set(p for p in settings.REQUIRED_PACKAGES.values() if p))))'
                $Requirements = Invoke-Hidden $Console @('-c',$Code,$Root)
                if ($Requirements.Code -ne 0) { throw 'Could not read app package requirements.' }
                $Packages = @($Requirements.Out | ConvertFrom-Json)
                if ($Packages.Count -eq 0 -or @($Packages | Where-Object { $_ -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$' }).Count -gt 0) { throw 'Invalid app package requirements.' }
                $PipOptions = @('-m','pip','--isolated','--cache-dir',(Join-Path $Data 'python-pip-cache'))
                $NetworkOptions = @('--disable-pip-version-check','--index-url','https://pypi.org/simple','--timeout','15','--retries','1')
                $Pip = Invoke-Hidden $Console ($PipOptions + @('install','--upgrade','--upgrade-strategy','only-if-needed') + $NetworkOptions + @('pip') + $Packages)
                if ($Pip.Code -ne 0) { Write-CommandFailure 'Shared package upgrade' $Pip; $State.LastResult = 'failed' }
                elseif (-not (Test-Environment $Console)) { $State.LastResult = 'verification_failed' }
                else {
                    $State.LastResult = if ($script:RuntimeDependencyConflicts) { 'completed_with_conflicts' } else { 'completed' }
                    Write-RuntimeLog INFO ('Weekly shared Python/package maintenance: ' + $State.LastResult)
                }
                Save-RuntimeState $State
                if ($State.LastResult -in @('failed','verification_failed')) {
                    Write-RuntimeLog ERROR 'Weekly shared-package maintenance failed. Review the error log; shared packages may have changed.'
                    $ExitCode = 1
                    if (-not $MaintenanceOnly -and -not (Test-Environment $Console)) { throw 'Shared packages failed validation after maintenance. Review the error log before restarting.' }
                }
            }
        } else { Write-RuntimeLog INFO 'No weekly maintenance due; no online Python/package update check at this start.' }
        if (-not $MaintenanceOnly) {
            # Initial setup/migration may install missing packages, but pins all
            # installed distributions: it cannot upgrade existing packages off-schedule.
            $Probe = 'import sys,json,importlib.metadata as m; sys.path.insert(0,sys.argv[1]); import settings; names=sorted(set(p for p in settings.REQUIRED_PACKAGES.values() if p)); found={d.metadata["Name"].lower().replace("_","-") for d in m.distributions() if d.metadata["Name"]}; print(json.dumps([n for n in names if n.lower().replace("_","-") not in found]))'
            $MissingResult = Invoke-Hidden $Console @('-c',$Probe,$Root)
            if ($MissingResult.Code -ne 0) { throw 'Could not inspect required packages locally.' }
            $Missing = @($MissingResult.Out | ConvertFrom-Json)
            if ($Missing.Count -gt 0) {
                if (Test-PythonBusy) { throw 'Required shared packages are missing, but Python is in use. Close Python programs and start FolderForge again.' }
                $Pins = Join-Path $Data ('runtime-pins-' + [guid]::NewGuid().ToString('N') + '.txt')
                try {
                    $PinCode = 'import importlib.metadata as m; names=sorted({d.metadata["Name"] for d in m.distributions() if d.metadata["Name"]}); print("\n".join(n+"=="+m.version(n) for n in names))'
                    $PinResult = Invoke-Hidden $Console @('-c',$PinCode)
                    if ($PinResult.Code -ne 0) { throw 'Could not pin installed packages. No package installation attempted.' }
                    [IO.File]::WriteAllText($Pins,$PinResult.Out,$Utf8NoBom)
                    $HasPip = Invoke-Hidden $Console @('-m','pip','--version')
                    if ($HasPip.Code -ne 0) {
                        $Ensure = Invoke-Hidden $Console @('-m','ensurepip')
                        if ($Ensure.Code -ne 0) { Write-CommandFailure 'Missing pip' $Ensure; throw 'pip is missing and could not be installed.' }
                    }
                    $Install = Invoke-Hidden $Console (@('-m','pip','--isolated','install','--constraint',$Pins,'--disable-pip-version-check','--index-url','https://pypi.org/simple','--timeout','15','--retries','1') + $Missing)
                    if ($Install.Code -ne 0) { Write-CommandFailure 'Missing shared packages' $Install; throw 'Missing shared packages could not be installed without changing existing versions. See the error log.' }
                    Write-RuntimeLog INFO 'Missing shared packages installed; existing versions were pinned and not upgraded.'
                } finally { if (Test-Path -LiteralPath $Pins) { Remove-Item -LiteralPath $Pins } }
            }
        }
    }
    if (-not $MaintenanceOnly) {
        $Windowless = Join-Path (Split-Path $Console) 'pythonw.exe'
        if (-not (Test-Path -LiteralPath $Windowless -PathType Leaf)) { throw 'pythonw.exe is unavailable. Start aborted instead of opening a console.' }
        if (-not $Running) {
            # Refresh cached launchers too, so a later missing-Python start can bootstrap itself.
            $BrandCode = 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from updater import ensure_launcher; ensure_launcher(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[1])/"Icon"/"projektmapp.ico")'
            try {
                $Brand = Invoke-Hidden $Console @('-I','-c',$BrandCode,$Root,$Windowless)
                if ($Brand.Code -ne 0) { Write-RuntimeLog WARNING 'Native launcher refresh failed; use Starta-FolderForge.vbs if needed.' }
            } catch { Write-RuntimeLog WARNING 'Native launcher refresh failed; use Starta-FolderForge.vbs if needed.' }
        }
        $AppArgs = @('--tray')
        if ($Arguments64) { $AppArgs = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Arguments64)).Split(@([char]0), [StringSplitOptions]::RemoveEmptyEntries)) }
        $env:FOLDERFORGE_RUNTIME_READY = '1'
        $env:FOLDERFORGE_RUNTIME_POLICY = 'weekly-shared'
        $env:FOLDERFORGE_RUNTIME_SECONDARY = if ($Running) { '1' } else { '0' }
        $Start = New-Object Diagnostics.ProcessStartInfo
        $Start.FileName = $Windowless
        $Start.Arguments = (Quote-Argument (Join-Path $Root 'folder.pyw')) + ' ' + (($AppArgs | ForEach-Object { Quote-Argument $_ }) -join ' ')
        $Start.WorkingDirectory = $Root
        $Start.UseShellExecute = $false
        $Start.CreateNoWindow = $true
        $Start.EnvironmentVariables.Remove('PYTHONHOME')
        $Start.EnvironmentVariables.Remove('PYTHONPATH')
        $Child = [Diagnostics.Process]::Start($Start)
        # Keep maintenance serialized until the app owns its lock, even on slow startup.
        try {
            while (-not $Child.HasExited -and -not (Test-AppRunning)) { Start-Sleep -Milliseconds 100 }
        } finally { $Child.Dispose() }
    }
} catch {
    Write-RuntimeLog ERROR $_.Exception.Message
    if ($State -and $State.LastResult -eq 'running') {
        $State.LastResult = 'failed'
        try { Save-RuntimeState $State } catch { }
    }
    if (-not $MaintenanceOnly) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'FolderForge - Python check') | Out-Null
    }
    $ExitCode = 1
} finally {
    if ($Held) { $Maintenance.ReleaseMutex() }
    $Maintenance.Dispose()
    if ((Get-Location).Path -eq $Root) { Pop-Location }
}
exit $ExitCode
''',
'Starta-FolderForge.vbs': r'''Option Explicit
Dim shell, fs, script, command, result
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
script = fs.BuildPath(fs.GetParentFolderName(WScript.ScriptFullName), "Starta-FolderForge.ps1")
command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & script & """"
If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "--maintenance" Then
        command = command & " -MaintenanceOnly"
        result = shell.Run(command, 0, True)
        WScript.Quit result
    End If
End If
shell.Run command, 0, False
''',
}
