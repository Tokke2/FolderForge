"""Keep legacy-update recovery payloads identical to extracted shared modules."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'updater.py'
source = path.read_text(encoding='utf-8')
start = '# BEGIN SHARED CORE PAYLOAD\n'
end = '# END SHARED CORE PAYLOAD\n'
assert source.count(start) == source.count(end) == 1
payload = 'SHARED_CORE_FILES = {\n'
for name in ('app_core.py', 'instance_lock.py', 'gui_entry.py', 'qt_diagnostics.py', 'qt_app.py', 'qt_preview.py', 'workspace.py', 'qt_help.py', 'qt_integrations.py', 'Starta-FolderForge-Tk.py', 'requirements-tk.txt'):
    payload += repr(name) + ': ' + repr((root / name).read_text(encoding='utf-8')) + ',\n'
payload += '}\n'
path.write_text(source.split(start)[0] + start + payload + end + source.split(end)[1], encoding='utf-8')
