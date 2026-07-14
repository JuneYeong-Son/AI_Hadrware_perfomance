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


@dataclass(frozen=True)
class WorkloadSpec:
    """Controlled GPU workload configuration.

    A workload is only comparable to another one with the same protocol, so the
    fields that define the protocol (name, dtype, shape, flop convention) are
    kept together and hashed into a stable ``protocol_id``.
    """

    name: str = "gemm_square_fp32"
    dtype: str = "float32"
    size: int = 4096
    # Long enough that nvidia-smi's utilization window sees a busy GPU and the
    # measured window dominates the pre-workload baseline sample.
    warmup_iterations: int = 20
    measured_iterations: int = 300
    flop_convention: str = "multiply_add_as_2"

    @property
    def shape(self) -> dict[str, int]:
        return {"m": self.size, "n": self.size, "k": self.size}

    def operation_count(self, iterations: int) -> int:
        # C = A @ B for square matrices: 2 * n^3 FLOPs per matmul when a
        # multiply-add is counted as two operations.
        return 2 * self.size * self.size * self.size * iterations


@dataclass
class WorkloadResult:
    workload_name: str
    backend: str
    dtype: str
    shape: dict[str, int]
    warmup_iterations: int
    measured_iterations: int
    elapsed_seconds: float | None
    operation_count: int | None
    achieved_tflops: float | None
    flop_convention: str
    timing_source: str  # "cuda_event" | "perf_counter" | "none"
    device_name: str | None
    reliability: str  # "valid" | "inconclusive" | "failed"
    reason: str | None = None


@dataclass(frozen=True)
class Finding:
    category: str  # thermal | power | cooling | workload | driver | none
    severity: str  # info | warning | critical
    title: str
    evidence: dict[str, Any]
    confidence: str  # low | medium | high
    recommendation: str


@dataclass
class ValidationResult:
    started_at: datetime
    finished_at: datetime
    device: dict[str, str]
    environment: dict[str, Any]
    workload: WorkloadResult
    samples: list[SensorSnapshot]
    telemetry_summary: dict[str, dict[str, float]]
    performance: dict[str, Any]
    findings: list[Finding]
    limitations: list[str]
    protocol_id: str
    baseline: dict[str, Any] | None = None
