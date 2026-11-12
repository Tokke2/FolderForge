"""Verify true vector originals, runtime formats and tray routing contracts."""
import ast
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import xml.etree.ElementTree as ET
import updater


class BrandAssetTests(unittest.TestCase):
    def test_print_originals_have_paths_not_rasters_or_font_dependencies(self):
        for name in ('folderforge-symbol', 'folderforge-logo', 'folderforge-logo-inverse', 'folderforge-logo-mono'):
            with self.subTest(name=name):
                root = ET.parse(Path('Icon') / (name + '.svg')).getroot()
                tags = [element.tag.split('}')[-1] for element in root.iter()]
                self.assertIn('viewBox', root.attrib)
                self.assertIn('path', tags)
                self.assertFalse({'image', 'text', 'script', 'foreignObject'} & set(tags))
                for element in root.iter():
                    self.assertFalse(any('href' in key for key in element.attrib))

    def test_vector_assets_participate_in_release_manifest(self):
        manifest = updater.content_manifest(Path('.'))
        for name in ('folderforge-symbol', 'folderforge-logo', 'folderforge-logo-inverse', 'folderforge-logo-mono'):
            self.assertIn('Icon/' + name + '.svg', manifest)
        self.assertFalse(updater._app_relative('Icon/../data/private.svg'))
        self.assertFalse(updater._app_relative('data/private.svg'))

    def test_runtime_icon_sizes(self):
        for name, size in [('folderforge-master.png', 1024), ('folderforge-tray.png', 64), ('projektmapp_icon_256.png', 256)]:
            data = (Path('Icon') / name).read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', data[16:24]), (size, size))
        data = Path('Icon/projektmapp.ico').read_bytes()
        self.assertEqual(struct.unpack('<HHH', data[:6]), (0, 1, 7))
        self.assertEqual(Path('Icon/folderforge.icns').read_bytes()[:4], b'icns')

    def test_iconic_main_window_routes_to_tray_not_exit(self):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        node = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_send_iconic_window_to_tray')
        ns = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'tray', 'exec'), ns)
        for state in ('iconic', 'normal', 'withdrawn'):
            window = Mock()
            window.winfo_exists.return_value = True
            window.state.return_value = state
            ns['_send_iconic_window_to_tray'](window)
            self.assertEqual(window._minimize_to_systray.call_count, int(state == 'iconic'))
            window._quit_app.assert_not_called()
