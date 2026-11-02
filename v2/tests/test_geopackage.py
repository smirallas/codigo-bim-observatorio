from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
from archive import Archive
from geopackage import wkb,import_roads


class GeoPackageTests(unittest.TestCase):
    def test_header_envelope_crs_and_invalid_flags(self):
        body=b'GP\x00\x01'+struct.pack('<i',4258)+b'WKB'
        self.assertEqual(wkb(body),b'WKB')
        envelope=b'GP\x00\x03'+struct.pack('<i',4258)+b'0'*32+b'WKB'
        self.assertEqual(wkb(envelope),b'WKB')
        for invalid in [body[:7],body.replace(b'GP',b'XX'),b'GP\x00\x01'+struct.pack('<i',4326)+b'WKB',body[:3]+b'\x11'+body[4:]]:
            with self.assertRaises(ValueError):wkb(invalid)

    def test_import_preserves_original_and_shared_segment_aliases(self):
        archive=Archive(os.environ['DATABASE_URL']);archive.migrate();identifier=None
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'fixture.gpkg';original=Path(temp)/'source.zip';original.write_bytes(b'synthetic original fixture')
            line=struct.pack('<BIIdddd',1,2,2,160,-40,160,-39.99)
            geometry=b'GP\x00\x01'+struct.pack('<i',4258)+line
            source=sqlite3.connect(path)
            source.execute('CREATE TABLE gpkg_geometry_columns(table_name,column_name,geometry_type_name,srs_id)')
            source.execute("INSERT INTO gpkg_geometry_columns VALUES('rt_tramo_vial','geometry','LINESTRING',4258)")
            source.execute('CREATE TABLE rt_tramo_vial(fid INTEGER PRIMARY KEY,geometry BLOB,id_tramo INTEGER,codigo TEXT)')
            source.executemany('INSERT INTO rt_tramo_vial VALUES(?,?,?,?)',[(1,geometry,1,'A-1'),(2,geometry,1,'N-1')]);source.commit();source.close()
            try:
                result=import_roads(archive,path,original);identifier=result['id']
                with archive.connect() as db:
                    self.assertEqual(db.execute('SELECT segments FROM network_imports WHERE id=%s',(identifier,)).fetchone()['segments'],1)
                    self.assertEqual(db.execute('SELECT count(*) AS n FROM network_aliases WHERE import_id=%s',(identifier,)).fetchone()['n'],2)
                    asset=db.execute('SELECT original,sha256 FROM network_assets WHERE import_id=%s',(identifier,)).fetchone()
                    self.assertEqual(bytes(asset['original']),original.read_bytes())
                    self.assertEqual(asset['sha256'],hashlib.sha256(original.read_bytes()).hexdigest())
            finally:
                if identifier:
                    with archive.connect() as db:db.execute('DELETE FROM network_imports WHERE id=%s',(identifier,))
