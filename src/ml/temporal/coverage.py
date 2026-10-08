"""Cobertura temporal, stitching e reamostragem para trilhas AIS reais."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import atan2, cos, radians, sin
from typing import Sequence

import numpy as np

from src.ingestion.models import AISObservation

STITCH_GAP_SECONDS = 300.0
RESAMPLE_INTERVAL_SECONDS = 60.0
MAX_INTERPOLATION_GAP_SECONDS = 120.0


@dataclass(frozen=True)
class ResampledTrack:
    """Grade temporal fixa com máscara de observação/interpolação válida."""

    mmsi: str
    timestamps: tuple[datetime, ...]
    latitude: np.ndarray
    longitude: np.ndarray
    sog_knots: np.ndarray
    cog_degrees: np.ndarray
    heading_degrees: np.ndarray
    mask: np.ndarray

    @property
    def missing_fraction(self) -> float:
        return float(1.0 - np.mean(self.mask)) if len(self.mask) else 1.0


def stitch_track(
    observations: Sequence[AISObservation],
    *,
    max_gap_seconds: float = STITCH_GAP_SECONDS,
) -> list[list[AISObservation]]:
    """Divide uma trilha quando o gap excede o limite de stitching.

    Um gap menor que 5 minutos permanece na mesma trilha; não há fusão entre
    MMSIs diferentes nem criação de observações sintéticas nesta etapa.
    """
    cleaned = sorted(
        (o for o in observations if o.valid),
        key=lambda o: o.received_at,
    )
    if not cleaned:
        return []
    segments: list[list[AISObservation]] = [[cleaned[0]]]
    threshold = max(0.0, float(max_gap_seconds))
    for current in cleaned[1:]:
        previous = segments[-1][-1]
        if (current.received_at - previous.received_at).total_seconds() > threshold:
            segments.append([current])
        else:
            segments[-1].append(current)
    return segments


def _interp(values: np.ndarray, known_times: np.ndarray, grid: np.ndarray, max_gap: float) -> tuple[np.ndarray, np.ndarray]:
    out = np.interp(grid, known_times, values)
    mask = np.ones(len(grid), dtype=bool)
    if len(known_times) < 2:
        mask[:] = False
        return out, mask
    nearest_left = np.searchsorted(known_times, grid, side="right") - 1
    nearest_left = np.clip(nearest_left, 0, len(known_times) - 1)
    nearest_right = np.clip(nearest_left + 1, 0, len(known_times) - 1)
    gap = known_times[nearest_right] - known_times[nearest_left]
    mask = (gap <= max_gap) | (grid == known_times[nearest_left])
    return out, mask


def _circular_interp(values: np.ndarray, known_times: np.ndarray, grid: np.ndarray, max_gap: float) -> tuple[np.ndarray, np.ndarray]:
    radians_values = np.unwrap(np.deg2rad(np.mod(values, 360.0)))
    interp, mask = _interp(radians_values, known_times, grid, max_gap)
    return np.mod(np.rad2deg(interp), 360.0), mask


def resample_track(
    observations: Sequence[AISObservation],
    *,
    interval_seconds: float = RESAMPLE_INTERVAL_SECONDS,
    max_interpolation_gap_seconds: float = MAX_INTERPOLATION_GAP_SECONDS,
) -> ResampledTrack | None:
    """Reamostra uma trilha para uma grade fixa sem esconder gaps grandes.

    Pontos interpolados recebem mask=1 somente quando o intervalo entre
    observações reais vizinhas é <= max_interpolation_gap_seconds. Valores
    fora dessa condição permanecem numericamente preenchidos para manter a
    forma do tensor, mas mask=0 impede que sejam tratados como evidência real.
    """
    cleaned = sorted((o for o in observations if o.valid), key=lambda o: o.received_at)
    if len(cleaned) < 2:
        return None
    step = max(1.0, float(interval_seconds))
    start = cleaned[0].received_at.astimezone(timezone.utc)
    end = cleaned[-1].received_at.astimezone(timezone.utc)
    start_epoch = start.timestamp()
    end_epoch = end.timestamp()
    grid_epoch = np.arange(start_epoch, end_epoch + 1e-6, step, dtype=np.float64)
    if len(grid_epoch) < 2:
        return None

    known = np.asarray([o.received_at.timestamp() for o in cleaned], dtype=np.float64)
    lat = np.asarray([o.latitude for o in cleaned], dtype=np.float64)
    lon = np.asarray([o.longitude for o in cleaned], dtype=np.float64)
    sog = np.asarray([o.sog_knots if o.sog_knots is not None else 0.0 for o in cleaned], dtype=np.float64)
    cog = np.asarray([o.cog_degrees if o.cog_degrees is not None else 0.0 for o in cleaned], dtype=np.float64)
    heading = np.asarray([o.heading_degrees if o.heading_degrees is not None else 0.0 for o in cleaned], dtype=np.float64)

    lat_i, m_lat = _interp(lat, known, grid_epoch, max_interpolation_gap_seconds)
    lon_i, m_lon = _interp(lon, known, grid_epoch, max_interpolation_gap_seconds)
    sog_i, m_sog = _interp(sog, known, grid_epoch, max_interpolation_gap_seconds)
    cog_i, m_cog = _circular_interp(cog, known, grid_epoch, max_interpolation_gap_seconds)
    heading_i, m_heading = _circular_interp(heading, known, grid_epoch, max_interpolation_gap_seconds)
    mask = m_lat & m_lon & m_sog & m_cog & m_heading

    timestamps = tuple(datetime.fromtimestamp(float(t), tz=timezone.utc) for t in grid_epoch)
    return ResampledTrack(
        mmsi=cleaned[0].mmsi,
        timestamps=timestamps,
        latitude=lat_i.astype(np.float32),
        longitude=lon_i.astype(np.float32),
        sog_knots=sog_i.astype(np.float32),
        cog_degrees=cog_i.astype(np.float32),
        heading_degrees=heading_i.astype(np.float32),
        mask=mask.astype(np.float32),
    )


def build_masked_windows(
    track: ResampledTrack,
    *,
    sequence_length: int,
    max_missing_fraction: float = 0.20,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Retorna janelas completas somente quando a ausência <= limite."""
    n = len(track.timestamps)
    length = max(1, int(sequence_length))
    allowed_missing = min(1.0, max(0.0, float(max_missing_fraction)))
    windows: list[tuple[np.ndarray, np.ndarray]] = []
    for start in range(0, max(0, n - length + 1)):
        mask = track.mask[start : start + length]
        if len(mask) != length or float(1.0 - np.mean(mask)) > allowed_missing:
            continue
        values = np.column_stack(
            [
                track.latitude[start : start + length],
                track.longitude[start : start + length],
                track.sog_knots[start : start + length],
                np.sin(np.deg2rad(track.cog_degrees[start : start + length])),
                np.cos(np.deg2rad(track.cog_degrees[start : start + length])),
                track.heading_degrees[start : start + length],
            ]
        ).astype(np.float32)
        windows.append((values, mask.astype(np.float32)))
    return windows
