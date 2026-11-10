"""Display-independent checks for remembered, screen-bounded geometry."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class PlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        cls.app = next(n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')

    def method(self, name, **ns):
        node = next(n for n in self.app.body if isinstance(n, ast.FunctionDef) and n.name == name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'placement', 'exec'), ns)
        return ns[name]

    def test_restore_disconnected_monitor_and_scale(self):
        app = Mock()
        app._get_window_scaling.return_value = 2
        app._scale = 1
        monitor = SimpleNamespace(left=40, top=0, width=1240, height=720)
        restore = self.method('_restore_window_placement',
                              read_json_safe=lambda *args: [-1920, 0, 1800, 1000],
                              DATA_DIR=Path('data'), enumerate_monitors=lambda: [monitor],
                              pick_monitor_for_point=lambda *args: monitor,
                              clamp_window_into_monitor=lambda x, y, w, h, m: (40, 0),
                              scaled=lambda value, scale: value)
        restore(app)
        app.geometry.assert_called_once_with('604x328+40+0')

    def test_invalid_saved_geometry_is_ignored(self):
        for value in (None, {}, [1, 2], [0, 0, -1, 700], [0, 0, True, 700]):
            app = Mock()
            self.method('_restore_window_placement', read_json_safe=lambda *args: value,
                        DATA_DIR=Path('data'))(app)
            app.geometry.assert_not_called()

    def test_hidden_or_maximized_window_does_not_overwrite_normal_size(self):
        for state, visible in (('withdrawn', False), ('normal', False), ('zoomed', True)):
            app, write = Mock(), Mock()
            app.state.return_value = state
            app.winfo_viewable.return_value = visible
            self.method('_remember_window_placement', atomic_write_json=write, DATA_DIR=Path('data'))(app)
            write.assert_not_called()

    def test_visible_window_is_saved_in_physical_pixels(self):
        app, write = Mock(), Mock()
        app.state.return_value = 'normal'
        app.winfo_viewable.return_value = True
        for key, value in dict(x=-1200, y=40, width=900, height=650).items():
            getattr(app, 'winfo_' + key).return_value = value
        self.method('_remember_window_placement', atomic_write_json=write, DATA_DIR=Path('data'))(app)
        write.assert_called_once_with(Path('data/window-placement.json'), [-1200, 40, 900, 650])

    def test_windows_work_area_and_responsive_page_contracts(self):
        monitors = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'enumerate_monitors')
        code = ast.unparse(monitors)
        self.assertIn('GetMonitorInfoW', code)
        self.assertIn('info.rcWork', code)
        for name in ('_build_tab_exportera', '_build_tab_mallar', '_build_tab_hotkey'):
            method = next(n for n in self.app.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertIn('CTkScrollableFrame', ast.unparse(method))
