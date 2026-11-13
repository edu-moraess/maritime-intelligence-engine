# MIE Observation Integrity Contract

**Status:** Implemented on `fix/mie-observation-integrity`; runtime validation pending  
**Date:** 2026-11-13  
**Scope:** AIS ingestion consumers, trajectory features, temporal ML, anomaly presentation, and data-quality UI

## 1. Governing rule

The MIE must never convert missing, invalid, or unobserved information into a value that can be mistaken for a real AIS observation.

- Observed values remain tied to their source report and timestamp.
- Derived values must be calculated only from valid source observations and presented as derived.
- Missing or invalid values remain unavailable.
- Synthetic fixtures are permitted in isolated tests, never in operational data paths.
- Historical real observations remain preserved; an older real observation is not synthetic, but must retain its original time and freshness state.

## 2. AIS field semantics

### Heading and COG

- **Heading** describes vessel bow orientation.
- **COG** describes direction of travel over ground.
- COG must not replace missing Heading.
- The tactical hull orientation is rendered only when a valid Heading exists.
- Movement vectors may use valid COG and SOG as a derived display of direction and speed.

### Missing and invalid fields

- Missing SOG/COG are not filled with zero.
- Invalid coordinates, SOG, and COG are excluded from trajectory feature construction.
- A field with no valid source value remains unavailable.
- A missing vessel name or ship type may be displayed as an explicit unknown/unspecified label, not as a guessed identity or classification.

## 3. Derived trajectory values

- The first report in a track has no preceding interval. Its time delta, distance, computed speed, course change, and dwell state are unavailable, not zero.
- Distances are calculated only between valid geographic coordinates.
- Computed speed is available only when the corresponding time interval is positive and the position pair is valid.
- Dwell ratios exclude intervals whose derived speed is unavailable.
- Summary statistics with no valid samples return unavailable values, not zero.

## 4. Embeddings and temporal model inputs

### Runtime trajectory embeddings

- An embedding uses an exact window of 32 complete, real AIS reports by default.
- The required fields are latitude, longitude, SOG, and COG.
- Missing, invalid, or insufficient source data causes the track to be excluded from embedding.
- No temporal interpolation, missing-value fill, or synthetic padding is allowed.

### Temporal sequence model

A sequence of **T transitions requires T+1 real position reports**:

- Each output row represents the transition from one observed report to the next.
- The origin report supplies the previous position; the destination report supplies the observed SOG/COG fields for that transition.
- Missing SOG/COG, invalid coordinates, non-positive intervals, or intervals crossing the configured continuity gap reject the sequence.
- Windows may share one endpoint report, but they do not duplicate transitions.
- Insufficient real data results in NOT_READY; the model must not fabricate rows to become ready.

## 5. Anomaly score semantics

- Rule scores are bounded, rule-derived exceedance indices based on observed values and configured thresholds.
- Dwell score is the observed ratio of valid movement intervals classified below the dwell-speed threshold.
- Session-relative Isolation Forest scores remain ranking signals only.
- None of these scores is a calibrated probability or confidence.
- Rule findings therefore leave the confidence field unavailable.
- A score threshold alone does not promote a vessel to CRITICAL. That status requires an explicit critical category.

## 6. Data quality and empty states

- An empty AIS session has unavailable quality (N/A), not 100%.
- Missing average speed is shown as N/A, not zero.
- No findings means no score is displayed; it does not mean normality is 100%.
- Historical real observations and last-good environmental observations are preserved with their original provenance and time. A stale observation must not be described as current.

## 7. Presentation-only geometry

Procedural ship hulls, map-cell centers, density cells, and hotspot markers are visualization or aggregation geometry. They are not AIS reports, measured vessel dimensions, exact event coordinates, or environmental observations. They must not be used as input evidence.

A generic hull may remain as an illustrative map symbol when a valid Heading exists. The UI must not imply that the polygon is the vessel's measured physical outline.

## 8. Explicitly out of scope

This change does not remove operational configuration defaults such as the configured monitoring bounding box, network retry jitter, or test-only synthetic fixtures. These are not synthetic AIS/environmental observations. Any future change to configuration policy must be reviewed separately.

## 9. Validation gate

Before merge or deployment, run the focused observation-integrity tests and the full test suite in Colab, followed by compileall and diff checks. No GitHub Actions workflow is used for this validation. No merge to `main`, safety-branch modification, training, or deployment is authorized by this document.
