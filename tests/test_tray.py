import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        cls.app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        nodes = [n for n in cls.app.body if isinstance(n, ast.FunctionDef) and n.name in
                 {'_on_window_unmap', '_send_iconic_window_to_tray'}]
        cls.ns = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'tray_methods', 'exec'), cls.ns)

    def test_iconic_window_sent_to_tray(self):
        app = Mock()
        app.state.return_value = 'iconic'
        self.ns['_send_iconic_window_to_tray'](app)
        app._minimize_to_systray.assert_called_once()

    def test_withdrawn_or_restored_window_not_minimized_again(self):
        for state in ['withdrawn', 'normal', 'zoomed']:
            app = Mock()
            app.state.return_value = state
            self.ns['_send_iconic_window_to_tray'](app)
            app._minimize_to_systray.assert_not_called()

    def test_destroyed_window_ignored(self):
        app = Mock()
        app.winfo_exists.return_value = False
        self.ns['_send_iconic_window_to_tray'](app)
        app.state.assert_not_called()
        app._minimize_to_systray.assert_not_called()

    def test_child_events_ignored(self):
        app = Mock()
        self.ns['_on_window_unmap'](app, SimpleNamespace(widget=object()))
        app.after_idle.assert_not_called()

    def test_main_window_event_deferred(self):
        app = Mock()
        self.ns['_on_window_unmap'](app, SimpleNamespace(widget=app))
        app.after_idle.assert_called_once_with(app._send_iconic_window_to_tray)

    def test_close_and_minimize_bindings(self):
        init = next(n for n in self.app.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        code = ast.unparse(init)
        self.assertIn("self.protocol('WM_DELETE_WINDOW', self._minimize_to_systray)", code)
        self.assertIn("self.bind('<Unmap>', self._on_window_unmap, add='+')", code)


if __name__ == '__main__':
    unittest.main()
