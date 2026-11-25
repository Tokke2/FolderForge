"""Expose failing tracebacks as check annotations, as well as downloadable logs."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
folder = root / 'windows-evidence'
folder.mkdir(exist_ok=True)
report = []
for test, traceback in result.errors + result.failures:
    text = f'{test}\n{traceback}'
    report.append(text)
    escaped = text.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::error title=Windows regression::' + escaped, flush=True)
(folder / 'unit-tests.txt').write_text('\n\n'.join(report) or f'{result.testsRun} tests passed', encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)
