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
    # Synthetic settings only inside the disposable test copy.
    size = os.environ.get('FOLDERFORGE_TEST_TEXT_SIZE', '100%')
    (base / 'data').mkdir(exist_ok=True)
    (base / 'data/settings.json').write_text(json.dumps({'text_size': size}), encoding='utf-8')
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
        if sys.platform.startswith('linux'):
            from Xlib import display
            connection = display.Display()
            try:
                assert connection.get_selection_owner(connection.intern_atom('_NET_SYSTEM_TRAY_S0')), 'No X11 tray manager'
            finally:
                connection.close()
        launch()
        time.sleep(3)
        assert status()['pid'] == first['pid']
        assert status()['state'] == 'withdrawn'
        command('restore', 1)
        wait(lambda s: s.get('state') in ('normal', 'zoomed'), 'Explicit restore failed')
        command('accessibility-regression', 31)
        report_path = base / 'data/accessibility-construction.json'
        deadline = time.monotonic() + 20
        report = None
        while time.monotonic() < deadline:
            try:
                report = json.loads(report_path.read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        assert report and report['injected'] and report['styled'] and not report['error'], report
        (evidence / 'accessibility-construction.json').write_text(json.dumps(report, indent=2))
        command('project-dialog', 21)
        layout_path = base / 'data/project-dialog-layout.json'
        deadline = time.monotonic() + 20
        layout = None
        while time.monotonic() < deadline:
            try:
                layout = json.loads(layout_path.read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        assert layout, 'Modal project dialog did not report its geometry'
        assert layout['text_size'] == size, layout
        width, height = layout['window']
        assert layout['subtitle'][2] > width * 0.65, ('Narrow subtitle', layout)
        assert layout['subtitle'][3] < 100, ('Vertically wrapped subtitle', layout)
        assert (abs(layout['location'][1] - layout['year'][1]) < 8
                or layout['year'][1] > layout['location'][1]), layout
        for key in ('preview', 'actions'):
            x, y, w, h = layout[key]
            assert y >= 0 and y + h <= height + 2, ('Footer clipped', key, layout)
        assert layout['actions'][1] >= layout['preview'][1] + layout['preview'][3], layout
        # Validate the real controls, not merely their containing frame.
        assert layout['create'][2] >= layout['button_text_width'] + 12, layout
        for name in ('create', 'cancel'):
            x, y, width, height = layout[name]
            assert width >= 60 and height < layout['window'][1] / 4, layout
            assert x >= 0 and x + width <= layout['window'][0], layout
            assert y >= 0 and y + height <= layout['window'][1], layout
        for name in ('location', 'year'):
            assert layout[name][2] >= 90, layout
        (evidence / 'project-dialog.json').write_text(json.dumps(layout, indent=2))
        command('close-project-dialog', 22)
        time.sleep(0.3)
        command('hide', 2)
        wait(lambda s: s.get('state') == 'withdrawn' and s.get('tray'), 'Hide failed')
        command('exit', 3)
        psutil.Process(first['pid']).wait(timeout=15)
        # A real healthy update must acknowledge its own Tk callback on this OS.
        pending = base / 'data/update-pending'
        pending.mkdir()
        for name in updater.FILES | updater.OPTIONAL_FILES:
            shutil.copy2(base / name, pending / name)
        keep = base / 'data/user-keep.txt'
        keep.write_text('preserve user data')
        updater.write_state(base, dict(installed='v0.0.2', pending='v0.0.2',
                                     pending_hashes=updater.content_manifest(pending)))
        updater.apply_pending(base)
        previous = os.environ.get('FOLDERFORGE_WINDOWS_SMOKE')
        os.environ['FOLDERFORGE_WINDOWS_SMOKE'] = '1'
        try:
            worker = updater.launch_update_trial(base, sys.executable)
        finally:
            if previous is None:
                os.environ.pop('FOLDERFORGE_WINDOWS_SMOKE', None)
            else:
                os.environ['FOLDERFORGE_WINDOWS_SMOKE'] = previous
        healthy = wait(lambda v: v.get('pid') != first['pid'] and v.get('state') == 'withdrawn' and v.get('tray'),
                       'Healthy update did not start hidden')
        assert worker.wait(timeout=30) == 0, 'Tk startup acknowledgement failed'
        assert not updater.read_state(base).get('startup_pending')
        assert (base / 'data/update-backup/folder.pyw').exists()
        assert keep.read_text() == 'preserve user data'
        command('exit', 4)
        psutil.Process(healthy['pid']).wait(timeout=15)

        # The old, stable supervisor must survive an intentionally broken app.
        pending.mkdir()
        for name in updater.FILES | updater.OPTIONAL_FILES:
            shutil.copy2(base / name, pending / name)
        (pending / 'folder.pyw').write_text("raise RuntimeError('intentional CI failed update')\n")
        updater.write_state(base, dict(installed='v0.0.2', pending='v0.0.2',
                                     pending_hashes=updater.content_manifest(pending)))
        updater.apply_pending(base)
        harness = base / 'data/recover-ci.py'
        harness.write_text('import importlib.util,sys\nfrom pathlib import Path\n'
            'b=Path(sys.argv[1])\ns=importlib.util.spec_from_file_location("stable",b/"data/update-supervisor.py")\n'
            'm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\n'
            'sys.exit(m.supervise_update(b,Path(sys.executable),offer=lambda question: True))\n')
        worker = subprocess.Popen([sys.executable, str(harness), str(base)], env=env, cwd=base,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert worker.wait(timeout=30) == 1, 'Broken update was not detected'
        restored = wait(lambda v: v.get('pid') != healthy['pid'] and v.get('state') == 'withdrawn' and v.get('tray'),
                        'Previous app did not restart after rollback')
        assert keep.read_text() == 'preserve user data'
        assert (base / 'folder.pyw').read_bytes() == (source / 'folder.pyw').read_bytes()
        command('exit', 5)
        psutil.Process(restored['pid']).wait(timeout=15)
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
