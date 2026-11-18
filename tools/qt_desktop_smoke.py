"""Real default startup/tray/duplicate/Qt update test in a disposable app copy."""
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
    source = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(source))
    import updater
    root = Path(tempfile.mkdtemp(prefix='FolderForge-Qt-desktop-')).resolve()
    current_pid = None
    env = os.environ.copy()
    env.pop('QT_QPA_PLATFORM', None)
    env.pop('FOLDERFORGE_GUI', None)
    env['FOLDERFORGE_QT_SMOKE'] = '1'
    env['PYTHONUTF8'] = '1'
    try:
        for name in updater.FILES | updater.OPTIONAL_FILES:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, root / name)
        shutil.copytree(source / 'Icon', root / 'Icon')
        (root / 'data').mkdir()
        (root / 'data/settings.json').write_text(json.dumps({'save_root': str(root / 'Projects')}))
        def read_status():
            try:
                return json.loads((root / 'data/qt-smoke-status.json').read_text())
            except (OSError, ValueError):
                return {}
        def wait(predicate, description, timeout=70):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                status = read_status()
                if status:
                    assert not status['tk_loaded'], 'Default app imported Tk'
                if predicate(status):
                    return status
                time.sleep(.1)
            errors = root / 'logs/folderforge-errors.log'
            raise AssertionError(description + '\n' + repr(read_status()) + '\n' +
                                 (errors.read_text(encoding='utf-8', errors='replace')[-10000:] if errors.exists() else 'No error log'))
        def command(action, number):
            path = root / 'data/qt-smoke-command.json'
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(pid=read_status()['pid'], id=number, action=action)))
            os.replace(temporary, path)
        def launch():
            if os.name == 'nt':
                args = ['wscript.exe', str(root / 'Starta-FolderForge.vbs')]
            else:
                args = ['/bin/sh', str(root / 'Starta-FolderForge.sh')]
            subprocess.Popen(args, cwd=root, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        launch()
        status = wait(lambda s: s.get('tray') and not s.get('visible'), 'Default hidden Qt startup failed')
        current_pid = status['pid']
        launch()
        time.sleep(3)
        assert read_status()['pid'] == current_pid and not read_status()['visible'], 'Duplicate start changed window/instance'
        command('restore', 1)
        wait(lambda s: s.get('visible'), 'Restore failed')
        command('project-dialog', 2)
        wait(lambda s: s.get('dialog') and s.get('project_focused'), 'Project name did not get focus')
        command('close-project-dialog', 3)
        wait(lambda s: not s.get('dialog'), 'Dialog did not close')
        command('close-main', 4)
        wait(lambda s: not s.get('visible') and s.get('tray'), 'Close did not hide to tray')
        command('restore', 5)
        wait(lambda s: s.get('visible'), 'Second restore failed')
        command('minimize-main', 6)
        wait(lambda s: not s.get('visible') and s.get('tray'), 'Minimize did not hide to tray')
        command('exit', 7)
        psutil.Process(current_pid).wait(timeout=15)
        # Apply a real same-release candidate; supervise and verify actual Qt acknowledgement.
        pending = root / 'data/update-pending'
        pending.mkdir()
        for name in updater.FILES | updater.OPTIONAL_FILES:
            (pending / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, pending / name)
        shutil.copytree(root / 'Icon', pending / 'Icon')
        updater.write_state(root, dict(installed='v0.0.2', pending='v0.0.2', pending_hashes=updater.content_manifest(pending)))
        updater.apply_pending(root)
        interpreter = Path(sys.executable)
        if os.name == 'nt': interpreter = interpreter.with_name('pythonw.exe')
        # Environment belongs to this disposable harness, not production settings.
        previous = os.environ.get('FOLDERFORGE_QT_SMOKE')
        os.environ['FOLDERFORGE_QT_SMOKE'] = '1'
        try:
            child = updater.launch_update_trial(root, interpreter)
            assert child.wait(timeout=110) == 0, 'Qt update supervisor did not accept healthy start'
        finally:
            if previous is None: os.environ.pop('FOLDERFORGE_QT_SMOKE', None)
            else: os.environ['FOLDERFORGE_QT_SMOKE'] = previous
        status = wait(lambda s: s.get('pid') != current_pid and s.get('tray') and not s.get('visible'), 'Updated Qt app not ready')
        current_pid = status['pid']
        assert updater.read_state(root).get('startup_verified_at'), 'Qt did not acknowledge update'
        command('exit', 8)
        psutil.Process(current_pid).wait(timeout=15)
        print('Default Qt desktop OK: hidden startup, tray, duplicate, focus, close/minimize, exit, actual update acknowledgement')
    finally:
        if current_pid:
            try:
                proc = psutil.Process(current_pid)
                if proc.is_running(): proc.terminate(); proc.wait(timeout=10)
            except psutil.Error:
                pass
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('::error title=Default Qt desktop::' + traceback.format_exc().replace('%','%25').replace('\r','%0D').replace('\n','%0A'), flush=True)
        raise
