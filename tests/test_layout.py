"""Layout contracts without a display server."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))

    def test_footer_has_own_nonexpanding_grid_row(self):
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dialog_layout')
        ctk = SimpleNamespace(CTkScrollableFrame=Mock(), CTkFrame=Mock())
        ns = {'ctk': ctk}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'layout', 'exec'), ns)
        win = Mock()
        body, footer = ns['dialog_layout'](win)
        win.grid_rowconfigure.assert_called_once_with(0, weight=1)
        body.grid.assert_called_once_with(row=0, column=0, sticky='nsew')
        self.assertEqual(footer.grid.call_args.kwargs['row'], 1)
        self.assertEqual(footer.grid.call_args.kwargs['sticky'], 'ew')

    def test_project_actions_follow_final_name_without_footer_gap(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        method = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_create_folder_dialog')
        code = ast.unparse(method)
        self.assertIn('footer.grid_remove()', code)
        self.assertIn("btn_row = ctk.CTkFrame(body, fg_color='transparent')", code)
        self.assertLess(code.index('preview_ram.pack('), code.index('btn_row.pack('))
        self.assertLess(code.index('btn_row.pack('), code.index('skapa_knapp ='))

    def test_dialogs_use_pinned_footer_layout(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        for name in ['_create_folder_dialog', '_create_from_structure_dialog', '_template_dialog',
                     '_show_export_result', '_show_info', '_show_cache_cleanup', '_show_update_status']:
            method = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == name)
            with self.subTest(name=name):
                self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                    and n.func.id == 'dialog_layout' for n in ast.walk(method)))


if __name__ == '__main__':
    unittest.main()
