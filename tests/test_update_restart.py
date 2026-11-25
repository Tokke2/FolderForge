import ast
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import updater
from test_updater import archive, COMMIT


class Dialog:
    def winfo_exists(self):
        return True


class UpdateRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pending = self.base / 'data/update-pending'
        self.pending.mkdir(parents=True)
        updater.unpack(archive(), self.pending)
        updater.write_state(self.base, {'pending': 'v0.0.2', 'pending_revision': 'a' * 40,
                                       'pending_hashes': updater.content_manifest(self.pending)})
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_restart_after_update')
        ns = dict(BASE_DIR=self.base, logger=logging.getLogger('restart-test'), tk=SimpleNamespace(Toplevel=Dialog))
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'restart', 'exec'), ns)
        self.restart = ns['_restart_after_update']
        self.app = SimpleNamespace(_restart_requested=False, _active_exports=0, _update_status_window=None,
                                   grab_current=Mock(return_value=None), winfo_children=Mock(return_value=[]),
                                   _save_settings_silent=Mock(), _shutdown_background_services=Mock())

    def test_verified_update_requests_restart_and_saves_settings(self):
        self.assertTrue(self.restart(self.app))
        self.assertTrue(self.app._restart_requested)
        self.app._save_settings_silent.assert_called_once()
        self.app._shutdown_background_services.assert_called_once()

    def test_corrupted_update_does_not_restart(self):
        (self.pending / 'folder.pyw').write_text('# corrupt')
        self.assertFalse(self.restart(self.app))
        self.app._shutdown_background_services.assert_not_called()

    def test_active_download_does_not_restart(self):
        with updater._check_lock:
            self.assertFalse(self.restart(self.app))

    def test_modal_input_waits_until_closed(self):
        self.app.grab_current.return_value = Dialog()
        self.assertFalse(self.restart(self.app))
        self.app.grab_current.return_value = None
        self.assertTrue(self.restart(self.app))

    def test_nonmodal_project_dialog_also_defers_restart(self):
        self.app.winfo_children.return_value = [Dialog()]
        self.assertFalse(self.restart(self.app))

    def test_status_dialog_does_not_block_restart(self):
        dialog = Dialog()
        self.app._update_status_window = dialog
        self.app.winfo_children.return_value = [dialog]
        self.assertTrue(self.restart(self.app))

    def test_active_export_defers_restart(self):
        self.app._active_exports = 1
        self.assertFalse(self.restart(self.app))

    def test_restart_requested_only_once(self):
        self.restart(self.app)
        self.restart(self.app)
        self.app._shutdown_background_services.assert_called_once()

    def test_install_failure_blocks_restart_loop(self):
        updater.mark_installation_failed(self.base, OSError('locked'))
        self.assertFalse(updater.pending_ready_for_restart(self.base))
        self.assertIn('pausad', updater.get_update_status(self.base, '0.0.2')['Status'])

    def test_manual_retry_clears_restart_block(self):
        updater.mark_installation_failed(self.base, OSError('locked'))
        release = b'{"tag_name": "v0.0.2"}'
        with patch.object(updater, 'fetch', side_effect=[release, COMMIT]):
            updater.check_once(self.base, '0.0.2', force=True)
        self.assertTrue(updater.pending_ready_for_restart(self.base))

    def test_native_dialog_lookup_failure_defers_without_losing_poll(self):
        self.app.grab_current.side_effect = KeyError('native dialog')
        self.assertFalse(self.restart(self.app))
        self.assertFalse(self.app._restart_requested)

    def test_successful_install_after_failure_clears_block(self):
        updater.mark_installation_failed(self.base, OSError('locked'))
        self.assertTrue(updater.apply_pending(self.base))
        state = updater.read_state(self.base)
        self.assertNotIn('restart_blocked', state)
        self.assertNotIn('installation_error', state)
        self.assertEqual(state['status'], 'checked')

    def test_hotkey_recording_defers_restart(self):
        self.app.recording_hotkey = True
        self.assertFalse(self.restart(self.app))

    def test_relaunch_is_after_mainloop_finally_and_minimized(self):
        source = Path('folder.pyw').read_text(encoding='utf-8')
        tail = source[source.index('        app.mainloop()'):]
        self.assertLess(tail.index('_instance_lock.release()'), tail.index('os.execv('))
        self.assertIn('"--tray"', tail)
        self.assertNotIn('shell=True', tail)
