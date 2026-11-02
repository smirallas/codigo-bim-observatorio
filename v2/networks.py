"""Importaciones WFS versionadas y asociación geométrica conservadora, sin asignar vías."""
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from psycopg.types.json import Jsonb

WFS='https://servicios.idee.es/wfs-inspire/transportes'
TYPES={'railway':'tn-ra:RailwayLink','highways':'tn-ro:RoadLink'}
GML='{http://www.opengis.net/gml/3.2}'
WFS_NS='{http://www.opengis.net/wfs/2.0}'


def parse_page(body):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('XML no admitido')
    root=ET.fromstring(body)
    if root.tag!=WFS_NS+'FeatureCollection':raise ValueError('No se recibió una colección WFS')
    segments=[]
    for member in root.findall(WFS_NS+'member'):
        for feature in member:
            identifier=feature.get(GML+'id')
            geometry=feature.find('.//'+GML+'LineString')
            if not identifier or geometry is None:raise ValueError('Enlace sin identificador o geometría lineal')
            srs=geometry.get('srsName','')
            if srs!='EPSG:25830':raise ValueError('CRS distinto del solicitado: '+srs)
            pos=geometry.find(GML+'posList')
            if pos is None or not pos.text:raise ValueError('Geometría vacía')
            dimension=int(pos.get('srsDimension',geometry.get('srsDimension','2')))
            values=[float(value) for value in pos.text.split()]
            if dimension not in (2,3) or len(values)%dimension or len(values)<dimension*2 or not all(math.isfinite(v) for v in values):raise ValueError('Coordenadas inválidas')
            coordinates=[values[i:i+2] for i in range(0,len(values),dimension)]
            attributes={}
            for item in feature.iter():
                if len(item)==0 and item.text and item.text.strip() and item.tag not in (GML+'posList',):
                    name=item.tag.rsplit('}',1)[-1]
                    if name not in attributes:attributes[name]=item.text.strip()
            fictitious={'true':True,'false':False}.get(attributes.get('fictitious','').lower())
            segments.append({'id':identifier,'geometry':{'type':'LineString','coordinates':coordinates},'attributes':attributes,'fictitious':fictitious})
    return segments


def import_network(archive,kind,bbox,page_size=5000,max_pages=5000,resume=None):
    if kind not in TYPES:raise ValueError('Tipo de red desconocido')
    west,south,east,north=bbox
    if not (-180<=west<east<=180 and -90<=south<north<=90):raise ValueError('Cobertura inválida')
    if not 1<=page_size<=5000:raise ValueError('Tamaño de página inválido')
    seen=set();offset=0;first_page=0
    with archive.connect() as db:
        if resume:
            row=db.execute('''SELECT id,status FROM network_imports WHERE id=%s AND kind=%s AND source_url=%s
                AND ST_Equals(coverage,ST_MakeEnvelope(%s,%s,%s,%s,4326))''',(resume,kind,WFS,*bbox)).fetchone()
            if not row or row['status']=='complete':raise ValueError('Importación no reanudable')
            identifier=row['id']
            for page in db.execute('SELECT page_index,original_gzip FROM network_pages WHERE import_id=%s ORDER BY page_index',(identifier,)).fetchall():
                items=parse_page(gzip.decompress(bytes(page['original_gzip'])))
                seen.add(hashlib.sha256(json.dumps([item['id'] for item in items]).encode()).hexdigest())
                offset+=len(items);first_page=page['page_index']+1
            db.execute("UPDATE network_imports SET status='loading',error_type=NULL WHERE id=%s",(identifier,))
        else:
            identifier=db.execute('''INSERT INTO network_imports(kind,source_url,coverage)
                VALUES(%s,%s,ST_MakeEnvelope(%s,%s,%s,%s,4326)) RETURNING id''',(kind,WFS,*bbox)).fetchone()['id']
    try:
        params={'service':'WFS','version':'2.0.0','request':'GetFeature','typeNames':TYPES[kind],
                'resultType':'hits','bbox':','.join(map(str,bbox))+',urn:ogc:def:crs:OGC:1.3:CRS84'}
        with urllib.request.urlopen(WFS+'?'+urllib.parse.urlencode(params),timeout=300) as response:
            expected=int(ET.fromstring(response.read(1_000_000)).get('numberMatched'))
        with archive.connect() as db:db.execute('UPDATE network_imports SET expected_segments=%s WHERE id=%s',(expected,identifier))
        print(json.dumps({'import_id':identifier,'expected':expected,'resume_offset':offset}),flush=True)
        for page in range(first_page,first_page+max_pages):
            params={'service':'WFS','version':'2.0.0','request':'GetFeature','typeNames':TYPES[kind],
                'count':page_size,'startIndex':offset,'srsName':'EPSG:25830',
                'outputFormat':'application/gml+xml; version=3.2',
                'bbox':','.join(map(str,bbox))+',urn:ogc:def:crs:OGC:1.3:CRS84'}
            request=urllib.request.Request(WFS+'?'+urllib.parse.urlencode(params),headers={
                'User-Agent':'CodigoBIM-NetworkImport/2.2 https://codigobim.com/','Accept-Encoding':'gzip'})
            for retry in range(3):
                try:
                    with urllib.request.urlopen(request,timeout=300) as response:
                        body=response.read(15_000_001);encoding=response.headers.get('Content-Encoding')
                    if len(body)>15_000_000:raise ValueError('Página demasiado grande')
                    if encoding=='gzip':
                        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:body=stream.read(40_000_001)
                    if len(body)>40_000_000:raise ValueError('Página descomprimida demasiado grande')
                    break
                except OSError:
                    if retry==2:raise
                    time.sleep(2+retry*2)
            segments=parse_page(body)
            fingerprint=hashlib.sha256(json.dumps([item['id'] for item in segments]).encode()).hexdigest()
            if segments and fingerprint in seen:raise ValueError('El servidor repite una página; importación incompleta')
            seen.add(fingerprint)
            with archive.connect() as db:
                db.execute('INSERT INTO network_pages VALUES(%s,%s,%s,%s)',(identifier,page,hashlib.sha256(body).hexdigest(),gzip.compress(body)))
                with db.cursor() as cursor:
                    cursor.executemany('''INSERT INTO network_segments VALUES(%s,%s,
                        ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),25830),4326),%s,%s) ON CONFLICT DO NOTHING''',
                        [(identifier,item['id'],json.dumps(item['geometry']),Jsonb(item['attributes']),item['fictitious']) for item in segments])
                db.execute('UPDATE network_imports SET pages=%s,segments=(SELECT count(*) FROM network_segments WHERE import_id=%s) WHERE id=%s',(page+1,identifier,identifier))
            print(json.dumps({'import_id':identifier,'kind':kind,'page':page,'features':len(segments)}),flush=True)
            offset+=len(segments)
            if not segments or offset>=expected:
                with archive.connect() as db:
                    count=db.execute('SELECT segments FROM network_imports WHERE id=%s',(identifier,)).fetchone()['segments']
                    if count!=expected or offset!=expected:raise ValueError('El total importado no coincide con el recuento oficial; no se declara completo')
                    db.execute("UPDATE network_imports SET status='complete',completed_at=now() WHERE id=%s",(identifier,))
                return {'id':identifier,'status':'complete','kind':kind,'bbox':bbox,'pages':page+1}
            time.sleep(0.25)
        raise ValueError('Se alcanzó el límite de páginas; no se declara completa')
    except Exception as error:
        with archive.connect() as db:db.execute("UPDATE network_imports SET status='failed',error_type=%s WHERE id=%s",(type(error).__name__,identifier))
        raise


def associate(archive,source,geometry,at=None,radius=120):
    if source not in ('rail','dgt') or geometry.get('type')!='Point':return {'status':'not_applicable','candidates':[]}
    kind='railway' if source=='rail' else 'highways'
    cutoff=at or datetime.now(timezone.utc)
    point=json.dumps(geometry)
    with archive.connect() as db:
        dataset=db.execute('''SELECT id,completed_at,source_url,metadata FROM network_imports
            WHERE kind=%s AND status='complete' AND completed_at<=%s
            AND ST_Covers(coverage,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) ORDER BY completed_at DESC,id DESC LIMIT 1''',(kind,cutoff,point)).fetchone()
        if not dataset:
            return {'status':'outside_coverage','physical_track_identified':False,'candidates':[],
                    'message':'No hay una importación completa disponible para esta zona y este instante.'}
        candidates=db.execute('''SELECT segment_id,attributes,fictitious,
            ST_Distance(geometry::geography,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)::geography) AS distance_m,
            ST_AsGeoJSON(geometry)::json AS geometry FROM network_segments
            WHERE import_id=%s AND ST_DWithin(geometry::geography,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)::geography,%s)
            ORDER BY distance_m,segment_id LIMIT 8''',(point,dataset['id'],point,radius)).fetchall()
        for candidate in candidates:
            candidate['references']=[row['ref'] for row in db.execute('''SELECT DISTINCT jsonb_build_object(
                'code',attributes->>'codigo','name',attributes->>'nombre','type',attributes->>'tipo_tramd',
                'tracks',attributes->>'n_vias','gauge',attributes->>'ancho_viad') AS ref
                FROM network_aliases WHERE import_id=%s AND segment_id=%s LIMIT 12''',(dataset['id'],candidate['segment_id'])).fetchall()]
    for candidate in candidates:candidate['distance_m']=round(candidate['distance_m'],1)
    close=[item for item in candidates if item['distance_m']<=candidates[0]['distance_m']+25] if candidates else []
    status='not_found' if not candidates else 'ambiguous' if len(close)>1 else 'reference_only' if candidates[0]['fictitious'] else 'candidate'
    messages={'not_found':'No se encuentra un tramo a menos de 120 m; no se asigna ninguno.',
        'ambiguous':'Hay varios tramos próximos compatibles. No se puede identificar uno con certeza.',
        'reference_only':'El enlace más cercano está declarado ficticio por la fuente. Solo sirve como referencia.',
        'candidate':'Se encuentra un tramo cartográfico próximo. La proximidad por sí sola no confirma la vía física.'}
    return {'status':status,'physical_track_identified':False,'radius_m':radius,'candidates':candidates,
            'network_import_id':dataset['id'],'network_imported_at':dataset['completed_at'].isoformat(),
            'source':dataset['source_url'],'message':messages[status],
            'attribution':dataset['metadata'].get('attribution','© IGN-CNIG · CC BY 4.0'),
            'method':'Distancia geodésica; tolerancia de ambigüedad 25 m. Precisión de la posición original desconocida.'}
