ALTER TABLE features ADD CONSTRAINT features_valid_geometry CHECK (ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry));
