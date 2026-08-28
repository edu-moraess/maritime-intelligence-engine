CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS regions (
    region_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    bbox geometry(POLYGON, 4326) NOT NULL,
    iana_timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS collection_sessions (
    session_id UUID PRIMARY KEY,
    region_id BIGINT REFERENCES regions(region_id) ON DELETE SET NULL,
    bbox geometry(POLYGON, 4326) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    collection_seconds DOUBLE PRECISION NOT NULL CHECK (collection_seconds >= 0),
    messages_received INTEGER NOT NULL DEFAULT 0 CHECK (messages_received >= 0),
    pipeline_version TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'AISSTREAM'
);

CREATE TABLE IF NOT EXISTS vessels (
    mmsi TEXT PRIMARY KEY,
    last_known_name TEXT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ais_observations (
    observation_id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES collection_sessions(session_id) ON DELETE CASCADE,
    mmsi TEXT NOT NULL REFERENCES vessels(mmsi),
    geom geometry(POINT, 4326) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    ais_timestamp_second SMALLINT NULL CHECK (ais_timestamp_second BETWEEN 0 AND 63),
    observed_at TIMESTAMPTZ NULL,
    sog_knots DOUBLE PRECISION NULL,
    cog_degrees DOUBLE PRECISION NULL,
    heading_degrees DOUBLE PRECISION NULL,
    vessel_name TEXT NULL,
    navigational_status INTEGER NULL,
    valid BOOLEAN NOT NULL,
    payload_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_ais_observations_mmsi_received_at
    ON ais_observations (mmsi, received_at);
CREATE INDEX IF NOT EXISTS idx_ais_observations_geom_gist
    ON ais_observations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_ais_observations_session_id
    ON ais_observations (session_id);
CREATE INDEX IF NOT EXISTS idx_collection_sessions_region_id
    ON collection_sessions (region_id);

INSERT INTO regions (name, bbox, iana_timezone)
VALUES
    ('Miami', ST_MakeEnvelope(-80.208, 25.603, -79.879, 25.835, 4326), 'America/New_York'),
    ('Santos', ST_MakeEnvelope(-46.800, -24.200, -46.000, -23.700, 4326), 'America/Sao_Paulo'),
    ('Singapore', ST_MakeEnvelope(103.550, 1.150, 104.200, 1.500, 4326), 'Asia/Singapore'),
    ('Rotterdam', ST_MakeEnvelope(3.800, 51.750, 4.800, 52.100, 4326), 'Europe/Amsterdam'),
    ('English Channel', ST_MakeEnvelope(-5.500, 49.800, 2.500, 51.500, 4326), 'UTC')
ON CONFLICT (name) DO NOTHING;

