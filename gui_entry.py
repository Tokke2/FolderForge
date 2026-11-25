"""Default Qt entry. No Tk imports or automatic dependency installation."""
import ctypes
import logging
import os
from pathlib import Path
import subprocess
import sys


def main():
    base = Path(__file__).resolve().parent
    from logg import init_logging
    init_logging()
    log = logging.getLogger('startup.qt')
    try:
        # Existing hidden native bootstrap discovers a usable system interpreter.
        if os.name == 'nt' and (os.environ.get('FOLDERFORGE_RUNTIME_READY') != '1'
                or os.environ.get('FOLDERFORGE_RUNTIME_POLICY') != 'system-python'):
            from updater import launch_runtime_bootstrap
            launch_runtime_bootstrap(base, sys.executable, sys.argv[1:])
            return 0
        from qt_diagnostics import save_startup_report
        save_startup_report(base, 'loading-qt')
        from qt_app import run
        log.info('Default GUI: Qt; Tk is available only through explicit reserve startup')
        return run()
    except Exception as exc:
        log.exception('Qt-start misslyckades; ingen automatisk Tk-start eller installation görs')
        try:
            from qt_diagnostics import save_startup_report
            save_startup_report(base, 'failed', str(exc))
        except Exception:
            log.exception('Kunde inte skriva startdiagnostik')
        message = ('FolderForge kunde inte starta Qt.\n\n' + str(exc) +
                   '\n\nSe logs/folderforge-errors.log och logs/startup-diagnostics.json.\n'
                   'PySide6 och övriga beroenden i requirements.txt måste finnas i den Python som startaren väljer.\n'
                   'Ingen installation kördes. Reserv: Starta-FolderForge-Tk.py. Följ IT-policy.')
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None, message, 'FolderForge – startfel', 0x10)
        else:
            print(message, file=sys.stderr)
        return 1
