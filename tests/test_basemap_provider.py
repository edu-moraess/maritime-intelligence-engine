from pathlib import Path


RENDER_SOURCE = Path("src/ui/_pages_map_render.py").read_text(encoding="utf-8")
STYLE_SOURCE = Path("src/ui/_pages_map_impl.py").read_text(encoding="utf-8")


def test_nautical_chart_uses_maplibre_and_standalone_renderer():
    assert 'map_provider = "maplibre"' in RENDER_SOURCE
    assert 'map_projection = "mercator"' in RENDER_SOURCE
    assert 'components.html(deck.to_html(as_string=True)' in RENDER_SOURCE
    assert 'if map_provider == "maplibre"' in RENDER_SOURCE
    assert 'show_error=(map_provider == "maplibre")' in RENDER_SOURCE


def test_non_nautical_styles_keep_native_streamlit_pydeck_renderer():
    assert 'map_provider = "carto"' in RENDER_SOURCE
    assert 'event = st.pydeck_chart(deck' in RENDER_SOURCE
    assert 'map_projection = None' in RENDER_SOURCE


def test_openwaters_style_is_the_real_style_url():
    assert "https://tiles.openwaters.io/seamap/style.json" in STYLE_SOURCE
    assert "MAP_STYLES.get(map_style, TACTICAL_MAP_STYLE)" in RENDER_SOURCE

def test_pydeck_runtime_builds_openwaters_maplibre_html():
    import json

    import pydeck as pdk

    style_url = "https://tiles.openwaters.io/seamap/style.json"
    deck = pdk.Deck(
        map_style=style_url,
        map_provider="maplibre",
        map_projection="mercator",
        initial_view_state=pdk.ViewState(latitude=25.7, longitude=-80.2, zoom=7),
        layers=[],
        show_error=True,
    )

    payload = json.loads(deck.to_json())
    assert payload["mapProvider"] == "maplibre"
    assert payload["mapProjection"] == "mercator"
    assert payload["mapStyle"] == style_url

    html = deck.to_html(as_string=True)
    assert "maplibre-gl.css" in html
    assert style_url in html
    assert "showError: true" in html
