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

    def test_existing_python_is_detected_before_install_and_no_upgrade_install_fallback(self):
        install = self.ps.index("@('install','--id'")
        self.assertLess(self.ps.index('Get-PythonInfo $Candidate'), install)
        self.assertLess(self.ps.index('if (-not $Info) {'), install)
        self.assertEqual(self.ps.count("@('install','--id'"), 1)
        upgrade = self.ps[self.ps.index("@('upgrade','--id'"):self.ps.index("$Code = 'import sys,json; sys.path.insert(0,sys.argv[1]); import settings; print(json.dumps(sorted(set(p for p in settings.REQUIRED_PACKAGES.values() if p))))'", self.ps.index("@('upgrade','--id'"))]
        self.assertNotIn("@('install'", upgrade)
        self.assertIn('Python.Python.$Series', upgrade)
        self.assertIn('No install fallback', upgrade)

    def test_registry_path_and_launcher_detection_avoid_store_alias_and_duplicate_runtime(self):
        for token in ['HKCU:', 'HKLM:', 'WOW6432Node', "@('-0p')", 'WindowsApps', 'Get-AppxPackage', '$ExistingCandidates.Count -gt 0']:
            self.assertIn(token, self.ps)
        self.assertIn('No parallel Python was installed', self.ps)
        self.assertIn('Only a prerelease Python was found', self.ps)

    def test_active_app_defers_mutations_and_other_python_processes_are_not_stopped(self):
        self.assertIn('Test-AppRunning', self.ps)
        self.assertIn('Package changes deferred', self.ps)
        self.assertIn("Name LIKE 'python%.exe'", self.ps)
        for token in ['Stop-Process', 'taskkill', 'TerminateProcess']:
            self.assertNotIn(token, self.ps)

    def test_weekly_updates_use_shared_python_without_creating_environment(self):
        self.assertIn('$Console = [string]$Info.executable', self.ps)
        self.assertNotIn("'-m','venv'", self.ps)
        self.assertNotIn('python-envs', self.ps)
        self.assertNotIn('CandidateConsole', self.ps)
        self.assertIn("$PipOptions = @('-m','pip','--isolated'", self.ps)
        self.assertIn("'--upgrade-strategy','only-if-needed'", self.ps)
        self.assertIn('Test-Environment $Console', self.ps)
        # Do not isolate Python's user-site: shared installs may live there.
        environment_check = self.ps[self.ps.index('function Test-Environment'):self.ps.index('function Get-LatestStableSeries')]
        self.assertNotIn("'-I'", environment_check)

    def test_schedule_state_is_atomic_and_old_environment_is_not_deleted(self):
        self.assertIn('[IO.File]::Replace($Temp, $Path, $null)', self.ps)
        self.assertIn('[IO.File]::Move($Temp, $Path)', self.ps)
        self.assertNotIn('shutil.rmtree', self.ps)
        self.assertNotIn('Remove-Item -Recurse', self.ps)
        self.assertIn('LastAttemptPeriod', self.ps)

    def test_shared_package_operations_and_logs_remain_explicit(self):
        self.assertIn("$Logs = Join-Path $Root 'logs'", self.ps)
        self.assertIn('folderforge-errors.log', self.ps)
        self.assertIn("$PipOptions = @('-m','pip','--isolated'", self.ps)
        self.assertIn("$Start.EnvironmentVariables.Remove('PYTHONHOME')", self.ps)
        self.assertIn("$Start.EnvironmentVariables.Remove('PYTHONPATH')", self.ps)
        self.assertIn("$env:FOLDERFORGE_RUNTIME_POLICY = 'weekly-shared'", self.ps)

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

    def test_latest_stable_is_discovered_not_hardcoded_and_patches_keep_existing_series(self):
        self.assertIn('api.github.com/repos/microsoft/winget-pkgs', self.ps)
        self.assertIn('/Python/Python/3', self.ps)
        self.assertNotIn('Python.Python.3.14', self.ps)
        self.assertNotIn('--pre', self.ps)
        self.assertIn('Python.Python.$Series', self.ps)

    def test_io_drains_both_native_streams_concurrently_without_showing_console(self):
        self.assertIn('$Out = $Process.StandardOutput.ReadToEndAsync()', self.ps)
        self.assertIn('$Err = $Process.StandardError.ReadToEndAsync()', self.ps)
        self.assertIn('$Info.CreateNoWindow = $true', self.ps)
        self.assertIn('$Info.UseShellExecute = $false', self.ps)
        self.assertIn('$Child.HasExited', self.ps)
        self.assertIn('FolderForge_RuntimeMaintenance', self.ps)

    def test_cached_native_launchers_are_refreshed_before_normal_app_start(self):
        self.assertIn('from updater import ensure_launcher', self.ps)
        self.assertLess(self.ps.index('from updater import ensure_launcher'), self.ps.index('$Child = [Diagnostics.Process]::Start($Start)'))
        self.assertIn('Native launcher refresh failed', self.ps)

    def test_runtime_command_failures_reach_central_logs_with_bounded_details(self):
        self.assertIn('function Write-CommandFailure', self.ps)
        self.assertIn('$Detail.Length -gt 4000', self.ps)
        self.assertIn("Write-CommandFailure 'Shared package upgrade' $Pip", self.ps)
        self.assertIn("Write-CommandFailure 'Python upgrade' $Upgrade", self.ps)

    def test_weekly_task_runs_monday_eight_with_missed_run_catchup(self):
        self.assertIn("-Weekly -WeeksInterval 1 -DaysOfWeek Monday -At '08:00'", self.ps)
        self.assertIn('-StartWhenAvailable', self.ps)
        self.assertIn('-LogonType Interactive -RunLevel Limited', self.ps)
        self.assertIn(' -MaintenanceOnly', updater.RUNTIME_BOOTSTRAP_FILES['Starta-FolderForge.vbs'])
        self.assertIn('if (-not $MaintenanceOnly)', self.ps)
        self.assertIn('Get-WeeklyBoundary $Now', self.ps)

    def test_weekly_attempt_is_recorded_before_network_operations(self):
        due = self.ps.index('        if ($Due) {')
        stamp = self.ps.index('$State.LastAttemptPeriod = $Boundary', due)
        upgrade = self.ps.index("@('upgrade','--id'", due)
        pip = self.ps.index("'install','--upgrade'", due)
        self.assertLess(due, stamp)
        self.assertLess(stamp, upgrade)
        self.assertLess(stamp, pip)
        self.assertIn('([datetime]$State.LastAttemptPeriod) -lt $Boundary', self.ps)
        self.assertIn('No weekly maintenance due; no online Python/package update check at this start', self.ps)

    def test_busy_deferral_does_not_mark_week_as_attempted(self):
        due = self.ps.index('        if ($Due) {')
        busy = self.ps.index('if (Test-PythonBusy)', due)
        stamp = self.ps.index('$State.LastAttemptPeriod =', due)
        self.assertLess(busy, stamp)
        self.assertIn('if ($MaintenanceOnly) { $ExitCode = 2 }', self.ps)
        self.assertIn('no maintenance attempt recorded', self.ps)

    def test_initial_missing_only_installs_pin_existing_versions_without_upgrade(self):
        start = self.ps.index('# Initial setup/migration')
        end = self.ps.index('$Windowless = Join-Path', start)
        initial = self.ps[start:end]
        self.assertIn("'--constraint',$Pins", initial)
        self.assertNotIn("'--upgrade'", initial)
        self.assertIn("$Console @('-m','ensurepip')", initial)
        self.assertIn('if (Test-PythonBusy)', initial)
        self.assertIn('m.version(n)', initial)

    def test_first_registration_does_not_run_historical_week_at_every_start(self):
        self.assertIn('if (-not $State.WeeklyEnabledAt)', self.ps)
        self.assertIn('$Boundary -ge ([datetime]$State.WeeklyEnabledAt)', self.ps)
        self.assertIn('$Now.Date.AddDays(-$Days).AddHours(8)', self.ps)
        self.assertIn('$Boundary = $Boundary.AddDays(-7)', self.ps)

    def test_private_runtime_migrates_even_on_internal_restart_without_secondary_loop(self):
        source = Path('folder.pyw').read_text(encoding='utf-8')
        self.assertIn('sys.prefix != sys.base_prefix', source)
        self.assertIn('os.environ.get("FOLDERFORGE_RUNTIME_POLICY") != "weekly-shared"', source)
        self.assertIn('os.environ.get("FOLDERFORGE_RUNTIME_SECONDARY") != "1"', source)
        self.assertIn('Recovery of a legacy private instance must still migrate', source)
        self.assertIn('\n    if IS_WINDOWS and sys.prefix != sys.base_prefix:\n', source)

    def test_scheduled_job_is_windowless_and_preserves_busy_exit_code(self):
        self.assertIn("'wscript.exe'", self.ps)
        self.assertIn('-Execute $WindowlessHost', self.ps)
        vbs = updater.RUNTIME_BOOTSTRAP_FILES['Starta-FolderForge.vbs']
        self.assertIn('shell.Run(command, 0, True)', vbs)
        self.assertIn('WScript.Quit result', vbs)
        self.assertIn('-MaintenanceOnly', vbs)

    def test_scheduled_job_skips_already_handled_week_without_retry_loop(self):
        self.assertIn('if ($MaintenanceOnly -and -not $Due)', self.ps)
        self.assertIn('Weekly maintenance already handled or not yet due', self.ps)
        self.assertIn('-DontStopIfGoingOnBatteries', self.ps)
        self.assertIn('-ExecutionTimeLimit ([TimeSpan]::Zero)', self.ps)

    def test_offline_weekly_failure_does_not_block_still_working_shared_imports(self):
        self.assertIn("if (-not $MaintenanceOnly -and -not (Test-Environment $Console))", self.ps)
        self.assertIn('completed_with_conflicts', self.ps)
