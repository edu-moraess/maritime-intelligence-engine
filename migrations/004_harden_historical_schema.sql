-- MIE V2 historical schema hardening.
-- This migration is intentionally idempotent so it is safe against a database
-- that was partially provisioned or migrated outside the MIE migration ledger.

CREATE EXTENSION IF NOT EXISTS postgis;

-- The writer's ON CONFLICT target must have an exact matching unique index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ais_observations_session_payload_hash
    ON ais_observations (session_id, payload_hash);

-- AIS special timestamp states (60-63) are not ordinary seconds.
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

-- Keep the region seed set deterministic without overwriting operator data.
INSERT INTO regions (name, bbox, iana_timezone)
VALUES
    ('Miami', ST_MakeEnvelope(-80.208, 25.603, -79.879, 25.835, 4326), 'America/New_York'),
    ('Santos', ST_MakeEnvelope(-46.800, -24.200, -46.000, -23.700, 4326), 'America/Sao_Paulo'),
    ('Singapore', ST_MakeEnvelope(103.550, 1.150, 104.200, 1.500, 4326), 'Asia/Singapore'),
    ('Rotterdam', ST_MakeEnvelope(3.800, 51.750, 4.800, 52.100, 4326), 'Europe/Amsterdam'),
    ('English Channel', ST_MakeEnvelope(-5.500, 49.800, 2.500, 51.500, 4326), 'UTC')
ON CONFLICT (name) DO NOTHING;
