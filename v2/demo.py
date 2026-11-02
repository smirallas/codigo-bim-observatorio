"""Capas sintéticas de ejemplo, disponibles sin consultas ni credenciales."""
from sources import point
AT = '2026-11-01T12:00:00+00:00'

def layers():
    common = {'kind': 'synthetic', 'received_at': AT, 'observed_at': AT}
    return {'rail': [point(-3.8, 39.7, {**common, 'id': 'SIM-TREN', 'label': 'Tren sintético', 'source': 'rail', 'speed_m_s': None})], 'roads': [{'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [[-3.9, 39.65], [-3.8, 39.7], [-3.7, 39.75]]}, 'properties': {**common, 'id': 'SIM-CARRETERA', 'label': 'Carretera sintética', 'source': 'roads'}}], 'dgt': [point(-3.79, 39.705, {**common, 'id': 'SIM-INCIDENCIA', 'label': 'Obras sintéticas', 'source': 'dgt'})], 'flights': [point(-3.82, 39.72, {**common, 'id': 'SIM-VUELO', 'label': 'Aeronave sintética', 'source': 'flights', 'altitude_m': 8000})], 'weather': [point(-3.77, 39.68, {**common, 'observed_at': None, 'valid_at': AT, 'id': 'SIM-METEO', 'label': 'Predicción sintética', 'source': 'weather', 'temperature_c': 14, 'precipitation_mm': 2})]}
