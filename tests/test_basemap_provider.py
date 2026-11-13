from pathlib import Path


RENDER_SOURCE = Path("src/ui/_pages_map_render.py").read_text(encoding="utf-8")
STYLE_SOURCE = Path("src/ui/_pages_map_impl.py").read_text(encoding="utf-8")


def test_supported_basemaps_keep_native_streamlit_pydeck_renderer():
    assert '"Dark Matter"' in STYLE_SOURCE
    assert '"Positron"' in STYLE_SOURCE
    assert '"Voyager"' in STYLE_SOURCE
    assert 'event = st.pydeck_chart(deck' in RENDER_SOURCE
    assert "components.html" not in RENDER_SOURCE
    assert "map_provider" not in RENDER_SOURCE
    assert "map_projection" not in RENDER_SOURCE


def test_deferred_nautical_chart_is_not_exposed_or_runtime_patched():
    assert "Nautical Chart" not in STYLE_SOURCE
    assert "openwaters.io/seamap" not in STYLE_SOURCE
    ui_init = Path("src/ui/__init__.py").read_text(encoding="utf-8")
    assert "patch_openwaters" not in ui_init
    assert "OPENWATERS_PATCHED" not in ui_init
