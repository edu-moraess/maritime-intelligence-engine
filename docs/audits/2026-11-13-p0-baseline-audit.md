# MIE P0 Baseline Audit — 2026-11-13

## Scope and provenance

- Repository: `edu-moraess/vyra-maritime-intell`
- Implementation branch: `feat/mie-p0-operational-reliability`
- Audited baseline commit: `5bbe456f657bd4524e71937cf73da420db4f0898`
- Audit method: read-only source inspection through GitHub contents API.
- Runtime tests: NOT RUN in this audit environment. No runtime behavior is claimed as independently reproduced.
- No production data, credentials, database records, or existing branches were modified.

## Confirmed by source inspection

### A1 — Collection is coupled to Streamlit's synchronous script

Evidence:
- `app.py::main` calls `engine.collect(seconds=...)` directly when the sidebar collection action is true.
- `MaritimeIntelligenceEngine.collect` synchronously iterates `self.provider.stream(..., duration_seconds=duration)`.
- `AISStreamProvider.stream` creates and consumes the WebSocket in the caller's thread and exits when its duration deadline is reached.

Impact:
- The Streamlit script is occupied during the collection window.
- The provider does not continue consuming after the requested finite window.
- Page navigation does not itself prove message loss; after the finite collection ends there is no active producer to receive new messages.

### A2 — The provider can retain a live-looking terminal state

Evidence:
- `AISStreamProvider._record` sets `_state = "LIVE AIS"`.
- At normal stream termination, `stream` closes the WebSocket and sets websocket status to CLOSED.
- The normal end-of-window branch does not transition a successful session out of `LIVE AIS`.

Impact:
- The status can describe a past successful receive rather than current feed vitality.

### A3 — Vessel snapshots are derived from the latest collection only

Evidence:
- `MaritimeIntelligenceEngine._current_session_tracks` groups `current_session_observations`.
- `_merged_vessels` derives vessel positions from those tracks and marks each stale using `settings.stale_after_seconds`.
- `snapshot` uses those vessels for the operational vessel list.

Impact:
- The map's operational targets depend on the latest finite session. Historical observations in the store are not automatically equivalent to current live targets.

### A4 — In-memory store already has internal synchronization

Evidence:
- `ObservationStore` uses a `threading.Lock` around append, extend, clear, and read operations.

Impact:
- The store has a basic thread-safe boundary, but this alone does not make the engine's multi-field state or snapshots atomic.

### A5 — Reconnect telemetry fields exist in the model but are not populated in provider status

Evidence:
- `IngestionStatus` declares reconnect attempts, last disconnect, last reconnect, and last error.
- `AISStreamProvider.status` constructs the status without supplying these optional fields, so their defaults are returned.

Impact:
- Consumers cannot treat these fields as measured reconnect telemetry.

### A6 — Engine state has no explicit synchronization boundary

Evidence:
- `snapshot` reads the store and then separately reads mutable engine fields (session observations, findings, embeddings, status, temporal results, regional events).
- `collect` and recomputation mutate those fields without an engine-level lock.

Impact:
- Introducing a background worker without an explicit engine synchronization strategy could expose mixed-generation snapshots or race conditions.

## Implementation constraints

1. A process-local singleton can prevent duplicate workers only within one Python process. It cannot guarantee one worker across multiple Streamlit replicas or server processes.
2. `st.session_state` is session-scoped and must not be used as cross-user or cross-process coordination.
3. A thread must have explicit start/stop semantics, bounded queue behavior, exception capture, and deterministic tests.
4. PostgreSQL outages must not silently discard in-memory observations; persistence retry/buffering policy must be explicit and bounded.
5. Historical positions must never be labeled live. Last-known positions require an explicit stale/age state.
6. Existing finite-window collection behavior should remain compatible until continuous-ingestion mode is proven.

## Gate before P0 implementation

- Capture and run the current test suite in the project-supported environment.
- Inventory every consumer of ingestion state and the legacy state literals.
- Define process-local ownership and deployment limitation.
- Define queue overflow and persistence failure policy.
- Add deterministic tests using a fake provider before enabling a real background worker.
- Do not claim the 30-minute live-network acceptance test from unit tests alone.

## Status

Baseline source audit: COMPLETE.
Runtime baseline: NOT RUN.
P0 implementation: PARTIAL — isolated worker primitive and deterministic tests added; not yet integrated into engine/Streamlit runtime.
