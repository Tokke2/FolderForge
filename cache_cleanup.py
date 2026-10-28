"""Försiktig rensning av enbart FolderForges egna återbildningsbara filer."""
from __future__ import annotations

from datetime import datetime
import logging
import math
from pathlib import Path
import re
import threading
import time

from historik import atomic_write_json, read_json_safe

DAY = 24 * 60 * 60
_lock = threading.Lock()
logger = logging.getLogger(__name__)


def state_path(base):
    return base / 'data/cache-cleanup.json'


def read_status(base):
    state = read_json_safe(state_path(base), {})
    return state if isinstance(state, dict) else {}


def valid_time(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def protected_paths(base):
    """Även projekt som användaren placerat i cacheområdet ska skyddas."""
    paths = []
    settings = read_json_safe(base / 'data/settings.json', {})
    if isinstance(settings, dict) and isinstance(settings.get('save_root'), str) and settings['save_root']:
        paths.append(Path(settings['save_root']).resolve())
    history = read_json_safe(base / 'data/history.json', [])
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and isinstance(item.get('path'), str) and item['path']:
                paths.append(Path(item['path']).resolve())
    return paths


def candidates(base, now):
    """Ingen generell *.tmp-sökning. Följ aldrig symlänkar/junctions."""
    base = base.resolve()
    data = base / 'data'
    if unsafe(data):
        return
    protected = protected_paths(base)
    for folder, age in [('cache', DAY), ('tmp', DAY), ('logs', 14 * DAY)]:
        root = data / folder
        if unsafe(root) or not root.is_dir():
            continue
        stack = [root]
        while stack:
            directory = stack.pop()
            try:
                children = list(directory.iterdir())
            except OSError:
                continue
            for path in children:
                try:
                    if unsafe(path) or not path.resolve().is_relative_to(root.resolve()):
                        continue
                    if any(path.resolve().is_relative_to(saved) for saved in protected):
                        continue
                    if path.is_dir():
                        if folder != 'logs':
                            stack.append(path)
                    elif path.is_file():
                        if folder == 'logs' and not re.fullmatch(r'folderforge\.log\.[1-3]', path.name):
                            continue
                        stat = path.stat()
                        if now - stat.st_mtime >= age:
                            yield path, stat.st_size
                except OSError:
                    continue


def unsafe(path):
    # is_junction finns från Python 3.12. På äldre Windows används filattribut.
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def clean_cache(base, *, manual=False, now=None):
    """Samma åldersfilter manuellt och automatiskt. Radera aldrig färska filer."""
    base = base.resolve()
    now = time.time() if now is None else now
    with _lock:
        # Skriv inte till en omdirigerad datamapp.
        if unsafe(base / 'data'):
            raise OSError('Datamappen är en länk; rensningen avbröts')
        previous = read_status(base)
        last = previous.get('last_run')
        if not manual and valid_time(last) and 0 <= now - last < DAY:
            return previous
        removed = freed = failed = 0
        for path, size in candidates(base, now):
            try:
                if unsafe(path) or any(unsafe(p) for p in path.parents if p != base and base in p.parents):
                    continue
                path.unlink()
                removed += 1
                freed += size
            except OSError:
                failed += 1
                logger.warning('Kunde inte rensa cachefil %s', path, exc_info=True)
        result = {'last_run': now, 'removed': removed, 'bytes': freed, 'failed': failed}
        if not atomic_write_json(state_path(base), result):
            raise OSError('Kunde inte spara tid för cacherensning')
        logger.info('Smart cacherensning: %s filer, %s byte, %s fel', removed, freed, failed)
        return result


def status_text(base):
    state = read_status(base)
    stamp = state.get('last_run')
    if not valid_time(stamp):
        return 'Ingen rensning har körts ännu.'
    try:
        date = datetime.fromtimestamp(stamp).astimezone().strftime('%Y-%m-%d %H:%M %Z')
    except (ValueError, OverflowError, OSError):
        return 'Tid för senaste rensning är okänd.'
    return (f"Senast: {date}\nRensat: {state.get('removed', 0)} filer, "
            f"{state.get('bytes', 0)} byte\nÖverhoppade filfel: {state.get('failed', 0)}")


def start_cleanup(base):
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                clean_cache(base)
            except Exception:
                logger.warning('Cacherensning misslyckades; appen fortsätter', exc_info=True)
            stop.wait(60 * 60)

    threading.Thread(target=worker, name='smart-cache-cleanup', daemon=True).start()
    return stop
