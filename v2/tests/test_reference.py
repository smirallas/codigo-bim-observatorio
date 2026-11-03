import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import reference


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        reference._failed.clear()

    def test_xyz_bounds_and_wms_axis_order(self):
        west,south,east,north=reference.tile_bbox(0,0,0)
        self.assertAlmostEqual(east,math.pi*6378137)
        self.assertEqual(west,-east);self.assertEqual(south,-north)
        query=parse_qs(urlsplit(reference.tile_url('railway',7,62,48)).query)
        self.assertEqual(query['SRS'],['EPSG:3857'])
        self.assertEqual(query['VERSION'],['1.1.1'])
        self.assertEqual(query['LAYERS'],['TN.RailTransportNetwork.RailwayLink'])

    def test_arbitrary_layers_and_invalid_tiles_cannot_trigger_downloads(self):
        with patch('reference.urllib.request.urlopen') as fetch:
            for args in [('custom',0,0,0),('railway',16,0,0),('highways',0,1,0),('railway',1,0,-1)]:
                with self.subTest(args=args),self.assertRaises(ValueError):reference.tile(*args)
        fetch.assert_not_called()

    def test_cached_png_avoids_request_and_stale_cache_survives_outage(self):
        with tempfile.TemporaryDirectory() as folder,patch('reference.CACHE',Path(folder)):
            file=Path(folder)/'railway-0-0-0.png';file.write_bytes(reference.PNG+b'fixture')
            with patch('reference.urllib.request.urlopen') as fetch:
                body,status=reference.tile('railway',0,0,0)
                self.assertEqual(status,'cache');fetch.assert_not_called()
            with patch('reference.TTL',-1),patch('reference.urllib.request.urlopen',side_effect=OSError):
                body,status=reference.tile('railway',0,0,0)
                self.assertEqual(status,'stale-cache')
                self.assertTrue(body.startswith(reference.PNG))

    def test_xml_exception_is_not_saved_as_png_and_outage_is_throttled(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'<ServiceException>Unavailable</ServiceException>'
        with tempfile.TemporaryDirectory() as folder,patch('reference.CACHE',Path(folder)),patch('reference.urllib.request.urlopen',return_value=Response()) as fetch:
            with self.assertRaises(ValueError):reference.tile('railway',0,0,0)
            with self.assertRaises(OSError):reference.tile('railway',1,0,0)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(list(Path(folder).glob('*.png')),[])


if __name__=='__main__':unittest.main()
