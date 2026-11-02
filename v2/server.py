"""API de consulta e iframe del laboratorio por capas. Sin escritura desde el navegador."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import re
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from archive import Archive, instant
from demo import AT, layers
from sources import CATALOG
from reference import reference_layers, tile

ROOT=Path(__file__).parent


def feature_payload(archive,source,capture_id,ordinal,at=None):
    """Lee una entidad exacta, no la primera que comparta número de tren."""
    cutoff=instant(at) if at else datetime.now(timezone.utc)
    if cutoff>datetime.now(timezone.utc)+timedelta(seconds=5):raise ValueError('Consulta futura')
    with archive.connect() as db:
        row=db.execute('''SELECT ST_AsGeoJSON(f.geometry)::json AS geometry,f.properties,
            c.id,c.received_at,c.published_at,c.sha256,c.metadata FROM features f JOIN captures c ON c.id=f.capture_id
            WHERE c.source=%s AND c.id=%s AND f.ordinal=%s AND c.received_at<=%s
            AND (c.published_at IS NULL OR c.published_at<=%s)''',(source,capture_id,ordinal,cutoff,cutoff)).fetchone()
    if not row:return None
    prop=row['properties']
    if prop.get('observed_at') and instant(prop['observed_at'])>cutoff:return None
    from networks import associate
    from schedule import lookup
    return {'feature':{'type':'Feature','geometry':row['geometry'],'properties':prop},
        'capture':{'id':row['id'],'received_at':row['received_at'].isoformat(),
            'published_at':row['published_at'].isoformat() if row['published_at'] else None,
            'sha256':row['sha256'],'metadata':row['metadata']},
        'association':associate(archive,source,row['geometry'],cutoff),
        'schedule':lookup(archive,prop,cutoff) if source=='rail' else None}


def bbox_value(value):
    values=[float(item) for item in value.split(',')]
    if len(values)!=4 or not all(math.isfinite(v) for v in values) or not (-180<=values[0]<values[2]<=180 and -90<=values[1]<values[3]<=90):
        raise ValueError('bbox inválido')
    return values


def layer_payload(source, query, archive):
    meta=CATALOG[source]
    mode=query.get('mode',['demo'])[0]
    if mode not in ('demo','archive'):
        raise ValueError('Modo no válido')
    cutoff=instant(query['at'][0]) if query.get('at') else datetime.now(timezone.utc)
    if cutoff>datetime.now(timezone.utc)+timedelta(seconds=5):
        raise ValueError('La consulta de disponibilidad no puede estar en el futuro')
    bbox=bbox_value(query['bbox'][0]) if query.get('bbox') else None
    if mode=='demo':
        snapshot={'received_at':AT,'kind':'synthetic','features':layers()[source],'attempt':{},'published_at':None}
    else:
        snapshot=archive.latest(source,cutoff,bbox)
        if snapshot is None:
            with archive.connect() as db:
                attempt=db.execute('SELECT status,error_type,http_status FROM attempts WHERE source=%s',(source,)).fetchone()
            return {'type':'FeatureCollection','features':[],'source':source,'status':'unavailable','attempt':attempt,
                    'note':'No hay captura disponible para ese instante; los ejemplos siguen en modo separado.'}
    features=snapshot['features']
    if mode=='archive' and source=='rail':
        from schedule import enrich
        enrich(archive,features,cutoff)
    capture_age=(cutoff-instant(snapshot['received_at'])).total_seconds()
    valid_at=instant(query['valid_at'][0]) if query.get('valid_at') else cutoff
    if mode=='archive' and source=='weather':
        features=[feature for feature in features if feature['properties'].get('valid_at') and
                  instant(feature['properties']['valid_at'])<=valid_at<instant(feature['properties']['valid_at'])+timedelta(hours=1)]
    for feature in features:
        prop=feature['properties']
        observed=prop.get('observed_at')
        prop['freshness']='synthetic' if mode=='demo' else 'forecast' if meta['kind']=='forecast' else 'reference' if meta['kind']=='reference' else (
            'unknown' if not observed else 'stale' if (cutoff-instant(observed)).total_seconds()>meta['ttl'] else 'recent')
    return {'type':'FeatureCollection','features':features,'source':source,'status':'synthetic' if mode=='demo' else 'available',
            'kind':snapshot['kind'],'received_at':snapshot['received_at'],'published_at':snapshot.get('published_at'),
            'capture_status':'synthetic' if mode=='demo' else 'stale' if capture_age>meta['ttl'] else 'recent',
            'capture_age_s':capture_age,'provenance':snapshot.get('metadata',{}),
            'attempt':snapshot.get('attempt',{}),'attribution':'Código BIM · ejemplo sintético (MIT)' if mode=='demo' else snapshot.get('metadata',{}).get('attribution',meta['attribution']),
            'availability_at':cutoff.isoformat(),'validity_at':valid_at.isoformat(),
            'note':'Ejemplo inventado' if mode=='demo' else 'La recepción no sustituye al tiempo de observación. Predicciones identificadas por su validez.'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self,status,data,content_type='application/json; charset=utf-8'):
        self.send_response(status)
        for key,value in {'Content-Type':content_type,'Content-Length':str(len(data)),
            'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store',
            'Content-Security-Policy':"default-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self' https://codigobim.com https://www.codigobim.com http://127.0.0.1:* http://localhost:*; base-uri 'none'; object-src 'none'"}.items():
            self.send_header(key,value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def json(self,status,value):
        self.send(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode())

    def do_GET(self):
        url=urlsplit(self.path)
        path=url.path.removeprefix('/v2') or '/'
        query=parse_qs(url.query,keep_blank_values=True)
        try:
            if path.startswith('/api/') and (any(k in query for k in ('at','valid_at')) or query.get('mode',['archive'])!=['archive']):
                return self.json(400,{'error':'Solo se consulta el estado actual de las fuentes reales'})
            if path=='/api/live':
                from collector import source_interval
                with Archive(os.environ['DATABASE_URL']).connect() as db:
                    rows=db.execute('SELECT source,attempted_at,status FROM attempts WHERE source=ANY(%s)',(list(CATALOG),)).fetchall()
                return self.json(200,[{**row,'attempted_at':row['attempted_at'].isoformat(),'interval_s':source_interval(row['source'])} for row in rows])
            if path=='/api/weather/maps':
                if 'weather' not in CATALOG:return self.json(404,{'error':'Meteorología no habilitada'})
                from weather_maps import payload
                return self.json(200,payload(Archive(os.environ['DATABASE_URL'])))
            if path.startswith('/api/weather/image/'):
                if 'weather' not in CATALOG:return self.json(404,{'error':'Meteorología no habilitada'})
                match=re.fullmatch(r'/api/weather/image/([1-9][0-9]{0,15})/(temperature|rain|wind)/(legend|([0-9]{1,2})/([0-9]{1,5})/([0-9]{1,5}))\.png',path)
                if not match:return self.json(400,{'error':'Mapa no válido'})
                from weather_maps import image
                capture_id,key,part,z,x,y=match.groups()
                body=image(Archive(os.environ['DATABASE_URL']),int(capture_id),key,query.get('valid',[''])[0],
                    int(z) if z else None,int(x) if x else None,int(y) if y else None,legend=part=='legend')
                return self.send(200,body,'image/png')
            if path=='/api/networks':
                with Archive(os.environ['DATABASE_URL']).connect() as db:
                    rows=db.execute('''SELECT DISTINCT ON (kind) kind,status,pages,segments,expected_segments,error_type,
                        completed_at,ST_AsGeoJSON(coverage)::json AS coverage FROM network_imports
                        ORDER BY kind,started_at DESC,id DESC''').fetchall()
                return self.json(200,[{k:v.isoformat() if isinstance(v,datetime) else v for k,v in row.items()} for row in rows])
            if path.startswith('/api/features/'):
                match=re.fullmatch(r'/api/features/([a-z]+)/([1-9][0-9]{0,15})/([0-9]{1,7})',path)
                if not match or match[1] not in CATALOG:return self.json(404,{'error':'Entidad desconocida'})
                source,capture_id,ordinal=match.groups()
                result=feature_payload(Archive(os.environ['DATABASE_URL']),source,int(capture_id),int(ordinal),query.get('at',[None])[0])
                return self.json(200,result) if result else self.json(404,{'error':'Entidad no disponible para este instante'})
            if path=='/api/reference-layers':
                return self.json(200,reference_layers(roads='roads' in CATALOG))
            if path.startswith('/api/reference/'):
                match=re.fullmatch(r'/api/reference/(railway|highways)/(\d{1,2})/(\d{1,5})/(\d{1,5})\.png',path)
                if not match:return self.json(400,{'error':'Referencia o tesela no válida'})
                source,z,x,y=match.groups()
                if source=='highways' and 'roads' not in CATALOG:return self.json(404,{'error':'Referencia no habilitada'})
                body,_=tile(source,int(z),int(x),int(y))
                return self.send(200,body,'image/png')
            if path=='/api/health':
                with Archive(os.environ['DATABASE_URL']).connect() as db:
                    db.execute('SELECT 1').fetchone()
                return self.json(200,{'status':'ok','version':'2.5.0','database':'postgresql-postgis','reader_storage':False})
            if path=='/api/layers':
                return self.json(200,[{'id':key,**value} for key,value in CATALOG.items()])
            if path.startswith('/api/layers/'):
                source=path.split('/')[-1]
                if source not in CATALOG:
                    return self.json(404,{'error':'Capa desconocida'})
                archive=Archive(os.environ['DATABASE_URL'])
                return self.json(200,layer_payload(source,{**query,'mode':['archive']},archive))
            assets={'/':'index.html','/app.js':'app.js','/inspector.js':'inspector.js','/categories.js':'categories.js','/domains.js':'domains.js','/domains.css':'domains.css','/weather.js':'weather.js','/wind-legend.svg':'wind-legend.svg','/inspector.css':'inspector.css','/shell.css':'shell.css','/style.css':'style.css','/geography.json':'geography.json',
                    **{'/'+name:name for name in ('maplibre-gl.mjs','maplibre-gl-worker.mjs','maplibre-gl-shared.mjs','maplibre-gl.css','maplibre-LICENSE.txt')}}
            if path in assets:
                name=assets[path]
                mime='text/html; charset=utf-8' if name.endswith('.html') else 'image/svg+xml' if name.endswith('.svg') else 'application/json' if name.endswith('.json') else 'text/css' if name.endswith('.css') else 'application/javascript' if name.endswith(('.js','.mjs')) else 'text/plain'
                return self.send(200,(ROOT/'web'/name).read_bytes(),mime)
            return self.json(404,{'error':'No encontrado'})
        except (ValueError,TypeError,KeyError) as error:
            return self.json(400,{'error':'Parámetros o datos no válidos'})
        except Exception:
            return self.json(503,{'error':'Fuente temporalmente no disponible. Vuelve a intentarlo en unos instantes.'})


if __name__=='__main__':
    Archive(os.environ['DATABASE_URL']).migrate()
    ThreadingHTTPServer((os.getenv('HOST','0.0.0.0'),int(os.getenv('PORT','8027'))),Handler).serve_forever()
