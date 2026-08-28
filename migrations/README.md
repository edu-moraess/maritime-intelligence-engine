# Historical schema migrations

The migration in `001_initial_historical.sql` creates the optional PostgreSQL/PostGIS schema for MIE V2 E1/E2. It is intentionally small and uses PostGIS geometry with SRID 4326.

The application applies pending SQL files lazily on the first collection that receives valid real AIS observations. The migration runner records applied filenames in `mie_schema_migrations`. It must never be used to seed synthetic AIS data.

For an external PostgreSQL/PostGIS service, apply the file with an operator-controlled migration process or allow the configured `HistoricalWriter` to apply it on first valid collection. `DATABASE_URL` is optional: when absent, the application remains LIVE-ONLY and does not connect. The Streamlit Community Cloud app must not run a local PostgreSQL service.

The writer uses `payload_hash` with `ON CONFLICT DO NOTHING` for idempotent factual observation inserts. `Clear Session` only clears live in-memory state; it never deletes historical rows.
