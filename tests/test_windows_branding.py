"""Windows integration contracts; native execution must be verified on Windows."""
import ast
import logging
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import updater


def app_functions(*names):
    tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
    nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
    nodes += [n for n in app.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(Path=Path, re=re, subprocess=subprocess, sys=sys, logger=logging.getLogger('branding'))
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'branding', 'exec'), ns)
    return ns


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pythonw = self.base / 'Python with spaces/pythonw.exe'
        self.pythonw.parent.mkdir()
        self.pythonw.touch()
        (self.base / 'folder.pyw').write_text('# app')
        self.icon = self.base / 'app.ico'
        self.icon.write_bytes(b'icon')

    def compiler(self, args, **kwargs):
        output = next(arg[5:] for arg in args if arg.startswith('/out:'))
        Path(output).write_bytes(b'MZtest executable')
        return SimpleNamespace(returncode=0)

    def build(self, runner=None):
        return updater.ensure_launcher(self.base, self.pythonw, self.icon,
                                       compiler='csc.exe', runner=runner or self.compiler)

    def test_native_launcher_has_embedded_icon_and_gui_target(self):
        runner = Mock(side_effect=self.compiler)
        exe = self.build(runner)
        self.assertEqual(exe.name, 'FolderForge.exe')
        self.assertIn('/target:winexe', runner.call_args.args[0])
        self.assertIn('/win32icon:' + str(self.icon), runner.call_args.args[0])

    def test_cached_launcher_not_recompiled(self):
        self.build()
        runner = Mock()
        self.build(runner)
        runner.assert_not_called()

    def test_new_icon_rebuilds_launcher(self):
        self.build()
        self.icon.write_bytes(b'new icon')
        runner = Mock(side_effect=self.compiler)
        self.build(runner)
        runner.assert_called_once()

    def test_missing_pythonw_has_no_pyw_fallback(self):
        self.pythonw.unlink()
        with self.assertRaisesRegex(OSError, 'pythonw.exe'):
            self.build()

    def test_failed_build_does_not_register_fake_executable(self):
        with self.assertRaises(OSError):
            self.build(Mock(return_value=SimpleNamespace(returncode=1, stderr='compiler failed')))
        self.assertFalse((self.base / 'data/launcher/FolderForge.exe').exists())

    def test_autostart_uses_native_launcher(self):
        ns = app_functions('build_autostart_command')
        ns.update(IS_WINDOWS=True, BASE_DIR=self.base, APP_ICON=self.icon)
        with patch.object(updater, 'ensure_launcher', return_value=self.base / 'FolderForge.exe'):
            command = ns['build_autostart_command'](['--tray'])
        self.assertTrue(command.endswith('FolderForge.exe" "--tray"'))
        self.assertNotIn('.pyw', command)
        self.assertNotIn('python', command.lower())

    def test_shortcut_preserves_spaces_and_embeds_icon(self):
        ns = app_functions('write_startup_shortcut')
        exe = self.base / 'Folder Forge/FolderForge.exe'
        folder = self.base / 'Startup'
        ps = []
        def runner(args, **kwargs):
            ps.append(args[-1])
            (folder / 'FolderForge.lnk').touch()
            return SimpleNamespace(returncode=0)
        ok, _ = ns['write_startup_shortcut']('FolderForge', f'"{exe}" --tray', folder, runner, self.icon)
        self.assertTrue(ok)
        self.assertIn(f"$s.TargetPath='{exe}';", ps[0])
        self.assertIn("$s.Arguments='--tray';", ps[0])
        self.assertIn(f"$s.IconLocation='{self.icon},0';", ps[0])

    def test_no_generic_bat_fallback(self):
        ns = app_functions('write_startup_shortcut')
        ok, _ = ns['write_startup_shortcut']('FolderForge', '"app.exe" --tray', self.base,
                                           Mock(side_effect=FileNotFoundError()), self.icon)
        self.assertFalse(ok)
        self.assertFalse((self.base / 'FolderForge.bat').exists())

    def test_window_icon_is_default_for_future_dialogs(self):
        ns = app_functions('apply_icon_to_window')
        ns['IS_WINDOWS'] = True
        win = Mock()
        self.assertEqual(ns['apply_icon_to_window'](win, self.icon), 'iconbitmap')
        self.assertEqual(win.iconbitmap.call_args_list[0].kwargs, {'default': str(self.icon)})
        self.assertEqual(win.iconbitmap.call_args_list[1].args, (str(self.icon),))

    def test_icon_reapplied_after_customtkinter_delay(self):
        ns = app_functions('_on_window_mapped')
        root = Mock()
        win = Mock()
        ns.update(tk=SimpleNamespace(Toplevel=Mock), APP_ICON=self.icon, apply_icon_to_window=Mock())
        ns['_on_window_mapped'](root, SimpleNamespace(widget=win))
        self.assertEqual(root.after.call_args.args[0], 350)
        root.after.call_args.args[1]()
        ns['apply_icon_to_window'].assert_called_once_with(win, self.icon)

    def test_source_quotes_paths_and_forwards_selftest(self):
        source = updater.launcher_source(Path('C:/Lisa"s/pythonw.exe'), Path('C:/Folder Forge/folder.pyw'))
        self.assertIn('@"C:/Lisa""s/pythonw.exe"', source)
        self.assertIn('args.Contains("--selftest")', source)
        self.assertIn('info.CreateNoWindow = true', source)
        self.assertIn('return process.ExitCode', source)
