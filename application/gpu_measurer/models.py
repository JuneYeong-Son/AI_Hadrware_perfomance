from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class GpuDevice:
    index: int
    name: str
    uuid: str


@dataclass(frozen=True)
class SensorSnapshot:
    timestamp: datetime
    gpu_index: int
    values: dict[str, float | str | None]


@dataclass
class BenchmarkMatch:
    requested_name: str
    passmark: dict[str, str] | None = None
    compute: dict[str, str] | None = None
    suggestions: list[tuple[str, float]] = field(default_factory=list)

    @property
    def exact(self) -> bool:
        return self.passmark is not None or self.compute is not None


@dataclass
class MeasurementResult:
    started_at: datetime
    finished_at: datetime
    gpu: dict[str, str]
    benchmark: BenchmarkMatch
    samples: list[SensorSnapshot]
    summary: dict[str, dict[str, float]]
    environment: dict[str, Any]
