from datetime import datetime,timedelta,timezone
import os
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,MagicMock,patch
from uuid import uuid4
from archive import Archive
from collector import source_interval,collect_one
from weather_maps import LAYERS,parse_metadata,times,image,valid_times,payload


def capabilities():
    rows=[]
    for item in LAYERS.values():
        rows.append(f'''<Layer><Name>{item['layer']}</Name><Dimension name="time">2026-11-01T00:00:00Z/2026-11-05T00:00:00Z/PT3H</Dimension><Dimension name="REFERENCE_TIME">2026-11-01T00:00:00Z,2099-01-01T00:00:00Z</Dimension><Style><Name>valid_style</Name></Style></Layer>''')
    return ('<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability>'+''.join(rows)+'</Capability></WMS_Capabilities>').encode()


class LiveWeatherTests(unittest.TestCase):
    def test_times_expand_explicit_intervals_and_reject_unbounded(self):
        self.assertEqual(len(times('2026-11-01T00:00:00Z/2026-11-01T06:00:00Z/PT3H')),3)
        with self.assertRaises(ValueError):times('2026-11-01T00:00:00Z/2099-01-01T00:00:00Z/PT1H')
        with self.assertRaises(ValueError):times('2026-11-01T00:00:00Z/2026-11-01T06:00:00Z/PT0H')

    def test_future_model_runs_excluded_old_run_marked_stale(self):
        result=parse_metadata(capabilities(),datetime(2026,11,2,tzinfo=timezone.utc))
        self.assertEqual(len(result['maps']),3)
        for item in result['maps']:
            self.assertEqual(item['run_at'],'2026-11-01T00:00:00+00:00')
            self.assertTrue(item['model_stale'])
        self.assertIn('6 h',result['maps'][1]['title'])

    def test_bad_xml_and_missing_required_forecast_layer_rejected(self):
        for body in [b'<!DOCTYPE x><x/>',b'<x/>',capabilities().replace(b'PT3H',b'PT0H')]:
            with self.assertRaises(ValueError):parse_metadata(body)

    def test_model_horizon_and_six_hour_rain_are_not_cartesian_dimensions(self):
        item={'id':'rain','run_at':'2026-11-02T06:00:00Z','times':[
            '2026-11-02T12:00:00Z','2026-11-02T15:00:00Z','2026-11-02T18:00:00Z','2026-11-09T12:00:00Z']}
        self.assertEqual(valid_times(item),['2026-11-02T12:00:00Z','2026-11-02T18:00:00Z'])

    def test_arbitrary_weather_layer_or_tile_cannot_trigger_provider(self):
        with patch('weather_maps.urllib.request.urlopen') as download:
            with self.assertRaises(ValueError):image(Mock(),1,'untrusted','',0,0,0)
            with self.assertRaises(ValueError):image(Mock(),1,'temperature','',20,0,0)
        download.assert_not_called()

    def test_per_source_intervals_minimum_and_error_backoff(self):
        with patch.dict(os.environ,{'RAIL_INTERVAL':'1','DGT_INTERVAL':'120'}):
            self.assertEqual(source_interval('rail'),30)
            self.assertEqual(source_interval('dgt'),120)
            self.assertEqual(source_interval('dgt',1),240)
            self.assertEqual(source_interval('dgt',10),900)
        self.assertGreaterEqual(source_interval('weather'),1800)

    def test_weather_map_failure_does_not_discard_archived_metadata(self):
        archive=Mock()
        with patch('weather_maps.collect_metadata',side_effect=TimeoutError):
            self.assertEqual(collect_one(archive,'weather_maps')['status'],'error')
        archive.add.assert_not_called();archive.attempt.assert_called_once()

    def test_later_receipt_of_older_catalog_cannot_roll_model_back(self):
        archive=Archive(os.environ['DATABASE_URL']);source='test-weather-'+uuid4().hex;now=datetime.now(timezone.utc)
        newer=parse_metadata(capabilities(),datetime(2026,11,2,tzinfo=timezone.utc))
        older=parse_metadata(capabilities().replace(b'2026-11-01',b'2026-10-31'),datetime(2026,11,2,tzinfo=timezone.utc))
        try:
            first=archive.add(source,now-timedelta(seconds=10),b'newer',[],'forecast',metadata=newer)
            archive.add(source,now,b'older',[],'forecast',metadata=older)
            self.assertEqual(payload(archive,source)['capture_id'],first['id'])
        finally:
            with archive.connect() as db:db.execute('DELETE FROM captures WHERE source=%s',(source,))

    def test_broken_wind_legend_does_not_block_map_tiles(self):
        archive=MagicMock();archive.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={
            'metadata':{'maps':[{'id':'wind','run_at':'2026-11-01T00:00:00Z','times':['2026-11-01T01:00:00Z'],'style':'example'}]}}
        with tempfile.TemporaryDirectory() as folder,patch('weather_maps.CACHE',Path(folder)),patch('weather_maps.urllib.request.urlopen',side_effect=[io.BytesIO(b'<ServiceException/>'),io.BytesIO(b'\x89PNG\r\n\x1a\nfixture')]):
            with self.assertRaises(ValueError):image(archive,987654321,'wind','2026-11-01T01:00:00Z',legend=True)
            self.assertTrue(image(archive,987654321,'wind','2026-11-01T01:00:00Z',0,0,0).startswith(b'\x89PNG'))
