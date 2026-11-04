# logg.py
# -*- coding: utf-8 -*-
"""
logg.py — hela appens loggning, samlad på ett ställe.

Bröts ut ur folder.pyw (modularisering). Innehåller:
  * LOG_FILE            — fullständig logg
  * ERROR_LOG_FILE      — samlade varningar/fel från alla appmoduler
  * init_logging()      — dagsarkiv + beständig fellogg + konsoll, idempotent
  * kraschloggning      — sys.excepthook + threading.excepthook

Designregler (oförändrade sedan utbrottet):
  * Handlare kopplas på ROT-loggaren — då når de även historik.py och
    framtida moduler via propagation, inte bara huvudfilen.
  * Appens DEBUG-diagnostik sparas. Pillow-brus kräver tillfälligt detaljläge.
    pythonw har ingen konsoll, så filen är den som räknas.
  * Loggningen kastar aldrig — den får aldrig stoppa appen den övervakar.

Beroenderiktning: settings.py → logg.py → historik.py → folder.pyw.
Denna modul importerar aldrig folder.pyw (ingen cirkel).
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
from contextlib import contextmanager
from datetime import date, datetime
import hashlib
import tempfile
import uuid
from pathlib import Path
from typing import Final

from settings import APP_NAME, APP_VERSION, LOG_DIR

# Loggfilens sökväg — härledd ur LOG_DIR i settings.py (sektion 2).
LOG_FILE: Final[Path] = LOG_DIR / "folderforge.log"
ERROR_LOG_FILE: Final[Path] = LOG_DIR / "folderforge-errors.log"
LEGACY_LOG_DIR: Final[Path] = LOG_DIR.parent / "data" / "logs"

# Vanliga loggar arkiveras per lokalt kalenderdatum. Olösta fel roteras aldrig bort.
_file_lock = threading.RLock()


def local_today():
    return datetime.now().date()


@contextmanager
def _locked_logs(folder):
    """Samma kortlivade fillås i alla processer, även före appens instanslås."""
    with _file_lock:
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / ".folderforge-log.lock").open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _atomic_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".log-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _atomic_text(path, text):
    _atomic_bytes(path, text.encode("utf-8"))


def migrate_legacy_logs():
    """Flytta tidigare data/logs utan att skriva över nyare loggar eller arkiv."""
    legacy = LEGACY_LOG_DIR
    if not legacy.is_dir() or legacy.resolve() == LOG_DIR.resolve():
        return
    if legacy.is_symlink() or getattr(legacy.lstat(), "st_file_attributes", 0) & 0x400:
        raise OSError("Den gamla loggmappen är en länk; flytta loggarna manuellt")
    with _locked_logs(legacy), _locked_logs(LOG_DIR):
        for source in sorted(legacy.rglob("*")):
            if not source.is_file() or source.is_symlink() or source.name == ".folderforge-log.lock":
                continue
            relative = source.relative_to(legacy)
            target = LOG_DIR / relative
            content = source.read_bytes()
            is_log = len(relative.parts) == 1 and re.fullmatch(r"folderforge(?:-errors)?\.log(?:\.\d+)?", source.name)
            digest = hashlib.sha256(content).hexdigest()
            marker = ("\n[Flyttad äldre logg " + source.name + " sha256=" + digest + "]\n").encode("utf-8")
            if target.exists():
                existing = target.read_bytes()
                if existing == content:
                    source.unlink()
                    continue
                if is_log:
                    # Om processen avbröts efter kopiering men före borttagning: kopiera inte igen.
                    if marker not in existing:
                        _atomic_bytes(target, content + marker + existing)
                else:
                    target = target.with_name(target.name + ".migrated-" + digest)
                    _atomic_bytes(target, content)
            else:
                _atomic_bytes(target, content + marker if is_log else content)
            # Originalet tas bort först när hela målfilen säkrats atomiskt.
            source.unlink()


def _archive_general(source, today):
    """Dela även blandade äldre loggar efter postdatum; behåll traceback intakt."""
    if not source.is_file():
        return
    text = source.read_text(encoding="utf-8", errors="replace")
    current = datetime.fromtimestamp(source.stat().st_mtime).date()
    buckets = {}
    retained = []
    archived = False
    for line in text.splitlines(keepends=True):
        if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[,.]\d+)?\s", line):
            try:
                current = date.fromisoformat(line[:10])
            except ValueError:
                pass
        if current < today:
            buckets.setdefault(current, []).append(line)
        else:
            retained.append(line)
    for day, lines in buckets.items():
        if day >= today:
            continue
        content = "".join(lines)
        digest = hashlib.sha256((source.name + "\0" + content).encode("utf-8")).hexdigest()
        target = source.parent / "archive" / day.isoformat() / f"folderforge-{digest}.log"
        # Deterministiskt namn gör ett avbrutet arkiveringsförsök säkert att upprepa.
        _atomic_text(target, content)
        archived = True
    if archived:
        _atomic_text(source, "".join(retained))


class DailyArchiveHandler(logging.Handler):
    def __init__(self, path):
        super().__init__(logging.DEBUG)
        self.path = Path(path)
        self.day = None
        self.archive()

    def archive(self):
        today = local_today()
        with _locked_logs(self.path.parent):
            for source in [self.path, *sorted(self.path.parent.glob(self.path.name + ".[0-9]*"))]:
                _archive_general(source, today)
            self.day = today

    def emit(self, record):
        try:
            if self.day != local_today():
                self.archive()
            with _locked_logs(self.path.parent):
                # En annan process kan också arkivera: inga filhandtag lämnas öppna.
                day = datetime.fromtimestamp(record.created).date()
                target = self.path
                if day < local_today():
                    target = self.path.parent / "archive" / day.isoformat() / "folderforge-late.log"
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8") as stream:
                    stream.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


class PersistentErrorHandler(logging.Handler):
    """Olösta varningar/fel: ingen storleks-, datum- eller antalsrensning."""
    def __init__(self, path):
        super().__init__(logging.WARNING)
        self.path = Path(path)
        with _locked_logs(self.path.parent):
            self.path.touch(exist_ok=True)

    def emit(self, record):
        try:
            with _locked_logs(self.path.parent):
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


def _merge_legacy_errors():
    """Även gamla storleksroterade fel betraktas som olösta."""
    with _locked_logs(ERROR_LOG_FILE.parent):
        sources = sorted((p for p in ERROR_LOG_FILE.parent.glob(ERROR_LOG_FILE.name + ".*")
                          if p.name.rsplit(".", 1)[-1].isdigit() and p.is_file()),
                         key=lambda p: int(p.name.rsplit(".", 1)[-1]), reverse=True)
        if not sources:
            return
        content = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sources)
        if ERROR_LOG_FILE.exists():
            content += ERROR_LOG_FILE.read_text(encoding="utf-8", errors="replace")
        _atomic_text(ERROR_LOG_FILE, content)
        for source in sources:
            target = ERROR_LOG_FILE.parent / "archive" / "legacy-error-copies" / (source.name + "-" + uuid.uuid4().hex)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)


def error_log_snapshot():
    with _locked_logs(ERROR_LOG_FILE.parent):
        content = ERROR_LOG_FILE.read_bytes() if ERROR_LOG_FILE.is_file() else b""
        return hashlib.sha256(content).hexdigest()


def archive_resolved_errors(expected_digest=None):
    """Anropas ENDAST efter användarens bekräftelse att samtliga listade fel är lösta."""
    with _locked_logs(ERROR_LOG_FILE.parent):
        if not ERROR_LOG_FILE.is_file() or not ERROR_LOG_FILE.stat().st_size:
            return None
        if expected_digest is not None:
            digest = hashlib.sha256(ERROR_LOG_FILE.read_bytes()).hexdigest()
            if digest != expected_digest:
                raise ValueError("Nya fel har tillkommit. Öppna felloggen och granska dem innan du bekräftar igen.")
        # Förhindra återimport även om processen stoppas precis efter flytten.
        (ERROR_LOG_FILE.parent / ".errors-history-imported").touch(exist_ok=True)
        now = datetime.now()
        target = (ERROR_LOG_FILE.parent / "resolved-errors" / now.date().isoformat()
                  / (now.strftime("%H%M%S") + "-" + uuid.uuid4().hex + ".log"))
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(ERROR_LOG_FILE, target)
        ERROR_LOG_FILE.touch()
        return target


def archive_old_logs():
    for handler in logging.getLogger().handlers[:]:
        if isinstance(handler, DailyArchiveHandler) and handler.day != local_today():
            handler.archive()


def start_log_archiver():
    """Arkivera inom en minut efter midnatt, även om ingen ny loggrad skrivs."""
    stop = threading.Event()
    def worker():
        while not stop.wait(60):
            try:
                archive_old_logs()
            except Exception:
                _logger.error("Kunde inte arkivera tidigare dagars loggar", exc_info=True)
    threading.Thread(target=worker, name="daily-log-archive", daemon=True).start()
    return stop


_initierad: bool = False
_logger = logging.getLogger(__name__)


def init_logging() -> None:
    """
    Koppla in dagsarkiverad loggfil, beständig fellogg + konsoll (om någon finns). Idempotent —
    ett andra anrop ändrar inget (och varnar i loggen).

    Handlarna sätts medvetet på ROT-loggaren: modul-loggare (folder,
    historik, logg) propagerar dit, så en enda konfiguration täcker
    hela appen. Kastar aldrig.
    """
    global _initierad
    if _initierad:
        _logger.warning("init_logging() anropad igen — hoppar över "
                        "(handlare fanns redan)")
        return

    migration_error = None
    try:
        migrate_legacy_logs()
    except Exception as exc:
        migration_error = (type(exc), exc, exc.__traceback__)

    rot = logging.getLogger()           # rot — allt propagerar hit
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s:%(lineno)d] [%(threadName)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    # Importera fel INNAN vanliga historiska loggar flyttas till datumarkiv.
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        marker = LOG_DIR / ".errors-history-imported"
        import_history = (not marker.exists() and not ERROR_LOG_FILE.exists()
                          and not any(LOG_DIR.glob(ERROR_LOG_FILE.name + ".[0-9]*")))
        _merge_legacy_errors()
        errors = PersistentErrorHandler(ERROR_LOG_FILE)
        errors.setFormatter(fmt)
        rot.addHandler(errors)
        if import_history:
            _import_existing_errors(errors)
        marker.touch(exist_ok=True)
    except Exception:
        _logger.error("Kunde inte öppna den samlade felloggen", exc_info=True)

    try:
        fil = DailyArchiveHandler(LOG_FILE)
        fil.setFormatter(fmt)
        fil.addFilter(LibraryNoiseFilter())
        rot.addHandler(fil)
    except Exception:
        _logger.error("Kunde inte öppna eller arkivera den vanliga loggen", exc_info=True)

    if sys.stderr is not None:          # pythonw har ingen konsoll
        kons = logging.StreamHandler()
        kons.setFormatter(fmt)
        kons.addFilter(LibraryNoiseFilter())
        rot.addHandler(kons)

    rot.setLevel(logging.DEBUG)
    _initierad = True
    if migration_error:
        _logger.error("Kunde inte flytta äldre loggar till appens logs-mapp; originalen sparas för nytt försök",
                      exc_info=migration_error)
    koppla_kraschloggning()
    _logger.info("──── %s %s startar — pid=%d argv=%s — loggfil: %s ────",
                 APP_NAME, APP_VERSION, os.getpid(), sys.argv, LOG_FILE)


def _import_existing_errors(handler) -> None:
    """Engångsimport från befintliga app-loggar, inklusive flerradiga traceback."""
    header = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[,.]\d+)?\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s")
    sources = [LOG_FILE.with_name(LOG_FILE.name + f".{number}") for number in (3, 2, 1)] + [LOG_FILE]
    for source in sources:
        try:
            with source.open(encoding="utf-8", errors="replace") as stream:
                selected = False
                record = []
                def emit():
                    if record:
                        level = getattr(logging, header.match(record[0]).group(1), logging.WARNING)
                        item = logging.LogRecord("tidigare_logg", level, str(source), 0,
                                                 "Tidigare poster från %s:\n%s", (source.name, "".join(record).rstrip()), None)
                        handler.handle(item)
                for line in stream:
                    match = header.match(line)
                    if match:
                        emit()
                        record = []
                        selected = match.group(1) in {"WARNING", "ERROR", "CRITICAL"}
                    if selected:
                        record.append(line)
                emit()
        except FileNotFoundError:
            continue
        except OSError:
            _logger.warning("Kunde inte importera tidigare fel från %s", source, exc_info=True)


def _log_ofangat(exc_type, exc_value, exc_tb) -> None:
    """Ofångade undantag — annars dör pythonw tyst utan spår i loggen."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    _logger.critical("OFÅNGAT UNDANTAG — appen avslutas oväntat",
                     exc_info=(exc_type, exc_value, exc_tb))


def koppla_kraschloggning() -> None:
    """Fånga alla ofångade undantag — huvudtråd OCH bakgrundstrådar."""
    sys.excepthook = _log_ofangat
    # Undantag i bakgrundstrådar (hotkey-lyssnaren, storleksräkning, ...)
    # hamnar annars heller ingenstans — fånga dem via samma väg.
    threading.excepthook = (lambda a: _log_ofangat(a.exc_type, a.exc_value,
                                                   a.exc_traceback))

# Detaljerad biblioteksloggning är tillfällig och återställs även vid omstart.
_debug_until = 0.0


def enable_detailed_logging(minutes=15):
    import time
    global _debug_until
    _debug_until = time.monotonic() + max(0, min(float(minutes), 60)) * 60


def detailed_logging_remaining():
    import time
    return max(0, int(_debug_until - time.monotonic()))


class LibraryNoiseFilter(logging.Filter):
    def filter(self, record):
        return not ((record.name == 'PIL' or record.name.startswith('PIL.')) and record.levelno < logging.WARNING
                    and not detailed_logging_remaining())


_ERROR_HEADER = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:[,.]\d+)?\s+'
    r'(WARNING|ERROR|CRITICAL)\s+(?:\[([^\]]+)\]\s+\[[^\]]+\]\s+)?(.*)')


def _error_entries(text):
    entries, current = [], None
    for line in text.splitlines(keepends=True):
        match = _ERROR_HEADER.match(line)
        if match:
            # Äldre importomslag är metadata; själva originalposten grupperas nedan.
            if current:
                entries.append(current)
            if (match[3] or '').startswith('tidigare_logg:'):
                current = None
                continue
            module = (match[3] or 'äldre_logg').rsplit(':', 1)[0]
            message = match[4]
            if module == 'äldre_logg' and message.startswith('[launcher] '):
                module, message = 'launcher', message[len('[launcher] '):]
            identity = '\0'.join((module, match[2], message))
            current = dict(id=hashlib.sha256(identity.encode()).hexdigest(),
                           first=match[1], level=match[2], module=module,
                           message=message, text=line)
        elif current:
            current['text'] += line
        elif line.strip() and not line.startswith('[Flyttad äldre logg '):
            # Även oformaterade/native poster måste kunna granskas, aldrig tappas bort.
            identity = hashlib.sha256(line.encode()).hexdigest()
            entries.append(dict(id=identity, first='Okänd tid', level='ERROR',
                                module='övrigt', message=line.strip(), text=line))
    if current:
        entries.append(current)
    for entry in entries:
        if 'Traceback (most recent call last)' in entry['text']:
            last_line = next(line for line in reversed(entry['text'].rstrip().splitlines())
                             if line.strip() and not line.startswith('[Flyttad äldre logg '))
            entry['id'] = hashlib.sha256((entry['id'] + '\0' + last_line).encode()).hexdigest()
    return entries


def get_error_issues():
    with _locked_logs(ERROR_LOG_FILE.parent):
        raw = ERROR_LOG_FILE.read_bytes() if ERROR_LOG_FILE.exists() else b''
        text = raw.decode('utf-8', errors='replace')
        snapshot = hashlib.sha256(raw).hexdigest()
        groups = {}
        for entry in _error_entries(text):
            if entry['id'] not in groups:
                groups[entry['id']] = dict(entry, last=entry['first'], count=0)
            group = groups[entry['id']]
            group['count'] += 1
            group['first'] = min(group['first'], entry['first'])
            if entry['first'] >= group['last']:
                group['text'] = entry['text']
            group['last'] = max(group['last'], entry['first'])
            # Senaste traceback finns i detaljvyn.
        return list(groups.values()), snapshot


def resolve_error_issue(issue_id, expected_digest):
    with _locked_logs(ERROR_LOG_FILE.parent):
        raw = ERROR_LOG_FILE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_digest:
            raise ValueError('Felloggen har ändrats. Uppdatera listan och granska felet igen.')
        entries = _error_entries(raw.decode('utf-8', errors='replace'))
        selected = [entry['text'] for entry in entries if entry['id'] == issue_id]
        if not selected:
            raise ValueError('Felet finns inte längre i den aktiva listan.')
        target = (ERROR_LOG_FILE.parent / 'resolved-errors' / local_today().isoformat()
                  / (uuid.uuid4().hex + '.log'))
        # Arkiv först: ett avbrott kan lämna felet aktivt, men aldrig tappa det.
        (ERROR_LOG_FILE.parent / '.errors-history-imported').touch(exist_ok=True)
        _atomic_text(target, ''.join(selected))
        _atomic_text(ERROR_LOG_FILE, ''.join(entry['text'] for entry in entries if entry['id'] != issue_id))
        return target


def export_diagnostic_package(destination):
    """Endast utvalda loggar/status, inga inställningar, projekt eller miljövariabler."""
    import json
    import platform
    import zipfile
    from settings import BASE_DIR
    from updater import get_update_status
    destination = Path(destination)
    if destination.suffix.lower() != '.zip':
        raise ValueError('Felsökningspaketet måste sparas som .zip, inte över en logg eller appfil.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.diagnostic-', dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as output:
            report = dict(app=APP_NAME, version=APP_VERSION, python=platform.python_version(),
                          system=platform.system(), update=get_update_status(BASE_DIR, APP_VERSION), files=[])
            with _locked_logs(LOG_DIR):
                def safe_log(path):
                    return (path.is_file() and not path.is_symlink()
                            and path.resolve().is_relative_to(LOG_DIR.resolve()))
                archives = sorted((p for p in (LOG_DIR / 'archive').rglob('*.log') if safe_log(p)),
                                  key=lambda p: p.stat().st_mtime, reverse=True)[:3]
                for path in [LOG_FILE, ERROR_LOG_FILE, *archives]:
                    if not safe_log(path):
                        continue
                    size = path.stat().st_size
                    with path.open('rb') as stream:
                        stream.seek(max(0, size - 2 * 1024 * 1024))
                        content = stream.read(2 * 1024 * 1024)
                    name = 'logs/' + path.relative_to(LOG_DIR).as_posix()
                    output.writestr(name, content)
                    report['files'].append(dict(name=name, original_bytes=size, truncated=size > len(content)))
            output.writestr('diagnostic.json', json.dumps(report, ensure_ascii=False, indent=2))
            output.writestr('LAS-MIG.txt', 'Kan innehålla personliga sökvägar och felmeddelanden. Granska innan delning.\n'
                            'Varje logg begränsas till de sista 2 MiB. Se diagnostic.json för begränsningar.\n')
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination
