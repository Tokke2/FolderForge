"""A profile is one template plus its save root, in the same atomic JSON file."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from workspace import Workspace


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.lock = SimpleNamespace(is_primary=True)
        self.ws = Workspace(self.lock, self.base)
        self.ws.config.save_root = str(self.base / 'Legacy')

    def test_legacy_template_inherits_global_path_without_migration(self):
        self.assertEqual(self.ws.profile_root('Skaderapport'), self.base / 'Legacy')
        self.ws.templates.save_template('Äldre mall', 'Bilder/\n')
        self.assertEqual(self.ws.profile_root('Äldre mall'), self.base / 'Legacy')
        self.assertNotIn('save_root', json.loads((self.base / 'data/templates/Äldre mall.json').read_text()))

    def test_two_profiles_route_projects_and_history_to_different_roots(self):
        for profile, root in [('Verkstad', self.base / 'Work'), ('Privat', self.base / 'Home')]:
            self.ws.save_profile(profile, 'Bilder/\nUnderlag/\n', str(root))
            name, items = self.ws.prepare_project('ABC123', profile)
            path = self.ws.create_project(name, items, profile)
            self.assertEqual(path.parent, root)
            self.assertTrue((path / 'Bilder').is_dir())
            self.assertTrue((path / 'Underlag').is_dir())
        self.assertEqual(len(self.ws.history.get_all()), 2)
        self.assertFalse((self.base / 'Legacy').exists())

    def test_default_profile_persists_and_overrides_global_destination(self):
        root = self.base / 'ProfileRoot'
        self.ws.save_profile('Jobb', 'Bilder/\n', str(root))
        self.ws.config.default_template = 'Jobb'
        self.ws.save_settings()
        reopened = Workspace(self.lock, self.base)
        self.assertEqual(reopened.profile_root(), root)
        reopened.config.save_root = str(self.base / 'ChangedGlobal')
        self.assertEqual(reopened.profile_root(), root)
        self.assertFalse(root.exists(), 'Saving or selecting a profile must not create projects')

    def test_legacy_template_edit_preserves_profile_destination(self):
        root = self.base / 'Work'
        self.ws.save_profile('Jobb', 'Bilder/\n', str(root))
        self.ws.templates.save_template('Jobb', 'Bilder/\nDiagnos/\n')
        self.assertEqual(self.ws.profile_root('Jobb'), root)
        self.assertIn('Diagnos/', self.ws.templates.list_templates()['Jobb'])

    def test_bad_path_and_empty_name_do_not_write_a_profile(self):
        for name, root in [('Bad', ''), ('Bad', 'relative/path'), ('', str(self.base))]:
            with self.subTest(name=name, root=root), self.assertRaises(ValueError):
                self.ws.save_profile(name, 'Bilder/\n', root)
        self.assertEqual(list((self.base / 'data/templates').glob('*.json')), [])

    def test_profile_write_failure_keeps_previous_atomic_record(self):
        self.ws.save_profile('Jobb', 'Bilder/\n', str(self.base / 'Before'))
        with patch('app_core.atomic_write_json', return_value=False), self.assertRaises(OSError):
            self.ws.save_profile('Jobb', 'Other/\n', str(self.base / 'After'))
        self.assertEqual(self.ws.profile_root('Jobb'), self.base / 'Before')
        self.assertEqual(self.ws.templates.list_templates()['Jobb'], 'Bilder/\n')

    def test_invalid_stored_destination_blocks_instead_of_saving_elsewhere(self):
        self.ws.save_profile('Jobb', 'Bilder/\n', str(self.base / 'Work'))
        path = self.base / 'data/templates/Jobb.json'
        data = json.loads(path.read_text())
        data['save_root'] = 123
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.ws.profile_root('Jobb')

    def test_saving_profile_requires_instance_lock(self):
        self.lock.is_primary = False
        with self.assertRaises(RuntimeError):
            self.ws.save_profile('Jobb', 'Bilder/\n', str(self.base / 'Work'))


class RecentProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.lock = SimpleNamespace(is_primary=True)
        self.ws = Workspace(self.lock, self.base)
        self.ws.config.default_template = 'Skaderapport'
        self.ws.save_settings()
        self.ws.save_profile('Privat', 'Bilder/\n', str(self.base / 'Home'))

    def test_last_choice_persists_without_changing_default(self):
        self.ws.remember_profile('Privat')
        reopened = Workspace(self.lock, self.base)
        self.assertEqual(reopened.selected_profile(), 'Privat')
        self.assertEqual(reopened.config.default_template, 'Skaderapport')
        self.assertEqual(reopened.profile_root(reopened.selected_profile()), self.base / 'Home')

    def test_default_is_fallback_and_does_not_override_recent(self):
        self.assertEqual(self.ws.selected_profile(), 'Skaderapport')
        self.ws.remember_profile('Privat')
        self.ws.config.default_template = 'Python Projekt'
        self.ws.save_settings()
        self.assertEqual(self.ws.selected_profile(), 'Privat')
        self.ws.templates.delete_template('Privat')
        self.assertEqual(self.ws.selected_profile(), 'Python Projekt')

    def test_remember_does_not_save_other_unsaved_settings(self):
        original = self.ws.config.save_root
        self.ws.config.save_root = str(self.base / 'NotYetSaved')
        self.ws.remember_profile('Privat')
        reopened = Workspace(self.lock, self.base)
        self.assertEqual(reopened.config.save_root, original)
        self.assertEqual(reopened.config.last_template, 'Privat')

    def test_failure_keeps_previous_choice(self):
        with patch('workspace.atomic_write_json', return_value=False), self.assertRaises(OSError):
            self.ws.remember_profile('Privat')
        self.assertEqual(self.ws.selected_profile(), 'Skaderapport')
        with self.assertRaises(ValueError):
            self.ws.remember_profile('saknas')
