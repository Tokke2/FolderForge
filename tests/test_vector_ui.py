"""Production UI uses native vector rendering instead of upscaled icon bitmaps."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import updater


class VectorUITests(unittest.TestCase):
    def test_navigation_vectors_are_local_scalable_and_release_hashed(self):
        manifest = updater.content_manifest(Path('.'))
        for name in ('create', 'history', 'templates', 'export', 'settings', 'keyboard'):
            for theme in ('light', 'dark'):
                path = Path('Icon') / f'nav-{name}-{theme}.svg'
                root = ET.parse(path).getroot()
                self.assertEqual(root.attrib['viewBox'], '0 0 24 24')
                self.assertFalse(any(node.tag.endswith('image') for node in root.iter()))
                self.assertIn(path.as_posix(), manifest)

    def test_live_logo_and_icons_use_svg_and_fractional_dpi_is_not_rounded(self):
        app = Path('qt_app.py').read_text(encoding='utf-8')
        self.assertIn('QSvgWidget(str(logo_path))', app)
        self.assertNotIn('image.scaled(220, 44', app)
        self.assertNotIn('-light.png', app)
        self.assertNotIn('-dark.png', app)
        host = Path('qt_preview.py').read_text(encoding='utf-8')
        self.assertIn('HighDpiScaleFactorRoundingPolicy.PassThrough', host)
        self.assertIn('Icon/folderforge-symbol.svg', host)
