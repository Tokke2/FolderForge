import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import updater


class InstanceHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.script = self.folder / 'folder.pyw'

    def test_fresh_probe_answers_only_when_primary_services_ui_tick(self):
        ready = threading.Event()
        def answer():
            while not ready.wait(0.01):
                updater.service_instance_health(self.folder, self.script)
        thread = threading.Thread(target=answer)
        thread.start()
        try:
            self.assertTrue(updater.probe_instance(self.folder, os.getpid(), timeout=1))
        finally:
            ready.set()
            thread.join()
        self.assertEqual(list(self.folder.glob('*.request')), [])
        self.assertEqual(list(self.folder.glob('*.reply')), [])

    def test_old_heartbeat_does_not_substitute_for_response(self):
        updater.service_instance_health(self.folder, self.script)
        self.assertFalse(updater.probe_instance(self.folder, os.getpid(), timeout=0.02))

    def test_wrong_pid_or_nonce_not_answered(self):
        path = self.folder / 'folderforge-probe-abc.request'
        path.write_text(json.dumps(dict(pid=os.getpid() + 1, nonce='abc')))
        updater.service_instance_health(self.folder, self.script)
        self.assertFalse(path.with_suffix('.reply').exists())
        path.write_text(json.dumps(dict(pid=os.getpid(), nonce='wrong')))
        updater.service_instance_health(self.folder, self.script)
        self.assertFalse(path.with_suffix('.reply').exists())

    def test_locked_cleanup_does_not_discard_valid_health_answer(self):
        write = updater._health_write
        def answer(path, value):
            write(path, value)
            write(path.with_suffix('.reply'), value)
        with patch.object(updater, '_health_write', side_effect=answer), \
             patch.object(Path, 'unlink', side_effect=PermissionError('Windows reader still open')):
            self.assertTrue(updater.probe_instance(self.folder, os.getpid(), 1))

    def test_concurrent_probes_have_separate_replies(self):
        stop = threading.Event()
        def answer():
            while not stop.wait(0.01):
                updater.service_instance_health(self.folder, self.script)
        worker = threading.Thread(target=answer)
        worker.start()
        results = []
        probes = [threading.Thread(target=lambda: results.append(updater.probe_instance(self.folder, os.getpid(), 2))) for _ in range(3)]
        try:
            for thread in probes:
                thread.start()
            for thread in probes:
                thread.join(3)
            self.assertEqual(results, [True, True, True])
        finally:
            stop.set()
            worker.join()

    def test_stale_files_are_cleaned_and_large_request_ignored(self):
        stale = self.folder / 'folderforge-probe-old.request'
        stale.write_text('{}')
        os.utime(stale, (1, 1))
        large = self.folder / 'folderforge-probe-big.request'
        large.write_text('x' * 3000)
        updater.service_instance_health(self.folder, self.script)
        self.assertFalse(stale.exists())
        self.assertFalse(large.exists())

    def test_cleanup_never_removes_another_owner_heartbeat(self):
        path = self.folder / 'folderforge-health.json'
        path.write_text(json.dumps(dict(pid=os.getpid() + 1)))
        updater.clear_instance_health(self.folder)
        self.assertTrue(path.exists())
        updater.service_instance_health(self.folder, self.script)
        updater.clear_instance_health(self.folder)
        self.assertFalse(path.exists())

    def identity(self, **changes):
        info = dict(ExecutablePath=r'C:\Python\pythonw.exe', Created='1234567890')
        argv = [info['ExecutablePath'], r'D:\Program\FolderForge\folder.pyw', '--tray']
        args = dict(info=info, argv=argv, script=argv[1], created=1234567890, image=info['ExecutablePath'])
        args.update(changes)
        return updater._verified_process_identity(**args)

    def test_exact_script_interpreter_and_start_time_are_required(self):
        self.assertTrue(self.identity())
        self.assertFalse(self.identity(created=1234567990))
        self.assertFalse(self.identity(argv=['pythonw.exe', r'D:\Other\script.py']))
        self.assertFalse(self.identity(argv=['pythonw.exe', '-c', 'code', r'D:\Program\FolderForge\folder.pyw']))
        self.assertFalse(self.identity(image=r'C:\Tools\other.exe'))
        self.assertFalse(self.identity(info=dict(Created='bad', ExecutablePath=r'C:\Python\pythonw.exe')))
        self.assertFalse(self.identity(info=dict(Created='1234567890', ExecutablePath=r'C:\Other\pythonw.exe')))

    def test_no_pid_guessing_or_self_termination(self):
        for pid in [None, -1, os.getpid()]:
            with self.assertRaises(ValueError):
                updater.VerifiedFolderForgeProcess(pid, self.script)

    def test_healthy_secondary_start_never_shows_dialog_or_terminates(self):
        lock = Mock(lock_dir=self.folder)
        lock.read_owner_pid.return_value = 123
        with patch.object(updater, 'probe_instance', return_value=True), \
             patch.object(updater, 'VerifiedFolderForgeProcess') as process:
            self.assertFalse(updater.recover_unresponsive_instance(lock, self.script))
        process.assert_not_called()
        lock.acquire.assert_not_called()

    def test_terminate_waits_on_verified_handle_not_pid(self):
        process = updater.VerifiedFolderForgeProcess.__new__(updater.VerifiedFolderForgeProcess)
        process.handle = 999
        process.api = Mock()
        process.api.WaitForSingleObject.side_effect = [0x102, 0]
        process.api.TerminateProcess.return_value = True
        process.terminate_and_wait()
        process.api.TerminateProcess.assert_called_once_with(999, 1)
        process.api.WaitForSingleObject.assert_any_call(999, 5000)
        process.close()
        process.api.CloseHandle.assert_called_once_with(999)

    def test_termination_timeout_prevents_starting_replacement(self):
        process = updater.VerifiedFolderForgeProcess.__new__(updater.VerifiedFolderForgeProcess)
        process.handle = 999
        process.api = Mock()
        process.api.WaitForSingleObject.return_value = 0x102
        process.api.TerminateProcess.return_value = True
        with self.assertRaises(TimeoutError):
            process.terminate_and_wait()

    def test_already_exited_handle_does_not_terminate_reused_pid(self):
        process = updater.VerifiedFolderForgeProcess.__new__(updater.VerifiedFolderForgeProcess)
        process.handle = 999
        process.api = Mock()
        process.api.WaitForSingleObject.return_value = 0
        process.terminate_and_wait()
        process.api.TerminateProcess.assert_not_called()

    def recovery_case(self, answers, consent=6, acquired=True, error=None):
        import ctypes
        from types import SimpleNamespace
        dialog = Mock(return_value=consent)
        process = Mock()
        if error:
            process.terminate_and_wait.side_effect = error
        lock = Mock(lock_dir=self.folder, is_primary=acquired)
        lock.read_owner_pid.return_value = 123
        lock.acquire.return_value = acquired
        with patch.object(updater.os, 'name', 'nt'), \
             patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(MessageBoxW=dialog), create=True), \
             patch.object(updater, 'probe_instance', side_effect=answers), \
             patch.object(updater, 'VerifiedFolderForgeProcess', return_value=process), \
             patch.object(updater, 'logger'):
            result = updater.recover_unresponsive_instance(lock, self.script)
        return result, process, lock, dialog

    def test_recovery_requires_explicit_consent_defaulting_to_no(self):
        result, process, lock, dialog = self.recovery_case([False], consent=7)
        self.assertFalse(result)
        process.terminate_and_wait.assert_not_called()
        lock.acquire.assert_not_called()
        self.assertEqual(dialog.call_args.args[3], 0x134)
        process.close.assert_called_once()

    def test_recovered_app_is_not_force_terminated_after_confirmation(self):
        result, process, lock, _ = self.recovery_case([False, True])
        self.assertFalse(result)
        process.terminate_and_wait.assert_not_called()
        lock.acquire.assert_not_called()

    def test_approved_recovery_still_requires_real_lock_acquisition(self):
        result, process, lock, _ = self.recovery_case([False, False])
        self.assertTrue(result)
        process.terminate_and_wait.assert_called_once()
        lock.acquire.assert_called_once()
        process.close.assert_called_once()

    def test_another_start_winning_lock_prevents_duplicate_instance(self):
        result, process, lock, _ = self.recovery_case([False, False], acquired=False)
        self.assertFalse(result)
        lock.acquire.assert_called_once()

    def test_failed_termination_never_starts_new_instance(self):
        result, process, lock, _ = self.recovery_case([False, False], error=TimeoutError('still alive'))
        self.assertFalse(result)
        lock.acquire.assert_not_called()
        process.close.assert_called_once()

    def test_unverifiable_process_is_never_force_terminated(self):
        import ctypes
        from types import SimpleNamespace
        dialog = Mock()
        lock = Mock(lock_dir=self.folder)
        lock.read_owner_pid.return_value = 123
        with patch.object(updater.os, 'name', 'nt'), \
             patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(MessageBoxW=dialog), create=True), \
             patch.object(updater, 'probe_instance', return_value=False), \
             patch.object(updater, 'VerifiedFolderForgeProcess', side_effect=ValueError('wrong script')), \
             patch.object(updater, 'logger'):
            self.assertFalse(updater.recover_unresponsive_instance(lock, self.script))
        lock.acquire.assert_not_called()
        self.assertEqual(dialog.call_count, 1)
        self.assertIn('wrong script', dialog.call_args.args[1])
