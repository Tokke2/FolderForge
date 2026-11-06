import ast
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import updater


class RuntimeBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.ps = updater.RUNTIME_BOOTSTRAP_FILES['Starta-FolderForge.ps1']

    def test_recovery_payloads_match_distributed_source_files(self):
        for name, text in updater.RUNTIME_BOOTSTRAP_FILES.items():
            self.assertEqual(Path(name).read_text(encoding='utf-8-sig'), text)
            self.assertIn(name, updater.FILES)

    def test_older_six_file_install_can_recover_new_bootstrap_scripts(self):
        script = updater.ensure_runtime_bootstrap(self.base)
        self.assertEqual(script, self.base / 'Starta-FolderForge.ps1')
        self.assertEqual(script.read_text(encoding='utf-8-sig'), self.ps)
        self.assertTrue((self.base / 'Starta-FolderForge.vbs').exists())
        self.assertTrue(script.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_repeated_bootstrap_generation_is_noop_and_repairs_changed_scripts(self):
        script = updater.ensure_runtime_bootstrap(self.base)
        first = script.stat().st_mtime_ns
        updater.ensure_runtime_bootstrap(self.base)
        self.assertEqual(first, script.stat().st_mtime_ns)
        script.write_text('broken')
        updater.ensure_runtime_bootstrap(self.base)
        self.assertEqual(script.read_text(encoding='utf-8-sig'), self.ps)

    def test_failed_atomic_bootstrap_write_keeps_existing_file(self):
        script = self.base / 'Starta-FolderForge.ps1'
        script.write_text('existing script')
        with patch.object(updater.os, 'replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError):
                updater.ensure_runtime_bootstrap(self.base)
        self.assertEqual(script.read_text(), 'existing script')
        self.assertFalse(list(self.base.glob('.bootstrap-*')))

    def test_python_handoff_is_windowless_with_lossless_argument_encoding(self):
        arguments = ['--tray', 'Rickard Längkvist', 'D:\\my folder\\', '"quoted"']
        with patch.object(updater.subprocess, 'Popen') as spawn:
            updater.launch_runtime_bootstrap(self.base, Path('pythonw.exe'), arguments)
        call = spawn.call_args
        argv = call.args[0]
        self.assertIn('-NoProfile', argv)
        self.assertIn('-NonInteractive', argv)
        self.assertIn('-File', argv)
        encoded = argv[argv.index('-Arguments64') + 1]
        self.assertEqual(base64.b64decode(encoded).decode().split('\0'), arguments)
        self.assertTrue(call.kwargs['close_fds'])
        self.assertNotIn('shell', call.kwargs)
        self.assertIn('creationflags', call.kwargs)

    def test_native_launcher_checks_runtime_except_for_selftest(self):
        source = updater.launcher_source(Path('pythonw.exe'), self.base / 'folder.pyw')
        self.assertIn('if (selftest)', source)
        self.assertIn('Starta-FolderForge.ps1', source)
        self.assertIn('-PreferredPython', source)
        self.assertIn('info.CreateNoWindow = true', source)
        self.assertIn('info.UseShellExecute = false', source)

    def test_missing_python_can_be_bootstrapped_without_running_python_first(self):
        vbs = updater.RUNTIME_BOOTSTRAP_FILES['Starta-FolderForge.vbs']
        self.assertIn('shell.Run command, 0, False', vbs)
        self.assertIn('powershell.exe', vbs)
        self.assertNotIn('python.exe', vbs)







    def test_every_external_start_but_not_selftest_or_internal_restart_checks_runtime(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        guards = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                          and child.func.id == 'launch_runtime_bootstrap' for child in ast.walk(node))]
        guard = next(node for node in guards if 'FOLDERFORGE_RUNTIME_READY' in ast.unparse(node.test))
        code = ast.unparse(guard)
        self.assertIn("'--selftest' not in sys.argv", code)
        self.assertIn('IS_WINDOWS', code)
        self.assertIn('sys.exit(0)', code)

    def test_system_python_selection_prefers_path_over_cached_interpreter(self):
        self.assertLess(self.ps.index("Get-Command $Name -All"), self.ps.index('if ($PreferredPython)'))
        self.assertNotIn('python-runtime.json', self.ps)

    def test_no_python_or_dependency_versions_are_checked(self):
        for token in ('sys.version_info', 'importlib.metadata', 'Test-Environment', 'REQUIRED_PACKAGES', 'Get-LatestStableSeries'):
            self.assertNotIn(token, self.ps)

    def test_no_install_upgrade_network_or_virtual_environment(self):
        for token in ('winget', 'pypi.org', 'Invoke-RestMethod', 'ensurepip', "'-m','pip'", "'-m','venv'", 'https://'):
            self.assertNotIn(token, self.ps)

    def test_obsolete_weekly_task_is_removed_not_recreated(self):
        self.assertIn('Unregister-ScheduledTask -TaskName $Name', self.ps)
        self.assertIn("'FolderForge Python weekly '", self.ps)
        self.assertNotIn('Register-ScheduledTask ', self.ps)
        self.assertNotIn('Get-ScheduledTask |', self.ps)
        self.assertIn("$Root.ToLowerInvariant()", self.ps)

    def test_legacy_maintenance_invocation_never_launches_app(self):
        self.assertLess(self.ps.index('if ($MaintenanceOnly) { exit 0 }'), self.ps.index('$Candidates ='))

    def test_no_python_check_popup_or_state_replacement(self):
        for token in ('MessageBox', 'System.Windows.Forms', '[IO.File]::Replace', 'Save-RuntimeState'):
            self.assertNotIn(token, self.ps)
        self.assertIn('folderforge-errors.log', self.ps)

    def test_minimized_windowless_start_is_enforced(self):
        self.assertIn("$AppArgs += '--tray'", self.ps)
        self.assertIn("$Start.FileName = $Windowless", self.ps)
        self.assertIn('$Start.CreateNoWindow = $true', self.ps)
        self.assertIn('$Start.UseShellExecute = $false', self.ps)
        self.assertIn("'system-python'", self.ps)

    def test_local_identity_probe_does_not_hide_shared_user_packages(self):
        self.assertIn('getattr(sys,"_base_executable",sys.executable)', self.ps)
        self.assertNotIn("'-I'", self.ps)
        self.assertIn('ReadToEndAsync()', self.ps)

    def test_startup_no_longer_installs_missing_packages(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.If) and '__name__' in ast.unparse(node.test):
                calls = [n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
                self.assertNotIn('check_and_install_requirements', calls)

    def test_selftest_and_internal_restart_remain_exempt(self):
        source = Path('folder.pyw').read_text(encoding='utf-8')
        self.assertIn('os.environ.get("FOLDERFORGE_RUNTIME_POLICY") != "system-python"', source)
        self.assertIn('"--selftest" not in sys.argv', source)
