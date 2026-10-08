"""Runtime evidence primitives used before EvidenceRegistry/Fusion exists.

These records make producer execution state explicit without claiming that the
runtime already implements the final EvidenceRecord contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvidenceState = Literal[
    "NOT_ANALYZED",
    "ANALYZED_NO_SIGNAL",
    "ANALYZED_SIGNAL",
    "NOT_APPLICABLE",
]
SignalPolarity = Literal["POSITIVE", "NEGATIVE", "INDETERMINATE"]
ReasonCode = Literal[
    "INSUFFICIENT_INPUT",
    "EXECUTION_FAILURE",
    "DEPENDENCY_UNAVAILABLE",
    "TIMEOUT",
    "UNKNOWN",
]


@dataclass(frozen=True)
class ProducerEvidence:
    """Explicit producer-side evidence state.

    This is intentionally smaller than the future EvidenceRecord and is not a
    registry or fusion object.
    """

    producer_id: str
    claim_type: str
    state: EvidenceState
    signal_polarity: SignalPolarity
    subject_id: str | None = None
    reason_code: ReasonCode | None = None
    score: float | None = None

    def __post_init__(self) -> None:
        if self.state == "NOT_ANALYZED" and self.reason_code is None:
            raise ValueError("NOT_ANALYZED requires a reason_code")
        if self.state != "NOT_ANALYZED" and self.reason_code is not None:
            raise ValueError("reason_code is only valid for NOT_ANALYZED")
        if self.state == "ANALYZED_NO_SIGNAL" and self.signal_polarity != "NEGATIVE":
            raise ValueError("ANALYZED_NO_SIGNAL requires NEGATIVE polarity")
        if self.state == "ANALYZED_SIGNAL" and self.signal_polarity != "POSITIVE":
            raise ValueError("ANALYZED_SIGNAL requires POSITIVE polarity")
