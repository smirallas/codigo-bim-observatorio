"""Adaptador histórico DWD, solo para pruebas de regresión. Sin uso en el visor activo. Metadatos archivados; WMS actual, sin replay implícito."""
from datetime import datetime,timedelta,timezone
import hashlib
import os
from pathlib import Path
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from uuid import uuid4
from archive import instant
from reference import PNG,tile_bbox

WMS='https://maps.dwd.de/geoserver/wms'
LAYERS={
 'temperature':{'layer':'dwd:Icon_reg025_fd_sl_T2M','title':'Temperatura a 2 m','unit':'°C'},
 'rain':{'layer':'dwd:Icon_reg025_fd_sl_TOTPREC06H','title':'Precipitación acumulada en 6 h','unit':'mm / 6 h'},
 'wind':{'layer':'dwd:Icon_reg025_fd_sl_UV10M','title':'Viento a 10 m','unit':'Según escala DWD'},
}
NS={'w':'http://www.opengis.net/wms'}
ATTRIBUTION='© Deutscher Wetterdienst (DWD) · ICON · CC BY 4.0'
CACHE=Path(os.getenv('WEATHER_MAP_CACHE','/tmp/codigo-bim-weather'))
_network=threading.BoundedSemaphore(3)
_lock=threading.Lock();_failed={}


def valid_times(item):
    # El catálogo agrega varias salidas: no es el producto cartesiano de ambas dimensiones.
    run=instant(item['run_at']);horizon=120 if run.hour in (6,18) else 180
    result=[]
    for value in item['times']:
        hours=(instant(value)-run).total_seconds()/3600
        if not 0<=hours<=horizon or (hours>78 and hours%3):continue
        # Se ofrecen acumulados de seis horas en intervalos de seis horas, nunca lluvia instantánea.
        if item['id']=='rain' and (hours<6 or hours%6):continue
        result.append(value)
    return result


def times(value):
    if '/' not in value:return sorted({instant(v).isoformat() for v in value.split(',') if v.strip()})
    start,end,step=value.split('/')
    match=re.fullmatch(r'PT([1-9][0-9]?)H',step)
    if not match:raise ValueError('Intervalo WMS no reconocido')
    current=instant(start);last=instant(end);result=[]
    while current<=last:
        result.append(current.isoformat());current+=timedelta(hours=int(match[1]))
        if len(result)>1000:raise ValueError('Demasiados instantes WMS')
    return result


def parse_metadata(body,now=None):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('XML no admitido')
    root=ET.fromstring(body);result=[];now=now or datetime.now(timezone.utc)
    for key,config in LAYERS.items():
        layer=next((l for l in root.findall('.//w:Layer',NS) if l.findtext('w:Name',namespaces=NS)==config['layer']),None)
        if layer is None:continue
        dimensions={d.get('name').lower():d for d in layer.findall('w:Dimension',NS)}
        if 'reference_time' not in dimensions or 'time' not in dimensions:continue
        runs=[t for t in times(dimensions['reference_time'].text or '') if instant(t)<=now]
        if not runs:continue
        run=max(runs,key=instant)
        valid=[t for t in times(dimensions['time'].text or '') if instant(t)>=instant(run)]
        styles=[s.findtext('w:Name',namespaces=NS) for s in layer.findall('w:Style',NS)]
        style=styles[0] if styles else ''
        if style and not re.fullmatch(r'[A-Za-z0-9_:.-]{1,100}',style):raise ValueError('Estilo WMS no admitido')
        item={'id':key,**config,'run_at':run,'times':valid,'style':style,
            'model_stale':(now-instant(run)).total_seconds()>18*3600}
        item['times']=valid_times(item);result.append(item)
    if len(result)!=3:raise ValueError('Faltan capas meteorológicas requeridas')
    return {'maps':result,'attribution':ATTRIBUTION,'kind':'forecast',
        'note':'Mapas WMS actuales del proveedor; no reconstruyen el tiempo conocido en un replay histórico.'}


def collect_metadata(archive):
    request=urllib.request.Request(WMS+'?service=WMS&version=1.3.0&request=GetCapabilities',headers={
        'User-Agent':'CodigoBIM-DataLab/2.3 https://codigobim.com/','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(request,timeout=45) as response:body=response.read(12_000_001)
    if len(body)>12_000_000:raise ValueError('Metadatos demasiado grandes')
    metadata=parse_metadata(body)
    result=archive.add('weather_maps',datetime.now(timezone.utc),body,[],'forecast',metadata=metadata)
    archive.attempt('weather_maps','ok',http_status=200)
    return {'source':'weather_maps','status':'ok',**result}


def payload(archive,source='weather_maps'):
    # Una recepción posterior puede ser un catálogo de caché anterior. No retroceder de modelo.
    with archive.connect() as db:
        snapshot=db.execute("""SELECT id,received_at,metadata FROM captures WHERE source=%s
            AND received_at<=now() ORDER BY (metadata->'maps'->0->>'run_at')::timestamptz DESC,received_at DESC,id DESC LIMIT 1""",(source,)).fetchone()
    if not snapshot:return {'status':'unavailable','maps':[],'note':'Aún no hay metadatos meteorológicos recibidos.'}
    metadata=snapshot['metadata'];now=datetime.now(timezone.utc)
    for item in metadata['maps']:
        item['times']=valid_times(item)
        item['model_stale']=(now-instant(item['run_at'])).total_seconds()>18*3600
        future=[t for t in item['times'] if instant(t)>=now]
        item['selected_time']=future[0] if future else item['times'][-1] if item['times'] else None
    return {'status':'available','capture_id':snapshot['id'],'received_at':snapshot['received_at'].isoformat(),**metadata}


def image(archive,capture_id,key,valid,z=None,x=None,y=None,legend=False):
    if key not in LAYERS:raise ValueError('Mapa no admitido')
    if not legend:bbox=tile_bbox(z,x,y)
    with archive.connect() as db:
        row=db.execute("SELECT metadata FROM captures WHERE id=%s AND source='weather_maps' AND received_at<=now()",(capture_id,)).fetchone()
    if not row:raise ValueError('Metadatos no disponibles')
    item=next((m for m in row['metadata']['maps'] if m['id']==key),None)
    if item is None or valid not in valid_times(item):raise ValueError('Instante no admitido')
    params={'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetLegendGraphic' if legend else 'GetMap',
        'FORMAT':'image/png','LAYER' if legend else 'LAYERS':LAYERS[key]['layer'],
        'STYLE' if legend else 'STYLES':item['style'],'TIME':valid.replace('+00:00','Z'),'DIM_REFERENCE_TIME':item['run_at'].replace('+00:00','Z')}
    if key=='wind':params['ELEVATION']='10'
    if not legend:params.update(SRS='EPSG:3857',BBOX=','.join(map(str,bbox)),WIDTH=256,HEIGHT=256,TRANSPARENT='TRUE')
    url=WMS+'?'+urllib.parse.urlencode(params);fingerprint=hashlib.sha256(url.encode()).hexdigest()
    failure_key=fingerprint  # Un fallo de una zona o leyenda no bloquea las demás teselas.
    CACHE.mkdir(parents=True,exist_ok=True);path=CACHE/(fingerprint+'.png')
    with _lock:
        if path.exists():return path.read_bytes()
        if time.monotonic()-_failed.get(failure_key,-1000)<60:raise OSError('WMS en espera tras un fallo')
    try:
        with _network:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CodigoBIM-DataLab/2.3 https://codigobim.com/','Cache-Control':'no-cache','Pragma':'no-cache'}),timeout=30) as response:body=response.read(2_000_001)
        if len(body)>2_000_000 or not body.startswith(PNG):raise ValueError('No se recibió una imagen meteorológica PNG')
        with _lock:
            temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
            temporary.write_bytes(body);temporary.replace(path)
            files=sorted(CACHE.glob('*.png'),key=lambda p:p.stat().st_mtime);size=sum(p.stat().st_size for p in files)
            for old in files:
                if size<=8*1024*1024:break
                if old==path:continue
                size-=old.stat().st_size;old.unlink(missing_ok=True)
        return body
    except Exception:
        with _lock:_failed[failure_key]=time.monotonic()
        raise
