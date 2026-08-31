-- Align the historical observation INSERT conflict target with the writer.
-- ais_observations.payload_hash is already globally unique, but the writer
-- uses (session_id, payload_hash) as its ON CONFLICT target. PostgreSQL
-- requires an exact matching unique/exclusion constraint for that target.
-- Keep the existing global uniqueness rule and add the matching composite
-- unique index so the INSERT remains valid and idempotent.

CREATE UNIQUE INDEX IF NOT EXISTS idx_ais_observations_session_payload_hash
    ON ais_observations (session_id, payload_hash);
