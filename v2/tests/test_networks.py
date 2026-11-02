from datetime import datetime,timedelta,timezone
import io
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from psycopg.types.json import Jsonb
from archive import Archive
from networks import parse_page,associate,import_network
from schedule import lookup
from server import feature_payload
from sources import rail


def gml(identifier='a',srs='EPSG:25830'):
    return f'''<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:n="urn:test"><wfs:member><n:RailwayLink gml:id="{identifier}"><n:fictitious>true</n:fictitious><n:geometry><gml:LineString srsName="{srs}"><gml:posList>500000 4400000 500010 4400010</gml:posList></gml:LineString></n:geometry></n:RailwayLink></wfs:member></wfs:FeatureCollection>'''.encode()


class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive=Archive(os.environ['DATABASE_URL']);cls.archive.migrate()

    def setUp(self):
        self.imports=[];self.captures=[];self.schedules=[]
        self.now=datetime.now(timezone.utc)
        self.point={'type':'Point','coordinates':[160,-40]}

    def tearDown(self):
        with self.archive.connect() as db:
            for identifier in self.imports:db.execute('DELETE FROM network_imports WHERE id=%s',(identifier,))
            for identifier in self.captures:db.execute('DELETE FROM captures WHERE id=%s',(identifier,))
            for identifier in self.schedules:db.execute('DELETE FROM schedule_imports WHERE id=%s',(identifier,))

    def dataset(self,status='complete',future=False):
        with self.archive.connect() as db:
            identifier=db.execute('''INSERT INTO network_imports(kind,source_url,coverage,status,completed_at)
                VALUES('railway','fixture',ST_MakeEnvelope(159,-41,161,-39,4326),%s,%s) RETURNING id''',
                (status,self.now+timedelta(hours=1) if future else self.now-timedelta(seconds=1))).fetchone()['id']
        self.imports.append(identifier);return identifier

    def segment(self,identifier,key='a',lon=160,fictitious=False):
        with self.archive.connect() as db:
            db.execute('''INSERT INTO network_segments(import_id,segment_id,geometry,attributes,fictitious)
                VALUES(%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),'{}',%s)''',
                (identifier,key,json.dumps({'type':'LineString','coordinates':[[lon,-40.001],[lon,-39.999]]}),fictitious))

    def test_parser_keeps_xy_and_fictitious(self):
        item=parse_page(gml())[0]
        self.assertEqual(item['geometry']['coordinates'][0],[500000,4400000])
        self.assertIs(item['fictitious'],True)
        for body in [gml(srs='EPSG:4326'),b'<!DOCTYPE x><x/>',gml().replace(b'500000',b'nan')]:
            with self.assertRaises(ValueError):parse_page(body)

    def test_nearest_is_only_candidate_never_physical_track(self):
        identifier=self.dataset();self.segment(identifier,lon=160.0001)
        result=associate(self.archive,'rail',self.point,self.now)
        self.assertEqual(result['status'],'candidate');self.assertFalse(result['physical_track_identified'])
        self.assertGreater(result['candidates'][0]['distance_m'],8)
        self.assertLess(result['candidates'][0]['distance_m'],9)

    def test_parallel_segments_are_ambiguous(self):
        identifier=self.dataset();self.segment(identifier);self.segment(identifier,'b',160.0001)
        self.assertEqual(associate(self.archive,'rail',self.point,self.now)['status'],'ambiguous')

    def test_fictitious_link_not_assigned_as_track(self):
        identifier=self.dataset();self.segment(identifier,fictitious=True)
        self.assertEqual(associate(self.archive,'rail',self.point,self.now)['status'],'reference_only')

    def test_no_candidate_and_no_complete_coverage_differ(self):
        identifier=self.dataset();self.segment(identifier,lon=160.01)
        self.assertEqual(associate(self.archive,'rail',self.point,self.now)['status'],'not_found')
        self.assertEqual(associate(self.archive,'rail',{'type':'Point','coordinates':[150,-30]},self.now)['status'],'outside_coverage')

    def test_failed_and_future_imports_cannot_support_a_replay(self):
        for status,future in [('failed',False),('complete',True)]:
            self.segment(self.dataset(status,future))
        self.assertEqual(associate(self.archive,'rail',self.point,self.now)['status'],'outside_coverage')

    def test_exact_feature_and_availability_no_train_number_join(self):
        properties={'id':'same-number','track_id':None,'observed_at':None}
        result=self.archive.add('rail',self.now,b'fixture'+uuid4().bytes,[{'geometry':self.point,'properties':properties}])
        self.captures.append(result['id'])
        self.assertIsNone(feature_payload(self.archive,'dgt',result['id'],0,self.now))
        self.assertIsNone(feature_payload(self.archive,'rail',result['id'],1,self.now))
        self.assertIsNone(feature_payload(self.archive,'rail',result['id'],0,self.now-timedelta(seconds=1)))
        detail=feature_payload(self.archive,'rail',result['id'],0,self.now)
        self.assertIsNone(detail['feature']['properties']['track_id'])
        self.assertEqual(detail['capture']['id'],result['id'])

    def test_schedule_exact_trip_no_match_by_number_or_other_date(self):
        with self.archive.connect() as db:
            identifier=db.execute("INSERT INTO schedule_imports(source_url,sha256,original) VALUES('fixture',%s,%s) RETURNING id",('0'*64,b'fixture')).fetchone()['id']
            self.schedules.append(identifier)
            db.execute('INSERT INTO schedule_stops VALUES(%s,%s,%s)',(identifier,'S1','Estación de ejemplo'))
            db.execute('INSERT INTO schedule_trips VALUES(%s,%s,%s)',(identifier,'123-2099-01-01',Jsonb({'service_name':'Prueba'})))
        at=datetime.now(timezone.utc)
        result=lookup(self.archive,{'stop_id':'S1','trip_id':'123-2099-01-02'},at)
        self.assertEqual(result['stop_name'],'Estación de ejemplo');self.assertIsNone(result['trip'])
        self.assertEqual(result['match'],'no_exact_trip')
        self.assertEqual(lookup(self.archive,{'trip_id':'123-2099-01-01'},at)['match'],'exact')
        self.assertEqual(lookup(self.archive,{},datetime(2000,1,1,tzinfo=timezone.utc))['status'],'unavailable')

    def test_rail_preserves_context_without_inventing_speed_or_timestamp(self):
        body=json.dumps({'entity':[{'id':'x','vehicle':{'trip':{'tripId':'T1'},'stopId':'S1','currentStatus':'STOPPED_AT','position':{'longitude':-3,'latitude':40}}}]})
        p=rail(body,self.now.isoformat())[0][0]['properties']
        self.assertEqual(p['trip_id'],'T1');self.assertEqual(p['stop_id'],'S1')
        self.assertIsNone(p['observed_at']);self.assertIsNone(p['speed_m_s']);self.assertIsNone(p['track_id'])

    def test_import_checks_hits_and_continues_when_server_caps_page(self):
        def response(body):
            stream=io.BytesIO(body);stream.headers={};return stream
        replies=[response(b'<FeatureCollection numberMatched="2"/>'),response(gml('a')),response(gml('b'))]
        with patch('networks.urllib.request.urlopen',side_effect=replies),patch('networks.time.sleep'):
            result=import_network(self.archive,'railway',[159,-41,161,-39])
        self.imports.append(result['id']);self.assertEqual(result['status'],'complete')
        with self.archive.connect() as db:
            count=db.execute('SELECT segments FROM network_imports WHERE id=%s',(result['id'],)).fetchone()['segments']
        self.assertEqual(count,2)
