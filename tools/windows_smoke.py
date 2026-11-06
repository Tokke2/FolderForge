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
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def monitor():
        def visit(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, 256)
            if name.value != 'ConsoleWindowClass':
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                command = ' '.join(psutil.Process(pid.value).cmdline())
                if str(base).lower() in command.lower():
                    violations.append(dict(pid=pid.value, window_class=name.value, command=command))
            except (psutil.Error, OSError):
                pass
            return True
        callback = callback_type(visit)
        while not stop.wait(0.01):
            user32.EnumWindows(callback, 0)
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
        command('restore', 1)
        wait(lambda s: s.get('state') == 'normal', 'Explicit tray restore failed')
        command('hide', 2)
        wait(lambda s: s.get('state') == 'withdrawn' and s.get('tray'), 'Return to tray failed')
        command('exit', 3)
        psutil.Process(first['pid']).wait(timeout=15)
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
    main()
