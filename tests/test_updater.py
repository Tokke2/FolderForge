import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from urllib.error import HTTPError

import updater


def archive(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        for name in updater.FILES:
            z.writestr('repo/' + name, '# new release\n')
        for name, content in (extra or {}).items():
            z.writestr(name, content)
    return output.getvalue()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_status_before_first_check(self):
        status = updater.get_update_status(self.base, '5.0')
        self.assertEqual(status['Installerad version'], '5.0')
        self.assertEqual(status['Senaste kontrollförsök'], 'Aldrig')

    def test_status_pending_release_and_installed_version(self):
        updater.write_state(self.base, {'installed': 'v5.1', 'pending': 'v5.2',
                                       'last_check': 100000, 'latest': 'v5.2', 'status': 'checked'})
        (self.base / 'data/update-pending').mkdir()
        status = updater.get_update_status(self.base, '5.0')
        self.assertEqual(status['Installerad version'], 'v5.1')
        self.assertIn('nästa appstart', status['Status'])
        self.assertNotEqual(status['Senaste kontrollförsök'], 'Aldrig')

    def test_failed_check_visible_in_status(self):
        with patch.object(updater, 'fetch', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                updater.check_once(self.base, '5.0', now=100000)
        status = updater.get_update_status(self.base, '5.0')
        self.assertIn('misslyckades', status['Status'])
        self.assertEqual(status['Senaste fel'], 'offline')

    def test_missing_release_is_not_reported_as_network_failure(self):
        url = f'https://api.github.com/repos/{updater.REPOSITORY}/releases/latest'
        with patch.object(updater, 'fetch', side_effect=HTTPError(url, 404, 'Not Found', {}, None)):
            updater.check_once(self.base, '5.0', now=100000)
        self.assertIn('Ingen stabil release', updater.get_update_status(self.base, '5.0')['Status'])

    def test_success_clears_previous_error(self):
        updater.write_state(self.base, {'status': 'error', 'error': 'offline'})
        release = json.dumps({'tag_name': 'v5.0', 'draft': False, 'prerelease': False}).encode()
        with patch.object(updater, 'fetch', return_value=release):
            updater.check_once(self.base, '5.0', now=100000)
        status = updater.get_update_status(self.base, '5.0')
        self.assertEqual(status['Senaste fel'], 'Inget registrerat')
        self.assertEqual(status['Senast hittade release'], 'v5.0')

    def test_corrupt_timestamp_and_stale_installed_version(self):
        updater.write_state(self.base, {'last_check': 'broken', 'installed': 'v4.0'})
        status = updater.get_update_status(self.base, '5.0')
        self.assertEqual(status['Installerad version'], '5.0')
        self.assertEqual(status['Senaste kontrollförsök'], 'Aldrig')

    def test_versions(self):
        self.assertEqual(updater.version('v5.1'), updater.version('5.1.0'))
        self.assertGreater(updater.version('5.10'), updater.version('5.9'))
        self.assertIsNone(updater.version('v6.0-rc1'))
        self.assertIsNone(updater.version('main'))

    def test_interval_survives_restart(self):
        updater.write_state(self.base, {'last_check': 100})
        with patch.object(updater, 'fetch') as fetch:
            updater.check_once(self.base, '5.0', now=101)
            fetch.assert_not_called()

    def test_download_and_apply_preserves_data(self):
        release = json.dumps({'tag_name': 'v5.1', 'draft': False, 'prerelease': False}).encode()
        with patch.object(updater, 'fetch', side_effect=[release, archive()]) as fetch:
            updater.check_once(self.base, '5.0', now=100000)
            self.assertTrue(fetch.call_args[0][0].endswith('/zipball/v5.1'))
        data = self.base / 'data/settings.json'
        data.write_text('user settings')
        (self.base / 'folder.pyw').write_text('# old')
        self.assertTrue(updater.apply_pending(self.base))
        self.assertEqual(data.read_text(), 'user settings')
        self.assertEqual((self.base / 'folder.pyw').read_text(), '# new release\n')
        self.assertEqual((self.base / 'data/update-backup/folder.pyw').read_text(), '# old')
        self.assertFalse(updater.apply_pending(self.base))

    def test_no_release_or_prerelease_is_not_downloaded(self):
        for tag, prerelease in [('v4.0', False), ('v6.0', True), ('main', False)]:
            with self.subTest(tag=tag), patch.object(updater, 'fetch', return_value=json.dumps(
                    {'tag_name': tag, 'prerelease': prerelease}).encode()) as fetch:
                updater.check_once(self.base, '5.0', now=100000)
                self.assertEqual(fetch.call_count, 1)
                (self.base / 'data/update-state.json').unlink()

    def test_archive_cannot_overwrite_data_or_git(self):
        updater.unpack(archive({'repo/../escape.py': 'bad', 'repo/data/settings.json': 'bad',
                                'repo/.git/config': 'bad'}), self.base)
        self.assertFalse((self.base / 'data').exists())
        self.assertFalse((self.base / '.git').exists())
        self.assertFalse((self.base.parent / 'escape.py').exists())

    def test_failed_network_is_throttled(self):
        with patch.object(updater, 'fetch', side_effect=OSError('offline')) as fetch:
            with self.assertRaises(OSError):
                updater.check_once(self.base, '5.0', now=100000)
            updater.check_once(self.base, '5.0', now=100001)
            self.assertEqual(fetch.call_count, 1)

    def test_incomplete_archive_rejected(self):
        with self.assertRaises(ValueError):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as z:
                z.writestr('repo/folder.pyw', '# incomplete')
            updater.unpack(output.getvalue(), self.base)


if __name__ == '__main__':
    unittest.main()
