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
OPTIONAL_FILES = frozenset({"app_core.py", "instance_lock.py", "qt_app.py", "workspace.py", "qt_preview.py", "Starta-FolderForge-Qt.py", "requirements-qt.txt", "Starta-FolderForge.py", "requirements.txt", "Starta-FolderForge.sh",
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
        raise ValueError('Appfiler ändrades före startbekräftelsen')
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
'app_core.py': '"""Shared GUI-independent project/domain logic. Extracted from the tested Tk app."""\nfrom __future__ import annotations\nimport atexit\nimport ctypes\nimport logging\nimport os\nimport re\nimport shutil\nimport tempfile\nimport time\nfrom datetime import datetime\nfrom pathlib import Path\nfrom dataclasses import dataclass, field, asdict\nfrom typing import Any, Callable, Dict, Final, Iterable, List, Optional, Sequence, Set, Tuple\nfrom settings import *\nfrom historik import atomic_write_json, read_json_safe\nlogger = logging.getLogger(__name__)\n\ndef validate_settings(data: Any) -> Tuple[Dict[str, Any], bool, List[str]]:\n    """\n    Returnerar (rensat_data, reparerad?, loggrader).\n    Okända nycklar behålls (framåtkompatibilitet) men ogiltiga TYPER och\n    ogiltiga ENUM-värden korrigeras till default — aldrig krasch.\n    """\n    log: List[str] = []\n    repaired = False\n\n    if not isinstance(data, dict):\n        return dict(), True, ["settings var inte en dict — nollställd till schema"]\n\n    out: Dict[str, Any] = dict(data)\n\n    for key, (typ, default) in SETTINGS_SCHEMA.items():\n        if key not in out or not isinstance(out[key], typ):\n            if key in out:\n                # log-listan är en vanlig lista → formatering sker direkt.\n                # (Lazy %s gäller endast logger-anrop, aldrig list.append.)\n                log.append("ogiltigt värde för %s (%r) → default" % (key, out[key]))\n                repaired = True\n            out[key] = default if not callable(default) else default()\n\n    for key, allowed in SETTINGS_ENUMS.items():\n        if out.get(key) not in allowed:\n            log.append("\'%s\' = %r ej i %s → %s" % (\n                key, out.get(key), tuple(allowed), SETTINGS_SCHEMA[key][1]))\n            out[key] = SETTINGS_SCHEMA[key][1]\n            repaired = True\n\n    if not out.get("save_root"):\n        out["save_root"] = str(Path.home() / "Projects")\n        repaired = True\n\n    tabs = out.get("visible_tabs")\n    if not isinstance(tabs, dict):\n        tabs = {}\n    cleaned_tabs: Dict[str, bool] = {}\n    for name, val in tabs.items():\n        cleaned_tabs[str(name)] = bool(val)\n    out["visible_tabs"] = cleaned_tabs\n\n    if out.get("start_minimized") is not True:\n        out["start_minimized"] = True\n        repaired = True\n        log.append("start_minimized → True (obligatorisk start i systemfältet)")\n    return out, repaired, log\n\n\nRESERVED_STEM_RE = re.compile(\n    r\'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\\..*)?$\', re.IGNORECASE,\n)\n\n\ndef sanitize_name(name: str, *, max_len: int = 255) -> str:\n    """\n    Rensar ett mapp-/filnamn enligt Windows-regler:\n      • ogiltiga tecken → \'_\'\n      • inledande/avslutande mellanslag och punkter tas bort\n      • reserverade namn blockeras ÄVEN med filändelse (CON.txt, NUL.md …)\n      • längdtak\n    """\n    if not isinstance(name, str):\n        raise ValueError("Namnet måste vara en sträng.")\n    cleaned = INVALID_NAME_CHARS.sub(\'_\', name)\n    cleaned = cleaned.strip().strip(\'.\').strip()\n    if not cleaned:\n        raise ValueError("Mappnamnet är tomt efter rensning.")\n    if cleaned.upper() in INVALID_NAMES or RESERVED_STEM_RE.match(cleaned):\n        raise ValueError(f"\'{cleaned}\' är ett reserverat systemnamn.")\n    if len(cleaned) > max_len:\n        raise ValueError(f"Mappnamnet är för långt (max {max_len} tecken).")\n    return cleaned\n\n\n_PLATE_RE = re.compile(\n    r"""^\\s*\n    (?P<bokst>[a-z]{3})              # tre bokstäver (ABC)\n    [\\s\\-–—]*                        # fri separator: mellanslag/streck/inget\n    (?:\n        (?P<s2>\\d{2})[\\s\\-]*(?P<s3>\\d)      # äldre format: ABC 123 (1973–2019)\n      | (?P<n2>\\d{2})[\\s\\-]*(?P<nb>[a-z])   # nyare format: ABC 12 A (2019–)\n    )\n    (?![a-zA-Z0-9])                  # regnr:t får inte flyta ihop med mer text\n    """,\n    re.IGNORECASE | re.VERBOSE,\n)\n\n\n_SUFFIX_STRIP = " \\t-–—_\\u00b7"   # tecken som inte ska inleda den fria texten\n\n\ndef normalize_plate_name(name: str) -> Tuple[str, Optional[str]]:\n    """\n    Normalisera ett projektnamn som BÖRJAR med ett svenskt registreringsnummer.\n\n      \'dss 817\'           → (\'DSS817\', \'DSS817\')\n      \'dss 81 7\'          → (\'DSS817\', \'DSS817\')\n      \'dss 817 stenskott\' → (\'DSS817 stenskott\', \'DSS817\')   (suffix orört)\n      \'abc 12 a 2021\'     → (\'ABC12A 2021\', \'ABC12A\')\n      \'Biltest\'           → (\'Biltest\', None)                (ingen ändring)\n\n    Båda svenska formaten stöds: ABC123 (1973–2019) och ABC12A (2019–).\n    Matchningen är medvetet tolerant (mellanslag/streck ignoreras, I/Q/V\n    blockeras inte): funktionen VARNAR mjukt via returvärdet None — den\n    stoppar eller ändrar aldrig ett namn som inte matchar.\n\n    Versaliseringen av HELA namnet sker av anroparen (safe_name.upper());\n    här normaliseras bara regnr-delen och gränsen mot fri eftertext.\n\n    Returnerar (ev. normaliserat namn, regnr eller None).\n    """\n    m = _PLATE_RE.match(name or "")\n    if not m:\n        return (name, None)\n    regnr = (m.group("bokst") + (m.group("s2") or m.group("n2"))\n             + (m.group("s3") or m.group("nb") or "")).upper()\n    suffix = name[m.end():].lstrip(_SUFFIX_STRIP)\n    return (regnr + ((" " + suffix) if suffix else ""), regnr)\n\n\ndef strip_root_level(items: List[Dict[str, Any]], root_name: str) -> Tuple[List[Dict[str, Any]], bool]:\n    """\n    Malltext och inklistrade träd har sin rot på rad 1 (\'projektnamn/\',\n    \'ärendenummer/\'), men _build_structure skapar redan\n    base = save_root / root_name. Utan denna funktion blir resultatet:\n\n        PROJEKT123/\n        └── PROJEKT123/      ← dublett (MB5)\n            ├── src/ ...\n\n    Bevis för att rad 1 ÄR roten: de inbyggda mallarna använder\n    \'projektnamn\'/\'ärendenummer\' som placeholder som ersätts med användarens\n    namn via .replace() — alltså är rad 1 per definition roten.\n\n    Regel: finns EXAKT EN post på toppnivå och den är en mapp, skalas den\n    nivån bort från alla poster. Flera toppnivåposter (docs/ + src/) lämnas\n    orörda, eftersom base då redan är deras gemensamma förälder.\n\n    Returnerar (nya_items, skalades_nivån_bort?).\n    """\n    if not items:\n        return items, False\n\n    top = [it for it in items if len(it.get(\'path\', [])) == 1]\n    if len(top) != 1 or not top[0].get(\'is_dir\'):\n        return items, False\n\n    root_label = str(top[0][\'path\'][0]).strip()\n    stripped: List[Dict[str, Any]] = []\n    for it in items:\n        path = list(it.get(\'path\', []))\n        if len(path) <= 1:\n            continue                      # själva rotraden försvinner\n        new_it = dict(it)\n        new_it[\'path\'] = path[1:]\n        stripped.append(new_it)\n\n    if not stripped:\n        # Endast en tom rotmapp i mallen → behåll originalet så att\n        # användaren inte står utan innehåll.\n        return items, False\n\n    return stripped, True\n\n\nMAX_TREE_DEPTH: int = 40\n\n\nMAX_TREE_ENTRIES: int = 20000\n\n\nTREE_IGNORED_DIRS = frozenset({\n    \'.git\', \'__pycache__\', \'.idea\', \'.vscode\',\n    \'node_modules\', \'venv\', \'.env\', \'.tox\',\n})\n\n\ndef generate_tree_string_safe(\n    root_path: Path,\n    max_depth: int = MAX_TREE_DEPTH,\n    max_entries: int = MAX_TREE_ENTRIES,\n    include_dotfiles: bool = False,\n) -> str:\n    """\n    Säkert alternativ till StructureEngine.generate_tree_string:\n      • max_depth    → ingen RecursionError vid extremt djupa träd\n      • resolve()-deduplicering → ingen oändlig loop vid cirkulära symlänkar\n      • max_entries  → ingen minnesexplosion vid t.ex. node_modules-jättar\n      • PermissionError per mapp → \'<Åtkomst nekad>\' istället för krasch\n      • include_dotfiles → .gitignore/.env kan exporteras (MB12)\n\n    Returnerar alltid en sträng; kastar aldrig.\n    """\n    root_path = Path(root_path)\n    if not root_path.exists():\n        return "Mappen finns inte."\n\n    lines: List[str] = [f"{root_path.name}/"]\n    state = {\'entries\': 0, \'hit_depth\': False, \'hit_entries\': False}\n    seen: set = set()\n    try:\n        seen.add(str(root_path.resolve()))\n    except OSError:\n        seen.add(str(root_path))\n\n    def walk(directory: Path, prefix: str, depth: int) -> None:\n        if depth >= max_depth:\n            state[\'hit_depth\'] = True\n            return\n        if state[\'hit_entries\']:\n            return\n        try:\n            contents = list(directory.iterdir())\n        except (PermissionError, OSError):\n            lines.append(f"{prefix}└── <Åtkomst nekad>")\n            return\n\n        filtered = []\n        for x in contents:\n            if x.name in TREE_IGNORED_DIRS:\n                continue\n            if x.name.startswith(\'.\') and not include_dotfiles:\n                continue\n            filtered.append(x)\n        filtered.sort(key=lambda p: (not p.is_dir(), p.name.lower()))\n\n        for i, path in enumerate(filtered):\n            if state[\'entries\'] >= max_entries:\n                state[\'hit_entries\'] = True\n                return\n            state[\'entries\'] += 1\n\n            is_last = i == len(filtered) - 1\n            connector = "└── " if is_last else "├── "\n            is_dir = path.is_dir()\n            lines.append(f"{prefix}{connector}{path.name}{\'/\' if is_dir else \'\'}")\n\n            if is_dir:\n                try:\n                    key = str(path.resolve())\n                except OSError:\n                    key = str(path)\n                if key in seen:\n                    lines.append(f"{prefix}{\'    \' if is_last else \'│   \'}└── <symlink-loop, hoppad över>")\n                    continue\n                seen.add(key)\n                walk(path, prefix + ("    " if is_last else "│   "), depth + 1)\n\n    walk(root_path, "", 0)\n\n    if state[\'hit_depth\']:\n        lines.append(f"... (avbröts: max djup {max_depth} nått)")\n    if state[\'hit_entries\']:\n        lines.append(f"... (avbröts: max {max_entries} poster nådda)")\n    return "\\n".join(lines)\n\n\nclass NameValidator:\n    @staticmethod\n    def sanitize(name: str) -> str:\n        """\n        Rensar ett mappnamn enligt Windows-regler.\n\n        M18 — delegerar till sanitize_name(), som utöver v4.1:s regler även\n        blockerar reserverade systemnamn MED filändelse (CON.txt, NUL.md,\n        LPT1.log) via RESERVED_STEM_RE. v4.1 jämförde bara cleaned.upper()\n        mot INVALID_NAMES och släppte alltså igenom "CON.txt", vilket kan\n        göra mappen omöjlig att skapa eller ta bort på Windows.\n\n        Kontraktet är oförändrat: returnerar en rensad sträng eller kastar\n        ValueError. Metoden behålls som publik API-yta — inget tas bort.\n        """\n        return sanitize_name(name)\n\n    @staticmethod\n    def is_safe_path(base: Path, target: Path) -> bool:\n        try:\n            target.resolve().relative_to(base.resolve())\n            return True\n        except ValueError:\n            return False\n\n\n@dataclass\nclass AppSettings:\n    save_root: str = field(default_factory=lambda: str(Path.home() / "Projects"))\n    open_after_creation: bool = True\n    theme: str = "Dark"\n    text_size: str = "100%"\n    high_contrast: bool = False\n    default_template: str = "Skaderapport"\n    last_template: str = ""\n    plate_mode: bool = True\n    start_minimized: bool = True    # starta i systray utan att visa fönstret\n    visible_tabs: Dict[str, bool] = field(default_factory=lambda: {\n        t: True for t in TAB_ICONS\n    })\n\n    def to_dict(self) -> dict:\n        return asdict(self)\n\n    @classmethod\n    def from_dict(cls, data: dict) -> "AppSettings":\n        # M3/C2 — validera mot schema INNAN något används. Fel typ, okänt\n        # enum-värde eller saknad nyckel rättas till default istället för att\n        # följa med in i appen och krascha längre ner i GUI:t. validate_settings\n        # är idempotent, så att _load_settings redan validerat spelar ingen roll.\n        data, repaired, log = validate_settings(data)\n        if repaired:\n            for line in log:\n                logger.warning("Inställning reparerad: %s", line)\n        default_tabs = {t: True for t in TAB_ICONS}\n        saved_tabs = data.get("visible_tabs", {})\n        default_tabs.update(saved_tabs)\n        return cls(\n            save_root=data.get("save_root", str(Path.home() / "Projects")),\n            open_after_creation=data.get("open_after_creation", True),\n            theme=data.get("theme", "Dark"),\n            text_size=data.get("text_size", "100%"),\n            high_contrast=data.get("high_contrast", False),\n            default_template=data.get("default_template", "Skaderapport"),\n            last_template=data.get("last_template", ""),\n            plate_mode=data.get("plate_mode", True),\n            start_minimized=data.get("start_minimized", True),\n            visible_tabs=default_tabs,\n        )\n\n\nclass TemplateManager:\n    def __init__(self, directory=None) -> None:\n        self.directory = Path(directory) if directory is not None else TEMPLATES_DIR\n        self.directory.mkdir(parents=True, exist_ok=True)\n        self._builtin = self._create_builtins()\n\n    @staticmethod\n    def _create_builtins() -> Dict[str, str]:\n        return {\n            "Python Projekt": (\n                "projektnamn/\\n    src/\\n        __init__.py\\n        main.py\\n"\n                "    tests/\\n        test_main.py\\n    docs/\\n"\n                "    requirements.txt\\n    README.md\\n    .gitignore\\n"\n            ),\n            "Webb Projekt": (\n                "projektnamn/\\n    public/\\n        index.html\\n        style.css\\n"\n                "    src/\\n        app.js\\n    assets/\\n        images/\\n"\n                "    README.md\\n    package.json\\n"\n            ),\n            "Skaderapport": (\n                "ärendenummer/\\n    Bilder/\\n    Skadeanmälan/\\n"\n                "    Diagnos/\\n    Instruktioner/\\n    Kvalitetsrapport/\\n"\n            ),\n        }\n\n    def list_templates(self) -> Dict[str, str]:\n        templates = dict(self._builtin)\n        for f in self.directory.glob("*.json"):\n            # M2/C41.3 — read_json_safe() återställer från .bak/.bak2 om filen\n            # är trasig, istället för att bara hoppa över mallen.\n            data = read_json_safe(f, None)\n            if not isinstance(data, dict):\n                logger.warning("Kunde inte läsa mall %s: ogiltig eller saknad JSON",\n                               f.name)\n                continue\n            try:\n                if isinstance(data["name"], str) and isinstance(data["structure"], str):\n                    templates[data["name"]] = data["structure"]\n            except KeyError as e:\n                logger.warning("Kunde inte läsa mall %s: %s", f.name, e)\n        return templates\n\n    def save_template(self, name: str, structure: str) -> None:\n        if name in self._builtin:\n            raise ValueError("Inbyggda mallar kan inte skrivas över. Välj ett eget namn.")\n        if not StructureEngine.parse_structure_text(structure)[1]:\n            raise ValueError("Mallen måste innehålla en struktur.")\n        safe = NameValidator.sanitize(name)\n        # M1/F1 — atomisk skrivning med backup. Obs: filen får nu indent=2\n        # (atomic_write_json:s standard) istället för en enda lång rad;\n        # innehållet och inläsningsvägen är oförändrade.\n        if not atomic_write_json(\n            self.directory / f"{safe}.json",\n            {"name": name, "structure": structure},\n        ):\n            raise OSError(f"Kunde inte spara mall {name!r}")\n\n    def delete_template(self, name: str) -> bool:\n        if name in self._builtin:\n            return False\n        safe = NameValidator.sanitize(name)\n        p = self.directory / f"{safe}.json"\n        if p.exists():\n            p.unlink()\n            return True\n        return False\n\n\nclass StructureEngine:\n    IGNORED_DIRS: Final[frozenset] = frozenset({\n        \'.git\', \'__pycache__\', \'.idea\', \'.vscode\',\n        \'node_modules\', \'venv\', \'.env\', \'.tox\',\n    })\n\n    @staticmethod\n    def is_file(name: str) -> bool:\n        clean = name.rstrip(\'/\\\\\')\n        if name.endswith((\'/\', \'\\\\\')):\n            return False\n        if clean.lower() in KNOWN_FILES:\n            return True\n        return \'.\' in clean\n\n    @staticmethod\n    def parse_structure_text(text: str) -> Tuple[Optional[str], List[dict]]:\n        lines = text.splitlines()\n        preprocessed: List[Tuple[int, str, Optional[str]]] = []\n        indent_lengths: Set[int] = set()\n\n        for line in lines:\n            if not line.strip():\n                continue\n            comment = None\n            if \'<-\' in line:\n                line, comment = line.split(\'<-\', 1)\n            elif \'←\' in line:\n                line, comment = line.split(\'←\', 1)\n            line = line.rstrip()\n            match = re.match(r\'^([ │├──└──\\t]*)\', line)\n            prefix = match.group(1) if match else ""\n            name = line[len(prefix):].strip()\n            if not name:\n                continue\n            if len(prefix) > 0:\n                indent_lengths.add(len(prefix))\n            preprocessed.append(\n                (len(prefix), name, comment.strip() if comment else None)\n            )\n\n        unit = min(indent_lengths) if indent_lengths else 1\n        items: List[dict] = []\n        stack: List[str] = []\n\n        for ilen, name, cmt in preprocessed:\n            depth = ilen // unit if unit else 0\n            while len(stack) > depth:\n                stack.pop()\n            clean = name.rstrip(\'/\\\\\')\n            is_dir = not StructureEngine.is_file(name)\n            items.append({\n                \'path\': list(stack) + [clean],\n                \'is_dir\': is_dir,\n                \'comment\': cmt,\n            })\n            if is_dir:\n                stack.append(clean)\n\n        return None, items\n\n    @classmethod\n    def generate_tree_string(cls, root_path: Path) -> str:\n        """\n        M12/MB10 — delegerar till generate_tree_string_safe(), som har\n        djupgräns (MAX_TREE_DEPTH), symlink-loop-detektering via resolve(),\n        posttak (MAX_TREE_ENTRIES) och PermissionError-hantering per mapp.\n\n        v4.1:s version rekade utan något tak: ett tillräckligt djupt träd gav\n        RecursionError och en cirkulär symlänk gav en oändlig loop. Alla\n        anropare får nu det säkra beteendet via denna enda ingång.\n\n        _tree_recursive() behålls oförändrad nedan — ingen metod tas bort.\n        """\n        return generate_tree_string_safe(root_path)\n\n    @classmethod\n    def _tree_recursive(\n        cls, directory: Path, prefix: str, lines: List[str],\n    ) -> None:\n        try:\n            contents = list(directory.iterdir())\n        except PermissionError:\n            lines.append(f"{prefix}└── <Åtkomst nekad>")\n            return\n        filtered = [\n            x for x in contents\n            if x.name not in cls.IGNORED_DIRS and not x.name.startswith(\'.\')\n        ]\n        filtered.sort(key=lambda x: (not x.is_dir(), x.name.lower()))\n        for i, path in enumerate(filtered):\n            is_last = i == len(filtered) - 1\n            connector = "└── " if is_last else "├── "\n            suffix = \'/\' if path.is_dir() else \'\'\n            lines.append(f"{prefix}{connector}{path.name}{suffix}")\n            if path.is_dir():\n                cls._tree_recursive(\n                    path, prefix + ("    " if is_last else "│   "), lines,\n                )\n\n    @staticmethod\n    def count_items(items: List[dict]) -> Tuple[int, int]:\n        return (\n            sum(1 for i in items if i[\'is_dir\']),\n            sum(1 for i in items if not i[\'is_dir\']),\n        )\n\n\ndef validate_project_year(value):\n    """År kan väljas eller skrivas; tomt/streck betyder inget år."""\n    year = str(value).strip()\n    if year in ("", "—"):\n        return "—"\n    if not re.fullmatch(r"[1-9][0-9]{3}", year):\n        raise ValueError("Ange ett fyrsiffrigt år, till exempel 2020, eller lämna fältet tomt.")\n    return year\n\n\ndef project_year_choices(today=None):\n    """Innevarande år och tre år bakåt, beräknat när väljaren öppnas."""\n    year = (today or datetime.now()).year\n    return [str(year - offset) for offset in range(4)]\n\n\n\nclass ExistingProject(FileExistsError):\n    def __init__(self, path):\n        self.path = Path(path)\n        super().__init__(f"Projektet finns redan: {self.path}")\n\n\ndef create_project_tree(save_root, root_name, items):\n    """Single implementation for both GUIs. Never merge into an existing project.\n\n    Validate every relative component before writing. On I/O failure a partial\n    project is left for inspection; never recursively delete potentially useful data.\n    """\n    root_name = NameValidator.sanitize(root_name)\n    base = Path(save_root) / root_name\n    checked = []\n    for item in items:\n        parts = item.get(\'path\')\n        if not isinstance(parts, (list, tuple)) or not parts:\n            raise ValueError(\'Tom sökväg i strukturen\')\n        for part in parts:\n            if not isinstance(part, str) or part in {\'.\', \'..\'} or sanitize_name(part) != part:\n                raise ValueError(f\'Otillåten sökväg i strukturen: {parts!r}\')\n        if not NameValidator.is_safe_path(base, base.joinpath(*parts)):\n            raise ValueError(\'Strukturen lämnar projektmappen\')\n        checked.append((list(parts), bool(item[\'is_dir\']), item.get(\'comment\')))\n    if base.parent.exists():\n        for path in base.parent.iterdir():\n            if path.name.casefold() == base.name.casefold():\n                raise ExistingProject(path)\n    base.mkdir(parents=True, exist_ok=False)\n    for parts, is_dir, comment in checked:\n        path = base.joinpath(*parts)\n        if not NameValidator.is_safe_path(base, path):\n            raise ValueError(\'Sökvägen har ändrats under skapandet\')\n        if is_dir:\n            path.mkdir(parents=True, exist_ok=True)\n        else:\n            path.parent.mkdir(parents=True, exist_ok=True)\n            with path.open(\'x\', encoding=\'utf-8\') as stream:\n                stream.write(f\'# {comment or path.name}\')\n    return base\n\n\ndef build_project_name(namn_text: str, lokal: str, year: str = "—", vehicle_type: str = "") -> str:\n    """Sätter ihop slutnamnet för standardprojekt.\n\n    Lokalen läggs efter projektnamnet, och valt år efter lokalen —\n    användarens beslut ("JPM602 SIDORUTA LAXÅ"). Handskrivna lokal-\n    ord i textfältet plockas bort först (case-insensitivt), så\n    dropdownen är enda källan → inga dubbletter möjliga.\n    """\n    year = str(year).strip()\n    ord_lista = [o for o in str(namn_text).split()\n                 if o.upper() not in LOKAL_CHOICES]\n    # Undvik dubbelt valt år utan att radera andra år i fri text.\n    if year and year != "—":\n        ord_lista = [o for o in ord_lista if o != year]\n    vehicle = str(vehicle_type or "").strip().upper()\n    if vehicle:\n        if vehicle not in VEHICLE_CHOICES:\n            raise ValueError("Okänt fordonsslag")\n        ord_lista = [word for word in ord_lista if word.upper() not in VEHICLE_CHOICES]\n        ord_lista.append(vehicle)\n    if lokal and lokal != "—":\n        ord_lista.append(lokal)\n    if year and year != "—":\n        ord_lista.append(year)\n    return " ".join(ord_lista)\n\n',
'instance_lock.py': '"""Shared GUI-independent instance locking. Extracted from the tested Tk app."""\nfrom __future__ import annotations\nimport atexit\nimport ctypes\nimport logging\nimport os\nimport re\nimport shutil\nimport tempfile\nimport time\nfrom datetime import datetime\nfrom pathlib import Path\nfrom dataclasses import dataclass, field, asdict\nfrom typing import Any, Callable, Dict, Final, Iterable, List, Optional, Sequence, Set, Tuple\nfrom settings import *\nfrom historik import atomic_write_json, read_json_safe\nlogger = logging.getLogger(__name__)\n\nDEFAULT_POLL_MS: int = 1000\n\n\ndef _pid_alive(pid: int) -> bool:\n    """Sant om processen med angivet PID lever (stale-detektering)."""\n    if not pid or pid <= 0:\n        return False\n    if IS_WINDOWS:\n        try:\n            import win32api\n            import win32con\n            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000\n            handle = win32api.OpenProcess(\n                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)\n            if not handle:\n                return False\n            try:\n                # ExitCodeProcess == STILL_ACTIVE (259) → lever\n                import win32process\n                code = win32process.GetExitCodeProcess(handle)\n                return code == win32con.STILL_ACTIVE\n            finally:\n                win32api.CloseHandle(handle)\n        except ImportError:\n            # pywin32 saknas/är trasig — KRITISK fallback via ren ctypes.\n            # Utan denna gren svarade funktionen "död" om varje PID på\n            # pywin32-lösa maskiner, vilket fick PID-filslåset att överta\n            # låset vid VARJE ny start → flera appfönster samtidigt.\n            try:\n                k32 = ctypes.windll.kernel32\n                handle = k32.OpenProcess(0x1000, False, int(pid))\n                if not handle:\n                    return False\n                try:\n                    code = ctypes.c_ulong(0)\n                    if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):\n                        return False\n                    return code.value == 259   # STILL_ACTIVE\n                finally:\n                    k32.CloseHandle(handle)\n            except Exception:\n                return False\n        except Exception:\n            return False\n    try:\n        os.kill(pid, 0)\n    except ProcessLookupError:\n        return False\n    except PermissionError:\n        return True          # finns men ägs av annan användare\n    except OSError:\n        return False\n    return True\n\n\ndef default_lock_dir(app_name: str) -> Path:\n    """Plattformsoberoende katalog för lås-/trigger-/pid-filer."""\n    if IS_WINDOWS:\n        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") \\\n            or tempfile.gettempdir()\n    else:\n        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()\n    return Path(base) / app_name\n\n\nclass SingleInstanceLock:\n    """\n    C1: Max en instans. Andra start → fokus på befintligt fönster.\n\n      Windows  : CreateMutexW, "Global\\\\" → "Local\\\\"-fallback,\n                 ERROR_ALREADY_EXISTS = 183\n      macOS/Linux: flock LOCK_EX | LOCK_NB (+ PID-fil med stale-detektering)\n      Ingen fcntl OCH ingen pywin32 → PID-filsfallback (självläkning, C41.2)\n\n    Fokus via triggerfil + poll-loop (~1000 ms) som anropar on_trigger i\n    Tk-huvudtråden via after(). Cleanup vid exit (atexit) och krasch (finally).\n    """\n\n    def __init__(\n        self,\n        app_name: str,\n        lock_dir: Optional[Path] = None,\n        poll_ms: int = DEFAULT_POLL_MS,\n    ) -> None:\n        self.app_name = str(app_name)\n        self.lock_dir = Path(lock_dir) if lock_dir else default_lock_dir(self.app_name)\n        self.poll_ms = max(50, int(poll_ms))\n\n        slug = re.sub(r"[^a-z0-9_]+", "_", self.app_name.lower()).strip("_")\n        self.lock_file = self.lock_dir / f"{slug}.lock"\n        self.pid_file = self.lock_dir / f"{slug}.pid"\n        self.trigger_file = self.lock_dir / f"{slug}_show.trigger"\n\n        self._mutex_handle: Optional[int] = None\n        self._mutex_name: Optional[str] = None\n        self._fd: Optional[int] = None\n        self._is_primary: bool = False\n        self._backend: str = "none"\n        self._last_trigger: Optional[str] = None   # filinnehåll, ej mtime\n        self._trigger_init: bool = False\n        self._poll_job: Optional[str] = None\n        self._atexit_registered: bool = False\n        self.check_trigger()  # Baseline before acquisition; do not lose a startup focus request.\n\n    # ------------------------------------------------------------------\n    # Status\n    # ------------------------------------------------------------------\n    @property\n    def is_primary(self) -> bool:\n        """True om DENNA process är den enda/primära instansen."""\n        return self._is_primary\n\n    @property\n    def backend(self) -> str:\n        """\'win32-mutex-global\', \'win32-mutex-local\', \'flock\', \'pidfile\'."""\n        return self._backend\n\n    def read_owner_pid(self) -> Optional[int]:\n        """PID för instansen som håller låset (diagnostik)."""\n        try:\n            return int(self.pid_file.read_text(encoding="utf-8").strip() or 0) or None\n        except (OSError, ValueError):\n            return None\n\n    # ------------------------------------------------------------------\n    # Förvärv\n    # ------------------------------------------------------------------\n    def acquire(self) -> bool:\n        """\n        Försök ta låset. True = vi är primär instans och ska köra.\n        False = en annan instans kör redan; anropa request_focus() och avsluta.\n        Kastar aldrig.\n        """\n        try:\n            self.lock_dir.mkdir(parents=True, exist_ok=True)\n        except OSError as exc:\n            logger.error("Kan inte skapa låskatalog %s: %s", self.lock_dir, exc)\n            return False         # Utan verifierat lås får ingen ny instans starta.\n\n        if IS_WINDOWS:\n            try:\n                ok = self._acquire_win32()\n                # Låsbeslutet MÅSTE synas i loggen. Utan denna rad kunde\n                # PyHANDLE-buggen leva osynlig: mutexen dog direkt, backend-\n                # strängen såg frisk ut, och dubbelstarter passerade tyst.\n                logger.info("Instanslås: %s (backend=%s pid=%d)",\n                            "TAGET" if ok else "UPPTAGET av annan instans — avslutar",\n                            self._backend, os.getpid())\n                return ok\n            except ImportError:\n                logger.error("Windows-instanslåset är otillgängligt — start stoppad.")\n                self._backend = "unavailable"\n                return False\n            except Exception as exc:\n                logger.error("Win32-instanslåset kunde inte verifieras (%s) — start stoppad.", exc)\n                self._backend = "unavailable"\n                return False\n\n        try:\n            import fcntl  # noqa: F401\n            ok = self._acquire_flock()\n            logger.info("Instanslås: %s (backend=%s pid=%d)",\n                        "TAGET" if ok else "UPPTAGET av annan instans — avslutar",\n                        self._backend, os.getpid())\n            return ok\n        except ImportError:\n            logger.warning("fcntl saknas — faller tillbaka på PID-fil.")\n        except Exception as exc:\n            logger.warning("flock misslyckades (%s) — fallback.", exc)\n\n        ok = self._acquire_pidfile()\n        logger.info("Instanslås: %s (backend=%s pid=%d)",\n                    "TAGET" if ok else "UPPTAGET av annan instans — avslutar",\n                    self._backend, os.getpid())\n        return ok\n\n    def _acquire_win32(self) -> bool:\n        try:\n            import win32api\n            import win32event\n            import winerror\n        except ImportError:\n            # pywin32 saknas på maskinen — ta samma mutex via ren ctypes\n            # (stdlib) istället. Spärren får ALDRIG bero på ett valfritt\n            # paket: PID-fils-fallbacken är inte atomär och kan släppa in\n            # två instanser som startar samtidigt (autostart + manuell\n            # start) → just det scenariot som gav dubbla tray-ikoner.\n            return self._acquire_win32_ctypes()\n\n        last_error = 0\n        for prefix in ("Global\\\\", "Local\\\\"):\n            name = f"{prefix}{self.app_name}_SingleInstance_Mutex"\n            try:\n                handle = win32event.CreateMutex(None, False, name)\n            except Exception as exc:\n                # Global\\ kräver rättigheter på vissa system → prova Local\\\n                logger.warning("CreateMutex(%s) misslyckades: %s", name, exc)\n                continue\n            last_error = win32api.GetLastError()\n            if last_error == winerror.ERROR_ALREADY_EXISTS:\n                try:\n                    win32api.CloseHandle(handle)\n                except Exception:\n                    pass\n                self._backend = "win32-mutex-inuse"\n                self._is_primary = False\n                return False\n            # KRITISKT: spara ALDRIG bara int(handle)! pywin32:s PyHANDLE\n            # stänger det underliggande handtaget automatiskt när objektet\n            # skräpsamlas — med int(handle) dog mutexen mikrosekunder efter\n            # förvärvet och instansspärren existerade aldrig i praktiken\n            # (verifierat i logg: dubbelstarter passerade utan avvisning).\n            # Detach() överför ägandet till oss; release() stänger explicit.\n            self._mutex_handle = handle.Detach()\n            self._mutex_name = name\n            self._backend = "win32-mutex-" + prefix.rstrip(chr(92)).lower()\n            self._is_primary = True\n            self._write_pid()\n            self._register_atexit()\n            return True\n\n        raise RuntimeError(f"CreateMutex fungerade inte (sista fel={last_error})")\n\n    def _acquire_win32_ctypes(self) -> bool:\n        """\n        Samma namngivna mutex som _acquire_win32, men via ren ctypes —\n        körs när pywin32 saknas. Identiska namn = samma spärr även om\n        två processer råkar gå olika vägar (den ena med, den andra utan\n        pywin32). use_last_error=True + set_last_error(0) före anropet,\n        annars är GetLastError opålitlig från ctypes.\n        """\n        ERROR_ALREADY_EXISTS = 183\n        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)\n        kernel32.CreateMutexW.restype = ctypes.c_void_p\n        kernel32.CreateMutexW.argtypes = (\n            ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)\n\n        for prefix in ("Global\\\\", "Local\\\\"):\n            name = f"{prefix}{self.app_name}_SingleInstance_Mutex"\n            ctypes.set_last_error(0)\n            handle = kernel32.CreateMutexW(None, False, name)\n            if not handle:\n                logger.warning("CreateMutexW(%s) misslyckades (fel=%s) — provar nästa.",\n                               name, ctypes.get_last_error())\n                continue\n            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:\n                kernel32.CloseHandle(ctypes.c_void_p(handle))\n                self._backend = "win32-mutex-inuse"\n                self._is_primary = False\n                return False\n            self._mutex_handle = int(handle)  # ctypes-int äger inget — ingen auto-stängning\n            self._mutex_name = name\n            self._backend = ("win32-mutex-global-ctypes" if prefix == "Global\\\\"\n                             else "win32-mutex-local-ctypes")\n            self._is_primary = True\n            self._write_pid()\n            self._register_atexit()\n            return True\n\n        raise RuntimeError("CreateMutexW (ctypes) fungerade inte")\n\n    def _acquire_flock(self) -> bool:\n        import fcntl\n\n        fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o600)\n        try:\n            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n        except OSError:\n            os.close(fd)\n            self._backend = "flock-inuse"\n            self._is_primary = False\n            return False\n\n        self._fd = fd\n        try:\n            os.ftruncate(fd, 0)\n            os.write(fd, str(os.getpid()).encode("ascii"))\n            os.fsync(fd)\n        except OSError as exc:\n            logger.warning("Kunde inte skriva PID i låsfil: %s", exc)\n\n        self._backend = "flock"\n        self._is_primary = True\n        self._write_pid()\n        self._register_atexit()\n        return True\n\n    def _acquire_pidfile(self) -> bool:\n        """Fallback utan fcntl/win32: PID-fil + stale-detektering."""\n        owner = self.read_owner_pid()\n        if owner and owner != os.getpid() and _pid_alive(owner):\n            self._backend = "pidfile-inuse"\n            self._is_primary = False\n            return False\n        if owner and not _pid_alive(owner):\n            logger.info("Stale PID-fil (%s) upptäckt — övertar låset.", owner)\n        self._write_pid()\n        self._backend = "pidfile"\n        self._is_primary = True\n        self._register_atexit()\n        return True\n\n    def _write_pid(self) -> None:\n        try:\n            self.lock_dir.mkdir(parents=True, exist_ok=True)\n            fd, tmp = tempfile.mkstemp(dir=str(self.lock_dir), suffix=".tmp")\n            with os.fdopen(fd, "w", encoding="utf-8") as fh:\n                fh.write(str(os.getpid()))\n                fh.flush()\n                os.fsync(fh.fileno())\n            os.replace(tmp, self.pid_file)\n        except OSError as exc:\n            logger.warning("Kunde inte skriva PID-fil: %s", exc)\n\n    def _register_atexit(self) -> None:\n        if self._atexit_registered:\n            return\n        try:\n            atexit.register(self.release)\n            self._atexit_registered = True\n        except Exception:\n            pass\n\n    # ------------------------------------------------------------------\n    # Fokus mellan instanser (triggerfil + poll)\n    # ------------------------------------------------------------------\n    def request_focus(self) -> bool:\n        """\n        Skrivs av den AVVISADE instansen: begär att den primära instansen\n        visar och fokuserar sitt fönster. Kastar aldrig.\n        """\n        try:\n            self.lock_dir.mkdir(parents=True, exist_ok=True)\n            fd, tmp = tempfile.mkstemp(dir=str(self.lock_dir), suffix=".tmp")\n            with os.fdopen(fd, "w", encoding="utf-8") as fh:\n                fh.write(f"{time.time_ns()}\\n{os.getpid()}\\n")\n                fh.flush()\n                os.fsync(fh.fileno())\n            os.replace(tmp, self.trigger_file)\n            return True\n        except OSError as exc:\n            logger.error("Kunde inte skriva triggerfil: %s", exc)\n            return False\n\n    def check_trigger(self) -> bool:\n        """\n        True om triggerfilen ändrats sedan senaste anropet.\n\n        Jämför FILINNEHÅLLET, inte mtime. Skäl (verifierat): två snabba\n        request_focus()-anrop kan ge IDENTISK st_mtime_ns eftersom\n        filsystemets tidsupplösning är för grov, medan innehållet\n        (time_ns + pid) alltid är unikt. Med mtime tappades den andra\n        förfrågan.\n\n        Första anropet sätter baslinjen och returnerar False. Baslinjen sätts\n        även när filen INTE finns ännu — annars tappas den första\n        fokusförfrågan, eftersom None då betyder både "ingen baslinje" och\n        "filen saknas" (se _trigger_init).\n        """\n        try:\n            state: Optional[str] = self.trigger_file.read_text(encoding="utf-8")\n        except OSError:\n            state = None\n\n        if not self._trigger_init:\n            self._trigger_init = True\n            self._last_trigger = state\n            return False\n\n        if state != self._last_trigger:\n            self._last_trigger = state\n            # En borttagen fil är ingen fokusförfrågan — bara ett nytt läge.\n            return state is not None\n        return False\n\n    def poll_start(self, root: Any, on_trigger: Any) -> bool:\n        """\n        Starta Tk-poll-loop (C1: ~1000 ms). Anropar on_trigger() i\n        huvudtråden när en annan instans begärt fokus.\n\n        root     : något med .after(ms, fn) — din CTk/Tk-instans\n        on_trigger: callback, t.ex. app._restore_from_tray\n        """\n        if not self._is_primary:\n            return False\n\n        pending_focus = self.check_trigger()  # Preserve requests received while GUI initialized.\n        from updater import service_instance_health\n        try:\n            service_instance_health(self.lock_dir, BASE_DIR / "folder.pyw")\n        except Exception:\n            logger.warning("Hälsosignalen kunde inte startas", exc_info=True)\n\n        def _loop() -> None:\n            nonlocal pending_focus\n            if not self._is_primary:\n                return\n            try:\n                service_instance_health(self.lock_dir, BASE_DIR / "folder.pyw")\n                requested = self.check_trigger()\n                if pending_focus or requested:\n                    pending_focus = False\n                    logger.info("Trigger mottagen — fokuserar fönster.")\n                    on_trigger()\n            except Exception:\n                logger.exception("Fel i single-instance poll-loop")\n            finally:\n                try:\n                    root.after(self.poll_ms, _loop)\n                except Exception:\n                    pass                   # fönstret stängs — avsluta loopen\n\n        try:\n            root.after(self.poll_ms, _loop)\n            return True\n        except Exception as exc:\n            logger.error("Kunde inte starta poll-loop: %s", exc)\n            return False\n\n    def poll_stop(self) -> None:\n        self._poll_job = None\n\n    # ------------------------------------------------------------------\n    # Cleanup\n    # ------------------------------------------------------------------\n    def release(self) -> None:\n        """Frigör låset. Idempotent — kan anropas flera gånger säkert."""\n        if self._is_primary:\n            try:\n                from updater import clear_instance_health\n                clear_instance_health(self.lock_dir)\n            except Exception:\n                pass  # Hälsostädning får aldrig hindra att instanslåset släpps.\n        self._is_primary = False\n\n        if self._fd is not None:\n            try:\n                import fcntl\n                fcntl.flock(self._fd, fcntl.LOCK_UN)\n            except Exception:\n                pass\n            try:\n                os.close(self._fd)\n            except OSError:\n                pass\n            self._fd = None\n\n        if self._mutex_handle is not None:\n            closed = False\n            try:\n                import win32api\n                win32api.CloseHandle(self._mutex_handle)\n                closed = True\n            except Exception:\n                pass\n            if not closed and IS_WINDOWS:\n                # Handtaget kan ha skapats via ctypes-vägen (utan pywin32) —\n                # stäng det då via ctypes så mutexen verkligen frigörs.\n                try:\n                    ctypes.windll.kernel32.CloseHandle(\n                        ctypes.c_void_p(self._mutex_handle))\n                except Exception:\n                    pass\n            self._mutex_handle = None\n            self._mutex_name = None\n\n        try:\n            logger.info("Instanslås frigivet (%s, pid=%d)",\n                        self._backend, os.getpid())\n        except Exception:\n            pass\n\n        for path in (self.pid_file, self.trigger_file):\n            try:\n                path.unlink()\n            except OSError:\n                pass\n\n        try:\n            if self.lock_file.exists() and not IS_WINDOWS:\n                self.lock_file.unlink()\n        except OSError:\n            pass\n\n',
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
        $Code = 'import tkinter,customtkinter; from PIL import Image; import pystray; r=customtkinter.CTk(); r.withdraw(); r.update_idletasks(); r.destroy()'
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
