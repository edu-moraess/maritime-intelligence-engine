from datetime import datetime, timezone

import pytest

from src.anomaly.evidence import analyze_anomalies
from src.environment.context import EnvironmentalContext
from src.evidence.runtime import ProducerEvidence
from src.ingestion.models import AISObservation, EnvironmentalObservation
from src.ml.temporal.evidence import temporal_evidence
from src.ml.temporal.types import TemporalFitResult


def _obs(*, sog=10.0, minute=0):
    return AISObservation(
        "368207620",
        25.7617,
        -80.1918,
        datetime(2026, 10, 8, 12, minute, tzinfo=timezone.utc),
        sog_knots=sog,
        cog_degrees=90.0,
        heading_degrees=90.0,
        raw={"id": minute},
    )


def test_rule_anomaly_analysis_emits_explicit_negative_evidence():
    findings, evidence = analyze_anomalies({"368207620": [_obs()]})

    assert findings == []
    by_claim = {item.claim_type: item for item in evidence}
    assert by_claim["SPEED_ANOMALY"].state == "ANALYZED_NO_SIGNAL"
    assert by_claim["SPEED_ANOMALY"].signal_polarity == "NEGATIVE"
    assert by_claim["SIGNAL_GAP"].state == "ANALYZED_NO_SIGNAL"
    assert by_claim["HEADING_ANOMALY"].state == "ANALYZED_NO_SIGNAL"
    assert by_claim["UNUSUAL_STOP"].state == "ANALYZED_NO_SIGNAL"
    assert by_claim["BEHAVIORAL_DEVIATION"].state == "NOT_ANALYZED"
    assert by_claim["BEHAVIORAL_DEVIATION"].reason_code == "INSUFFICIENT_INPUT"


def test_not_analyzed_requires_closed_reason():
    with pytest.raises(ValueError):
        ProducerEvidence(
            producer_id="TEST",
            claim_type="TEST",
            state="NOT_ANALYZED",
            signal_polarity="INDETERMINATE",
        )


def test_open_meteo_model_state_cannot_expose_physical_observation_time():
    validity = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    state = EnvironmentalObservation(
        source="open-meteo-marine",
        nature="ENVIRONMENTAL_MODEL_STATE",
        latitude=25.76,
        longitude=-80.19,
        model_validity_time=validity,
        region="region_1",
    )

    assert state.observed_at is None
    assert state.model_validity_time == validity
    assert state.reference_time == validity
    assert state.as_dict()["nature"] == "ENVIRONMENTAL_MODEL_STATE"


def test_environment_context_uses_reference_time_for_model_state():
    validity = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    state = EnvironmentalObservation(
        source="open-meteo-marine",
        nature="ENVIRONMENTAL_MODEL_STATE",
        latitude=25.76,
        longitude=-80.19,
        model_validity_time=validity,
        region="region_1",
    )

    context = EnvironmentalContext(region="region_1").add(state)
    assert context.reference_time == validity
    assert context.latest is state


def test_temporal_ready_is_score_evidence_not_negative_anomaly_evidence():
    result = TemporalFitResult(
        status="READY",
        reason="test",
        scores=[],
    )
    assert temporal_evidence(result) == []


def test_temporal_unavailable_is_not_analyzed():
    result = TemporalFitResult(status="UNAVAILABLE", reason="PyTorch unavailable")
    evidence = temporal_evidence(result)

    assert len(evidence) == 1
    assert evidence[0].state == "NOT_ANALYZED"
    assert evidence[0].reason_code == "DEPENDENCY_UNAVAILABLE"
