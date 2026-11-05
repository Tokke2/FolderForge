"""Keep embedded bootstrap recovery payloads identical to the editable scripts."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'updater.py'
source = path.read_text(encoding='utf-8')
marker = 'RUNTIME_BOOTSTRAP_FILES = {\n'
assert source.count(marker) == 1
payload = marker
for name in ('Starta-FolderForge.ps1', 'Starta-FolderForge.vbs'):
    text = (root / name).read_text(encoding='utf-8-sig')
    assert "'''" not in text
    payload += repr(name) + ": r'''" + text + "''',\n"
payload += '}\n'
path.write_text(source.split(marker, 1)[0] + payload, encoding='utf-8')
