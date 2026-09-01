"""Regression tests for the post-collection sidebar connection refresh."""

from pathlib import Path


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_collection_refreshes_sidebar_after_collection():
    """Sidebar renders before collection, so completion must trigger a rerun."""
    assert 'st.session_state["collection_result"]' in APP_SOURCE
    assert "The sidebar is rendered before collection" in APP_SOURCE
    assert "st.rerun()" in APP_SOURCE
    assert "collection_result = st.session_state.pop(" in APP_SOURCE


def test_collection_result_is_preserved_across_refresh():
    """The rerun must not discard the existing collection result message."""
    assert '"success"' in APP_SOURCE
    assert '"warning"' in APP_SOURCE
    assert "Collection elapsed " in APP_SOURCE
