from __future__ import annotations

from typing import Any

from .models import (
    BenchmarkMatch,
    Finding,
    MeasurementResult,
    SensorSnapshot,
    ValidationResult,
    WorkloadResult,
)


SCHEMA_VERSION = "1.0"
SENSITIVE_KEYS = {"uuid", "hostname"}


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in SENSITIVE_KEYS else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    return value


def benchmark_to_dict(benchmark: BenchmarkMatch) -> dict[str, Any]:
    return {
        "requested_name": benchmark.requested_name,
        "exact_match": benchmark.exact,
        "passmark": benchmark.passmark,
        "compute": benchmark.compute,
        "suggestions": [
            {"name": name, "similarity": round(score, 6)}
            for name, score in benchmark.suggestions
        ],
    }


def snapshot_to_dict(snapshot: SensorSnapshot) -> dict[str, Any]:
    return {
        "timestamp": snapshot.timestamp.isoformat(timespec="seconds"),
        "gpu_index": snapshot.gpu_index,
        "values": snapshot.values,
    }


def measurement_to_dict(result: MeasurementResult) -> dict[str, Any]:
    return {
        "started_at": result.started_at.isoformat(timespec="seconds"),
        "finished_at": result.finished_at.isoformat(timespec="seconds"),
        "duration_seconds": round(
            (result.finished_at - result.started_at).total_seconds(), 3
        ),
        "gpu": result.gpu,
        "benchmark": benchmark_to_dict(result.benchmark),
        "summary": result.summary,
        "environment": result.environment,
        "samples": [snapshot_to_dict(sample) for sample in result.samples],
    }


def workload_to_dict(workload: WorkloadResult) -> dict[str, Any]:
    return {
        "workload_name": workload.workload_name,
        "backend": workload.backend,
        "dtype": workload.dtype,
        "shape": workload.shape,
        "warmup_iterations": workload.warmup_iterations,
        "measured_iterations": workload.measured_iterations,
        "elapsed_seconds": (
            round(workload.elapsed_seconds, 6)
            if workload.elapsed_seconds is not None
            else None
        ),
        "operation_count": workload.operation_count,
        "achieved_tflops": (
            round(workload.achieved_tflops, 4)
            if workload.achieved_tflops is not None
            else None
        ),
        "flop_convention": workload.flop_convention,
        "timing_source": workload.timing_source,
        "device_name": workload.device_name,
        "reliability": workload.reliability,
        "reason": workload.reason,
    }


def finding_to_dict(finding: Finding) -> dict[str, Any]:
    return {
        "category": finding.category,
        "severity": finding.severity,
        "title": finding.title,
        "evidence": finding.evidence,
        "confidence": finding.confidence,
        "recommendation": finding.recommendation,
    }


def validation_to_dict(result: ValidationResult) -> dict[str, Any]:
    """The response areas the frontend/CLI/LLM consume directly."""
    return {
        "device": result.device,
        "environment": result.environment,
        "workload": workload_to_dict(result.workload),
        "performance": result.performance,
        "telemetry_summary": result.telemetry_summary,
        "findings": [finding_to_dict(finding) for finding in result.findings],
        "baseline": result.baseline,
        "limitations": result.limitations,
        "protocol_id": result.protocol_id,
        "started_at": result.started_at.isoformat(timespec="seconds"),
        "finished_at": result.finished_at.isoformat(timespec="seconds"),
        "samples": [snapshot_to_dict(sample) for sample in result.samples],
    }


def response_envelope(
    data: Any,
    provider: str,
    *,
    ok: bool = True,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "provider": provider,
        "data": data,
        "error": error,
    }
