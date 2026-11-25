"""Shared production services tested without importing Tk or Qt."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

from app_core import ExistingProject, create_project_tree
from instance_lock import SingleInstanceLock
from workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = SingleInstanceLock('FolderForge-test-' + uuid.uuid4().hex, self.root / 'lock')
        self.assertTrue(self.lock.acquire())
        self.addCleanup(self.lock.release)
        self.workspace = Workspace(self.lock, self.root)
        self.workspace.config.save_root = str(self.root / 'Projects')
        self.workspace.save_settings()

    def test_lock_is_required_before_opening_or_writing_data(self):
        self.lock.release()
        with self.assertRaises(RuntimeError):
            Workspace(self.lock, self.root)
        with self.assertRaises(RuntimeError):
            self.workspace.save_settings()

    def test_shared_lock_rejects_second_process(self):
        code = ('from instance_lock import SingleInstanceLock; import sys; '
                'lock=SingleInstanceLock(sys.argv[1],sys.argv[2]); '
                'ok=lock.acquire(); lock.release(); sys.exit(1 if ok else 0)')
        result = subprocess.run([sys.executable, '-c', code, self.lock.app_name, str(self.lock.lock_dir)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.lock.is_primary)

    def test_shared_project_and_history_round_trip(self):
        name, items = self.workspace.prepare_project('abc 123 vindruta')
        path = self.workspace.create_project(name, items)
        self.assertEqual(path.name, 'ABC123 VINDRUTA')
        self.assertTrue((path / 'Bilder').is_dir())
        reloaded = Workspace(self.lock, self.root)
        self.assertEqual(reloaded.history.get_all()[0]['path'], str(path.resolve()))
        with self.assertRaises(ExistingProject):
            reloaded.create_project(name.lower(), items)
        self.assertEqual(len(reloaded.history.get_all()), 1)

    def test_invalid_structure_is_rejected_before_any_project_is_created(self):
        for parts in (['..', 'outside'], ['/outside'], ['CON.txt'], ['a/b'], []):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                create_project_tree(self.root / 'Projects', 'TEST', [{'path': parts, 'is_dir': True}])
        self.assertFalse((self.root / 'Projects').exists())

    def test_unknown_settings_and_templates_survive_round_trip(self):
        self.workspace.raw['future_key'] = {'keep': True}
        self.workspace.save_settings()
        self.workspace.templates.save_template('Verkstad', 'projekt/\n    Foto/\n')
        other = Workspace(self.lock, self.root)
        self.assertEqual(other.raw['future_key'], {'keep': True})
        self.assertIn('Verkstad', other.templates.list_templates())

    def test_production_module_is_gui_independent(self):
        code = "import app_core,instance_lock,workspace,sys; assert 'tkinter' not in sys.modules; assert 'PySide6' not in sys.modules"
        subprocess.run([sys.executable, '-c', code], check=True, timeout=15)
