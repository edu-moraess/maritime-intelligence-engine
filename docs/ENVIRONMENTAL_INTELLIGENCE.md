# Environmental Intelligence Contract

The MIE treats external environmental feeds as **model state**, not physical sensor observations.

## Current sources

### Open-Meteo Marine

Provides marine model variables including wave height, wave period/direction, wind-wave and swell components, ocean current velocity/direction, and sea-surface temperature.

### Open-Meteo Weather

Provides atmospheric model state including 10 m wind speed/direction, 10 m gusts, precipitation, visibility, and mean-sea-level pressure.

The application keeps marine and atmospheric sources separate and preserves source/timestamp provenance.

## Evidence semantics

1. **AIS observation** — real vessel observation received from AISStream.
2. **Environmental model state** — external numerical model output valid at a location/time.
3. **Derived intelligence** — correlations, behavior classifications, anomaly scores, or risk signals computed by MIE.

The environmental layer must not claim that weather or ocean conditions caused a vessel maneuver. Such a relationship requires explicit spatial/temporal alignment and a derived analytical method.

## Copernicus Marine

An optional Copernicus Marine adapter is now wired behind an explicit opt-in flag. The current adapter reads the global hourly surface-current dataset `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i` and derives current speed/bearing from the eastward (`uo`) and northward (`vo`) velocity components. The official product is global at 0.083° horizontal resolution and exposes hourly surface-current fields.

The Copernicus Marine Toolbox is the official programmatic interface and supports Python API access to metadata, subsets and remote datasets.

Enable only when Copernicus credentials are configured:

`MIE_COPERNICUS_MARINE_ENABLED=true`

Credentials may be provided through the Toolbox configuration or `COPERNICUSMARINE_SERVICE_USERNAME` / `COPERNICUSMARINE_SERVICE_PASSWORD`.

Missing package, disabled flag, unavailable credentials, or remote failure must never fabricate or substitute environmental values. The MIE simply omits that source from the current environmental context.

The next candidate product is the global wave analysis/forecast dataset, to be integrated only after validating its variables and temporal semantics.

## Spatial-temporal alignment

Future vessel-level environmental context should be computed as:

AIS position/time -> environmental field lookup -> aligned state -> derived feature

The aligned state should retain source, model/product, valid timestamp, retrieval timestamp, coordinates, units, forecast/analysis classification, and age at alignment.

No causal inference should be emitted merely because AIS and environmental values coexist.

## Roadmap

1. Open-Meteo Marine — implemented.
2. Open-Meteo Weather — implemented.
3. Multi-source environmental state — implemented.
4. Copernicus Marine adapter — planned.
5. Spatial interpolation / nearest-grid selection — planned.
6. AIS × environment temporal alignment — planned.
7. Derived environmental-behavior features — planned and must remain explicitly derived.
