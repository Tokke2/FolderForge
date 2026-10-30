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
FILES = frozenset({"folder.pyw", "settings.py", "historik.py", "logg.py", "updater.py", "cache_cleanup.py"})
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


def get_update_activity(base):
    """Lättviktig UI-modell, utan nätverk eller filhashning."""
    state = read_state(base)
    received, total = state.get("downloaded", 0), state.get("download_total")
    progress = None
    if isinstance(received, (int, float)) and isinstance(total, (int, float)) and total > 0:
        progress = max(0.0, min(1.0, received / total))
    ready = bool(version(state.get("pending", "")) and (base / "data/update-pending").is_dir())
    return {"busy": _check_lock.locked(), "ready": ready, "progress": progress,
            "phase": state.get("status", "idle"), "error": state.get("error", "")}


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
        status = f"{pending} är hämtad och väntar på nästa appstart."
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
        "Senaste fel": state.get("error") or "Inget registrerat",
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
            info.FileName = INTERPRETER;
            info.Arguments = Quote(SCRIPT) + " " + String.Join(" ", args.Select(Quote).ToArray());
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
                string logDir = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(SCRIPT), "data", "logs");
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
