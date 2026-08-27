"""Runtime trajectory representation for real AIS observations only.

No public pretrained trajectory checkpoint is bundled. The adapter intentionally
uses a deterministic feature representation followed by PCA fitted on the real
tracks available in the current session, and reports that provenance explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.ingestion.models import AISObservation, SimilarTrack
from src.trajectory.features import trajectory_vector


@dataclass
class EmbeddingResult:
    mmsis: list[str]
    matrix: np.ndarray
    projection: np.ndarray
    clusters: np.ndarray
    anomaly_scores: np.ndarray
    method: str
    model_checkpoint: str


class TrajectoryEmbeddingAdapter:
    """Fit representations only from the real observations passed to ``fit``."""

    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.pca: PCA | None = None
        self.clusterer: KMeans | None = None
        self.detector: IsolationForest | None = None
        self.result: EmbeddingResult | None = None

    @property
    def model_checkpoint(self) -> str:
        return "none: runtime PCA/IsolationForest trained only on real AIS observations"

    def fit(self, tracks: dict[str, list[AISObservation]]) -> EmbeddingResult | None:
        rows: list[tuple[str, np.ndarray]] = []
        for mmsi, observations in tracks.items():
            vector = trajectory_vector(observations)
            if vector is not None and np.isfinite(vector).all():
                rows.append((mmsi, vector))
        if len(rows) < 3:
            self.result = None
            return None
        mmsis = [item[0] for item in rows]
        matrix = np.vstack([item[1] for item in rows])
        scaled = self.scaler.fit_transform(matrix)
        n_components = max(2, min(8, scaled.shape[0] - 1, scaled.shape[1]))
        self.pca = PCA(n_components=n_components, random_state=self.random_state)
        projection = self.pca.fit_transform(scaled)
        n_clusters = max(2, min(5, len(rows) // 3))
        self.clusterer = KMeans(n_clusters=n_clusters, n_init=10, random_state=self.random_state)
        clusters = self.clusterer.fit_predict(projection)
        self.detector = IsolationForest(contamination="auto", random_state=self.random_state, n_estimators=100)
        self.detector.fit(projection)
        raw_scores = -self.detector.score_samples(projection)
        anomaly_scores = _normalize(raw_scores)
        self.result = EmbeddingResult(
            mmsis=mmsis,
            matrix=matrix,
            projection=projection,
            clusters=clusters,
            anomaly_scores=anomaly_scores,
            method="Feature vector → StandardScaler → PCA → KMeans + IsolationForest",
            model_checkpoint=self.model_checkpoint,
        )
        return self.result

    def embed(self, observations: list[AISObservation]) -> np.ndarray | None:
        vector = trajectory_vector(observations)
        if vector is None or self.pca is None:
            return None
        scaled = self.scaler.transform(vector.reshape(1, -1))
        return self.pca.transform(scaled)[0]

    def similar_tracks(
        self,
        current: list[AISObservation],
        tracks: dict[str, list[AISObservation]],
        limit: int = 5,
        region: str = "configured AIS area",
        current_mmsi: str | None = None,
    ) -> list[SimilarTrack]:
        if self.result is None:
            return []
        query = self.embed(current)
        if query is None:
            return []
        distances: list[tuple[float, str, int]] = []
        for mmsi, projection, cluster in zip(self.result.mmsis, self.result.projection, self.result.clusters):
            if current_mmsi is not None and mmsi == current_mmsi:
                continue
            if tracks.get(mmsi) is current:
                continue
            distance = float(np.linalg.norm(query - projection))
            distances.append((distance, mmsi, int(cluster)))
        distances.sort(key=lambda item: item[0])
        return [
            SimilarTrack(
                mmsi=mmsi,
                date=_track_date(tracks.get(mmsi, [])),
                region=region,
                cluster=cluster,
                similarity=float(1.0 / (1.0 + distance)),
            )
            for distance, mmsi, cluster in distances[:limit]
        ]


def _normalize(values: np.ndarray) -> np.ndarray:
    minimum, maximum = float(np.min(values)), float(np.max(values))
    if maximum - minimum < 1e-9:
        return np.full_like(values, 0.5, dtype=float)
    return (values - minimum) / (maximum - minimum)


def _track_date(track: list[AISObservation]) -> datetime:
    return track[0].timestamp if track else datetime.now(timezone.utc)
