import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import settings
import updater


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def console_function(self):
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'relaunch_without_console')
        ns = {'IS_WINDOWS': True, 'sys': SimpleNamespace(executable=str(self.base / 'python.exe'),
              argv=['folder.pyw'], frozen=False), 'Path': Path, 'BASE_DIR': self.base,
              '__file__': str(self.base / 'folder.pyw'), 'logger': Mock(),
              'ctypes': SimpleNamespace(windll=SimpleNamespace(kernel32=Mock())),
              'shutil': SimpleNamespace(which=Mock(return_value=None)),
              'subprocess': SimpleNamespace(Popen=Mock(), CREATE_NO_WINDOW=0x8000000, DETACHED_PROCESS=8)}
        nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node]
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'startup', 'exec'), ns)
        return ns

    def test_console_relaunch_is_detached_and_windowless(self):
        (self.base / 'pythonw.exe').touch()
        ns = self.console_function()
        self.assertTrue(ns['relaunch_without_console']())
        ns['ctypes'].windll.kernel32.FreeConsole.assert_called_once()
        self.assertEqual(ns['subprocess'].Popen.call_args.kwargs['creationflags'], 0x8000008)
        self.assertEqual(ns['subprocess'].Popen.call_args.args[0][0], str(self.base / 'pythonw.exe'))

    def test_missing_windowless_interpreter_aborts(self):
        ns = self.console_function()
        with self.assertRaises(SystemExit):
            ns['relaunch_without_console']()
        ns['subprocess'].Popen.assert_not_called()

    def test_failed_windowless_relaunch_aborts(self):
        (self.base / 'pythonw.exe').touch()
        ns = self.console_function()
        ns['subprocess'].Popen.side_effect = OSError('failed')
        with self.assertRaises(SystemExit):
            ns['relaunch_without_console']()

    def test_selftest_keeps_diagnostic_output(self):
        ns = self.console_function()
        ns['sys'].argv.append('--selftest')
        self.assertFalse(ns['relaunch_without_console']())
        ns['ctypes'].windll.kernel32.FreeConsole.assert_not_called()

    def test_legacy_start_visible_setting_is_repaired(self):
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_settings')
        ns = vars(settings).copy()
        ns['Path'] = Path
        nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node]
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'startup', 'exec'), ns)
        result, repaired, _ = ns['validate_settings']({'start_minimized': False})
        self.assertTrue(result['start_minimized'])
        self.assertTrue(repaired)

    def test_constructor_unconditionally_withdraws(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        init = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        direct = [ast.unparse(n) for n in init.body]
        self.assertIn('self.withdraw()', direct)
        self.assertIn('self.after_idle(self._minimize_to_systray)', direct)
        self.assertLess(direct.index('self.withdraw()'), direct.index('self.update_idletasks()'))

    def test_launcher_enforces_tray_and_never_creates_console(self):
        source = updater.launcher_source(Path('pythonw.exe'), Path('folder.pyw'))
        self.assertIn('args.Concat(new[] { "--tray" })', source)
        self.assertIn('info.CreateNoWindow = true', source)
        self.assertIn('info.UseShellExecute = false', source)

    def test_second_start_does_not_restore_hidden_window(self):
        entry = ast.unparse(self.tree)
        self.assertNotIn('_instance_lock.request_focus()', entry)
        self.assertIn('_start_minimerad = True', entry)
