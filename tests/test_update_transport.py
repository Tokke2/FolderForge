import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import updater


class Response(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_streaming_progress_with_known_length(self):
        body = b'x' * 150000
        progress = []
        with patch.object(updater, 'urlopen', return_value=Response(body, {'Content-Length': str(len(body))})):
            self.assertEqual(updater.fetch('https://api.github.com/test', 200000,
                                           progress=lambda count, total: progress.append((count, total))), body)
        self.assertEqual(progress[0], (0, len(body)))
        self.assertEqual(progress[-1], (len(body), len(body)))
        self.assertGreater(len(progress), 2)

    def test_unknown_length_still_respects_download_limit(self):
        with patch.object(updater, 'urlopen', return_value=Response(b'x' * 30)):
            with self.assertRaises(ValueError):
                updater.fetch('https://api.github.com/test', 20)

    def test_declared_oversize_rejected_before_read(self):
        with patch.object(updater, 'urlopen', return_value=Response(b'x', {'Content-Length': '1000'})):
            with self.assertRaises(ValueError):
                updater.fetch('https://api.github.com/test', 20)

    def test_transient_network_failure_retried(self):
        with patch.object(updater, 'urlopen', side_effect=[URLError('offline'), Response(b'ok')]) as request, \
                patch.object(updater.time, 'sleep'):
            self.assertEqual(updater.fetch('https://api.github.com/test', 20), b'ok')
            self.assertEqual(request.call_count, 2)

    def test_permanent_404_not_retried(self):
        error = HTTPError('https://api.github.com/test', 404, 'Not Found', {}, None)
        with patch.object(updater, 'urlopen', side_effect=error) as request, patch.object(updater.time, 'sleep'):
            with self.assertRaises(HTTPError):
                updater.fetch('https://api.github.com/test', 20)
            self.assertEqual(request.call_count, 1)

    def test_incomplete_body_retried(self):
        with patch.object(updater, 'urlopen', side_effect=[Response(b'a', {'Content-Length': '3'}), Response(b'abc')]), \
                patch.object(updater.time, 'sleep'):
            self.assertEqual(updater.fetch('https://api.github.com/test', 20), b'abc')

    def test_attempts_are_bounded(self):
        with patch.object(updater, 'urlopen', side_effect=URLError('offline')) as request, patch.object(updater.time, 'sleep'):
            with self.assertRaises(URLError):
                updater.fetch('https://api.github.com/test', 20)
            self.assertEqual(request.call_count, 3)

    def test_failed_atomic_state_write_preserves_old_state(self):
        updater.write_state(self.base, {'status': 'checked'})
        with patch.object(updater.os, 'replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError):
                updater.write_state(self.base, {'status': 'checking'})
        self.assertEqual(updater.read_state(self.base), {'status': 'checked'})
        self.assertEqual(list((self.base / 'data').glob('*.tmp')), [])

    def test_recover_previous_pending_after_interrupted_stage(self):
        from test_updater import archive
        previous = self.base / 'data/update-pending-previous'
        previous.mkdir(parents=True)
        updater.unpack(archive(), previous)
        state = {'pending': 'v0.0.2', 'pending_hashes': updater.content_manifest(previous)}
        updater.recover_pending(self.base, state)
        self.assertTrue(updater.matches_manifest(self.base / 'data/update-pending', state['pending_hashes']))
        self.assertFalse(previous.exists())

    def test_aborted_check_retries_without_waiting_twelve_hours(self):
        updater.write_state(self.base, {'status': 'downloading', 'last_check': 100000})
        with patch.object(updater, 'fetch', return_value=json.dumps({'tag_name': 'v0.0.1'}).encode()) as request:
            updater.check_once(self.base, '0.0.2', now=100001)
            request.assert_called_once()

    def test_failed_stage_keeps_previous_valid_download(self):
        from test_updater import archive, COMMIT, REVISION
        pending = self.base / 'data/update-pending'
        pending.mkdir(parents=True)
        updater.unpack(archive(), pending)
        hashes = updater.content_manifest(pending)
        updater.write_state(self.base, {'pending': 'v0.0.2', 'pending_revision': 'b' * 40,
                                       'pending_hashes': hashes})
        original = updater.os.replace
        previous = self.base / 'data/update-pending-previous'
        def replace(source, destination):
            if Path(destination) == pending and Path(source) != previous:
                raise OSError('staging locked')
            return original(source, destination)
        release = json.dumps({'tag_name': 'v0.0.2'}).encode()
        with patch.object(updater, 'fetch', side_effect=[release, COMMIT, archive()]),                 patch.object(updater.os, 'replace', side_effect=replace):
            with self.assertRaises(OSError):
                updater.check_once(self.base, '0.0.2', now=100000)
        self.assertTrue(updater.matches_manifest(pending, hashes))
        self.assertEqual(updater.read_state(self.base)['pending_revision'], 'b' * 40)

    def test_activity_reports_progress_without_network(self):
        updater.write_state(self.base, {'downloaded': 30, 'download_total': 100, 'status': 'downloading'})
        with updater._check_lock, patch.object(updater, 'fetch') as fetch:
            activity = updater.get_update_activity(self.base)
            self.assertTrue(activity['busy'])
            self.assertEqual(activity['progress'], 0.3)
            fetch.assert_not_called()

    def test_rate_limit_message_is_actionable(self):
        error = HTTPError('https://api.github.com/test', 429, 'rate limit', {}, None)
        with patch.object(updater, 'fetch', side_effect=error):
            with self.assertRaises(HTTPError):
                updater.check_once(self.base, '0.0.2', force=True)
        self.assertIn('begränsar', updater.read_state(self.base)['error'])
