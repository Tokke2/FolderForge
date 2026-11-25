import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import logg


def issue(identity, module='updater', level='ERROR', count=1):
    return dict(id=identity, module=module, level=level, count=count, message='failure ' + identity,
                text='Traceback detail ' + identity, first='2026-11-04 10:00:00', last='2026-11-04 12:00:00')


class Variable:
    def __init__(self, value=''):
        self.value, self.callbacks = value, []
    def get(self):
        return self.value
    def set(self, value):
        self.value = value
        for callback in self.callbacks:
            callback()
    def trace_add(self, _, callback):
        self.callbacks.append(callback)


class Widget:
    def __init__(self, parent=None, kind='', **kwargs):
        self.kind, self.parent, self.options = kind, parent, kwargs
        self.children, self.jobs, self.bindings = [], {}, {}
        self.text, self.inserts, self.closed = '', 0, False
        self._parent_canvas = SimpleNamespace(yview=lambda: (0.4, 1), yview_moveto=Mock())
        if isinstance(parent, Widget):
            parent.children.append(self)
    def pack(self, **_):
        pass
    def configure(self, **kwargs):
        self.options.update(kwargs)
    def winfo_children(self):
        return self.children[:]
    def destroy(self):
        self.closed = True
        if isinstance(self.parent, Widget):
            self.parent.children.remove(self)
        if '<Destroy>' in self.bindings:
            self.bindings['<Destroy>'](SimpleNamespace(widget=self))
    def delete(self, *_):
        self.text = ''
    def insert(self, _, text):
        self.text += text
        self.inserts += 1
    def after(self, milliseconds, callback):
        identity = str(len(self.jobs) + 1)
        self.jobs[identity] = callback
        return identity
    def after_cancel(self, identity):
        self.jobs.pop(identity, None)
    def bind(self, name, callback, **_):
        self.bindings[name] = callback
    def protocol(self, name, callback):
        self.bindings[name] = callback
    def title(self, *_):
        pass
    def geometry(self, *_):
        pass
    def transient(self, *_):
        pass
    def update_idletasks(self):
        pass
    def invoke(self):
        self.options['command']()


class IssueFilterTests(unittest.TestCase):
    def test_level_module_and_text_filters_combine(self):
        items = [issue('A'), issue('B', 'gui', 'WARNING'), issue('C', 'gui', 'CRITICAL')]
        self.assertEqual([i['id'] for i in logg.filter_error_issues(items, level='Fel')], ['A', 'C'])
        self.assertEqual([i['id'] for i in logg.filter_error_issues(items, 'DETAIL b', 'Varningar', 'gui')], ['B'])
        self.assertEqual(logg.filter_error_issues(items, 'missing'), [])
        self.assertEqual([i['id'] for i in logg.filter_error_issues(items, level='Kritiska')], ['C'])

    def setUp(self):
        self.widgets = []
        def factory(kind):
            def create(parent=None, **kwargs):
                widget = Widget(parent, kind, **kwargs)
                self.widgets.append(widget)
                return widget
            return create
        ctk = SimpleNamespace(StringVar=Variable)
        for name in ['CTkToplevel', 'CTkLabel', 'CTkEntry', 'CTkFrame', 'CTkOptionMenu', 'CTkScrollableFrame', 'CTkTextbox', 'CTkButton']:
            setattr(ctk, name, factory(name))
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_show_error_issues')
        self.ns = dict(ctk=ctk, adapt_control_row=Mock(), apply_icon_to_window=Mock(), APP_ICON=Path('icon'),
                       UI_PRIMARY='primary', UI_BACKGROUND='background', UI_TEXT='text', UI_BORDER='border',
                       messagebox=Mock(), dialog_layout=lambda win: (Widget(win), Widget(win)))
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'issues', 'exec'), self.ns)
        self.source = Mock(return_value=([issue('A'), issue('B', 'gui', 'WARNING')], 'snapshot-1'))
        self.resolve = Mock()
        for name, value in [('get_error_issues', self.source), ('resolve_error_issue', self.resolve)]:
            context = patch.object(logg, name, value)
            context.start()
            self.addCleanup(context.stop)
        self.ns['_show_error_issues'](SimpleNamespace(_export_diagnostics=Mock()))
        self.win = self.widgets[0]
        self.details = next(w for w in self.widgets if w.kind == 'CTkTextbox')

    def button(self, text):
        return next(w for w in reversed(self.widgets) if not w.closed and text in w.options.get('text', ''))

    def tick(self):
        key = next(iter(self.win.jobs))
        self.win.jobs.pop(key)()

    def test_auto_refresh_retains_selection_and_highlight(self):
        self.button('failure A').invoke()
        self.source.return_value = ([issue('A', count=2), issue('B', 'gui', 'WARNING')], 'snapshot-2')
        self.tick()
        self.assertIn('Antal: 2', self.details.text)
        self.assertEqual(self.button('failure A').options['fg_color'], 'primary')
        self.assertEqual(self.button('Markera valt').options['state'], 'normal')

    def test_unchanged_refresh_preserves_selected_text_and_does_not_rebuild(self):
        button = self.button('failure A')
        button.invoke()
        inserts = self.details.inserts
        self.tick()
        self.assertIs(self.button('failure A'), button)
        self.assertEqual(self.details.inserts, inserts)

    def test_search_keeps_selected_visible_issue_and_clears_hidden_selection(self):
        self.button('failure A').invoke()
        variable = next(w for w in self.widgets if w.kind == 'CTkEntry').options['textvariable']
        variable.set('failure A')
        self.assertEqual(self.button('failure A').options['fg_color'], 'primary')
        variable.set('failure B')
        self.assertEqual(self.details.text, '')
        self.assertEqual(self.button('Markera valt').options['state'], 'disabled')

    def test_background_refresh_paused_during_resolution_confirmation(self):
        self.button('failure A').invoke()
        def confirm(*args, **kwargs):
            self.source.return_value = ([issue('A', count=2)], 'snapshot-2')
            self.tick()
            return True
        self.ns['messagebox'].askyesno.side_effect = confirm
        self.button('Markera valt').invoke()
        self.resolve.assert_called_once_with('A', 'snapshot-1')

    def test_destroy_cancels_refresh_timer(self):
        self.assertTrue(self.win.jobs)
        self.button('Stäng').invoke()
        self.assertTrue(self.win.closed)
        self.assertFalse(self.win.jobs)

    def test_auto_read_failure_is_quiet_and_retries_next_tick(self):
        self.source.side_effect = OSError('temporarily locked')
        self.tick()
        self.ns['messagebox'].showerror.assert_not_called()
        self.source.side_effect = None
        self.tick()
        self.assertTrue(self.win.jobs)
