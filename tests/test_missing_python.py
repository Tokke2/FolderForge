"""Installer policy regressions; all installers and dialogs are local mocks."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MissingPythonTests(unittest.TestCase):
    def test_windows_offer_is_only_in_absence_branch(self):
        source = (ROOT / 'Starta-FolderForge.ps1').read_text(encoding='utf-8-sig')
        main = source.split('\ntry {\n    Remove-LegacyMaintenanceTask', 1)[1]
        gate = main.index('if (-not (Test-AnyInstalledPython $Candidates))')
        offer = main.index('Offer-MissingPythonInstall')
        gui = main.index('$Windowless = Select-ExistingPython')
        self.assertLess(gate, offer)
        self.assertLess(offer, gui)
        self.assertNotIn('Offer-MissingPythonInstall', main[gui:])
        body = source.split('function Offer-MissingPythonInstall', 1)[1].split('\ntry {', 1)[0]
        self.assertLess(body.index('$Answer -ne 6'), body.index("Get-Command 'winget.exe'"))
        self.assertIn('Test-AnyInstalledPython @(Get-PythonCandidates)', body)
        self.assertNotIn("'upgrade'", source)

    def test_release_entrypoints_and_no_standalone_installer(self):
        import updater
        import plistlib
        for name in ('Starta-FolderForge.sh', 'Starta-FolderForge.app/Contents/MacOS/FolderForge',
                     'Starta-FolderForge.app/Contents/Info.plist'):
            self.assertTrue((ROOT / name).is_file())
            self.assertIn(name, updater.OPTIONAL_FILES)
        info = plistlib.loads((ROOT / 'Starta-FolderForge.app/Contents/Info.plist').read_bytes())
        self.assertTrue(info['LSUIElement'])
        self.assertFalse(list(ROOT.glob('Installera*.bat')))

    @unittest.skipIf(os.name == 'nt', 'POSIX shell')
    def test_shell_policy_present_declined_accepted_and_failed(self):
        functions = (ROOT / 'Starta-FolderForge.sh').read_text().split('# MAIN --', 1)[0]
        for present, consent, result, expected in [(1, 0, 0, ''), (0, 1, 0, 'ask\n'),
                                                  (0, 0, 0, 'ask\ninstall\n'),
                                                  (0, 0, 7, 'ask\ninstall\n')]:
            with self.subTest(present=present, consent=consent, result=result), tempfile.TemporaryDirectory() as temp:
                Path(temp, 'logs').mkdir()
                script = functions + '''
ROOT=$1
find_python() { PYTHON_PRESENT=''' + str(present) + '''; PYTHON_COMMAND=/bin/true; }
confirm_missing() { printf 'ask\\n' >> "$ROOT/calls"; return ''' + str(consent) + '''; }
install_missing() { printf 'install\\n' >> "$ROOT/calls"; return ''' + str(result) + '''; }
notify() { :; }
start_or_offer
'''
                proc = subprocess.run(['/bin/sh', '-c', script, 'test', temp], timeout=10, capture_output=True)
                calls = Path(temp, 'calls')
                self.assertEqual(calls.read_text() if calls.exists() else '', expected)
                self.assertEqual(proc.returncode, result)
                self.assertFalse(Path(temp, 'logs/python-first-install.lock').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX shell')
    def test_broken_executable_counts_as_present(self):
        functions = (ROOT / 'Starta-FolderForge.sh').read_text().split('# MAIN --', 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp, 'python')
            candidate.write_text('#!/bin/sh\nexit 1\n')
            candidate.chmod(0o755)
            script = functions + '\nPYTHON_PRESENT=0; PYTHON_COMMAND=; consider_python "$1"; [ "$PYTHON_PRESENT" -eq 1 ] && [ -z "$PYTHON_COMMAND" ]'
            subprocess.run(['/bin/sh', '-c', script, 'test', str(candidate)], check=True, timeout=10)
