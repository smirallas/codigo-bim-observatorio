"""GTFS estático de Renfe: nombres de parada y viajes unidos por identificador exacto."""
import csv
import hashlib
import io
import zipfile
import urllib.request
from psycopg.types.json import Jsonb

URL='https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip'


def enrich(archive,features,at):
    """Una consulta para todos los viajes exactos de la capa, sin peticiones por tren."""
    ids=list({f['properties'].get('trip_id') for f in features if f['properties'].get('trip_id')})
    with archive.connect() as db:
        dataset=db.execute('SELECT id FROM schedule_imports WHERE received_at<=%s ORDER BY received_at DESC,id DESC LIMIT 1',(at,)).fetchone()
        trips={row['trip_id']:row['details'] for row in db.execute('SELECT trip_id,details FROM schedule_trips WHERE import_id=%s AND trip_id=ANY(%s)',(dataset['id'],ids)).fetchall()} if dataset and ids else {}
    for feature in features:
        p=feature['properties'];trip=trips.get(p.get('trip_id'),{})
        p.update(service_type=trip.get('service_name'),planned_origin=trip.get('origin'),planned_destination=trip.get('destination'))


def import_schedule(archive):
    with urllib.request.urlopen(URL,timeout=45) as response:body=response.read(25_000_001)
    if len(body)>25_000_000:raise ValueError('GTFS demasiado grande')
    with zipfile.ZipFile(io.BytesIO(body)) as package:
        if sum(item.file_size for item in package.infolist())>150_000_000:raise ValueError('GTFS descomprimido demasiado grande')
        def rows(name):
            path=next(item.filename for item in package.infolist() if item.filename.split('/')[-1]==name)
            with package.open(path) as stream:
                for row in csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig')):
                    yield {key.strip():value.strip() for key,value in row.items() if key}
        stops={row['stop_id']:row['stop_name'] for row in rows('stops.txt')}
        routes={row['route_id']:row for row in rows('routes.txt')}
        trips={row['trip_id']:{'trip_id':row['trip_id'],'service_id':row.get('service_id'),
                'service_name':routes.get(row['route_id'],{}).get('route_short_name'),
                'route_id':row['route_id'],'headsign':row.get('trip_headsign')} for row in rows('trips.txt')}
        ends={}
        for row in rows('stop_times.txt'):
            key=row['trip_id'];order=int(row['stop_sequence']);entry=(order,row['stop_id'],row.get('arrival_time'),row.get('departure_time'))
            if key not in ends:ends[key]=[entry,entry]
            else:
                if order<ends[key][0][0]:ends[key][0]=entry
                if order>ends[key][1][0]:ends[key][1]=entry
        for key,trip in trips.items():
            if key in ends:
                first,last=ends[key]
                trip.update(origin=stops.get(first[1]),destination=stops.get(last[1]),scheduled_departure=first[3],scheduled_arrival=last[2])
        with archive.connect() as db:
            identifier=db.execute('INSERT INTO schedule_imports(source_url,sha256,original) VALUES(%s,%s,%s) RETURNING id',
                (URL,hashlib.sha256(body).hexdigest(),body)).fetchone()['id']
            with db.cursor() as cursor:
                cursor.executemany('INSERT INTO schedule_stops VALUES(%s,%s,%s)',[(identifier,key,name) for key,name in stops.items()])
                cursor.executemany('INSERT INTO schedule_trips VALUES(%s,%s,%s)',[(identifier,key,Jsonb(details)) for key,details in trips.items()])
    return {'id':identifier,'stops':len(stops),'trips':len(trips),'sha256':hashlib.sha256(body).hexdigest()}


def lookup(archive,properties,at):
    with archive.connect() as db:
        dataset=db.execute('SELECT id,received_at,sha256 FROM schedule_imports WHERE received_at<=%s ORDER BY received_at DESC,id DESC LIMIT 1',(at,)).fetchone()
        if not dataset:return {'status':'unavailable','match':'none'}
        stop=db.execute('SELECT name FROM schedule_stops WHERE import_id=%s AND stop_id=%s',(dataset['id'],properties.get('stop_id'))).fetchone()
        trip=db.execute('SELECT details FROM schedule_trips WHERE import_id=%s AND trip_id=%s',(dataset['id'],properties.get('trip_id'))).fetchone()
    return {'status':'available','match':'exact' if trip else 'no_exact_trip','stop_name':stop['name'] if stop else None,
            'trip':trip['details'] if trip else None,'imported_at':dataset['received_at'].isoformat(),'sha256':dataset['sha256'],
            'note':'Horario planificado; no acredita puntualidad. El viaje solo se enlaza por trip_id exacto.'}
