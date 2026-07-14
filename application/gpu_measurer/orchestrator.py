"""Coordinates a full controlled measurement.

Steps: pre-check the device and backend, sample sensors in the background while
the workload runs, then combine the workload result with the telemetry and
diagnostics into a single ``ValidationResult``. Sensor collection and compute
stay in separate components; this class only orchestrates them.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable

from .collector import CollectorError, GpuCollector
from .diagnostics import DiagnosticEngine
from .gpu_reference import FP32_GEMM_NORMAL_RANGE_PCT, theoretical_peak_tflops
from .models import SensorSnapshot, ValidationResult, WorkloadSpec
from .reporting import summarize_snapshots
from .workload import GpuWorkloadRunner, protocol_id

# progress(event_name, payload) — e.g. ("stage", {"name": "workload"}) or
# ("sample", {"temperature_c": 70.0, ...}). Used by the desktop worker to drive
# the progress screen without the UI touching the collector directly.
ProgressCallback = Callable[[str, dict[str, Any]], None]

# Sensor fields we expect to try to collect; used to report which ones were
# unsupported (all-null) as an explicit limitation rather than a blank chart.
TRACKED_SENSOR_FIELDS = [
    "temperature_c",
    "gpu_utilization_pct",
    "memory_controller_pct",
    "power_draw_w",
    "power_limit_w",
    "graphics_clock_mhz",
    "memory_clock_mhz",
    "fan_speed_pct",
    "encoder_utilization_pct",
    "decoder_utilization_pct",
    "throttle_reasons_active",
]


class _SensorSampler:
    """Samples a collector on a background thread until stopped."""

    def __init__(
        self,
        collector: GpuCollector,
        gpu_index: int,
        interval: float,
        on_sample: Callable[[SensorSnapshot], None] | None = None,
    ):
        self._collector = collector
        self._gpu_index = gpu_index
        self._interval = interval
        self._on_sample = on_sample
        self._stop = threading.Event()
        self._samples: list[SensorSnapshot] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _record(self) -> None:
        try:
            snapshot = self._collector.snapshot(self._gpu_index)
        except CollectorError:
            return
        self._samples.append(snapshot)
        if self._on_sample is not None:
            self._on_sample(snapshot)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._record()
            self._stop.wait(self._interval)

    def start(self) -> None:
        # Guarantee at least one sample even for very short workloads.
        self._record()
        self._thread.start()

    def stop(self) -> list[SensorSnapshot]:
        self._stop.set()
        self._thread.join(timeout=5.0)
        return self._samples


class MeasurementOrchestrator:
    def __init__(
        self,
        collector: GpuCollector,
        runner: GpuWorkloadRunner,
        *,
        sample_interval: float = 0.25,
        diagnostics: DiagnosticEngine | None = None,
    ):
        self.collector = collector
        self.runner = runner
        self.sample_interval = sample_interval
        self.diagnostics = diagnostics or DiagnosticEngine()

    def validate(
        self,
        spec: WorkloadSpec,
        gpu_index: int,
        *,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ValidationResult:
        def emit(event: str, payload: dict[str, Any]) -> None:
            if progress is not None:
                progress(event, payload)

        def emit_stage(name: str) -> None:
            emit("stage", {"name": name})

        started_at = datetime.now().astimezone()
        emit_stage("precheck")
        device = self.collector.static_info(gpu_index)  # raises if index missing
        environment = self._environment()

        sampler = _SensorSampler(
            self.collector,
            gpu_index,
            self.sample_interval,
            on_sample=lambda snapshot: emit("sample", dict(snapshot.values)),
        )
        emit_stage("workload")
        sampler.start()
        try:
            workload = self.runner.run(
                spec,
                gpu_index,
                cancel_check=(cancel_event.is_set if cancel_event is not None else None),
            )
        finally:
            samples = sampler.stop()

        emit_stage("diagnose")

        telemetry_summary = summarize_snapshots(samples)
        findings = self.diagnostics.diagnose(samples, workload)

        # Downgrade a nominally-valid result to inconclusive when diagnostics
        # judged the workload itself insufficient (low utilization / too short).
        if workload.reliability == "valid" and any(
            finding.category == "workload" for finding in findings
        ):
            workload.reliability = "inconclusive"
            workload.reason = workload.reason or "workload did not meet validity thresholds"

        performance = {
            "achieved_tflops": workload.achieved_tflops,
            "reliability": workload.reliability,
            "theoretical_peak_tflops": None,
            "theoretical_peak_source": "not_available",
            "peak_utilization_pct": None,
            "peak_utilization_status": "not_comparable",
        }
        # "사양 대비 %" — only when the model has a documented theoretical peak and
        # the measurement is valid; otherwise it stays not_comparable (brief §5).
        peak, source = theoretical_peak_tflops(device.get("name"), spec.dtype)
        if peak and workload.achieved_tflops and workload.reliability == "valid":
            pct = round(workload.achieved_tflops / peak * 100, 1)
            low, high = FP32_GEMM_NORMAL_RANGE_PCT
            performance["theoretical_peak_tflops"] = peak
            performance["theoretical_peak_source"] = source
            performance["peak_utilization_pct"] = pct
            performance["peak_utilization_status"] = "ok"
            # Rough guide for the default FP32 GEMM protocol only (see reference).
            if spec.name == WorkloadSpec().name and spec.dtype == "float32":
                performance["normal_range_pct"] = [low, high]
                performance["within_normal_range"] = pct >= low

        emit_stage("done")
        finished_at = datetime.now().astimezone()
        return ValidationResult(
            started_at=started_at,
            finished_at=finished_at,
            device=device,
            environment=environment,
            workload=workload,
            samples=samples,
            telemetry_summary=telemetry_summary,
            performance=performance,
            findings=findings,
            limitations=self._limitations(samples, workload, performance),
            protocol_id=protocol_id(spec),
        )

    def _environment(self) -> dict[str, object]:
        environment: dict[str, object] = dict(self.collector.environment())
        environment["collector_provider"] = self.collector.provider_name
        environment["workload_backend"] = self.runner.backend_name
        try:
            import torch

            environment["torch_version"] = torch.__version__
            environment["cuda_version"] = getattr(torch.version, "cuda", None)
        except ImportError:
            environment["torch_version"] = None
            environment["cuda_version"] = None
        return environment

    def _limitations(self, samples, workload, performance) -> list[str]:
        limitations = [
            "정적 벤치마크 CSV는 참고값이며 현재 장비의 측정값이 아닙니다.",
            "이 결과는 검사 시점의 소프트웨어와 환경에서 관찰된 상태만 설명합니다.",
        ]
        # Only note the missing '사양 대비 %' when we actually could not compute it
        # (unknown model / non-FP32 / invalid run). If it was computed, this line
        # would contradict the on-screen percentage.
        if performance.get("peak_utilization_status") != "ok":
            limitations.insert(
                0,
                "이 GPU 모델의 이론 성능(theoretical peak) 참고값이 없어 '사양 대비 %'(peak_utilization)를 계산하지 않았습니다 (not_comparable).",
            )

        unsupported = [
            field
            for field in TRACKED_SENSOR_FIELDS
            if not any(sample.values.get(field) is not None for sample in samples)
        ]
        if unsupported:
            limitations.append(
                "지원되지 않거나 수집되지 않은 센서: " + ", ".join(unsupported)
            )

        if workload.backend == "fake" or not getattr(self.runner, "is_available", lambda: True)():
            limitations.append(
                "실제 GPU workload backend가 없어 achieved TFLOPS는 실제 측정값이 아닙니다."
            )
        if workload.reliability != "valid":
            limitations.append(
                "측정 상태가 valid가 아니므로 CPU/host 영향이 배제되지 않았습니다."
            )
        return limitations
