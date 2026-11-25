"""Tray asset is shipped, tracked by updates and separate from the wordmark."""
from pathlib import Path
import struct
import unittest
import updater


class TrayBadgeTests(unittest.TestCase):
    def test_tray_badge_is_a_small_rgba_png_in_update_manifest(self):
        path = Path('Icon/folderforge-tray.png')
        content = path.read_bytes()
        self.assertEqual(content[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', content[16:24]), (64, 64))
        self.assertEqual(content[25], 6)  # RGBA, transparent rounded corners.
        self.assertIn(path.as_posix(), updater.content_manifest(Path('.')))

    def test_only_tray_selects_dedicated_badge_and_keeps_legacy_fallback(self):
        source = Path('folder.pyw').read_text(encoding='utf-8')
        start = source.index('    def _minimize_to_systray')
        end = source.index('    def _stop_tray_icon', start)
        tray = source[start:end]
        self.assertIn('folderforge-tray.png', tray)
        self.assertIn('tray_path.is_file()', tray)
        self.assertIn('APP_ICON_PNG', tray)
        self.assertIn('folderforge-logo.png', source)
