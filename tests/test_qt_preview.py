"""Optional Qt stays isolated from production Tk and storage."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest

import updater


class QtPreviewTests(unittest.TestCase):
    def test_preview_is_optional_and_does_not_change_standard_dependencies(self):
        for name in ('qt_preview.py', 'Starta-FolderForge-Qt.py', 'requirements-qt.txt'):
            self.assertIn(name, updater.OPTIONAL_FILES)
            self.assertNotIn(name, updater.FILES)
        self.assertIn('PySide6', Path('requirements.txt').read_text())
        self.assertNotIn('qt_preview', Path('Starta-FolderForge.py').read_text())
        self.assertIn('from gui_entry import main as _qt_main', Path('folder.pyw').read_text())

    def test_no_production_imports_or_file_writes(self):
        source = Path('qt_preview.py').read_text()
        tree = ast.parse(source.split("\ndef run(", 1)[0])
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                for module in modules:
                    self.assertNotIn(module, {'tkinter', 'customtkinter', 'settings', 'historik', 'updater'})
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
                self.assertNotIn(name, {'open', 'write_text', 'write_bytes', 'mkdir', 'unlink', 'rmtree', 'Popen'})
        self.assertIn('Inga mappar skapas', source)
        self.assertIn('QLockFile', source)
        self.assertIn('isSystemTrayAvailable', source)

    def test_missing_optional_dependency_has_no_install_or_automatic_tk_fallback(self):
        # -S hides third-party site packages, exercising a clean Python without Qt.
        result = subprocess.run([sys.executable, '-S', 'Starta-FolderForge-Qt.py'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn('requirements-qt.txt', result.stderr)
        self.assertIn('Tk-startfilen', result.stderr)
