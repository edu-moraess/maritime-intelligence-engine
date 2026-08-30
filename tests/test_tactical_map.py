"""Unit tests for tactical maritime map helpers."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from src.ui.tactical_map import (
    anomaly_mmsi_sets, build_track_segments, classify_vessel_status,
    density_points_from_observations, enrich_tactical_rows,
    movement_vector_endpoint, resolve_course_degrees, resolve_vessel_course, ship_polygon,
)
def test_resolve_vessel_course_prefers_heading():
    assert resolve_vessel_course(90.0, 180.0) == 90.0
def test_resolve_vessel_course_cog_fallback():
    assert resolve_vessel_course(None, 180.0) == 180.0
    assert resolve_vessel_course(400.0, 180.0) == 180.0
def test_resolve_vessel_course_missing():
    assert resolve_vessel_course(None, None) is None
    assert resolve_vessel_course(-1, 360) is None
def test_resolve_course_degrees_row():
    assert resolve_course_degrees({"heading_degrees": 10, "cog_degrees": 90}) == 10.0
def test_status_matrix():
    base = {"mmsi": "111111111", "stale": False, "message_count": 5}
    assert classify_vessel_status(base, selected_mmsi=None, anomaly_mmsis=set(), critical_mmsis=set()) == "NORMAL"
    assert classify_vessel_status({**base, "stale": True}, selected_mmsi=None, anomaly_mmsis=set(), critical_mmsis=set()) == "ATTENTION"
    assert classify_vessel_status(base, selected_mmsi=None, anomaly_mmsis={"111111111"}, critical_mmsis=set()) == "ANOMALY"
    assert classify_vessel_status(base, selected_mmsi=None, anomaly_mmsis={"111111111"}, critical_mmsis={"111111111"}) == "CRITICAL"
    assert classify_vessel_status(base, selected_mmsi="111111111", anomaly_mmsis={"111111111"}, critical_mmsis={"111111111"}) == "SELECTED"
def test_anomaly_mmsi_sets():
    findings = [SimpleNamespace(mmsi="1", score=0.4, category="x"), SimpleNamespace(mmsi="2", score=0.91, category="x"), SimpleNamespace(mmsi="3", score=0.1, category="critical_event")]
    anomaly, critical = anomaly_mmsi_sets(findings)
    assert anomaly == {"1","2","3"} and critical == {"2","3"}
def test_ship_polygon_orientation_differs():
    north, east = ship_polygon(0.0,0.0,0.0,scale_deg=0.02), ship_polygon(0.0,0.0,90.0,scale_deg=0.02)
    assert north[0]==north[-1] and north!=east
def test_vector_zero_and_positive_sog():
    assert movement_vector_endpoint(1.0,2.0,90.0,0.0) is None
    tip = movement_vector_endpoint(1.0,2.0,90.0,10.0)
    assert tip is not None and tip[1]>2.0
def test_track_zero_one_two_three_unordered():
    assert build_track_segments([], selected=False)==[]
    t0=datetime(2026,1,1,tzinfo=timezone.utc)
    one=[SimpleNamespace(latitude=1.0,longitude=2.0,received_at=t0)]
    assert build_track_segments(one, selected=False)==[]
    two=one+[SimpleNamespace(latitude=1.1,longitude=2.1,received_at=t0+timedelta(minutes=1))]
    assert len(build_track_segments(two, selected=False))==1
    unordered=[SimpleNamespace(latitude=1.2,longitude=10.2,received_at=t0+timedelta(minutes=10)),
               SimpleNamespace(latitude=1.0,longitude=10.0,received_at=t0),
               SimpleNamespace(latitude=1.1,longitude=10.1,received_at=t0+timedelta(minutes=5))]
    segs=build_track_segments(unordered, selected=True)
    assert len(segs)==2 and segs[0]["path"][0]==[10.0,1.0] and segs[-1]["color"][3]>=segs[0]["color"][3]
def test_enrich_integrity_and_selection_helper():
    rows=[{"mmsi":"111111111","name":"A","latitude":51.1,"longitude":1.1,"sog_knots":5.0,"cog_degrees":90.0,"heading_degrees":90.0,"stale":False,"message_count":4},
          {"mmsi":"222222222","name":"B","latitude":51.2,"longitude":1.2,"sog_knots":0.0,"cog_degrees":None,"heading_degrees":None,"stale":True,"message_count":1},
          {"mmsi":"333333333","name":"C","latitude":51.3,"longitude":1.3,"sog_knots":12.0,"cog_degrees":180.0,"heading_degrees":None,"stale":False,"message_count":8}]
    out=enrich_tactical_rows(rows, selected_mmsi="111111111", anomaly_mmsis={"333333333"}, critical_mmsis=set())
    assert len(out)==3 and out[0]["tactical_status"]=="SELECTED" and out[1]["tactical_status"]=="ATTENTION" and out[2]["tactical_status"]=="ANOMALY"
    assert out[0]["has_vector"] is True and out[1]["has_vector"] is False
    assert density_points_from_observations([])==[]
    from src.ui.pages_helpers import _apply_map_selection
    import streamlit as st
    class EventTrack:
        class selection:
            objects={"tracks":[{"mmsi":"999999999"}]}
    class EventOk:
        class selection:
            objects={"ais-targets":[{"mmsi":"235102528"}]}
    st.session_state.selected_mmsi="111111111"
    _apply_map_selection(EventTrack()); assert st.session_state.selected_mmsi=="111111111"
    _apply_map_selection(EventOk()); assert st.session_state.selected_mmsi=="235102528"
