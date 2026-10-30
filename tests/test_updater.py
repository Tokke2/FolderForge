import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from urllib.error import HTTPError

import updater

REVISION = "a" * 40
COMMIT = json.dumps({"sha": REVISION}).encode()


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
        with patch.object(updater, 'fetch', side_effect=[release, COMMIT, archive()]):
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
        with patch.object(updater, 'fetch', side_effect=[release, COMMIT, archive()]) as fetch:
            updater.check_once(self.base, '5.0', now=100000)
            self.assertTrue(fetch.call_args[0][0].endswith('/zipball/' + REVISION))
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

    def release(self, tag='v0.0.2'):
        return json.dumps({'tag_name': tag, 'draft': False, 'prerelease': False}).encode()

    def test_same_version_new_commit_is_downloaded_and_remembered(self):
        updater.write_state(self.base, {'installed': 'v0.0.2', 'installed_revision': 'b' * 40})
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]) as fetch:
            updater.check_once(self.base, '0.0.2', now=100000)
            self.assertTrue(fetch.call_args.args[0].endswith('/zipball/' + REVISION))
        self.assertEqual(updater.read_state(self.base)['pending_revision'], REVISION)
        self.assertTrue(updater.apply_pending(self.base))
        self.assertEqual(updater.read_state(self.base)['installed_revision'], REVISION)
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT]) as fetch:
            updater.check_once(self.base, '0.0.2', now=100000 + updater.INTERVAL)
            self.assertEqual(fetch.call_count, 2)
        self.assertFalse(updater.apply_pending(self.base))

    def test_legacy_same_version_without_revision_is_updated(self):
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000)
        self.assertTrue((self.base / 'data/update-pending').is_dir())
        self.assertEqual(updater.read_state(self.base)['pending'], 'v0.0.2')

    def test_identical_files_establish_baseline_without_reinstall(self):
        updater.unpack(archive(), self.base)
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000)
        state = updater.read_state(self.base)
        self.assertEqual(state['installed_revision'], REVISION)
        self.assertNotIn('pending', state)
        self.assertFalse(updater.apply_pending(self.base))

    def test_pending_revision_not_downloaded_twice(self):
        pending = self.base / 'data/update-pending'
        pending.mkdir(parents=True)
        updater.unpack(archive(), pending)
        updater.write_state(self.base, {'pending': 'v0.0.2', 'pending_revision': REVISION,
                                       'pending_hashes': updater.content_manifest(pending)})
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT]) as fetch:
            updater.check_once(self.base, '0.0.2', now=100000)
            self.assertEqual(fetch.call_count, 2)

    def test_changed_pending_revision_replaces_old_download(self):
        updater.write_state(self.base, {'pending': 'v0.0.2', 'pending_revision': 'b' * 40})
        (self.base / 'data/update-pending').mkdir()
        (self.base / 'data/update-pending/stale').touch()
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000)
        self.assertFalse((self.base / 'data/update-pending/stale').exists())
        self.assertEqual(updater.read_state(self.base)['pending_revision'], REVISION)

    def test_invalid_revision_not_downloaded(self):
        with patch.object(updater, 'fetch', side_effect=[self.release(), b'{"sha": "main"}']) as fetch:
            with self.assertRaises(ValueError):
                updater.check_once(self.base, '0.0.2', now=100000)
            self.assertEqual(fetch.call_count, 2)
        self.assertFalse((self.base / 'data/update-pending').exists())

    def test_build_ids_visible_in_status(self):
        updater.write_state(self.base, {'installed_revision': 'a' * 40,
                                       'latest_revision': 'b' * 40, 'pending_revision': 'c' * 40})
        status = updater.get_update_status(self.base, '0.0.2')
        self.assertEqual(status['Installerat bygg-ID'], 'a' * 12)
        self.assertEqual(status['Senaste bygg-ID'], 'b' * 12)
        self.assertEqual(status['Väntande bygg-ID'], 'c' * 12)

    def test_manual_check_bypasses_interval(self):
        updater.write_state(self.base, {'last_check': 100000})
        release = json.dumps({'tag_name': 'v4.0'}).encode()
        with patch.object(updater, 'fetch', return_value=release) as fetch:
            updater.check_once(self.base, '5.0', now=100001, force=True)
            fetch.assert_called_once()
        self.assertEqual(updater.read_state(self.base)['last_check'], 100001)

    def test_parallel_manual_check_does_not_fetch(self):
        with updater._check_lock, patch.object(updater, 'fetch') as fetch:
            self.assertFalse(updater.check_once(self.base, '0.0.2', force=True))
            fetch.assert_not_called()

    def test_release_notes_saved_for_pending_revision(self):
        release = json.dumps({'tag_name': 'v0.0.2', 'body': 'Ny funktion: VINDRUTA'}).encode()
        with patch.object(updater, 'fetch', side_effect=[release, COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000, force=True)
        status = updater.get_update_status(self.base, '0.0.2')
        self.assertEqual(status['Ändringar i hämtad uppdatering'], 'Ny funktion: VINDRUTA')
        updater.apply_pending(self.base)
        self.assertNotIn('pending_notes', updater.read_state(self.base))
        self.assertIn('Ingen hämtad', updater.get_update_status(self.base, '0.0.2')['Ändringar i hämtad uppdatering'])

    def test_failed_manual_check_releases_lock(self):
        with patch.object(updater, 'fetch', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                updater.check_once(self.base, '0.0.2', force=True)
        self.assertTrue(updater._check_lock.acquire(blocking=False))
        updater._check_lock.release()

    def install_current(self):
        updater.unpack(archive(), self.base)
        updater.write_state(self.base, {'installed': 'v0.0.2', 'installed_revision': REVISION,
                                       'installed_hashes': updater.content_manifest(self.base)})

    def test_same_commit_changed_file_is_repaired(self):
        self.install_current()
        (self.base / 'folder.pyw').write_text('# local change')
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000, force=True)
        self.assertTrue(updater.apply_pending(self.base))
        self.assertEqual((self.base / 'folder.pyw').read_text(), '# new release\n')

    def test_same_commit_missing_file_is_repaired(self):
        self.install_current()
        (self.base / 'logg.py').unlink()
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000, force=True)
        self.assertTrue(updater.apply_pending(self.base))
        self.assertTrue((self.base / 'logg.py').is_file())

    def test_unchanged_commit_and_files_do_not_download(self):
        self.install_current()
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT]) as fetch:
            updater.check_once(self.base, '0.0.2', now=100000, force=True)
            self.assertEqual(fetch.call_count, 2)
        self.assertFalse(updater.apply_pending(self.base))

    def test_modified_pending_files_are_rejected(self):
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT, archive()]):
            updater.check_once(self.base, '0.0.2', now=100000)
        (self.base / 'data/update-pending/folder.pyw').write_text('# changed after download')
        with self.assertRaises(ValueError):
            updater.apply_pending(self.base)
        self.assertFalse((self.base / 'folder.pyw').exists())

    def test_manifest_cannot_reference_user_data(self):
        self.install_current()
        hashes = updater.content_manifest(self.base)
        hashes['data/settings.json'] = 'a' * 64
        self.assertFalse(updater.matches_manifest(self.base, hashes))

    def test_user_data_changes_do_not_trigger_app_update(self):
        self.install_current()
        (self.base / 'data/settings.json').write_text('{"save_root": "my projects"}')
        with patch.object(updater, 'fetch', side_effect=[self.release(), COMMIT]) as fetch:
            updater.check_once(self.base, '0.0.2', now=100000, force=True)
            self.assertEqual(fetch.call_count, 2)

    def test_changed_icon_is_detected(self):
        self.install_current()
        icon = self.base / 'Icon/app.png'
        icon.parent.mkdir()
        icon.write_bytes(b'original icon')
        state = updater.read_state(self.base)
        state['installed_hashes'] = updater.content_manifest(self.base)
        updater.write_state(self.base, state)
        icon.write_bytes(b'changed icon')
        self.assertFalse(updater.matches_manifest(self.base, state['installed_hashes']))

    def test_incomplete_archive_rejected(self):
        with self.assertRaises(ValueError):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as z:
                z.writestr('repo/folder.pyw', '# incomplete')
            updater.unpack(output.getvalue(), self.base)


if __name__ == '__main__':
    unittest.main()
