"""Provider-neutral environmental source interface.

No external provider is implemented in Phase 1.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import EnvironmentalDataset


class EnvironmentalProvider(Protocol):
    """Fetch an environmental dataset without coupling to AISProvider."""

    source: str

    def fetch(
        self,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> EnvironmentalDataset:
        """Return provider data; implementations must preserve source provenance."""
        ...
