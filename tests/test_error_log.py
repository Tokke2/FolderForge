import ast
import logging
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import logg


class ErrorLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = logging.getLogger()
        self.old_handlers, self.old_level = self.root.handlers[:], self.root.level
        self.root.handlers = []
        self.addCleanup(self.restore_logging)
        for obj, name, value in [(logg, 'LOG_DIR', self.folder),
                                 (logg, 'LEGACY_LOG_DIR', self.folder / 'old-logs'),
                                 (logg, 'LOG_FILE', self.folder / 'folderforge.log'),
                                 (logg, 'ERROR_LOG_FILE', self.folder / 'folderforge-errors.log'),
                                 (logg, '_initierad', False),
                                 (sys, 'stderr', None), (sys, 'excepthook', sys.excepthook),
                                 (threading, 'excepthook', threading.excepthook)]:
            context = patch.object(obj, name, value)
            context.start()
            self.addCleanup(context.stop)

    def restore_logging(self):
        for handler in self.root.handlers[:]:
            handler.close()
        self.root.handlers = self.old_handlers
        self.root.setLevel(self.old_level)

    def read_errors(self):
        return (self.folder / 'folderforge-errors.log').read_text(encoding='utf-8')

    def test_all_module_errors_and_warnings_collected_without_info(self):
        logg.init_logging()
        for name in ['folder', 'historik', 'updater', 'cache_cleanup']:
            logger = logging.getLogger(name)
            logger.info('ordinary ' + name)
            logger.warning('warning ' + name)
            logger.error('error ' + name)
        text = self.read_errors()
        self.assertNotIn('ordinary', text)
        for name in ['folder', 'historik', 'updater', 'cache_cleanup']:
            self.assertIn('warning ' + name, text)
            self.assertIn('error ' + name, text)
            self.assertIn('[' + name + ':', text)
        self.assertIn('ordinary updater', (self.folder / 'folderforge.log').read_text())

    def test_exception_traceback_included(self):
        logg.init_logging()
        try:
            raise ValueError('diagnostic detail')
        except ValueError:
            logging.getLogger('updater').exception('operation failed')
        text = self.read_errors()
        self.assertIn('Traceback (most recent call last)', text)
        self.assertIn('ValueError: diagnostic detail', text)
        self.assertIn('MainThread', text)

    def test_existing_rotated_log_errors_imported_with_multiline_trace(self):
        (self.folder / 'folderforge.log.1').write_text(
            '2026-10-30 10:00:00 INFO    ordinary old message\n'
            '2026-10-30 10:00:01 ERROR   old error\nTraceback old details\n'
            '2026-10-30 10:00:02 DEBUG   not imported\n', encoding='utf-8')
        logg.init_logging()
        text = self.read_errors()
        self.assertIn('folderforge.log.1', text)
        self.assertIn('old error', text)
        self.assertIn('Traceback old details', text)
        self.assertNotIn('ordinary old message', text)
        self.assertNotIn('not imported', text)
        logg.init_logging()
        self.assertEqual(self.read_errors().count('old error'), 1)

    def test_existing_error_log_is_not_reimported(self):
        (self.folder / 'folderforge-errors.log').write_text('already imported\n')
        (self.folder / 'folderforge.log').write_text('2026-10-30 10:00:00 ERROR   historical\n')
        logg.init_logging()
        self.assertNotIn('historical', self.read_errors())

    def test_initialization_does_not_duplicate_records(self):
        logg.init_logging()
        logg.init_logging()
        logging.getLogger('test_error_log').error('unique failure')
        self.assertEqual(self.read_errors().count('unique failure'), 1)

    def test_error_log_works_when_general_log_cannot_open(self):
        (self.folder / 'folderforge.log').mkdir()
        logg.init_logging()
        logging.getLogger('historik').error('still captured')
        self.assertIn('still captured', self.read_errors())

    def test_unresolved_errors_are_never_rotated_away(self):
        logg.init_logging()
        for index in range(150):
            logging.getLogger('retention').error('failure %s %s', index, 'x' * 100)
        self.assertFalse((self.folder / 'folderforge-errors.log.1').exists())
        for index in range(150):
            self.assertIn('failure ' + str(index) + ' ', self.read_errors())

    def test_unhandled_background_thread_exception_is_logged(self):
        logg.init_logging()
        def fail():
            raise RuntimeError('background failure')
        thread = threading.Thread(target=fail, name='error-log-test')
        thread.start()
        thread.join()
        text = self.read_errors()
        self.assertIn('background failure', text)
        self.assertIn('error-log-test', text)

    def test_tk_callback_error_is_logged(self):
        logg.init_logging()
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == 'report_callback_exception')
        nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node]
        namespace = {'logger': logging.getLogger('folder')}
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'callback', 'exec'), namespace)
        namespace['report_callback_exception'](None, ValueError, ValueError('GUI failure'), None)
        self.assertIn('GUI failure', self.read_errors())

    def test_smart_cleanup_preserves_central_error_log(self):
        import cache_cleanup
        base = self.folder
        errors = base / 'logs/folderforge-errors.log'
        errors.parent.mkdir(parents=True)
        errors.write_text('critical history')
        self.assertNotIn(errors, [path for path, _ in cache_cleanup.candidates(base, 9999999999)])

    def test_menu_opens_error_log_in_notepad_without_console(self):
        logg.init_logging()
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_open_error_log')
        nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node]
        namespace = {'ERROR_LOG_FILE': self.folder / 'folderforge-errors.log', 'IS_WINDOWS': True,
                     'subprocess': SimpleNamespace(Popen=Mock(), CREATE_NO_WINDOW=0x8000000),
                     'messagebox': Mock(), 'logger': logging.getLogger('folder')}
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'menu', 'exec'), namespace)
        namespace['_open_error_log'](None)
        namespace['subprocess'].Popen.assert_called_once_with(
            ['notepad.exe', str(self.folder / 'folderforge-errors.log')], creationflags=0x8000000)

    def archive_contents(self):
        return ''.join(p.read_text(encoding='utf-8') for p in (self.folder / 'archive').rglob('*.log'))

    def test_prior_dates_archived_and_today_kept_with_traceback(self):
        from datetime import date
        path = self.folder / 'folderforge.log'
        path.write_text('2026-11-02 09:00:00 INFO    older\n'
                        '2026-11-03 23:59:59 ERROR   prior failure\nTraceback details\nValueError: detail\n'
                        '2026-11-04 00:00:00 INFO    current\n'
                        '2026-11-05 00:00:00 INFO    future clock record\n', encoding='utf-8')
        with patch.object(logg, 'local_today', return_value=date(2026, 11, 4)):
            handler = logg.DailyArchiveHandler(path)
            self.addCleanup(handler.close)
        self.assertNotIn('older', path.read_text())
        self.assertNotIn('prior failure', path.read_text())
        self.assertIn('current', path.read_text())
        self.assertIn('future clock record', path.read_text())
        yesterday = ''.join(p.read_text() for p in (self.folder / 'archive/2026-11-03').glob('*.log'))
        self.assertIn('prior failure\nTraceback details\nValueError: detail\n', yesterday)
        self.assertTrue((self.folder / 'archive/2026-11-02').is_dir())

    def test_midnight_rollover_without_restart(self):
        from datetime import date, datetime
        path = self.folder / 'folderforge.log'
        with patch.object(logg, 'local_today', return_value=date(2026, 11, 3)):
            handler = logg.DailyArchiveHandler(path)
            self.addCleanup(handler.close)
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            record = logging.LogRecord('day', logging.INFO, '', 0, 'before midnight', (), None)
            record.created = datetime(2026, 11, 3, 23, 59, 59).timestamp()
            handler.handle(record)
        with patch.object(logg, 'local_today', return_value=date(2026, 11, 4)):
            record = logging.LogRecord('day', logging.INFO, '', 0, 'after midnight', (), None)
            record.created = datetime(2026, 11, 4, 0, 0, 1).timestamp()
            handler.handle(record)
        self.assertIn('before midnight', self.archive_contents())
        self.assertNotIn('before midnight', path.read_text())
        self.assertIn('after midnight', path.read_text())

    def test_errors_imported_before_old_general_log_is_archived(self):
        (self.folder / 'folderforge.log').write_text('2020-01-01 10:00:00 ERROR   unresolved old issue\n')
        logg.init_logging()
        self.assertIn('unresolved old issue', self.read_errors())
        self.assertIn('unresolved old issue', self.archive_contents())
        self.assertNotIn('unresolved old issue', (self.folder / 'folderforge.log').read_text())

    def test_old_rotated_errors_merge_into_active_error_log(self):
        (self.folder / 'folderforge-errors.log.5').write_text('oldest unresolved\n')
        (self.folder / 'folderforge-errors.log.1').write_text('newer unresolved\n')
        (self.folder / 'folderforge-errors.log').write_text('active unresolved\n')
        logg.init_logging()
        for text in ['oldest unresolved', 'newer unresolved', 'active unresolved']:
            self.assertEqual(self.read_errors().count(text), 1)
        self.assertFalse((self.folder / 'folderforge-errors.log.1').exists())

    def test_resolved_errors_archived_only_after_explicit_action_and_recurrence_kept(self):
        logg.init_logging()
        logging.getLogger('fixed').error('failure to resolve')
        snapshot = logg.error_log_snapshot()
        target = logg.archive_resolved_errors(expected_digest=snapshot)
        self.assertIn('failure to resolve', target.read_text())
        self.assertEqual(self.read_errors(), '')
        self.assertIn('resolved-errors', str(target))
        logging.getLogger('fixed').error('failure to resolve')
        self.assertEqual(self.read_errors().count('failure to resolve'), 1)

    def test_new_error_during_confirmation_prevents_bulk_resolution(self):
        logg.init_logging()
        logging.getLogger('race').error('known error')
        snapshot = logg.error_log_snapshot()
        logging.getLogger('race').error('brand new error')
        with self.assertRaises(ValueError):
            logg.archive_resolved_errors(expected_digest=snapshot)
        self.assertIn('known error', self.read_errors())
        self.assertIn('brand new error', self.read_errors())

    def test_resolved_errors_not_reimported_on_restart(self):
        logg.init_logging()
        logging.getLogger('fixed').error('resolved issue')
        logg.archive_resolved_errors()
        for handler in self.root.handlers:
            handler.close()
        self.root.handlers = []
        logg._initierad = False
        logg.init_logging()
        self.assertNotIn('resolved issue', self.read_errors())

    def test_failed_archive_write_keeps_active_log_intact(self):
        from datetime import date
        path = self.folder / 'folderforge.log'
        original = '2020-01-01 10:00:00 ERROR   retain on failure\ntraceback\n'
        path.write_text(original)
        with patch.object(logg, '_atomic_text', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                logg.DailyArchiveHandler(path)
        self.assertEqual(path.read_text(), original)

    def test_repeated_archive_is_idempotent(self):
        path = self.folder / 'folderforge.log'
        path.write_text('2020-01-01 10:00:00 INFO   archived once\n')
        handler = logg.DailyArchiveHandler(path)
        self.addCleanup(handler.close)
        first = list((self.folder / 'archive').rglob('*.log'))
        handler.archive()
        self.assertEqual(list((self.folder / 'archive').rglob('*.log')), first)
        self.assertEqual(self.archive_contents().count('archived once'), 1)

    def test_empty_error_log_resolution_is_noop(self):
        logg.init_logging()
        self.assertIsNone(logg.archive_resolved_errors())

    def test_cleanup_preserves_daily_archives_and_resolved_errors(self):
        import cache_cleanup
        for relative in ['archive/2020-01-01/old.log', 'resolved-errors/2020-01-01/fixed.log']:
            path = self.folder / 'logs' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('history')
        candidates = [path for path, _ in cache_cleanup.candidates(self.folder, 9999999999)]
        self.assertEqual(candidates, [])

    def test_resolution_ui_requires_confirmation(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_resolve_logged_errors')
        namespace = dict(messagebox=Mock(), logger=logging.getLogger('test'))
        namespace['messagebox'].askyesno.return_value = False
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'resolve', 'exec'), namespace)
        with patch.object(logg, 'archive_resolved_errors') as resolve:
            namespace['_resolve_logged_errors'](object())
        resolve.assert_not_called()

    def test_periodic_archive_handles_idle_midnight(self):
        from datetime import date
        path = self.folder / 'folderforge.log'
        path.write_text('2026-11-03 12:00:00 INFO    idle day\n')
        with patch.object(logg, 'local_today', return_value=date(2026, 11, 3)):
            handler = logg.DailyArchiveHandler(path)
            self.root.addHandler(handler)
            self.addCleanup(handler.close)
        with patch.object(logg, 'local_today', return_value=date(2026, 11, 4)):
            logg.archive_old_logs()
        self.assertNotIn('idle day', path.read_text())
        self.assertIn('idle day', self.archive_contents())

    def test_failed_resolution_move_retains_unresolved_log(self):
        logg.init_logging()
        logging.getLogger('permission').error('must remain unresolved')
        original = self.read_errors()
        with patch.object(logg.os, 'replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                logg.archive_resolved_errors()
        self.assertEqual(self.read_errors(), original)

    def test_windows_shared_lock_is_acquired_and_released(self):
        fake = SimpleNamespace(LK_LOCK=1, LK_UNLCK=0, locking=Mock())
        with patch.dict(sys.modules, {'msvcrt': fake}), patch.object(logg.os, 'name', 'nt'):
            with logg._locked_logs(self.folder):
                pass
        self.assertEqual([call.args[1:] for call in fake.locking.call_args_list], [(1, 1), (0, 1)])

    def test_import_error_reports_exact_python_and_manual_command_without_installing(self):
        import subprocess
        requirements = self.folder / 'requirements.txt'
        requirements.write_text('customtkinter')
        executable = "C:\\Users\\Rickard's folder\\Python314\\pythonw.exe"
        with patch.object(sys, 'executable', executable), patch.object(sys, 'platform', 'win32'), \
             patch.object(subprocess, 'run') as run, patch.object(subprocess, 'Popen') as popen, \
             self.assertLogs(logg._logger, 'ERROR') as captured:
            logg.report_import_failure(ModuleNotFoundError("No module named 'customtkinter'", name='customtkinter'), self.folder)
        text = '\n'.join(captured.output)
        self.assertIn('Python=' + executable, text)
        self.assertIn("Rickard''s folder", text)
        self.assertIn('python.exe', text)
        self.assertIn('-m pip install -r', text)
        self.assertIn('Ingen installation körs', text)
        run.assert_not_called()
        popen.assert_not_called()

    def test_tkinter_failure_is_not_treated_as_a_pip_package(self):
        with self.assertLogs(logg._logger, 'ERROR') as captured:
            logg.report_import_failure(ModuleNotFoundError('missing Tk', name='_tkinter'), self.folder)
        text = '\n'.join(captured.output)
        self.assertIn('Tk-stöd', text)
        self.assertNotIn('-m pip install', text)

    def test_redirected_stderr_does_not_duplicate_errors_or_copy_info(self):
        import io
        redirected = io.StringIO()
        with patch.object(sys, 'stderr', redirected):
            logg.init_logging()
            logging.getLogger('redirected').info('general-only-message')
            logging.getLogger('redirected').warning('single-error-message')
        content = self.read_errors()
        self.assertNotIn('general-only-message', content)
        self.assertEqual(content.count('single-error-message'), 1)
        self.assertEqual(redirected.getvalue(), '')

    def test_multiple_processes_preserve_all_error_records(self):
        import subprocess
        script = """
import logging, sys
from pathlib import Path
import logg
logg.LOG_DIR = Path(sys.argv[1])
logg.LEGACY_LOG_DIR = logg.LOG_DIR / 'unused-old-logs'
logg.LOG_FILE = logg.LOG_DIR / 'folderforge.log'
logg.ERROR_LOG_FILE = logg.LOG_DIR / 'folderforge-errors.log'
sys.stderr = None
logg.init_logging()
for n in range(30):
    logging.getLogger('multi').error('MULTI-%s-%02d-END', sys.argv[2], n)
"""
        children = [subprocess.Popen([sys.executable, '-c', script, str(self.folder), str(index)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in range(3)]
        try:
            for child in children:
                out, err = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, err.decode())
            content = self.read_errors()
            for index in range(3):
                for number in range(30):
                    self.assertEqual(content.count(f'MULTI-{index}-{number:02d}-END'), 1)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()

    def test_old_unresolved_errors_survive_daily_archive(self):
        original = '2020-01-01 12:00:00 ERROR   unresolved across dates\n'
        (self.folder / 'folderforge-errors.log').write_text(original)
        logg.init_logging()
        logg.archive_old_logs()
        self.assertEqual(self.read_errors(), original)

    def test_background_archiver_is_stoppable_and_checks_each_minute(self):
        stop = Mock()
        stop.wait.side_effect = [False, True]
        with patch.object(logg.threading, 'Event', return_value=stop), \
             patch.object(logg.threading, 'Thread') as thread, \
             patch.object(logg, 'archive_old_logs') as archive:
            self.assertIs(logg.start_log_archiver(), stop)
            thread.call_args.kwargs['target']()
        archive.assert_called_once()
        self.assertEqual([call.args for call in stop.wait.call_args_list], [(60,), (60,)])

    def test_shutdown_stops_background_archiving(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_shutdown_background_services')
        ns = dict(logger=logging.getLogger('shutdown-test'))
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'shutdown', 'exec'), ns)
        dummy = SimpleNamespace(_log_archive_stop=Mock(), _cleanup_stop=Mock(), _update_stop=Mock(),
                                _stop_tray_icon=Mock(), global_hotkey=None, hotkey_listener=None, quit=Mock())
        ns['_shutdown_background_services'](dummy)
        dummy._log_archive_stop.set.assert_called_once()
        dummy.quit.assert_called_once()

    def legacy_file(self, name, text):
        path = logg.LEGACY_LOG_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_logs_live_directly_beneath_application_folder(self):
        import settings
        self.assertEqual(settings.LOG_DIR, settings.BASE_DIR / 'logs')

    def test_migration_preserves_errors_and_nested_archives(self):
        old_error = self.legacy_file('folderforge-errors.log', 'unresolved old error\n')
        self.legacy_file('archive/2020-01-01/old.log', 'older archive')
        self.legacy_file('resolved-errors/2020-01-01/fixed.log', 'resolved history')
        logg.migrate_legacy_logs()
        self.assertIn('unresolved old error', self.read_errors())
        self.assertFalse(old_error.exists())
        self.assertEqual((self.folder / 'archive/2020-01-01/old.log').read_text(), 'older archive')
        self.assertEqual((self.folder / 'resolved-errors/2020-01-01/fixed.log').read_text(), 'resolved history')

    def test_migration_merges_existing_native_error_log_without_overwriting(self):
        self.legacy_file('folderforge-errors.log', 'old issue\n')
        (self.folder / 'folderforge-errors.log').write_text('new native issue\n')
        logg.migrate_legacy_logs()
        self.assertEqual(self.read_errors().count('old issue'), 1)
        self.assertEqual(self.read_errors().count('new native issue'), 1)

    def test_migration_conflicting_archive_keeps_both_versions(self):
        self.legacy_file('archive/old.log', 'source archive')
        dest = self.folder / 'archive/old.log'
        dest.parent.mkdir(parents=True)
        dest.write_text('existing archive')
        logg.migrate_legacy_logs()
        self.assertEqual(dest.read_text(), 'existing archive')
        self.assertEqual(next(dest.parent.glob('old.log.migrated-*')).read_text(), 'source archive')

    def test_migration_copy_failure_keeps_original(self):
        source = self.legacy_file('folderforge-errors.log', 'do not lose this')
        with patch.object(logg, '_atomic_bytes', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                logg.migrate_legacy_logs()
        self.assertEqual(source.read_text(), 'do not lose this')

    def test_migration_retry_after_source_removal_failure_is_idempotent(self):
        source = self.legacy_file('folderforge-errors.log', 'old unresolved\n')
        real_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == source:
                raise PermissionError('source temporarily locked')
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            with self.assertRaises(PermissionError):
                logg.migrate_legacy_logs()
        with (self.folder / 'folderforge-errors.log').open('a') as stream:
            stream.write('new unresolved\n')
        logg.migrate_legacy_logs()
        self.assertEqual(self.read_errors().count('old unresolved'), 1)
        self.assertEqual(self.read_errors().count('new unresolved'), 1)
        self.assertFalse(source.exists())

    def test_native_launcher_uses_same_app_log_folder(self):
        import updater
        source = updater.launcher_source(Path('pythonw.exe'), Path('folder.pyw'))
        self.assertIn('Path.Combine(System.IO.Path.GetDirectoryName(', source)
        self.assertNotIn('"data", "logs"', source)
        self.assertIn('"logs"', source)
