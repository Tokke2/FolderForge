"""Local, allowlisted diagnostics. No network, environment dump or project contents."""
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import sys
import tempfile
from datetime import datetime, timezone


def startup_report(base, phase='running', error=''):
    from updater import read_state, FILES, OPTIONAL_FILES
    base = Path(base)
    packages = {}
    for name in ('PySide6', 'shiboken6', 'pynput', 'pywin32'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = 'saknas'
    expected = read_state(base).get('installed_hashes', {})
    mismatches = []
    if isinstance(expected, dict):
        for name, digest in expected.items():
            if name not in FILES | OPTIONAL_FILES and not (name.startswith('Icon/')
                    and len(Path(name).parts) == 2 and Path(name).suffix in {'.png', '.ico', '.icns', '.svg'}):
                continue
            path = base / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                mismatches.append(name)
    return dict(time=datetime.now(timezone.utc).isoformat(), phase=phase, error=error[:2000],
                gui='Qt', executable=sys.executable, python=platform.python_version(),
                system=platform.system(), machine=platform.machine(), packages=packages,
                mismatched_files=mismatches, pid=os.getpid())


def save_startup_report(base, phase='running', error=''):
    report = startup_report(base, phase, error)
    folder = Path(base) / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'startup-diagnostics.json'
    if phase == 'loading-qt' and target.is_file():
        try:
            existing = json.loads(target.read_text(encoding='utf-8'))
            other_pid = existing.get('pid') if isinstance(existing, dict) else None
            if isinstance(other_pid, int) and other_pid > 0 and other_pid != os.getpid():
                from instance_lock import _pid_alive
                if _pid_alive(other_pid):
                    return report
        except Exception:
            pass
    fd, temporary = tempfile.mkstemp(prefix='.startup-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report


def install_qt_message_logging():
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    log = logging.getLogger('qt.native')
    def handler(kind, context, message):
        level = logging.DEBUG
        if kind == QtMsgType.QtWarningMsg:
            level = logging.WARNING
        elif kind in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            level = logging.ERROR
        log.log(level, '%s', message)
    # Retain callable for the entire process, including native plugin failures.
    install_qt_message_logging.handler = handler
    qInstallMessageHandler(handler)
