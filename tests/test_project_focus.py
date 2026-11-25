"""Initial project-name focus must survive mapping without stealing later focus."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class ProjectFocusTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'focus_project_name')
        self.ns = {'tk': SimpleNamespace(TclError=RuntimeError)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'focus', 'exec'), self.ns)
        self.entry = Mock()
        self.entry._ff_initial_focus_done = False
        self.entry.winfo_exists.return_value = True
        self.entry.winfo_viewable.return_value = True
        self.window = self.entry.winfo_toplevel.return_value
        self.window.focus_get.return_value = None

    def test_visible_field_activates_and_selects_all_once(self):
        self.ns['focus_project_name'](self.entry)
        self.ns['focus_project_name'](self.entry)
        self.entry.focus_force.assert_called_once()
        self.entry.select_range.assert_called_once_with(0, 'end')
        self.entry.icursor.assert_called_once_with('end')

    def test_waits_until_dialog_is_visible(self):
        self.entry.winfo_viewable.return_value = False
        self.ns['focus_project_name'](self.entry)
        self.entry.focus_force.assert_not_called()
        self.entry.winfo_viewable.return_value = True
        self.entry.after.call_args.args[1]()
        self.entry.focus_force.assert_called_once()

    def test_does_not_override_another_chosen_dialog_field(self):
        other = Mock()
        other.winfo_toplevel.return_value = self.window
        self.window.focus_get.return_value = other
        self.ns['focus_project_name'](self.entry)
        self.entry.focus_force.assert_not_called()
        self.entry.select_range.assert_not_called()

    def test_closed_dialog_is_ignored_and_retries_are_bounded(self):
        self.entry.winfo_exists.return_value = False
        self.ns['focus_project_name'](self.entry)
        self.entry.after.assert_not_called()
        self.entry.winfo_exists.return_value = True
        self.entry.winfo_viewable.return_value = False
        self.ns['focus_project_name'](self.entry, attempts=0)
        self.entry.after.assert_not_called()
