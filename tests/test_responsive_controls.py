"""Shared control rows adapt without a display server."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class ResponsiveControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        cls.node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'adapt_control_row')

    def helper(self):
        ns = {}
        exec(compile(ast.Module(body=[self.node], type_ignores=[]), 'controls', 'exec'), ns)
        return ns['adapt_control_row']

    def row(self, width, scale=1):
        frame = Mock()
        frame._ff_responsive_row = False
        frame.winfo_width.return_value = width
        frame._get_widget_scaling.return_value = scale
        frame.winfo_exists.return_value = True
        font = Mock()
        font.measure.return_value = 100
        controls = [Mock() for _ in range(3)]
        for control in controls:
            control.winfo_manager.return_value = 'pack'
            control.cget.side_effect = lambda key: font if key == 'font' else 'Action'
        frame.winfo_children.return_value = controls
        return frame, controls

    def test_all_controls_reflow_at_each_width_and_scaling(self):
        for width, scale, columns in ((700, 1, 3), (350, 1, 2), (160, 1, 1), (700, 2, 2)):
            with self.subTest(width=width, scale=scale):
                frame, controls = self.row(width, scale)
                self.helper()(frame)
                frame.after.call_args.args[1]()
                for index, control in enumerate(controls):
                    control.grid.assert_called_once_with(row=index // columns, column=index % columns,
                                                         sticky='ew', padx=4, pady=4)

    def test_existing_grid_is_not_replaced(self):
        frame, controls = self.row(700)
        controls[0].winfo_manager.return_value = 'grid'
        self.helper()(frame)
        frame.bind.assert_not_called()

    def test_identical_layout_does_not_reconfigure_controls(self):
        frame, controls = self.row(700)
        helper = self.helper()
        helper(frame)
        frame.after.call_args.args[1]()
        frame.bind.call_args.args[1](SimpleNamespace(widget=frame))
        frame.after.call_args.args[1]()
        helper(frame)
        for control in controls:
            control.grid.assert_called_once()
        frame.bind.assert_called_once()

    def test_descendant_events_do_not_schedule_reflow(self):
        frame, _controls = self.row(700)
        self.helper()(frame)
        frame.after.call_args.args[1]()
        frame.after.reset_mock()
        frame.bind.call_args.args[1](SimpleNamespace(widget=object()))
        frame.after.assert_not_called()
