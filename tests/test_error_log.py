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

    def test_rotating_error_log_keeps_archives(self):
        with patch.object(logg, '_FEL_STORLEK', 180):
            logg.init_logging()
        for index in range(15):
            logging.getLogger('rotation').error('failure %s %s', index, 'x' * 100)
        self.assertTrue((self.folder / 'folderforge-errors.log.1').exists())
        self.assertIn('failure 14', self.read_errors())

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
        errors = base / 'data/logs/folderforge-errors.log'
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
