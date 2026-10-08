from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.environment import (
    AlignmentPolicy,
    AlignmentStatus,
    EnvironmentalDataset,
    EnvironmentalNature,
    EnvironmentalPoint,
    EvidenceStatus,
    SpatialTemporalAligner,
    VesselEnvironmentTrack,
    haversine_km,
)
from src.ingestion.models import AISObservation

UTC = timezone.utc
BASE = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def ais(*, received_at: datetime = BASE, latitude: float = 25.0, longitude: float = -80.0) -> AISObservation:
    return AISObservation(
        mmsi="368207620",
        latitude=latitude,
        longitude=longitude,
        received_at=received_at,
        ais_timestamp_second=42,
        sog_knots=10.0,
        cog_degrees=90.0,
    )


def point(
    *,
    nature: EnvironmentalNature = EnvironmentalNature.ENVIRONMENTAL_OBSERVATION,
    reference_time: datetime | None = BASE,
    latitude: float | None = 25.0,
    longitude: float | None = -80.0,
    model_validity_time: datetime | None = None,
) -> EnvironmentalPoint:
    return EnvironmentalPoint(
        source="test-provider",
        nature=nature,
        latitude=latitude,
        longitude=longitude,
        reference_time=reference_time,
        model_validity_time=model_validity_time,
        variables={"wave_height": 1.2},
        spatial_resolution="point",
        temporal_resolution="PT1H",
        provenance={"provider_record_id": "r-1"},
    )


def dataset(p: EnvironmentalPoint) -> EnvironmentalDataset:
    return EnvironmentalDataset(
        source=p.source,
        nature=p.nature,
        points=(p,),
        spatial_resolution=p.spatial_resolution,
        temporal_resolution=p.temporal_resolution,
        provenance={"source": "fixture"},
    )


def explicit_policy(**kwargs) -> AlignmentPolicy:
    values = {
        "max_spatial_distance_km": 2.0,
        "max_temporal_delta_seconds": 300.0,
        "spatial_method": "DIRECT_POINT",
        "temporal_method": "ABSOLUTE_REFERENCE_TIME",
    }
    values.update(kwargs)
    return AlignmentPolicy(**values)


def test_nature_is_explicit_and_model_state_is_not_observation() -> None:
    observation = point()
    assert observation.nature is EnvironmentalNature.ENVIRONMENTAL_OBSERVATION
    model = point(
        nature=EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE,
        model_validity_time=BASE,
    )
    assert model.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE
    with pytest.raises(ValueError, match="model_validity_time"):
        point(nature=EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE)
    with pytest.raises(ValueError, match="not valid"):
        point(model_validity_time=BASE)


def test_model_state_rejects_divergent_temporal_references() -> None:
    with pytest.raises(ValueError, match="must equal"):
        point(
            nature=EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE,
            reference_time=BASE,
            model_validity_time=BASE + timedelta(minutes=1),
        )


def test_model_state_reference_is_canonical_and_consistent() -> None:
    model = point(
        nature=EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE,
        reference_time=None,
        model_validity_time=BASE,
    )
    assert model.reference_time == BASE
    assert model.model_validity_time == BASE


def test_timestamps_are_timezone_aware_and_normalized_to_utc() -> None:
    plus_two = BASE.astimezone(timezone(timedelta(hours=2)))
    environmental = point(reference_time=plus_two)
    assert environmental.reference_time == BASE
    with pytest.raises(ValueError, match="timezone-aware"):
        point(reference_time=datetime(2026, 10, 8, 12, 0))


def test_model_validity_time_is_the_model_alignment_reference_not_observed_at() -> None:
    model = point(
        nature=EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE,
        reference_time=BASE,
        model_validity_time=BASE,
    )
    result = SpatialTemporalAligner(explicit_policy()).align(ais(), dataset(model))
    assert result.match is not None
    assert result.match.temporal_delta_seconds == 0.0
    assert result.match.temporal_match_status is AlignmentStatus.LIMITED
    assert ais().observed_at is None


def test_ais_timestamp_second_is_not_converted_to_absolute_datetime() -> None:
    observation = ais()
    assert observation.ais_timestamp_second == 42
    assert observation.observed_at is None
    assert observation.received_at == BASE


def test_distance_is_explicit_and_coordinates_are_preserved() -> None:
    environmental = point(latitude=25.01, longitude=-80.0)
    result = SpatialTemporalAligner(explicit_policy(max_spatial_distance_km=2.0)).align(ais(), dataset(environmental))
    assert result.match is not None
    assert result.match.spatial_distance_km == pytest.approx(haversine_km(25.0, -80.0, 25.01, -80.0))
    assert result.match.environmental_point.latitude == 25.01
    assert result.match.spatial_match_status is AlignmentStatus.VALID


def test_dataset_rejects_source_and_nature_incompatibility() -> None:
    observation = point()
    with pytest.raises(ValueError, match="source and nature"):
        EnvironmentalDataset(
            source="different-provider",
            nature=observation.nature,
            points=(observation,),
        )
    model = point(
        nature=EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE,
        model_validity_time=BASE,
    )
    with pytest.raises(ValueError, match="source and nature"):
        EnvironmentalDataset(
            source=model.source,
            nature=EnvironmentalNature.ENVIRONMENTAL_OBSERVATION,
            points=(model,),
        )


def test_empty_dataset_remains_valid_absence_representation() -> None:
    empty = EnvironmentalDataset(
        source="future-provider",
        nature=EnvironmentalNature.ENVIRONMENTAL_OBSERVATION,
    )
    assert empty.points == ()


def test_no_threshold_is_not_implicitly_selected() -> None:
    result = SpatialTemporalAligner().align(ais(), dataset(point()))
    assert result.status is EvidenceStatus.NOT_ANALYZED
    assert result.reason_code == "SPATIAL_POLICY_REQUIRED"


def test_no_interpolation_or_nearest_point_is_silent() -> None:
    first = point()
    second = point(latitude=25.1)
    multi = EnvironmentalDataset(source=first.source, nature=first.nature, points=(first, second))
    result = SpatialTemporalAligner(explicit_policy()).align(ais(), multi)
    assert result.status is EvidenceStatus.NOT_ANALYZED
    assert result.reason_code == "INSUFFICIENT_METADATA"
    unsupported = SpatialTemporalAligner(explicit_policy(spatial_method="NEAREST_CELL")).align(ais(), dataset(first))
    assert unsupported.reason_code == "INTERPOLATION_POLICY_REQUIRED"


def test_temporal_delta_and_mismatch_are_explicit() -> None:
    environmental = point(reference_time=BASE + timedelta(seconds=120))
    result = SpatialTemporalAligner(explicit_policy()).align(ais(), dataset(environmental))
    assert result.match is not None
    assert result.match.temporal_delta_seconds == 120.0
    assert result.match.temporal_match_status is AlignmentStatus.VALID
    late = point(reference_time=BASE + timedelta(seconds=301))
    mismatch = SpatialTemporalAligner(explicit_policy()).align(ais(), dataset(late))
    assert mismatch.status is EvidenceStatus.NOT_ANALYZED
    assert mismatch.reason_code == "TEMPORAL_MISMATCH"
    assert mismatch.match is not None
    assert mismatch.match.temporal_match_status is AlignmentStatus.MISMATCH


def test_missing_dataset_and_point_are_not_analyzed() -> None:
    aligner = SpatialTemporalAligner(explicit_policy())
    assert aligner.align(ais(), None).reason_code == "NO_ENVIRONMENTAL_DATASET"
    empty = EnvironmentalDataset(source="test-provider", nature=EnvironmentalNature.ENVIRONMENTAL_OBSERVATION)
    assert aligner.align(ais(), empty).reason_code == "NO_ENVIRONMENTAL_POINT"


def test_missing_temporal_or_spatial_reference_is_not_analyzed() -> None:
    aligner = SpatialTemporalAligner(explicit_policy())
    assert aligner.align(ais(), dataset(point(reference_time=None))).reason_code == "MISSING_TEMPORAL_REFERENCE"
    assert aligner.align(ais(), dataset(point(latitude=None))).reason_code == "MISSING_SPATIAL_REFERENCE"


def test_missing_provenance_is_not_analyzed() -> None:
    environmental = EnvironmentalPoint(
        source="test-provider",
        nature=EnvironmentalNature.ENVIRONMENTAL_OBSERVATION,
        latitude=25.0,
        longitude=-80.0,
        reference_time=BASE,
        provenance={},
    )
    result = SpatialTemporalAligner(explicit_policy()).align(ais(), dataset(environmental))
    assert result.status is EvidenceStatus.NOT_ANALYZED
    assert result.reason_code == "INSUFFICIENT_METADATA"


def test_spatial_mismatch_is_not_analyzed_not_no_signal() -> None:
    far = point(latitude=26.0)
    result = SpatialTemporalAligner(explicit_policy()).align(ais(), dataset(far))
    assert result.status is EvidenceStatus.NOT_ANALYZED
    assert result.reason_code == "SPATIAL_MISMATCH"
    assert result.match is not None
    assert result.match.spatial_match_status is AlignmentStatus.MISMATCH


def test_track_preserves_ais_environment_and_provenance_without_mutation() -> None:
    observation = ais()
    environmental = point()
    result = SpatialTemporalAligner(explicit_policy()).align(observation, dataset(environmental))
    assert result.match is not None
    track = VesselEnvironmentTrack.from_match(result.match)
    assert track.mmsi == observation.mmsi
    assert track.ais_observation is observation
    assert track.environmental_point is environmental
    assert track.source == "test-provider"
    assert track.nature is environmental.nature
    assert track.provenance["provider_record_id"] == "r-1"
    assert track.spatial_distance_km == 0.0
    assert track.temporal_delta_seconds == 0.0
    assert track.contextual_alignment is True
    assert observation.observed_at is None


def test_valid_match_is_not_positive_evidence() -> None:
    result = SpatialTemporalAligner(explicit_policy()).align(ais(), dataset(point()))
    assert result.match is not None
    assert result.match.matched is True
    assert result.status is EvidenceStatus.NOT_ANALYZED
    assert result.reason_code == "ALIGNMENT_ONLY_NO_ANALYSIS"


def test_variables_and_provenance_are_immutable_views() -> None:
    environmental = point()
    with pytest.raises(TypeError):
        environmental.variables["wave_height"] = 9.0  # type: ignore[index]
    with pytest.raises(TypeError):
        environmental.provenance["x"] = "y"  # type: ignore[index]
