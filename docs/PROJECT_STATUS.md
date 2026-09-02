# MIE Project Status

## Status date

2026-09-01

This document records the current engineering and validation position of the Maritime Intelligence Engine (MIE). It is intended to keep the repository aligned with what has actually been implemented and observed in live AIS sessions.

## Current system

MIE is an end-to-end maritime intelligence platform built around real AIS telemetry:

`AISStream → validation → session tracks → feature engineering → PCA/KMeans/Isolation Forest → temporal intelligence → vessel intelligence → operational UI → PostgreSQL/PostGIS`

The project does **not** use synthetic vessels, mock traffic, or fabricated fallback observations.

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
- PostgreSQL/PostGIS historical persistence
- Idempotent historical observation persistence
- Temporal track diagnostics
- TCN temporal autoencoder trained only on real AIS observations

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

The temporal model reached READY in this session, but the diagnostics demonstrate that long fixed windows are not uniformly supported by regional AIS coverage.

### Danish Straits

Two 900-second-class sessions previously observed approximately:

- 2.1k real AIS position reports per session
- ~617–633 active vessels
- 263 tracks with ≥4 points
- TCN training available with T=32

The comparison establishes that temporal coverage varies materially by region and collection session.

## Adaptive temporal model

PR #34 introduces conservative data-driven temporal scale selection.

The default adapter chooses the longest supported scale:

`T=32 → T=16 → T=8 → NOT_READY`

A scale is supported only when enough tracks contain that many **real validated observations**. Short tracks are never stretched or fabricated to satisfy a longer sequence.

The current default minimum is the existing deep-model requirement of 8 usable tracks.

Therefore, the Houston evidence above should select T=8, while a denser region can continue using T=16 or T=32 when its real AIS coverage supports them.

The model architecture, features, training budget, ingestion, persistence, and anomaly-score semantics are intentionally unchanged by this PR.

## Important analytical semantics

- `deep_anomaly_score` is a session-relative ranking, not a probability.
- An anomaly is an analytical signal, not proof of malicious intent or a threat.
- Insufficient observations mean insufficient evidence, not normal behavior.
- A large training loss difference between sessions must not be interpreted as model accuracy without a controlled validation protocol.
- Regional temporal coverage must be measured before comparing model behavior across regions.

## Current research direction

The immediate objective is **not** to make the TCN more complex. The objective is to establish a reliable temporal foundation:

1. measure real track coverage;
2. select an appropriate temporal scale;
3. preserve evidence provenance;
4. validate temporal scores quantitatively;
5. build historical behavioral baselines;
6. add environmental context such as weather and ocean conditions;
7. combine behavioral, temporal, trajectory, and environmental evidence;
8. use LLMs as an interpretation layer rather than as the raw anomaly detector.

## What is not yet validated

The following should not yet be claimed as production-proven:

- universal maritime anomaly classification;
- calibrated anomaly probabilities;
- malicious-intent detection;
- quantitative superiority of TCN over Isolation Forest;
- cross-region generalization of temporal scores;
- causal explanations for anomalies;
- continuous-learning performance;
- weather/ocean contextual anomaly reduction.

## Next validation gate

After PR #34 is merged, the next deployment smoke test should confirm the selected temporal scale in the live System diagnostics. The Houston session should select T=8 from the observed 11 tracks with ≥8 points.

After that, the project should move toward controlled temporal validation and historical baselines rather than repeatedly tuning the model from isolated session losses.

## Engineering principle

> Build the evidence boundary before increasing model complexity.

MIE should prefer an explicit `NOT_READY` or shorter supported temporal scale over fabricated or unsupported temporal evidence.
