"""Real Tk + tray integration in CI; synthetic isolated data, no registrations."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


def main():
    import psutil
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import updater
    source = Path(__file__).resolve().parents[1]
    base = Path(tempfile.mkdtemp(prefix='FolderForge-posix-')).resolve()
    evidence = source / 'windows-evidence'
    evidence.mkdir(exist_ok=True)
    for name in updater.FILES | updater.OPTIONAL_FILES:
        shutil.copy2(source / name, base / name)
    shutil.copytree(source / 'Icon', base / 'Icon')
    env = os.environ.copy()
    env['FOLDERFORGE_WINDOWS_SMOKE'] = '1'
    status_path = base / 'data/windows-smoke-status.json'
    observed = []
    def status():
        try:
            return json.loads(status_path.read_text())
        except (OSError, ValueError):
            return {}
    def wait(predicate, reason):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            value = status()
            if value:
                observed.append(value)
            if predicate(value):
                return value
            time.sleep(0.1)
        raise AssertionError(reason + ': ' + repr(status()))
    def command(action, number):
        path = base / 'data/windows-smoke-command.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(pid=status()['pid'], id=number, action=action)))
        os.replace(temp, path)
    def launch():
        process = subprocess.run([sys.executable, str(base / 'Starta-FolderForge.py')], env=env,
                                 cwd=base, capture_output=True, timeout=15)
        assert process.returncode == 0, process.stderr
    try:
        launch()
        first = wait(lambda s: s.get('state') == 'withdrawn' and s.get('tray'), 'Hidden GUI/tray did not initialize')
        launch()
        time.sleep(3)
        assert status()['pid'] == first['pid']
        assert status()['state'] == 'withdrawn'
        command('restore', 1)
        wait(lambda s: s.get('state') in ('normal', 'zoomed'), 'Explicit restore failed')
        command('hide', 2)
        wait(lambda s: s.get('state') == 'withdrawn' and s.get('tray'), 'Hide failed')
        command('exit', 3)
        psutil.Process(first['pid']).wait(timeout=15)
    finally:
        for process in psutil.process_iter(['pid', 'cmdline']):
            if process.pid != os.getpid() and str(base) in ' '.join(process.info['cmdline'] or []):
                try:
                    process.terminate()
                except psutil.Error:
                    pass
        (evidence / 'posix-startup.json').write_text(json.dumps(observed, indent=2))
        if (base / 'logs').exists():
            shutil.copytree(base / 'logs', evidence / 'logs', dirs_exist_ok=True)
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        text = traceback.format_exc()
        for log in Path('windows-evidence/logs').glob('*.log'):
            text += '\n' + log.name + '\n' + log.read_text(encoding='utf-8', errors='replace')[-8000:]
        text = text.encode('ascii', 'backslashreplace').decode('ascii')
        print('::error title=POSIX GUI startup::' + text.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'), flush=True)
        raise
