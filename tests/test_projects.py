"""Headless tests of the actual app methods, without loading GUI dependencies."""
import ast
from dataclasses import dataclass, field, asdict
import logging
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import historik
import settings


def load_logic():
    tree = ast.parse(Path('folder.pyw').read_text(encoding='utf-8'))
    classes = {'TemplateManager', 'NameValidator', 'StructureEngine', 'AppSettings'}
    nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in classes:
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {'sanitize_name', 'strip_root_level', 'validate_settings', 'focus_project_name'}:
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == 'FolderForgeApp':
            nodes.extend(n for n in node.body if isinstance(n, ast.FunctionDef)
                         and n.name in {'_build_structure', '_create_std_proj'})
    namespace = vars(settings).copy()
    namespace.update(Path=Path, re=re, logger=logging.getLogger('test'),
                     dataclass=dataclass, field=field, asdict=asdict,
                     atomic_write_json=historik.atomic_write_json,
                     read_json_safe=historik.read_json_safe, messagebox=Mock(),
                     RESERVED_STEM_RE=re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I))
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'app_logic', 'exec'), namespace)
    return namespace


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.ns = load_logic()
        self.ns['TEMPLATES_DIR'] = self.base / 'templates'
        self.manager = self.ns['TemplateManager']()

    def test_saved_templates_reload_and_default_setting(self):
        self.manager.save_template('Verkstad', 'projekt/\n    Foto/\n    Dokument/\n')
        self.assertIn('Verkstad', self.ns['TemplateManager']().list_templates())
        cfg = self.ns['AppSettings'].from_dict({'default_template': 'Verkstad'})
        self.assertEqual(cfg.to_dict()['default_template'], 'Verkstad')

    def test_project_name_focus_selects_existing_text(self):
        entry = Mock()
        entry.winfo_exists.return_value = True
        self.ns['focus_project_name'](entry)
        entry.focus_set.assert_called_once()
        entry.select_range.assert_called_once_with(0, 'end')
        entry.icursor.assert_called_once_with('end')

    def test_closed_name_field_is_not_focused(self):
        entry = Mock()
        entry.winfo_exists.return_value = False
        self.ns['focus_project_name'](entry)
        entry.focus_set.assert_not_called()

    def test_empty_template_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.save_template('Tom', '')

    def test_default_structure_used_and_override_not_saved(self):
        self.manager.save_template('Verkstad', 'projekt/\n    Foto/\n')
        cfg = SimpleNamespace(save_root=str(self.base), default_template='Verkstad', plate_mode=False)
        app = SimpleNamespace(settings=cfg, template_mgr=self.manager, _show_preview=Mock(return_value=True),
                              _build_structure=Mock())
        self.ns['_create_std_proj'](app, 'jobb')
        name, items = app._build_structure.call_args.args
        self.assertEqual(name, 'JOBB')
        self.assertEqual(items[0]['path'], ['Foto'])
        self.assertEqual(cfg.default_template, 'Verkstad')

    def test_existing_project_never_merged_even_with_yes(self):
        (self.base / 'JOBB').mkdir()
        app = SimpleNamespace(settings=SimpleNamespace(save_root=str(self.base)),
                              _open_path=Mock(), _on_creation_success=Mock())
        self.ns['messagebox'].askyesno.return_value = True
        created = self.ns['_build_structure'](app, 'jobb', [{'path': ['ny'], 'is_dir': True}])
        self.assertFalse(created)
        self.assertFalse((self.base / 'JOBB/ny').exists())
        self.assertFalse((self.base / 'jobb').exists())
        app._on_creation_success.assert_not_called()
        app._open_path.assert_called_once()

    def test_creation_recorded_once_and_nested_structure_created(self):
        app = SimpleNamespace(settings=SimpleNamespace(save_root=str(self.base)),
                              _open_path=Mock(), _on_creation_success=Mock())
        self.assertTrue(self.ns['_build_structure'](app, 'Nytt', [
            {'path': ['Foto'], 'is_dir': True, 'comment': ''}]))
        self.assertTrue((self.base / 'Nytt/Foto').is_dir())
        app._on_creation_success.assert_called_once_with(self.base / 'Nytt')

    def test_history_persists_all_projects_and_deduplicates(self):
        with patch.object(historik, 'HISTORY_FILE', self.base / 'history.json'):
            history = historik.ProjectHistory()
            for i in range(25):
                history.add(self.base / f'Project{i}')
            history.add(self.base / 'project0')
            self.assertEqual(len(history.get_all()), 25)
            reloaded = historik.ProjectHistory()
            self.assertEqual(len(reloaded.get_all()), 25)
            reloaded.remove(str(self.base / 'PROJECT0'))
            self.assertEqual(len(reloaded.get_all()), 24)


if __name__ == '__main__':
    unittest.main()
