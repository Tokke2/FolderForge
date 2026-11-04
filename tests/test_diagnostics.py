import ast
import json
import logging
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import logg


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.logs = self.base / 'logs'
        self.logs.mkdir()
        self.errors = self.logs / 'folderforge-errors.log'
        for name, value in [('LOG_DIR', self.logs), ('LOG_FILE', self.logs / 'folderforge.log'),
                            ('ERROR_LOG_FILE', self.errors), ('_debug_until', 0)]:
            context = patch.object(logg, name, value)
            context.start()
            self.addCleanup(context.stop)

    def write(self, message, module='app', level='ERROR', day='2026-11-04', detail=''):
        with self.errors.open('a', encoding='utf-8', newline='') as stream:
            stream.write(f'{day} 12:00:00 {level} [{module}:42] [MainThread] {message}\n' + detail)

    def test_identical_errors_grouped_with_count_first_and_last(self):
        self.write('same', day='2026-11-02')
        self.write('same')
        self.write('different')
        issues, _ = logg.get_error_issues()
        self.assertEqual(len(issues), 2)
        same = next(i for i in issues if i['message'] == 'same')
        self.assertEqual(same['count'], 2)
        self.assertEqual(same['first'], '2026-11-02 12:00:00')
        self.assertEqual(same['last'], '2026-11-04 12:00:00')

    def test_modules_and_exception_details_not_conflated(self):
        self.write('failure', module='a')
        self.write('failure', module='b')
        self.write('callback', detail='Traceback (most recent call last):\nValueError: bad\n')
        self.write('callback', detail='Traceback (most recent call last):\nOSError: bad\n')
        self.assertEqual(len(logg.get_error_issues()[0]), 4)

    def test_resolve_selected_group_preserves_others_and_recurrence_reopens(self):
        self.write('selected')
        self.write('selected')
        self.write('keep')
        issues, snapshot = logg.get_error_issues()
        selected = next(i for i in issues if i['message'] == 'selected')
        archive = logg.resolve_error_issue(selected['id'], snapshot)
        self.assertEqual(archive.read_text().count('selected'), 2)
        self.assertNotIn('selected', self.errors.read_text())
        self.assertIn('keep', self.errors.read_text())
        self.write('selected')
        active = next(i for i in logg.get_error_issues()[0] if i['id'] == selected['id'])
        self.assertEqual(active['count'], 1)

    def test_stale_snapshot_cannot_resolve_new_occurrences(self):
        self.write('old')
        issues, snapshot = logg.get_error_issues()
        self.write('new')
        with self.assertRaises(ValueError):
            logg.resolve_error_issue(issues[0]['id'], snapshot)
        self.assertIn('old', self.errors.read_text())
        self.assertIn('new', self.errors.read_text())

    def test_windows_crlf_snapshot_can_resolve(self):
        self.errors.write_bytes(b'2026-11-04 12:00:00 ERROR [app:1] [MainThread] windows\r\n')
        issues, snapshot = logg.get_error_issues()
        logg.resolve_error_issue(issues[0]['id'], snapshot)
        self.assertEqual(self.errors.read_bytes(), b'')

    def test_archive_failure_retains_active_errors(self):
        self.write('keep')
        issues, snapshot = logg.get_error_issues()
        with patch.object(logg, '_atomic_text', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                logg.resolve_error_issue(issues[0]['id'], snapshot)
        self.assertIn('keep', self.errors.read_text())

    def test_historical_import_wrapper_not_counted_as_an_extra_issue(self):
        self.errors.write_text('2026-11-04 10:00:00 WARNING [tidigare_logg:0] [MainThread] Tidigare poster:\n'
                               '2026-11-02 12:00:00 WARNING [app:10] [MainThread] same\n')
        self.write('same', level='WARNING')
        issues, _ = logg.get_error_issues()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['count'], 2)

    def test_empty_error_list(self):
        self.assertEqual(logg.get_error_issues()[0], [])

    def test_pillow_noise_hidden_normally_but_warnings_preserved(self):
        filt = logg.LibraryNoiseFilter()
        def record(name, level):
            return logging.LogRecord(name, level, '', 0, 'message', (), None)
        self.assertFalse(filt.filter(record('PIL.Image', logging.DEBUG)))
        self.assertTrue(filt.filter(record('PIL.Image', logging.WARNING)))
        self.assertTrue(filt.filter(record('updater', logging.DEBUG)))
        with patch('time.monotonic', return_value=100):
            logg.enable_detailed_logging(15)
            self.assertTrue(filt.filter(record('PIL.Image', logging.DEBUG)))
        with patch('time.monotonic', return_value=1001):
            self.assertFalse(filt.filter(record('PIL.Image', logging.DEBUG)))

    def test_export_contains_only_logs_and_diagnostics_not_project_or_settings(self):
        self.write('diagnostic error')
        (self.base / 'settings.json').write_text('private settings')
        (self.logs / 'settings.json').write_text('not a log')
        target = self.base / 'package.zip'
        with patch('updater.get_update_status', return_value={'Status': 'test'}):
            logg.export_diagnostic_package(target)
        with zipfile.ZipFile(target) as package:
            self.assertEqual(set(package.namelist()), {'logs/folderforge-errors.log', 'diagnostic.json', 'LAS-MIG.txt'})
            self.assertIn(b'diagnostic error', package.read('logs/folderforge-errors.log'))
            self.assertEqual(json.loads(package.read('diagnostic.json'))['update']['Status'], 'test')

    def test_export_bounds_large_logs_and_reports_truncation(self):
        self.errors.write_bytes(b'x' * (3 * 1024 * 1024))
        target = self.base / 'package.zip'
        with patch('updater.get_update_status', return_value={}):
            logg.export_diagnostic_package(target)
        with zipfile.ZipFile(target) as package:
            self.assertEqual(len(package.read('logs/folderforge-errors.log')), 2 * 1024 * 1024)
            self.assertTrue(json.loads(package.read('diagnostic.json'))['files'][0]['truncated'])

    def test_export_cannot_overwrite_log_with_zip(self):
        self.write('keep')
        with self.assertRaises(ValueError):
            logg.export_diagnostic_package(self.errors)
        self.assertIn('keep', self.errors.read_text())

    def test_export_skips_log_symlink_to_private_file(self):
        private = self.base / 'private.log'
        private.write_text('private content')
        (self.logs / 'folderforge.log').symlink_to(private)
        target = self.base / 'package.zip'
        with patch('updater.get_update_status', return_value={}):
            logg.export_diagnostic_package(target)
        with zipfile.ZipFile(target) as package:
            self.assertNotIn('logs/folderforge.log', package.namelist())

    def test_export_failure_preserves_previous_zip(self):
        target = self.base / 'package.zip'
        target.write_bytes(b'previous package')
        with patch('updater.get_update_status', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                logg.export_diagnostic_package(target)
        self.assertEqual(target.read_bytes(), b'previous package')
        self.assertFalse(list(self.base.glob('.diagnostic-*')))


    def test_native_launcher_error_has_identifiable_module(self):
        self.errors.write_text('2026-11-04 12:00:00 ERROR [launcher] process failed\n')
        issues, _ = logg.get_error_issues()
        self.assertEqual(issues[0]['module'], 'launcher')

    def test_resolved_error_is_safe_if_active_rewrite_fails(self):
        self.write('preserve')
        issues, snapshot = logg.get_error_issues()
        atomic = logg._atomic_text
        def write(path, text):
            if path == self.errors:
                raise OSError('active log locked')
            atomic(path, text)
        with patch.object(logg, '_atomic_text', side_effect=write):
            with self.assertRaises(OSError):
                logg.resolve_error_issue(issues[0]['id'], snapshot)
        self.assertIn('preserve', self.errors.read_text())
        self.assertIn('preserve', next((self.logs / 'resolved-errors').rglob('*.log')).read_text())

    def test_export_privacy_decline_does_not_open_save_dialog(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_export_diagnostics')
        ns = dict(messagebox=SimpleNamespace(askyesno=Mock(return_value=False)), filedialog=Mock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'export', 'exec'), ns)
        with patch.object(logg, 'export_diagnostic_package') as export:
            ns['_export_diagnostics'](object())
        export.assert_not_called()
        ns['filedialog'].asksaveasfilename.assert_not_called()

    def test_diagnostic_ui_exposes_group_count_dates_and_confirmation(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_show_error_issues')
        code = ast.unparse(node)
        for token in ['get_error_issues()', "issue['count']", "issue['first']", "issue['last']",
                      'messagebox.askyesno', 'resolve_error_issue', 'dialog_layout(win)']:
            self.assertIn(token, code)


class HotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        names = {'normalize_hotkey_keys', 'validate_hotkey_combo', 'hotkey_expression', 'hotkey_label'}
        nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                nodes.append(node)
        cls.ns = dict(re=re, HOTKEY_MODIFIERS={'ctrl', 'alt', 'shift', 'cmd', 'win'}, HOTKEY_MAX_KEYS=5,
                      HOTKEY_KEY_ORDER={'ctrl': 0, 'alt': 1, 'shift': 2, 'cmd': 3})
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'hotkeys', 'exec'), cls.ns)
        cls.app_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')

    def test_letter_not_wrapped_in_angles(self):
        self.assertEqual(self.ns['hotkey_expression'](['ctrl', 'alt', 'm']), '<ctrl>+<alt>+m')

    def test_special_keys_wrapped_and_windows_modifier_normalized(self):
        self.assertEqual(self.ns['hotkey_expression'](['win', 'f5']), '<cmd>+<f5>')

    def test_ctrl_character_from_pynput_recording_becomes_letter(self):
        ok, keys, _ = self.ns['validate_hotkey_combo'](['ctrl', '\r'])
        self.assertTrue(ok)
        self.assertEqual(keys, ['ctrl', 'm'])

    def test_plain_letter_or_unknown_key_rejected(self):
        for combo in [['m'], ['ctrl'], ['ctrl', '<m>'], ['ctrl', 'unknown key'], ['ctrl', '+']]:
            with self.subTest(combo=combo):
                self.assertFalse(self.ns['validate_hotkey_combo'](combo)[0])

    def test_standard_combo_is_accepted(self):
        self.assertTrue(self.ns['validate_hotkey_combo'](['ctrl', 'alt', 'm'])[0])

    def test_recording_cancel_clears_restart_guard(self):
        node = next(n for n in self.app_node.body if isinstance(n, ast.FunctionDef) and n.name == '_cancel_hotkey_rec')
        ns = dict(scaled=lambda x, s: x)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'cancel', 'exec'), ns)
        app = SimpleNamespace(recording_hotkey=True, hotkey_listener=None, hk_rec_frame=Mock(),
                              hk_display_frame=Mock(), _scale=1, _update_ui_from_settings=Mock())
        ns['_cancel_hotkey_rec'](app)
        self.assertFalse(app.recording_hotkey)

    def test_backend_validation_happens_before_save_and_failed_save_keeps_old_combo(self):
        node = next(n for n in self.app_node.body if isinstance(n, ast.FunctionDef) and n.name == '_save_hotkey_rec')
        ns = dict(self.ns, keyboard=SimpleNamespace(HotKey=SimpleNamespace(parse=Mock())),
                  atomic_write_json=Mock(return_value=False), HOTKEY_CONFIG=Path('hotkey.json'),
                  logger=logging.getLogger('test'), messagebox=Mock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'save', 'exec'), ns)
        app = SimpleNamespace(pressed_keys_for_recording={'ctrl', 'm'}, hotkey_listener=None,
                              current_hotkey={'alt', 'x'}, _cancel_hotkey_rec=Mock(), _setup_global_hotkey=Mock())
        ns['_save_hotkey_rec'](app)
        self.assertEqual(app.current_hotkey, {'alt', 'x'})
        app._setup_global_hotkey.assert_not_called()
        ns['keyboard'].HotKey.parse.assert_called_once_with('<ctrl>+m')

    def test_invalid_backend_expression_is_not_saved(self):
        node = next(n for n in self.app_node.body if isinstance(n, ast.FunctionDef) and n.name == '_save_hotkey_rec')
        ns = dict(self.ns, keyboard=SimpleNamespace(HotKey=SimpleNamespace(parse=Mock(side_effect=ValueError('bad')))),
                  atomic_write_json=Mock(), logger=logging.getLogger('test'), messagebox=Mock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'save', 'exec'), ns)
        app = SimpleNamespace(pressed_keys_for_recording={'ctrl', 'm'}, hotkey_listener=None, _cancel_hotkey_rec=Mock())
        ns['_save_hotkey_rec'](app)
        ns['atomic_write_json'].assert_not_called()
