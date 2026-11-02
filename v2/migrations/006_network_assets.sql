ALTER TABLE network_imports ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}';
CREATE TABLE network_assets (
 import_id bigint NOT NULL REFERENCES network_imports(id) ON DELETE CASCADE,
 part integer NOT NULL,
 sha256 char(64) NOT NULL,
 original bytea NOT NULL,
 PRIMARY KEY(import_id,part)
);
CREATE TABLE network_aliases (
 import_id bigint NOT NULL REFERENCES network_imports(id) ON DELETE CASCADE,
 segment_id text NOT NULL,
 source_row bigint NOT NULL,
 attributes jsonb NOT NULL,
 PRIMARY KEY(import_id,source_row)
);
CREATE INDEX network_alias_segment ON network_aliases(import_id,segment_id);
