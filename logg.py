# logg.py
# -*- coding: utf-8 -*-
"""
logg.py — hela appens loggning, samlad på ett ställe.

Bröts ut ur folder.pyw (modularisering). Innehåller:
  * LOG_FILE            — fullständig logg
  * ERROR_LOG_FILE      — samlade varningar/fel från alla appmoduler
  * init_logging()      — roterande fil + konsoll, idempotent
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
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from settings import APP_NAME, APP_VERSION, LOG_DIR

# Loggfilens sökväg — härledd ur LOG_DIR i settings.py (sektion 2).
LOG_FILE: Final[Path] = LOG_DIR / "folderforge.log"
ERROR_LOG_FILE: Final[Path] = LOG_DIR / "folderforge-errors.log"

_LOGG_STORLEK: Final[int] = 400 * 1024   # bytes per loggfil innan rotation
_FEL_STORLEK: Final[int] = 512 * 1024
_FEL_ARKIV: Final[int] = 5

_LOGG_ARKIV: Final[int] = 3              # antal arkivfiler som sparas

_initierad: bool = False
_logger = logging.getLogger(__name__)


def init_logging() -> None:
    """
    Koppla in roterande loggfil + konsoll (om någon finns). Idempotent —
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
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fil = RotatingFileHandler(LOG_FILE, maxBytes=_LOGG_STORLEK,
                                  backupCount=_LOGG_ARKIV, encoding="utf-8")
        fil.setLevel(logging.DEBUG)     # filen får ALLT — det är poängen
        fil.setFormatter(fmt)
        rot.addHandler(fil)
    except Exception as exc:            # låst fil, skrivskyddad mapp, ...
        if sys.stderr is not None:
            print(f"VARNING: loggfil kunde inte öppnas: {exc}", file=sys.stderr)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        import_history = not ERROR_LOG_FILE.exists() and not ERROR_LOG_FILE.with_name(ERROR_LOG_FILE.name + ".1").exists()
        errors = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=_FEL_STORLEK,
                                    backupCount=_FEL_ARKIV, encoding="utf-8")
        errors.setLevel(logging.WARNING)
        errors.setFormatter(fmt)
        rot.addHandler(errors)
        if import_history:
            _import_existing_errors(errors)
    except Exception:
        # Den andra filhandlaren kan fortfarande fånga detta fel.
        _logger.error("Kunde inte öppna den samlade felloggen", exc_info=True)

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
    header = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s")
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
