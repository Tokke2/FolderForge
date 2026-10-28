import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cache_cleanup as cache


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.now = 2000000

    def file(self, name, age):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('data')
        os.utime(path, (self.now - age, self.now - age))
        return path

    def test_smart_filters(self):
        old = [self.file('data/cache/nested/old.bin', 2 * cache.DAY),
               self.file('data/tmp/temp.tmp', 2 * cache.DAY),
               self.file('data/logs/folderforge.log.1', 15 * cache.DAY)]
        protected = [self.file(name, 30 * cache.DAY) for name in [
            'data/history.json', 'data/settings.json', 'data/templates/mall.json',
            'data/update-backup/settings.py', 'data/update-pending/folder.pyw',
            'data/logs/folderforge.log', 'data/logs/unknown.log', 'project/test.tmp',
            '.git/keep', 'unknown.tmp']]
        protected += [self.file('data/cache/new.bin', 60),
                      self.file('data/logs/folderforge.log.2', cache.DAY)]
        result = cache.clean_cache(self.base, now=self.now)
        self.assertEqual(result['removed'], 3)
        self.assertTrue(all(not p.exists() for p in old))
        self.assertTrue(all(p.exists() for p in protected))

    def test_daily_schedule_persisted_across_calls(self):
        cache.clean_cache(self.base, now=self.now)
        old = self.file('data/cache/old.bin', 2 * cache.DAY)
        cache.clean_cache(self.base, now=self.now + 100)
        self.assertTrue(old.exists())
        cache.clean_cache(self.base, now=self.now + cache.DAY)
        self.assertFalse(old.exists())

    def test_manual_run_still_preserves_fresh_files(self):
        cache.clean_cache(self.base, now=self.now)
        old = self.file('data/cache/old.bin', 2 * cache.DAY)
        fresh = self.file('data/cache/new.bin', 10)
        cache.clean_cache(self.base, manual=True, now=self.now + 20)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_symlink_never_followed_or_removed(self):
        outside = self.file('outside/important', 30 * cache.DAY)
        root = self.base / 'data/cache'
        root.mkdir(parents=True)
        (root / 'link').symlink_to(outside.parent, target_is_directory=True)
        cache.clean_cache(self.base, now=self.now)
        self.assertTrue(outside.exists())
        self.assertTrue((root / 'link').is_symlink())

    def test_project_paths_inside_cache_are_protected(self):
        project = self.file('data/cache/project/photo.jpg', 30 * cache.DAY)
        historical = self.file('data/tmp/old-project/file.txt', 30 * cache.DAY)
        (self.base / 'data/settings.json').write_text(json.dumps({'save_root': str(project.parent)}))
        (self.base / 'data/history.json').write_text(json.dumps([{'path': str(historical.parent)}]))
        cache.clean_cache(self.base, now=self.now)
        self.assertTrue(project.exists())
        self.assertTrue(historical.exists())

    def test_locked_file_does_not_stop_cleanup(self):
        locked = self.file('data/cache/locked', 2 * cache.DAY)
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == locked:
                raise PermissionError('locked')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'unlink', unlink), self.assertLogs(cache.logger, 'WARNING'):
            result = cache.clean_cache(self.base, now=self.now)
        self.assertEqual(result['failed'], 1)
        self.assertTrue(locked.exists())

    def test_status_before_and_after_run(self):
        self.assertIn('Ingen rensning', cache.status_text(self.base))
        cache.clean_cache(self.base, now=self.now)
        self.assertIn('0 filer', cache.status_text(self.base))


if __name__ == '__main__':
    unittest.main()
