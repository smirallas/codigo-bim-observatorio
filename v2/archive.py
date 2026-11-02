"""Archivo PostgreSQL/PostGIS. Cada captura y sus geometrías se confirman juntas."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def instant(value):
    time = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if time.tzinfo is None:
        raise ValueError('Se necesita zona horaria')
    return time.astimezone(timezone.utc)


class Archive:
    def __init__(self, dsn):
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row)

    def migrate(self):
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(219701)")
            db.execute('CREATE EXTENSION IF NOT EXISTS postgis')
            db.execute('CREATE TABLE IF NOT EXISTS migrations (name text PRIMARY KEY, sha256 text NOT NULL)')
            for file in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                old = db.execute('SELECT sha256 FROM migrations WHERE name=%s', (file.name,)).fetchone()
                if old:
                    if old['sha256'] != digest:
                        raise ValueError('Migración aplicada modificada: ' + file.name)
                    continue
                db.execute(file.read_text(encoding='utf-8'))
                db.execute('INSERT INTO migrations VALUES (%s,%s)', (file.name, digest))

    def add(self, source, received_at, original, features, kind='observation', published_at=None, metadata=None):
        digest = hashlib.sha256(original).hexdigest()
        received = instant(received_at)
        published = instant(published_at) if published_at else None
        # Serialización estricta antes de abrir la transacción (NaN no es JSON válido).
        json.dumps(features, allow_nan=False)
        with self.connect() as db:
            row = db.execute('''INSERT INTO captures(source,received_at,published_at,sha256,original,normalized,kind,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source,received_at,sha256)
                DO UPDATE SET sha256=excluded.sha256 RETURNING id''',
                (source, received, published, digest, original, Jsonb(features), kind, Jsonb(metadata or {}))).fetchone()
            capture_id = row['id']
            for index, feature in enumerate(features):
                db.execute('''INSERT INTO features VALUES (%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s)
                    ON CONFLICT DO NOTHING''', (capture_id, index, json.dumps(feature['geometry']), Jsonb(feature['properties'])))
        return {'id': capture_id, 'sha256': digest, 'features': len(features)}

    def attempt(self, source, status, error_type=None, http_status=None):
        with self.connect() as db:
            db.execute('''INSERT INTO attempts VALUES (%s,now(),%s,%s,%s) ON CONFLICT(source)
                DO UPDATE SET attempted_at=excluded.attempted_at,status=excluded.status,
                error_type=excluded.error_type,http_status=excluded.http_status''',
                (source, status, error_type, http_status))

    def latest(self, source, at=None, bbox=None):
        cutoff = instant(at) if at else datetime.now(timezone.utc)
        with self.connect() as db:
            capture = db.execute('''SELECT id,source,received_at,published_at,sha256,kind,metadata FROM captures
                WHERE source=%s AND received_at<=%s AND (published_at IS NULL OR published_at<=%s)
                ORDER BY received_at DESC,id DESC LIMIT 1''', (source, cutoff, cutoff)).fetchone()
            if not capture:
                return None
            params = [capture['id']]
            spatial = ''
            if bbox:
                spatial = ' AND geometry && ST_MakeEnvelope(%s,%s,%s,%s,4326)'
                params.extend(bbox)
            rows = db.execute('SELECT ordinal,ST_AsGeoJSON(geometry)::json AS geometry,properties FROM features WHERE capture_id=%s' + spatial + ' ORDER BY ordinal', params).fetchall()
            visible = []
            for row in rows:
                prop = row['properties']
                prop['capture_id']=capture['id'];prop['ordinal']=row['ordinal'];prop['feature_key']=str(capture['id'])+':'+str(row['ordinal'])
                if prop.get('observed_at') and instant(prop['observed_at']) > cutoff:
                    continue
                visible.append({'type': 'Feature', **row})
            attempt = db.execute('SELECT * FROM attempts WHERE source=%s AND attempted_at<=%s', (source,cutoff)).fetchone()
            return {**{key: value.isoformat() if isinstance(value, datetime) else value for key, value in capture.items()},
                    'features': visible, 'attempt': {key: value.isoformat() if isinstance(value, datetime) else value for key, value in (attempt or {}).items()}}

    def prune(self, days=7, max_per_source=10080, source=None):
        if days < 1 or max_per_source < 1:
            raise ValueError('Retención inválida')
        with self.connect() as db:
            db.execute("DELETE FROM captures WHERE received_at < now() - make_interval(days => %s) AND (%s::text IS NULL OR source=%s)", (days,source,source))
            db.execute('''DELETE FROM captures WHERE id IN (SELECT id FROM
                (SELECT id,row_number() OVER(PARTITION BY source ORDER BY received_at DESC,id DESC) AS rank FROM captures) ranked
                WHERE rank>%s) AND (%s::text IS NULL OR source=%s)''', (max_per_source,source,source))
