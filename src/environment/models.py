"""Immutable, provenance-preserving contracts for environmental alignment.

This module deliberately contains no provider integration and no statistical
analysis. Environmental values remain separate from AIS observations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping


class EnvironmentalNature(str, Enum):
    ENVIRONMENTAL_OBSERVATION = "ENVIRONMENTAL_OBSERVATION"
    ENVIRONMENTAL_MODEL_STATE = "ENVIRONMENTAL_MODEL_STATE"


class AlignmentStatus(str, Enum):
    VALID = "VALID"
    LIMITED = "LIMITED"
    MISMATCH = "MISMATCH"
    INDETERMINATE = "INDETERMINATE"
    DESIGN_DECISION_REQUIRED = "DESIGN_DECISION_REQUIRED"
    NOT_ANALYZED = "NOT_ANALYZED"


class EvidenceStatus(str, Enum):
    NOT_ANALYZED = "NOT_ANALYZED"


_REASON_NO_DATASET = "NO_ENVIRONMENTAL_DATASET"
_REASON_NO_POINT = "NO_ENVIRONMENTAL_POINT"
_REASON_MISSING_SPATIAL_REFERENCE = "MISSING_SPATIAL_REFERENCE"
_REASON_MISSING_TEMPORAL_REFERENCE = "MISSING_TEMPORAL_REFERENCE"
_REASON_MISSING_METADATA = "INSUFFICIENT_METADATA"
_REASON_SPATIAL_POLICY = "SPATIAL_POLICY_REQUIRED"
_REASON_TEMPORAL_POLICY = "TEMPORAL_POLICY_REQUIRED"
_REASON_SPATIAL_MISMATCH = "SPATIAL_MISMATCH"
_REASON_TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
_REASON_INTERPOLATION_POLICY = "INTERPOLATION_POLICY_REQUIRED"


def _utc_or_none(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _coordinate(value: float | None, name: str, minimum: float, maximum: float) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not isfinite(numeric) or not minimum <= numeric <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum} and {maximum}")
    return numeric


@dataclass(frozen=True)
class EnvironmentalPoint:
    """One environmental value set at a spatial-temporal reference.

    ``reference_time`` may be absent only to preserve an explicitly incomplete
    upstream record. The aligner then returns NOT_ANALYZED rather than guessing.
    A model state must always carry ``model_validity_time``.
    """

    source: str
    nature: EnvironmentalNature
    latitude: float | None
    longitude: float | None
    reference_time: datetime | None
    model_validity_time: datetime | None = None
    variables: Mapping[str, Any] = field(default_factory=dict)
    spatial_resolution: str | float | None = None
    temporal_resolution: str | float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")
        if not isinstance(self.nature, EnvironmentalNature):
            raise TypeError("nature must be an EnvironmentalNature")
        object.__setattr__(self, "latitude", _coordinate(self.latitude, "latitude", -90.0, 90.0))
        object.__setattr__(self, "longitude", _coordinate(self.longitude, "longitude", -180.0, 180.0))
        reference = _utc_or_none(self.reference_time, "reference_time")
        validity = _utc_or_none(self.model_validity_time, "model_validity_time")
        if self.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE and validity is None:
            raise ValueError("model_validity_time is required for an environmental model state")
        if self.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE and reference is None:
            reference = validity
        if (
            self.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE
            and reference is not None
            and reference != validity
        ):
            raise ValueError("reference_time must equal model_validity_time for an environmental model state")
        if self.nature is EnvironmentalNature.ENVIRONMENTAL_OBSERVATION and validity is not None:
            raise ValueError("model_validity_time is not valid for a physical environmental observation")
        object.__setattr__(self, "reference_time", reference)
        object.__setattr__(self, "model_validity_time", validity)
        object.__setattr__(self, "variables", _mapping(self.variables))
        object.__setattr__(self, "metadata", _mapping(self.metadata))
        object.__setattr__(self, "provenance", _mapping(self.provenance))

    @property
    def temporal_reference(self) -> datetime | None:
        """Return the comparison reference without calling a model state observed."""
        if self.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE:
            return self.model_validity_time
        return self.reference_time


@dataclass(frozen=True)
class EnvironmentalDataset:
    """A provider-neutral collection; it need not be a grid, sensor or series."""

    source: str
    nature: EnvironmentalNature
    points: tuple[EnvironmentalPoint, ...] = ()
    spatial_resolution: str | float | None = None
    temporal_resolution: str | float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")
        if not isinstance(self.nature, EnvironmentalNature):
            raise TypeError("nature must be an EnvironmentalNature")
        points = tuple(self.points)
        if any(point.source != self.source or point.nature is not self.nature for point in points):
            raise ValueError("dataset source and nature must match every point")
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "metadata", _mapping(self.metadata))
        object.__setattr__(self, "provenance", _mapping(self.provenance))


@dataclass(frozen=True)
class AlignmentPolicy:
    """Explicit matching policy; absent values intentionally block matching."""

    max_spatial_distance_km: float | None = None
    max_temporal_delta_seconds: float | None = None
    spatial_method: str | None = None
    temporal_method: str | None = None

    def __post_init__(self) -> None:
        if self.max_spatial_distance_km is not None and (
            not isfinite(float(self.max_spatial_distance_km)) or self.max_spatial_distance_km < 0
        ):
            raise ValueError("max_spatial_distance_km must be finite and non-negative")
        if self.max_temporal_delta_seconds is not None and (
            not isfinite(float(self.max_temporal_delta_seconds)) or self.max_temporal_delta_seconds < 0
        ):
            raise ValueError("max_temporal_delta_seconds must be finite and non-negative")

    @property
    def spatially_defined(self) -> bool:
        return self.max_spatial_distance_km is not None and self.spatial_method is not None

    @property
    def temporally_defined(self) -> bool:
        return self.max_temporal_delta_seconds is not None and self.temporal_method is not None


@dataclass(frozen=True)
class SpatialTemporalMatch:
    """Audit record for one AIS/environment pair, including failed matches."""

    ais_observation: Any
    environmental_point: EnvironmentalPoint
    spatial_distance_km: float | None
    temporal_delta_seconds: float | None
    spatial_match_status: AlignmentStatus
    temporal_match_status: AlignmentStatus
    source: str
    nature: EnvironmentalNature
    provenance: Mapping[str, Any]
    spatial_method: str | None = None
    temporal_method: str | None = None

    def __post_init__(self) -> None:
        if self.source != self.environmental_point.source or self.nature is not self.environmental_point.nature:
            raise ValueError("match source and nature must match the environmental point")
        object.__setattr__(self, "provenance", _mapping(self.provenance))

    @property
    def matched(self) -> bool:
        return self.spatial_match_status in {AlignmentStatus.VALID, AlignmentStatus.LIMITED} and self.temporal_match_status in {AlignmentStatus.VALID, AlignmentStatus.LIMITED}


@dataclass(frozen=True)
class AlignmentResult:
    """Result that never promotes insufficient context to an analytical signal."""

    status: EvidenceStatus
    reason_code: str
    match: SpatialTemporalMatch | None = None


@dataclass(frozen=True)
class VesselEnvironmentTrack:
    """Separate contextual alignment; it is not a modified AIS observation."""

    mmsi: str
    ais_observation: Any
    environmental_point: EnvironmentalPoint
    vessel_latitude: float
    vessel_longitude: float
    environment_latitude: float | None
    environment_longitude: float | None
    vessel_reference_time: datetime
    environment_reference_time: datetime | None
    spatial_distance_km: float | None
    temporal_delta_seconds: float | None
    spatial_match_status: AlignmentStatus
    temporal_match_status: AlignmentStatus
    environmental_variables: Mapping[str, Any]
    source: str
    nature: EnvironmentalNature
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "vessel_reference_time", _utc_or_none(self.vessel_reference_time, "vessel_reference_time"))
        object.__setattr__(self, "environment_reference_time", _utc_or_none(self.environment_reference_time, "environment_reference_time"))
        object.__setattr__(self, "environmental_variables", _mapping(self.environmental_variables))
        object.__setattr__(self, "provenance", _mapping(self.provenance))

    @classmethod
    def from_match(cls, match: SpatialTemporalMatch) -> "VesselEnvironmentTrack":
        ais = match.ais_observation
        return cls(
            mmsi=str(ais.mmsi),
            ais_observation=ais,
            environmental_point=match.environmental_point,
            vessel_latitude=float(ais.latitude),
            vessel_longitude=float(ais.longitude),
            environment_latitude=match.environmental_point.latitude,
            environment_longitude=match.environmental_point.longitude,
            vessel_reference_time=ais.received_at,
            environment_reference_time=match.environmental_point.temporal_reference,
            spatial_distance_km=match.spatial_distance_km,
            temporal_delta_seconds=match.temporal_delta_seconds,
            spatial_match_status=match.spatial_match_status,
            temporal_match_status=match.temporal_match_status,
            environmental_variables=match.environmental_point.variables,
            source=match.source,
            nature=match.nature,
            provenance=match.provenance,
        )

    @property
    def contextual_alignment(self) -> bool:
        return True
