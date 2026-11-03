"""Datos sintéticos de prueba; los productos reales se comprueban aparte por HTTP."""
from datetime import datetime,timezone
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import numpy as np
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from weather_maps import parse_package,image,raster_path,payload,collect_metadata,LAYERS

VALID='2026-11-03T12:00:00+00:00'

def package(bad_date=False):
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for key,item in LAYERS.items():
            with MemoryFile() as memory:
                with memory.open(driver='GTiff',height=4,width=4,count=4,dtype='uint8',crs='EPSG:4326',transform=from_bounds(-11,34,5,45,4,4)) as raster:
                    data=np.full((4,4,4),150,dtype='uint8');data[3]=255;raster.write(data)
                    raster.update_tags(FUENTE='AEMET',FECHA='2026-11-03T11:00:00+00:00' if bad_date else VALID,
                       ESCALA="{'Lista RGBA':[{'Valores':[0,10],'RGBA':['1','2','3','255']}]}")
                data=memory.read()
            member=tarfile.TarInfo('down_'+VALID+'_'+item['suffix']+'.tif');member.size=len(data);member.mtime=1793700000
            archive.addfile(member,io.BytesIO(data))
    return buffer.getvalue()

class AemetTests(unittest.TestCase):
    def test_identical_package_is_not_archived_again(self):
        archive=MagicMock();archive.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'id':123}
        with patch('weather_maps.urllib.request.urlopen',side_effect=[io.BytesIO(package()),io.BytesIO(package())]):
            result=collect_metadata(archive)
        self.assertEqual(result['status'],'cached');self.assertEqual(result['id'],123)
        archive.add.assert_not_called()

    def test_domain_failure_does_not_publish_partial_replacement(self):
        archive=MagicMock()
        with patch('weather_maps.urllib.request.urlopen',side_effect=[io.BytesIO(package()),TimeoutError]):
            with self.assertRaises(TimeoutError):collect_metadata(archive)
        archive.add.assert_not_called()

    def test_package_keeps_explicit_validity_scales_and_all_three_fields(self):
        files,scales,generated=parse_package(package(),'PB')
        self.assertEqual(set(scales),set(LAYERS));self.assertEqual(len(files),3)
        self.assertEqual({valid for key,valid in files},{VALID});self.assertTrue(generated)

    def test_wrong_date_missing_fields_and_untrusted_region_rejected(self):
        with self.assertRaises(ValueError):parse_package(package(True),'PB')
        with self.assertRaises(ValueError):parse_package(package(),'arbitrary')
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w:gz'):pass
        with self.assertRaises(ValueError):parse_package(out.getvalue(),'PB')

    def test_invalid_requests_do_not_open_provider_or_database(self):
        archive=MagicMock()
        for args in [('bad','',0,0,0),('temperature',VALID,18,0,0)]:
            with self.assertRaises(ValueError):image(archive,1,*args)
        with self.assertRaises(ValueError):raster_path(archive,1,'../secret')
        archive.connect.assert_not_called()

    def test_unknown_validity_rejected_before_reading_raster(self):
        archive=MagicMock();archive.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'metadata':{'maps':[{'id':'temperature','times':[VALID]}]}}
        with patch('weather_maps.raster_path') as source:
            with self.assertRaises(ValueError):image(archive,1,'temperature','2099-01-01T00:00:00Z',0,0,0)
            source.assert_not_called()

    def test_reprojection_produces_transparency_outside_domain(self):
        files,scales,_=parse_package(package(),'PB');data=files[('temperature',VALID)][1]
        archive=MagicMock();archive.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'metadata':{'maps':[{'id':'temperature','times':[VALID],'rasters':{VALID:['ignored']}}]}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.tif';path.write_bytes(data)
            with patch('weather_maps.raster_path',return_value=path):
                inside=Image.open(io.BytesIO(image(archive,1,'temperature',VALID,5,15,12)))
                outside=Image.open(io.BytesIO(image(archive,1,'temperature',VALID,5,0,0)))
        self.assertTrue(inside.getchannel('A').getbbox());self.assertIsNone(outside.getchannel('A').getbbox())

    def test_no_aemet_capture_is_honestly_unavailable(self):
        archive=MagicMock();archive.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=None
        self.assertEqual(payload(archive)['status'],'unavailable')
