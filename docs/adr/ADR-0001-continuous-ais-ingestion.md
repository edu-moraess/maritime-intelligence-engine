# ADR-0001: Continuous AIS ingestion ownership for MIE

- Status: ACCEPTED FOR PROCESS-LOCAL P0 PROTOTYPE — runtime acceptance pending
- Date: 2026-11-13
- Scope: P0.1/P0.2 operational reliability
- Supersedes: none

## Implementation checkpoint (2026-11-13)

The branch now contains a first process-local implementation of this decision:

- `AISIngestionWorker` owns the provider stream in one daemon thread, with explicit start/stop, a bounded queue (default capacity 5,000), queue-drop telemetry, and a receive-freshness state.
- `AISStreamProvider.stream(..., message_limit=0)` supports a managed continuous mode without the finite collection cap. The legacy finite-window cap remains the default for existing callers.
- The Streamlit app obtains its engine from a process-shared `st.cache_resource` registry. One active engine/worker configuration is selected per Python process; changing the active configuration stops and closes the previous engine before replacement.
- The app exposes explicit Start Live AIS / Stop Live AIS controls and refreshes the operational page using a two-second Streamlit fragment.
- Engine mutations and snapshots are serialized with an engine-level reentrant lock. Analytics recomputation during live ingestion is throttled to at most once every ten seconds; operational vessel positions are updated as observations are drained.
- A stopped continuous session is persisted through the existing historical writer. Last-known targets remain in the vessel snapshot and are now included on the overview map by default with a distinct stale style and actual last-report age.

This remains a process-local design. A deployment with multiple replicas or independent Python worker processes can still open one subscription per process. There is no cross-replica lease or leader election.

Automated tests for worker lifecycle, continuous message-limit bypass, provider reconnect telemetry, engine drain/stop behavior, and stale target presentation have been added or updated. They have **not yet been executed** in this environment. The 30-minute live-network acceptance test and Colab full-suite validation remain mandatory before production acceptance.

## Context

The current application starts a finite AIS collection synchronously from `app.py::main`. The provider consumes the WebSocket in the caller's thread and exits at the configured collection deadline. The Streamlit session owns the engine, while the provider's successful receive state can remain `LIVE AIS` after the socket is closed.

The requested behavior is continuous ingestion independent of the currently selected page. The deployment may run more than one Python process or replica; a Python singleton is not a distributed singleton.

## Decision proposed

Introduce a process-local ingestion runtime with the following responsibilities:

1. Own exactly one worker per normalized ingestion configuration within a Python process.
2. Own the provider connection and its stop event.
3. Publish validated AIS observations through a bounded, thread-safe queue.
4. Expose immutable health snapshots: lifecycle state, last successful receive, reconnect counters/timestamps, last error, queue depth, and drop count.
5. Keep Streamlit pages as readers/command clients; page rendering must not create a worker.
6. Have the engine drain observations under an engine-level lock, update session state atomically, and publish immutable snapshots.
7. Provide explicit stop/join with a bounded timeout for configuration changes and process shutdown.

The initial implementation must remain process-local. If deployment has multiple workers/replicas, each process may create its own AIS subscription. This limitation must be surfaced in the System page and deployment documentation. Global exclusivity requires a separate coordinator/worker deployment and is out of scope until justified.

## Queue and failure policy

- Queue capacity must be finite and configurable.
- Queue overflow must never silently masquerade as healthy ingestion. Count dropped observations, set health to DEGRADED, and expose the counter.
- Do not silently drop data to hide PostgreSQL outages. The in-memory queue/store and historical writer need explicit bounded retry behavior; a persistent outbox is a separate design decision if lossless buffering across process restarts is required.
- A provider exception must be captured as a sanitized error; reconnect attempts use bounded exponential backoff with jitter.
- A successful connection is not sufficient for LIVE. LIVE requires a recent accepted PositionReport within a configured freshness window.
- On stale feed, transition to DEGRADED; on worker stop, transition to STOPPED; on terminal configuration/provider error, transition to ERROR.

## Concurrency invariants

1. Only the worker thread calls the provider's blocking stream iterator.
2. Only the engine's drain/commit operation mutates engine session analytics.
3. The engine lock protects generation changes and all fields that must be observed as one snapshot.
4. No Streamlit API is called from the worker thread.
5. No provider or engine worker is created from a page renderer or rerun callback.
6. Worker start is idempotent for the same process-local runtime key.
7. Stop is idempotent; a new worker is not started until the previous worker has terminated or a clear ERROR is exposed.
8. Queue overflow, reconnects, and persistence failures are observable.

## Compatibility and rollout

- Preserve the current finite collection mode behind the existing operator action during the first rollout.
- Add continuous mode as an explicit operational mode only after deterministic fake-provider tests pass.
- Do not remove legacy state literals until every UI consumer and test has been migrated.
- Avoid Redis, Kafka, Celery, or new infrastructure in this phase.
- Keep historical database schema unchanged.

## Required validation gates

### Automated deterministic tests
- start is idempotent;
- stop unblocks a fake provider and joins;
- provider exceptions increment reconnect telemetry;
- accepted observations are delivered exactly once to the engine queue;
- queue saturation increments drop telemetry and degrades health;
- LIVE expires after the freshness threshold without a new message;
- repeated Streamlit rerun/read calls do not create additional workers;
- concurrent snapshot and drain operations never expose a mixed generation;
- configuration change stops the old worker before replacement;
- all legacy finite-window tests continue to pass.

### Runtime acceptance
- 30-minute navigation test across Overview, Analysis/Data, Fleet, Behavior, SPLIT, and UNIFIED while messages continue arriving;
- network interruption causes a visible non-LIVE state within the documented threshold;
- network restoration is evidenced by a reconnect and newly received messages;
- stale last-known positions remain visible with explicit age and never use the LIVE style;
- restart and persistence recovery preserve historical integrity.

## Consequences

Positive:
- Streamlit navigation no longer owns the WebSocket lifecycle.
- Feed health becomes measurable rather than inferred from a stale status string.
- Concurrency and deployment boundaries become explicit.

Costs/risks:
- Thread lifecycle and process shutdown require careful testing.
- Process-local ownership does not prevent duplicate subscriptions across multiple replicas.
- A bounded queue requires an explicit overflow policy.
- Engine snapshot locking may increase contention if analytics remain inside the critical section.

## Approval gate

This ADR is a design proposal, not evidence that continuous ingestion has been implemented. Implementation must follow the baseline audit, preserve the finite-window path until parity is proven, and must not claim global single-instance behavior on a multi-process deployment.
