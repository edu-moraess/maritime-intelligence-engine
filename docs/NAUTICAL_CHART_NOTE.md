# Nautical chart rendering note

The tactical map uses the real Open Waters Seamap style when `Nautical Chart` is selected:

`https://tiles.openwaters.io/seamap/style.json`

PyDeck must explicitly receive `map_provider="maplibre"` and `map_projection="mercator"` for this style. The native Streamlit `st.pydeck_chart` bundle does not currently include the MapLibre runtime, so the Nautical Chart path renders the standalone PyDeck HTML. That document loads `maplibre-gl` and preserves the Open Waters style URL as the basemap source.

Dark Matter, Positron, and Voyager continue to use the native `st.pydeck_chart` path with the Carto provider. No PyDeck layers are used to simulate a nautical chart, and no paid API key is required.

The standalone component is visualization-only from Streamlit's perspective: its map click events are not returned through `on_select`. Consequently, the existing vessel-selection callback remains available for the native Carto path, while Nautical Chart map clicks do not update `selected_mmsi`. The AIS data, selection state model, and intelligence pipeline are otherwise unchanged.

The chart is for visualization only, not navigation. Attribution is shown in the overview UI.
