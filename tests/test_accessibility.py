"""Display-independent behavioral tests for the actual GUI accessibility helpers."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
import weakref

import settings

SOURCE = Path('folder.pyw').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
NAMES = {'TEXT_SIZES', 'FOCUS_TAG', 'CONTROLS', 'COLOR_KEYS', 'accessibility_logger',
         'text_scale', 'widget_kind', 'contrast_colors', 'AccessibilityController',
         'validate_settings'}
NODES = [n for n in TREE.body if getattr(n, 'name', None) in NAMES or
         isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in NAMES for t in n.targets)]
NS = dict(vars(settings), logging=logging, weakref=weakref, SimpleNamespace=SimpleNamespace,
          tk=SimpleNamespace(TclError=RuntimeError))
exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + NODES,
                                                      type_ignores=[])), 'accessibility_helpers', 'exec'), NS)
Controller = NS['AccessibilityController']


class Widget:
    def __init__(self, parent=None, y=0, state='normal', visible=True, **options):
        self.master = parent
        self.children = []
        if parent:
            parent.children.append(self)
        self.options = dict(state=state, height=28, highlightthickness=0, highlightcolor='gray',
                            highlightbackground='gray', **options)
        self.visible, self.y = visible, y
        self.tags, self.bindings, self.calls = ('widget', 'native-class'), {}, 0
        self.focused = self.grabbed = None
    def cget(self, key):
        if key not in self.options:
            raise RuntimeError('unsupported Tk option')
        return self.options[key]
    def configure(self, **kwargs):
        self.options.update(kwargs)
    def bind(self, sequence, callback, add=None): self.bindings[sequence] = callback
    def bind_all(self, sequence, callback, add=None): self.bind(sequence, callback, add)
    def bind_class(self, tag, sequence, callback, add=None): self.bind(sequence, callback, add)
    def bindtags(self, tags=None):
        if tags is not None: self.tags = tags
        return self.tags
    def winfo_children(self): return self.children
    def winfo_exists(self): return True
    def after(self, milliseconds, callback):
        if not hasattr(self, 'timers'): self.timers = []
        self.timers.append(callback)
    def run_timers(self):
        callbacks, self.timers = getattr(self, 'timers', []), []
        for callback in callbacks: callback()
    def winfo_toplevel(self):
        return self if self.master is None or isinstance(self, CTkToplevel) else self.master.winfo_toplevel()
    def winfo_viewable(self): return self.visible
    def winfo_y(self): return self.y
    def winfo_x(self): return 0
    def winfo_manager(self): return 'pack'
    def winfo_rgb(self, color):
        if not isinstance(color, str) or not color.startswith('#'): raise ValueError()
        return tuple(int(color[i:i+2], 16) * 257 for i in (1, 3, 5))
    def grab_current(self): return self.grabbed
    def focus_get(self): return self.focused
    def focus_set(self): self.winfo_toplevel().focused = self
    def invoke(self): self.calls += 1
    def toggle(self): self.calls += 1
    def _open_dropdown_menu(self): self.calls += 1
    def insert(self, where, value): self.inserted = value


class CTk(Widget): pass
class CTkFrame(Widget): pass
class CTkToplevel(Widget): pass
class CTkButton(Widget): pass
class CTkEntry(Widget): pass
class CTkTextbox(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._textbox = self._x_scrollbar = self._y_scrollbar = object()
class CTkCheckBox(Widget): pass
class CTkRadioButton(Widget): pass
class CTkOptionMenu(Widget): pass
class DropdownMenu(Widget): pass


class AccessibilityTests(unittest.TestCase):
    def setUp(self):
        self.root = CTk(fg_color='#101010')
        self.ctk = SimpleNamespace(get_appearance_mode=lambda: 'Dark')
        self.controller = Controller(self.root, self.ctk)

    def event(self, widget, key='Return'):
        return SimpleNamespace(widget=widget, keysym=key)

    def test_partial_textbox_prevents_parent_redraw_until_construction_finishes(self):
        parent = CTkFrame(self.root, fg_color='#222222')
        box = CTkTextbox(parent)
        del box._x_scrollbar
        self.controller.on_map(self.event(parent))
        self.assertFalse(hasattr(parent, '_ff_accessible_colors'))
        self.root.run_timers()
        self.assertFalse(hasattr(parent, '_ff_accessible_colors'))
        self.assertTrue(getattr(self.root, 'timers', []))
        box._x_scrollbar = object()
        self.root.run_timers()
        self.assertTrue(hasattr(parent, '_ff_accessible_colors'))

    def test_repeated_map_events_are_coalesced_and_destroyed_widgets_ignored(self):
        parent = CTkFrame(self.root, fg_color='#222222')
        self.controller.on_map(self.event(parent))
        self.controller.on_map(self.event(parent))
        self.assertEqual(len(self.root.timers), 1)
        parent.winfo_exists = lambda: False
        self.root.run_timers()
        self.assertFalse(hasattr(parent, '_ff_accessible_colors'))

    def test_refresh_also_defers_incomplete_textbox_subtrees(self):
        parent = CTkFrame(self.root, fg_color='#222222')
        box = CTkTextbox(parent)
        del box._y_scrollbar
        self.controller.prepare(parent)
        self.assertFalse(hasattr(parent, '_ff_accessible_colors'))
        box._y_scrollbar = object()
        self.root.run_timers()
        self.assertTrue(hasattr(parent, '_ff_accessible_colors'))

    def test_missing_x11_keysym_does_not_break_windows_startup(self):
        bind = self.root.bind_class
        def windows_bind(tag, sequence, callback, add=None):
            if sequence == '<ISO_Left_Tab>':
                raise RuntimeError('bad event type or keysym ISO_Left_Tab')
            bind(tag, sequence, callback, add)
        self.root.bind_class = windows_bind
        Controller(self.root, self.ctk)
        self.assertIn('<Shift-Tab>', self.root.bindings)
        self.assertIn('<Tab>', self.root.bindings)

    def test_segmented_button_readable_parent_option_is_not_configured(self):
        class CTkSegmentedButton(CTkFrame):
            def configure(self, **kwargs):
                if 'border_color' in kwargs:
                    raise ValueError('border_color is not supported')
                super().configure(**kwargs)
        segmented = CTkSegmentedButton(self.root, border_color='#888888', fg_color='#222222')
        self.controller.prepare(segmented)
        self.assertNotIn('border_color', segmented._ff_accessible_colors)
        self.controller.high_contrast = True
        self.controller.prepare(segmented)
        self.assertEqual(segmented.cget('fg_color'), '#000000')

    def test_supported_sizes_and_corrupt_value_fallback(self):
        self.assertEqual([NS['text_scale'](s) for s in NS['TEXT_SIZES']], [1, 1.1, 1.25, 1.5])
        for value in ('500%', None, 125, True, [], {}):
            self.assertEqual(NS['text_scale'](value), 1)

    def test_tab_order_tracks_visual_order_not_creation_order(self):
        last = CTkButton(self.root, y=100)
        first = CTkEntry(self.root, y=0)
        self.assertEqual(self.controller.candidates(self.root), [first, last])

    def test_hidden_and_disabled_actions_are_skipped(self):
        CTkButton(self.root, visible=False)
        CTkButton(self.root, state='disabled')
        entry = CTkEntry(self.root)
        self.assertEqual(self.controller.candidates(self.root), [entry])

    def test_read_only_details_remain_keyboard_reachable(self):
        details = CTkTextbox(self.root, state='disabled')
        self.assertIn(details, self.controller.candidates(self.root))

    def test_composite_widget_has_one_tab_stop(self):
        button = CTkButton(self.root)
        Widget(button)
        Widget(button)
        self.assertEqual(self.controller.candidates(self.root), [button])

    def test_focus_moves_forward_and_wraps(self):
        a, b = CTkEntry(self.root, y=0), CTkButton(self.root, y=30)
        self.assertEqual(self.controller.move_focus(self.event(a), 1), 'break')
        self.assertIs(self.root.focused, b)
        self.controller.move_focus(self.event(b), 1)
        self.assertIs(self.root.focused, a)

    def test_shift_tab_moves_backwards_and_wraps(self):
        a, b = CTkEntry(self.root, y=0), CTkButton(self.root, y=30)
        self.controller.move_focus(self.event(a), -1)
        self.assertIs(self.root.focused, b)

    def test_modal_dialog_traps_focus_without_touching_main_window(self):
        main = CTkButton(self.root)
        dialog = CTkToplevel(self.root)
        a, b = CTkEntry(dialog), CTkButton(dialog, y=30)
        self.root.grabbed = dialog
        self.controller.move_focus(self.event(a), 1)
        self.assertIs(dialog.focused, b)
        self.assertIsNone(self.root.focused)
        self.assertNotIn(main, self.controller.candidates(dialog))

    def test_page_subtree_can_supply_its_own_first_control(self):
        page = CTkFrame(self.root)
        entry = CTkEntry(page)
        CTkButton(self.root)
        self.assertEqual(self.controller.candidates(page), [entry])

    def test_button_enter_is_consumed_without_dialog_default_double_action(self):
        button = CTkButton(self.root)
        label = Widget(button)
        self.assertEqual(self.controller.activate(self.event(label)), 'break')
        self.assertEqual(button.calls, 1)

    def test_disabled_actions_are_not_invoked_even_if_previously_focused(self):
        button = CTkButton(self.root, state='disabled')
        self.controller.activate(self.event(button))
        self.assertEqual(button.calls, 0)

    def test_checkbox_and_radio_are_keyboard_activated(self):
        for kind in (CTkCheckBox, CTkRadioButton):
            control = kind(self.root)
            self.assertEqual(self.controller.activate(self.event(control, 'space')), 'break')
            self.assertEqual(control.calls, 1)

    def test_entry_and_textbox_keep_their_return_and_space_behavior(self):
        for kind in (CTkEntry, CTkTextbox):
            control = kind(self.root)
            self.assertIsNone(self.controller.activate(self.event(control)))

    def test_tab_character_can_still_be_inserted_into_template_editor(self):
        box = CTkTextbox(self.root)
        text = Widget(box)
        self.assertEqual(self.controller.insert_tab(self.event(text)), 'break')
        self.assertEqual(text.inserted, '\t')
        self.assertIsNone(self.controller.insert_tab(self.event(CTkEntry(self.root))))

    def test_dropdown_can_be_opened_without_mouse(self):
        dropdown = CTkOptionMenu(self.root)
        self.assertEqual(self.controller.open_choices(self.event(dropdown)), 'break')
        self.assertEqual(dropdown.calls, 1)

    def test_key_bindings_run_before_native_text_tab_insertion(self):
        entry = CTkEntry(self.root)
        native = Widget(entry)
        self.controller.prepare(native)
        self.assertEqual(native.tags[0], NS['FOCUS_TAG'])
        self.assertIn('<ISO_Left_Tab>', self.root.bindings)
        self.assertIn('<Tab>', self.root.bindings)

    def test_focus_highlight_is_visible_and_restores_original_native_options(self):
        entry = CTkEntry(self.root)
        native = Widget(entry)
        self.controller.focus_in(self.event(native))
        self.assertEqual(native.cget('highlightthickness'), 2)
        self.controller.focus_out(None)
        self.assertEqual(native.cget('highlightthickness'), 0)
        self.assertEqual(native.cget('highlightcolor'), 'gray')

    def test_high_contrast_is_reversible(self):
        button = CTkButton(self.root, fg_color='#4488CC', text_color='#EEEEEE', border_width=0)
        self.controller.refresh(True)
        self.assertEqual(button.cget('text_color'), '#FFFFFF')
        self.assertEqual(button.cget('fg_color'), '#003B70')
        self.assertEqual(button.cget('border_width'), 2)
        self.controller.refresh(False)
        self.assertEqual(button.cget('fg_color'), '#4488CC')
        self.assertEqual(button.cget('text_color'), '#EEEEEE')
        self.assertEqual(button.cget('border_width'), 0)

    def test_selection_changes_during_contrast_are_preserved_when_disabled(self):
        button = CTkButton(self.root, fg_color='#222222')
        self.controller.refresh(True)
        button.configure(fg_color='#AA5500')
        self.assertEqual(button.cget('fg_color'), '#003B70')
        self.controller.refresh(False)
        self.assertEqual(button.cget('fg_color'), '#AA5500')

    def test_new_dialog_widgets_get_contrast_and_keyboard_support(self):
        self.controller.refresh(True)
        dialog = CTkToplevel(self.root)
        entry = CTkEntry(dialog, fg_color='#EEEEEE', text_color='#111111')
        self.controller.on_map(self.event(entry))
        self.root.run_timers()
        self.assertEqual(entry.cget('fg_color'), '#000000')
        self.assertEqual(entry.cget('text_color'), '#FFFFFF')
        self.assertIn(NS['FOCUS_TAG'], entry.tags)

    def test_focus_mark_survives_changing_accessibility_options(self):
        entry = CTkEntry(self.root)
        native = Widget(entry)
        self.root.focused = native
        self.controller.focus_in(self.event(native))
        self.controller.refresh(True)
        self.assertEqual(native.cget('highlightthickness'), 2)
        self.assertEqual(native.cget('highlightcolor'), '#FFD54F')

    def test_checked_radio_and_scroll_thumb_remain_visible(self):
        colors = NS['contrast_colors']
        self.assertEqual(colors('CTkRadioButton', {'fg_color': '#123456'})['fg_color'], '#FFFFFF')
        self.assertEqual(colors('CTkScrollbar', {'button_color': '#123456'})['button_color'], '#FFFFFF')

    def test_contrast_text_meets_seven_to_one_on_surfaces_and_buttons(self):
        fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'contrast_ratio')
        dependencies = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in {'_hex_to_rgb', 'relative_luminance'}]
        ns = {}
        exec('from __future__ import annotations\n' + '\n'.join(ast.unparse(n) for n in dependencies + [fn]), ns)
        for foreground, background in [('#FFFFFF', '#000000'), ('#FFFFFF', '#003B70'), ('#BBBBBB', '#000000')]:
            self.assertGreaterEqual(ns['contrast_ratio'](foreground, background), 7)

    def test_invalid_saved_accessibility_values_are_repaired(self):
        clean, repaired, _ = NS['validate_settings']({'text_size': '999%', 'high_contrast': 'yes'})
        self.assertTrue(repaired)
        self.assertEqual(clean['text_size'], '100%')
        self.assertIs(clean['high_contrast'], False)

    def test_settings_round_trip_and_scaling_are_wired_into_app(self):
        appsettings = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'AppSettings')
        ns = dict(NS)
        exec('from dataclasses import dataclass, field, asdict', ns)
        exec(compile(ast.Module(body=[appsettings], type_ignores=[]), 'settings', 'exec'), ns)
        obj = ns['AppSettings'].from_dict({'text_size': '150%', 'high_contrast': True})
        self.assertEqual(obj.to_dict()['text_size'], '150%')
        self.assertTrue(obj.to_dict()['high_contrast'])
        self.assertIn('ctk.set_widget_scaling(text_scale(self.settings.text_size))', SOURCE)
        self.assertIn('self._save_settings_silent()', SOURCE)

    def test_resize_handler_does_not_replace_responsive_sidebar_handler(self):
        self.assertIn('self.bind("<Configure>", self._on_resize, add="+")', SOURCE)
        self.assertIn('self.winfo_width() / text_scale(self.settings.text_size)', SOURCE)

    def test_existing_update_clients_need_no_new_payload_filename(self):
        import updater
        self.assertNotIn('accessibility.py', updater.FILES)
        self.assertNotIn('from accessibility import', SOURCE)

    def test_keyboard_page_switch_is_blocked_in_modal_dialog(self):
        app = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        method = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_keyboard_page')
        ns = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'page_switch', 'exec'), ns)
        fake = SimpleNamespace(grab_current=lambda: object())
        self.assertIsNone(ns['_keyboard_page'](fake, self.event(self.root), 1))

    def test_native_dropdown_menu_keeps_its_own_enter_and_arrow_bindings(self):
        menu = DropdownMenu(CTkOptionMenu(self.root))
        self.controller.prepare(menu)
        self.assertNotIn(NS['FOCUS_TAG'], menu.tags)

    def test_wrapped_button_height_can_shrink_again(self):
        button = CTkButton(self.root)
        label = SimpleNamespace(configure=lambda **kwargs: None, winfo_reqheight=lambda: 60)
        button._text_label = label
        button._get_widget_scaling = lambda: 1
        button.winfo_width = lambda: 150
        self.controller.prepare(button)
        self.controller.wrap_button(button)
        self.assertEqual(button.cget('height'), 72)
        label.winfo_reqheight = lambda: 14
        self.controller.wrap_button(button)
        self.assertEqual(button.cget('height'), 28)

    def test_navigation_remains_scrollable_in_short_windows(self):
        self.assertIn('self._nav_scroll = ctk.CTkScrollableFrame(', SOURCE)
        self.assertIn('self._nav_scroll if self._layout == "sidebar" else self._tab_bar', SOURCE)

    def test_scrollable_frame_uses_parent_palette_without_losing_original_colors(self):
        class CTkScrollableFrame(Widget):
            def __init__(self, parent):
                super().__init__(parent)
                self._parent_frame = parent
            def configure(self, **kwargs):
                self._parent_frame.configure(**kwargs)
                self.painted = self._parent_frame.cget('fg_color')
        parent = CTkFrame(self.root, fg_color='#EEEEEE')
        scroll = CTkScrollableFrame(parent)
        self.controller.refresh(True)
        self.assertEqual(scroll.painted, '#000000')
        self.controller.refresh(False)
        self.assertEqual(scroll.painted, '#EEEEEE')
        self.assertEqual(parent.cget('fg_color'), '#EEEEEE')

    def test_modified_keys_and_hotkey_recording_do_not_activate_focused_button(self):
        button = CTkButton(self.root)
        event = self.event(button)
        event.state = 4
        self.assertIsNone(self.controller.activate(event))
        event.state = 0
        self.root.recording_hotkey = True
        self.assertIsNone(self.controller.activate(event))
        self.assertEqual(button.calls, 0)

    def test_page_keys_scroll_container_but_preserve_text_editor_behavior(self):
        class CTkScrollableFrame(Widget): pass
        from unittest.mock import Mock
        scroll = CTkScrollableFrame(self.root)
        scroll._parent_canvas = SimpleNamespace(yview_scroll=Mock())
        button, editor = CTkButton(scroll), CTkTextbox(scroll)
        self.assertEqual(self.controller.scroll_page(self.event(button), 1), 'break')
        scroll._parent_canvas.yview_scroll.assert_called_once_with(1, 'pages')
        self.assertIsNone(self.controller.scroll_page(self.event(editor), 1))

    def menu_fixture(self):
        class Menu(Widget): pass
        menu = Menu(self.root, font='font-name', background='#EEEEEE', foreground='#111111',
                    activebackground='#224466', activeforeground='#EEEEEE', disabledforeground='#888888')
        fakefont = SimpleNamespace(Font=lambda **kwargs: SimpleNamespace(
            actual=lambda: dict(family='Segoe UI', size=12, weight='normal')))
        from unittest.mock import patch
        return menu, patch.dict('sys.modules', {'tkinter': SimpleNamespace(font=fakefont)})

    def test_native_menu_color_aliases_preserve_theme_changes_during_contrast(self):
        menu, patcher = self.menu_fixture()
        with patcher:
            self.controller.style_menu(menu)
            self.controller.high_contrast = True
            self.controller.style_menu(menu)
            menu.configure(bg='#FFFFFE', fg='#000001')
            self.assertEqual(menu.cget('background'), '#000000')
            self.controller.high_contrast = False
            self.controller.style_menu(menu)
            self.assertEqual(menu.cget('background'), '#FFFFFE')
            self.assertEqual(menu.cget('foreground'), '#000001')

    def test_native_menu_font_scales_without_compounding(self):
        menu, patcher = self.menu_fixture()
        with patcher:
            self.controller.size = '150%'
            self.controller.style_menu(menu)
            self.assertEqual(menu.cget('font')[1], 18)
            self.controller.style_menu(menu)
            self.assertEqual(menu.cget('font')[1], 18)
            self.controller.size = '100%'
            self.controller.style_menu(menu)
            self.assertEqual(menu.cget('font')[1], 12)

    def test_header_theme_choice_updates_saved_setting_variable(self):
        from unittest.mock import Mock
        app = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        method = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_toggle_theme')
        ns = {'ctk': SimpleNamespace(get_appearance_mode=lambda: 'Dark', set_appearance_mode=Mock())}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'theme', 'exec'), ns)
        fake = SimpleNamespace(settings=SimpleNamespace(theme='Dark'), theme_var=Mock(),
                               _apply_menu_theme=Mock(), _theme_btn=Mock(), _save_settings_silent=Mock())
        ns['_toggle_theme'](fake)
        fake.theme_var.set.assert_called_once_with('Light')
        self.assertEqual(fake.settings.theme, 'Light')

    def test_checkbox_caption_wraps_without_consuming_checkmark_space(self):
        from unittest.mock import Mock
        control = CTkCheckBox(self.root)
        control.winfo_width = lambda: 220
        control._canvas = SimpleNamespace(winfo_width=lambda: 30)
        control._get_widget_scaling = lambda: 1.5
        control._text_label = SimpleNamespace(configure=Mock())
        self.controller.wrap_toggle(control)
        control._text_label.configure.assert_called_once_with(wraplength=175)
