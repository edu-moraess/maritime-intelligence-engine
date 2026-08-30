"""Tests for Vessel Quick Intelligence popup helpers."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import patch
from src.ui.vessel_popup import render_vessel_quick_intelligence
def test_render_none_vessel_does_not_crash():
    render_vessel_quick_intelligence(None, SimpleNamespace(findings=[], vessels=[]))
def test_render_with_vessel_no_photo():
    vessel=SimpleNamespace(mmsi="235102528",vessel_name="BF VOLUNTEER",sog_knots=0.1,cog_degrees=272.6,heading_degrees=259.0,latitude=51.32,longitude=1.42,imo=None)
    with patch("src.ui.vessel_popup._cached_photo", return_value=None):
        render_vessel_quick_intelligence(vessel, SimpleNamespace(findings=[SimpleNamespace(mmsi="235102528",category="loitering",score=0.4)], vessels=[vessel]))
def test_render_with_photo_sets_session_keys():
    import streamlit as st
    from src.enrichment.vessel_photo import VesselPhoto
    vessel=SimpleNamespace(mmsi="235102528",vessel_name="BF VOLUNTEER",sog_knots=1.0,cog_degrees=10.0,heading_degrees=10.0,latitude=51.0,longitude=1.0,imo=None)
    photo=VesselPhoto(image_bytes=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82',mime_type="image/jpeg",source_url="https://commons.example/File:X.jpg",commons_title="File:X.jpg",license_name="CC BY-SA 4.0",author="A",qid="Q1",verified=True)
    with patch("src.ui.vessel_popup._cached_photo", return_value=photo):
        render_vessel_quick_intelligence(vessel, SimpleNamespace(findings=[], vessels=[vessel]))
    assert st.session_state.get("quick_intel_mmsi")=="235102528"
