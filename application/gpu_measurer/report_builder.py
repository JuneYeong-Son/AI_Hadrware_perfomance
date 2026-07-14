"""Human-readable reports built from a ValidationResult.

Two audiences, per the brief: an internal operational report with full detail,
and an external/shared report that masks sensitive identifiers and never reads
like a manufacturer certification.
"""

from __future__ import annotations

from typing import Any

from .models import ValidationResult

RELIABILITY_LABEL = {
    "valid": "검사 통과",
    "inconclusive": "판정 불가",
    "failed": "검사 실패",
}

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def verdict(result: ValidationResult) -> str:
    """Overall verdict shown first: 통과 / 주의 / 판정 불가 / 실패."""
    if result.workload.reliability == "failed":
        return "실패"
    if result.workload.reliability == "inconclusive":
        return "판정 불가"
    severities = {finding.severity for finding in result.findings}
    if "critical" in severities:
        return "주의"
    if "warning" in severities:
        return "주의"
    return "통과"


def _fmt(value: Any) -> str:
    return "확인 불가" if value is None else str(value)


def build_text_report(result: ValidationResult) -> str:
    workload = result.workload
    lines = [
        "# 통제된 workload 기반 GPU 성능 검사 리포트 (내부용)",
        "이 결과는 검사 시점의 소프트웨어와 환경에서 관찰된 상태를 설명합니다.",
        "",
        "[요약]",
        f"판정={verdict(result)}",
        f"측정 신뢰성={RELIABILITY_LABEL.get(workload.reliability, workload.reliability)}",
        f"achieved_tflops={_fmt(round(workload.achieved_tflops, 3) if workload.achieved_tflops else None)}",
        f"검사 시각={result.started_at.isoformat(timespec='seconds')}",
        "",
        "[장치]",
    ]
    for key in ["index", "name", "driver_version", "vbios_version", "compute_cap", "memory.total"]:
        value = "[redacted]" if key == "uuid" else result.device.get(key, "N/A")
        lines.append(f"{key}={value}")

    lines += ["", "[workload]"]
    lines.append(f"name={workload.workload_name}")
    lines.append(f"backend={workload.backend}")
    lines.append(f"dtype={workload.dtype}")
    lines.append(f"shape={workload.shape}")
    lines.append(f"warmup_iterations={workload.warmup_iterations}")
    lines.append(f"measured_iterations={workload.measured_iterations}")
    lines.append(f"elapsed_seconds={_fmt(workload.elapsed_seconds)}")
    lines.append(f"operation_count={_fmt(workload.operation_count)}")
    lines.append(f"flop_convention={workload.flop_convention}")
    lines.append(f"timing_source={workload.timing_source}")
    lines.append(f"protocol_id={result.protocol_id}")

    lines += ["", "[telemetry_summary]"]
    for field, stats in result.telemetry_summary.items():
        lines.append(
            f"{field}=min:{stats['min']:.2f},avg:{stats['avg']:.2f},max:{stats['max']:.2f}"
        )

    lines += ["", "[findings]"]
    for finding in sorted(result.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9)):
        lines.append(
            f"- [{finding.severity}/{finding.confidence}] ({finding.category}) {finding.title}"
        )
        lines.append(f"  근거={finding.evidence}")
        lines.append(f"  권장={finding.recommendation}")

    lines += ["", "[limitations]"]
    lines.extend(f"- {item}" for item in result.limitations)
    lines.append("")
    return "\n".join(lines)


def build_shared_report(result: ValidationResult) -> dict[str, Any]:
    """External/shared report: masked identity, observed facts only."""
    workload = result.workload
    return {
        "title": "통제된 workload 기반 GPU 성능 검사 리포트",
        "disclaimer": "이 결과는 검사 시점의 소프트웨어와 환경에서 관찰된 상태를 설명하며, 제조사 인증이나 절대적 정상 보증이 아닙니다.",
        "device": {
            "name": result.device.get("name"),
            "vram_total": result.device.get("memory.total"),
            "driver_version": result.device.get("driver_version"),
            "compute_cap": result.device.get("compute_cap"),
        },
        "measured_at": result.started_at.isoformat(timespec="seconds"),
        "workload": {
            "name": workload.workload_name,
            "dtype": workload.dtype,
            "shape": workload.shape,
            "timing_source": workload.timing_source,
        },
        "achieved_tflops": (
            round(workload.achieved_tflops, 3) if workload.achieved_tflops else None
        ),
        "verdict": verdict(result),
        "reliability": workload.reliability,
        "observed_causes": [
            {"title": f.title, "severity": f.severity, "confidence": f.confidence}
            for f in result.findings
            if f.category != "none"
        ],
        "limitations": result.limitations,
    }
