# MIE Project Status

## Status date

2026-09-03

This document records the current engineering and validation position of the Maritime Intelligence Engine (MIE). It is intended to keep the repository aligned with what has actually been implemented and observed in live AIS sessions.

## Current system

MIE is an end-to-end maritime intelligence platform built around real AIS telemetry:

`AISStream → validation → session tracks → feature engineering → PCA/KMeans/Isolation Forest → temporal intelligence → vessel intelligence → operational UI → PostgreSQL/PostGIS`

The project does **not** use synthetic vessels, mock traffic, or fabricated fallback observations.

## Current engineering milestone — dual-region monitoring

The operational workspace now supports two maritime monitoring regions simultaneously through one dual-region overview.

Implemented on the development branch:

- two configured Bounding Boxes can be monitored together;
- regional map state is isolated between Region A and Region B;
- SPLIT mode renders two independent tactical views;
- UNIFIED mode renders one enclosing tactical viewport across both regions;
- UNIFIED mode does not calculate an artificial geographic midpoint;
- vessel selection is independent in SPLIT mode;
- UNIFIED vessel selection persists across Streamlit reruns through dedicated session state;
- selected vessels open the corresponding Vessel Intelligence context;
- regional analytical state remains separated even when the tactical map is unified;
- map widget keys are unique across regional and unified views.

The current development commit for the unified-selection correction is:

`ec17115d82d8a1e12493e740126854491876834d`

This milestone addresses the operational presentation and selection flow. It does not claim that the underlying AIS coverage or temporal model is uniformly sufficient across regions.

## Production-validated capabilities

- Real AISStream WebSocket ingestion
- Server-side geographic Bounding Box subscriptions
- Explicit LIVE AIS / disconnected operational states
- Real AIS validation and temporal integrity controls
- Session-based vessel tracking
- Vessel selection and investigation
- Behavioral feature engineering
- PCA, KMeans, and Isolation Forest analysis
- Explainable behavioral signals
- Tactical geospatial visualization
- 30 maritime monitoring region presets
- Two-region operational monitoring
- SPLIT / UNIFIED tactical map views
- Independent regional vessel selection
- Vessel Intelligence from selected vessels
- PostgreSQL/PostGIS historical persistence
- Idempotent historical observation persistence
- Temporal track diagnostics
- GRU temporal autoencoder trained only on real AIS observations

## Live multi-region observation

A recent live validation session used two geographically distinct regions:

- **Region A — Malacca Strait:** `(1.000, 99.500) → (6.000, 104.000)`
- **Region B — Strait of Gibraltar:** `(35.700, -5.800) → (36.300, -4.900)`

Observed during the session:

- ~636 seconds of collection elapsed;
- 272 real AIS position reports received;
- 143 vessels represented in the session;
- regional observations were visible in both monitored areas;
- the Gibraltar region exposed its own regional tactical state;
- the application maintained the two regions without requiring a synthetic geographic center.

The observed density also reinforced the temporal coverage limitation: active-vessel count does not imply sufficient repeated observations per vessel for deep temporal inference.

## Temporal intelligence — current evidence

The temporal diagnostics layer was added before changing the temporal model so that sequence availability could be measured instead of assumed.

### Houston Ship Channel

Observed live session:

- ~974 seconds elapsed
- 549 real AIS position reports persisted
- 181 active vessels
- 69 tracks with ≥4 points
- 11 tracks with ≥8 points
- 0 tracks with ≥16 points
- 0 tracks with ≥32 points
- 17 sliding T=8 windows
- 11 non-overlapping T=8 windows
- 0 T=16 windows
- 0 T=32 windows
- median track points: 3
- median track duration: 7.0 minutes
- maximum observed receive-time gap: 24.7 minutes

The temporal diagnostics demonstrate that long fixed windows are not uniformly supported by regional AIS coverage.

### Danish Straits

Two 900-second-class sessions previously observed approximately:

- 2.1k real AIS position reports per session
- ~617–633 active vessels
- 263 tracks with ≥4 points
- TCN training available with T=32

The comparison establishes that temporal coverage varies materially by region and collection session.

## Adaptive temporal model

The current temporal production path uses a GRU Temporal Autoencoder with conservative data-driven sequence selection.

The adapter chooses the longest supported scale:

`T=32 → T=16 → T=8 → NOT_READY`

A scale is supported only when enough tracks contain that many **real validated observations**. Short tracks are never stretched or fabricated to satisfy a longer sequence.

The current default minimum is the existing deep-model requirement of 8 usable tracks.

Temporal model readiness remains a data-coverage condition, not a promise that every live region can support deep temporal inference.

## Important analytical semantics

- `deep_anomaly_score` is a session-relative ranking, not a probability.
- An anomaly is an analytical signal, not proof of malicious intent or a threat.
- Insufficient observations mean insufficient evidence, not normal behavior.
- A large training loss difference between sessions must not be interpreted as model accuracy without a controlled validation protocol.
- Regional temporal coverage must be measured before comparing model behavior across regions.
- A unified map is a visualization mode; it does not merge regional analytical evidence into a single undifferentiated region.

## Current research direction

The immediate objective is **not** to make the temporal model more complex. The objective is to establish a reliable multi-channel intelligence foundation:

1. maintain trustworthy multi-region AIS monitoring;
2. measure real track coverage;
3. select an appropriate temporal scale;
4. preserve evidence provenance;
5. validate temporal scores quantitatively;
6. build historical behavioral baselines;
7. add environmental context such as weather and ocean conditions;
8. combine behavioral, temporal, trajectory, and environmental evidence;
9. use LLMs as an interpretation layer rather than as the raw anomaly detector.

## What is not yet validated

The following should not yet be claimed as production-proven:

- universal maritime anomaly classification;
- calibrated anomaly probabilities;
- malicious-intent detection;
- quantitative superiority of GRU over Isolation Forest;
- cross-region generalization of temporal scores;
- causal explanations for anomalies;
- continuous-learning performance;
- weather/ocean contextual anomaly reduction;
- cross-channel anomaly fusion.

## Next validation gate

The next engineering step is to preserve the current stable multi-region AIS workflow while introducing environmental channels independently. Weather should be implemented as a provider-based channel rather than coupled directly to the AIS ingestion path.

The first environmental milestone should validate provider normalization and per-region context before allowing weather or ocean observations to influence anomaly scoring.

## Engineering principle

> Build the evidence boundary before increasing model complexity.

MIE should prefer an explicit `NOT_READY` or shorter supported temporal scale over fabricated or unsupported temporal evidence.
