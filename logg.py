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
  * Filen får DEBUG-nivå (allt), konsollen samma — pythonw har ingen
    konsoll, så filen är den som räknas.
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


def _atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".log-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


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
        rot.addHandler(fil)
    except Exception:
        _logger.error("Kunde inte öppna eller arkivera den vanliga loggen", exc_info=True)

    if sys.stderr is not None:          # pythonw har ingen konsoll
        kons = logging.StreamHandler()
        kons.setFormatter(fmt)
        rot.addHandler(kons)

    rot.setLevel(logging.DEBUG)
    _initierad = True
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
