import ast
from datetime import datetime
import re
from pathlib import Path
import unittest
import settings


class YearTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'project_year_choices', 'validate_project_year'}]
        app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FolderForgeApp')
        method = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_bygg_projektnamn')
        method.decorator_list = []
        nodes.append(method)
        cls.ns = {'datetime': datetime, 're': re, 'LOKAL_CHOICES': settings.LOKAL_CHOICES}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'years', 'exec'), cls.ns)

    def test_current_year_and_three_previous(self):
        self.assertEqual(self.ns['project_year_choices'](datetime(2026, 10, 28)), ['2026', '2025', '2024', '2023'])

    def test_new_year_rollover(self):
        self.assertEqual(self.ns['project_year_choices'](datetime(2027, 1, 1)), ['2027', '2026', '2025', '2024'])

    def test_year_after_location(self):
        self.assertEqual(self.ns['_bygg_projektnamn']('ABC123 SIDORUTA', 'LAXÅ', '2025'), 'ABC123 SIDORUTA LAXÅ 2025')

    def test_optional_year_and_location(self):
        build = self.ns['_bygg_projektnamn']
        self.assertEqual(build('ABC123', '—', '2026'), 'ABC123 2026')
        self.assertEqual(build('ABC123', 'LAXÅ'), 'ABC123 LAXÅ')
        self.assertEqual(build('ABC123', '—'), 'ABC123')

    def test_selected_year_not_duplicated(self):
        self.assertEqual(self.ns['_bygg_projektnamn']('ABC123 2026', 'LAXÅ', '2026'), 'ABC123 LAXÅ 2026')

    def test_windscreen_damage_type_and_project_name(self):
        self.assertEqual(settings.DAMAGE_TYPE_CHIPS.count('VINDRUTA'), 1)
        self.assertEqual(self.ns['_bygg_projektnamn']('ABC123 VINDRUTA', 'LAXÅ', '2026'),
                         'ABC123 VINDRUTA LAXÅ 2026')

    def test_custom_year_outside_suggestions(self):
        year = self.ns['validate_project_year'](' 2010 ')
        self.assertEqual(self.ns['_bygg_projektnamn']('ABC123', 'LAXÅ', year), 'ABC123 LAXÅ 2010')

    def test_optional_typed_year(self):
        self.assertEqual(self.ns['validate_project_year'](''), '—')
        self.assertEqual(self.ns['validate_project_year'](' — '), '—')

    def test_invalid_typed_year(self):
        for value in ['20', '20266', 'abcd', '../2020', '0000']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.ns['validate_project_year'](value)

    def test_editable_picker_preserves_custom_year_on_refresh(self):
        source = Path('folder.pyw').read_text(encoding='utf-8')
        self.assertIn('year_menu = ctk.CTkComboBox(', source)
        tree = ast.parse(source)
        refresh = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'refresh_year_choices')
        self.assertNotIn('year_var.set', ast.unparse(refresh))
