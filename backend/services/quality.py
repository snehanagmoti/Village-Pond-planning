"""Shared quality and upstream-error types for analysis services."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

QualityStatus = Literal["reliable", "degraded", "unavailable"]


class UpstreamDataError(RuntimeError):
    """Raised when a required source cannot provide defensible data."""

    def __init__(self, source: str, message: str):
        super().__init__(message)
        self.source = source
        self.message = message


class AnalysisValidationError(RuntimeError):
    """Raised when derived data fails a scientific-quality gate."""


@dataclass
class SourceInfo:
    name: str
    status: QualityStatus
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolution: Optional[str] = None
    period: Optional[str] = None
    model: Optional[str] = None
    coverage_ratio: Optional[float] = None
    message: Optional[str] = None
    license_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
