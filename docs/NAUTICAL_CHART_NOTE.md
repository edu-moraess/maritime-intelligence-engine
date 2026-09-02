# Nautical chart rendering note

The tactical map uses the Open Waters Seamap MapLibre style when `Nautical Chart` is selected.

PyDeck must explicitly use `map_provider="maplibre"` for this style; otherwise the style URL is interpreted through the default Carto provider path and the nautical style is not rendered correctly.

The chart is for visualization only, not navigation. Attribution is shown in the overview UI.
