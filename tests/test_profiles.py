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

    def test_overwrite_existing_custom_and_builtin_profiles_atomically(self):
        bilar_root = self.base / 'Bilder' / 'Bilar'
        # Initial creation returns False (new profile)
        self.assertFalse(self.ws.save_profile('Bilrutan', 'Bilder/\nREADME.md\n.gitignore\n', str(bilar_root)))
        # Overwriting existing custom profile returns True and updates structure + save_root
        new_root = self.base / 'Bilder' / 'Verkstad'
        self.assertTrue(self.ws.save_profile('bilrutan', 'Bilder/\nUnderlag/\n.gitignore\n', str(new_root)))
        reopened = Workspace(self.lock, self.base)
        names = list(reopened.templates.list_templates())
        self.assertEqual([n for n in names if n.casefold() == 'bilrutan'], ['bilrutan'])
        self.assertEqual(reopened.profile_root('bilrutan'), new_root)
        self.assertIn('Underlag/', reopened.templates.list_templates()['bilrutan'])

        # Overwriting built-in profile updates both structure and save_root across reloads
        skade_root = self.base / 'Skador'
        self.assertTrue(self.ws.save_profile('Skaderapport', 'Bilder/\nKvitton/\n', str(skade_root)))
        reopened2 = Workspace(self.lock, self.base)
        self.assertEqual(reopened2.profile_root('Skaderapport'), skade_root)
        self.assertEqual(reopened2.templates.list_templates()['Skaderapport'], 'Bilder/\nKvitton/\n')

    def test_delete_custom_and_builtin_profiles_and_restore_builtins(self):
        # Create Bilrutan with .bak backup present by saving twice
        self.ws.save_profile('Bilrutan', 'Bilder/\n', str(self.base / 'Bilar1'))
        self.ws.save_profile('Bilrutan', 'Bilder/\nUnderlag/\n', str(self.base / 'Bilar2'))
        self.ws.config.default_template = 'Bilrutan'
        self.ws.remember_profile('Bilrutan')
        self.ws.save_settings()
        self.assertTrue((self.base / 'data/templates/Bilrutan.json.bak').exists())

        # Deleting active/default custom profile cleans up .json + .bak and updates fallback
        fallback = self.ws.delete_profile('Bilrutan')
        self.assertNotIn('Bilrutan', self.ws.templates.list_templates())
        self.assertFalse((self.base / 'data/templates/Bilrutan.json').exists())
        self.assertFalse((self.base / 'data/templates/Bilrutan.json.bak').exists())
        self.assertEqual(fallback, 'Skaderapport')
        self.assertEqual(self.ws.config.default_template, 'Skaderapport')

        # Deleting built-in profiles persists across Workspace reloads
        self.ws.delete_profile('Python Projekt')
        self.ws.delete_profile('Webb Projekt')
        self.ws.delete_profile('Skaderapport')
        # Only 'Privat' remains now
        reopened = Workspace(self.lock, self.base)
        self.assertEqual(list(reopened.templates.list_templates()), ['Privat'])
        self.assertEqual(reopened.selected_profile(), 'Privat')

        # Cannot delete the very last remaining profile
        with self.assertRaises(ValueError):
            reopened.delete_profile('Privat')
        self.assertEqual(list(reopened.templates.list_templates()), ['Privat'])

        # Restoring built-in templates brings them back cleanly
        restored = reopened.restore_builtin_profiles()
        self.assertEqual(set(restored), {'Python Projekt', 'Webb Projekt', 'Skaderapport'})
        for builtin_name in ('Python Projekt', 'Webb Projekt', 'Skaderapport'):
            self.assertIn(builtin_name, reopened.templates.list_templates())

    def test_create_project_with_gitignore_and_dotfiles_succeeds(self):
        bilar_root = self.base / 'Bilder' / 'Bilar'
        self.ws.save_profile(
            'Bilrutan',
            'projektnamn/\n    src/\n        __init__.py\n        main.py\n'
            '    tests/\n        test_main.py\n    docs/\n'
            '    requirements.txt\n    README.md\n    .gitignore\n',
            str(bilar_root),
        )
        name, items = self.ws.prepare_project('FGZ029 VINDRUTA LAXÅ 2021', 'Bilrutan')
        created = self.ws.create_project(name, items, 'Bilrutan')
        self.assertEqual(created, bilar_root / 'FGZ029 VINDRUTA LAXÅ 2021')
        self.assertTrue((created / '.gitignore').is_file())
        self.assertTrue((created / 'src' / 'main.py').is_file())
        self.assertTrue((created / 'docs').is_dir())

