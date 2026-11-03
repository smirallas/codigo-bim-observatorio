"""Predicciones AEMET HARMONIE-AROME: GeoTIFF oficiales, reproyectados sin interpolar colores."""
import ast
from datetime import datetime, timezone
import hashlib
import gzip
import io
import os
from pathlib import Path
import re
import tarfile
import threading
import urllib.request
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from archive import instant
from reference import tile_bbox

URL='https://www.aemet.es/es/api-eltiempo/modelos/download/harmonie/'
LAYERS={
 'temperature':{'suffix':'11','title':'Temperatura a 2 m','unit':'°C'},
 'rain':{'suffix':'61_1HH','title':'Precipitación en la hora previa','unit':'mm / 1 h'},
 'wind':{'suffix':'32','title':'Velocidad del viento','unit':'km/h'},
}
ATTRIBUTION='© AEMET · HARMONIE-AROME · elaboración cartográfica de Código BIM'
CACHE=Path(os.getenv('WEATHER_MAP_CACHE','/tmp/codigo-bim-weather'))
_lock=threading.Lock()
_render=threading.BoundedSemaphore(2)
PATTERN=re.compile(r'down_(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00)_(11|32|61_1HH)\.tif')
MAX_DOWNLOAD=80_000_000


def parse_package(body,region):
    if region not in ('PB','CAN'):raise ValueError('Área no admitida')
    files={};scales={};generated=[]
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as package:
        members=package.getmembers()
        if len(members)>2000 or sum(m.size for m in members)>250_000_000:raise ValueError('Paquete AEMET demasiado grande')
        for member in members:
            match=PATTERN.fullmatch(member.name)
            if not match:continue
            if not member.isfile() or member.size>4_000_000:raise ValueError('Raster no admitido')
            valid,suffix=match.groups();key=next(k for k,v in LAYERS.items() if v['suffix']==suffix)
            data=package.extractfile(member).read()
            with MemoryFile(data) as memory, memory.open() as dataset:
                tags=dataset.tags()
                if dataset.crs!=rasterio.crs.CRS.from_epsg(4326) or dataset.count!=4 or dataset.dtypes!=('uint8',)*4 or dataset.width*dataset.height>2_000_000:raise ValueError('GeoTIFF AEMET inesperado')
                if instant(tags['FECHA'])!=instant(valid) or tags.get('FUENTE')!='AEMET':raise ValueError('Fecha o fuente del raster incoherente')
                if key not in scales:
                    scale=ast.literal_eval(tags['ESCALA'])['Lista RGBA']
                    if not isinstance(scale,list) or not 1<=len(scale)<=100:raise ValueError('Escala no válida')
                    scales[key]=scale
            files[(key,instant(valid).isoformat())]=(region+'/'+member.name,data)
            generated.append(datetime.fromtimestamp(member.mtime,timezone.utc).isoformat())
    if not all(any(k==key for k,_ in files) for key in LAYERS):raise ValueError('Faltan campos AEMET')
    return files,scales,max(generated)


def collect_metadata(archive):
    # Los dos dominios se validan antes de publicar una captura. Sin sustitución por otro proveedor.
    rasters={key:{} for key in LAYERS};scales={};generations={};content={}
    for region in ('PB','CAN'):
        request=urllib.request.Request(URL+region,headers={'User-Agent':'CodigoBIM-Observatorio/2.6 https://codigobim.com/'})
        with urllib.request.urlopen(request,timeout=90) as response:body=response.read(MAX_DOWNLOAD+1)
        if len(body)>MAX_DOWNLOAD:raise ValueError('Descarga AEMET demasiado grande')
        files,legend,generated=parse_package(body,region);scales.update(legend);generations[region]=generated
        for (key,valid),(name,data) in files.items():
            rasters[key].setdefault(valid,[]).append(name);content[name]=data
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as package:
        for name,data in sorted(content.items()):
            info=tarfile.TarInfo(name);info.size=len(data);package.addfile(info,io.BytesIO(data))
    now=datetime.now(timezone.utc)
    metadata={'provider':'aemet','attribution':ATTRIBUTION,'kind':'forecast','generated_at_by_region':generations,
      'note':'Predicción, no observación. La hora de salida del modelo no está identificada en estos archivos.',
      'maps':[{'id':key,**config,'run_at':None,'times':sorted(rasters[key]),'rasters':rasters[key],
        'scale':scales[key],'generated_at':max(generations.values())} for key,config in LAYERS.items()]}
    original=gzip.compress(buffer.getvalue(),mtime=0)
    digest=hashlib.sha256(original).hexdigest()
    with archive.connect() as db:
        previous=db.execute("SELECT id FROM captures WHERE source='weather_maps' AND sha256=%s ORDER BY received_at DESC LIMIT 1",(digest,)).fetchone()
    if previous:
        archive.attempt('weather_maps','cached',http_status=200)
        return {'source':'weather_maps','status':'cached','id':previous['id'],'sha256':digest}
    result=archive.add('weather_maps',now,original,[],'forecast',metadata=metadata)
    archive.attempt('weather_maps','ok',http_status=200)
    return {'source':'weather_maps','status':'ok',**result}


def payload(archive,source='weather_maps'):
    with archive.connect() as db:
        row=db.execute("""SELECT id,received_at,metadata FROM captures WHERE source=%s AND metadata->>'provider'='aemet'
          AND received_at<=now() ORDER BY metadata->'maps'->0->>'generated_at' DESC,received_at DESC,id DESC LIMIT 1""",(source,)).fetchone()
    if not row:return {'status':'unavailable','maps':[],'note':'Aún no hay mapas de AEMET recibidos.'}
    metadata=row['metadata'];now=datetime.now(timezone.utc)
    for item in metadata['maps']:
        future=[t for t in item['times'] if instant(t)>=now]
        item['selected_time']=future[0] if future else item['times'][-1]
        item['model_stale']=(now-instant(item['generated_at'])).total_seconds()>18*3600
    # No enviar al navegador rutas internas ni la tabla de archivos.
    return {'status':'available','capture_id':row['id'],'received_at':row['received_at'].isoformat(),**metadata,
       'maps':[{k:v for k,v in m.items() if k not in ('rasters','scale')} for m in metadata['maps']]}


def raster_path(archive,capture_id,name):
    if not re.fullmatch(r'(PB|CAN)/down_[0-9T:+.-]+_(11|32|61_1HH)\.tif',name):raise ValueError('Archivo no permitido')
    directory=CACHE/('aemet-'+str(capture_id));path=directory/(hashlib.sha256(name.encode()).hexdigest()+'.tif')
    with _lock:
        if path.exists():return path
        with archive.connect() as db:
            row=db.execute("SELECT original FROM captures WHERE id=%s AND source='weather_maps' AND metadata->>'provider'='aemet'",(capture_id,)).fetchone()
        if not row:raise ValueError('Captura AEMET no disponible')
        directory.mkdir(parents=True,exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(bytes(row['original'])),mode='r:gz') as package:
            # Materializar una vez; nombres hash, nunca extraer rutas del proveedor.
            for member in package:
                if not re.fullmatch(r'(PB|CAN)/down_[0-9T:+.-]+_(11|32|61_1HH)\.tif',member.name):continue
                target=directory/(hashlib.sha256(member.name.encode()).hexdigest()+'.tif')
                temporary=target.with_suffix('.'+uuid4().hex+'.tmp');temporary.write_bytes(package.extractfile(member).read());temporary.replace(target)
        # Solo caché regenerable de AEMET; nunca originales archivados ni otras fuentes.
        directories=[d for d in CACHE.glob('aemet-*') if d.is_dir() and re.fullmatch(r'aemet-[0-9]+',d.name)]
        size=sum(f.stat().st_size for d in directories for f in d.glob('*.tif'))
        for old in sorted(directories,key=lambda d:d.stat().st_mtime):
            if size<=256*1024*1024:break
            if old==directory:continue
            for f in old.glob('*.tif'):
                size-=f.stat().st_size;f.unlink()
            if not any(old.iterdir()):old.rmdir()
        return path


def legend_image(item):
    scale=item['scale'];image=Image.new('RGBA',(230,len(scale)*20+28),'white');draw=ImageDraw.Draw(image)
    draw.text((4,3),item['unit'],fill='black')
    for i,entry in enumerate(scale):
        color=tuple(map(int,entry['RGBA']));low,high=entry['Valores'];label=f'{low} - {high}' if high!='' else f'>= {low}'
        draw.rectangle((4,26+i*20,32,42+i*20),fill=color);draw.text((40,26+i*20),label,fill='black')
    out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()


def image(archive,capture_id,key,valid,z=None,x=None,y=None,legend=False):
    if key not in LAYERS:raise ValueError('Mapa no admitido')
    bbox=None if legend else tile_bbox(z,x,y)
    with archive.connect() as db:
        row=db.execute("SELECT metadata FROM captures WHERE id=%s AND source='weather_maps' AND metadata->>'provider'='aemet' AND received_at<=now()",(capture_id,)).fetchone()
    if not row:raise ValueError('Metadatos AEMET no disponibles')
    item=next((m for m in row['metadata']['maps'] if m['id']==key),None)
    if not item or valid not in item['times']:raise ValueError('Validez no admitida')
    if legend:return legend_image(item)
    with _render,rasterio.Env(GDAL_CACHEMAX=16):
        canvas=np.zeros((4,256,256),dtype='uint8');transform=from_bounds(*bbox,256,256)
        for name in item['rasters'][valid]:
            with rasterio.open(raster_path(archive,capture_id,name)) as src:
                output=np.zeros_like(canvas)
                reproject(rasterio.band(src,[1,2,3,4]),output,src_transform=src.transform,src_crs=src.crs,
                   dst_transform=transform,dst_crs='EPSG:3857',resampling=Resampling.nearest,num_threads=1)
                mask=output[3]>0;canvas[:,mask]=output[:,mask]
        out=io.BytesIO();Image.fromarray(canvas.transpose(1,2,0)).save(out,format='PNG');return out.getvalue()
