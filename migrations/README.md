# Historical schema migrations

The migrations in `001_initial_historical.sql` and `002_fix_historical_constraints.sql` create and correct the optional PostgreSQL/PostGIS schema for MIE V2 E1/E2. They are intentionally small and use PostGIS geometry with SRID 4326. Migration 002 changes the legacy global payload uniqueness to `UNIQUE (session_id, payload_hash)` and restricts normal AIS seconds to 0–59; existing special values are set to NULL rather than converted.

The application applies pending SQL files lazily on the first collection that receives valid real AIS observations only when both `DATABASE_URL` and the explicit persistence opt-in are enabled. The migration runner records applied filenames in `mie_schema_migrations`. It must never be used to seed synthetic AIS data.

For an external PostgreSQL/PostGIS service, apply the files with an operator-controlled migration process or allow the explicitly enabled `HistoricalWriter` to apply them on first valid collection. `DATABASE_URL` is optional and `HISTORICAL_PERSISTENCE_ENABLED` defaults to false: when either is absent/off, the application remains LIVE-ONLY and does not connect. The Streamlit Community Cloud app must not run a local PostgreSQL service.

The writer uses `ON CONFLICT (session_id, payload_hash) DO NOTHING` for per-session idempotent factual observation inserts. The same real payload may therefore be stored once in each distinct collection session. `Clear Session` only clears live in-memory state; it never deletes historical rows.
