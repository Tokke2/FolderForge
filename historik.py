# historik.py
# -*- coding: utf-8 -*-
"""
historik.py — projekthistorik + appens säkra JSON-persistens.

Bröts ut ur folder.pyw (modularisering). Innehåller:
  * ProjectHistory     — historiklistan: ladda/spara/lägg till/ta bort/
                         rensa, med MAX_HISTORY-capping
  * atomic_write_json  — atomisk JSON-skrivning (tmp→fsync→replace + .bak)
  * read_json_safe     — självläkande läsning (fil→.bak→.bak2→default)
  * _fsync_dir         — fsync av föräldramappen (mappostens beständighet)

JSON-hjälparna är generella och delas av ALL fil-persistens i appen
(settings.json, hotkey_config.json, autostart-export ...) — de bor här
eftersom historiken var den första persistens som bröts ut;
folder.pyw importerar dem härifrån.

Beroenderiktning: settings.py → logg.py → historik.py → folder.pyw.
Denna modul importerar aldrig folder.pyw (ingen cirkel).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from settings import HISTORY_FILE, IS_WINDOWS, MAX_HISTORY

logger = logging.getLogger(__name__)


def _fsync_dir(path: Path) -> None:
    """fsync på föräldramappen så att även filposten (rename) blir beständig."""
    if not IS_WINDOWS:
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    backup: bool = True,
    indent: int = 2,
) -> bool:
    """
    Skriver JSON atomiskt enligt specens låsta regel:
      tempfile.mkstemp → os.fdopen → fsync → os.replace
    ALDRIG Path.replace. ALDRIG closefd=False.

    Tar även en backup av den gamla filen (krav F1) innan ny data skrivs.
    Returnerar True om skrivningen lyckades, False annars (ingen exception
    läcker ut till GUI-tråden).
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if backup and path.exists():
            for bak in (path.with_suffix(path.suffix + ".bak"),
                        path.with_suffix(path.suffix + ".bak2")):
                try:
                    if bak.exists() and bak.stat().st_size == 0:
                        bak.unlink()          # rensa bara trasiga 0-byte-backuper
                except OSError:
                    pass
            try:
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            except OSError:
                pass  # backup är "bäst-effort" — skrivningen får aldrig blockeras

        payload = json.dumps(data, ensure_ascii=False, indent=indent)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        _fsync_dir(path)
        return True
    except OSError:
        return False


def read_json_safe(path: Path, default: Any = None) -> Any:
    """
    Självläkande JSON-läsning (C41.3):
      1. vanlig läsning (BOM-tolerant via utf-8-sig)
      2. trasig/oläsbar → försök .bak
      3. .bak trasig    → försök .bak2
      4. allt trasigt   → default (aldrig krasch, aldrig tyst dataförlust utan logg)
    """
    path = Path(path)
    candidates: List[Path] = [path]
    if path.exists():
        candidates += [path.with_suffix(path.suffix + ".bak"),
                       path.with_suffix(path.suffix + ".bak2")]
    for cand in candidates:
        if not cand.exists():
            continue
        try:
            with cand.open("r", encoding="utf-8-sig") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
    return default


# ============================================================
# Projekthistorik
# ============================================================
class ProjectHistory:
    def __init__(self) -> None:
        self._items: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        # M2/C41.3 — read_json_safe() provar fil → .bak → .bak2 → default och
        # är BOM-tolerant (utf-8-sig). v4.1 kastade bort HELA historiken vid en
        # enda trasig fil, utan backup och utan att försöka återställa.
        data = read_json_safe(HISTORY_FILE, [])
        if isinstance(data, list):
            return data
        logger.warning("history.json innehöll inte en lista — tom historik används")
        return []

    def _save(self) -> None:
        # M1/F1 — atomisk skrivning: tempfile.mkstemp → os.fdopen → fsync →
        # os.replace, med .bak-backup före skrivning. write_text() kunde vid
        # krasch eller full disk lämna en trunkerad fil som nästa start inte
        # kunde läsa. Returnerar bool så att felet loggas istället för att kastas.
        if not atomic_write_json(HISTORY_FILE, self._items):
            logger.warning("Kunde inte spara historik (atomisk skrivning misslyckades)")

    def add(self, path: Path) -> None:
        path_str = str(path)
        self._items = [i for i in self._items if i.get("path") != path_str]
        self._items.insert(0, {
            "path": path_str,
            "name": path.name,
            "created": datetime.now().isoformat(),
        })
        self._items = self._items[:MAX_HISTORY]
        self._save()

    def get_all(self) -> List[Dict]:
        valid = [i for i in self._items if Path(i.get("path", "")).exists()]
        if len(valid) != len(self._items):
            self._items = valid
            self._save()
        return valid

    def remove(self, path_str: str) -> None:
        self._items = [i for i in self._items if i.get("path") != path_str]
        self._save()

    def clear(self) -> None:
        self._items = []
        self._save()
