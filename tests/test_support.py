"""Fixed Swish recipient, offline QR asset, no payment settings or web embeds."""
import ast
import hashlib
from pathlib import Path
import unittest

from tools.build_swish_qr import SWISH_PAYLOAD
import updater


class SupportTests(unittest.TestCase):
    def setUp(self):
        self.source = Path('folder.pyw').read_text(encoding='utf-8')
        tree = ast.parse(self.source)
        self.method = next(node for node in ast.walk(tree)
                           if isinstance(node, ast.FunctionDef) and node.name == '_show_support')
        self.code = ast.get_source_segment(self.source, self.method)

    def test_standard_payload_fixed_recipient_empty_amount(self):
        self.assertEqual(SWISH_PAYLOAD, 'C46721817177;;FolderForge;6')

    def test_menu_is_explicit_and_dialog_is_read_only(self):
        self.assertIn('label="Stöd FolderForge – Swish", command=self._show_support', self.source)
        for forbidden in ('CTkEntry', 'CTkTextbox', 'webbrowser', 'urlopen', 'requests.',
                          'self.settings', 'paypal', 'ko-fi', 'qrserver'):
            self.assertNotIn(forbidden, self.code)
        self.assertIn('existing.winfo_exists()', self.code)
        self.assertIn('dialog_layout(win)', self.code)
        self.assertIn("win.bind('<Escape>'", self.code)
        self.assertIn('Kontrollera alltid mottagarens namn', self.code)

    def test_qr_is_shipped_and_hashed_by_updater(self):
        path = Path('Icon/swish-folderforge.png')
        content = path.read_bytes()
        self.assertTrue(content.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(updater.content_manifest(Path('.'))[path.as_posix()], hashlib.sha256(content).hexdigest())
