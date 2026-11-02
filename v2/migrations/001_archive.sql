CREATE TABLE captures (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source text NOT NULL,
 received_at timestamptz NOT NULL,
 published_at timestamptz,
 sha256 char(64) NOT NULL,
 original bytea NOT NULL,
 normalized jsonb NOT NULL,
 kind text NOT NULL CHECK(kind IN ('observation','forecast','synthetic','reference')),
 UNIQUE(source, received_at, sha256)
);
CREATE INDEX captures_lookup ON captures(source, received_at DESC, id DESC);
CREATE TABLE features (
 capture_id bigint NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
 ordinal integer NOT NULL,
 geometry geometry(Geometry,4326) NOT NULL,
 properties jsonb NOT NULL,
 PRIMARY KEY(capture_id,ordinal)
);
CREATE INDEX features_geometry ON features USING gist(geometry);
CREATE TABLE attempts (
 source text PRIMARY KEY,
 attempted_at timestamptz NOT NULL,
 status text NOT NULL,
 error_type text,
 http_status integer
);
