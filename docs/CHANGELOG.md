# MIE Engineering Changelog

This log records meaningful engineering milestones and validated behavior changes in the Maritime Intelligence Engine. It is intentionally concise and should describe implemented behavior rather than planned work.

## 2026-09-03 — Tactical operational language refinement

### Updated

- Standardized the dual-region overview around an **Operational Picture** vocabulary.
- Renamed unified-map messaging from generic presentation language to **CONSOLIDATED OPERATIONAL PICTURE**.
- Standardized selected-vessel panels as **tactical contact panels**.
- Reframed regional terminology as monitored operational areas while retaining exact geographic region names and Bounding Box coordinates.
- Standardized system telemetry labels as **SIGNAL FRESHNESS**, **TEMPORAL READINESS**, **WEBSOCKET RECOVERY**, and **CONNECTION STATE**.
- Preserved existing internal workspace routing identifiers so UI terminology changes do not alter application control flow.
- Clarified the nautical-chart disclaimer as visualization-only and explicitly not for navigation.

### Consistency corrections

- Removed the implication that UNIFIED creates a geographic midpoint; it remains an enclosing operational viewport.
- Kept regional analytical state isolated in both SPLIT and UNIFIED modes.
- Kept **REAL AIS** provenance explicit in the operational overview.
- Retained the distinction between a vessel as a domain entity and a tactical **contact** as its operational presentation.

## 2026-09-03 — Dual-region operational monitoring

### Added

- Two-region monitoring in the operational overview.
- SPLIT tactical mode with independent Region A and Region B map views.
- UNIFIED tactical mode using one enclosing geographic viewport.
- Region-aware vessel selection in SPLIT mode.
- Persistent vessel selection in UNIFIED mode across Streamlit reruns.
- Vessel Intelligence context for selected vessels in regional and unified views.

### Fixed

- Duplicate Streamlit PyDeck widget identity caused by reusing the same map key across regional maps.
- Vessel-selection state leaking between Region A and Region B.
- UNIFIED selection being lost during `st.rerun()`, preventing the selected vessel's intelligence panel from loading.

### Design decisions

- UNIFIED is a visualization mode and does not create an artificial geographic midpoint.
- Regional analytical state remains separated even when the map is unified.
- Each tactical map receives a unique widget key.
- Real AIS observations remain the only source of vessel telemetry.

### Validation evidence

A live multi-region session used:

- Region A — Malacca Strait: `(1.000, 99.500) → (6.000, 104.000)`
- Region B — Strait of Gibraltar: `(35.700, -5.800) → (36.300, -4.900)`
- ~636 seconds elapsed
- 272 real AIS position reports
- 143 vessels represented in the session

### Relevant commits

- `536e5a385061baf77ad9ed00e555c849a522b069` — isolated regional selection state
- `24c8ba2de3030f17c7f1670c3490313cff2f6362` — added SPLIT / UNIFIED map views
- `ee1cff42c497643d661768f74d47393dccfde5aa` — tightened split map spacing
- `ec17115d82d8a1e12493e740126854491876834d` — persisted UNIFIED vessel selection
- `751e00aade13a9b47fc8115c9b35cc8ce3f9dcfb` — refined tactical operational language
- `d8b3e7e2079b0158567b96f4ea18cc9e7267ce77` — standardized system/workspace terminology

## Documentation policy

For each significant MIE feature or correction:

1. update `README.md` when the public capability or architecture changes;
2. update `docs/PROJECT_STATUS.md` with the current engineering/validation position;
3. add a concise entry here when the change is a meaningful milestone;
4. keep claims tied to implemented or observed evidence;
5. explicitly distinguish live validation, local validation, and unvalidated research.
