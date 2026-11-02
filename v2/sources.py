"""Adaptadores separados; ningún campo ausente se convierte en observación inventada."""
from datetime import datetime, timezone
import json
import math
import xml.etree.ElementTree as ET
CATALOG = {'rail': {'title': 'Posiciones ferroviarias', 'group': 'Ferrocarril', 'color': '#136b60', 'kind': 'observation', 'ttl': 120, 'attribution': 'Renfe Data · CC BY 4.0', 'url': 'https://data.renfe.com/es/dataset/posicion-vehiculos-av-ld-md'}, 'roads': {'title': 'Red viaria', 'group': 'Carreteras', 'color': '#77736a', 'kind': 'reference', 'ttl': 2592000, 'attribution': '© OpenStreetMap contributors · ODbL (o licencia del archivo importado)', 'url': 'https://www.openstreetmap.org/copyright'}, 'dgt': {'title': 'Incidencias DGT', 'group': 'Carreteras', 'color': '#b96420', 'kind': 'observation', 'ttl': 600, 'attribution': 'DGT · NAP · DATEX II 3.7 · Creative Commons Attribution', 'url': 'https://nap.dgt.es/es/dataset/incidencias-dgt-datex2-v3-7'}}

def timestamp(value):
    try:
        if isinstance(value, bool) or value is None:
            return None
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None

def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)

def point(lon, lat, properties):
    if not numeric(lat) or not numeric(lon) or (not (-90 <= lat <= 90 and -180 <= lon <= 180)):
        return None
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': properties}

def rail(body, received):
    feed = json.loads(body)
    features = []
    if not isinstance(feed.get('entity', []), list):
        raise ValueError('entity no es una lista')
    for entity in feed.get('entity', []):
        if not isinstance(entity, dict) or not isinstance(entity.get('vehicle'), dict):
            continue
        vehicle = entity['vehicle']
        position = vehicle.get('position') or {}
        if not isinstance(position, dict):
            continue
        speed = position.get('speed')
        feature = point(position.get('longitude'), position.get('latitude'), {'id': str((vehicle.get('vehicle') or {}).get('id') or entity.get('id', 'sin-id')), 'label': str((vehicle.get('vehicle') or {}).get('label') or entity.get('id', 'Vehículo')), 'observed_at': timestamp(vehicle.get('timestamp')), 'received_at': received, 'published_at': timestamp(feed.get('header', {}).get('timestamp')), 'speed_m_s': speed if numeric(speed) and speed >= 0 else None, 'track_id': None, 'kind': 'observation', 'source': 'rail'})
        if feature:
            trip = vehicle.get('trip') or {}
            feature['properties'].update(entity_id=entity.get('id'), trip_id=trip.get('tripId') or trip.get('trip_id'), operator=None, operator_basis=None, route_id=trip.get('routeId') or trip.get('route_id'), start_date=trip.get('startDate') or trip.get('start_date'), stop_id=vehicle.get('stopId') or vehicle.get('stop_id'), current_status=vehicle.get('currentStatus') or vehicle.get('current_status'), stop_sequence=vehicle.get('currentStopSequence') or vehicle.get('current_stop_sequence'), bearing_deg=position.get('bearing'), odometer_m=position.get('odometer'), occupancy=vehicle.get('occupancyStatus') or vehicle.get('occupancy_status'))
            features.append(feature)
    return (features, timestamp(feed.get('header', {}).get('timestamp')))

def dgt(body, received):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('Declaraciones XML no admitidas')
    root = ET.fromstring(body)

    def local(node):
        return node.tag.rsplit('}', 1)[-1]

    def first(node, name):
        return next((child.text for child in node.iter() if local(child) == name), None)
    features = []
    records = [node for node in root.iter() if local(node) == 'situationRecord']
    if not records and (not any((local(node) == 'situationPublication' for node in root.iter()))) and ('SituationPublication' not in str(root.attrib)):
        raise ValueError('No se reconoce SituationPublication DATEX II')
    for record in records:
        try:
            lon, lat = (float(first(record, 'longitude')), float(first(record, 'latitude')))
        except (TypeError, ValueError):
            continue
        feature = point(lon, lat, {'id': record.attrib.get('id', 'sin-id'), 'label': record.attrib.get('{http://www.w3.org/2001/XMLSchema-instance}type', 'Incidencia DGT').split(':')[-1], 'observed_at': None, 'updated_at': first(record, 'situationRecordVersionTime'), 'valid_from': first(record, 'overallStartTime'), 'valid_to': first(record, 'overallEndTime'), 'received_at': received, 'kind': 'observation', 'source': 'dgt', 'road_name': first(record, 'roadNumber') or first(record, 'roadName'), 'description': first(record, 'value'), 'cause': first(record, 'causeType'), 'validity_status': first(record, 'validityStatus'), 'municipality': first(record, 'municipality'), 'province': first(record, 'province'), 'start_pk': next((first(node, 'kilometerPoint') for node in record.iter() if local(node) == 'from'), None) or first(record, 'fromKilometre'), 'end_pk': next((first(node, 'kilometerPoint') for node in record.iter() if local(node) == 'to'), None) or first(record, 'toKilometre'), 'location_basis': 'Coordenada explícita publicada; puede ser un extremo de la localización lineal'})
        if feature:
            features.append(feature)
    return (features, first(root, 'publicationTime'))

def roads(body, received):
    if body.lstrip().startswith(b'<'):
        if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
            raise ValueError('Declaraciones XML no admitidas')
        root = ET.fromstring(body)
        if root.tag != 'osm':
            raise ValueError('Se esperaba OSM XML')
        nodes = {item.attrib['id']: [float(item.attrib['lon']), float(item.attrib['lat'])] for item in root.findall('node')}
        features = []
        for way in root.findall('way'):
            tags = {tag.attrib['k']: tag.attrib['v'] for tag in way.findall('tag')}
            refs = [node.attrib['ref'] for node in way.findall('nd')]
            if not tags.get('highway') or len(refs) < 2 or any((ref not in nodes for ref in refs)):
                continue
            features.append({'type': 'Feature', 'id': way.attrib['id'], 'geometry': {'type': 'LineString', 'coordinates': [nodes[ref] for ref in refs]}, 'properties': tags})
        body = json.dumps({'type': 'FeatureCollection', 'features': features}).encode()
    feed = json.loads(body)
    if feed.get('type') != 'FeatureCollection' or not isinstance(feed.get('features'), list):
        raise ValueError('Se necesita FeatureCollection GeoJSON')
    features = []
    for index, item in enumerate(feed['features']):
        geometry = item.get('geometry') or {}
        if geometry.get('type') not in ('LineString', 'MultiLineString'):
            continue
        coords = geometry.get('coordinates', [])
        lines = [coords] if geometry['type'] == 'LineString' else coords
        if not lines or any((len(line) < 2 or any((len(p) < 2 or not point(p[0], p[1], {}) for p in line)) for line in lines)):
            raise ValueError('Geometría viaria inválida')
        properties = item.get('properties') or {}
        features.append({'type': 'Feature', 'geometry': geometry, 'properties': {'id': str(item.get('id', index)), 'label': str(properties.get('name') or properties.get('ref') or 'Tramo'), 'observed_at': None, 'received_at': received, 'source': 'roads', 'kind': 'reference'}})
    return (features, None)
ADAPTERS = {'rail': rail, 'dgt': dgt, 'roads': roads}
