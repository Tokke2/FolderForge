"""Real Windows GUI smoke test in an isolated installation, never user data.

Observe visible console windows every 10ms; this detects observed flashes, not
an absolute guarantee for all hardware/Windows policies. No startup registrations
or release network calls are allowed in the application test mode.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time


def main():
    if os.name != 'nt':
        raise SystemExit('Run this test on Windows, not a mocked desktop.')
    import psutil
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import updater
    evidence = Path('windows-evidence').resolve()
    evidence.mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='FolderForge-smoke-'))
    source = Path(__file__).resolve().parents[1]
    for name in updater.FILES:
        shutil.copy2(source / name, base / name)
    shutil.copytree(source / 'Icon', base / 'Icon')
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    launcher = updater.ensure_launcher(base, pythonw, base / 'Icon/projektmapp.ico')
    env = os.environ.copy()
    env['FOLDERFORGE_WINDOWS_SMOKE'] = '1'
    # Child must route through the actual windowless bootstrap on its first start.
    env.pop('FOLDERFORGE_RUNTIME_READY', None)
    env.pop('FOLDERFORGE_RUNTIME_POLICY', None)
    status_file = base / 'data/windows-smoke-status.json'
    violations, observations = [], []
    stop = threading.Event()
    allow_window = threading.Event()
    baseline_consoles = set()
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visible_windows():
        windows = []
        def visit(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, name, 256)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                windows.append((hwnd, name.value, pid.value))
            return True
        user32.EnumWindows(callback_type(visit), 0)
        return windows
    baseline_consoles.update(hwnd for hwnd, name, pid in visible_windows() if name == 'ConsoleWindowClass')
    def monitor():
        while not stop.wait(0.01):
            for hwnd, name, pid in visible_windows():
                if name == 'ConsoleWindowClass' and hwnd not in baseline_consoles:
                    # conhost owns a console window, not necessarily the app PID.
                    violations.append(dict(pid=pid, window_class=name, reason='new visible console'))
                if name.startswith('Tk') and not allow_window.is_set():
                    try:
                        command_line = ' '.join(psutil.Process(pid).cmdline())
                        if str(base).lower() in command_line.lower():
                            violations.append(dict(pid=pid, window_class=name, reason='GUI mapped before explicit restore'))
                    except psutil.Error:
                        pass
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    processes = []
    def launch():
        process = subprocess.Popen([str(launcher)], cwd=base, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process.pid)
    def status():
        try:
            return json.loads(status_file.read_text())
        except (OSError, ValueError):
            return {}
    def wait(predicate, message, timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = status()
            if value:
                observations.append(value)
                assert value['console'] == 0, 'GUI inherited a console handle'
            if predicate(value):
                return value
            time.sleep(0.1)
        raise AssertionError(message + ': ' + repr(status()))
    def command(action, number):
        path = base / 'data/windows-smoke-command.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(id=number, action=action)))
        os.replace(temporary, path)
    try:
        launch()
        first = wait(lambda s: s.get('state') == 'withdrawn' and s.get('tray'), 'Hidden GUI/tray not ready')
        assert first['icon'] not in ('none', 'failed', ''), first
        launch()
        time.sleep(3)
        second = wait(lambda s: s.get('pid') == first['pid'] and s.get('state') == 'withdrawn' and s.get('tray'), 'Double start changed primary')
        active = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            command_line = ' '.join(proc.info['cmdline'] or [])
            if proc.info['name'].lower() == 'pythonw.exe' and str(base / 'folder.pyw').lower() in command_line.lower():
                active.append(proc.pid)
        assert active == [first['pid']], ('Duplicate GUI processes', active)
        allow_window.set()
        command('restore', 1)
        wait(lambda s: s.get('state') == 'normal', 'Explicit tray restore failed')
        command('hide', 2)
        wait(lambda s: s.get('state') == 'withdrawn' and s.get('tray'), 'Return to tray failed')
        allow_window.clear()
        command('exit', 3)
        psutil.Process(first['pid']).wait(timeout=15)
        last_pid = first['pid']
        # Cold-start through VBS and directly through the hidden PS path as well.
        for number, arguments in enumerate([
            ['wscript.exe', str(base / 'Starta-FolderForge.vbs')],
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(base / 'Starta-FolderForge.ps1')],
        ], 10):
            subprocess.Popen(arguments, cwd=base, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
            current = wait(lambda s: s.get('pid') != last_pid and s.get('state') == 'withdrawn' and s.get('tray'),
                           'Cold VBS/PowerShell startup failed')
            last_pid = current['pid']
            command('exit', number)
            psutil.Process(last_pid).wait(timeout=15)
        # Install a deliberately broken candidate in the disposable installation.
        # The stable supervisor must restore the real previous app, with consent
        # supplied explicitly by this test harness (never a production flag).
        pending = base / 'data/update-pending'
        pending.mkdir()
        for name in updater.FILES:
            shutil.copy2(base / name, pending / name)
        (pending / 'folder.pyw').write_text("raise RuntimeError('simulated failed update')\n")
        sentinel = base / 'data/user-keep.txt'
        sentinel.write_text('user data must survive')
        updater.write_state(base, dict(installed='v0.0.2', pending='v0.0.2',
                                     pending_hashes=updater.content_manifest(pending)))
        updater.apply_pending(base)
        harness = base / 'data/trial-ci.py'
        harness.write_text(
            'import importlib.util,sys\nfrom pathlib import Path\n'
            'base=Path(sys.argv[1])\n'
            'spec=importlib.util.spec_from_file_location("stable",base/"data/update-supervisor.py")\n'
            'module=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n'
            'sys.exit(module.supervise_update(base,Path(sys.argv[2]),offer=lambda message: True))\n')
        worker = subprocess.Popen([str(pythonw), str(harness), str(base), str(pythonw)],
                                  cwd=base, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        assert worker.wait(timeout=45) == 1, 'Failed candidate was not detected'
        recovered = wait(lambda s: s.get('pid') != last_pid and s.get('state') == 'withdrawn' and s.get('tray'),
                         'Previous app did not restart hidden after rollback')
        assert sentinel.read_text() == 'user data must survive'
        assert (base / 'folder.pyw').read_bytes() == (source / 'folder.pyw').read_bytes()
        assert not (base / 'data/update-transaction.json').exists()
        command('exit', 4)
        psutil.Process(recovered['pid']).wait(timeout=15)
        assert not violations, violations
    finally:
        stop.set()
        thread.join(3)
        # Cleanup is limited to processes launched from this isolated test installation.
        for proc in psutil.process_iter(['pid', 'cmdline']):
            if proc.pid != os.getpid() and str(base).lower() in ' '.join(proc.info['cmdline'] or []).lower():
                try:
                    proc.terminate()
                except psutil.Error:
                    pass
        (evidence / 'startup.json').write_text(json.dumps(dict(observations=observations, visible_consoles=violations), indent=2))
        if (base / 'logs').exists():
            shutil.copytree(base / 'logs', evidence / 'logs', dirs_exist_ok=True)
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        details = traceback.format_exc()
        for log in Path('windows-evidence/logs').glob('*.log'):
            details += '\n' + log.name + '\n' + log.read_text(encoding='utf-8', errors='replace')[-12000:]
        print('::error title=Real Windows startup::' + details.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'), flush=True)
        raise
