"""Migration must also work with older allowlists which omit the new modules."""
from pathlib import Path
import tempfile
import unittest
import updater


class SharedCoreUpgradeTests(unittest.TestCase):
    def test_recovery_sources_match_distributed_files(self):
        for name, source in updater.SHARED_CORE_FILES.items():
            self.assertEqual(Path(name).read_text(encoding='utf-8'), source)
            self.assertIn(name, updater.OPTIONAL_FILES)

    def test_legacy_install_recovers_modules_without_changing_hashed_app_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in updater.FILES:
                (root / name).write_text('# legacy staged app')
            manifest = updater.content_manifest(root)
            updater.ensure_shared_core(root)
            self.assertTrue(updater.matches_manifest(root, manifest))
            for name, source in updater.SHARED_CORE_FILES.items():
                self.assertEqual((root / name).read_text(), source)
            self.assertFalse(list(root.glob('.shared-core-*')))

    def test_existing_modules_are_never_rewritten_before_integrity_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            updater.ensure_shared_core(root)
            target = root / 'app_core.py'
            target.write_text('# modified')
            updater.ensure_shared_core(root)
            self.assertEqual(target.read_text(), '# modified')
