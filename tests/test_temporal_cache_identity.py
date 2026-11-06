"""Regression tests for temporal cache identity and retry semantics."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest
from src.config.settings import AppSettings, DEFAULT_BBOX
from src.ingestion.models import AISObservation
from src.intelligence.engine import _track_fingerprint, create_engine
from src.ml.temporal.types import TemporalFitResult

BASE=datetime(2026,11,6,12,0,0,tzinfo=timezone.utc)
REGION_A=((10.0,100.0),(11.0,101.0))
REGION_B=((50.0,-5.0),(51.0,2.0))

def _obs(mmsi,seconds,*,lon,lat=25.7,sog=10.0,cog=90.0,heading=90.0):
    return AISObservation(mmsi=mmsi,latitude=lat,longitude=lon,
        received_at=BASE+timedelta(seconds=seconds),sog_knots=sog,
        cog_degrees=cog,heading_degrees=heading,vessel_name="TEST",
        ais_timestamp_second=seconds%60)

def _tracks(prefix="800000",lon_offset=0.0):
    return {f"{prefix}{i:03d}":[
        _obs(f"{prefix}{i:03d}",0,lon=-80.10+lon_offset+i*0.01),
        _obs(f"{prefix}{i:03d}",60,lon=-80.09+lon_offset+i*0.01)]
        for i in range(1,4)}

def _stationary():
    return {"700000001":[_obs("700000001",0,lon=-80.5,sog=0.0),
                         _obs("700000001",60,lon=-80.5,sog=0.0)]}

class _ScriptedAdapter:
    def __init__(self,*outcomes):
        self.outcomes=list(outcomes); self.calls=0; self.seed=42
    def fit(self,tracks):
        outcome=self.outcomes[min(self.calls,len(self.outcomes)-1)]
        self.calls+=1
        if isinstance(outcome,Exception): raise outcome
        return outcome

def _result(status): return TemporalFitResult(status=status,reason=f"scripted {status}")
def _engine(adapter=None):
    engine=create_engine(AppSettings(aisstream_api_key="k",bbox=DEFAULT_BBOX))
    if adapter is not None: engine.temporal_adapter=adapter
    return engine
def _load(engine,tracks):
    engine.current_session_observations=[o for track in tracks.values() for o in track]

def test_fingerprint_is_deterministic_and_track_order_independent():
    tracks=_tracks()
    reordered={k:list(reversed(v)) for k,v in reversed(list(tracks.items()))}
    assert _track_fingerprint(tracks)==_track_fingerprint(reordered)

@pytest.mark.parametrize("attr,value",[
    ("latitude",25.8),("longitude",-79.0),("sog_knots",11.0),
    ("cog_degrees",91.0),("heading_degrees",92.0)])
def test_fingerprint_changes_when_content_changes_with_same_shape(attr,value):
    tracks=_tracks(); baseline=_track_fingerprint(tracks); mmsi=next(iter(tracks))
    changed={k:list(v) for k,v in tracks.items()}
    changed[mmsi][-1]=replace(changed[mmsi][-1],**{attr:value})
    assert _track_fingerprint(changed)!=baseline

def test_fingerprint_changes_with_timestamp_and_observation_count():
    tracks=_tracks(); baseline=_track_fingerprint(tracks); mmsi=next(iter(tracks))
    shifted={k:list(v) for k,v in tracks.items()}
    last=shifted[mmsi][-1]
    shifted[mmsi][-1]=replace(last,received_at=last.received_at+timedelta(seconds=1))
    assert _track_fingerprint(shifted)!=baseline
    extended={k:list(v) for k,v in tracks.items()}
    extended[mmsi].append(_obs(mmsi,120,lon=-80.0))
    assert _track_fingerprint(extended)!=baseline

def test_equal_timestamp_order_is_part_of_temporal_input_identity():
    first=_obs("800000001",0,lon=-80.1); second=_obs("800000001",0,lon=-80.2)
    assert _track_fingerprint({"800000001":[first,second]})!=_track_fingerprint(
        {"800000001":[second,first]})

def test_fingerprint_of_empty_inputs_is_stable():
    assert _track_fingerprint({})==_track_fingerprint({"800000001":[]})
    assert _track_fingerprint({})!=_track_fingerprint(_tracks())

@pytest.mark.parametrize("status,expected_calls",[
    ("READY",1),("NOT_READY",1),("WAITING",1),("FAILED",2),("UNAVAILABLE",2)])
def test_only_deterministic_outcomes_are_served_from_cache(status,expected_calls):
    adapter=_ScriptedAdapter(_result(status)); engine=_engine(adapter); _load(engine,_tracks())
    engine._recompute(); engine._recompute()
    assert adapter.calls==expected_calls

def test_failed_result_is_retried_and_recovers():
    adapter=_ScriptedAdapter(_result("FAILED"),_result("READY"))
    engine=_engine(adapter); _load(engine,_tracks())
    engine._recompute()
    assert engine.temporal.status=="FAILED" and engine._temporal_fingerprint is None
    engine._recompute()
    assert engine.temporal.status=="READY" and adapter.calls==2
    engine._recompute()
    assert adapter.calls==2

def test_transient_exception_preserves_cause_and_is_retried():
    adapter=_ScriptedAdapter(RuntimeError("transient outage"),_result("READY"))
    engine=_engine(adapter); _load(engine,_tracks())
    engine._recompute()
    assert engine.temporal.status=="FAILED"
    assert "transient outage" in engine.temporal.reason
    engine._recompute()
    assert engine.temporal.status=="READY" and adapter.calls==2

def test_same_shape_content_change_invalidates_cache():
    adapter=_ScriptedAdapter(_result("READY")); engine=_engine(adapter)
    _load(engine,_tracks()); engine._recompute()
    _load(engine,_tracks(lon_offset=0.001)); engine._recompute()
    assert adapter.calls==2

def test_tracks_outside_model_tracks_do_not_invalidate_cache():
    adapter=_ScriptedAdapter(_result("READY")); engine=_engine(adapter)
    tracks=_tracks(); _load(engine,tracks); engine._recompute(); first=engine.temporal
    _load(engine,{**tracks,**_stationary()}); engine._recompute()
    assert adapter.calls==1 and engine.temporal is first

def test_cache_key_depends_on_session_region_and_configuration():
    engine=_engine(); tracks=_tracks(); base=engine._temporal_cache_key(tracks)
    assert engine._temporal_cache_key(tracks)==base
    engine._session_generation+=1
    assert engine._temporal_cache_key(tracks)!=base
    engine._session_generation-=1
    original=engine.settings
    engine.settings=replace(original,bbox=REGION_A,monitoring_bboxes=(REGION_A,REGION_B))
    assert engine._temporal_cache_key(tracks)!=base
    engine.settings=original
    assert engine._temporal_cache_key(tracks)==base
    engine.temporal_adapter.seed+=1
    assert engine._temporal_cache_key(tracks)!=base

def test_clear_session_data_starts_a_new_session_identity():
    engine=_engine(); tracks=_tracks(); before=engine._temporal_cache_key(tracks)
    engine.clear_session_data()
    assert engine._temporal_cache_key(tracks)!=before
