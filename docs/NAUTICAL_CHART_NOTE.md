# Nautical chart — implementation deferred

The Open Waters Seamap / Nautical Chart option has been removed from the active
MIE basemap selector and renderer.

The previous implementation was isolated behind a MapLibre-specific PyDeck
runtime patch and a standalone HTML rendering path. That path did not produce
a reliable nautical basemap in the application, so it has been withdrawn rather
than leaving a nonfunctional option exposed.

The existing Carto basemaps (Dark Matter, Positron, and Voyager) remain on the
native Streamlit PyDeck renderer. No AIS ingestion, region configuration,
vessel data, map overlays, or intelligence logic is changed by this removal.

Future reintroduction must be treated as a separate implementation, with a
validated renderer integration and an explicit browser-level acceptance test
before the option is exposed again. The chart is intended for visualization
only, not navigation.
