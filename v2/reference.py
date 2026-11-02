"""Cartografía IGN por teselas WMS fijas: contexto visual, nunca vía asignada a un tren."""
import math
import os
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request

WMS='https://servicios.idee.es/wms-inspire/transportes'
REFERENCES={
 'railway':{'title':'Trazado ferroviario · IGN','layer':'TN.RailTransportNetwork.RailwayLink'},
 'highways':{'title':'Carreteras · IGN','layer':'TN.RoadTransportNetwork.RoadLink'},
}
CACHE=Path(os.getenv('REFERENCE_CACHE','/tmp/codigo-bim-transportes'))
TTL=7*24*3600
MAX_CACHE_BYTES=24*1024*1024
PNG=b'\x89PNG\r\n\x1a\n'
_network=threading.BoundedSemaphore(4)
_failed={}


def tile_bbox(z,x,y):
    if any(type(value) is not int for value in (z,x,y)) or not 0<=z<=15 or not 0<=x<2**z or not 0<=y<2**z:
        raise ValueError('Tesela fuera de rango')
    world=math.pi*6378137
    span=2*world/(2**z)
    return (x*span-world,world-(y+1)*span,(x+1)*span-world,world-y*span)


def tile_url(source,z,x,y):
    if source not in REFERENCES:raise ValueError('Referencia desconocida')
    bbox=tile_bbox(z,x,y)
    # WMS 1.1.1 y EPSG:3857 mantienen orden X,Y y evitan ambigüedad de ejes 4326.
    return WMS+'?'+urllib.parse.urlencode({'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetMap',
        'LAYERS':REFERENCES[source]['layer'],'STYLES':'','SRS':'EPSG:3857',
        'BBOX':','.join(str(value) for value in bbox),'WIDTH':256,'HEIGHT':256,
        'FORMAT':'image/png','TRANSPARENT':'TRUE'})


def reference_layers(roads=True):
    return [{'id':key,'title':value['title'],'tiles':[f'api/reference/{key}/{{z}}/{{x}}/{{y}}.png'],
             'attribution':'© IGN-CNIG · licencia compatible con CC BY 4.0',
             'url':'https://www.ign.es/web/ign/portal/politica-datos',
             'note':'Cartografía de referencia actual; no reconstruye la infraestructura de la fecha de una captura.'}
            for key,value in REFERENCES.items() if roads or key=='railway']


def tile(source,z,x,y):
    url=tile_url(source,z,x,y)
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/f'{source}-{z}-{x}-{y}.png'
    previous=path.read_bytes() if path.exists() else None
    if previous and time.time()-path.stat().st_mtime<TTL:return previous,'cache'
    if time.time()-_failed.get(source,0)<60:
        if previous:return previous,'stale-cache'
        raise OSError('Servicio de referencia temporalmente no disponible')
    try:
        with _network:
            request=urllib.request.Request(url,headers={'User-Agent':'CodigoBIM-DataLab/2.0 https://codigobim.com/'})
            with urllib.request.urlopen(request,timeout=20) as response:
                body=response.read(1_000_001)
            if len(body)>1_000_000 or not body.startswith(PNG):raise ValueError('El WMS no devolvió una imagen PNG válida')
        # No guardar una respuesta parcial o una excepción XML bajo extensión PNG.
        temporary=path.with_name(path.name+'.'+str(threading.get_ident())+'.tmp')
        temporary.write_bytes(body);temporary.replace(path)
        files=sorted(CACHE.glob('*.png'),key=lambda file:file.stat().st_mtime)
        size=sum(file.stat().st_size for file in files)
        for old in files:
            if size<=MAX_CACHE_BYTES:break
            if old==path:continue
            amount=old.stat().st_size
            old.unlink(missing_ok=True);size-=amount
        return body,'fetched'
    except Exception:
        _failed[source]=time.time()
        if previous:return previous,'stale-cache'
        raise
