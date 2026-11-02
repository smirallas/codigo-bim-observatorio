"""Capas sintéticas de ejemplo, disponibles sin consultas ni credenciales."""
from sources import point
AT = '2026-11-01T12:00:00+00:00'

def layers():
    common = {'kind': 'synthetic', 'received_at': AT, 'observed_at': AT}
    return {'rail': [point(-3.8, 39.7, {**common, 'id': 'SIM-TREN', 'label': 'Tren sintético', 'source': 'rail', 'speed_m_s': None})]}
