import ast
import json
import os
from pathlib import Path
import plistlib
import shlex
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import updater
from tools.create_shortcut import create_shortcut


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        (self.base / 'Icon').mkdir()
        (self.base / 'Icon/folderforge.icns').write_bytes(b'icns')
        (self.base / 'folder.pyw').write_text('# GUI')

    @unittest.skipIf(os.name == 'nt', 'POSIX launch contract')
    def test_detached_launch_redirects_streams_without_shell(self):
        with patch.object(updater.subprocess, 'Popen') as spawn:
            updater.launch_portable(self.base, Path(sys.executable))
        args, kwargs = spawn.call_args
        self.assertEqual(args[0][-1], '--tray')
        self.assertEqual(args[0][1], str(self.base / 'folder.pyw'))
        self.assertTrue(kwargs['start_new_session'])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['stdout'], updater.subprocess.DEVNULL)

    @unittest.skipIf(os.name == 'nt', 'POSIX launch contract')
    def test_existing_transaction_routes_through_preserved_supervisor(self):
        (self.base / 'data').mkdir()
        (self.base / 'data/update-transaction.json').write_text('{}')
        with self.assertRaises(OSError):
            updater.launch_portable(self.base)
        (self.base / 'data/update-supervisor.py').write_text('# stable')
        with patch.object(updater.subprocess, 'Popen') as spawn:
            updater.launch_portable(self.base)
        self.assertIn('--recover', spawn.call_args.args[0])

    def test_optional_portable_files_do_not_break_older_manifests(self):
        for name in updater.FILES:
            (self.base / name).write_text('# app')
        manifest = updater.content_manifest(self.base)
        self.assertTrue(updater.matches_manifest(self.base, manifest))
        for name in updater.OPTIONAL_FILES:
            (self.base / name).write_text('# optional')
        self.assertTrue(updater.matches_manifest(self.base, manifest))
        new_manifest = updater.content_manifest(self.base)
        self.assertTrue(updater.OPTIONAL_FILES.issubset(new_manifest))
        self.assertTrue(updater.matches_manifest(self.base, new_manifest))

    def test_linux_shortcut_is_terminal_free_and_quotes_paths(self):
        base = self.base / 'Lisa\'s folder %test'
        base.mkdir()
        target = create_shortcut(base, Path(sys.executable), 'linux')
        text = target.read_text(encoding='utf-8')
        self.assertIn('Terminal=false', text)
        self.assertIn('%%test', text)
        self.assertIn('Icon=' + str(base / 'Icon/projektmapp_icon_256.png').replace('\\', '\\\\'), text)
        self.assertNotIn('sh -c', text)
        self.assertIn('Exec="', text)

    def test_macos_bundle_has_matching_icon_and_quoted_executable(self):
        target = create_shortcut(self.base, Path(sys.executable), 'darwin')
        with (target / 'Contents/Info.plist').open('rb') as stream:
            info = plistlib.load(stream)
        self.assertEqual(info['CFBundleIconFile'], 'folderforge.icns')
        executable = target / 'Contents/MacOS/FolderForge'
        args = shlex.split(executable.read_text().split('exec ', 1)[1])
        self.assertEqual(args, [str(Path(sys.executable).resolve()), str(self.base / 'Starta-FolderForge.py')])
        self.assertTrue((target / 'Contents/Resources/folderforge.icns').exists())

    def test_unsupported_shortcut_does_not_silently_create_windows_console(self):
        with self.assertRaises(ValueError):
            create_shortcut(self.base, Path(sys.executable), 'win32')

    @unittest.skipIf(os.name == 'nt', 'POSIX real flock')
    def test_real_posix_app_lock_blocks_rollback(self):
        import fcntl
        (self.base / 'FolderForge').mkdir()
        path = self.base / 'FolderForge/folderforge.lock'
        with patch.dict(os.environ, XDG_RUNTIME_DIR=str(self.base)):
            with path.open('a+b') as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(updater._app_mutex_exists())
            self.assertFalse(updater._app_mutex_exists())

    def test_portable_tray_integrates_cocoa_main_loop(self):
        source = Path('folder.pyw').read_text(encoding='utf-8')
        self.assertIn('self.systray_icon.run_detached()', source)
        self.assertIn("elif sys.platform == 'darwin':", source)
        self.assertIn('if sys.platform == "darwin":', source)
        self.assertIn("threading.Thread(target=self.systray_icon.run, daemon=True).start()", source)


if __name__ == '__main__':
    unittest.main()
