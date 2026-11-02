CREATE TABLE network_imports (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 kind text NOT NULL CHECK(kind IN ('railway','highways')),
 source_url text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 status text NOT NULL DEFAULT 'loading' CHECK(status IN ('loading','complete','failed')),
 coverage geometry(Polygon,4326) NOT NULL,
 pages integer NOT NULL DEFAULT 0,
 segments integer NOT NULL DEFAULT 0,
 error_type text
);
CREATE TABLE network_pages (
 import_id bigint NOT NULL REFERENCES network_imports(id) ON DELETE CASCADE,
 page_index integer NOT NULL,
 sha256 char(64) NOT NULL,
 original_gzip bytea NOT NULL,
 PRIMARY KEY(import_id,page_index)
);
CREATE TABLE network_segments (
 import_id bigint NOT NULL REFERENCES network_imports(id) ON DELETE CASCADE,
 segment_id text NOT NULL,
 geometry geometry(LineString,4326) NOT NULL CHECK(ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry)),
 attributes jsonb NOT NULL,
 fictitious boolean,
 PRIMARY KEY(import_id,segment_id)
);
CREATE INDEX network_segments_geography ON network_segments USING gist((geometry::geography));
CREATE INDEX network_segments_geometry ON network_segments USING gist(geometry);
CREATE TABLE schedule_imports (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 received_at timestamptz NOT NULL DEFAULT now(),
 source_url text NOT NULL,
 sha256 char(64) NOT NULL,
 original bytea NOT NULL
);
CREATE TABLE schedule_stops (
 import_id bigint NOT NULL REFERENCES schedule_imports(id) ON DELETE CASCADE,
 stop_id text NOT NULL,
 name text NOT NULL,
 PRIMARY KEY(import_id,stop_id)
);
CREATE TABLE schedule_trips (
 import_id bigint NOT NULL REFERENCES schedule_imports(id) ON DELETE CASCADE,
 trip_id text NOT NULL,
 details jsonb NOT NULL,
 PRIMARY KEY(import_id,trip_id)
);
