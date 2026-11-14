# MIE — Concept B Maturity Assessment

**Assessment date:** 2026-11-14  
**Repository:** `edu-moraess/vyra-maritime-intell`  
**Branch reviewed:** `fix/mie-p0-async-collection-safety`  
**Scope:** Read-only review of the existing application, UI modules, intelligence contracts, README and project-status documentation. No ingestion, engine, session, persistence, database, credential or deployment behavior was changed.

## Executive assessment

Concept B should be treated as a product-architecture and integration evolution, not as a request to recreate the five environments. The repository already contains substantial implementations for all five. The principal gap is the consistency and depth with which those capabilities are connected into one investigative workflow.

The most valuable next increment is to consolidate the existing **Vessel Intelligence** implementation around the deterministic profile contracts already present in `src/intelligence/profile.py`, while preserving explicit separation between live session evidence and persisted historical evidence. This is a narrower and more defensible step than adding another model or another dashboard.

## Capability matrix

| Concept B environment | Current implementation found | Maturity assessment | Remaining work |
|---|---|---|---|
| Operational Overview | Live operational bar, two-region monitoring, SPLIT/UNIFIED map, region comparison, regional events, environmental context, map layers and vessel selection | **Implemented** | Improve cross-page investigative continuity and information hierarchy; do not rebuild the overview. |
| Geospatial Intelligence | PyDeck/Plotly-backed tactical map, region filtering, observed trails, heading vectors, stale/freshness layers, traffic hexbin, anomaly types and hotspots | **Implemented, tactical depth** | Evolve toward analytical geospatial workflows only where there is a defined evidence-backed use case (spatial-temporal queries, corridor/area context and event-to-map navigation). |
| Vessel Intelligence | Vessel list/search, selected-vessel profile view, session telemetry, track/speed charts, anomaly timeline, historical-profile action and optional Gemini interpretation | **Implemented, integration gap** | Make the deterministic profile contract the canonical source for the page; expose identity, telemetry, movement, historical coverage, anomalies and confidence with provenance and explicit readiness. |
| Behavioral & Temporal Intelligence | PCA projection, KMeans clusters, Isolation Forest ranking, explainable findings, similarity search, TCN temporal adapter and track-coverage diagnostics | **Implemented, validation-limited** | Controlled out-of-sample validation, historical baselines and cross-session/cross-region comparability. Session-relative scores must remain explicitly session-relative. |
| Data Quality & Observability | Quality counters, freshness, reconnect/queue telemetry, temporal readiness, persistence state, provider/system diagnostics | **Implemented** | Consolidate these into an evidence-oriented observability view with clear source, time window, scope and failure reason. Avoid duplicating existing counters. |
| Collection & Session Management (transversal) | AIS controls, region presets, finite/continuous collection, session state, persistence controls and two-region configuration | **Implemented** | Preserve the current operational behavior; improve discoverability and explain session boundaries without changing collection semantics. |

## Evidence and important distinctions

### 1. Overview and geospatial workspace

The current overview is not an empty shell. It already supports regional snapshots, separate A/B selection state, SPLIT and UNIFIED rendering, a unified enclosing viewport, and presentation-only filtering that keeps regional analytical evidence separated. The map supports operational overlays and selected-vessel context.

**Assessment:** the map is already the primary operational surface. The Concept B opportunity is not simply to make it larger or add more layers. It is to connect map selections, vessel investigations, behavioral findings and temporal evidence into a coherent investigation path.

### 2. Vessel Intelligence — highest-value integration gap

The current page renders identity/telemetry, session-relative anomaly evidence, an observed-event timeline, current-session trajectory and speed charts, then the optional Gemini panel. Historical observations are loaded only after an explicit operator action, which is a sound boundary.

The repository also contains:
- `src/historical/profile.py`: deterministic metrics from persisted real AIS observations;
- `src/intelligence/profile.py`: typed profile blocks for identity, telemetry, historical context, movement, anomalies and deterministic confidence;
- `src/ui/gemini_panel.py`: explicit historical-profile loading and optional LLM interpretation.

However, the main Vessel Intelligence renderer still constructs much of its presentation directly from the current vessel snapshot, track and findings. The profile contract is therefore not yet the single canonical presentation model for the investigation page.

**Recommended increment:** integrate the existing deterministic profile contract into the Vessel Intelligence page. Do not create a second profile model. Keep live and historical provenance separate; missing static identity fields must remain unavailable rather than inferred. Keep Gemini strictly as an optional interpretation layer and never let it alter analytical scores.

### 3. Behavioral and temporal intelligence

The repository contains real implementations for PCA/KMeans/Isolation Forest, similarity search, explainable anomaly findings and a TCN Temporal Autoencoder. Temporal diagnostics measure real track coverage and supported window counts.

The key limitation is not the absence of models. It is validation and comparability:
- session-relative anomaly scores are not calibrated probabilities;
- temporal readiness depends on real repeated observations;
- one session's loss or score distribution cannot establish model superiority;
- cross-region generalization and context-aware anomaly fusion remain unproven.

**Recommended increment:** prioritize controlled evaluation and historical baselines before adding model complexity or combining scores.

### 4. Data quality, observability and environmental context

The current implementation exposes validation counters, stale records, freshness, receive-time gaps, invalid records, duplicates, impossible speeds/jumps, queue/drop/reconnect telemetry, temporal readiness and historical persistence state. Marine model context is shown separately from AIS evidence.

**Recommended increment:** improve evidence lineage in the interface: every metric/finding should make its source, region, time scope and live-versus-persisted status clear. Environmental context must remain contextual evidence, not a causal explanation or an automatic anomaly modifier without validation.

### 5. Static identity and external enrichment

The current profile contract can display fields such as IMO and callsign when present in the raw observation, but missing values remain unavailable. The reviewed application code does not establish a complete, independently validated static-vessel-data enrichment workflow.

**Recommended increment:** treat static identity enrichment as a separate provider-backed capability with source, retrieval time, field-level provenance and conflict handling. Do not silently infer or overwrite identity fields. This should follow the Vessel Intelligence profile integration, not precede it.

## Prioritized implementation sequence

### P1 — Canonical Vessel Intelligence Profile
- Use the existing `VesselIntelligenceProfile` contract as the page's presentation model.
- Separate identity, live telemetry, movement, current-session findings and persisted history.
- Show provenance and availability per block.
- Preserve the explicit operator action before loading historical records.
- Keep deterministic confidence semantics transparent; do not present it as ML probability.
- Keep Gemini optional and downstream of the evidence model.

### P2 — Investigation continuity
- Preserve the selected MMSI when moving between map, vessel list, anomaly explorer and trajectory views.
- Provide direct navigation from a finding to the corresponding vessel and observed track context.
- Keep regional selection isolated in SPLIT mode and explicit in UNIFIED mode.
- Do not alter the engine's regional/session data semantics.

### P3 — Historical behavioral baselines
- Extend persisted real-AIS profiles beyond simple descriptive aggregates only after session identity and time coverage are adequate.
- Compare like-for-like vessel, region and time contexts.
- Display baseline sample count and coverage; return NOT_READY when insufficient.
- Validate with held-out sessions before using baseline deviations in anomaly scoring.

### P4 — Event intelligence and contextual evidence
- Evolve the current event timeline/findings into traceable investigation records with observation references, time, region, affected MMSI, contributing signals and review status.
- Keep environmental observations as a separate evidence channel.
- Do not assert causality or threat classification from correlation or anomaly scores.

### P5 — Advanced geospatial intelligence and multimodal expansion
- Add spatial-temporal investigation tools only against concrete operator workflows.
- Consider external geospatial sources, SAR and computer vision as separate evidence providers with independent provenance and synchronization.
- Do not represent these channels as implemented until ingestion, alignment, validation and UI evidence are actually present.

## Non-goals for this increment

- Rebuilding Overview, map, Vessel Intelligence, Behavioral, Temporal, Data Quality or System pages.
- Replacing PCA, KMeans, Isolation Forest or TCN.
- Adding new AIS subscriptions or starting a live collection.
- Changing AIS ingestion, worker lifecycle, session boundaries, persistence, PostgreSQL/PostGIS configuration or credentials.
- Changing `main`, enabling GitHub Actions, or deploying automatically.
- Treating LLM output as a source of truth or an anomaly detector.

## Acceptance criteria for P1

1. Existing tests for profile construction and historical loading pass.
2. Vessel Intelligence renders from one deterministic profile object.
3. Live-session and persisted-history fields remain visibly distinct.
4. Missing identity fields remain unavailable and are never inferred.
5. Confidence shows its rule-based reasons and does not masquerade as a probability.
6. Historical data is fetched only after explicit operator action.
7. Gemini remains optional and cannot change profile fields, confidence or anomaly scores.
8. No changes to ingestion, collection, session, persistence schema or database configuration.
9. Manual Colab validation and visual validation are recorded before considering the increment complete.

## Review limitations

This is a source-level maturity assessment of the named branch and the files inspected. It is not a fresh pytest run, a Streamlit deployment test, a live AIS validation, a database connectivity test or a full visual audit. Existing project-status documents contain earlier validation statements and dates; they should not be interpreted as evidence that the latest UI patch has passed automated or deployment validation.
