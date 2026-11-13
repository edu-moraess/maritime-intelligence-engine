# MIE Canonical Metric Contract

- Version: 1
- Date: 2026-11-13
- Scope: operational summary, traffic analytics, data quality, and regional comparison.

All operational summary metrics below are scoped to `current_session_observations` and the corresponding latest vessel snapshots. Restored historical observations are excluded unless a metric explicitly states otherwise.

| Metric | Definition | Population / rule |
|---|---|---|
| `messages` | Accepted AIS PositionReport observations | Count of observations in the current finite or continuous session |
| `unique_vessels` | Distinct MMSIs observed | Distinct MMSIs in current-session observations |
| `active_vessels` | Fresh observed vessels | Latest report age is at or below `stale_after_seconds` |
| `observed_vessels` | Vessels represented in the current session | Fresh plus stale last-known vessel snapshots |
| `stale_vessels` | Vessels with an old last-known report | Latest report age exceeds `stale_after_seconds` |
| `speed_sample_count` | Fresh vessels with SOG | Stale vessel speeds are excluded |
| `average_speed_knots` | Mean SOG | Arithmetic mean over `speed_sample_count`; `N/A` when the sample count is zero; unavailable samples are never replaced with zero |
| `anomalies` | Finding events | Count of current-session anomaly findings |
| `anomaly_vessels` | Distinct MMSIs with findings | Unique MMSIs across current-session findings |
| `regions` | Configured monitoring regions | Number of active Bounding Boxes; never inferred from coordinate clusters |

## Other operational fields

- `IngestionStatus.active_vessels` uses the same fresh-vessel definition.
- `IngestionStatus.messages_received` is the provider's cumulative accepted report counter since its last explicit provider reset; it is not the same field as the current-session `summary.messages`.
- Data Quality uses only the current-session observations. Historical hydration is not silently mixed into the session quality denominator.
- The overview map includes last-known stale positions by default. Stale positions are not LIVE targets and show their actual last-report age.
- Traffic throughput charts, tactical trails, and map density layers use current-session observations. SOG distribution uses fresh vessel snapshots only.
- Tactical map `targets` counts the visible current-session vessel snapshots. Tactical `tracks` counts only MMSIs represented among those visible targets with at least two current-session reports; tracks outside the map's selected region are excluded.
- Regional temporal scores are session-relative. If the temporal model is not READY, eligible-track and top-quartile metrics are `N/A`, not zero. If the model is READY but there are too few scores to estimate a quartile threshold, the top-quartile rate remains `N/A`.

## Guardrails

1. Never call coordinate clusters or map cells “regions”.
2. Never count stale last-known positions as active vessels.
3. Never average stale SOG values into a live speed metric.
4. Never substitute zero for an unavailable temporal metric.
5. Keep current-session and restored historical populations visibly distinct.
6. Every metric change must update its tests and this contract.


## Regional comparison reconciliation

- Regional `unique_vessels` means distinct MMSIs observed in that region during the current session; it is not the same as the overview's `active_vessels`, which includes only fresh vessel snapshots.
- Regional `anomalies` counts finding events. Tactical-map `ANOMALOUS VESSELS` counts distinct MMSIs represented by those findings in the map's region.
- Regional `position_reports` sum to the session message count only when every observation belongs to exactly one configured region. Observations inside both regions are counted as ambiguous and excluded from both; observations outside both regions are counted as unassigned and excluded.
- The overview labels these populations explicitly. Do not compare active vessels with observed vessels, or anomaly events with anomalous-vessel counts, as if they were the same metric.
