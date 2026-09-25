from datetime import datetime, timezone

from src.ingestion.aisstream import AISStreamProvider
from src.ingestion.models import AISObservation


def _obs(mmsi: str, minute: int) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=25.7 + minute * 0.001,
        longitude=-80.2 + minute * 0.001,
        received_at=datetime(2026, 9, 25, 0, minute, tzinfo=timezone.utc),
        sog_knots=8.0,
    )


def test_provider_derives_tracks_from_bounded_observations():
    provider = AISStreamProvider(api_key="key", bbox=[[[25.0, -81.0], [26.0, -80.0]]], max_messages=2)

    provider._record(_obs("111000001", 1))
    provider._record(_obs("111000001", 2))
    provider._record(_obs("222000001", 3))

    tracks = provider.fetch_tracks()

    assert tracks == {
        "111000001": [provider._observations[0]],
        "222000001": [provider._observations[1]],
    }
    assert not hasattr(provider, "_tracks")


def test_provider_vessel_view_uses_the_same_observation_buffer():
    provider = AISStreamProvider(api_key="key", bbox=[[[25.0, -81.0], [26.0, -80.0]]], max_messages=10)
    provider._record(_obs("111000001", 1))
    provider._record(_obs("111000001", 2))

    vessels = provider.fetch_vessels()

    assert len(vessels) == 1
    assert vessels[0].mmsi == "111000001"
    assert vessels[0].message_count == 2