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


def supervise_update(base, interpreter, recover=False, timeout=90, offer=None):
    # Serialize workers before inspecting a journal or offering recovery.
    handle = None
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
    try:
        return _supervise_update(base, interpreter, recover, timeout, offer)
    finally:
        if handle:
            api.CloseHandle(handle)


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
            and not path.is_absolute() and (name in FILES or
            len(path.parts) == 2 and path.parts[0] == 'Icon' and path.suffix.lower() in {'.png', '.ico'}))


def _invalidate_app_bytecode(base):
    """Discard only our generated bytecode, never package caches or user data."""
    cache = Path(base) / '__pycache__'
    if cache.is_symlink():
        raise ValueError('Appens bytekodscache är en symbolisk länk')
    for name in FILES:
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
        if target.is_symlink() or saved.is_symlink() or target.parent.is_symlink() or saved.parent.is_symlink():
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
    sources += list((pending / "Icon").glob("*.png")) + list((pending / "Icon").glob("*.ico"))
    backup = base / "data/update-backup"
    if backup.exists():
        shutil.rmtree(backup)
    # Finish the backup and durable journal BEFORE replacing a single app file.
    entries = {}
    for source in sources:
        relative = source.relative_to(pending)
        target, saved = base / relative, backup / relative
        if target.is_symlink() or saved.is_symlink() or target.parent.is_symlink() or saved.parent.is_symlink():
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
            } else if (System.IO.File.Exists(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(SCRIPT), "data", "update-transaction.json")) &&
                       System.IO.File.Exists(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(SCRIPT), "data", "update-supervisor.py"))) {
                info.FileName = INTERPRETER;
                info.Arguments = Quote(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(SCRIPT), "data", "update-supervisor.py"))
                    + " --recover " + Quote(System.IO.Path.GetDirectoryName(SCRIPT)) + " " + Quote(INTERPRETER);
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
        if target.is_file() and target.read_bytes().replace(b'\r\n', b'\n') == payload.replace(b'\r\n', b'\n'):
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
        $Process.WaitForExit()
        return [pscustomobject]@{ Code = $Process.ExitCode; Out = $Out.Result; Err = $Err.Result }
    } finally { $Process.Dispose() }
}

function Resolve-ExistingPython([string]$Candidate) {
    if (-not $Candidate -or $Candidate -match '\\Microsoft\\WindowsApps\\') { return $null }
    if ([IO.Path]::GetFileName($Candidate) -match '^pythonw') { $Candidate = Join-Path (Split-Path $Candidate) 'python.exe' }
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $null }
    try {
        # Local interpreter identity only; no version/dependency/update check.
        $Result = Invoke-Hidden $Candidate @('-c','import sys; print(getattr(sys,"_base_executable",sys.executable))')
        if ($Result.Code -ne 0) { return $null }
        $Console = $Result.Out.Trim()
        $Windowless = Join-Path (Split-Path $Console) 'pythonw.exe'
        if (Test-Path -LiteralPath $Windowless -PathType Leaf) { return $Windowless }
    } catch { }
    return $null
}
try {
    Remove-LegacyMaintenanceTask
    # Backward-compatible exit for a previously scheduled maintenance invocation.
    if ($MaintenanceOnly) { exit 0 }
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
    if ($PreferredPython) { $Candidates.Add($PreferredPython) }
    $Windowless = $null
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        $Windowless = Resolve-ExistingPython $Candidate
        if ($Windowless) { break }
    }
    if (-not $Windowless) { throw 'No existing system Python with pythonw.exe could be found. No Python was installed or updated.' }
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
