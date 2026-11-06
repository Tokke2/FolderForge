"""Startup acknowledgement and rollback protect only the app, not user files."""
import os
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import updater
from test_updater import archive


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for name in updater.FILES:
            (self.base / name).write_text('# previous application\n')
        self.data = self.base / 'data'
        self.data.mkdir()
        (self.data / 'settings.json').write_text('important settings')
        (self.data / 'history.json').write_text('important history')
        self.project = self.base / 'Projects'
        self.project.mkdir()
        (self.project / 'work.txt').write_text('never touch')
        interpreter_patch = patch.object(updater, '_windowless_interpreter', side_effect=lambda p: Path(p))
        interpreter_patch.start()
        self.addCleanup(interpreter_patch.stop)
        self.stage()

    def stage(self):
        pending = self.data / 'update-pending'
        pending.mkdir(exist_ok=True)
        updater.unpack(archive(), pending)
        updater.write_state(self.base, dict(installed='v0.0.1', installed_revision='old', pending='v0.0.2',
                           pending_hashes=updater.content_manifest(pending)))

    def install(self):
        self.assertTrue(updater.apply_pending(self.base))
        return updater.read_transaction(self.base)

    def test_successful_copy_is_not_yet_successful_start(self):
        journal = self.install()
        self.assertEqual(journal['phase'], 'installing')
        self.assertTrue(updater.read_state(self.base)['startup_pending'])
        self.assertEqual((self.data / 'update-backup/folder.pyw').read_text(), '# previous application\n')
        self.assertTrue((self.data / 'update-supervisor.py').is_file())
        compile((self.data / 'update-supervisor.py').read_text(), 'supervisor', 'exec')

    def test_valid_live_trial_can_acknowledge_start(self):
        journal = self.install()
        journal['trial_pid'] = os.getpid()
        updater._write_transaction(self.base, journal)
        with patch.dict(os.environ, FOLDERFORGE_UPDATE_TOKEN=journal['token']):
            self.assertTrue(updater.confirm_startup(self.base))
        self.assertEqual(updater.read_transaction(self.base)['phase'], 'confirmed')
        self.assertFalse(updater.read_state(self.base)['startup_pending'])
        self.assertTrue((self.data / 'update-backup/folder.pyw').exists())

    def test_another_process_or_stale_token_cannot_confirm(self):
        journal = self.install()
        journal['trial_pid'] = os.getpid() + 100
        updater._write_transaction(self.base, journal)
        with patch.dict(os.environ, FOLDERFORGE_UPDATE_TOKEN=journal['token']):
            self.assertFalse(updater.confirm_startup(self.base))
        journal['trial_pid'] = os.getpid()
        updater._write_transaction(self.base, journal)
        with patch.dict(os.environ, FOLDERFORGE_UPDATE_TOKEN='wrong'):
            self.assertFalse(updater.confirm_startup(self.base))

    def test_modified_candidate_cannot_confirm(self):
        journal = self.install()
        journal['trial_pid'] = os.getpid()
        updater._write_transaction(self.base, journal)
        (self.base / 'folder.pyw').write_text('# tampered')
        with patch.dict(os.environ, FOLDERFORGE_UPDATE_TOKEN=journal['token']):
            with self.assertRaises(ValueError):
                updater.confirm_startup(self.base)

    def test_rollback_restores_previous_app_and_leaves_user_data(self):
        self.install()
        self.assertTrue(updater.rollback_update(self.base))
        for name in updater.FILES:
            self.assertEqual((self.base / name).read_text(), '# previous application\n')
        self.assertEqual((self.data / 'settings.json').read_text(), 'important settings')
        self.assertEqual((self.data / 'history.json').read_text(), 'important history')
        self.assertEqual((self.project / 'work.txt').read_text(), 'never touch')
        self.assertEqual(updater.read_state(self.base)['installed'], 'v0.0.1')
        self.assertTrue(updater.read_state(self.base)['restart_blocked'])

    def test_corrupted_backup_aborts_before_any_restore(self):
        self.install()
        (self.data / 'update-backup/settings.py').write_text('# damaged')
        with self.assertRaises(ValueError):
            updater.rollback_update(self.base)
        self.assertEqual((self.base / 'folder.pyw').read_text(), '# new release\n')
        self.assertIsNotNone(updater.read_transaction(self.base))

    def test_journal_cannot_target_settings_or_projects(self):
        journal = self.install()
        for name in ['data/settings.json', '../escape.py', 'Projects/work.txt', '/absolute.py']:
            journal['files'] = {name: None}
            updater._write_transaction(self.base, journal)
            with self.assertRaises(ValueError):
                updater.rollback_update(self.base)
        self.assertEqual((self.data / 'settings.json').read_text(), 'important settings')

    def test_next_update_does_not_replace_unconfirmed_backup(self):
        journal = self.install()
        self.stage()
        with self.assertRaises(RuntimeError):
            updater.apply_pending(self.base)
        self.assertEqual(updater.read_transaction(self.base)['token'], journal['token'])
        self.assertEqual((self.data / 'update-backup/settings.py').read_text(), '# previous application\n')

    def test_no_network_check_until_candidate_is_acknowledged(self):
        self.install()
        with patch.object(updater, 'fetch') as fetch:
            self.assertFalse(updater.check_once(self.base, 'v0.0.2', force=True))
        fetch.assert_not_called()

    def test_failed_trial_offers_rollback_without_forced_termination(self):
        self.install()
        child = Mock(pid=123)
        child.poll.return_value = 1
        offer = Mock(return_value=True)
        with patch.object(updater, '_app_mutex_exists', return_value=False), \
             patch.object(updater.subprocess, 'Popen', return_value=child) as spawn:
            self.assertEqual(updater.supervise_update(self.base, Path('pythonw.exe'), offer=offer), 1)
        offer.assert_called_once()
        child.terminate.assert_not_called()
        child.kill.assert_not_called()
        self.assertEqual(spawn.call_count, 2)
        self.assertFalse((self.data / 'update-transaction.json').exists())

    def test_declining_rollback_retains_all_backups(self):
        self.install()
        child = Mock(pid=123)
        child.poll.return_value = 1
        with patch.object(updater, '_app_mutex_exists', return_value=False), \
             patch.object(updater.subprocess, 'Popen', return_value=child):
            updater.supervise_update(self.base, Path('pythonw.exe'), offer=lambda _: False)
        self.assertTrue((self.data / 'update-backup/settings.py').exists())
        self.assertIsNotNone(updater.read_transaction(self.base))

    def test_slow_live_trial_is_not_killed_or_rolled_back(self):
        self.install()
        child = Mock(pid=123)
        child.poll.return_value = None
        offer = Mock()
        with patch.object(updater, '_app_mutex_exists', return_value=False), \
             patch.object(updater.subprocess, 'Popen', return_value=child):
            self.assertEqual(updater.supervise_update(self.base, Path('pythonw.exe'), timeout=0, offer=offer), 2)
        offer.assert_not_called()
        child.terminate.assert_not_called()
        self.assertIsNotNone(updater.read_transaction(self.base))

    def test_running_app_is_never_rolled_back_underneath(self):
        self.install()
        offer = Mock(return_value=True)
        with patch.object(updater, '_app_mutex_exists', return_value=True), patch.object(updater.subprocess, 'Popen') as spawn:
            updater.supervise_update(self.base, Path('pythonw.exe'), recover=True, offer=offer)
        offer.assert_not_called()
        spawn.assert_not_called()

    def test_tk_acknowledgement_retries_until_supervisor_publishes_pid(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_confirm_update_start')
        ns = dict(os=os, BASE_DIR=self.base, logger=Mock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'tk-confirm', 'exec'), ns)
        app = Mock()
        app.winfo_exists.return_value = True
        app.systray_icon.visible = True
        with patch.dict(os.environ, FOLDERFORGE_UPDATE_TOKEN='trial'), \
             patch.object(updater, 'confirm_startup', return_value=False):
            ns['_confirm_update_start'](app)
        app.after.assert_called_once_with(250, app._confirm_update_start)
        app.after.reset_mock()
        with patch.dict(os.environ, FOLDERFORGE_UPDATE_TOKEN='trial'), \
             patch.object(updater, 'confirm_startup', return_value=True):
            ns['_confirm_update_start'](app)
        app.after.assert_not_called()

    def test_direct_rollback_refuses_a_running_app(self):
        self.install()
        with patch.object(updater, '_app_mutex_exists', return_value=True):
            with self.assertRaises(RuntimeError):
                updater.rollback_update(self.base)
        self.assertEqual((self.base / 'folder.pyw').read_text(), '# new release\n')
        self.assertIsNotNone(updater.read_transaction(self.base))

    def test_update_and_rollback_discard_only_app_bytecode(self):
        cache = self.base / '__pycache__'
        cache.mkdir()
        ours = cache / 'settings.cpython-313.pyc'
        other = cache / 'unrelated.cpython-313.pyc'
        ours.write_bytes(b'old cached code')
        other.write_bytes(b'not our module')
        self.install()
        self.assertFalse(ours.exists())
        ours.write_bytes(b'candidate cached code')
        updater.rollback_update(self.base)
        self.assertFalse(ours.exists())
        self.assertEqual(other.read_bytes(), b'not our module')

    def test_recovery_guards_are_in_both_windowless_launchers(self):
        ps = updater.RUNTIME_BOOTSTRAP_FILES['Starta-FolderForge.ps1']
        self.assertIn('update-transaction.json', ps)
        self.assertIn("@('--recover',$Root,$Windowless)", ps)
        native = updater.launcher_source(Path('pythonw.exe'), Path('folder.pyw'))
        self.assertIn('update-supervisor.py', native)
        self.assertIn(' --recover ', native)
        self.assertIn('info.CreateNoWindow = true', native)
