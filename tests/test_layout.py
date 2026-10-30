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

    def test_manual_update_available_in_app_and_tray(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        code = ast.unparse(app)
        self.assertIn("label='Sök uppdatering nu'", code)
        self.assertIn("text='Sök uppdatering nu'", code)
        tray = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_minimize_to_systray')
        self.assertIn("'Sök uppdatering nu'", ast.unparse(tray))
        self.assertIn('ui_call(self, self._check_updates_now)', ast.unparse(tray))

    def test_main_window_has_visible_manual_update_button(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        method = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_create_gui')
        code = ast.unparse(method)
        self.assertIn('self._update_check_button = ctk.CTkButton(self,', code)
        self.assertIn("text='Sök uppdatering nu'", code)
        self.assertIn('command=self._check_updates_now', code)
        self.assertIn("self._update_check_button.pack(fill='x'", code)

    def test_initial_layout_hides_empty_status_and_undo_rows(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        create = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_create_gui')
        code = ast.unparse(create)
        self.assertIn('self._result_banner.pack_forget()', code)
        self.assertIn('self._undo_bar.pack_forget()', code)

    def test_update_view_has_progress_notes_and_error_log_access(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        view = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_show_update_status')
        code = ast.unparse(view)
        self.assertIn('ctk.CTkProgressBar(', code)
        self.assertIn('ctk.CTkTextbox(', code)
        self.assertIn('command=self._open_error_log', code)
        self.assertIn("state='disabled' if busy else 'normal'", code)

    def test_creation_screen_uses_two_distinct_cards(self):
        app = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        view = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_build_tab_skapa')
        code = ast.unparse(view)
        self.assertIn('Använd din standardmall', code)
        self.assertIn('Egen struktur', code)
        self.assertIn('corner_radius=14', code)
        self.assertIn('self._default_template_label', code)

    def test_primary_action_and_muted_text_have_readable_contrast(self):
        import settings
        def luminance(color):
            values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
            return sum(v * w for v, w in zip(values, (0.2126, 0.7152, 0.0722)))
        def contrast(a, b):
            lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
            return (lighter + 0.05) / (darker + 0.05)
        for primary in settings.UI_PRIMARY:
            self.assertGreaterEqual(contrast(primary, '#FFFFFF'), 4.5)
        for index in (0, 1):
            self.assertGreaterEqual(contrast(settings.UI_MUTED[index], settings.UI_SURFACE[index]), 4.5)

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
