from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4
from archive import Archive
from collector import collect_one, public_url
from demo import AT, layers
from sources import ADAPTERS, rail
from unittest.mock import patch
NOW = datetime.now(timezone.utc)

class AdapterTests(unittest.TestCase):

    def test_rail_missing_time_and_speed_remain_unknown(self):
        body = b'{"header":{"timestamp":"1793542287"},"entity":[{"id":"a","vehicle":{"position":{"latitude":40,"longitude":-3}}}]}'
        features, published = rail(body, AT)
        self.assertIsNone(features[0]['properties']['observed_at'])
        self.assertIsNone(features[0]['properties']['speed_m_s'])
        self.assertIsNotNone(published)

    def test_collector_failure_keeps_other_sources_independent(self):
        archive = unittest.mock.Mock()
        with patch('collector.download', side_effect=TimeoutError):
            result = collect_one(archive, 'rail')
        self.assertEqual(result['status'], 'error')
        archive.add.assert_not_called()
        archive.attempt.assert_called_once()

    def test_provenance_does_not_store_url_secrets(self):
        url = public_url('https://user:secret@example.org/data?bbox=1&api_key=secret&token=secret')
        self.assertEqual(url, 'https://example.org/data?bbox=1')

class DatabaseTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.archive = Archive(os.environ['DATABASE_URL'])
        cls.archive.migrate()

    def setUp(self):
        self.source = 'test-' + uuid4().hex

    def tearDown(self):
        with self.archive.connect() as db:
            db.execute('DELETE FROM captures WHERE source=%s', (self.source,))

    def add(self, received=None, features=None, published=None, kind='synthetic'):
        return self.archive.add(self.source, received or NOW, b'original exacto', features or layers()['rail'], kind, published)

    def test_original_hash_postgis_and_idempotent_capture(self):
        first = self.add()
        second = self.add()
        self.assertEqual(first['id'], second['id'])
        with self.archive.connect() as db:
            row = db.execute('SELECT original,sha256 FROM captures WHERE id=%s', (first['id'],)).fetchone()
            self.assertEqual(bytes(row['original']), b'original exacto')
            self.assertEqual(row['sha256'], hashlib.sha256(b'original exacto').hexdigest())
            self.assertEqual(db.execute('SELECT ST_SRID(geometry) AS srid FROM features WHERE capture_id=%s', (first['id'],)).fetchone()['srid'], 4326)

    def test_replay_excludes_late_capture_and_future_publication(self):
        self.add(received=NOW + timedelta(minutes=1))
        self.assertIsNone(self.archive.latest(self.source, NOW))
        self.add(received=NOW, published=NOW + timedelta(minutes=1))
        self.assertIsNone(self.archive.latest(self.source, NOW))

    def test_future_individual_observation_is_not_available(self):
        features = deepcopy(layers()['rail'])
        features[0]['properties']['observed_at'] = (NOW + timedelta(hours=1)).isoformat()
        self.add(features=features)
        self.assertEqual(self.archive.latest(self.source, NOW)['features'], [])

    def test_bbox_filters_postgis_geometry(self):
        self.add()
        self.assertEqual(len(self.archive.latest(self.source, NOW, [-4, 39, -3, 40])['features']), 1)
        self.assertEqual(self.archive.latest(self.source, NOW, [0, 0, 1, 1])['features'], [])

    def test_malformed_geometry_rolls_back_whole_capture(self):
        features = deepcopy(layers()['rail'])
        features.append({'geometry': {'type': 'LineString', 'coordinates': [[0, 0]]}, 'properties': {}})
        with self.assertRaises(Exception):
            self.add(features=features)
        self.assertIsNone(self.archive.latest(self.source, NOW))

    def test_migration_repeated_and_constraint_enforced(self):
        self.archive.migrate()
        with self.assertRaises(Exception):
            self.add(kind='invented')
        self.assertIsNone(self.archive.latest(self.source, NOW))

    def test_retention_removes_old_and_excess_captures_only_for_test_source(self):
        self.add(received=NOW - timedelta(days=8))
        for seconds in (3, 2, 1):
            self.add(received=NOW - timedelta(seconds=seconds))
        self.archive.prune(days=7, max_per_source=2, source=self.source)
        with self.archive.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) AS total FROM captures WHERE source=%s', (self.source,)).fetchone()['total'], 2)
if __name__ == '__main__':
    unittest.main()
