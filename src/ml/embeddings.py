"""Runtime trajectory representation for real AIS observations only.

No public pretrained trajectory checkpoint is bundled. The adapter intentionally
uses a deterministic feature representation followed by PCA fitted on the real
tracks available in the current session.

IsolationForest is used as an unsupervised relative outlier detector. Its
normalized score is a session-relative ranking signal, NOT a probability or
calibrated confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

        # PCA/KMeans/IsolationForest are not meaningful with fewer than
        # three independent real trajectories.
        if len(rows) < 3:
            self.result = None
            self.pca = None
            self.clusterer = None
            self.detector = None
            return None

        mmsis = [item[0] for item in rows]
        matrix = np.vstack([item[1] for item in rows])

        scaled = self.scaler.fit_transform(matrix)

        n_components = max(
            2,
            min(8, scaled.shape[0] - 1, scaled.shape[1]),
        )

        self.pca = PCA(
            n_components=n_components,
            random_state=self.random_state,
        )
        projection = self.pca.fit_transform(scaled)

        n_clusters = max(2, min(5, len(rows) // 3))

        # KMeans requires n_clusters <= number of observations.
        n_clusters = min(n_clusters, len(rows))

        self.clusterer = KMeans(
            n_clusters=n_clusters,
            n_init=10,
            random_state=self.random_state,
        )
        clusters = self.clusterer.fit_predict(projection)

        self.detector = IsolationForest(
            contamination="auto",
            random_state=self.random_state,
            n_estimators=100,
        )
        self.detector.fit(projection)

        # IsolationForest.score_samples(): higher = more normal.
        # Negating it produces an outlier-oriented score where larger
        # values indicate greater isolation.
        raw_scores = -self.detector.score_samples(projection)

        # IMPORTANT:
        # This is only a relative score within the current real AIS session.
        # It is NOT a probability and must never be presented as confidence.
        anomaly_scores = _normalize(raw_scores)

        self.result = EmbeddingResult(
            mmsis=mmsis,
            matrix=matrix,
            projection=projection,
            clusters=clusters,
            anomaly_scores=anomaly_scores,
            method=(
                "Feature vector → StandardScaler → PCA → "
                "KMeans + IsolationForest (session-relative)"
            ),
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

        for mmsi, projection, cluster in zip(
            self.result.mmsis,
            self.result.projection,
            self.result.clusters,
        ):
            if current_mmsi is not None and mmsi == current_mmsi:
                continue

            if tracks.get(mmsi) is current:
                continue

            distance = float(np.linalg.norm(query - projection))

            distances.append(
                (distance, mmsi, int(cluster))
            )

        distances.sort(key=lambda item: item[0])

        return [
            SimilarTrack(
                mmsi=mmsi,
                first_received_at=_track_first_received_at(
                    tracks.get(mmsi, [])
                ),
                region=region,
                cluster=cluster,
                similarity=float(1.0 / (1.0 + distance)),
                source_label="REAL AIS SESSION",
            )
            for distance, mmsi, cluster in distances[:limit]
        ]


def _normalize(values: np.ndarray) -> np.ndarray:
    """Normalize an outlier score for relative ranking inside one session.

    The result is intentionally bounded to [0, 1], but it is NOT a probability
    and has no calibrated statistical confidence interpretation.
    """
    values = np.asarray(values, dtype=float)

    if values.size == 0:
        return np.array([], dtype=float)

    minimum = float(np.min(values))
    maximum = float(np.max(values))

    if maximum - minimum < 1e-9:
        return np.full_like(values, 0.5, dtype=float)

    normalized = (values - minimum) / (maximum - minimum)

    return np.clip(normalized, 0.0, 1.0)


def _track_first_received_at(
    track: list[AISObservation],
) -> datetime | None:
    return track[0].received_at if track else None