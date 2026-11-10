"""Top navigation wraps without hiding configured-visible tabs."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class TopTabsTests(unittest.TestCase):
    def test_grid_wraps_and_keeps_all_visible_tabs(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and any(isinstance(m, ast.FunctionDef) and m.name == '_rebuild_tab_bar' for m in n.body))
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_rebuild_tab_bar')
        for width, columns in ((1000, 6), (500, 3), (260, 1)):
            with self.subTest(width=width):
                font = Mock()
                font.measure.return_value = 100
                buttons = {str(i): Mock() for i in range(6)}
                for button in buttons.values():
                    button.cget.return_value = font
                bar = Mock()
                bar.winfo_width.return_value = width
                bar._get_widget_scaling.return_value = 1
                view = SimpleNamespace(_layout='tabs', _tab_bar=bar, _tab_buttons=buttons,
                                       _scale=1, _settings=SimpleNamespace(visible_tabs={}))
                ns = dict(scaled=lambda value, scale: value)
                exec(compile(ast.Module(body=[method], type_ignores=[]), 'tabs', 'exec'), ns)
                ns['_rebuild_tab_bar'](view)
                for index, button in enumerate(buttons.values()):
                    self.assertEqual(button.grid.call_args.kwargs['row'], index // columns)
                    self.assertEqual(button.grid.call_args.kwargs['column'], index % columns)
                ns['_rebuild_tab_bar'](view)
                for button in buttons.values():
                    self.assertEqual(button.grid.call_count, 1)

    def test_app_selects_top_tabs(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        create = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_create_gui')
        self.assertIn("layout='tabs'", ast.unparse(create))

