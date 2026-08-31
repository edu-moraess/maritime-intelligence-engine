-- MIE V2 E1/E2 corrective migration.
-- 001 created the inline PostgreSQL names used below:
--   ais_observations_payload_hash_key
--   ais_observations_ais_timestamp_second_check
-- Existing 60–63 values are special AIS states, not ordinary seconds; they are
-- nulled rather than converted or mapped to an absolute timestamp.

UPDATE ais_observations
SET ais_timestamp_second = NULL
WHERE ais_timestamp_second IS NOT NULL
  AND ais_timestamp_second NOT BETWEEN 0 AND 59;

ALTER TABLE ais_observations
    DROP CONSTRAINT IF EXISTS ais_observations_ais_timestamp_second_check;

ALTER TABLE ais_observations
    DROP CONSTRAINT IF EXISTS ais_observations_ais_timestamp_second_normal_check;

ALTER TABLE ais_observations
    ADD CONSTRAINT ais_observations_ais_timestamp_second_normal_check
    CHECK (ais_timestamp_second BETWEEN 0 AND 59);

ALTER TABLE ais_observations
    DROP CONSTRAINT IF EXISTS ais_observations_payload_hash_key;

DROP INDEX IF EXISTS ais_observations_payload_hash_key;

ALTER TABLE ais_observations
    DROP CONSTRAINT IF EXISTS ais_observations_session_payload_hash_key;

ALTER TABLE ais_observations
    ADD CONSTRAINT ais_observations_session_payload_hash_key
    UNIQUE (session_id, payload_hash);
