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
        self.assertIn('label="Donationer – Stöd FolderForge", command=self._show_support', self.source)
        for forbidden in ('CTkEntry', 'CTkTextbox', 'urlopen', 'requests.',
                          'self.settings', 'qrserver'):
            self.assertNotIn(forbidden, self.code)
        self.assertIn('existing.winfo_exists()', self.code)
        self.assertIn('dialog_layout(win)', self.code)
        self.assertIn("win.bind('<Escape>'", self.code)
        self.assertIn('Kontrollera alltid mottagarens namn', self.code)
        self.assertIn('Alla funktioner fungerar precis lika bra utan donation.', self.code)
        self.assertIn('Tack för att du använder FolderForge!', self.code)

    def test_qr_is_shipped_and_hashed_by_updater(self):
        path = Path('Icon/swish-folderforge.png')
        content = path.read_bytes()
        self.assertTrue(content.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(updater.content_manifest(Path('.'))[path.as_posix()], hashlib.sha256(content).hexdigest())

    def test_payment_links_are_fixed_and_only_open_on_click(self):
        calls = [node for node in ast.walk(self.method) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == 'webbrowser']
        self.assertEqual({node.args[0].value for node in calls},
                         {'https://paypal.me/Rickard3dPrint', 'https://ko-fi.com/tokke2'})
        parents = {child: parent for parent in ast.walk(self.method) for child in ast.iter_child_nodes(parent)}
        for call in calls:
            self.assertEqual(call.func.attr, 'open')
            self.assertIsInstance(parents[call], ast.Lambda)
        self.assertIn('Mottagarlänkarna är fasta', self.code)


class QtSupportTests(unittest.TestCase):
    def test_menu_and_fixed_offline_payment_choices(self):
        source = Path('qt_app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'donations')
        code = ast.get_source_segment(source, method)
        self.assertIn("help_menu.addAction('Donationer – Stöd FolderForge', self.donations)", source)
        for expected in ('swish-folderforge.png', '0721817177', 'Kontrollera alltid mottagarens namn',
                         'QScrollArea', 'pixmap.isNull()', 'dialog.exec()'):
            self.assertIn(expected, code)
        for forbidden in ('qrserver', 'urlopen', 'requests.', 'QLineEdit', 'QWebEngine'):
            self.assertNotIn(forbidden, code)
        calls = [n for n in ast.walk(method) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == 'webbrowser']
        self.assertEqual({n.args[0].value for n in calls},
            {'https://paypal.me/Rickard3dPrint', 'https://ko-fi.com/tokke2'})
        parents = {child: parent for parent in ast.walk(method) for child in ast.iter_child_nodes(parent)}
        for call in calls:
            self.assertIsInstance(parents[call], ast.Lambda)
