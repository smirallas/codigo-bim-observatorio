"""Adaptadores separados; ningún campo ausente se convierte en observación inventada."""
from datetime import datetime, timezone
import json
import math
import xml.etree.ElementTree as ET
CATALOG = {'rail': {'title': 'Posiciones ferroviarias', 'group': 'Ferrocarril', 'color': '#136b60', 'kind': 'observation', 'ttl': 120, 'attribution': 'Renfe Data · CC BY 4.0', 'url': 'https://data.renfe.com/es/dataset/posicion-vehiculos-av-ld-md'}}

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
ADAPTERS = {'rail': rail}
