"""Lee el formato GeoPackage oficial; la persistencia de la aplicación sigue en PostGIS."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
from psycopg.types.json import Jsonb

LAYERS={'highways':('rt_tramo_vial','geometry','13139379'),
        'railway':('rt_tramofc_linea','geom','13139375')}


def wkb(blob):
    if len(blob)<8 or blob[:2]!=b'GP' or blob[2]!=0:raise ValueError('Cabecera GeoPackage inválida')
    flags=blob[3];envelope=(flags>>1)&7
    if envelope>4 or flags&0x30:raise ValueError('Geometría vacía o extendida no admitida')
    srid=struct.unpack('<i' if flags&1 else '>i',blob[4:8])[0]
    if srid!=4258:raise ValueError('Se esperaba ETRS89 EPSG:4258')
    offset=8+(0,32,48,48,64)[envelope]
    if len(blob)<=offset:raise ValueError('WKB vacío')
    return blob[offset:]


def import_roads(archive,path,original,kind='highways'):
    table,column,source_id=LAYERS[kind]
    source_url='https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec='+source_id
    path=Path(path).resolve();original=Path(original).resolve()
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
    try:
        geometry=source.execute('SELECT geometry_type_name,srs_id FROM gpkg_geometry_columns WHERE table_name=? AND column_name=?',(table,column)).fetchone()
        if not geometry or tuple(geometry)!=('LINESTRING',4258):raise ValueError('Capa oficial no reconocida')
        expected=source.execute('SELECT count(*) FROM '+table).fetchone()[0]
        with archive.connect() as db:
            identifier=db.execute('''INSERT INTO network_imports(kind,source_url,coverage,metadata)
                VALUES(%s,%s,ST_MakeEnvelope(-18,27,5,44.5,4326),%s) RETURNING id''',
                (kind,source_url,Jsonb({'format':'GeoPackage','table':table,'expected_rows':expected,
                    'coverage_note':'Red ferroviaria de España.' if kind=='railway' else 'Red de carreteras de España; no incluye todo el viario urbano ni caminos.',
                    'attribution':'Obra derivada de IGR-RT 2026 CC-BY 4.0 scne.es'}))).fetchone()['id']
        try:
            digest=hashlib.sha256()
            with original.open('rb') as stream:
                part=0
                while chunk:=stream.read(8*1024*1024):
                    digest.update(chunk)
                    with archive.connect() as db:db.execute('INSERT INTO network_assets VALUES(%s,%s,%s,%s)',(identifier,part,hashlib.sha256(chunk).hexdigest(),chunk))
                    part+=1
            with archive.connect() as db:
                db.execute("UPDATE network_imports SET metadata=metadata||%s WHERE id=%s",(Jsonb({'original_name':original.name,'sha256':digest.hexdigest()}),identifier))
                db.execute('CREATE TEMP TABLE stage_network(id text,row_id bigint,wkb bytea,attributes jsonb)')
                cursor=source.execute('SELECT * FROM '+table+' ORDER BY fid');total=0
                while rows:=cursor.fetchmany(5000):
                    db.execute('TRUNCATE stage_network')
                    with db.cursor().copy('COPY stage_network FROM STDIN') as copy:
                        for row in rows:
                            if row['id_tramo'] is None:raise ValueError('Tramo sin identificador')
                            props={key:row[key] for key in row.keys() if key!=column}
                            copy.write_row(('CNIG:'+table+':'+str(row['id_tramo']),row['fid'],wkb(row[column]),Jsonb(props)))
                    # Las distintas carreteras que comparten tramo no son vías paralelas.
                    db.execute('''INSERT INTO network_segments(import_id,segment_id,geometry,attributes,fictitious)
                        SELECT %s,id,ST_Transform(ST_Force2D(ST_GeomFromWKB(wkb,4258)),4326),attributes,NULL
                        FROM (SELECT DISTINCT ON (id) * FROM stage_network ORDER BY id,row_id) s
                        ON CONFLICT DO NOTHING''',(identifier,))
                    db.execute('INSERT INTO network_aliases SELECT %s,id,row_id,attributes FROM stage_network',(identifier,))
                    total+=len(rows)
                    db.execute('UPDATE network_imports SET pages=pages+1,segments=(SELECT count(*) FROM network_segments WHERE import_id=%s) WHERE id=%s',(identifier,identifier))
                    db.commit()
                    print(json.dumps({'import_id':identifier,'rows':total,'expected_rows':expected}),flush=True)
                if total!=expected:raise ValueError('Importación incompleta')
                count=db.execute('SELECT count(*) AS n FROM network_aliases WHERE import_id=%s',(identifier,)).fetchone()['n']
                if count!=expected:raise ValueError('Faltan registros del original')
                db.execute("UPDATE network_imports SET status='complete',completed_at=now(),expected_segments=segments WHERE id=%s",(identifier,))
            return {'id':identifier,'status':'complete','rows':total,'original_sha256':digest.hexdigest()}
        except Exception as error:
            with archive.connect() as db:db.execute("UPDATE network_imports SET status='failed',error_type=%s WHERE id=%s",(type(error).__name__,identifier))
            raise
    finally:source.close()
