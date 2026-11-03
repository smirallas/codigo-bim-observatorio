"""Crear configuración local sin sobrescribir secretos existentes ni imprimirlos."""
from pathlib import Path
import secrets

path=Path(__file__).parent/'.env'
with path.open('x',encoding='utf-8') as file:
    file.write('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\nLAB_PORT=8042\nENABLED_SOURCES=rail,roads,dgt,flights,schedule,weather_maps\n')
print('Configuración local creada. No compartir .env.')
