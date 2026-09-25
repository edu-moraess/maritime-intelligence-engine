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


def test_provider_is_stream_only():
    provider = AISStreamProvider(
        api_key="key",
        bbox=[[[25.0, -81.0], [26.0, -80.0]]],
        max_messages=2,
    )

    provider._record(_obs("111000001", 1))
    provider._record(_obs("111000001", 2))

    assert not hasattr(provider, "_observations")
    assert not hasattr(provider, "_tracks")
    assert provider.status.messages_received == 2
    assert provider.status.active_vessels == 0


def test_provider_reset_keeps_no_observation_state():
    provider = AISStreamProvider(
        api_key="key",
        bbox=[[[25.0, -81.0], [26.0, -80.0]]],
    )
    provider._record(_obs("111000001", 1))

    provider.reset_session()

    assert not hasattr(provider, "_observations")
    assert provider.status.messages_received == 0
    assert provider.status.state == "DISCONNECTED"
