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
| `average_speed_knots` | Mean SOG | Arithmetic mean over `speed_sample_count`; unavailable samples are not imputed |
| `anomalies` | Finding events | Count of current-session anomaly findings |
| `anomaly_vessels` | Distinct MMSIs with findings | Unique MMSIs across current-session findings |
| `regions` | Configured monitoring regions | Number of active Bounding Boxes; never inferred from coordinate clusters |

## Other operational fields

- `IngestionStatus.active_vessels` uses the same fresh-vessel definition.
- `IngestionStatus.messages_received` is the provider's cumulative accepted report counter since its last explicit provider reset; it is not the same field as the current-session `summary.messages`.
- Data Quality uses only the current-session observations. Historical hydration is not silently mixed into the session quality denominator.
- The overview map includes last-known stale positions by default. Stale positions are not LIVE targets and show their actual last-report age.
- Traffic throughput charts use current-session observations. SOG distribution uses fresh vessel snapshots only.
- Regional temporal scores are session-relative. If the temporal model is not READY, eligible-track and top-quartile metrics are `N/A`, not zero. If the model is READY but there are too few scores to estimate a quartile threshold, the top-quartile rate remains `N/A`.

## Guardrails

1. Never call coordinate clusters or map cells “regions”.
2. Never count stale last-known positions as active vessels.
3. Never average stale SOG values into a live speed metric.
4. Never substitute zero for an unavailable temporal metric.
5. Keep current-session and restored historical populations visibly distinct.
6. Every metric change must update its tests and this contract.
