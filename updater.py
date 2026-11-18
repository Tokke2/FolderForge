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
OPTIONAL_FILES = frozenset({"os_startup.py", "qt_help.py", "qt_integrations.py", "gui_entry.py", "qt_diagnostics.py", "Starta-FolderForge-Tk.py", "requirements-tk.txt", "app_core.py", "instance_lock.py", "qt_app.py", "workspace.py", "qt_preview.py", "Starta-FolderForge-Qt.py", "requirements-qt.txt", "Starta-FolderForge.py", "requirements.txt", "Starta-FolderForge.sh",
    "Starta-FolderForge.app/Contents/Info.plist", "Starta-FolderForge.app/Contents/MacOS/FolderForge",
    "Starta-FolderForge.app/Contents/Resources/folderforge.icns"})
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
            allowed = name in FILES | OPTIONAL_FILES or (len(relative.parts) == 2 and relative.parts[0] == "Icon"
                       and relative.suffix.lower() in {".png", ".ico", ".icns", ".svg"})
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
            and (str(file.relative_to(root).as_posix()) in FILES | OPTIONAL_FILES
                 or (len(file.relative_to(root).parts) == 2
                     and file.relative_to(root).parts[0] == "Icon"
                     and file.suffix.lower() in {".png", ".ico", ".icns", ".svg"}))}


def matches_manifest(root, manifest):
    if not isinstance(manifest, dict) or not FILES.issubset(manifest):
        return False
    try:
        for name, digest in manifest.items():
            relative = PurePosixPath(name)
            if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                    or not (name in FILES | OPTIONAL_FILES or (len(relative.parts) == 2 and relative.parts[0] == "Icon"
                                              and relative.suffix.lower() in {".png", ".ico", ".icns", ".svg"}))):
                return False
            file = root / name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def manifest_differences(base, manifest):
    """Names only, never contents; invalid paths are not accessed."""
    if not isinstance(manifest, dict) or not FILES.issubset(manifest):
        return ['ogiltigt eller ofullständigt manifest']
    result = []
    for name, digest in manifest.items():
        if not _app_relative(name):
            return ['otillåten manifestsökväg']
        path = Path(base) / name
        try:
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                result.append(name)
        except OSError:
            result.append(name + ' (kunde inte läsas)')
    return result[:30]


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
    if read_state(base).get('startup_pending') or not _check_lock.acquire(blocking=False):
        return False
    try:
        _checked_once(base, current_version, now, force=force)
        return True
    finally:
        _check_lock.release()


def pending_ready_for_restart(base):
    state = read_state(base)
    if state.get('startup_pending'):
        return False

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


def launch_portable(base=None, interpreter=None):
    """Start hidden using existing Python only; no shell, pip or installations."""
    import sys
    base = Path(base or Path(__file__).resolve().parent).resolve()
    interpreter = Path(interpreter or sys.executable)
    if os.name == 'nt':
        return launch_runtime_bootstrap(base, interpreter, ['--tray'])
    logs = base / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    journal = base / 'data/update-transaction.json'
    supervisor = base / 'data/update-supervisor.py'
    if journal.exists():
        if not supervisor.is_file():
            raise OSError('Återställningsövervakaren saknas; säkerhetskopian lämnas orörd')
        args = [str(interpreter), str(supervisor), '--recover', str(base), str(interpreter)]
    else:
        args = [str(interpreter), str(base / 'folder.pyw'), '--tray']
    with (logs / 'folderforge-errors.log').open('ab') as errors:
        return subprocess.Popen(args, cwd=base, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=errors,
                                start_new_session=True, close_fds=True)


def supervise_update(base, interpreter, recover=False, timeout=90, offer=None):
    # Serialize workers before inspecting a journal or offering recovery.
    handle = None
    lock_stream = None
    if os.name == 'nt':
        import ctypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        api.CreateMutexW.restype = ctypes.c_void_p
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        name = 'Local\\FolderForge_Update_' + hashlib.sha256(str(Path(base).resolve()).lower().encode()).hexdigest()[:16]
        ctypes.set_last_error(0)
        handle = api.CreateMutexW(None, False, name)
        if not handle:
            raise OSError('Uppdateringslåset kunde inte tas')
        if ctypes.get_last_error() == 183:
            api.CloseHandle(handle)
            return 0
    else:
        import fcntl
        folder = Path(base) / 'data'
        folder.mkdir(parents=True, exist_ok=True)
        lock_stream = (folder / 'update-supervisor.lock').open('a+b')
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_stream.close()
            return 0
    try:
        return _supervise_update(base, interpreter, recover, timeout, offer)
    finally:
        if handle:
            api.CloseHandle(handle)
        if lock_stream:
            lock_stream.close()


# A stable copy of this module supervises a candidate, even if new imports fail.
def _write_transaction(base, value):
    path = Path(base) / 'data/update-transaction.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.transaction-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_transaction(base):
    path = Path(base) / 'data/update-transaction.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text('utf-8'))
    if not isinstance(value, dict) or not isinstance(value.get('token'), str):
        raise ValueError('Ogiltig uppdateringstransaktion; ingen automatisk ändring görs')
    return value


def _app_relative(name):
    path = PurePosixPath(name)
    return (isinstance(name, str) and '\\' not in name and '..' not in path.parts
            and not path.is_absolute() and (name in FILES | OPTIONAL_FILES or
            len(path.parts) == 2 and path.parts[0] == 'Icon' and path.suffix.lower() in {'.png', '.ico', '.icns', '.svg'}))


def _invalidate_app_bytecode(base):
    """Discard only our generated bytecode, never package caches or user data."""
    cache = Path(base) / '__pycache__'
    if cache.is_symlink():
        raise ValueError('Appens bytekodscache är en symbolisk länk')
    for name in FILES | OPTIONAL_FILES:
        if Path(name).suffix == '.py':
            for entry in cache.glob(Path(name).stem + '.*.pyc'):
                entry.unlink(missing_ok=True)


def rollback_update(base):
    """Restore only journaled app files; never settings, projects, history or logs."""
    base = Path(base)
    journal = read_transaction(base)
    if not journal:
        return False
    if _app_mutex_exists():
        raise RuntimeError('Stäng FolderForge före återställning; inga processer avslutas automatiskt')
    entries = journal.get('files')
    if not isinstance(entries, dict) or not entries or not all(_app_relative(n) for n in entries):
        raise ValueError('Otillåten sökväg i återställningen')
    backup = base / 'data/update-backup'
    # Validate the ENTIRE backup before changing any current file.
    for name, digest in entries.items():
        target, saved = base / name, backup / name
        if target.is_symlink() or saved.is_symlink():
            raise ValueError('Symbolisk länk bland appfiler')
        if any(parent.is_symlink() for parent in list(target.parents)[:len(Path(name).parts)] + list(saved.parents)[:len(Path(name).parts)]):
            raise ValueError('Symbolisk länk i återställningen')
        if digest is not None and (not saved.is_file() or hashlib.sha256(saved.read_bytes()).hexdigest() != digest):
            raise ValueError('Säkerhetskopian saknas eller har ändrats: ' + name)
    for name, digest in entries.items():
        target = base / name
        if digest is None:
            target.unlink(missing_ok=True)
        else:
            temporary = target.with_name(target.name + '.rollback-tmp')
            shutil.copy2(backup / name, temporary)
            os.replace(temporary, target)
    _invalidate_app_bytecode(base)
    state = dict(journal['previous_state'])
    for key in ('pending', 'pending_hashes', 'pending_revision', 'pending_notes'):
        state.pop(key, None)
    state.update(status='error', restart_blocked=True,
                 installation_error='Föregående app återställd efter misslyckad start.', startup_pending=False)
    write_state(base, state)
    (base / 'data/update-transaction.json').unlink()
    return True


def confirm_startup(base):
    """Called by a live Tk callback only after the hidden GUI and tray are ready."""
    journal = read_transaction(base)
    if not journal or journal.get('phase') == 'confirmed':
        return False
    if (os.environ.get('FOLDERFORGE_UPDATE_TOKEN') != journal['token']
            or journal.get('trial_pid') != os.getpid()):
        return False
    state = read_state(base)
    if not matches_manifest(Path(base), state.get('installed_hashes')):
        raise ValueError('Appfiler ändrades före startbekräftelsen: ' + ', '.join(manifest_differences(Path(base), state.get('installed_hashes'))))
    state.update(startup_pending=False, startup_verified_at=time.time())
    write_state(base, state)
    journal['phase'] = 'confirmed'
    _write_transaction(base, journal)
    return True


def _windowless_interpreter(interpreter):
    interpreter = Path(interpreter)
    if os.name == 'nt':
        interpreter = interpreter.with_name('pythonw.exe')
        if not interpreter.is_file():
            raise OSError('pythonw.exe saknas; ingen konsolreserv används')
    return interpreter


def launch_update_trial(base, interpreter):
    base = Path(base)
    interpreter = _windowless_interpreter(interpreter)
    supervisor = base / 'data/update-supervisor.py'
    if not supervisor.is_file():
        raise OSError('Stabil uppdateringsövervakare saknas')
    return subprocess.Popen([str(interpreter), str(supervisor), '--trial', str(base), str(interpreter)],
                            cwd=str(base), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)


def _app_mutex_exists():
    if os.name != 'nt':
        import fcntl
        path = Path(os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()) / 'FolderForge/folderforge.lock'
        if not path.exists():
            return False
        try:
            with path.open('r+b') as stream:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
        except OSError:
            return True  # Unknown ownership/permissions is not permission to restore.
        return False
    import ctypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenMutexW.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_wchar_p]
    api.OpenMutexW.restype = ctypes.c_void_p
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    for name in ('Global\\FolderForge_SingleInstance_Mutex', 'Local\\FolderForge_SingleInstance_Mutex'):
        handle = api.OpenMutexW(0x100000, False, name)
        if handle:
            api.CloseHandle(handle)
            return True
    return False


def _offer_rollback(message):
    if os.name != 'nt':
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            try:
                return messagebox.askyesno('FolderForge – säker återställning', message +
                    '\n\nÅterställ föregående app? Projekt och inställningar ändras inte.',
                    parent=root, default='no', icon='warning')
            finally:
                root.destroy()
        except Exception:
            logger.exception('Återställningsfrågan kunde inte visas; säkerhetskopian behålls')
            return False
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, message + '\n\nÅterställ föregående app? Dina projekt och inställningar ändras inte.',
                                            'FolderForge – säker återställning', 0x134) == 6


def _supervise_update(base, interpreter, recover=False, timeout=90, offer=None):
    """No forced termination. A timeout with a live child leaves backup untouched."""
    base = Path(base)
    offer = offer or _offer_rollback
    journal = read_transaction(base)
    if not journal:
        return 0
    if journal.get('phase') == 'confirmed':
        (base / 'data/update-transaction.json').unlink()
        if recover and not _app_mutex_exists():
            subprocess.Popen([str(_windowless_interpreter(interpreter)), str(base / 'folder.pyw'), '--tray'],
                             cwd=str(base), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
        return 0
    if _app_mutex_exists():
        return 0  # Never roll back files underneath an existing app.
    if recover:
        if offer('Förra uppdateringen saknar bekräftad start.'):
            rollback_update(base)
            subprocess.Popen([str(_windowless_interpreter(interpreter)), str(base / 'folder.pyw'), '--tray'],
                             cwd=str(base), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
        return 1
    env = os.environ.copy()
    env.update(FOLDERFORGE_UPDATE_TOKEN=journal['token'], FOLDERFORGE_RUNTIME_READY='1',
               FOLDERFORGE_RUNTIME_POLICY='system-python')
    logdir = base / 'logs'
    logdir.mkdir(parents=True, exist_ok=True)
    env['PYTHONIOENCODING'] = 'utf-8'
    with (logdir / 'folderforge-errors.log').open('ab') as errors:
        child = subprocess.Popen([str(_windowless_interpreter(interpreter)), str(base / 'folder.pyw'), '--tray'],
                                 cwd=str(base), env=env, stderr=errors, stdout=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
    journal.update(trial_pid=child.pid, phase='starting')
    _write_transaction(base, journal)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = read_transaction(base)
        if current and current.get('phase') == 'confirmed' and current['token'] == journal['token']:
            (base / 'data/update-transaction.json').unlink()
            return 0
        if child.poll() is not None:
            logger.error('Den uppdaterade appen avslutades före startbekräftelsen (exit=%s).', child.returncode)
            mark_installation_failed(base, 'Den uppdaterade appen avslutades före startbekräftelsen.')
            if offer('Den uppdaterade appen kunde inte starta.'):
                rollback_update(base)
                subprocess.Popen([str(_windowless_interpreter(interpreter)), str(base / 'folder.pyw'), '--tray'],
                                 cwd=str(base), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
            return 1
        time.sleep(0.25)
    mark_installation_failed(base, 'Startbekräftelse saknas. Stäng appen och starta igen för att erbjudas återställning.')
    # In particular, do NOT kill a slow/busy candidate and do not replace its files.
    return 2


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
    transaction = read_transaction(base)
    if transaction and transaction.get('phase') != 'confirmed':
        raise RuntimeError('Föregående uppdatering saknar startbekräftelse; säkerhetskopian behålls')
    sources = [pending / name for name in FILES]
    if not all(path.is_file() for path in sources):
        return False
    sources += [pending / name for name in OPTIONAL_FILES if (pending / name).is_file()]
    sources += list((pending / "Icon").glob("*.png")) + list((pending / "Icon").glob("*.ico")) + list((pending / "Icon").glob("*.icns")) + list((pending / "Icon").glob("*.svg"))
    backup = base / "data/update-backup"
    if backup.exists():
        shutil.rmtree(backup)
    # Finish the backup and durable journal BEFORE replacing a single app file.
    entries = {}
    for source in sources:
        relative = source.relative_to(pending)
        target, saved = base / relative, backup / relative
        if target.is_symlink() or saved.is_symlink():
            raise ValueError('Symbolisk länk bland appfiler')
        if any(parent.is_symlink() for parent in list(target.parents)[:len(relative.parts)] + list(saved.parents)[:len(relative.parts)]):
            raise ValueError('Symbolisk länk bland appfiler')
        if target.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            entries[relative.as_posix()] = hashlib.sha256(saved.read_bytes()).hexdigest()
        else:
            entries[relative.as_posix()] = None
    import uuid
    journal = dict(token=uuid.uuid4().hex, phase='installing', files=entries, previous_state=dict(state))
    # Snapshot the working updater: recovery must not import the candidate's code.
    supervisor = base / 'data/update-supervisor.py'
    entrypoint = """
if __name__ == '__main__':
    import sys
    try:
        _base = Path(sys.argv[2])
        (_base / 'logs').mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=_base / 'logs/folderforge-errors.log', encoding='utf-8', level=logging.WARNING,
                            format='%(asctime)s %(levelname)s [updater:%(lineno)d] [%(threadName)s] %(message)s')
        sys.exit(supervise_update(_base, Path(sys.argv[3]), recover=sys.argv[1] == '--recover'))
    except Exception:
        logger.exception('Uppdateringens startövervakning misslyckades; säkerhetskopian behålls.')
        sys.exit(1)
"""
    supervisor.write_text(Path(__file__).read_text('utf-8') + entrypoint, encoding='utf-8')
    _write_transaction(base, journal)
    changed = []
    try:
        _invalidate_app_bytecode(base)
        for source in sources:
            relative = source.relative_to(pending)
            target = base / relative
            saved = backup / relative
            existed = target.exists()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".update-tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
            changed.append((target, saved, existed))
            if os.name != 'nt' and relative.as_posix() in {'Starta-FolderForge.sh', 'Starta-FolderForge.app/Contents/MacOS/FolderForge'}:
                target.chmod(target.stat().st_mode | 0o111)
        installed_hashes = state.pop("pending_hashes", None) or content_manifest(pending)
        state["installed_hashes"] = installed_hashes
        state.pop("restart_blocked", None)
        state.pop("installation_error", None)
        state.pop("error", None)
        state["status"] = "checked"
        state["startup_pending"] = True
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
        (base / 'data/update-transaction.json').unlink(missing_ok=True)
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
                # Consume before answering so another UI tick cannot recreate the reply.
                request.unlink(missing_ok=True)
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
        # Windows may still hold a request open in the Tk responder. Cleanup
        # must not turn a valid health answer into an exception/failed probe.
        for path in (request, reply):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # The responder's age filter removes leftovers later.


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
    """Keep startup minimized, including double starts; never terminate automatically."""
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
            logger.info('Befintlig FolderForge-instans svarar (pid=%s); extra start avslutas utan fönstervisning', pid)
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
        if target.is_file():
            # Equivalent shipped UTF-8 scripts must retain their EXACT bytes:
            # adding a BOM at startup invalidates the installed SHA-256 manifest.
            try:
                existing = target.read_bytes().decode('utf-8-sig').replace('\r\n', '\n')
            except UnicodeDecodeError:
                existing = None
            if existing == content.replace('\r\n', '\n'):
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


def ensure_shared_core(base):
    """Recover newly extracted modules for legacy updaters with a fixed allowlist.

    Payload comes from the hash-verified updater itself. Existing modules are
    never rewritten. Normal updates journal and hash these optional files.
    """
    base = Path(base)
    for name, text in SHARED_CORE_FILES.items():
        target = base / name
        if target.is_symlink():
            raise ValueError('Symbolisk länk i gemensam appmodul')
        if target.exists():
            continue
        payload = text.encode('utf-8')
        # Publish a fully flushed file without overwriting a concurrent creator.
        fd, temp = tempfile.mkstemp(prefix='.shared-core-', dir=base)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp, target)
            except FileExistsError:
                pass
        finally:
            os.unlink(temp)


# BEGIN SHARED CORE PAYLOAD
SHARED_CORE_FILES = {
'app_core.py': '"""Shared GUI-independent project/domain logic. Extracted from the tested Tk app."""\nfrom __future__ import annotations\nimport atexit\nimport ctypes\nimport logging\nimport os\nimport re\nimport shutil\nimport tempfile\nimport time\nfrom datetime import datetime\nfrom pathlib import Path\nfrom dataclasses import dataclass, field, asdict\nfrom typing import Any, Callable, Dict, Final, Iterable, List, Optional, Sequence, Set, Tuple\nfrom settings import *\nfrom historik import atomic_write_json, read_json_safe\nlogger = logging.getLogger(__name__)\n\nHOTKEY_MODIFIERS: frozenset = frozenset({\n    "ctrl", "alt", "shift", "cmd", "win", "super", "option", "command",\n})\n\nHOTKEY_MAX_KEYS: int = 5\n\nHOTKEY_KEY_ORDER: Dict[str, int] = {\n    \'ctrl\': 0, \'control\': 0, \'alt\': 1, \'option\': 1,\n    \'shift\': 2, \'cmd\': 3, \'win\': 3, \'super\': 3, \'command\': 3,\n}\n\ndef validate_settings(data: Any) -> Tuple[Dict[str, Any], bool, List[str]]:\n    """\n    Returnerar (rensat_data, reparerad?, loggrader).\n    Okända nycklar behålls (framåtkompatibilitet) men ogiltiga TYPER och\n    ogiltiga ENUM-värden korrigeras till default — aldrig krasch.\n    """\n    log: List[str] = []\n    repaired = False\n\n    if not isinstance(data, dict):\n        return dict(), True, ["settings var inte en dict — nollställd till schema"]\n\n    out: Dict[str, Any] = dict(data)\n\n    for key, (typ, default) in SETTINGS_SCHEMA.items():\n        if key not in out or not isinstance(out[key], typ):\n            if key in out:\n                # log-listan är en vanlig lista → formatering sker direkt.\n                # (Lazy %s gäller endast logger-anrop, aldrig list.append.)\n                log.append("ogiltigt värde för %s (%r) → default" % (key, out[key]))\n                repaired = True\n            out[key] = default if not callable(default) else default()\n\n    for key, allowed in SETTINGS_ENUMS.items():\n        if out.get(key) not in allowed:\n            log.append("\'%s\' = %r ej i %s → %s" % (\n                key, out.get(key), tuple(allowed), SETTINGS_SCHEMA[key][1]))\n            out[key] = SETTINGS_SCHEMA[key][1]\n            repaired = True\n\n    if not out.get("save_root"):\n        out["save_root"] = str(Path.home() / "Projects")\n        repaired = True\n\n    tabs = out.get("visible_tabs")\n    if not isinstance(tabs, dict):\n        tabs = {}\n    cleaned_tabs: Dict[str, bool] = {}\n    for name, val in tabs.items():\n        cleaned_tabs[str(name)] = bool(val)\n    out["visible_tabs"] = cleaned_tabs\n\n    if out.get("start_minimized") is not True:\n        out["start_minimized"] = True\n        repaired = True\n        log.append("start_minimized → True (obligatorisk start i systemfältet)")\n    return out, repaired, log\n\n\nRESERVED_STEM_RE = re.compile(\n    r\'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\\..*)?$\', re.IGNORECASE,\n)\n\n\ndef sanitize_name(name: str, *, max_len: int = 255) -> str:\n    """\n    Rensar ett mapp-/filnamn enligt Windows-regler:\n      • ogiltiga tecken → \'_\'\n      • inledande/avslutande mellanslag och punkter tas bort\n      • reserverade namn blockeras ÄVEN med filändelse (CON.txt, NUL.md …)\n      • längdtak\n    """\n    if not isinstance(name, str):\n        raise ValueError("Namnet måste vara en sträng.")\n    cleaned = INVALID_NAME_CHARS.sub(\'_\', name)\n    cleaned = cleaned.strip().strip(\'.\').strip()\n    if not cleaned:\n        raise ValueError("Mappnamnet är tomt efter rensning.")\n    if cleaned.upper() in INVALID_NAMES or RESERVED_STEM_RE.match(cleaned):\n        raise ValueError(f"\'{cleaned}\' är ett reserverat systemnamn.")\n    if len(cleaned) > max_len:\n        raise ValueError(f"Mappnamnet är för långt (max {max_len} tecken).")\n    return cleaned\n\n\n_PLATE_RE = re.compile(\n    r"""^\\s*\n    (?P<bokst>[a-z]{3})              # tre bokstäver (ABC)\n    [\\s\\-–—]*                        # fri separator: mellanslag/streck/inget\n    (?:\n        (?P<s2>\\d{2})[\\s\\-]*(?P<s3>\\d)      # äldre format: ABC 123 (1973–2019)\n      | (?P<n2>\\d{2})[\\s\\-]*(?P<nb>[a-z])   # nyare format: ABC 12 A (2019–)\n    )\n    (?![a-zA-Z0-9])                  # regnr:t får inte flyta ihop med mer text\n    """,\n    re.IGNORECASE | re.VERBOSE,\n)\n\n\n_SUFFIX_STRIP = " \\t-–—_\\u00b7"   # tecken som inte ska inleda den fria texten\n\n\ndef normalize_plate_name(name: str) -> Tuple[str, Optional[str]]:\n    """\n    Normalisera ett projektnamn som BÖRJAR med ett svenskt registreringsnummer.\n\n      \'dss 817\'           → (\'DSS817\', \'DSS817\')\n      \'dss 81 7\'          → (\'DSS817\', \'DSS817\')\n      \'dss 817 stenskott\' → (\'DSS817 stenskott\', \'DSS817\')   (suffix orört)\n      \'abc 12 a 2021\'     → (\'ABC12A 2021\', \'ABC12A\')\n      \'Biltest\'           → (\'Biltest\', None)                (ingen ändring)\n\n    Båda svenska formaten stöds: ABC123 (1973–2019) och ABC12A (2019–).\n    Matchningen är medvetet tolerant (mellanslag/streck ignoreras, I/Q/V\n    blockeras inte): funktionen VARNAR mjukt via returvärdet None — den\n    stoppar eller ändrar aldrig ett namn som inte matchar.\n\n    Versaliseringen av HELA namnet sker av anroparen (safe_name.upper());\n    här normaliseras bara regnr-delen och gränsen mot fri eftertext.\n\n    Returnerar (ev. normaliserat namn, regnr eller None).\n    """\n    m = _PLATE_RE.match(name or "")\n    if not m:\n        return (name, None)\n    regnr = (m.group("bokst") + (m.group("s2") or m.group("n2"))\n             + (m.group("s3") or m.group("nb") or "")).upper()\n    suffix = name[m.end():].lstrip(_SUFFIX_STRIP)\n    return (regnr + ((" " + suffix) if suffix else ""), regnr)\n\n\ndef strip_root_level(items: List[Dict[str, Any]], root_name: str) -> Tuple[List[Dict[str, Any]], bool]:\n    """\n    Malltext och inklistrade träd har sin rot på rad 1 (\'projektnamn/\',\n    \'ärendenummer/\'), men _build_structure skapar redan\n    base = save_root / root_name. Utan denna funktion blir resultatet:\n\n        PROJEKT123/\n        └── PROJEKT123/      ← dublett (MB5)\n            ├── src/ ...\n\n    Bevis för att rad 1 ÄR roten: de inbyggda mallarna använder\n    \'projektnamn\'/\'ärendenummer\' som placeholder som ersätts med användarens\n    namn via .replace() — alltså är rad 1 per definition roten.\n\n    Regel: finns EXAKT EN post på toppnivå och den är en mapp, skalas den\n    nivån bort från alla poster. Flera toppnivåposter (docs/ + src/) lämnas\n    orörda, eftersom base då redan är deras gemensamma förälder.\n\n    Returnerar (nya_items, skalades_nivån_bort?).\n    """\n    if not items:\n        return items, False\n\n    top = [it for it in items if len(it.get(\'path\', [])) == 1]\n    if len(top) != 1 or not top[0].get(\'is_dir\'):\n        return items, False\n\n    root_label = str(top[0][\'path\'][0]).strip()\n    stripped: List[Dict[str, Any]] = []\n    for it in items:\n        path = list(it.get(\'path\', []))\n        if len(path) <= 1:\n            continue                      # själva rotraden försvinner\n        new_it = dict(it)\n        new_it[\'path\'] = path[1:]\n        stripped.append(new_it)\n\n    if not stripped:\n        # Endast en tom rotmapp i mallen → behåll originalet så att\n        # användaren inte står utan innehåll.\n        return items, False\n\n    return stripped, True\n\n\nMAX_TREE_DEPTH: int = 40\n\n\nMAX_TREE_ENTRIES: int = 20000\n\n\nTREE_IGNORED_DIRS = frozenset({\n    \'.git\', \'__pycache__\', \'.idea\', \'.vscode\',\n    \'node_modules\', \'venv\', \'.env\', \'.tox\',\n})\n\n\ndef generate_tree_string_safe(\n    root_path: Path,\n    max_depth: int = MAX_TREE_DEPTH,\n    max_entries: int = MAX_TREE_ENTRIES,\n    include_dotfiles: bool = False,\n) -> str:\n    """\n    Säkert alternativ till StructureEngine.generate_tree_string:\n      • max_depth    → ingen RecursionError vid extremt djupa träd\n      • resolve()-deduplicering → ingen oändlig loop vid cirkulära symlänkar\n      • max_entries  → ingen minnesexplosion vid t.ex. node_modules-jättar\n      • PermissionError per mapp → \'<Åtkomst nekad>\' istället för krasch\n      • include_dotfiles → .gitignore/.env kan exporteras (MB12)\n\n    Returnerar alltid en sträng; kastar aldrig.\n    """\n    root_path = Path(root_path)\n    if not root_path.exists():\n        return "Mappen finns inte."\n\n    lines: List[str] = [f"{root_path.name}/"]\n    state = {\'entries\': 0, \'hit_depth\': False, \'hit_entries\': False}\n    seen: set = set()\n    try:\n        seen.add(str(root_path.resolve()))\n    except OSError:\n        seen.add(str(root_path))\n\n    def walk(directory: Path, prefix: str, depth: int) -> None:\n        if depth >= max_depth:\n            state[\'hit_depth\'] = True\n            return\n        if state[\'hit_entries\']:\n            return\n        try:\n            contents = list(directory.iterdir())\n        except (PermissionError, OSError):\n            lines.append(f"{prefix}└── <Åtkomst nekad>")\n            return\n\n        filtered = []\n        for x in contents:\n            if x.name in TREE_IGNORED_DIRS:\n                continue\n            if x.name.startswith(\'.\') and not include_dotfiles:\n                continue\n            filtered.append(x)\n        filtered.sort(key=lambda p: (not p.is_dir(), p.name.lower()))\n\n        for i, path in enumerate(filtered):\n            if state[\'entries\'] >= max_entries:\n                state[\'hit_entries\'] = True\n                return\n            state[\'entries\'] += 1\n\n            is_last = i == len(filtered) - 1\n            connector = "└── " if is_last else "├── "\n            is_dir = path.is_dir()\n            lines.append(f"{prefix}{connector}{path.name}{\'/\' if is_dir else \'\'}")\n\n            if is_dir:\n                try:\n                    key = str(path.resolve())\n                except OSError:\n                    key = str(path)\n                if key in seen:\n                    lines.append(f"{prefix}{\'    \' if is_last else \'│   \'}└── <symlink-loop, hoppad över>")\n                    continue\n                seen.add(key)\n                walk(path, prefix + ("    " if is_last else "│   "), depth + 1)\n\n    walk(root_path, "", 0)\n\n    if state[\'hit_depth\']:\n        lines.append(f"... (avbröts: max djup {max_depth} nått)")\n    if state[\'hit_entries\']:\n        lines.append(f"... (avbröts: max {max_entries} poster nådda)")\n    return "\\n".join(lines)\n\n\nclass NameValidator:\n    @staticmethod\n    def sanitize(name: str) -> str:\n        """\n        Rensar ett mappnamn enligt Windows-regler.\n\n        M18 — delegerar till sanitize_name(), som utöver v4.1:s regler även\n        blockerar reserverade systemnamn MED filändelse (CON.txt, NUL.md,\n        LPT1.log) via RESERVED_STEM_RE. v4.1 jämförde bara cleaned.upper()\n        mot INVALID_NAMES och släppte alltså igenom "CON.txt", vilket kan\n        göra mappen omöjlig att skapa eller ta bort på Windows.\n\n        Kontraktet är oförändrat: returnerar en rensad sträng eller kastar\n        ValueError. Metoden behålls som publik API-yta — inget tas bort.\n        """\n        return sanitize_name(name)\n\n    @staticmethod\n    def is_safe_path(base: Path, target: Path) -> bool:\n        try:\n            target.resolve().relative_to(base.resolve())\n            return True\n        except ValueError:\n            return False\n\n\n@dataclass\nclass AppSettings:\n    save_root: str = field(default_factory=lambda: str(Path.home() / "Projects"))\n    open_after_creation: bool = True\n    theme: str = "Dark"\n    text_size: str = "100%"\n    high_contrast: bool = False\n    default_template: str = "Skaderapport"\n    last_template: str = ""\n    plate_mode: bool = True\n    start_minimized: bool = True    # starta i systray utan att visa fönstret\n    visible_tabs: Dict[str, bool] = field(default_factory=lambda: {\n        t: True for t in TAB_ICONS\n    })\n\n    def to_dict(self) -> dict:\n        return asdict(self)\n\n    @classmethod\n    def from_dict(cls, data: dict) -> "AppSettings":\n        # M3/C2 — validera mot schema INNAN något används. Fel typ, okänt\n        # enum-värde eller saknad nyckel rättas till default istället för att\n        # följa med in i appen och krascha längre ner i GUI:t. validate_settings\n        # är idempotent, så att _load_settings redan validerat spelar ingen roll.\n        data, repaired, log = validate_settings(data)\n        if repaired:\n            for line in log:\n                logger.warning("Inställning reparerad: %s", line)\n        default_tabs = {t: True for t in TAB_ICONS}\n        saved_tabs = data.get("visible_tabs", {})\n        default_tabs.update(saved_tabs)\n        return cls(\n            save_root=data.get("save_root", str(Path.home() / "Projects")),\n            open_after_creation=data.get("open_after_creation", True),\n            theme=data.get("theme", "Dark"),\n            text_size=data.get("text_size", "100%"),\n            high_contrast=data.get("high_contrast", False),\n            default_template=data.get("default_template", "Skaderapport"),\n            last_template=data.get("last_template", ""),\n            plate_mode=data.get("plate_mode", True),\n            start_minimized=data.get("start_minimized", True),\n            visible_tabs=default_tabs,\n        )\n\n\nclass TemplateManager:\n    def __init__(self, directory=None) -> None:\n        self.directory = Path(directory) if directory is not None else TEMPLATES_DIR\n        self.directory.mkdir(parents=True, exist_ok=True)\n        self._builtin = self._create_builtins()\n\n    @staticmethod\n    def _create_builtins() -> Dict[str, str]:\n        return {\n            "Python Projekt": (\n                "projektnamn/\\n    src/\\n        __init__.py\\n        main.py\\n"\n                "    tests/\\n        test_main.py\\n    docs/\\n"\n                "    requirements.txt\\n    README.md\\n    .gitignore\\n"\n            ),\n            "Webb Projekt": (\n                "projektnamn/\\n    public/\\n        index.html\\n        style.css\\n"\n                "    src/\\n        app.js\\n    assets/\\n        images/\\n"\n                "    README.md\\n    package.json\\n"\n            ),\n            "Skaderapport": (\n                "ärendenummer/\\n    Bilder/\\n    Skadeanmälan/\\n"\n                "    Diagnos/\\n    Instruktioner/\\n    Kvalitetsrapport/\\n"\n            ),\n        }\n\n    def list_templates(self) -> Dict[str, str]:\n        templates = dict(self._builtin)\n        for f in self.directory.glob("*.json"):\n            # M2/C41.3 — read_json_safe() återställer från .bak/.bak2 om filen\n            # är trasig, istället för att bara hoppa över mallen.\n            data = read_json_safe(f, None)\n            if not isinstance(data, dict):\n                logger.warning("Kunde inte läsa mall %s: ogiltig eller saknad JSON",\n                               f.name)\n                continue\n            try:\n                if isinstance(data["name"], str) and isinstance(data["structure"], str):\n                    templates[data["name"]] = data["structure"]\n            except KeyError as e:\n                logger.warning("Kunde inte läsa mall %s: %s", f.name, e)\n        return templates\n\n    def save_template(self, name: str, structure: str) -> None:\n        if name in self._builtin:\n            raise ValueError("Inbyggda mallar kan inte skrivas över. Välj ett eget namn.")\n        if not StructureEngine.parse_structure_text(structure)[1]:\n            raise ValueError("Mallen måste innehålla en struktur.")\n        safe = NameValidator.sanitize(name)\n        # M1/F1 — atomisk skrivning med backup. Obs: filen får nu indent=2\n        # (atomic_write_json:s standard) istället för en enda lång rad;\n        # innehållet och inläsningsvägen är oförändrade.\n        if not atomic_write_json(\n            self.directory / f"{safe}.json",\n            {"name": name, "structure": structure},\n        ):\n            raise OSError(f"Kunde inte spara mall {name!r}")\n\n    def delete_template(self, name: str) -> bool:\n        if name in self._builtin:\n            return False\n        safe = NameValidator.sanitize(name)\n        p = self.directory / f"{safe}.json"\n        if p.exists():\n            p.unlink()\n            return True\n        return False\n\n\nclass StructureEngine:\n    IGNORED_DIRS: Final[frozenset] = frozenset({\n        \'.git\', \'__pycache__\', \'.idea\', \'.vscode\',\n        \'node_modules\', \'venv\', \'.env\', \'.tox\',\n    })\n\n    @staticmethod\n    def is_file(name: str) -> bool:\n        clean = name.rstrip(\'/\\\\\')\n        if name.endswith((\'/\', \'\\\\\')):\n            return False\n        if clean.lower() in KNOWN_FILES:\n            return True\n        return \'.\' in clean\n\n    @staticmethod\n    def parse_structure_text(text: str) -> Tuple[Optional[str], List[dict]]:\n        lines = text.splitlines()\n        preprocessed: List[Tuple[int, str, Optional[str]]] = []\n        indent_lengths: Set[int] = set()\n\n        for line in lines:\n            if not line.strip():\n                continue\n            comment = None\n            if \'<-\' in line:\n                line, comment = line.split(\'<-\', 1)\n            elif \'←\' in line:\n                line, comment = line.split(\'←\', 1)\n            line = line.rstrip()\n            match = re.match(r\'^([ │├──└──\\t]*)\', line)\n            prefix = match.group(1) if match else ""\n            name = line[len(prefix):].strip()\n            if not name:\n                continue\n            if len(prefix) > 0:\n                indent_lengths.add(len(prefix))\n            preprocessed.append(\n                (len(prefix), name, comment.strip() if comment else None)\n            )\n\n        unit = min(indent_lengths) if indent_lengths else 1\n        items: List[dict] = []\n        stack: List[str] = []\n\n        for ilen, name, cmt in preprocessed:\n            depth = ilen // unit if unit else 0\n            while len(stack) > depth:\n                stack.pop()\n            clean = name.rstrip(\'/\\\\\')\n            is_dir = not StructureEngine.is_file(name)\n            items.append({\n                \'path\': list(stack) + [clean],\n                \'is_dir\': is_dir,\n                \'comment\': cmt,\n            })\n            if is_dir:\n                stack.append(clean)\n\n        return None, items\n\n    @classmethod\n    def generate_tree_string(cls, root_path: Path) -> str:\n        """\n        M12/MB10 — delegerar till generate_tree_string_safe(), som har\n        djupgräns (MAX_TREE_DEPTH), symlink-loop-detektering via resolve(),\n        posttak (MAX_TREE_ENTRIES) och PermissionError-hantering per mapp.\n\n        v4.1:s version rekade utan något tak: ett tillräckligt djupt träd gav\n        RecursionError och en cirkulär symlänk gav en oändlig loop. Alla\n        anropare får nu det säkra beteendet via denna enda ingång.\n\n        _tree_recursive() behålls oförändrad nedan — ingen metod tas bort.\n        """\n        return generate_tree_string_safe(root_path)\n\n    @classmethod\n    def _tree_recursive(\n        cls, directory: Path, prefix: str, lines: List[str],\n    ) -> None:\n        try:\n            contents = list(directory.iterdir())\n        except PermissionError:\n            lines.append(f"{prefix}└── <Åtkomst nekad>")\n            return\n        filtered = [\n            x for x in contents\n            if x.name not in cls.IGNORED_DIRS and not x.name.startswith(\'.\')\n        ]\n        filtered.sort(key=lambda x: (not x.is_dir(), x.name.lower()))\n        for i, path in enumerate(filtered):\n            is_last = i == len(filtered) - 1\n            connector = "└── " if is_last else "├── "\n            suffix = \'/\' if path.is_dir() else \'\'\n            lines.append(f"{prefix}{connector}{path.name}{suffix}")\n            if path.is_dir():\n                cls._tree_recursive(\n                    path, prefix + ("    " if is_last else "│   "), lines,\n                )\n\n    @staticmethod\n    def count_items(items: List[dict]) -> Tuple[int, int]:\n        return (\n            sum(1 for i in items if i[\'is_dir\']),\n            sum(1 for i in items if not i[\'is_dir\']),\n        )\n\n\ndef validate_project_year(value):\n    """År kan väljas eller skrivas; tomt/streck betyder inget år."""\n    year = str(value).strip()\n    if year in ("", "—"):\n        return "—"\n    if not re.fullmatch(r"[1-9][0-9]{3}", year):\n        raise ValueError("Ange ett fyrsiffrigt år, till exempel 2020, eller lämna fältet tomt.")\n    return year\n\n\ndef project_year_choices(today=None):\n    """Innevarande år och tre år bakåt, beräknat när väljaren öppnas."""\n    year = (today or datetime.now()).year\n    return [str(year - offset) for offset in range(4)]\n\n\n\nclass ExistingProject(FileExistsError):\n    def __init__(self, path):\n        self.path = Path(path)\n        super().__init__(f"Projektet finns redan: {self.path}")\n\n\ndef create_project_tree(save_root, root_name, items):\n    """Single implementation for both GUIs. Never merge into an existing project.\n\n    Validate every relative component before writing. On I/O failure a partial\n    project is left for inspection; never recursively delete potentially useful data.\n    """\n    root_name = NameValidator.sanitize(root_name)\n    base = Path(save_root) / root_name\n    checked = []\n    for item in items:\n        parts = item.get(\'path\')\n        if not isinstance(parts, (list, tuple)) or not parts:\n            raise ValueError(\'Tom sökväg i strukturen\')\n        for part in parts:\n            if not isinstance(part, str) or part in {\'.\', \'..\'} or sanitize_name(part) != part:\n                raise ValueError(f\'Otillåten sökväg i strukturen: {parts!r}\')\n        if not NameValidator.is_safe_path(base, base.joinpath(*parts)):\n            raise ValueError(\'Strukturen lämnar projektmappen\')\n        checked.append((list(parts), bool(item[\'is_dir\']), item.get(\'comment\')))\n    if base.parent.exists():\n        for path in base.parent.iterdir():\n            if path.name.casefold() == base.name.casefold():\n                raise ExistingProject(path)\n    base.mkdir(parents=True, exist_ok=False)\n    for parts, is_dir, comment in checked:\n        path = base.joinpath(*parts)\n        if not NameValidator.is_safe_path(base, path):\n            raise ValueError(\'Sökvägen har ändrats under skapandet\')\n        if is_dir:\n            path.mkdir(parents=True, exist_ok=True)\n        else:\n            path.parent.mkdir(parents=True, exist_ok=True)\n            with path.open(\'x\', encoding=\'utf-8\') as stream:\n                stream.write(f\'# {comment or path.name}\')\n    return base\n\n\ndef build_project_name(namn_text: str, lokal: str, year: str = "—", vehicle_type: str = "") -> str:\n    """Sätter ihop slutnamnet för standardprojekt.\n\n    Lokalen läggs efter projektnamnet, och valt år efter lokalen —\n    användarens beslut ("JPM602 SIDORUTA LAXÅ"). Handskrivna lokal-\n    ord i textfältet plockas bort först (case-insensitivt), så\n    dropdownen är enda källan → inga dubbletter möjliga.\n    """\n    year = str(year).strip()\n    ord_lista = [o for o in str(namn_text).split()\n                 if o.upper() not in LOKAL_CHOICES]\n    # Undvik dubbelt valt år utan att radera andra år i fri text.\n    if year and year != "—":\n        ord_lista = [o for o in ord_lista if o != year]\n    vehicle = str(vehicle_type or "").strip().upper()\n    if vehicle:\n        if vehicle not in VEHICLE_CHOICES:\n            raise ValueError("Okänt fordonsslag")\n        ord_lista = [word for word in ord_lista if word.upper() not in VEHICLE_CHOICES]\n        ord_lista.append(vehicle)\n    if lokal and lokal != "—":\n        ord_lista.append(lokal)\n    if year and year != "—":\n        ord_lista.append(year)\n    return " ".join(ord_lista)\n\n\n\ndef validate_hotkey_combo(keys: Iterable[str]) -> Tuple[bool, List[str], str]:\n    """\n    Godkänner bara kombinationer som INTE kan stjäla vanlig skrivning:\n      • minst 1 modifierare (ctrl/alt/shift/cmd/win)\n      • minst 1 icke-modifierare\n      • max 5 tangenter\n      • inga mellanslag i namn\n    Returnerar (ok?, normaliserad_lista, felmeddelande).\n    """\n    norm = normalize_hotkey_keys(keys)\n\n    if not norm:\n        return False, [], "Inga tangenter registrerade."\n    if len(norm) > HOTKEY_MAX_KEYS:\n        return False, norm, f"Max {HOTKEY_MAX_KEYS} tangenter i en kombination."\n\n    mods = [k for k in norm if k in HOTKEY_MODIFIERS]\n    base = [k for k in norm if k not in HOTKEY_MODIFIERS]\n\n    if not mods:\n        return False, norm, (\n            "Snabbtangenten måste innehålla minst en modifierare "\n            "(Ctrl, Alt, Shift eller Win) — annars blockerar den "\n            "vanlig skrivning i hela Windows."\n        )\n    if not base:\n        return False, norm, "Kombinationen saknar en vanlig tangent."\n    for key in base:\n        if not ((len(key) == 1 and key.isprintable() and key not in "+<> ")\n                or key in {"space", "enter", "tab", "esc", "backspace", "delete", "insert", "home", "end", "page_up", "page_down", "up", "down", "left", "right"}\n                or re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", key)):\n            return False, norm, "Okänd tangent: " + key\n    return True, norm, ""\n\n\ndef normalize_hotkey_keys(keys: Iterable[str]) -> List[str]:\n    """\n    Normaliserar pynput-tangentnamn till en stabil, läsbar ordning:\n      \'Key.ctrl_l\' → \'ctrl\', \'Key.shift_r\' → \'shift\', modifierare först.\n    Samma logik som redan finns i _on_press_rec, men GUI-fri och testbar.\n    """\n    norm: List[str] = []\n    for k in keys or []:\n        if k is None:\n            continue\n        raw = str(k)\n        if len(raw) == 1 and 1 <= ord(raw) <= 26:\n            raw = chr(ord(raw) + 96)  # pynput kan ge Ctrl+M som \\r\n        s = raw.strip().lower()\n        if not s:\n            continue\n        if s.startswith(\'key.\'):\n            s = s[4:]\n        s = s.replace(\'_l\', \'\').replace(\'_r\', \'\')\n        s = {\'win\': \'cmd\', \'super\': \'cmd\', \'command\': \'cmd\', \'option\': \'alt\', \'control\': \'ctrl\'}.get(s, s)\n        if s and s not in norm:\n            norm.append(s)\n    norm.sort(key=lambda x: (HOTKEY_KEY_ORDER.get(x, 99), x))\n    return norm\n\n\ndef hotkey_expression(keys):\n    """pynput: <ctrl>+<alt>+m, aldrig <m>."""\n    return "+".join(k if len(k) == 1 else "<" + k + ">" for k in normalize_hotkey_keys(keys))\n\n',
'instance_lock.py': '"""Shared GUI-independent instance locking. Extracted from the tested Tk app."""\nfrom __future__ import annotations\nimport atexit\nimport ctypes\nimport logging\nimport os\nimport re\nimport shutil\nimport tempfile\nimport time\nfrom datetime import datetime\nfrom pathlib import Path\nfrom dataclasses import dataclass, field, asdict\nfrom typing import Any, Callable, Dict, Final, Iterable, List, Optional, Sequence, Set, Tuple\nfrom settings import *\nfrom historik import atomic_write_json, read_json_safe\nlogger = logging.getLogger(__name__)\n\nDEFAULT_POLL_MS: int = 1000\n\n\ndef _pid_alive(pid: int) -> bool:\n    """Sant om processen med angivet PID lever (stale-detektering)."""\n    if not pid or pid <= 0:\n        return False\n    if IS_WINDOWS:\n        try:\n            import win32api\n            import win32con\n            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000\n            handle = win32api.OpenProcess(\n                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)\n            if not handle:\n                return False\n            try:\n                # ExitCodeProcess == STILL_ACTIVE (259) → lever\n                import win32process\n                code = win32process.GetExitCodeProcess(handle)\n                return code == win32con.STILL_ACTIVE\n            finally:\n                win32api.CloseHandle(handle)\n        except ImportError:\n            # pywin32 saknas/är trasig — KRITISK fallback via ren ctypes.\n            # Utan denna gren svarade funktionen "död" om varje PID på\n            # pywin32-lösa maskiner, vilket fick PID-filslåset att överta\n            # låset vid VARJE ny start → flera appfönster samtidigt.\n            try:\n                k32 = ctypes.windll.kernel32\n                handle = k32.OpenProcess(0x1000, False, int(pid))\n                if not handle:\n                    return False\n                try:\n                    code = ctypes.c_ulong(0)\n                    if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):\n                        return False\n                    return code.value == 259   # STILL_ACTIVE\n                finally:\n                    k32.CloseHandle(handle)\n            except Exception:\n                return False\n        except Exception:\n            return False\n    try:\n        os.kill(pid, 0)\n    except ProcessLookupError:\n        return False\n    except PermissionError:\n        return True          # finns men ägs av annan användare\n    except OSError:\n        return False\n    return True\n\n\ndef default_lock_dir(app_name: str) -> Path:\n    """Plattformsoberoende katalog för lås-/trigger-/pid-filer."""\n    if IS_WINDOWS:\n        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") \\\n            or tempfile.gettempdir()\n    else:\n        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()\n    return Path(base) / app_name\n\n\nclass SingleInstanceLock:\n    """\n    C1: Max en instans. Andra start → fokus på befintligt fönster.\n\n      Windows  : CreateMutexW, "Global\\\\" → "Local\\\\"-fallback,\n                 ERROR_ALREADY_EXISTS = 183\n      macOS/Linux: flock LOCK_EX | LOCK_NB (+ PID-fil med stale-detektering)\n      Ingen fcntl OCH ingen pywin32 → PID-filsfallback (självläkning, C41.2)\n\n    Fokus via triggerfil + poll-loop (~1000 ms) som anropar on_trigger i\n    Tk-huvudtråden via after(). Cleanup vid exit (atexit) och krasch (finally).\n    """\n\n    def __init__(\n        self,\n        app_name: str,\n        lock_dir: Optional[Path] = None,\n        poll_ms: int = DEFAULT_POLL_MS,\n    ) -> None:\n        self.app_name = str(app_name)\n        self.lock_dir = Path(lock_dir) if lock_dir else default_lock_dir(self.app_name)\n        self.poll_ms = max(50, int(poll_ms))\n\n        slug = re.sub(r"[^a-z0-9_]+", "_", self.app_name.lower()).strip("_")\n        self.lock_file = self.lock_dir / f"{slug}.lock"\n        self.pid_file = self.lock_dir / f"{slug}.pid"\n        self.trigger_file = self.lock_dir / f"{slug}_show.trigger"\n\n        self._mutex_handle: Optional[int] = None\n        self._mutex_name: Optional[str] = None\n        self._fd: Optional[int] = None\n        self._is_primary: bool = False\n        self._backend: str = "none"\n        self._last_trigger: Optional[str] = None   # filinnehåll, ej mtime\n        self._trigger_init: bool = False\n        self._poll_job: Optional[str] = None\n        self._atexit_registered: bool = False\n        self.check_trigger()  # Baseline before acquisition; do not lose a startup focus request.\n\n    # ------------------------------------------------------------------\n    # Status\n    # ------------------------------------------------------------------\n    @property\n    def is_primary(self) -> bool:\n        """True om DENNA process är den enda/primära instansen."""\n        return self._is_primary\n\n    @property\n    def backend(self) -> str:\n        """\'win32-mutex-global\', \'win32-mutex-local\', \'flock\', \'pidfile\'."""\n        return self._backend\n\n    def read_owner_pid(self) -> Optional[int]:\n        """PID för instansen som håller låset (diagnostik)."""\n        try:\n            return int(self.pid_file.read_text(encoding="utf-8").strip() or 0) or None\n        except (OSError, ValueError):\n            return None\n\n    # ------------------------------------------------------------------\n    # Förvärv\n    # ------------------------------------------------------------------\n    def acquire(self) -> bool:\n        """\n        Försök ta låset. True = vi är primär instans och ska köra.\n        False = en annan instans kör redan; anropa request_focus() och avsluta.\n        Kastar aldrig.\n        """\n        try:\n            self.lock_dir.mkdir(parents=True, exist_ok=True)\n        except OSError as exc:\n            logger.error("Kan inte skapa låskatalog %s: %s", self.lock_dir, exc)\n            return False         # Utan verifierat lås får ingen ny instans starta.\n\n        if IS_WINDOWS:\n            try:\n                ok = self._acquire_win32()\n                # Låsbeslutet MÅSTE synas i loggen. Utan denna rad kunde\n                # PyHANDLE-buggen leva osynlig: mutexen dog direkt, backend-\n                # strängen såg frisk ut, och dubbelstarter passerade tyst.\n                logger.info("Instanslås: %s (backend=%s pid=%d)",\n                            "TAGET" if ok else "UPPTAGET av annan instans — avslutar",\n                            self._backend, os.getpid())\n                return ok\n            except ImportError:\n                logger.error("Windows-instanslåset är otillgängligt — start stoppad.")\n                self._backend = "unavailable"\n                return False\n            except Exception as exc:\n                logger.error("Win32-instanslåset kunde inte verifieras (%s) — start stoppad.", exc)\n                self._backend = "unavailable"\n                return False\n\n        try:\n            import fcntl  # noqa: F401\n            ok = self._acquire_flock()\n            logger.info("Instanslås: %s (backend=%s pid=%d)",\n                        "TAGET" if ok else "UPPTAGET av annan instans — avslutar",\n                        self._backend, os.getpid())\n            return ok\n        except ImportError:\n            logger.warning("fcntl saknas — faller tillbaka på PID-fil.")\n        except Exception as exc:\n            logger.warning("flock misslyckades (%s) — fallback.", exc)\n\n        ok = self._acquire_pidfile()\n        logger.info("Instanslås: %s (backend=%s pid=%d)",\n                    "TAGET" if ok else "UPPTAGET av annan instans — avslutar",\n                    self._backend, os.getpid())\n        return ok\n\n    def _acquire_win32(self) -> bool:\n        try:\n            import win32api\n            import win32event\n            import winerror\n        except ImportError:\n            # pywin32 saknas på maskinen — ta samma mutex via ren ctypes\n            # (stdlib) istället. Spärren får ALDRIG bero på ett valfritt\n            # paket: PID-fils-fallbacken är inte atomär och kan släppa in\n            # två instanser som startar samtidigt (autostart + manuell\n            # start) → just det scenariot som gav dubbla tray-ikoner.\n            return self._acquire_win32_ctypes()\n\n        last_error = 0\n        for prefix in ("Global\\\\", "Local\\\\"):\n            name = f"{prefix}{self.app_name}_SingleInstance_Mutex"\n            try:\n                handle = win32event.CreateMutex(None, False, name)\n            except Exception as exc:\n                # Global\\ kräver rättigheter på vissa system → prova Local\\\n                logger.warning("CreateMutex(%s) misslyckades: %s", name, exc)\n                continue\n            last_error = win32api.GetLastError()\n            if last_error == winerror.ERROR_ALREADY_EXISTS:\n                try:\n                    win32api.CloseHandle(handle)\n                except Exception:\n                    pass\n                self._backend = "win32-mutex-inuse"\n                self._is_primary = False\n                return False\n            # KRITISKT: spara ALDRIG bara int(handle)! pywin32:s PyHANDLE\n            # stänger det underliggande handtaget automatiskt när objektet\n            # skräpsamlas — med int(handle) dog mutexen mikrosekunder efter\n            # förvärvet och instansspärren existerade aldrig i praktiken\n            # (verifierat i logg: dubbelstarter passerade utan avvisning).\n            # Detach() överför ägandet till oss; release() stänger explicit.\n            self._mutex_handle = handle.Detach()\n            self._mutex_name = name\n            self._backend = "win32-mutex-" + prefix.rstrip(chr(92)).lower()\n            self._is_primary = True\n            self._write_pid()\n            self._register_atexit()\n            return True\n\n        raise RuntimeError(f"CreateMutex fungerade inte (sista fel={last_error})")\n\n    def _acquire_win32_ctypes(self) -> bool:\n        """\n        Samma namngivna mutex som _acquire_win32, men via ren ctypes —\n        körs när pywin32 saknas. Identiska namn = samma spärr även om\n        två processer råkar gå olika vägar (den ena med, den andra utan\n        pywin32). use_last_error=True + set_last_error(0) före anropet,\n        annars är GetLastError opålitlig från ctypes.\n        """\n        ERROR_ALREADY_EXISTS = 183\n        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)\n        kernel32.CreateMutexW.restype = ctypes.c_void_p\n        kernel32.CreateMutexW.argtypes = (\n            ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)\n\n        for prefix in ("Global\\\\", "Local\\\\"):\n            name = f"{prefix}{self.app_name}_SingleInstance_Mutex"\n            ctypes.set_last_error(0)\n            handle = kernel32.CreateMutexW(None, False, name)\n            if not handle:\n                logger.warning("CreateMutexW(%s) misslyckades (fel=%s) — provar nästa.",\n                               name, ctypes.get_last_error())\n                continue\n            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:\n                kernel32.CloseHandle(ctypes.c_void_p(handle))\n                self._backend = "win32-mutex-inuse"\n                self._is_primary = False\n                return False\n            self._mutex_handle = int(handle)  # ctypes-int äger inget — ingen auto-stängning\n            self._mutex_name = name\n            self._backend = ("win32-mutex-global-ctypes" if prefix == "Global\\\\"\n                             else "win32-mutex-local-ctypes")\n            self._is_primary = True\n            self._write_pid()\n            self._register_atexit()\n            return True\n\n        raise RuntimeError("CreateMutexW (ctypes) fungerade inte")\n\n    def _acquire_flock(self) -> bool:\n        import fcntl\n\n        fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o600)\n        try:\n            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n        except OSError:\n            os.close(fd)\n            self._backend = "flock-inuse"\n            self._is_primary = False\n            return False\n\n        self._fd = fd\n        try:\n            os.ftruncate(fd, 0)\n            os.write(fd, str(os.getpid()).encode("ascii"))\n            os.fsync(fd)\n        except OSError as exc:\n            logger.warning("Kunde inte skriva PID i låsfil: %s", exc)\n\n        self._backend = "flock"\n        self._is_primary = True\n        self._write_pid()\n        self._register_atexit()\n        return True\n\n    def _acquire_pidfile(self) -> bool:\n        """Fallback utan fcntl/win32: PID-fil + stale-detektering."""\n        owner = self.read_owner_pid()\n        if owner and owner != os.getpid() and _pid_alive(owner):\n            self._backend = "pidfile-inuse"\n            self._is_primary = False\n            return False\n        if owner and not _pid_alive(owner):\n            logger.info("Stale PID-fil (%s) upptäckt — övertar låset.", owner)\n        self._write_pid()\n        self._backend = "pidfile"\n        self._is_primary = True\n        self._register_atexit()\n        return True\n\n    def _write_pid(self) -> None:\n        try:\n            self.lock_dir.mkdir(parents=True, exist_ok=True)\n            fd, tmp = tempfile.mkstemp(dir=str(self.lock_dir), suffix=".tmp")\n            with os.fdopen(fd, "w", encoding="utf-8") as fh:\n                fh.write(str(os.getpid()))\n                fh.flush()\n                os.fsync(fh.fileno())\n            os.replace(tmp, self.pid_file)\n        except OSError as exc:\n            logger.warning("Kunde inte skriva PID-fil: %s", exc)\n\n    def _register_atexit(self) -> None:\n        if self._atexit_registered:\n            return\n        try:\n            atexit.register(self.release)\n            self._atexit_registered = True\n        except Exception:\n            pass\n\n    # ------------------------------------------------------------------\n    # Fokus mellan instanser (triggerfil + poll)\n    # ------------------------------------------------------------------\n    def request_focus(self) -> bool:\n        """\n        Skrivs av den AVVISADE instansen: begär att den primära instansen\n        visar och fokuserar sitt fönster. Kastar aldrig.\n        """\n        try:\n            self.lock_dir.mkdir(parents=True, exist_ok=True)\n            fd, tmp = tempfile.mkstemp(dir=str(self.lock_dir), suffix=".tmp")\n            with os.fdopen(fd, "w", encoding="utf-8") as fh:\n                fh.write(f"{time.time_ns()}\\n{os.getpid()}\\n")\n                fh.flush()\n                os.fsync(fh.fileno())\n            os.replace(tmp, self.trigger_file)\n            return True\n        except OSError as exc:\n            logger.error("Kunde inte skriva triggerfil: %s", exc)\n            return False\n\n    def check_trigger(self) -> bool:\n        """\n        True om triggerfilen ändrats sedan senaste anropet.\n\n        Jämför FILINNEHÅLLET, inte mtime. Skäl (verifierat): två snabba\n        request_focus()-anrop kan ge IDENTISK st_mtime_ns eftersom\n        filsystemets tidsupplösning är för grov, medan innehållet\n        (time_ns + pid) alltid är unikt. Med mtime tappades den andra\n        förfrågan.\n\n        Första anropet sätter baslinjen och returnerar False. Baslinjen sätts\n        även när filen INTE finns ännu — annars tappas den första\n        fokusförfrågan, eftersom None då betyder både "ingen baslinje" och\n        "filen saknas" (se _trigger_init).\n        """\n        try:\n            state: Optional[str] = self.trigger_file.read_text(encoding="utf-8")\n        except OSError:\n            state = None\n\n        if not self._trigger_init:\n            self._trigger_init = True\n            self._last_trigger = state\n            return False\n\n        if state != self._last_trigger:\n            self._last_trigger = state\n            # En borttagen fil är ingen fokusförfrågan — bara ett nytt läge.\n            return state is not None\n        return False\n\n    def poll_start(self, root: Any, on_trigger: Any) -> bool:\n        """\n        Starta Tk-poll-loop (C1: ~1000 ms). Anropar on_trigger() i\n        huvudtråden när en annan instans begärt fokus.\n\n        root     : något med .after(ms, fn) — din CTk/Tk-instans\n        on_trigger: callback, t.ex. app._restore_from_tray\n        """\n        if not self._is_primary:\n            return False\n\n        pending_focus = self.check_trigger()  # Preserve requests received while GUI initialized.\n        from updater import service_instance_health\n        try:\n            service_instance_health(self.lock_dir, BASE_DIR / "folder.pyw")\n        except Exception:\n            logger.warning("Hälsosignalen kunde inte startas", exc_info=True)\n\n        def _loop() -> None:\n            nonlocal pending_focus\n            if not self._is_primary:\n                return\n            try:\n                service_instance_health(self.lock_dir, BASE_DIR / "folder.pyw")\n                requested = self.check_trigger()\n                if pending_focus or requested:\n                    pending_focus = False\n                    logger.info("Trigger mottagen — fokuserar fönster.")\n                    on_trigger()\n            except Exception:\n                logger.exception("Fel i single-instance poll-loop")\n            finally:\n                try:\n                    root.after(self.poll_ms, _loop)\n                except Exception:\n                    pass                   # fönstret stängs — avsluta loopen\n\n        try:\n            root.after(self.poll_ms, _loop)\n            return True\n        except Exception as exc:\n            logger.error("Kunde inte starta poll-loop: %s", exc)\n            return False\n\n    def poll_stop(self) -> None:\n        self._poll_job = None\n\n    # ------------------------------------------------------------------\n    # Cleanup\n    # ------------------------------------------------------------------\n    def release(self) -> None:\n        """Frigör låset. Idempotent — kan anropas flera gånger säkert."""\n        if not self._is_primary and self._fd is None and self._mutex_handle is None:\n            return  # A rejected or previously released instance owns no files.\n        if self._is_primary:\n            # Remove owner metadata WHILE still holding the OS lock. Never unlink\n            # the flock inode: a concurrent acquirer could otherwise lock a new file.\n            for path in (self.pid_file, self.trigger_file):\n                try:\n                    path.unlink()\n                except OSError:\n                    pass\n            try:\n                from updater import clear_instance_health\n                clear_instance_health(self.lock_dir)\n            except Exception:\n                pass  # Hälsostädning får aldrig hindra att instanslåset släpps.\n        self._is_primary = False\n\n        if self._fd is not None:\n            try:\n                import fcntl\n                fcntl.flock(self._fd, fcntl.LOCK_UN)\n            except Exception:\n                pass\n            try:\n                os.close(self._fd)\n            except OSError:\n                pass\n            self._fd = None\n\n        if self._mutex_handle is not None:\n            closed = False\n            try:\n                import win32api\n                win32api.CloseHandle(self._mutex_handle)\n                closed = True\n            except Exception:\n                pass\n            if not closed and IS_WINDOWS:\n                # Handtaget kan ha skapats via ctypes-vägen (utan pywin32) —\n                # stäng det då via ctypes så mutexen verkligen frigörs.\n                try:\n                    ctypes.windll.kernel32.CloseHandle(\n                        ctypes.c_void_p(self._mutex_handle))\n                except Exception:\n                    pass\n            self._mutex_handle = None\n            self._mutex_name = None\n\n        try:\n            logger.info("Instanslås frigivet (%s, pid=%d)",\n                        self._backend, os.getpid())\n        except Exception:\n            pass\n\n',
'gui_entry.py': '"""Default Qt entry. No Tk imports or automatic dependency installation."""\nimport ctypes\nimport logging\nimport os\nfrom pathlib import Path\nimport subprocess\nimport sys\n\n\ndef main():\n    base = Path(__file__).resolve().parent\n    from logg import init_logging\n    init_logging()\n    log = logging.getLogger(\'startup.qt\')\n    try:\n        # Existing hidden native bootstrap discovers a usable system interpreter.\n        if os.name == \'nt\' and (os.environ.get(\'FOLDERFORGE_RUNTIME_READY\') != \'1\'\n                or os.environ.get(\'FOLDERFORGE_RUNTIME_POLICY\') != \'system-python\'):\n            from updater import launch_runtime_bootstrap\n            launch_runtime_bootstrap(base, sys.executable, sys.argv[1:])\n            return 0\n        from qt_diagnostics import save_startup_report\n        save_startup_report(base, \'loading-qt\')\n        from qt_app import run\n        log.info(\'Default GUI: Qt; Tk is available only through explicit reserve startup\')\n        return run()\n    except Exception as exc:\n        log.exception(\'Qt-start misslyckades; ingen automatisk Tk-start eller installation görs\')\n        try:\n            from qt_diagnostics import save_startup_report\n            save_startup_report(base, \'failed\', str(exc))\n        except Exception:\n            log.exception(\'Kunde inte skriva startdiagnostik\')\n        message = (\'FolderForge kunde inte starta Qt.\\n\\n\' + str(exc) +\n                   \'\\n\\nSe logs/folderforge-errors.log och logs/startup-diagnostics.json.\\n\'\n                   \'PySide6 och övriga beroenden i requirements.txt måste finnas i den Python som startaren väljer.\\n\'\n                   \'Ingen installation kördes. Reserv: Starta-FolderForge-Tk.py. Följ IT-policy.\')\n        if os.name == \'nt\':\n            ctypes.windll.user32.MessageBoxW(None, message, \'FolderForge – startfel\', 0x10)\n        else:\n            print(message, file=sys.stderr)\n        return 1\n',
'qt_diagnostics.py': '"""Local, allowlisted diagnostics. No network, environment dump or project contents."""\nimport hashlib\nimport importlib.metadata\nimport json\nimport logging\nimport os\nfrom pathlib import Path\nimport platform\nimport sys\nimport tempfile\nfrom datetime import datetime, timezone\n\n\ndef startup_report(base, phase=\'running\', error=\'\'):\n    from updater import read_state, FILES, OPTIONAL_FILES\n    base = Path(base)\n    packages = {}\n    for name in (\'PySide6\', \'shiboken6\', \'pynput\', \'pywin32\'):\n        try:\n            packages[name] = importlib.metadata.version(name)\n        except importlib.metadata.PackageNotFoundError:\n            packages[name] = \'saknas\'\n    expected = read_state(base).get(\'installed_hashes\', {})\n    mismatches = []\n    if isinstance(expected, dict):\n        for name, digest in expected.items():\n            if name not in FILES | OPTIONAL_FILES and not (name.startswith(\'Icon/\')\n                    and len(Path(name).parts) == 2 and Path(name).suffix in {\'.png\', \'.ico\', \'.icns\', \'.svg\'}):\n                continue\n            path = base / name\n            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:\n                mismatches.append(name)\n    return dict(time=datetime.now(timezone.utc).isoformat(), phase=phase, error=error[:2000],\n                gui=\'Qt\', executable=sys.executable, python=platform.python_version(),\n                system=platform.system(), machine=platform.machine(), packages=packages,\n                mismatched_files=mismatches, pid=os.getpid())\n\n\ndef save_startup_report(base, phase=\'running\', error=\'\'):\n    report = startup_report(base, phase, error)\n    folder = Path(base) / \'logs\'\n    folder.mkdir(parents=True, exist_ok=True)\n    fd, temporary = tempfile.mkstemp(prefix=\'.startup-\', dir=folder)\n    try:\n        with os.fdopen(fd, \'w\', encoding=\'utf-8\') as stream:\n            json.dump(report, stream, ensure_ascii=False, indent=2)\n            stream.flush()\n            os.fsync(stream.fileno())\n        os.replace(temporary, folder / \'startup-diagnostics.json\')\n    finally:\n        if os.path.exists(temporary):\n            os.unlink(temporary)\n    return report\n\n\ndef install_qt_message_logging():\n    from PySide6.QtCore import qInstallMessageHandler, QtMsgType\n    log = logging.getLogger(\'qt.native\')\n    def handler(kind, context, message):\n        level = logging.DEBUG\n        if kind == QtMsgType.QtWarningMsg:\n            level = logging.WARNING\n        elif kind in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):\n            level = logging.ERROR\n        log.log(level, \'%s\', message)\n    # Retain callable for the entire process, including native plugin failures.\n    install_qt_message_logging.handler = handler\n    qInstallMessageHandler(handler)\n',
'qt_app.py': '"""Opt-in functional Qt client. Tk remains the default and full-feature fallback."""\nfrom pathlib import Path\nimport threading\nimport logging\nimport webbrowser\n\nfrom PySide6.QtCore import QObject, Signal, QRect, QTimer, QUrl, Qt\nfrom PySide6.QtGui import QDesktopServices, QPixmap\nfrom PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QStackedWidget, QSizePolicy,\n    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,\n    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)\n\nfrom app_core import (build_project_name, ExistingProject, StructureEngine, project_year_choices, validate_project_year)\nfrom qt_preview import PreviewWindow, fit_to_screen\nfrom settings import APP_VERSION, BASE_DIR, LOKAL_CHOICES, VEHICLE_CHOICES\nfrom workspace import Workspace\n\n\ndef label(text):\n    result = QLabel(text)\n    result.setWordWrap(True)\n    result.setTextFormat(Qt.PlainText)\n    return result\n\n\ndef button(layout, text, callback):\n    result = QPushButton(text)\n    result.clicked.connect(callback)\n    layout.addWidget(result)\n    return result\n\n\ndef page(tabs, title):\n    scroll = QScrollArea()\n    scroll.setWidgetResizable(True)\n    widget = QWidget()\n    layout = QVBoxLayout(widget)\n    scroll.setWidget(widget)\n    tabs.addTab(scroll, title)\n    return layout\n\n\nclass ResponsiveTabs(QWidget):\n    """All page names remain visible; navigation wraps rather than scrolling away."""\n    def __init__(self):\n        super().__init__()\n        layout = QVBoxLayout(self)\n        self.header = QGridLayout()\n        layout.addLayout(self.header)\n        self.stack = QStackedWidget()\n        layout.addWidget(self.stack)\n        self.buttons = []\n        self.columns = 0\n\n    def addTab(self, widget, title):\n        index = self.stack.addWidget(widget)\n        control = QPushButton(title)\n        control.setCheckable(True)\n        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)\n        control.clicked.connect(lambda checked=False, n=index: self.setCurrentIndex(n))\n        self.buttons.append(control)\n        self.reflow(force=True)\n        self.setCurrentIndex(self.stack.currentIndex())\n        return index\n\n    def count(self):\n        return self.stack.count()\n\n    def currentIndex(self):\n        return self.stack.currentIndex()\n\n    def setCurrentIndex(self, index):\n        self.stack.setCurrentIndex(index)\n        for n, control in enumerate(self.buttons):\n            control.setChecked(n == index)\n\n    def resizeEvent(self, event):\n        super().resizeEvent(event)\n        self.reflow()\n\n    def reflow(self, force=False):\n        needed = max((b.fontMetrics().horizontalAdvance(b.text()) + 48 for b in self.buttons), default=180)\n        columns = max(1, min(len(self.buttons), max(1, self.width() - 24) // needed))\n        if not force and columns == self.columns:\n            return\n        while self.header.count():\n            self.header.takeAt(0)\n        for col in range(max(self.columns, columns)):\n            self.header.setColumnStretch(col, 1 if col < columns else 0)\n        for index, control in enumerate(self.buttons):\n            self.header.addWidget(control, index // columns, index % columns)\n        self.columns = columns\n\n\nclass ExportBridge(QObject):\n    ready = Signal(str)\n    failed = Signal(str)\n\n\nclass ProjectDialog(QDialog):\n    def __init__(self, window):\n        super().__init__(window)\n        self.window = window\n        self.setWindowTitle(\'Skapa standardprojekt – Qt\')\n        self.setModal(True)\n        layout = QVBoxLayout(self)\n        scroll = QScrollArea()\n        scroll.setWidgetResizable(True)\n        content = QWidget()\n        body = QVBoxLayout(content)\n        form = QFormLayout()\n        form.setRowWrapPolicy(QFormLayout.WrapLongRows)\n        self.name = QLineEdit()\n        self.name.setAccessibleName(\'Projektnamn\')\n        self.location = QComboBox()\n        self.location.addItems([\'—\'] + list(LOKAL_CHOICES))\n        self.year = QComboBox()\n        self.year.setEditable(True)\n        self.year.addItems([\'—\'] + project_year_choices())\n        self.vehicle = QComboBox()\n        self.vehicle.addItems([\'—\'] + list(VEHICLE_CHOICES))\n        self.template = QComboBox()\n        self.template.addItems(list(window.workspace.templates.list_templates()))\n        self.template.setCurrentText(window.workspace.config.default_template)\n        for title, widget in ((\'&Projektnamn\', self.name), (\'&Fordon\', self.vehicle),\n                              (\'&Lokal\', self.location), (\'&År\', self.year), (\'&Mall\', self.template)):\n            form.addRow(title, widget)\n        body.addLayout(form)\n        body.addWidget(label(\'Tillfällig egen struktur (frivilligt, ändrar inte dina sparade mallar):\'))\n        self.custom = QPlainTextEdit()\n        self.custom.setPlaceholderText(\'Lämna tomt för vald mall, eller klistra in ett indraget mappträd.\')\n        self.custom.setMaximumHeight(130)\n        body.addWidget(self.custom)\n        self.preview = label(\'\')\n        body.addWidget(self.preview)\n        self.error = label(\'\')\n        body.addWidget(self.error)\n        scroll.setWidget(content)\n        layout.addWidget(scroll)\n        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)\n        self.create_button = actions.button(QDialogButtonBox.Save)\n        self.create_button.setText(\'Skapa projekt…\')\n        actions.accepted.connect(self.create)\n        actions.rejected.connect(self.reject)\n        layout.addWidget(actions)\n        self.name.textChanged.connect(self.refresh)\n        for widget in (self.location, self.year, self.vehicle, self.template):\n            widget.currentTextChanged.connect(self.refresh)\n        self.custom.textChanged.connect(self.refresh)\n        self.refresh()\n\n    def prepare(self):\n        year = validate_project_year(self.year.currentText())\n        if not self.name.text().strip():\n            raise ValueError(\'Ange ett projektnamn\')\n        name = build_project_name(self.name.text(), self.location.currentText(), year,\n                                 \'\' if self.vehicle.currentText() == \'—\' else self.vehicle.currentText())\n        return self.window.workspace.prepare_project(name, self.template.currentText(),\n            self.custom.toPlainText() if self.custom.toPlainText().strip() else None)\n\n    def refresh(self):\n        try:\n            name, items = self.prepare()\n            folders, files = StructureEngine.count_items(items)\n            self.preview.setText(f\'Slutnamn: {name}\\n{folders} mappar, {files} filer\')\n            self.error.clear()\n            self.create_button.setEnabled(True)\n        except (ValueError, OSError) as exc:\n            self.preview.clear()\n            self.error.setText(str(exc))\n            self.create_button.setEnabled(False)\n\n    def create(self):\n        try:\n            name, items = self.prepare()\n            path = Path(self.window.workspace.config.save_root) / name\n            if QMessageBox.question(self, \'Bekräfta skapande\',\n                    f\'Skapa projektet här?\\n{path}\\n\\n{len(items)} strukturposter.\',\n                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:\n                return\n            path = self.window.workspace.create_project(name, items)\n            self.window.statusBar().showMessage(f\'Skapad: {path}\')\n            stat = path.stat()\n            self.window._created.append((path, stat.st_dev, stat.st_ino))\n            self.window.refresh_history()\n            if self.window.workspace.config.open_after_creation:\n                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))\n            self.name.setFocus()\n            self.name.selectAll()\n        except ExistingProject as exc:\n            if QMessageBox.question(self, \'Projektet finns redan\',\n                    f\'Ingenting har slagits ihop eller skrivits över.\\nÖppna {exc.path}?\',\n                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:\n                QDesktopServices.openUrl(QUrl.fromLocalFile(str(exc.path)))\n        except (ValueError, OSError, RuntimeError) as exc:\n            logging.getLogger(\'qt.projects\').exception(\'Projektet kunde inte skapas\')\n            QMessageBox.warning(self, \'Projektet kunde inte skapas\', str(exc))\n\n    def showEvent(self, event):\n        super().showEvent(event)\n        fit_to_screen(self, 640, 680)\n        QTimer.singleShot(0, self.focus_name)\n\n    def focus_name(self):\n        self.name.setFocus()\n        self.name.selectAll()\n\n\nclass QtWindow(PreviewWindow):\n    def __init__(self, workspace):\n        super().__init__()\n        self.workspace = workspace\n        self._hotkeys = None\n        self._busy_tasks = 0\n        self._export_bridge = ExportBridge(self)\n        self._export_bridge.ready.connect(self.export_ready)\n        self._export_bridge.failed.connect(self.export_failed)\n        self.setWindowTitle(f\'FolderForge {APP_VERSION} · Qt\')\n        self.tabs = ResponsiveTabs()\n        self.setCentralWidget(self.tabs)\n        create = page(self.tabs, \'Skapa\')\n        create.addWidget(label(\'FolderForge · Qt\\nSkapa projektmappar med dina mallar.\'))\n        button(create, \'Sök uppdatering nu\', self.check_updates)\n        self._created = []\n        button(create, \'Ångra senast skapade projekt…\', self.undo_last)\n        button(create, \'Skapa standardprojekt\', self.open_project)\n        create.addWidget(label(\'Sparplats: \' + workspace.config.save_root))\n        create.addStretch()\n        history = page(self.tabs, \'Historik\')\n        self.history_list = QListWidget()\n        self.history_list.itemDoubleClicked.connect(self.open_history)\n        history.addWidget(self.history_list)\n        button(history, \'Öppna markerad mapp\', lambda: self.open_history(self.history_list.currentItem()))\n        button(history, \'Uppdatera listan\', self.refresh_history)\n        self.template_page()\n        self.export_page()\n        self.settings_page()\n        self.menuBar().clear()\n        help_menu = self.menuBar().addMenu(\'Hjälp\')\n        self.exit_action.setText(\'Avsluta FolderForge Qt\')\n        help_menu.addAction(self.exit_action)\n        help_menu.addAction(\'Donationer – Stöd FolderForge\', self.donations)\n        help_menu.addAction(\'Uppdateringsstatus\', self.update_status)\n        help_menu.addAction(\'Sök uppdatering nu\', self.check_updates)\n        help_menu.addAction(\'Felsökning och fellista…\', self.diagnostics)\n        help_menu.addAction(\'Detaljerad loggning i 15 minuter\', self.enable_debug)\n        help_menu.addAction(\'Om FolderForge\', lambda: QMessageBox.information(self, \'FolderForge\',\n            f\'FolderForge {APP_VERSION} · Qt\\n© Rickard Längkvist\\n\'\n            \'Explicit Tk-reserv finns via Starta-FolderForge-Tk.py.\'))\n        self.setAcceptDrops(True)\n        self.refresh_history()\n        self.apply_accessibility()\n        self._placement_timer = QTimer(self)\n        self._placement_timer.setSingleShot(True)\n        self._placement_timer.timeout.connect(self.save_placement)\n        QApplication.instance().aboutToQuit.connect(self.save_placement)\n\n    def restore(self):\n        from historik import read_json_safe\n        raw = read_json_safe(self.workspace.base / \'data/qt-window-placement.json\', {})\n        rectangle = None\n        if isinstance(raw, dict) and all(isinstance(raw.get(k), int) and not isinstance(raw[k], bool) for k in (\'x\', \'y\', \'width\', \'height\')):\n            if raw[\'width\'] > 0 and raw[\'height\'] > 0:\n                rectangle = QRect(raw[\'x\'], raw[\'y\'], raw[\'width\'], raw[\'height\'])\n        screens = QApplication.screens()\n        screen = self.screen() or QApplication.primaryScreen()\n        if rectangle is not None:\n            best = max(screens, key=lambda item: item.availableGeometry().intersected(rectangle).width()\n                       * item.availableGeometry().intersected(rectangle).height(), default=screen)\n            if best.availableGeometry().intersects(rectangle):\n                screen = best\n        area = screen.availableGeometry().adjusted(12, 12, -12, -12)\n        if rectangle is None:\n            rectangle = QRect(0, 0, min(760, area.width()), min(560, area.height()))\n            rectangle.moveCenter(area.center())\n        width = min(max(300, rectangle.width()), area.width())\n        height = min(max(250, rectangle.height()), area.height())\n        x = max(area.left(), min(rectangle.x(), area.right() - width + 1))\n        y = max(area.top(), min(rectangle.y(), area.bottom() - height + 1))\n        self.setGeometry(x, y, width, height)\n        self.showNormal()\n        self.raise_()\n        self.activateWindow()\n        self.tabs.reflow(force=True)\n\n    def save_placement(self):\n        if not self.workspace.lock.is_primary or not self.isVisible() or self.isMinimized() or self.isMaximized():\n            return\n        from historik import atomic_write_json\n        rect = self.geometry()\n        atomic_write_json(self.workspace.base / \'data/qt-window-placement.json\',\n                          dict(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height()))\n\n    def resizeEvent(self, event):\n        super().resizeEvent(event)\n        if hasattr(self, \'_placement_timer\'):\n            self._placement_timer.start(500)\n\n    def moveEvent(self, event):\n        super().moveEvent(event)\n        if hasattr(self, \'_placement_timer\'):\n            self._placement_timer.start(500)\n\n    def closeEvent(self, event):\n        self.save_placement()\n        super().closeEvent(event)\n\n    def open_project(self):\n        if self.dialog and self.dialog.isVisible():\n            self.dialog.raise_()\n            self.dialog.activateWindow()\n            return\n        self.dialog = ProjectDialog(self)\n        self.dialog.show()\n\n    def refresh_history(self):\n        self.history_list.clear()\n        for entry in self.workspace.history.get_all():\n            self.history_list.addItem(entry[\'path\'])\n\n    def open_history(self, item):\n        if item:\n            QDesktopServices.openUrl(QUrl.fromLocalFile(item.text()))\n\n    def template_page(self):\n        layout = page(self.tabs, \'Mallar\')\n        self.templates = QComboBox()\n        self.templates.addItems(list(self.workspace.templates.list_templates()))\n        self.template_name = QLineEdit()\n        self.template_name.setPlaceholderText(\'Mallnamn (nytt namn skapar en egen mall)\')\n        self.structure = QPlainTextEdit()\n        layout.addWidget(self.templates)\n        layout.addWidget(self.template_name)\n        layout.addWidget(self.structure)\n        def load(name):\n            self.template_name.setText(name)\n            self.structure.setPlainText(self.workspace.templates.list_templates().get(name, \'\'))\n        self.templates.currentTextChanged.connect(load)\n        def save():\n            try:\n                self.workspace.require_lock()\n                self.workspace.templates.save_template(self.template_name.text(), self.structure.toPlainText())\n                self.templates.clear()\n                self.templates.addItems(list(self.workspace.templates.list_templates()))\n                self.structure.document().setModified(False)\n                self.statusBar().showMessage(\'Mall sparad\')\n            except (OSError, ValueError, RuntimeError) as exc:\n                logging.getLogger(\'qt.templates\').exception(\'Mall kunde inte sparas\')\n                QMessageBox.warning(self, \'Kunde inte spara mall\', str(exc))\n        button(layout, \'Spara som egen mall\', save)\n        def set_default():\n            self.workspace.config.default_template = self.templates.currentText()\n            self.save_settings()\n        button(layout, \'Använd vald mall som standard\', set_default)\n        def remove():\n            if QMessageBox.question(self, \'Ta bort egen mall?\', self.templates.currentText(),\n                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:\n                return\n            try:\n                if not self.workspace.templates.delete_template(self.templates.currentText()):\n                    raise ValueError(\'Inbyggda mallar kan inte tas bort\')\n                self.templates.clear()\n                self.templates.addItems(list(self.workspace.templates.list_templates()))\n            except (OSError, ValueError) as exc:\n                QMessageBox.warning(self, \'Kunde inte ta bort mall\', str(exc))\n        button(layout, \'Ta bort vald egen mall…\', remove)\n        load(self.templates.currentText())\n\n    def export_page(self):\n        layout = page(self.tabs, \'Exportera\')\n        layout.addWidget(label(\'Välj en mapp för säker trälexport. Resultatet kan kopieras eller sparas.\'))\n        self.export_text = QPlainTextEdit()\n        self.export_text.setReadOnly(True)\n        def choose():\n            folder = QFileDialog.getExistingDirectory(self, \'Välj mapp\')\n            if folder:\n                # Bounded traversal uses the exact shared Tk engine.\n                self.start_export(Path(folder))\n        button(layout, \'Välj mapp\', choose)\n        layout.addWidget(self.export_text)\n        def save():\n            path, _ = QFileDialog.getSaveFileName(self, \'Spara struktur\', \'struktur.txt\', \'Text (*.txt)\')\n            if path:\n                try:\n                    Path(path).write_text(self.export_text.toPlainText(), encoding=\'utf-8\')\n                except OSError as exc:\n                    logging.getLogger(\'qt.export\').exception(\'Textfilen kunde inte sparas\')\n                    QMessageBox.warning(self, \'Kunde inte exportera\', str(exc))\n        button(layout, \'Spara text…\', save)\n\n    def settings_page(self):\n        layout = page(self.tabs, \'Inställningar\')\n        layout.addWidget(label(\'Samma sparplats och inställningsformat som Tk. Ändringar sparas först med Spara.\'))\n        self.root_edit = QLineEdit(self.workspace.config.save_root)\n        layout.addWidget(self.root_edit)\n        def choose():\n            path = QFileDialog.getExistingDirectory(self, \'Sparplats\', self.root_edit.text())\n            if path:\n                self.root_edit.setText(path)\n        button(layout, \'Välj sparplats…\', choose)\n        self.open_after = QCheckBox(\'Öppna mappen efter skapande\')\n        self.open_after.setChecked(self.workspace.config.open_after_creation)\n        self.plate_mode = QCheckBox(\'Normalisera registreringsnummer\')\n        self.plate_mode.setChecked(self.workspace.config.plate_mode)\n        layout.addWidget(self.open_after)\n        layout.addWidget(self.plate_mode)\n        self.theme = QComboBox()\n        self.theme.addItems([\'Dark\', \'Light\', \'System\'])\n        self.theme.setCurrentText(self.workspace.config.theme)\n        self.text_size = QComboBox()\n        self.text_size.addItems([\'100%\', \'110%\', \'125%\', \'150%\'])\n        self.text_size.setCurrentText(self.workspace.config.text_size)\n        self.high_contrast = QCheckBox(\'Hög kontrast\')\n        self.high_contrast.setChecked(self.workspace.config.high_contrast)\n        layout.addWidget(label(\'Tema\'))\n        layout.addWidget(self.theme)\n        layout.addWidget(label(\'Textstorlek\'))\n        layout.addWidget(self.text_size)\n        layout.addWidget(self.high_contrast)\n        def save():\n            if not self.root_edit.text().strip():\n                QMessageBox.warning(self, \'Sparplats\', \'Välj en sparplats först.\')\n                return\n            self.workspace.config.save_root = self.root_edit.text().strip()\n            self.workspace.config.open_after_creation = self.open_after.isChecked()\n            self.workspace.config.plate_mode = self.plate_mode.isChecked()\n            self.workspace.config.theme = self.theme.currentText()\n            self.workspace.config.text_size = self.text_size.currentText()\n            self.workspace.config.high_contrast = self.high_contrast.isChecked()\n            self.save_settings()\n        button(layout, \'Spara inställningar\', save)\n        def startup(enabled):\n            if QMessageBox.question(self, \'Ändra autostart?\',\n                    (\'Aktivera\' if enabled else \'Avaktivera\') + \' FolderForge vid inloggning?\\n\'\n                    \'Följ arbetsgivarens IT-policy. Inga paket installeras.\',\n                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:\n                return\n            try:\n                from os_startup import configure_autostart\n                import json\n                result = configure_autostart(enabled)\n                details = json.dumps(result, ensure_ascii=False, indent=2)\n                if not result.get(\'ok\'):\n                    raise RuntimeError(details)\n                QMessageBox.information(self, \'Autostart\', details)\n            except Exception as exc:\n                import logging\n                logging.getLogger(\'qt.autostart\').exception(\'Ändring av autostart misslyckades\')\n                QMessageBox.warning(self, \'Autostart misslyckades\', str(exc))\n        button(layout, \'Starta med operativsystemet…\', lambda: startup(True))\n        button(layout, \'Stäng av autostart…\', lambda: startup(False))\n        layout.addWidget(label(\'Global snabbtangent, till exempel ctrl+alt+m\'))\n        self.hotkey_edit = QLineEdit()\n        self.hotkey_edit.setPlaceholderText(\'ctrl+alt+m\')\n        def save_hotkey():\n            try:\n                if self._hotkeys is None:\n                    raise RuntimeError(\'Snabbtangentsbryggan är inte startad\')\n                self._hotkeys.register(self.hotkey_edit.text().split(\'+\'), save=True)\n                self.hotkey_edit.setModified(False)\n                self.statusBar().showMessage(self._hotkeys.last_status)\n            except Exception as exc:\n                import logging\n                logging.getLogger(\'qt.hotkey\').exception(\'Kunde inte ändra snabbtangent\')\n                QMessageBox.warning(self, \'Snabbtangent\', str(exc))\n        layout.addWidget(self.hotkey_edit)\n        button(layout, \'Spara snabbtangent\', save_hotkey)\n        layout.addStretch()\n\n    def apply_accessibility(self):\n        config = self.workspace.config\n        factor = int(config.text_size.rstrip(\'%\')) / 100\n        dark = config.theme == \'Dark\'\n        if config.theme == \'System\':\n            dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark\n        if config.high_contrast:\n            background, foreground, field, accent, focus = \'#000000\', \'#FFFFFF\', \'#000000\', \'#164B73\', \'#FFFF00\'\n        elif dark:\n            background, foreground, field, accent, focus = \'#101C2C\', \'#EDF4FA\', \'#203249\', \'#215C95\', \'#FFCE66\'\n        else:\n            background, foreground, field, accent, focus = \'#F4F7FB\', \'#172B42\', \'#FFFFFF\', \'#155A94\', \'#005FCC\'\n        self.setStyleSheet(f"""\n            QWidget {{ background: {background}; color: {foreground}; font-size: {round(15 * factor)}px; }}\n            QPushButton {{ background: {accent}; color: white; padding: 12px; border: 2px solid transparent; border-radius: 7px; }}\n            QPushButton:checked {{ background: #316FA5; color: white; }}\n            QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 2px solid {focus}; }}\n            QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{ background: {field}; padding: 6px; border: 2px solid #708090; }}\n            QTabBar::tab {{ padding: 10px; }}\n            QTabBar::tab:selected, QMenu::item:selected {{ background: {accent}; color: white; }}\n        """)\n        QTimer.singleShot(0, lambda: self.tabs.reflow(force=True))\n\n    def save_settings(self):\n        try:\n            self.workspace.save_settings()\n            self.apply_accessibility()\n            self.statusBar().showMessage(\'Inställningar sparade\')\n        except (OSError, RuntimeError) as exc:\n            logging.getLogger(\'qt.settings\').exception(\'Inställningar kunde inte sparas\')\n            QMessageBox.warning(self, \'Skrivfel\', str(exc))\n\n    def donations(self):\n        dialog = QDialog(self)\n        dialog.setWindowTitle(\'Donationer – Stöd FolderForge\')\n        layout = QVBoxLayout(dialog)\n        layout.addWidget(label(\'Gillar du FolderForge?\\n\\nHar appen gjort din vardag enklare? \'\n            \'En frivillig gåva visar uppskattning och uppmuntrar fortsatt utveckling. \'\n            \'Du väljer själv belopp. Alla funktioner fungerar lika bra utan donation.\\n\'\n            \'Tack för att du använder FolderForge!\\n– Rickard Längkvist\'))\n        qr = QLabel()\n        qr.setAlignment(Qt.AlignCenter)\n        qr.setPixmap(QPixmap(str(BASE_DIR / \'Icon/swish-folderforge.png\')).scaled(\n            240, 240, Qt.KeepAspectRatio, Qt.FastTransformation))\n        layout.addWidget(qr)\n        layout.addWidget(label(\'Swish 0721817177 · välj belopp i Swish. Kontrollera mottagaren innan betalning.\'))\n        button(layout, \'PayPal\', lambda: webbrowser.open(\'https://paypal.me/Rickard3dPrint\', new=2))\n        button(layout, \'Ko-fi\', lambda: webbrowser.open(\'https://ko-fi.com/tokke2\', new=2))\n        button(layout, \'Stäng\', dialog.reject)\n        fit_to_screen(dialog, 560, 650)\n        dialog.exec()\n\n    def update_status(self):\n        from updater import get_update_status\n        dialog = QDialog(self)\n        dialog.setWindowTitle(\'Uppdateringsstatus – Qt\')\n        layout = QVBoxLayout(dialog)\n        text = QPlainTextEdit()\n        text.setReadOnly(True)\n        layout.addWidget(text)\n        def refresh():\n            text.setPlainText(\'\\n\\n\'.join(f\'{key}: {value}\' for key, value in get_update_status(BASE_DIR, APP_VERSION).items()))\n        timer = QTimer(dialog)\n        timer.timeout.connect(refresh)\n        timer.start(1000)\n        refresh()\n        layout.addWidget(label(\'Hämtad uppdatering installeras genom dold omstart när öppna dialoger och osparade ändringar är avslutade.\'))\n        button(layout, \'Sök uppdatering nu\', self.check_updates)\n        button(layout, \'Stäng\', dialog.reject)\n        fit_to_screen(dialog, 620, 600)\n        dialog.exec()\n\n    def check_updates(self):\n        from updater import check_once\n        threading.Thread(target=check_once, args=(BASE_DIR, APP_VERSION),\n                         kwargs={\'force\': True}, daemon=True, name=\'qt-release-check\').start()\n        self.statusBar().showMessage(\'Uppdateringskontroll begärd – se uppdateringsstatus\')\n\n\n    def start_export(self, folder):\n        if self._busy_tasks:\n            self.statusBar().showMessage(\'En export pågår redan. Vänta tills den är klar.\')\n            return\n        self._busy_tasks += 1\n        self.statusBar().showMessage(\'Läser mappstruktur i bakgrunden…\')\n        def worker():\n            try:\n                self._export_bridge.ready.emit(StructureEngine.generate_tree_string(folder))\n            except Exception as exc:\n                logging.getLogger(\'qt.export\').exception(\'Trälexport misslyckades\')\n                self._export_bridge.failed.emit(str(exc))\n        threading.Thread(target=worker, name=\'qt-tree-export\', daemon=True).start()\n\n    def export_ready(self, text):\n        self._busy_tasks = max(0, self._busy_tasks - 1)\n        self.export_text.setPlainText(text)\n        self.statusBar().showMessage(\'Struktur klar – du kan spara texten\')\n\n    def export_failed(self, message):\n        self._busy_tasks = max(0, self._busy_tasks - 1)\n        QMessageBox.warning(self, \'Export misslyckades\', message)\n\n    def can_restart(self):\n        if any(isinstance(widget, QDialog) and widget.isVisible() for widget in QApplication.topLevelWidgets()):\n            return False\n        config = self.workspace.config\n        return (self._busy_tasks == 0 and not self.structure.document().isModified()\n                and self.root_edit.text().strip() == config.save_root\n                and self.open_after.isChecked() == config.open_after_creation\n                and self.plate_mode.isChecked() == config.plate_mode\n                and self.theme.currentText() == config.theme\n                and self.text_size.currentText() == config.text_size\n                and self.high_contrast.isChecked() == config.high_contrast\n                and (self._hotkeys is None or not self.hotkey_edit.isModified()))\n\n    def start_integrations(self):\n        from qt_integrations import HotkeyBridge\n        self._hotkeys = HotkeyBridge(self)\n        self._hotkeys.status.connect(self.statusBar().showMessage)\n        self.hotkey_edit.setText(\'+\'.join(self._hotkeys.keys))\n        self.hotkey_edit.setModified(False)\n        self._hotkeys.start()\n        QApplication.instance().aboutToQuit.connect(self._hotkeys.stop)\n\n    def diagnostics(self):\n        from qt_help import DiagnosticsDialog\n        dialog = DiagnosticsDialog(self)\n        dialog.exec()\n\n    def enable_debug(self):\n        from logg import enable_detailed_logging\n        enable_detailed_logging(15)\n        self.statusBar().showMessage(\'Detaljerad loggning aktiv i 15 minuter\')\n\n    def undo_last(self):\n        if not self._created:\n            QMessageBox.information(self, \'Ångra\', \'Inget projekt har skapats i denna session.\')\n            return\n        path, device, inode = self._created[-1]\n        try:\n            stat = path.stat()\n            if path.is_symlink() or (stat.st_dev, stat.st_ino) != (device, inode):\n                raise ValueError(\'Mappen har ersatts eller flyttats; automatisk radering stoppas\')\n            if QMessageBox.warning(self, \'Ta bort hela projektet?\',\n                    f\'{path}\\n\\nALLT innehåll, även filer du lagt till, tas bort permanent. Fortsätt?\',\n                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:\n                return\n            import shutil\n            shutil.rmtree(path)\n            self._created.pop()\n            self.workspace.history.remove(str(path))\n            self.refresh_history()\n        except (OSError, ValueError) as exc:\n            logging.getLogger(\'qt.projects\').exception(\'Ångra/radering stoppades\')\n            QMessageBox.warning(self, \'Ångra stoppades\', str(exc))\n\n    def dragEnterEvent(self, event):\n        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):\n            event.acceptProposedAction()\n\n    def dropEvent(self, event):\n        folders = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]\n        if folders and folders[0].is_dir():\n            self.start_export(folders[0])\n            self.tabs.setCurrentIndex(3)\n            event.acceptProposedAction()\n\n\ndef run():\n    from qt_preview import run as run_host\n\n    def build(lock):\n        from logg import init_logging, start_log_archiver\n        import logg\n        if not logg._initierad:\n            init_logging()\n        start_log_archiver()\n        window = QtWindow(Workspace(lock))\n        window.start_integrations()\n        return window\n\n    return run_host(window_factory=build, production=True)\n',
'qt_preview.py': '"""Opt-in, read-only Qt UI experiment. Never imports Tk or production storage.\n\nNo project creation, settings/history writes, updater, autostart or global hooks.\nQt types are imported only when this optional module is explicitly selected.\n"""\nfrom pathlib import Path\n\nfrom PySide6.QtCore import QEvent, QTimer, Qt\nfrom PySide6.QtGui import QAction, QIcon\nfrom PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,\n    QFormLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,\n    QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)\n\nROOT = Path(__file__).resolve().parent\n\n\ndef fit_to_screen(window, width, height):\n    screen = window.screen() or QApplication.primaryScreen()\n    if not screen:\n        return\n    area = screen.availableGeometry().adjusted(12, 12, -12, -12)\n    window.resize(min(width, area.width()), min(height, area.height()))\n    frame = window.frameGeometry()\n    frame.moveCenter(area.center())\n    window.move(frame.topLeft())\n\n\nclass ProjectPreview(QDialog):\n    def __init__(self, parent=None):\n        super().__init__(parent)\n        self.setWindowTitle(\'Standardprojekt – endast Qt-förhandsvisning\')\n        self.setModal(True)\n        layout = QVBoxLayout(self)\n        scroll = QScrollArea()\n        scroll.setWidgetResizable(True)\n        content = QWidget()\n        body = QVBoxLayout(content)\n        explanation = QLabel(\'TESTLÄGE · Inga mappar skapas och ingenting sparas.\\n\'\n                             \'Prova fokus, Tab-ordning, större text och fönstrets storlek.\')\n        explanation.setWordWrap(True)\n        body.addWidget(explanation)\n        form = QFormLayout()\n        form.setRowWrapPolicy(QFormLayout.WrapLongRows)\n        self.name = QLineEdit()\n        self.name.setPlaceholderText(\'Skriv ett projektnamn…\')\n        self.name.setAccessibleName(\'Projektnamn\')\n        self.location = QLineEdit()\n        self.location.setAccessibleName(\'Lokal\')\n        self.year = QComboBox()\n        self.year.setEditable(True)\n        # UI sample only: full shared production naming logic is a later step.\n        from datetime import date\n        year = date.today().year\n        self.year.addItems([\'—\'] + [str(year - n) for n in range(4)])\n        self.year.setAccessibleName(\'År\')\n        form.addRow(\'&Projektnamn\', self.name)\n        form.addRow(\'&Lokal\', self.location)\n        form.addRow(\'&År\', self.year)\n        body.addLayout(form)\n        body.addWidget(QLabel(\'Enkel namnförhandsvisning (inte produktionsvalidering):\'))\n        self.preview = QLabel()\n        self.preview.setWordWrap(True)\n        self.preview.setTextFormat(Qt.PlainText)\n        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)\n        body.addWidget(self.preview)\n        body.addStretch()\n        scroll.setWidget(content)\n        layout.addWidget(scroll)\n        buttons = QDialogButtonBox(QDialogButtonBox.Close)\n        buttons.button(QDialogButtonBox.Close).setText(\'Stäng – inget sparas\')\n        buttons.rejected.connect(self.reject)\n        layout.addWidget(buttons)\n        self.name.textChanged.connect(self.update_preview)\n        self.location.textChanged.connect(self.update_preview)\n        self.year.currentTextChanged.connect(self.update_preview)\n        QWidget.setTabOrder(self.name, self.location)\n        QWidget.setTabOrder(self.location, self.year)\n        QWidget.setTabOrder(self.year, buttons.button(QDialogButtonBox.Close))\n        self.update_preview()\n\n    def update_preview(self):\n        parts = [self.name.text().strip(), self.location.text().strip()]\n        if self.year.currentText().strip() != \'—\':\n            parts.append(self.year.currentText().strip())\n        self.preview.setText(\' \'.join(p for p in parts if p) or \'Ditt projektnamn visas här\')\n\n    def showEvent(self, event):\n        super().showEvent(event)\n        fit_to_screen(self, 600, 430)\n        QTimer.singleShot(0, self.focus_name)\n\n    def focus_name(self):\n        self.name.setFocus(Qt.OtherFocusReason)\n        self.name.selectAll()\n\n\nclass PreviewWindow(QMainWindow):\n    def __init__(self):\n        super().__init__()\n        self.setWindowTitle(\'FolderForge · Qt-prototyp · TESTLÄGE\')\n        self.setWindowIcon(QIcon(str(ROOT / \'Icon/projektmapp_icon_256.png\')))\n        self.dialog = None\n        content = QWidget()\n        layout = QVBoxLayout(content)\n        brand = QLabel(\'FolderForge / Qt\')\n        brand.setObjectName(\'brand\')\n        layout.addWidget(brand)\n        notice = QLabel(\'SEPARAT PROTOTYP – INGA ÄNDRINGAR SPARAS\\n\'\n                        \'Din vanliga Tk-app är fortfarande standard och reserv.\\n\'\n                        \'Här provar vi bara det nya gränssnittet. Riktiga projekt,\\n\'\n                        \'historik, inställningar och uppdateringar lämnas orörda.\')\n        notice.setWordWrap(True)\n        layout.addWidget(notice)\n        self.open_button = QPushButton(\'Prova standardprojektdialogen\')\n        self.open_button.clicked.connect(self.open_project)\n        layout.addWidget(self.open_button)\n        layout.addStretch()\n        hint = QLabel(\'Öppna den vanliga appen med din befintliga startfil.\\n\'\n                      \'Det här är inte en ersättare för Tk ännu.\\n© Rickard Längkvist\')\n        hint.setWordWrap(True)\n        layout.addWidget(hint)\n        self.setCentralWidget(content)\n        help_menu = self.menuBar().addMenu(\'Hjälp\')\n        about = help_menu.addAction(\'Om Qt-prototypen\')\n        about.triggered.connect(lambda: QMessageBox.information(self, \'Qt-prototyp\',\n            \'Endast en gränssnittsförhandsvisning. Inga projekt skapas.\\n\'\n            \'Ingen automatisk migrering, installation eller ändring av Tk-versionen.\'))\n        self.exit_action = QAction(\'Avsluta Qt-prototypen\', self)\n        self.exit_action.triggered.connect(QApplication.instance().quit)\n        help_menu.addAction(self.exit_action)\n        self.tray = None\n        self.setStyleSheet(\'\'\'\n            QMainWindow, QDialog { background: #101c2c; }\n            QWidget { background: #101c2c; color: #edf4fa; font-size: 15px; }\n            QWidget#qt_scrollarea_viewport, QScrollArea { background: #101c2c; }\n            QLabel#brand { color: #59e0d0; font-size: 28px; font-weight: 700; }\n            QPushButton { background: #215c95; padding: 12px; border-radius: 7px; }\n            QPushButton:hover { background: #2f75b6; }\n            QPushButton:focus, QLineEdit:focus, QComboBox:focus { border: 2px solid #ffce66; }\n            QLineEdit, QComboBox { background: #203249; padding: 8px; border: 2px solid #52657a; }\n            QMenu { background: #203249; }\n            QMenu::item:selected { background: #215c95; }\n        \'\'\')\n\n    def open_project(self):\n        if self.dialog and self.dialog.isVisible():\n            self.dialog.raise_()\n            self.dialog.activateWindow()\n            return\n        self.dialog = ProjectPreview(self)\n        self.dialog.show()\n\n    def restore(self):\n        fit_to_screen(self, 700, 480)\n        self.showNormal()\n        self.raise_()\n        self.activateWindow()\n\n    def closeEvent(self, event):\n        if self.tray and self.tray.isVisible():\n            self.hide()\n            event.ignore()\n        else:\n            event.accept()\n\n    def changeEvent(self, event):\n        super().changeEvent(event)\n        if event.type() == QEvent.WindowStateChange and self.isMinimized() and self.tray:\n            QTimer.singleShot(0, self.hide)\n\n\ndef run(window_factory=None, production=False):\n    import hashlib\n    import os\n    import sys\n    from PySide6.QtCore import QLockFile, QStandardPaths\n    if production:\n        from qt_diagnostics import install_qt_message_logging\n        install_qt_message_logging()\n    app = QApplication(sys.argv)\n    app.setApplicationName(\'FolderForge\' if production else \'FolderForge Qt-prototyp\')\n    app.setQuitOnLastWindowClosed(False)\n    # Prototype-only lock in OS temp; never opens or changes production\'s lock/data.\n    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]\n    if production:\n        from instance_lock import SingleInstanceLock\n        from settings import APP_NAME\n        lock = SingleInstanceLock(APP_NAME)\n        acquired = lock.acquire()\n    else:\n        lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation)) /\n                             (\'folderforge-qt-preview-\' + key + \'.lock\')))\n        acquired = lock.tryLock(0)\n    if not acquired:\n        return 0\n    release = lock.release if production else lock.unlock\n    if production:\n        from updater import apply_pending, launch_update_trial, mark_installation_failed\n        try:\n            updated = apply_pending(ROOT)\n        except Exception as exc:\n            import logging\n            logging.getLogger(\'qt.update\').exception(\'Kunde inte installera uppdatering; aktuell app används\')\n            mark_installation_failed(ROOT, exc)\n            updated = False\n        if updated:\n            release()\n            launch_update_trial(ROOT, sys.executable)\n            return 0\n    if not QSystemTrayIcon.isSystemTrayAvailable():\n        print(\'FolderForge kräver ett tillgängligt systemfält. Se logs/ och reservstarten Starta-FolderForge-Tk.py.\', file=sys.stderr)\n        release()\n        return 1\n    try:\n        window = window_factory(lock) if window_factory else PreviewWindow()\n    except Exception:\n        release()\n        raise\n    tray = QSystemTrayIcon(window.windowIcon(), window)\n    tray.setToolTip(\'FolderForge · Qt\' if production else \'FolderForge · Qt-prototyp (testläge)\')\n    menu = QMenu()\n    menu.addAction(\'Öppna FolderForge\' if production else \'Öppna Qt-prototypen\', window.restore)\n    menu.addAction(window.exit_action)\n    tray.setContextMenu(menu)\n    tray.activated.connect(lambda reason: window.restore() if reason == QSystemTrayIcon.Trigger else None)\n    window.tray = tray\n    tray.show()\n    # Remains hidden until an explicit tray action. Never starts Tk in this process.\n    stop = None\n    cleanup = None\n    if production:\n        from updater import service_instance_health, start_updates\n        from settings import APP_VERSION\n        health = QTimer(window)\n        health.timeout.connect(lambda: service_instance_health(lock.lock_dir, ROOT / \'folder.pyw\'))\n        health.start(500)\n        if os.environ.get(\'FOLDERFORGE_QT_SMOKE\') == \'1\':\n            import threading\n            stop = threading.Event()\n        else:\n            stop = start_updates(ROOT, APP_VERSION)\n        from cache_cleanup import start_cleanup\n        cleanup = start_cleanup(ROOT)\n        from qt_diagnostics import save_startup_report\n        from updater import confirm_startup, pending_ready_for_restart\n        import logging\n        log = logging.getLogger(\'qt.update\')\n        def acknowledge():\n            try:\n                if not tray.isVisible():\n                    raise RuntimeError(\'Tray-ikonen är inte redo\')\n                confirm_startup(ROOT)\n                save_startup_report(ROOT, \'ready\')\n            except Exception as exc:\n                log.exception(\'Startbekräftelse misslyckades; backup behålls\')\n                save_startup_report(ROOT, \'confirmation-failed\', str(exc))\n        QTimer.singleShot(500, acknowledge)\n        restart_timer = QTimer(window)\n        def restart_if_safe():\n            if hasattr(window, \'can_restart\') and window.can_restart() and pending_ready_for_restart(ROOT):\n                log.info(\'Uppdatering klar; säker dold Qt-omstart begärd\')\n                app.exit(71)\n        restart_timer.timeout.connect(restart_if_safe)\n        restart_timer.start(2000)\n        if os.environ.get(\'FOLDERFORGE_QT_SMOKE\') == \'1\':\n            import json\n            from historik import atomic_write_json\n            status_path = ROOT / \'data/qt-smoke-status.json\'\n            command_path = ROOT / \'data/qt-smoke-command.json\'\n            last_command = [None]\n            def smoke_tick():\n                try:\n                    command = json.loads(command_path.read_text(encoding=\'utf-8\'))\n                except (OSError, ValueError):\n                    command = {}\n                if command.get(\'pid\') == os.getpid() and command.get(\'id\') != last_command[0]:\n                    last_command[0] = command.get(\'id\')\n                    action = command.get(\'action\')\n                    if action == \'restore\': window.restore()\n                    elif action == \'project-dialog\': window.open_project()\n                    elif action == \'close-project-dialog\' and window.dialog: window.dialog.reject()\n                    elif action == \'close-main\': window.close()\n                    elif action == \'minimize-main\': window.showMinimized()\n                    elif action == \'exit\': app.quit()\n                dialog = getattr(window, \'dialog\', None)\n                atomic_write_json(status_path, dict(pid=os.getpid(), visible=window.isVisible(),\n                    tray=tray.isVisible(), gui=\'qt\', tk_loaded=\'tkinter\' in sys.modules,\n                    dialog=bool(dialog and dialog.isVisible()),\n                    project_focused=bool(dialog and dialog.isVisible() and app.focusWidget() is dialog.name)), backup=False)\n            smoke_timer = QTimer(window)\n            smoke_timer.timeout.connect(smoke_tick)\n            smoke_timer.start(100)\n    result = 1\n    try:\n        result = app.exec()\n    finally:\n        if stop is not None:\n            stop.set()\n        if cleanup is not None:\n            cleanup.set()\n        tray.hide()\n        release()\n    if production and result == 71:\n        import subprocess\n        subprocess.Popen([sys.executable, str(ROOT / \'folder.pyw\'), \'--tray\'], cwd=ROOT,\n                         creationflags=getattr(subprocess, \'CREATE_NO_WINDOW\', 0), close_fds=True)\n        return 0\n    return result\n',
'workspace.py': '"""Shared storage facade for the opt-in Qt client; requires the production lock."""\nfrom pathlib import Path\n\nfrom app_core import (AppSettings, NameValidator, StructureEngine, TemplateManager,\n                      create_project_tree, normalize_plate_name, strip_root_level)\nfrom historik import ProjectHistory, atomic_write_json, read_json_safe\nfrom settings import BASE_DIR\n\n\nclass Workspace:\n    def __init__(self, lock, base=BASE_DIR):\n        if not lock.is_primary:\n            raise RuntimeError(\'Instanslåset måste vara taget innan data öppnas\')\n        self.lock = lock\n        self.base = Path(base)\n        self.settings_file = self.base / \'data/settings.json\'\n        raw = read_json_safe(self.settings_file, {})\n        self.raw = raw if isinstance(raw, dict) else {}\n        self.config = AppSettings.from_dict(self.raw)\n        self.templates = TemplateManager(self.base / \'data/templates\')\n        self.history = ProjectHistory(self.base / \'data/history.json\')\n\n    def require_lock(self):\n        if not self.lock.is_primary:\n            raise RuntimeError(\'Instanslåset är inte längre taget\')\n\n    def save_settings(self):\n        self.require_lock()\n        # Preserve unknown keys for compatibility with Tk and future versions.\n        result = dict(self.raw)\n        result.update(self.config.to_dict())\n        if not atomic_write_json(self.settings_file, result):\n            raise OSError(\'Inställningarna kunde inte sparas\')\n        self.raw = result\n\n    def prepare_project(self, name, template=None, custom_structure=None):\n        self.require_lock()\n        if self.config.plate_mode:\n            name, _ = normalize_plate_name(name)\n        name = NameValidator.sanitize(name).upper()\n        structure = custom_structure\n        if structure is None:\n            templates = self.templates.list_templates()\n            selected = template or self.config.default_template\n            if selected not in templates:\n                raise ValueError(\'Vald mall saknas. Välj en befintlig mall.\')\n            structure = templates[selected]\n        _, items = StructureEngine.parse_structure_text(structure)\n        items, _ = strip_root_level(items, name)\n        return name, items\n\n    def create_project(self, name, items):\n        self.require_lock()\n        path = create_project_tree(self.config.save_root, name, items)\n        self.history.add(path)\n        return path\n',
'qt_help.py': '"""Qt troubleshooting UI using the existing persistent error archive and export."""\nimport json\nfrom pathlib import Path\n\nfrom PySide6.QtCore import QTimer\nfrom PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,\n    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,\n    QPlainTextEdit, QPushButton, QVBoxLayout)\n\nfrom qt_preview import fit_to_screen\n\n\nclass DiagnosticsDialog(QDialog):\n    def __init__(self, parent):\n        super().__init__(parent)\n        self.setWindowTitle(\'FolderForge – felsökning och fellista\')\n        self.digest = None\n        self.issues = []\n        self.current_id = None\n        layout = QVBoxLayout(self)\n        notice = QLabel(\'Lokala fel och startdiagnostik. Inget skickas automatiskt.\\n\'\n                        \'Markera ett fel för hela tracebacken. Export kan innehålla personliga sökvägar.\')\n        notice.setWordWrap(True)\n        layout.addWidget(notice)\n        filters = QHBoxLayout()\n        self.query = QLineEdit()\n        self.query.setPlaceholderText(\'Sök i fel, modul eller traceback…\')\n        self.level = QComboBox()\n        self.level.addItems([\'Alla nivåer\', \'WARNING\', \'ERROR\', \'CRITICAL\'])\n        filters.addWidget(self.query)\n        filters.addWidget(self.level)\n        layout.addLayout(filters)\n        self.list = QListWidget()\n        layout.addWidget(self.list)\n        self.details = QPlainTextEdit()\n        self.details.setReadOnly(True)\n        layout.addWidget(self.details)\n        self.summary = QLabel()\n        self.summary.setWordWrap(True)\n        layout.addWidget(self.summary)\n        self.list.currentRowChanged.connect(self.select)\n        self.query.textChanged.connect(self.filter)\n        self.level.currentTextChanged.connect(self.filter)\n        for title, callback in [(\'Uppdatera\', self.refresh), (\'Markera valt fel åtgärdat…\', self.resolve),\n                                (\'Start-/systemkontroll\', self.system_check), (\'Exportera ZIP…\', self.export)]:\n            button = QPushButton(title)\n            button.clicked.connect(callback)\n            layout.addWidget(button)\n        buttons = QDialogButtonBox(QDialogButtonBox.Close)\n        buttons.rejected.connect(self.reject)\n        layout.addWidget(buttons)\n        self.timer = QTimer(self)\n        self.timer.timeout.connect(self.refresh)\n        self.timer.start(2000)\n        self.refresh()\n        fit_to_screen(self, 800, 720)\n\n    def refresh(self):\n        from logg import get_error_issues\n        try:\n            issues, digest = get_error_issues()\n            if digest == self.digest:\n                return\n            self.issues, self.digest = issues, digest\n            self.filter()\n        except OSError as exc:\n            self.summary.setText(f\'Kunde inte läsa felloggen: {exc}\')\n\n    def filter(self):\n        from logg import filter_error_issues\n        selected = self.current_id\n        self.visible = filter_error_issues(self.issues, self.query.text(), self.level.currentText())\n        self.list.blockSignals(True)\n        self.list.clear()\n        for issue in self.visible:\n            self.list.addItem(f"{issue[\'level\']} · {issue[\'count\']} gånger · {issue[\'module\']} · {issue[\'message\']}")\n        index = next((n for n, issue in enumerate(self.visible) if issue[\'id\'] == selected), -1)\n        self.list.setCurrentRow(index)\n        self.list.blockSignals(False)\n        self.select(index)\n        self.summary.setText(f\'{len(self.visible)} visade felgrupper av {len(self.issues)}. \'\n                             \'Åtgärdade fel arkiveras; nytillkomna fel stoppar samtidig arkivering.\')\n\n    def select(self, index):\n        if 0 <= index < len(self.visible):\n            issue = self.visible[index]\n            self.current_id = issue[\'id\']\n            self.details.setPlainText(f"Första: {issue[\'first\']}\\nSenaste: {issue[\'last\']}\\n\\n{issue[\'text\']}")\n        else:\n            self.current_id = None\n            self.details.clear()\n\n    def resolve(self):\n        if not self.current_id:\n            return\n        from logg import resolve_error_issue\n        if QMessageBox.question(self, \'Arkivera valt fel?\',\n                \'Detta markerar felet åtgärdat i listan, men reparerar inte orsaken.\\n\'\n                \'Originalet sparas i resolved-errors. Fortsätt?\', QMessageBox.Yes | QMessageBox.No,\n                QMessageBox.No) != QMessageBox.Yes:\n            return\n        try:\n            resolve_error_issue(self.current_id, self.digest)\n        except (OSError, ValueError) as exc:\n            QMessageBox.warning(self, \'Arkivering stoppad\', str(exc))\n        self.refresh()\n\n    def display_report(self):\n        from qt_diagnostics import startup_report\n        from settings import BASE_DIR\n        from PySide6.QtCore import qVersion\n        report = startup_report(BASE_DIR, \'manual-system-check\')\n        report[\'qt_version\'] = qVersion()\n        report[\'screens\'] = [dict(width=s.availableGeometry().width(), height=s.availableGeometry().height(),\n                                  dpi=round(s.logicalDotsPerInch(), 2), ratio=s.devicePixelRatio())\n                             for s in QApplication.screens()]\n        return report\n\n    def system_check(self):\n        self.timer.stop()\n        try:\n            self.details.setPlainText(json.dumps(self.display_report(), ensure_ascii=False, indent=2))\n        except Exception as exc:\n            QMessageBox.warning(self, \'Systemkontroll misslyckades\', str(exc))\n\n    def export(self):\n        from logg import export_diagnostic_package\n        if QMessageBox.question(self, \'Exportera lokalt felsökningspaket?\',\n                \'ZIP-filen innehåller loggar, fel, tolk-/paketversioner, uppdateringsstatus och skärmdata.\\n\'\n                \'Personliga sökvägar och feltexter kan finnas. Inga projektfiler eller \'\n                \'inställningsfiler samlas in och ingenting skickas. Granska ZIP-filen innan delning.\',\n                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:\n            return\n        path, _ = QFileDialog.getSaveFileName(self, \'Spara felsökningspaket\', \'FolderForge-felsokning.zip\', \'ZIP (*.zip)\')\n        if not path:\n            return\n        try:\n            export_diagnostic_package(path, self.display_report())\n            QMessageBox.information(self, \'Export klar\', f\'Sparad lokalt:\\n{path}\\nIngenting har skickats.\')\n        except (OSError, ValueError) as exc:\n            QMessageBox.warning(self, \'Export misslyckades\', str(exc))\n',
'qt_integrations.py': '"""Qt-safe global shortcut bridge. Registration errors are logged, never hidden."""\nimport logging\nfrom PySide6.QtCore import QObject, Signal\nfrom app_core import validate_hotkey_combo, hotkey_expression\nfrom historik import read_json_safe, atomic_write_json\nfrom settings import HOTKEY_CONFIG, DEFAULT_HOTKEY\n\n\nclass HotkeyBridge(QObject):\n    activated = Signal()\n    status = Signal(str)\n\n    def __init__(self, parent):\n        super().__init__(parent)\n        self.listener = None\n        data = read_json_safe(HOTKEY_CONFIG, {})\n        keys = data.get(\'hotkey\', DEFAULT_HOTKEY) if isinstance(data, dict) else DEFAULT_HOTKEY\n        ok, normalized, error = validate_hotkey_combo(keys)\n        self.keys = normalized if ok else list(DEFAULT_HOTKEY)\n        self.activated.connect(parent.restore)\n        self.last_status = \'\'\n\n    def register(self, keys=None, save=False):\n        ok, normalized, error = validate_hotkey_combo(keys if keys is not None else self.keys)\n        if not ok:\n            raise ValueError(error)\n        expression = hotkey_expression(normalized)\n        from pynput import keyboard\n        keyboard.HotKey.parse(expression)\n        if save and not atomic_write_json(HOTKEY_CONFIG, {\'hotkey\': normalized}):\n            raise OSError(\'Snabbtangenten kunde inte sparas\')\n        if self.listener is not None:\n            self.listener.stop()\n        self.listener = keyboard.GlobalHotKeys({expression: self.activated.emit})\n        self.listener.start()\n        self.keys = normalized\n        self.last_status = \'Snabbtangent aktiv: \' + \' + \'.join(normalized)\n        self.status.emit(self.last_status)\n\n    def start(self):\n        try:\n            self.register()\n        except Exception as exc:\n            self.last_status = \'Snabbtangent ej tillgänglig: \' + str(exc)\n            logging.getLogger(\'qt.hotkey\').warning(self.last_status, exc_info=True)\n            self.status.emit(self.last_status)\n\n    def stop(self):\n        if self.listener is not None:\n            self.listener.stop()\n            self.listener = None\n',
'Starta-FolderForge-Tk.py': '#!/usr/bin/env python3\n"""Explicit legacy Tk reserve. Never mix Qt/Tk event loops in one process."""\nimport os\nfrom pathlib import Path\nfrom updater import launch_portable\n\nif __name__ == \'__main__\':\n    os.environ[\'FOLDERFORGE_GUI\'] = \'tk\'\n    launch_portable(Path(__file__).resolve().parent)\n',
'requirements-tk.txt': '# Manual installation by the user/IT only. The app never runs pip at startup.\ncustomtkinter>=5.2,<6\nPillow>=10\npystray>=0.19\npynput>=1.7\ntkinterdnd2>=0.4\npywin32>=306; sys_platform == "win32"\n',
'os_startup.py': '"""Shared OS startup integration. No GUI imports and no changes without explicit calls."""\nfrom __future__ import annotations\nimport ctypes\nimport logging\nimport os\nimport re\nimport subprocess\nimport sys\nfrom pathlib import Path\nfrom typing import Any, Callable, Dict, Iterable, List, Optional, Tuple\nfrom settings import APP_ICON, BASE_DIR, IS_WINDOWS\nlogger = logging.getLogger(__name__)\n\ndef build_autostart_command(script_args: Optional[Iterable[str]] = None) -> str:\n    """\n    Bygger autostart-kommandot och GARANTERAR att ingen svart konsolruta\n    visas vid inloggning:\n      • fryst exe (PyInstaller/Nuitka) → "exe" --tray  (ingen python alls)\n      • Python-källkod på Windows → egen FolderForge.exe med inbäddad ikon\n      • inga .pyw-filassociationer eller Python-ikoner i autostartgenvägen\n    """\n    args = list(script_args) if script_args else ["--tray"]\n    quoted_args = " ".join(f\'"{a}"\' for a in args)\n\n    if getattr(sys, "frozen", False):\n        return f\'"{sys.executable}" {quoted_args}\'.strip()\n\n    exe = Path(sys.executable)\n    if IS_WINDOWS:\n        from updater import ensure_launcher\n        # En egen winexe med inbäddad ikon, inte .pyw-filassociationen.\n        launcher = ensure_launcher(BASE_DIR, exe, APP_ICON)\n        return f\'"{launcher}" {quoted_args}\'.strip()\n    return f\'"{exe}" "{Path(sys.argv[0]).resolve()}" {quoted_args}\'\n\n\ndef is_stale_console_entry(command: str) -> bool:\n    """\n    True om kommandoraden refererar konsol-python (python.exe / python3.12.exe)\n    istället för pythonw.exe eller en fryst exe — d.v.s. skulle visa en svart\n    konsolruta vid inloggning.\n\n    REN STRÄNGANALYS av Windows-kommandosemantik. Medvetet UTAN plattformsgrind:\n    frågan "pekar detta på konsol-python?" är meningsfull oavsett var koden körs,\n    och en grind här gjorde funktionen värdelös för headless-testning (C47) samt\n    bröt befintliga tester. Plattformsgrinden hör hemma i repair_stale_autostart,\n    som redan returnerar \'skipped\' utanför Windows när ingen backend injicerats.\n    I produktion körs denna funktion endast på Windows.\n    """\n    if not command:\n        return False\n    if getattr(sys, "frozen", False):\n        return False\n    low = command.lower()\n    if "pythonw" in low:\n        return False\n    return "python" in low\n\n\nAUTOSTART_KEY_PATH: str = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"\n\n\nclass _WinregBackend:\n    """Standardbackend mot det riktiga Windows-registret."""\n\n    def read(self, key_path: str, value_name: str) -> Optional[str]:\n        import winreg\n        try:\n            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,\n                                winreg.KEY_READ) as k:\n                data, kind = winreg.QueryValueEx(k, value_name)\n                return str(data)\n        except FileNotFoundError:\n            return None\n        except OSError as exc:\n            logger.warning("Kunde inte läsa autostart: %s", exc)\n            return None\n\n    def write(self, key_path: str, value_name: str, command: str) -> bool:\n        import winreg\n        try:\n            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,\n                                winreg.KEY_SET_VALUE | winreg.KEY_READ) as k:\n                winreg.SetValueEx(k, value_name, 0, winreg.REG_SZ, command)\n                # VERIFY-AFTER-WRITE: läs tillbaka inom samma nyckelhantering\n                back, _kind = winreg.QueryValueEx(k, value_name)\n                return str(back) == command\n        except OSError as exc:\n            logger.error("Kunde inte skriva autostart: %s", exc)\n            return False\n\n    def delete(self, key_path: str, value_name: str) -> bool:\n        import winreg\n        try:\n            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,\n                                winreg.KEY_SET_VALUE) as k:\n                try:\n                    winreg.DeleteValue(k, value_name)\n                except FileNotFoundError:\n                    return True            # redan borta = önskat läge\n                return self.read(key_path, value_name) is None\n        except OSError as exc:\n            logger.error("Kunde inte ta bort autostart: %s", exc)\n            return False\n\n\ndef _backend(reg: Any) -> Any:\n    return reg if reg is not None else _WinregBackend()\n\n\ndef read_autostart_entry(app_name: str, reg: Any = None,\n                         key_path: str = AUTOSTART_KEY_PATH) -> Optional[str]:\n    """Befintligt registervärde, eller None om det inte finns."""\n    if not IS_WINDOWS and reg is None:\n        return None\n    return _backend(reg).read(key_path, app_name)\n\n\ndef write_autostart_entry(app_name: str, command: str, reg: Any = None,\n                          key_path: str = AUTOSTART_KEY_PATH) -> Tuple[bool, str]:\n    """\n    Skriv autostartkommando och verifiera att det faktiskt lagrades.\n    Returnerar (lyckades?, det som nu står i registret).\n    """\n    if not command or not command.strip():\n        return False, ""\n    backend = _backend(reg)\n    if not IS_WINDOWS and reg is None:\n        return False, ""\n    ok = backend.write(key_path, app_name, command)\n    stored = backend.read(key_path, app_name) or ""\n    if ok and stored != command:\n        logger.warning("Verify-after-write avvek: skrev %r, läste %r", command, stored)\n        return False, stored\n    return bool(ok), stored\n\n\ndef delete_autostart_entry(app_name: str, reg: Any = None,\n                           key_path: str = AUTOSTART_KEY_PATH) -> bool:\n    """Ta bort autostart. True även om värdet redan saknades."""\n    if not IS_WINDOWS and reg is None:\n        return True\n    return bool(_backend(reg).delete(key_path, app_name))\n\n\ndef repair_stale_autostart(app_name: str, reg: Any = None,\n                           script_args: Optional[List[str]] = None,\n                           key_path: str = AUTOSTART_KEY_PATH,\n                           command_builder: Optional[Any] = None) -> str:\n    """\n    C44: upptäck och reparera ett autostartvärde som skulle visa en svart\n    konsolruta (pekar på python.exe istället för pythonw.exe).\n\n    Returnerar en av:\n      \'not_set\'   — ingen autostart registrerad (inget att göra)\n      \'ok\'        — värde finns och är korrekt\n      \'repaired\'  — trasigt värde funnet och omskrivet (verify-after-write OK)\n      \'error\'     — reparation misslyckades (loggat)\n      \'skipped\'   — ej Windows och ingen injicerad backend\n\n    command_builder: valfri funktion (script_args) -> kommandosträng. Default\n    är build_autostart_command. Injicerbar eftersom den är plattformsberoende —\n    utan detta går Windows-reparationsgrenen inte att testa headless på Linux.\n    """\n    injected = reg is not None\n\n    if not IS_WINDOWS and not injected:\n        return "skipped"\n\n    current = read_autostart_entry(app_name, reg, key_path)\n    if current is None:\n        return "not_set"\n    if not is_stale_console_entry(current):\n        return "ok"\n\n    builder = command_builder if callable(command_builder) else build_autostart_command\n    fixed = builder(script_args or ["--tray"])\n\n    # B7/v5.0 — IDEMPOTENSVAKT, validering FÖRE skrivning.\n    #\n    # Utan denna vakt fanns en verklig oändlig reparations-loop. När\n    # pythonw.exe saknas (embedded Python, omdömd interpreter) bygger\n    # build_autostart_command() fallback-grenen\n    #     cmd /c start "" /B "C:\\Python312\\python.exe" "..."\n    # och is_stale_console_entry() dömer ut EXAKT den formen som stale, eftersom\n    # den innehåller "python" men inte "pythonw". Funktionen skrev därför\n    # tillbaka ett värde identiskt med det befintliga, och nästa uppstart\n    # "reparerade" igen: en registerskrivning och en WARNING i loggen vid VARJE\n    # start, i all evighet, utan att problemet någonsin löstes.\n    #\n    # v4.3 validerade dessutom EFTER skrivning, så ett känt trasigt värde hann\n    # hamna i registret innan felet upptäcktes. Nu skrivs ingenting alls om\n    # det byggda kommandot inte är en faktisk förbättring.\n    #\n    # Returvärdet är medvetet oförändrat ("error") för att inte bryta det\n    # dokumenterade kontraktet eller befintliga tester — skillnaden är att\n    # registret inte längre skrivs i onödan och att loggen säger vad användaren\n    # faktiskt behöver göra.\n    if fixed == current:\n        logger.error(\n            "Autostart kan inte repareras automatiskt: det byggda kommandot "\n            "skiljer sig inte från det befintliga (%r). Saknas pythonw.exe? "\n            "Bygg en fryst .exe med --windowed.", current)\n        return "error"\n    if is_stale_console_entry(fixed):\n        logger.error(\n            "Autostart kan inte repareras automatiskt: det byggda kommandot "\n            "visar fortfarande en konsolruta (%r) och skrivs därför INTE till "\n            "registret. Saknas pythonw.exe? Bygg en fryst .exe med --windowed.",\n            fixed)\n        return "error"\n\n    logger.warning("Stale autostart upptäckt (konsol-python): %r — reparerar.", current)\n    ok, stored = write_autostart_entry(app_name, fixed, reg, key_path)\n    if ok and not is_stale_console_entry(stored):\n        logger.info("Autostart reparerad till: %r", stored)\n        return "repaired"\n    logger.error("Autostart-reparation misslyckades; registret innehåller %r", stored)\n    return "error"\n\n\nAUTOSTART_TASK_NAME: str = "FolderForge_Autostart"\n\n\n_CSLID_STARTUP: int = 0x0007\n\n\ndef get_startup_folder(\n    windll: Any = None, create: bool = False,\n) -> Optional[Path]:\n    """\n    Sökvägen till användarens Start-meny\\\\Program\\\\Startup (shell:startup).\n\n    Prova SHGetKnownFolderPath (Vista+) och fall tillbaka på\n    SHGetFolderPathW med CSIDL_STARTUP. Returnerar None utanför Windows\n    eller om båda misslyckas.\n\n    Kastar aldrig.\n    """\n    if not IS_WINDOWS:\n        return None\n\n    dll = windll if windll is not None else getattr(ctypes, "windll", None)\n    if dll is None:\n        return None\n\n    # 1) Modern API: SHGetKnownFolderPath. GUID-strukturen byggs manuellt med\n    #    ctypes så att inget extra beroende (comtypes/pywin32) krävs för att\n    #    hitta mappen — detta är en fallback-väg och måste vara beroendefri.\n    try:\n        shell32 = dll.shell32\n        ole32 = dll.ole32\n\n        class GUID(ctypes.Structure):\n            _fields_ = [\n                ("Data1", ctypes.c_ulong),\n                ("Data2", ctypes.c_ushort),\n                ("Data3", ctypes.c_ushort),\n                ("Data4", ctypes.c_ubyte * 8),\n            ]\n\n        g = GUID()\n        g.Data1 = 0xB97D20BB\n        g.Data2 = 0xF46A\n        g.Data3 = 0x4C97\n        for i, byte in enumerate(\n                (0xBA, 0x10, 0x5E, 0x36, 0x08, 0x43, 0x08, 0x54)):\n            g.Data4[i] = byte\n\n        out = ctypes.c_wchar_p()\n        # KF_FLAG_DEFAULT = 0\n        hr = shell32.SHGetKnownFolderPath(\n            ctypes.byref(g), 0, None, ctypes.byref(out))\n        if hr == 0 and out.value:\n            p = Path(out.value)\n            try:\n                ole32.CoTaskMemFree(out)\n            except Exception:\n                pass\n            if create:\n                try:\n                    p.mkdir(parents=True, exist_ok=True)\n                except OSError as exc:\n                    logger.debug("Kunde inte skapa startup-mappen: %s", exc)\n            return p\n    except Exception as exc:                        # pragma: no cover - OS\n        logger.debug("SHGetKnownFolderPath misslyckades: %s", exc)\n\n    # 2) Fallback: SHGetFolderPathW med CSIDL_STARTUP\n    try:\n        buf = ctypes.create_unicode_buffer(260)     # MAX_PATH\n        # SHGetFolderPathW(hwnd, csidl, hToken, dwFlags, pszPath)\n        hr = dll.shell32.SHGetFolderPathW(None, _CSLID_STARTUP, None, 0, buf)\n        if hr == 0 and buf.value:\n            p = Path(buf.value)\n            if create:\n                try:\n                    p.mkdir(parents=True, exist_ok=True)\n                except OSError as exc:\n                    logger.debug("Kunde inte skapa startup-mappen: %s", exc)\n            return p\n    except Exception as exc:                        # pragma: no cover - OS\n        logger.debug("SHGetFolderPathW misslyckades: %s", exc)\n\n    return None\n\n\ndef write_startup_shortcut(\n    app_name: str,\n    command: str,\n    startup_dir: Optional[Path] = None,\n    runner: Optional[Callable[..., Any]] = None,\n    icon_path: Optional[Path] = None,\n) -> Tuple[bool, str]:\n    """\n    Skriv en autostart-genväg i Start-menyns startup-mapp.\n\n    .lnk via PowerShell WScript.Shell med appens ikon. Ingen generisk\n    .bat/.pyw-fallback: register eller Schemaläggaren kan starta vår exe.\n\n    Returnerar (ok, detalj). Kastar aldrig: detta är en fallback-väg som körs\n    NÄR registret redan nekat, och får inte självt krascha appen.\n    """\n    if not command or not command.strip():\n        return False, "tomt kommando"\n\n    folder = Path(startup_dir) if startup_dir else get_startup_folder(create=True)\n    if folder is None:\n        return False, "startup-mappen kunde inte hittas"\n    try:\n        folder.mkdir(parents=True, exist_ok=True)\n    except OSError as exc:\n        return False, f"startup-mappen är inte skrivbar: {exc}"\n\n    slug = re.sub(r"[^A-Za-z0-9_\\-]+", "_", str(app_name)).strip("_") or "App"\n    run = runner if runner is not None else subprocess.run\n\n    # ── Spår 1: riktig .lnk via PowerShell ────────────────────────\n    lnk = folder / f"{slug}.lnk"\n    match = re.fullmatch(r\'\\s*(?:"([^"]+)"|(\\S+))(?:\\s+(.*))?\', command.strip())\n    if not match:\n        return False, "ogiltigt startkommando"\n    exe = match.group(1) or match.group(2)\n    args = match.group(3) or ""\n\n    def _psq(text: Any) -> str:\n        """PowerShell-citering: \' dubbleras till \'\' i enkelciterade strängar.\n\n        Utan detta bröt en sökväg med apostrof (t.ex. C:\\\\Users\\\\Lisa\'s ...)\n        hela kommandot, och spår 1 föll tyst tillbaka på .bat-varianten."""\n        return str(text).replace("\'", "\'\'")\n\n    ps = (\n        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("\n        f"\'{_psq(lnk)}\');"\n        f"$s.TargetPath=\'{_psq(exe)}\';"\n        f"$s.Arguments=\'{_psq(args.strip())}\';"\n        f"$s.WorkingDirectory=\'{_psq(Path(exe).parent)}\';"\n        "$s.WindowStyle=7;"       # 7 = minimerad, ingen konsolruta\n    )\n    if icon_path is not None:\n        # Genvägen får appens ikon — annars visar Explorer Pythons standard.\n        ps += f"$s.IconLocation=\'{_psq(icon_path)},0\';"\n    ps += "$s.Save()"\n    try:\n        res = run(\n            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],\n            capture_output=True, text=True, timeout=25,\n            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),\n        )\n        if getattr(res, "returncode", 1) == 0 and lnk.exists():\n            legacy = folder / f"{slug}.bat"\n            if legacy.exists():\n                legacy.unlink()\n            return True, f"lnk:{lnk}"\n        logger.debug("PowerShell-genväg misslyckades: %s",\n                     getattr(res, "stderr", "")[:200])\n    except FileNotFoundError:\n        logger.debug("powershell finns inte — ingen ikonlös reservgenväg skapas.")\n    except Exception as exc:\n        logger.debug("PowerShell-genväg kastade: %s", exc)\n\n    # Registrera aldrig en generisk .bat/.pyw som ikonmässig reserv.\n    # Register/Schemaläggaren kan fortfarande starta vår brandade exe.\n    return False, "kunde inte skapa Windows-genväg med FolderForge-ikon"\n\n\ndef delete_startup_shortcut(\n    app_name: str, startup_dir: Optional[Path] = None,\n) -> bool:\n    """Ta bort både .lnk och .bat ur startup-mappen. Kastar aldrig."""\n    folder = Path(startup_dir) if startup_dir else get_startup_folder()\n    if folder is None or not folder.exists():\n        return True                                   # inget att ta bort\n    slug = re.sub(r"[^A-Za-z0-9_\\-]+", "_", str(app_name)).strip("_") or "App"\n    removed_any = True\n    for ext in (".lnk", ".bat"):\n        f = folder / f"{slug}{ext}"\n        try:\n            if f.exists():\n                f.unlink()\n        except OSError as exc:\n            logger.warning("Kunde inte ta bort %s: %s", f, exc)\n            removed_any = False\n    return removed_any\n\n\ndef read_startup_shortcut(app_name: str, startup_dir: Optional[Path] = None) -> Optional[str]:\n    """Returnera sökvägen till befintlig genväg, annars None. Kastar aldrig."""\n    folder = Path(startup_dir) if startup_dir else get_startup_folder()\n    if folder is None or not folder.exists():\n        return None\n    slug = re.sub(r"[^A-Za-z0-9_\\-]+", "_", str(app_name)).strip("_") or "App"\n    for ext in (".lnk", ".bat"):\n        f = folder / f"{slug}{ext}"\n        if f.exists():\n            return str(f)\n    return None\n\n\ndef build_task_scheduler_command(\n    app_name: str, command: str, task_name: Optional[str] = None,\n) -> List[str]:\n    """\n    Bygg schtasks-kommandot för "kör vid inloggning".\n\n    Returnerar en ARGUMENTLISTA (inte en sträng) så att anropet kan göras utan\n    shell=True — ingen injektionsrisk från användarens sökvägar (C19-anda).\n\n    /RL LIMITED  — kör utan förhöjda rättigheter, så att ingen UAC-prompt\n                   dyker upp vid inloggning (höger prio: användaren ser inget).\n    /SC ONLOGON  — vid inloggning, inte vid uppstart (app är per-användare).\n    /F           — skriv över befintlig uppgift (idempotent).\n    """\n    tn = str(task_name or AUTOSTART_TASK_NAME)\n    return [\n        "schtasks", "/Create", "/F",\n        "/TN", tn,\n        "/TR", str(command),\n        "/SC", "ONLOGON",\n        "/RL", "LIMITED",\n    ]\n\n\ndef register_task_scheduler(\n    app_name: str,\n    command: str,\n    task_name: Optional[str] = None,\n    runner: Optional[Callable[..., Any]] = None,\n) -> Tuple[bool, str]:\n    """\n    Registrera autostart via Task Scheduler — tredje spåret.\n\n    Mer robust än Run-nyckeln: överlever vissa gruppolicyer som rensar\n    HKCU\\\\...\\\\Run, och syns i schemaläggaren där användaren kan felsöka.\n\n    Returnerar (ok, detalj). Kastar aldrig.\n    """\n    if not IS_WINDOWS:\n        return False, "task scheduler är Windows-only"\n    if not command or not command.strip():\n        return False, "tomt kommando"\n\n    run = runner if runner is not None else subprocess.run\n    argv = build_task_scheduler_command(app_name, command, task_name)\n    try:\n        res = run(\n            argv, capture_output=True, text=True, timeout=25,\n            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),\n        )\n        rc = getattr(res, "returncode", 1)\n        if rc == 0:\n            return True, f"schtasks:{task_name or AUTOSTART_TASK_NAME}"\n        err = (getattr(res, "stderr", "") or getattr(res, "stdout", "") or "").strip()\n        return False, f"schtasks rc={rc}: {err[:200]}"\n    except FileNotFoundError:\n        return False, "schtasks.exe finns inte"\n    except subprocess.TimeoutExpired:\n        return False, "schtasks-timeout (25 s)"\n    except Exception as exc:\n        return False, f"schtasks kastade: {exc}"\n\n\ndef unregister_task_scheduler(\n    task_name: Optional[str] = None,\n    runner: Optional[Callable[..., Any]] = None,\n) -> Tuple[bool, str]:\n    """Avregistrera uppgiften. Saknad uppgift räknas som lyckat (idempotent)."""\n    if not IS_WINDOWS:\n        return True, "skipped"\n    tn = str(task_name or AUTOSTART_TASK_NAME)\n    run = runner if runner is not None else subprocess.run\n    try:\n        res = run(\n            ["schtasks", "/Delete", "/F", "/TN", tn],\n            capture_output=True, text=True, timeout=25,\n            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),\n        )\n        rc = getattr(res, "returncode", 1)\n        if rc == 0:\n            return True, "deleted"\n        err = (getattr(res, "stderr", "") or "").lower()\n        # "The system cannot find the file specified" → fanns inte redan\n        if "cannot find" in err or "inte hitta" in err:\n            return True, "not-present"\n        return False, f"schtasks rc={rc}: {err[:200]}"\n    except FileNotFoundError:\n        return False, "schtasks.exe finns inte"\n    except Exception as exc:\n        return False, f"schtasks kastade: {exc}"\n\n\ndef enable_autostart_all_methods(\n    app_name: str,\n    command: str,\n    reg_writer: Optional[Callable[..., Tuple[bool, Optional[str]]]] = None,\n    startup_dir: Optional[Path] = None,\n    runner: Optional[Callable[..., Any]] = None,\n    icon_path: Optional[Path] = None,\n) -> Dict[str, Any]:\n    """\n    Slå på autostart och rapportera utfallet för VARJE metod.\n\n    Detta är orkestreringen: registret först (billigast, mest osynligt),\n    därefter startup-genväg om registret nekade, därefter Task Scheduler.\n    Appen kräver att MINST EN lyckas — men rapporterar alla tre så att\n    diagnostiken (B5) kan visa exakt vad som hände.\n\n    Returnerar en dict: {"ok": bool, "methods": {namn: {"ok":..,"detail":..}}}\n    Kastar aldrig.\n    """\n    resultat: Dict[str, Any] = {"ok": False, "methods": {}}\n\n    # 1) Registret — använd befintlig write_autostart_entry om ingen injiceras\n    try:\n        writer = reg_writer\n        if writer is None:\n            writer = globals().get("write_autostart_entry")\n        if writer is not None:\n            ok, stored = writer(app_name, command)\n            resultat["methods"]["registry"] = {\n                "ok": bool(ok), "detail": stored or ("skrivet" if ok else "nekad"),\n            }\n        else:\n            resultat["methods"]["registry"] = {\n                "ok": False, "detail": "write_autostart_entry saknas"}\n    except Exception as exc:\n        resultat["methods"]["registry"] = {"ok": False, "detail": f"kastade: {exc}"}\n\n    # 2) Startup-genväg — prova ALLTID, så att vi har redundans\n    try:\n        ok, detail = write_startup_shortcut(app_name, command, startup_dir,\n                                            runner, icon_path=icon_path)\n        resultat["methods"]["startup_folder"] = {"ok": bool(ok), "detail": detail}\n    except Exception as exc:\n        resultat["methods"]["startup_folder"] = {"ok": False, "detail": f"kastade: {exc}"}\n\n    # 3) Task Scheduler — endast om de två första misslyckades (undvik\n    #    trippla poster som alla startar appen)\n    if not any(m["ok"] for m in resultat["methods"].values()):\n        try:\n            ok, detail = register_task_scheduler(app_name, command, None, runner)\n            resultat["methods"]["task_scheduler"] = {"ok": bool(ok), "detail": detail}\n        except Exception as exc:\n            resultat["methods"]["task_scheduler"] = {"ok": False, "detail": f"kastade: {exc}"}\n\n    resultat["ok"] = any(m["ok"] for m in resultat["methods"].values())\n    return resultat\n\n\ndef disable_autostart_all_methods(\n    app_name: str,\n    reg_deleter: Optional[Callable[..., Any]] = None,\n    startup_dir: Optional[Path] = None,\n    runner: Optional[Callable[..., Any]] = None,\n) -> Dict[str, Any]:\n    """\n    Stäng av autostart i ALLA tre mekanismer (idempotent).\n\n    Viktigt: v4.3 raderade bara Run-nyckeln. Om en genväg eller uppgift\n    skapats tidigare skulle appen fortsätta starta trots att rutan visar "av"\n    — ett tyst löftesbrott. Därför rensas alla tre.\n    """\n    resultat: Dict[str, Any] = {"ok": True, "methods": {}}\n    try:\n        deleter = reg_deleter or globals().get("delete_autostart_entry")\n        if deleter is not None:\n            deleter(app_name)\n            resultat["methods"]["registry"] = {"ok": True, "detail": "raderad"}\n        else:\n            resultat["methods"]["registry"] = {"ok": True, "detail": "saknad backend"}\n    except Exception as exc:\n        resultat["methods"]["registry"] = {"ok": False, "detail": f"kastade: {exc}"}\n        resultat["ok"] = False\n\n    try:\n        ok = delete_startup_shortcut(app_name, startup_dir)\n        resultat["methods"]["startup_folder"] = {\n            "ok": bool(ok), "detail": "rensad" if ok else "kunde inte raderas"}\n        if not ok:\n            resultat["ok"] = False\n    except Exception as exc:\n        resultat["methods"]["startup_folder"] = {"ok": False, "detail": f"kastade: {exc}"}\n        resultat["ok"] = False\n\n    try:\n        ok, detail = unregister_task_scheduler(None, runner)\n        resultat["methods"]["task_scheduler"] = {"ok": bool(ok), "detail": detail}\n        if not ok:\n            resultat["ok"] = False\n    except Exception as exc:\n        resultat["methods"]["task_scheduler"] = {"ok": False, "detail": f"kastade: {exc}"}\n        resultat["ok"] = False\n\n    return resultat\n\n\n\ndef configure_autostart(enabled, base=BASE_DIR, system=None):\n    """Explicit user action only. Never installs packages or bypasses OS policy."""\n    import plistlib\n    from historik import _fsync_dir\n    system = system or sys.platform\n    base = Path(base).resolve()\n    if system == \'win32\':\n        if enabled:\n            return enable_autostart_all_methods(\'FolderForge\', build_autostart_command(), icon_path=APP_ICON)\n        return disable_autostart_all_methods(\'FolderForge\')\n    if system == \'darwin\':\n        target = Path.home() / \'Library/LaunchAgents/se.folderforge.autostart.plist\'\n        content = plistlib.dumps(dict(Label=\'se.folderforge.autostart\', RunAtLoad=True,\n            ProgramArguments=[\'/bin/sh\', str(base / \'Starta-FolderForge.sh\')],\n            WorkingDirectory=str(base), ProcessType=\'Background\'))\n    elif system.startswith(\'linux\'):\n        target = Path(os.environ.get(\'XDG_CONFIG_HOME\', str(Path.home() / \'.config\'))) / \'autostart/FolderForge.desktop\'\n        def quote(value):\n            value = str(value)\n            if any(char in value for char in \'\\r\\n\'):\n                raise ValueError(\'Radbrytning i appens sökväg\')\n            return \'"\' + value.replace(\'%\', \'%%\').replace(\'\\\\\', \'\\\\\\\\\').replace(\'"\', \'\\\\"\').replace(\'`\', \'\\\\`\').replace(\'$\', \'\\\\$\') + \'"\'\n        content = (\'[Desktop Entry]\\nType=Application\\nName=FolderForge\\nTerminal=false\\n\'\n            \'Exec=/bin/sh \' + quote(base / \'Starta-FolderForge.sh\') + \'\\nIcon=\' +\n            str(base / \'Icon/projektmapp_icon_256.png\').replace(\'\\\\\', \'\\\\\\\\\') + \'\\n\').encode(\'utf-8\')\n    else:\n        raise ValueError(\'Operativsystemet stöds inte för autostart\')\n    if target.is_symlink() or target.parent.is_symlink():\n        raise ValueError(\'Symbolisk länk i autostartplatsen; ingen ändring görs\')\n    if enabled:\n        import tempfile\n        target.parent.mkdir(parents=True, exist_ok=True)\n        fd, temporary = tempfile.mkstemp(prefix=\'.folderforge-\', dir=target.parent)\n        try:\n            with os.fdopen(fd, \'wb\') as stream:\n                stream.write(content)\n                stream.flush()\n                os.fsync(stream.fileno())\n            os.replace(temporary, target)\n        finally:\n            if os.path.exists(temporary):\n                os.unlink(temporary)\n    else:\n        target.unlink(missing_ok=True)\n    return {\'ok\': True, \'methods\': {\'os_login\': {\'ok\': True,\n            \'detail\': (\'Aktiverad för nästa inloggning: \' if enabled else \'Avaktiverad: \') + str(target)}}}\n',
}
# END SHARED CORE PAYLOAD

RUNTIME_BOOTSTRAP_FILES = {
'Starta-FolderForge.ps1': r'''param([string]$PreferredPython = '', [string]$Arguments64 = '', [switch]$MaintenanceOnly)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
function Write-StartError([string]$Message) {
    try {
        $Logs = Join-Path $Root 'logs'
        [IO.Directory]::CreateDirectory($Logs) | Out-Null
        [IO.File]::AppendAllText((Join-Path $Logs 'folderforge-errors.log'),
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ERROR [launcher] ' + $Message + [Environment]::NewLine)
    } catch { }
}
function Remove-LegacyMaintenanceTask {
    # Retire only this installation's former weekly Python task.
    try {
        $Digest = [Security.Cryptography.SHA256]::Create()
        try { $Hash = (($Digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0,12) }
        finally { $Digest.Dispose() }
        $Name = 'FolderForge Python weekly ' + $Hash.ToUpperInvariant()
        $Task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        if ($Task) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction Stop }
    } catch { Write-StartError ('Could not remove obsolete Python task: ' + $_.Exception.Message) }
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
        if (-not $Process.WaitForExit(15000)) {
            # Only this freshly launched identity/GUI probe, never a running app.
            $Process.Kill()
            $Process.WaitForExit()
            throw 'Det lokala Python-provet svarade inte inom 15 sekunder'
        }
        return [pscustomobject]@{ Code = $Process.ExitCode; Out = $Out.Result; Err = $Err.Result }
    } finally { $Process.Dispose() }
}

function Write-StartInfo([string]$Message) {
    try {
        $Logs = Join-Path $Root 'logs'
        [IO.Directory]::CreateDirectory($Logs) | Out-Null
        [IO.File]::AppendAllText((Join-Path $Logs 'folderforge.log'),
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' INFO [launcher] ' + $Message + [Environment]::NewLine)
    } catch { }
}
function Resolve-ExistingPython([string]$Candidate) {
    if (-not $Candidate -or $Candidate -match '\\Microsoft\\WindowsApps\\') { return $null }
    if ([IO.Path]::GetFileName($Candidate) -match '^pythonw') { $Candidate = Join-Path (Split-Path $Candidate) 'python.exe' }
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $null }
    try {
        # Identity/version of an EXISTING interpreter, never package versions or downloads.
        $Code = 'import json,sys; print(json.dumps({"executable":getattr(sys,"_base_executable",sys.executable),"version":list(sys.version_info[:2])}))'
        $Result = Invoke-Hidden $Candidate @('-c',$Code)
        if ($Result.Code -ne 0) { throw $Result.Err }
        $Identity = (($Result.Out.Trim() -split "`n")[-1]) | ConvertFrom-Json
        $Console = [string]$Identity.executable
        if ([IO.Path]::GetFileName($Console) -match '^pythonw') { $Console = Join-Path (Split-Path $Console) 'python.exe' }
        $Windowless = Join-Path (Split-Path $Console) 'pythonw.exe'
        if (-not (Test-Path -LiteralPath $Windowless -PathType Leaf)) { throw 'pythonw.exe saknas' }
        return [pscustomobject]@{ Console = $Console; Windowless = $Windowless;
            Major = [int]$Identity.version[0]; Minor = [int]$Identity.version[1];
            Version = ([string]$Identity.version[0] + '.' + [string]$Identity.version[1]) }
    } catch {
        Write-StartInfo ('Hoppar över Python ' + $Candidate + ': ' + $_.Exception.Message)
        return $null
    }
}
function Test-ExistingPythonGui($Python) {
    if ($Python.Major -ne 3 -or $Python.Minor -lt 11) {
        Write-StartInfo ('Hoppar över Python ' + $Python.Version + ': appen kräver Python 3.11 eller senare')
        return $false
    }
    try {
        # Short-lived LOCAL functional probe. No app imports, settings, pip,
        # network, hotkey hooks, autostart or installations. Withdraw before update.
        if ($env:FOLDERFORGE_GUI -eq 'tk') {
        $Code = 'import tkinter,customtkinter; from PIL import Image; import pystray; r=customtkinter.CTk(); r.withdraw(); r.update_idletasks(); r.destroy()'
        } else {
            $Code = 'from PySide6.QtWidgets import QApplication; from PySide6.QtGui import QIcon; a=QApplication([]); a.processEvents(); a.quit()'
        }
        $Result = Invoke-Hidden $Python.Console @('-c',$Code)
        if ($Result.Code -eq 0) { return $true }
        $Reason = $Result.Err.Trim()
        if ($Reason.Length -gt 1200) { $Reason = $Reason.Substring($Reason.Length - 1200) }
        Write-StartInfo ('Hoppar över Python ' + $Python.Version + ' (' + $Python.Console + '): GUI-provet misslyckades. ' + $Reason)
    } catch {
        Write-StartInfo ('Hoppar över Python ' + $Python.Version + ' (' + $Python.Console + '): ' + $_.Exception.Message)
    }
    return $false
}
function Select-ExistingPython([string[]]$Candidates) {
    $Resolved = @()
    $PrimaryCandidate = @($Candidates | Where-Object { $_ -and $_ -notmatch '\\Microsoft\\WindowsApps\\' } | Select-Object -First 1)
    $Primary = $null
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        $Python = Resolve-ExistingPython $Candidate
        if ($Python -and $Resolved.Windowless -notcontains $Python.Windowless) { $Resolved += $Python }
        if ($Python -and $Candidate -eq $PrimaryCandidate[0]) { $Primary = $Python.Windowless }
    }
    if (-not $Resolved.Count) { return $null }
    # Keep the current PATH choice first. If unusable, prefer installed 3.14;
    # then try other installed versions, newest first. No version is installed.
    $Ordered = @($Resolved | Sort-Object @{Expression={
        if ($_.Windowless -eq $Primary) { 0 } elseif ($_.Version -eq '3.14') { 1 } else { 2 }
    }}, @{Expression={ -1 * $_.Minor }})
    foreach ($Python in $Ordered) {
        if (Test-ExistingPythonGui $Python) {
            Write-StartInfo ('Vald system-Python ' + $Python.Version + ': ' + $Python.Windowless)
            return $Python.Windowless
        }
    }
    return $null
}

function Get-PythonCandidates {
    $Candidates = New-Object 'System.Collections.Generic.List[string]'
    # Respect the system PATH instead of saved runtime state or a chosen version.
    foreach ($Name in @('python.exe','python3.exe','pythonw.exe')) {
        foreach ($Command in @(Get-Command $Name -All -ErrorAction SilentlyContinue)) { $Candidates.Add($Command.Source) }
    }
    $Py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($Py) {
        # Listing does not execute a Store alias or install a missing Python.
        try { $Listed = Invoke-Hidden $Py.Source @('-0p') }
        catch { $Listed = [pscustomobject]@{ Out = '' } }
        $Lines = @($Listed.Out -split "`n")
        foreach ($Line in @($Lines | Sort-Object { if ($_ -match '\*') { 0 } else { 1 } })) {
            if ($Line -match '([A-Za-z]:\\.*pythonw?\.exe)\s*$') { $Candidates.Add($Matches[1].Trim()) }
        }
    }
    # Also discover normally registered installs when py.exe is absent.
    foreach ($RegistryRoot in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore', 'HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        foreach ($VersionKey in @(Get-ChildItem -LiteralPath $RegistryRoot -ErrorAction SilentlyContinue)) {
            $InstallKey = Get-Item -LiteralPath ($VersionKey.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
            if ($InstallKey) {
                $Executable = [string]$InstallKey.GetValue('ExecutablePath')
                if (-not $Executable) {
                    $InstallDir = [string]$InstallKey.GetValue('')
                    if ($InstallDir) { $Executable = Join-Path $InstallDir 'python.exe' }
                }
                if ($Executable) { $Candidates.Add($Executable) }
            }
        }
    }
    if ($PreferredPython) { $Candidates.Add($PreferredPython) }
    foreach ($Pattern in @("$env:LOCALAPPDATA\Programs\Python\Python*\python.exe", "$env:USERPROFILE\miniconda3\python.exe", "$env:USERPROFILE\anaconda3\python.exe", "$env:ProgramData\Anaconda3\python.exe")) {
        foreach ($File in @(Get-Item -Path $Pattern -ErrorAction SilentlyContinue)) { $Candidates.Add($File.FullName) }
    }
    return $Candidates.ToArray()
}
function Test-AnyInstalledPython([string[]]$Candidates) {
    # Presence, NOT GUI compatibility: old/broken Python must never trigger setup.
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and $Candidate -notmatch '\\Microsoft\\WindowsApps\\' -and
            (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $true }
    }
    return $false
}
function Get-LatestStablePythonPackageId([string]$Listing) {
    $Minors = @()
    foreach ($Line in ($Listing -split "`n")) {
        if ($Line -match '(?i)preview|alpha|beta|\drc\d|\d[aAbB]\d|\bdev\b') { continue }
        foreach ($Match in [regex]::Matches($Line, 'Python\.Python\.3\.(\d+)(?![\w.])')) {
            $Minor = [int]$Match.Groups[1].Value
            if ($Minor -ge 11) { $Minors += $Minor }
        }
    }
    if (-not $Minors.Count) { return $null }
    return 'Python.Python.3.' + ($Minors | Sort-Object -Descending -Unique | Select-Object -First 1)
}
function Invoke-PythonInstaller([string]$File, [string[]]$Arguments) {
    # Used ONLY after explicit consent and confirmed absence, never for upgrades.
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $File
    $Info.Arguments = (($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Process = [Diagnostics.Process]::Start($Info)
    try {
        $Out = $Process.StandardOutput.ReadToEndAsync()
        $Err = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        return [pscustomobject]@{ Code=$Process.ExitCode; Out=$Out.Result; Err=$Err.Result }
    } finally { $Process.Dispose() }
}
function Offer-MissingPythonInstall {
    $Dialog = New-Object -ComObject WScript.Shell
    $Answer = $Dialog.Popup('Ingen Python-installation hittades. Vill du installera den senaste stabila Python som finns i winget? Installationen sker bara efter ditt ja och kan stoppas av arbetsgivarens IT-policy. Wingets käll- och paketvillkor godkänns för hämtningen; Python-installationsprogrammet visas. Om winget saknas öppnas i stället python.org för manuell installation. FolderForges extra paket installeras inte.', 0, 'FolderForge - Python saknas', 4 + 32 + 256)
    if ($Answer -ne 6) { Write-StartInfo 'Python saknas; användaren avstod installation.'; return $false }
    $Winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $Winget) {
        Start-Process 'https://www.python.org/downloads/windows/'
        Write-StartInfo 'Öppnade python.org efter samtycke; ingen installation kördes av startfilen.'
        return $false
    }
    $Listing = Invoke-PythonInstaller $Winget.Source @('search','--id','Python.Python.3','--source','winget','--accept-source-agreements','--disable-interactivity')
    if ($Listing.Code -ne 0) { throw ('Kunde inte läsa wingets Python-lista: ' + $Listing.Err) }
    $Id = Get-LatestStablePythonPackageId $Listing.Out
    if (-not $Id) { throw 'Ingen entydig stabil Python hittades i winget. Ingen installation kördes.' }
    # Recheck just before installation in case a concurrent installer finished.
    if (Test-AnyInstalledPython @(Get-PythonCandidates)) { return $true }
    Write-StartInfo ('Uttryckligen godkänd förstagångsinstallation: ' + $Id)
    $Installed = Invoke-PythonInstaller $Winget.Source @('install','--id',$Id,'--exact','--source','winget','--scope','user','--interactive','--accept-source-agreements','--accept-package-agreements')
    if ($Installed.Code -ne 0) { throw ('Python installerades inte (winget exit ' + $Installed.Code + '): ' + $Installed.Err) }
    return $true
}


try {
    Remove-LegacyMaintenanceTask
    # Backward-compatible exit for a previously scheduled maintenance invocation.
    if ($MaintenanceOnly) { exit 0 }
    $Candidates = @(Get-PythonCandidates)
    if (-not (Test-AnyInstalledPython $Candidates)) {
        # The only install offer in the app: absence, never a failed GUI probe.
        $SetupLock = New-Object Threading.Mutex($false, 'Local\FolderForge_FirstPythonSetup')
        $OwnSetup = $false
        try {
            $OwnSetup = $SetupLock.WaitOne(0)
            if (-not $OwnSetup) { throw 'En Python-installationsdialog är redan aktiv. Starta igen när den är klar.' }
            $Candidates = @(Get-PythonCandidates)
            if (-not (Test-AnyInstalledPython $Candidates)) {
                if (-not (Offer-MissingPythonInstall)) { exit 0 }
            }
            $Candidates = @(Get-PythonCandidates)
        } finally {
            if ($OwnSetup) { $SetupLock.ReleaseMutex() }
            $SetupLock.Dispose()
        }
    }
    $Windowless = Select-ExistingPython -Candidates @($Candidates)
    if (-not $Windowless) { throw 'Ingen installerad system-Python kunde köra appens GUI-beroenden. Se hoppade tolkar i folderforge.log. Ingen Python eller paket installerades eller uppgraderades.' }
    $AppArgs = @('--tray')
    if ($Arguments64) { $AppArgs = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Arguments64)).Split(@([char]0), [StringSplitOptions]::RemoveEmptyEntries)) }
    if ($AppArgs -notcontains '--tray') { $AppArgs += '--tray' }
    $env:FOLDERFORGE_RUNTIME_READY = '1'
    $env:FOLDERFORGE_RUNTIME_POLICY = 'system-python'
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $Windowless
    $Target = Join-Path $Root 'folder.pyw'
    $Supervisor = Join-Path $Root 'data/update-supervisor.py'
    if ((Test-Path -LiteralPath (Join-Path $Root 'data/update-transaction.json')) -and (Test-Path -LiteralPath $Supervisor)) {
        $Target = $Supervisor
        $AppArgs = @('--recover',$Root,$Windowless)
    }
    $Start.Arguments = (Quote-Argument $Target) + ' ' + (($AppArgs | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Start.WorkingDirectory = $Root
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.EnvironmentVariables.Remove('PYTHONHOME')
    $Start.EnvironmentVariables.Remove('PYTHONPATH')
    $Child = [Diagnostics.Process]::Start($Start)
    $Child.Dispose()
    exit 0
} catch {
    Write-StartError $_.Exception.Message
    exit 1
}
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
