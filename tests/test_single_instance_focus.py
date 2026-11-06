"""Lock, startup-race and branding regressions, without a GUI display."""
import ast
import atexit
import ctypes
import os
from pathlib import Path
import re
import struct
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import updater


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SingleInstanceLock')
        self.ns = dict(Path=Path, os=os, re=re, tempfile=tempfile, time=time,
                       ctypes=ctypes, atexit=Mock(), logger=Mock(), IS_WINDOWS=(os.name == 'nt'),
                       DEFAULT_POLL_MS=1000, BASE_DIR=self.folder, _pid_alive=lambda pid: pid == os.getpid())
        nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node]
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'lock', 'exec'), self.ns)
        self.Lock = self.ns['SingleInstanceLock']

    def test_only_one_primary_and_second_start_can_request_its_window(self):
        primary, secondary = self.Lock('FolderForge', self.folder), self.Lock('FolderForge', self.folder)
        self.addCleanup(primary.release)
        self.addCleanup(secondary.release)
        self.assertTrue(primary.acquire())
        self.assertFalse(secondary.acquire())
        self.assertFalse(secondary.is_primary)
        self.assertTrue(secondary.request_focus())
        self.assertTrue(primary.check_trigger())
        self.assertFalse(primary.check_trigger())

    def test_request_received_during_gui_initialization_is_not_lost(self):
        lock = self.Lock('FolderForge', self.folder)
        lock._is_primary = True
        lock.request_focus()
        root, restore = Mock(), Mock()
        with patch.object(updater, 'service_instance_health'):
            self.assertTrue(lock.poll_start(root, restore))
            tick = root.after.call_args.args[1]
            tick()
            restore.assert_called_once()
            tick()
            restore.assert_called_once()

    def test_old_trigger_does_not_open_a_fresh_first_start(self):
        (self.folder / 'folderforge_show.trigger').write_text('old request')
        lock = self.Lock('FolderForge', self.folder)
        self.assertFalse(lock.check_trigger())

    def test_inaccessible_lock_folder_never_allows_unlocked_start(self):
        lock = self.Lock('FolderForge', self.folder)
        lock.lock_dir = Mock()
        lock.lock_dir.mkdir.side_effect = PermissionError('denied')
        self.assertFalse(lock.acquire())
        self.assertFalse(lock.is_primary)

    def test_windows_mutex_failure_never_falls_back_to_racy_pid_file(self):
        self.ns['IS_WINDOWS'] = True
        lock = self.Lock('FolderForge', self.folder)
        lock._acquire_win32 = Mock(side_effect=OSError('unavailable'))
        lock._acquire_pidfile = Mock()
        self.assertFalse(lock.acquire())
        lock._acquire_pidfile.assert_not_called()

    def test_healthy_existing_instance_stays_minimized_without_termination(self):
        lock = Mock(lock_dir=self.folder)
        lock.read_owner_pid.return_value = os.getpid()
        with patch.object(updater, 'probe_instance', return_value=True), \
             patch.object(updater, 'VerifiedFolderForgeProcess') as verified:
            self.assertFalse(updater.recover_unresponsive_instance(lock, self.folder / 'folder.pyw'))
        lock.request_focus.assert_not_called()
        lock.acquire.assert_not_called()
        verified.assert_not_called()

    def test_failed_restore_request_does_not_create_second_instance(self):
        lock = Mock(lock_dir=self.folder)
        lock.read_owner_pid.return_value = os.getpid()
        lock.request_focus.return_value = False
        with patch.object(updater, 'probe_instance', return_value=True):
            self.assertFalse(updater.recover_unresponsive_instance(lock, self.folder / 'folder.pyw'))
        lock.acquire.assert_not_called()

    def test_icon_has_all_windows_sizes_and_matching_png_assets(self):
        data = Path('Icon/projektmapp.ico').read_bytes()
        reserved, kind, count = struct.unpack_from('<HHH', data)
        self.assertEqual((reserved, kind), (0, 1))
        sizes = set()
        for index in range(count):
            width, height = struct.unpack_from('<BB', data, 6 + index * 16)
            sizes.add((width or 256, height or 256))
        self.assertTrue({(n, n) for n in (16, 24, 32, 48, 64, 128, 256)}.issubset(sizes))
        png = Path('Icon/projektmapp_icon_256.png').read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack_from('>II', png, 16), (256, 256))
        self.assertEqual(png, Path('Icon/projektmapp_icon (1).png').read_bytes())
