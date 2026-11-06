"""Regression tests: temporal windows preserve the newest real AIS observations."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from src.ingestion.models import AISObservation
from src.ml.temporal.preprocess import FEATURE_NAMES,build_temporal_sequences
from src.ml.temporal.types import MAX_TRACK_GAP_SECONDS

SOG_COLUMN=FEATURE_NAMES.index("sog_knots")
BASE=datetime(2026,11,6,12,0,0,tzinfo=timezone.utc)
MMSI="366123456"

def _obs(index,offset_seconds):
    return AISObservation(MMSI,25.0+index*0.001,-80.0+index*0.001,
        BASE+timedelta(seconds=offset_seconds),sog_knots=float(index),cog_degrees=90.0)
def _segment(start_index,count,start_offset=0,spacing=30):
    return [_obs(start_index+i,start_offset+i*spacing) for i in range(count)]
def _sog(sequence):
    return [int(value) for value in sequence.sequence[:,SOG_COLUMN].tolist()]
def _build(observations,window,cap=8):
    return build_temporal_sequences({MMSI:observations},sequence_length=window,
        minimum_points=4,max_windows_per_track=cap)

def test_window_uses_newest_points_when_length_is_not_a_multiple():
    sequences=_build(_segment(0,47),32)
    assert len(sequences)==1 and _sog(sequences[0])==list(range(15,47))

def test_windows_are_contiguous_non_overlapping_and_end_anchored():
    sequences=_build(_segment(0,20),8)
    assert [_sog(s) for s in sequences]==[list(range(4,12)),list(range(12,20))]

def test_exact_multiple_keeps_every_point():
    sequences=_build(_segment(0,16),8)
    assert [_sog(s) for s in sequences]==[list(range(0,8)),list(range(8,16))]

def test_cap_keeps_newest_windows_in_chronological_order():
    sequences=_build(_segment(0,40),8,cap=3)
    assert [_sog(s) for s in sequences]==[
        list(range(16,24)),list(range(24,32)),list(range(32,40))]

def test_newest_segment_wins_when_cap_is_reached_across_gaps():
    older=_segment(0,8,start_offset=0)
    newer=_segment(10,8,start_offset=8*30+int(2*MAX_TRACK_GAP_SECONDS))
    sequences=_build(older+newer,8,cap=1)
    assert len(sequences)==1 and _sog(sequences[0])==list(range(10,18))

def test_windows_never_cross_a_gap_and_stay_chronological():
    older=_segment(0,8,start_offset=0)
    newer=_segment(10,8,start_offset=8*30+int(2*MAX_TRACK_GAP_SECONDS))
    sequences=_build(older+newer,8,cap=8)
    assert [_sog(s) for s in sequences]==[list(range(0,8)),list(range(10,18))]

def test_too_short_segment_yields_no_window():
    assert _build(_segment(0,7),8)==[]
