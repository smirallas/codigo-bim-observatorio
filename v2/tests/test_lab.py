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
from sources import ADAPTERS, dgt, flights, rail, roads, weather
from server import Handler, bbox_value, layer_payload
from engine import available, evaluate
from scenarios import all_scenarios, iso
from unittest.mock import patch
NOW = datetime.now(timezone.utc)

class AdapterTests(unittest.TestCase):

    def test_rail_missing_time_and_speed_remain_unknown(self):
        body = b'{"header":{"timestamp":"1793542287"},"entity":[{"id":"a","vehicle":{"position":{"latitude":40,"longitude":-3}}}]}'
        features, published = rail(body, AT)
        self.assertIsNone(features[0]['properties']['observed_at'])
        self.assertIsNone(features[0]['properties']['speed_m_s'])
        self.assertIsNotNone(published)

    def test_flight_position_time_is_not_last_contact(self):
        state = ['abc', ' EXAMPLE ', 'ES', 1793542200, 1793542287, -3.8, 39.7, 8000, False, 200, 180, 0, None, 8100, None, False, 0]
        features, published = flights(json.dumps({'time': 1793542287, 'states': [state]}), AT)
        self.assertNotEqual(features[0]['properties']['observed_at'], features[0]['properties']['contact_at'])
        state[5] = None
        self.assertEqual(flights(json.dumps({'time': 1793542287, 'states': [state]}), AT)[0], [])

    def test_flight_adsblol_units_and_relative_position_age(self):
        feed = {'now': 1793542287000, 'ac': [{'hex': 'synthetic', 'flight': 'SIM', 'lat': 39.7, 'lon': -3.8, 'seen_pos': 10, 'seen': 2, 'gs': 100, 'alt_baro': 10000, 'type': 'adsb_icao'}]}
        features, _ = flights(json.dumps(feed), AT)
        prop = features[0]['properties']
        self.assertAlmostEqual(prop['speed_m_s'], 51.44444444)
        self.assertEqual(prop['altitude_m'], 3048)
        self.assertNotEqual(prop['observed_at'], prop['contact_at'])
        self.assertEqual(prop['time_basis'], 'feed_now_minus_seen_pos')

    def test_weather_is_a_forecast_with_validity(self):
        body = json.dumps({'latitude': 39.7, 'longitude': -3.8, 'generationtime_ms': 25, 'hourly': {'time': [1793542200], 'temperature_2m': [14], 'precipitation': [2], 'wind_speed_10m': [5]}})
        features, published = weather(body, AT)
        self.assertIsNone(published)
        self.assertIsNone(features[0]['properties']['observed_at'])
        self.assertEqual(features[0]['properties']['kind'], 'forecast')

    def test_met_forecast_units_and_issuance(self):
        body = json.dumps({'geometry': {'coordinates': [-3.8, 39.7, 0]}, 'properties': {'meta': {'updated_at': AT}, 'timeseries': [{'time': AT, 'data': {'instant': {'details': {'air_temperature': 14, 'wind_speed': 10}}}}]}})
        features, published = weather(body, AT)
        self.assertEqual(features[0]['properties']['wind_km_h'], 36)
        self.assertIsNone(features[0]['properties']['precipitation_mm'])
        self.assertEqual(published, AT)

    def test_weather_expiry_avoids_another_provider_request(self):
        archive = unittest.mock.Mock()
        archive.latest.return_value = {'metadata': {'expires': 'Mon, 01 Nov 2094 18:00:00 GMT'}}
        with patch('collector.download') as fetch:
            self.assertEqual(collect_one(archive, 'weather')['status'], 'cached')
        fetch.assert_not_called()

    def test_datex_uses_explicit_coordinates_and_keeps_missing_observation(self):
        xml = b'<situationPublication xmlns="urn:test"><publicationTime>2026-11-01T12:00:00Z</publicationTime><situationRecord id="r1"><latitude>40.1</latitude><longitude>-3.8</longitude></situationRecord><situationRecord id="without"><roadNumber>A-4</roadNumber></situationRecord></situationPublication>'
        features, _ = dgt(xml, AT)
        self.assertEqual(len(features), 1)
        self.assertIsNone(features[0]['properties']['observed_at'])
        with self.assertRaises(ValueError):
            dgt(b'<!DOCTYPE x><situationPublication/>', AT)

    def test_road_import_and_invalid_latitude(self):
        feature = layers()['roads'][0]
        features, _ = roads(json.dumps({'type': 'FeatureCollection', 'features': [feature]}).encode(), AT)
        self.assertEqual(features[0]['geometry']['type'], 'LineString')
        feature['geometry']['coordinates'][0][1] = 200
        with self.assertRaises(ValueError):
            roads(json.dumps({'type': 'FeatureCollection', 'features': [feature]}).encode(), AT)

    def test_osm_only_imports_highways_and_preserves_geometry(self):
        xml = b'<osm><node id="1" lon="-3" lat="40"/><node id="2" lon="-3.1" lat="40.1"/><way id="3"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/><tag k="ref" v="A-X"/></way></osm>'
        features, _ = roads(xml, AT)
        self.assertEqual(features[0]['geometry']['coordinates'][1], [-3.1, 40.1])

    def test_bbox_rejects_nan_and_reversed_bounds(self):
        for value in ('nan,0,1,2', '3,4,1,2', '-200,0,1,2', '0,0,1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bbox_value(value)

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

    def test_oauth_credentials_are_not_in_report(self):
        archive = unittest.mock.Mock()
        archive.add.return_value = {'id': 1}
        with patch.dict(os.environ, {'FLIGHTS_PROVIDER': 'opensky', 'OPENSKY_CLIENT_ID': 'fixture-client', 'OPENSKY_CLIENT_SECRET': 'fixture-secret'}), patch('collector.download') as fetch:
            fetch.side_effect = [b'{"access_token":"fixture-token"}', b'{"time":1793542287,"states":[]}']
            result = collect_one(archive, 'flights')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(fetch.call_args.args[1], {'Authorization': 'Bearer fixture-token'})
        self.assertTrue(fetch.call_args.args[0].startswith('https://opensky-network.org/'))
        self.assertNotIn('fixture-secret', json.dumps(result))

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

    def test_forecast_validity_can_be_future_without_future_capture(self):
        feature = deepcopy(layers()['weather'][0])
        valid = NOW + timedelta(hours=1)
        feature['properties']['valid_at'] = valid.isoformat()
        mocked = unittest.mock.Mock()
        mocked.latest.return_value = {'features': [feature], 'received_at': NOW.isoformat(), 'kind': 'forecast'}
        result = layer_payload('weather', {'mode': ['archive'], 'valid_at': [valid.isoformat()]}, mocked)
        self.assertEqual(len(result['features']), 1)
        self.assertEqual(result['features'][0]['properties']['freshness'], 'forecast')

class RuleTests(unittest.TestCase):

    def test_scenario_outcomes_and_late_arrivals(self):
        expected = ['candidate', 'no_candidate', 'not_evaluable', 'not_evaluable', 'no_candidate', 'not_evaluable']
        for case, status in zip(all_scenarios(), expected):
            at = case['times'][-1]
            with self.subTest(case=case['id']):
                self.assertEqual(evaluate(case['events'], case['train_ids'], at)['status'], status)
        case = all_scenarios()[0]
        self.assertEqual(evaluate(case['events'], case['train_ids'], iso(0))['conditional_reference_reach_s'], 100)
        events = deepcopy(case['events'][:2])
        events[0]['received_at'] = iso(20)
        self.assertEqual(evaluate(events, case['train_ids'], iso(0))['status'], 'not_evaluable')

class HTTPTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}/v2'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        return urlopen(self.base + path, timeout=5)

    def test_health_and_real_layers_only(self):
        with self.get('/api/health') as response:
            self.assertEqual(json.load(response)['database'], 'postgresql-postgis')
            self.assertIsNone(response.headers.get('Set-Cookie'))
        with patch.object(Archive, 'latest', return_value=None):
            for source in ADAPTERS:
                with self.get('/api/layers/' + source) as response:
                    data = json.load(response)
                    self.assertEqual(data['status'], 'unavailable')
                    self.assertEqual(data['features'], [])

    def test_private_paths_and_bad_parameters(self):
        for path, status in [('/.env', 404), ('/../archive.py', 404), ('/api/layers/absent', 404), ('/api/layers/rail?bbox=nan,0,1,2', 400), ('/api/layers/rail?mode=whatever', 400), ('/api/replay?scenario=approach&step=99', 404), ('/api/scenarios', 404), ('/api/layers/rail?mode=demo', 400), ('/api/layers/rail?at=2026-11-01T00:00:00Z', 400), ('/api/layers/rail?at=', 400), ('/api/layers/weather?valid_at=2026-11-01T00:00:00Z', 400), ('/api/features/rail/1/0?at=2026-11-01T00:00:00Z', 400)]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, status)

    def test_embedding_policy_and_local_map_assets(self):
        with self.get('/') as response:
            self.assertIn('https://codigobim.com', response.headers['Content-Security-Policy'])
            self.assertIn('MapLibre', response.read().decode())
        for asset in ('maplibre-gl.mjs', 'maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs', 'maplibre-gl.css', 'app.js', 'domains.js', 'domains.css'):
            with self.get('/' + asset) as response:
                self.assertEqual(response.status, 200)
if __name__ == '__main__':
    unittest.main()
