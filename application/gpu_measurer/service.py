from __future__ import annotations

from pathlib import Path
from typing import Any

from .benchmarks import BenchmarkRepository
from .collector import GpuCollector
from .models import BenchmarkMatch, MeasurementResult, SensorSnapshot
from .reporting import run_measurement
from .serialization import benchmark_to_dict, measurement_to_dict, snapshot_to_dict


class GpuMeasurementService:
    """Application boundary shared by desktop, web, CLI, and agent adapters."""

    def __init__(
        self,
        collector: GpuCollector,
        benchmarks: BenchmarkRepository,
    ):
        self.collector = collector
        self.benchmarks = benchmarks

    @property
    def provider_name(self) -> str:
        return self.collector.provider_name

    def list_devices(self) -> list[dict[str, Any]]:
        return [
            {"index": device.index, "name": device.name, "uuid": device.uuid}
            for device in self.collector.list_devices()
        ]

    def inspect_device(self, gpu_index: int) -> dict[str, Any]:
        gpu = self.collector.static_info(gpu_index)
        return {
            "gpu": gpu,
            "benchmark": benchmark_to_dict(self.benchmarks.match(gpu["name"])),
            "environment": self.collector.environment(),
        }

    def benchmark_match(self, gpu_name: str) -> BenchmarkMatch:
        return self.benchmarks.match(gpu_name)

    def environment(self) -> dict[str, str]:
        return self.collector.environment()

    def current_snapshot(self, gpu_index: int) -> tuple[SensorSnapshot, dict[str, Any]]:
        snapshot = self.collector.snapshot(gpu_index)
        return snapshot, snapshot_to_dict(snapshot)

    def measure(
        self,
        gpu_index: int,
        duration_seconds: float,
        interval_seconds: float,
    ) -> tuple[MeasurementResult, dict[str, Any]]:
        result = run_measurement(
            self.collector,
            self.benchmarks,
            gpu_index,
            duration_seconds,
            interval_seconds,
        )
        return result, measurement_to_dict(result)


def build_service(repo_root: Path, collector: GpuCollector) -> GpuMeasurementService:
    benchmarks = BenchmarkRepository(repo_root / "data" / "static" / "benchmarks")
    return GpuMeasurementService(collector, benchmarks)
