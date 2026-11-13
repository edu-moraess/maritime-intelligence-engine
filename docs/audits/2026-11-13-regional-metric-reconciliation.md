# MIE — Regional Metric Reconciliation Audit

- Date: 2026-11-13
- Scope: read-only review of the operator-provided LIVE AIS dashboard snapshot and the P0 work branch.
- Branch: `feat/mie-p0-operational-reliability`
- Baseline: `5bbe456f657bd4524e71937cf73da420db4f0898`
- Status: metric semantics clarified; runtime reconciliation still requires a fresh Colab validation.

## Observed dashboard evidence

The supplied dashboard snapshot displayed:

| Surface | Metric | Value |
|---|---|---:|
| Overview | Vessels | 128 |
| Overview | Messages | 827 |
| Overview | Anomalies | 18 |
| Region A (Miami) | Vessels | 43 |
| Region A (Miami) | Reports | 117 |
| Region A (Miami) | Anomalies | 4 |
| Region A map | Targets | 43 |
| Region A map | Tracks | 25 |
| Region A map | Anomalies | 3 |
| Region B (Malacca) | Vessels | 341 |
| Region B (Malacca) | Reports | 707 |
| Region B (Malacca) | Anomalies | 14 |
| Region B map | Targets | 341 |
| Region B map | Tracks | 170 |
| Region B map | Anomalies | 12 |

The regional report counts sum to 824, three fewer than the overview's 827 session messages. The screenshot alone does not establish whether those three observations were outside both configured boxes, inside both boxes, or a combination.

## Code-level findings

1. The overview's `active_vessels` is calculated from fresh `VesselSnapshot` values only.
2. Regional `unique_vessels` counts distinct MMSIs represented in all current-session observations for each region. It can include vessels whose latest report is stale.
3. Map `TARGETS` counts visible map rows; stale rows are included when the default "Include stale session targets" control is enabled.
4. The overview's `anomalies` counts finding events.
5. Tactical-map anomaly totals count distinct MMSIs with findings represented on that map, not finding events.

Therefore, the displayed values are not directly additive/comparable. The original labels obscured these population and unit differences.

## Changes made on the work branch

- Overview summary labels now say `Active vessels` and `Anomaly events`.
- Regional comparison labels now say `Observed vessels` and `Anomaly events`.
- Tactical map strips now say `ANOMALOUS VESSELS`.
- `RegionComparison` now exposes `unassigned_observations` separately from `ambiguous_observations`.
- Regional UI now reports observations outside both regions and observations inside both regions, rather than silently hiding the outside-region count.
- Added a deterministic unit test for observations outside both configured regions.
- Updated the canonical metric contract.

## Validation still required

The code changes have been committed but have **not** been executed in Colab yet. Pull the latest branch and run the existing P0 validator, which includes `tests/test_region_comparison.py` and the full repository suite.

On the next live session, verify the reconciliation identity:

`session messages = Region A reports + Region B reports + ambiguous observations + unassigned observations`

This identity should hold for the same immutable snapshot. If it does not, investigate observation validity, session mutation, and region membership before accepting the metric contract.

## Operational status

This audit does not approve P0 operational acceptance. The supplied run was stopped before the planned 30-minute observation window was established as complete. Worker lifecycle diagnostics, controlled interruption/recovery, and UI responsiveness remain separate acceptance items.
