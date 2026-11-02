"""Recolector central: configuración del servidor, nunca URLs recibidas del visitante."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import gzip
import io
import random
import time
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from archive import Archive
from sources import ADAPTERS, CATALOG
URLS = {'rail': 'https://gtfsrt.renfe.com/vehicle_positions_LD.json', 'dgt': os.getenv('DGT_URL', 'https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v37.xml'), 'flights': 'https://opensky-network.org/api/states/all?lamin=38&lomin=-5&lamax=41&lomax=-2', 'weather': 'https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=39.7000&lon=-3.8000', 'roads': os.getenv('ROADS_URL') or 'https://www.openstreetmap.org/api/0.6/map?bbox=-3.705,40.414,-3.695,40.420'}
MAX_BYTES = 15000000
FLIGHT_URLS = {'adsblol': 'https://api.adsb.lol/v2/point/39.7/-3.8/100', 'opensky': 'https://opensky-network.org/api/states/all?lamin=38&lomin=-5&lamax=41&lomax=-2'}

def public_url(url):
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.urlencode([(key, value) for key, value in urllib.parse.parse_qsl(parsed.query) if key.lower() not in ('apikey', 'api_key', 'token', 'access_token', 'key', 'secret', 'client_secret')])
    host = parsed.hostname or ''
    if parsed.port:
        host += ':' + str(parsed.port)
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, query, ''))

def download(url, headers=None, data=None, info=None):
    if not url.startswith('https://'):
        raise ValueError('Solo fuentes HTTPS configuradas en el servidor')
    request = urllib.request.Request(url, data=data, headers={'User-Agent': 'CodigoBIM-DataLab/2.0 https://codigobim.com/', 'Accept-Encoding': 'gzip', **(headers or {})})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(MAX_BYTES + 1)
        if info is not None:
            info.update({key.lower(): response.headers[key] for key in ('Expires', 'Last-Modified', 'Content-Encoding') if response.headers.get(key)})
        encoding = response.headers.get('Content-Encoding')
    if len(body) > MAX_BYTES:
        raise ValueError('Límite de tamaño de fuente')
    if encoding == 'gzip':
        body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Límite de tamaño descomprimido')
    return body

def collect_one(archive, source):
    try:
        if source == 'weather_maps':
            from weather_maps import collect_metadata
            return collect_metadata(archive)
        if source == 'schedule':
            with archive.connect() as db:
                previous = db.execute("SELECT id FROM schedule_imports WHERE received_at>now()-interval '6 hours' ORDER BY received_at DESC LIMIT 1").fetchone()
            if previous:
                return {'source': 'schedule', 'status': 'cached'}
            from schedule import import_schedule
            return {'source': 'schedule', 'status': 'ok', **import_schedule(archive)}
        url = URLS[source]
        provider = os.getenv('FLIGHTS_PROVIDER', 'adsblol')
        if source == 'flights':
            url = FLIGHT_URLS[provider]
        if not url:
            archive.attempt(source, 'not_configured')
            return {'source': source, 'status': 'not_configured'}
        headers = {}
        if source == 'weather':
            previous = archive.latest(source)
            metadata = previous.get('metadata', {}) if previous else {}
            expires = metadata.get('expires')
            if expires and datetime.now(timezone.utc) < parsedate_to_datetime(expires):
                archive.attempt(source, 'cached')
                return {'source': source, 'status': 'cached'}
            if metadata.get('last-modified'):
                headers['If-Modified-Since'] = metadata['last-modified']
        if source == 'flights' and provider == 'opensky' and os.getenv('OPENSKY_CLIENT_ID') and os.getenv('OPENSKY_CLIENT_SECRET'):
            payload = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': os.environ['OPENSKY_CLIENT_ID'], 'client_secret': os.environ['OPENSKY_CLIENT_SECRET']}).encode()
            token = json.loads(download('https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token', {'Content-Type': 'application/x-www-form-urlencoded'}, payload))['access_token']
            headers['Authorization'] = 'Bearer ' + token
        info = {}
        body = download(url, headers, info=info)
        received = datetime.now(timezone.utc).isoformat()
        features, published = ADAPTERS[source](body, received)
        if source == 'rail':
            for feature in features:
                feature['properties'].update(operator='Renfe', operator_basis='Feed oficial Renfe AV/LD/MD; no representa a todos los operadores')
        attribution = 'OpenSky Network · sujeto a sus condiciones de uso' if source == 'flights' and provider == 'opensky' else CATALOG[source]['attribution']
        report = archive.add(source, received, body, features, CATALOG[source]['kind'], published, {'url': public_url(url), 'adapter_version': '2.0.0', 'attribution': attribution, **info})
        archive.attempt(source, 'ok', http_status=200)
        return {'source': source, 'status': 'ok', **report}
    except Exception as error:
        code = error.code if isinstance(error, urllib.error.HTTPError) else None
        if code == 304:
            archive.attempt(source, 'cached', http_status=304)
            return {'source': source, 'status': 'cached'}
        archive.attempt(source, 'error', type(error).__name__, code)
        return {'source': source, 'status': 'error', 'error_type': type(error).__name__, 'http_status': code}
DEFAULT_INTERVALS = {'rail': 60, 'dgt': 120, 'flights': 60, 'weather': 10800, 'weather_maps': 3600, 'roads': 2592000, 'schedule': 21600}
MIN_INTERVALS = {'rail': 30, 'dgt': 60, 'flights': 30, 'weather': 1800, 'weather_maps': 1800, 'roads': 86400, 'schedule': 3600}

def source_interval(source, failures=0):
    configured = int(os.getenv(source.upper() + '_INTERVAL', str(DEFAULT_INTERVALS[source])))
    base = max(MIN_INTERVALS[source], configured)
    return base if not failures else max(base, min(900, base * 2 ** min(failures, 5)))

def run(archive, sources):
    next_due = {source: 0 for source in sources}
    failures = {source: 0 for source in sources}
    pending = {}
    pruned = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        while True:
            Path('/tmp/collector-heartbeat').touch()
            now = time.monotonic()
            for source, future in list(pending.items()):
                if not future.done():
                    continue
                result = future.result()
                print(json.dumps(result), flush=True)
                failures[source] = failures[source] + 1 if result['status'] == 'error' else 0
                next_due[source] = now + source_interval(source, failures[source]) + random.uniform(0, 3)
                del pending[source]
            for source in sources:
                if source not in pending and now >= next_due[source]:
                    pending[source] = executor.submit(collect_one, archive, source)
            if now - pruned >= 3600:
                archive.prune()
                pruned = now
            time.sleep(1)
if __name__ == '__main__':
    archive = Archive(os.environ['DATABASE_URL'])
    archive.migrate()
    sources = [key.strip() for key in os.getenv('ENABLED_SOURCES', 'rail').split(',') if key.strip()]
    if any((key not in ADAPTERS and key not in ('weather_maps', 'schedule') for key in sources)):
        raise ValueError('Fuente desconocida')
    if os.getenv('COLLECT_ONCE') == '1':
        for source in sources:
            print(json.dumps(collect_one(archive, source)), flush=True)
    else:
        run(archive, sources)
