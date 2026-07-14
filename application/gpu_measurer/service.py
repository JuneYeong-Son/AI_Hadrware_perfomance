from __future__ import annotations

from pathlib import Path
from typing import Any

from .baseline import BaselineStore, build_history_view, compare_models
from .benchmarks import BenchmarkRepository
from .collector import GpuCollector, NvidiaSmiError
from .models import BenchmarkMatch, MeasurementResult, SensorSnapshot, ValidationResult, WorkloadSpec
from .orchestrator import MeasurementOrchestrator
from .reporting import run_measurement
from .report_builder import build_shared_report, build_text_report
from .serialization import benchmark_to_dict, measurement_to_dict, snapshot_to_dict, validation_to_dict
from .usage_monitor import UsageMonitor, abuse_indicators
from .workload import GpuWorkloadRunner, get_default_workload_runner


class GpuMeasurementService:
    """Application boundary shared by desktop, web, CLI, and agent adapters."""

    def __init__(
        self,
        collector: GpuCollector,
        benchmarks: BenchmarkRepository,
        *,
        workload_runner: GpuWorkloadRunner | None = None,
        baseline_store: BaselineStore | None = None,
        usage_monitor: UsageMonitor | None = None,
    ):
        self.collector = collector
        self.benchmarks = benchmarks
        self.workload_runner = workload_runner or get_default_workload_runner()
        self.baseline_store = baseline_store
        self.usage_monitor = usage_monitor

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

    # --- Controlled GPU workload validation (P0) ---------------------------

    def _device_uuid(self, gpu_index: int) -> str:
        return self.collector.static_info(gpu_index).get("uuid", "unknown")

    def validate_gpu(
        self,
        gpu_index: int,
        spec: WorkloadSpec | None = None,
        *,
        attach_history: bool = True,
        progress=None,
        cancel_event=None,
    ) -> tuple[ValidationResult, dict[str, Any]]:
        """Run a controlled GPU workload and diagnose the result.

        ``progress`` and ``cancel_event`` let a desktop background worker drive a
        progress screen and cancel a long workload without the UI touching the
        collector or reimplementing any measurement logic.
        """
        spec = spec or WorkloadSpec()
        orchestrator = MeasurementOrchestrator(self.collector, self.workload_runner)
        result = orchestrator.validate(
            spec, gpu_index, progress=progress, cancel_event=cancel_event
        )
        if attach_history and self.baseline_store is not None:
            uuid = result.device.get("uuid", "unknown")
            history = build_history_view(self.baseline_store.load_history(uuid))
            result.baseline = {
                "record_count": history["record_count"],
                "comparison": history["comparison"],
            }
        return result, validation_to_dict(result)

    def baseline_gpu(
        self,
        gpu_index: int,
        spec: WorkloadSpec | None = None,
        *,
        progress=None,
        cancel_event=None,
    ) -> tuple[ValidationResult, dict[str, Any]]:
        """Validate, then store the result as a baseline only when it is valid."""
        if self.baseline_store is None:
            raise ValueError("baseline store is not configured")
        result, payload = self.validate_gpu(
            gpu_index,
            spec,
            attach_history=False,
            progress=progress,
            cancel_event=cancel_event,
        )
        if result.workload.reliability != "valid":
            payload["baseline_saved"] = False
            payload["baseline_note"] = "측정 상태가 valid가 아니므로 기준선으로 저장하지 않았습니다."
            return result, payload
        record = self.baseline_store.save(result)
        payload["baseline_saved"] = True
        payload["baseline_id"] = record["baseline_id"]
        return result, payload

    def save_result_as_baseline(self, result: ValidationResult) -> dict[str, Any]:
        """Store an already-computed valid result as a baseline (no re-run)."""
        if self.baseline_store is None:
            raise ValueError("baseline store is not configured")
        if result.workload.reliability != "valid":
            return {
                "saved": False,
                "note": "측정 상태가 정상(valid)이 아니어서 기준으로 저장하지 않았습니다.",
            }
        record = self.baseline_store.save(result)
        return {"saved": True, "baseline_id": record["baseline_id"]}

    def compare_models(self, protocol_id: str | None = None) -> dict[str, Any]:
        """Cross-model comparison over the saved results (same protocol only)."""
        if self.baseline_store is None:
            return {"available": False, "protocol_id": None, "entries": []}
        return compare_models(self.baseline_store.all_records(), protocol_id=protocol_id)

    def read_gpu_history(self, gpu_index: int) -> dict[str, Any]:
        if self.baseline_store is None:
            raise ValueError("baseline store is not configured")
        try:
            uuid = self._device_uuid(gpu_index)
        except NvidiaSmiError:
            uuid = "unknown"
        return build_history_view(self.baseline_store.load_history(uuid))

    # --- Usage monitoring & used-GPU health indicators --------------------

    def record_usage(self, gpu_uuid: str, values: dict[str, Any]) -> None:
        if self.usage_monitor is not None and gpu_uuid:
            self.usage_monitor.record(gpu_uuid, values)

    def usage_summary(self, gpu_uuid: str) -> dict[str, Any]:
        if self.usage_monitor is None or not gpu_uuid:
            return {"has_data": False}
        return self.usage_monitor.summary(gpu_uuid)

    def abuse_check(self, result: ValidationResult) -> dict[str, Any]:
        """Observable-only used-GPU indicators (never a mining/age verdict)."""
        from .serialization import finding_to_dict

        rated = result.device.get("clocks.max.graphics")
        try:
            rated_clock = float(rated) if rated not in (None, "", "[N/A]") else None
        except (TypeError, ValueError):
            rated_clock = None
        usage = self.usage_summary(result.device.get("uuid", ""))
        return abuse_indicators(
            findings=[finding_to_dict(f) for f in result.findings],
            telemetry=result.telemetry_summary,
            performance=result.performance,
            rated_max_graphics_clock=rated_clock,
            usage=usage,
        )

    def text_report(self, result: ValidationResult) -> str:
        return build_text_report(result)

    def shared_report(self, result: ValidationResult) -> dict[str, Any]:
        return build_shared_report(result)


def build_service(repo_root: Path, collector: GpuCollector) -> GpuMeasurementService:
    benchmarks = BenchmarkRepository(repo_root / "data" / "static" / "benchmarks")
    baseline_store = BaselineStore(repo_root / "application" / "baselines")
    usage_monitor = UsageMonitor(repo_root / "application" / "monitor")
    return GpuMeasurementService(
        collector,
        benchmarks,
        baseline_store=baseline_store,
        usage_monitor=usage_monitor,
    )
