CREATE TABLE IF NOT EXISTS collection_session_regions (
    session_id UUID NOT NULL REFERENCES collection_sessions(session_id) ON DELETE CASCADE,
    region_index INTEGER NOT NULL CHECK (region_index >= 0),
    bbox geometry(POLYGON, 4326) NOT NULL,
    PRIMARY KEY (session_id, region_index)
);

CREATE INDEX IF NOT EXISTS idx_collection_session_regions_session_id
    ON collection_session_regions (session_id);

CREATE INDEX IF NOT EXISTS idx_collection_session_regions_bbox_gist
    ON collection_session_regions USING GIST (bbox);
