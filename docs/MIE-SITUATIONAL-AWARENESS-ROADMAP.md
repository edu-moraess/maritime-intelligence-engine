# MIE Maritime Situational Awareness & Environmental Intelligence

**Status:** Design baseline / implementation plan  
**Date:** 2026-11-13  
**Repository:** `edu-moraess/vyra-maritime-intell`  
**Baseline branch:** `fix/mie-p0-async-collection-safety`  
**Baseline commit:** `71390a5e1553c7e620be8e8994fb9fdad7ccdcd7`  
**Work branch:** `feat/mie-maritime-situational-awareness`

## 1. Purpose

Evolve the MIE operational experience from a vessel-monitoring dashboard into a professional maritime situational-awareness workspace. The map must support vessel identification, movement interpretation, environmental context, and evidence-led investigation.

This work is an incremental evolution. Existing AIS ingestion, collection lifecycle, session state, intelligence, persistence, and vessel selection are compatibility boundaries and must not be rewritten as part of a visual redesign.

## 2. Audited baseline

The following facts were verified on the baseline commit.

### 2.1 Existing vessel-map capabilities

- `src/ui/tactical_map.py` already generates procedural vector hull polygons by coarse AIS ship-type family.
- Vessel symbols can be oriented using heading, falling back to COG when heading is unavailable.
- Movement vectors, observed track trails, selection emphasis, anomaly rings, freshness, density, traffic corridors, and anomaly hotspots already exist.
- `src/ui/_pages_map_render.py` composes these as PyDeck layers and supports vessel selection through Streamlit's native PyDeck chart selection.
- `src/ui/pages_overview.py` exposes map controls and renders the vessel map and selected-vessel intelligence panel.
- Existing tests include `tests/test_tactical_map.py`, `tests/test_map_region_scope.py`, and presentation/profile tests.

**Design implication:** retain and improve the existing map implementation; do not replace the renderer or ship-symbol system before a focused visual and browser-level assessment.

### 2.2 Existing environmental capabilities

- `src/environment/open_meteo_marine.py` integrates the Open-Meteo Marine API.
- Current marine variables include wave height, wave direction, wave period, wind-wave height, swell height/direction, ocean-current velocity/direction, and sea-surface temperature.
- `src/environment/context.py` represents regional environmental evidence and explicit availability/failure states.
- `src/intelligence/environment_vessel.py` associates a vessel position with an environmental observation only when it belongs to exactly one configured monitoring region.
- `src/intelligence/environment_behavior.py` correlates current-session behavior with environmental context and explicitly avoids causal or predictive-risk claims.
- `src/ui/pages_overview.py` displays regional wave context; `src/ui/vessel_popup.py` exposes environmental context in the vessel profile.
- Existing tests cover provider parsing, environmental context, region matching, engine refresh, and vessel/environment association.

### 2.3 Verified limitations and gaps

1. Environmental retrieval currently samples the center of each configured monitoring bounding box. It is not a spatially resolved environmental field over the map or vessel track.
2. The current environmental domain model has no explicit forecast-valid time, forecast issue/run time, lead time, model identifier, grid resolution, or spatial geometry.
3. The current Marine provider requests current marine conditions; it does not implement storm polygons/tracks, precipitation, lightning, meteorological warnings, or a full wind/weather overlay.
4. The map renderer currently composes AIS, trajectory, density, freshness, and anomaly layers; no environmental raster/vector overlay layer was found in the audited map path.
5. Environmental refresh is called from engine collection/finalization paths and uses synchronous provider requests with a per-request timeout. Its impact on collection completion and engine lock duration must be measured before adding more providers or spatial samples.
6. The existing Nautical Chart experiment was withdrawn because the standalone MapLibre/PyDeck path did not provide a reliable browser integration. Do not reintroduce it without browser-level acceptance testing.
7. The current map is for situational visualization, not certified navigation.

## 3. Product experience

### 3.1 Workspace layout

Use a map-centered workspace with three functional zones:

- **Left rail:** vessel search, fleet list, vessel-type filters, status/freshness filters, and layer controls.
- **Center:** geographic map, vessel symbols, tracks, environmental overlays, and time controls.
- **Right inspection panel:** selected-vessel identity, live AIS state, data quality/freshness, track history, environmental exposure context, and evidence-backed findings.

The workspace must remain responsive and must not make collection controls or page navigation inaccessible.

### 3.2 Vessel cartography

Improve the existing vector hulls rather than replacing them by default:

- preserve ship-type family distinctions only where source data supports them;
- distinguish heading from course over ground (COG);
- label vessels progressively according to zoom and selection;
- preserve clear selected-target focus without hiding surrounding traffic;
- make stale/last-known positions visually distinct from live positions;
- expose timestamp and freshness in the tooltip;
- avoid labels and halos that obscure dense traffic.

### 3.3 Environmental map layers

The layer system should support independently toggled overlays:

- significant wave height, with direction and period details;
- wind speed/direction and gusts;
- storm cells and official storm tracks/forecast cones where a suitable authoritative source exists;
- precipitation intensity;
- lightning observations where a reliable provider is available;
- official marine/weather warnings;
- contextual geographic areas such as ports and anchorages, subject to source and licensing review.

Every layer must display source, units, issue/observation time, valid time, update time, spatial resolution where available, and a clear unavailable/stale state.

Do not portray a point observation as a continuous field. Use a spatial grid/raster, contour, vector field, or explicitly marked point sample according to the actual provider data.

### 3.4 Time controls

Environmental and AIS views must be temporally aligned. Distinguish:
- observation time;
- provider/model issue time;
- forecast valid time;
- AIS receive/observation time.

A time slider must not imply historical or forecast coverage that the source does not provide.

## 4. Environmental data architecture

Introduce a provider-neutral environmental contract before adding multiple data sources.

The normalized domain should represent, where supported:

- source/provider and product/model identifier;
- retrieval timestamp;
- observation timestamp or forecast issue time;
- forecast valid time and lead time;
- latitude/longitude or grid/geometry reference;
- variable name, numeric value, unit, and quality/availability metadata;
- spatial and temporal resolution;
- provenance and license/attribution metadata.

Keep marine observations and meteorological products semantically distinct. A missing variable remains unavailable; never fill it with zero, interpolation, or synthetic values without an explicit, documented method.

### Provider selection gate

Evaluate candidate sources against:
1. global/regional coverage for MIE monitoring regions;
2. current observations and forecast horizon;
3. spatial/temporal resolution;
4. availability of wave, wind, storm, precipitation, lightning, and warning products;
5. rate limits, authentication, latency, and service reliability;
6. licensing, attribution, and redistribution terms;
7. historical access and reproducibility.

Open-Meteo Marine remains the current marine provider baseline. Additional weather/storm providers are not selected in this design document; source selection requires a separate evidence-based review.

### Runtime and resilience

- Environmental acquisition must not block AIS ingestion or Streamlit rendering.
- Use bounded, explicit timeouts and cache keys that include provider, region/grid, product, and valid time.
- Preserve last-good values only with an explicit stale/degraded state and age.
- Bound concurrency, request volume, memory, and cache retention.
- Provider failure must not change AIS collection state.
- Do not hold broad engine locks while waiting on external network calls; confirm this with tests and concurrency review before refactoring.
- Make environmental refresh independently observable in diagnostics.

## 5. Vessel–environment correlation

The correlation layer should initially provide deterministic, descriptive context:

- sample environmental conditions at the vessel position and relevant time;
- optionally sample along a track at bounded spatial/temporal intervals;
- calculate proximity to storm polygons or warning geometries only when the source geometry and time validity are known;
- expose environmental age, spatial distance, source, valid time, and data quality;
- compare observed vessel behavior and environmental conditions on a shared timeline.

It must not claim that weather caused a speed/course change, infer intent, or issue a safety/risk classification without a separately validated model and explicit evidence. Correlation is not causation.

## 6. Implementation phases and gates

### Phase 0 — Baseline preservation and visual audit
- Capture current Overview/map/profile states at desktop and mobile widths.
- Inventory all existing PyDeck layers, Streamlit selection state, controls, and profile sections.
- Record visual issues and functional dependencies.
- Establish baseline manual validation steps and test commands.

**Gate:** no source changes until the current UI and map-selection behavior are documented.

### Phase 1 — Visual system and map UX
- Define layout, spacing, typography, color semantics, legend, tooltips, and responsive behavior.
- Improve vessel labels, symbol scaling, selection focus, and stale-state presentation.
- Consolidate map controls into discoverable layer groups.
- Preserve existing map selection and operational controls.

**Gate:** browser-level acceptance confirms selection, navigation, and collection remain functional.

### Phase 2 — Environmental data contract and provider assessment
- Define provider-neutral models and validation.
- Assess sources for storm, wind, precipitation, lightning, warnings, and forecast wave fields.
- Add explicit provenance, time validity, units, and stale-state semantics.
- Measure current synchronous refresh latency and lock contention.

**Gate:** source, licensing, data semantics, and operational impact are documented before integration.

### Phase 3 — Environmental map layers
- Add one layer at a time, beginning with spatially resolved wave height.
- Follow with wind vectors/fields, precipitation, and storm/warning geometry as supported by verified sources.
- Add legends, units, attribution, valid-time controls, and unavailable states.
- Test map rendering with real provider payloads and deterministic fixtures.

**Gate:** no layer may render invented or semantically misleading data.

### Phase 4 — Vessel–environment correlation
- Align AIS and environmental timestamps.
- Add bounded spatial/temporal sampling and track context.
- Show evidence and provenance for every association.
- Validate edge cases: stale data, out-of-region vessels, overlapping regions, missing timestamps, and provider outages.

**Gate:** outputs remain descriptive and explainable; no unsupported causal or risk claims.

### Phase 5 — Regression, performance, and documentation
- Run the full existing test suite and new targeted tests.
- Validate live/finite AIS collection, navigation, vessel selection, profiles, and provider-failure behavior.
- Measure render latency, network latency, memory/cache bounds, and request counts.
- Update architecture, data contracts, provider notes, operational runbook, and validation evidence.

**Gate:** report all results and warnings; no merge to `main` or Streamlit deployment without explicit user authorization.

## 7. Acceptance criteria

- Existing AIS collection and stop/reconnect behavior remain unchanged.
- Vessel selection still works on the supported map renderer.
- Existing ship symbols, trails, filters, and profile functions do not regress.
- Environmental overlays can be toggled independently and have accurate legends.
- Every environmental value has source, unit, and time-validity metadata.
- Missing/stale/provider-failed data is explicit and never rendered as a real zero or current condition.
- Environmental requests cannot block AIS ingestion or UI navigation.
- Vessel–environment associations expose time alignment and provenance.
- Full manual and automated regression evidence is recorded.
- Work remains isolated from `main`; deployment and merge require explicit authorization.

## 8. Non-goals and safety boundaries

- No replacement of AIS ingestion or the current session engine as part of the visual work.
- No synthetic vessels, fabricated storm cells, or invented environmental measurements in production paths.
- No claim that an anomaly proves illicit activity or that environmental correlation proves causality.
- No certified navigation, collision avoidance, or autonomous safety decisions.
- No new provider/API key committed to the repository.
- No GitHub Actions workflow changes; validation remains manual/Colab-first.
- No merge to `main` and no Streamlit deployment without explicit authorization.

## 9. Baseline references

- `src/ui/tactical_map.py`
- `src/ui/_pages_map_render.py`
- `src/ui/_pages_map_impl.py`
- `src/ui/pages_overview.py`
- `src/ui/vessel_popup.py`
- `src/environment/context.py`
- `src/environment/open_meteo_marine.py`
- `src/ingestion/models.py`
- `src/intelligence/environment_vessel.py`
- `src/intelligence/environment_behavior.py`
- `src/intelligence/engine.py`
- `tests/test_tactical_map.py`
- `tests/test_open_meteo_marine.py`
- `tests/test_environment_vessel.py`
- `tests/test_environmental_context.py`
- `tests/test_engine_environmental_context.py`
