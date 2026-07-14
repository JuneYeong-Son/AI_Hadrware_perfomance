"""Rule-based diagnosis of a controlled measurement.

The engine never says only "it is slow". Every finding carries the observed
evidence, a severity, a confidence, and a recommendation. Cause attribution is
probabilistic: physical failure, mining history, or age are never asserted from
sensors alone.
"""

from __future__ import annotations

from .models import Finding, SensorSnapshot, WorkloadResult

# Thresholds for the initial rule set. They are intentionally conservative so a
# finding means "worth a human look", not a hard verdict.
HIGH_TEMPERATURE_C = 80.0
SUSTAINED_HIGH_TEMPERATURE_C = 83.0
CLOCK_DROP_RATIO = 0.95  # current < 95% of the run's own max => "dropped"
POWER_LIMIT_RATIO = 0.97  # draw >= 97% of limit => power capped
MIN_VALID_UTILIZATION_PCT = 50.0
MIN_VALID_ELAPSED_S = 0.2


def _numeric(samples: list[SensorSnapshot], field: str) -> list[float]:
    return [
        float(sample.values[field])
        for sample in samples
        if isinstance(sample.values.get(field), (int, float))
    ]


def _throttle_counts(samples: list[SensorSnapshot]) -> tuple[int, int]:
    """(thermal reason samples, any active throttle samples)."""
    thermal = 0
    active = 0
    for sample in samples:
        raw = sample.values.get("throttle_reasons_active")
        if not isinstance(raw, str) or raw in {"", "none"}:
            continue
        active += 1
        if "thermal" in raw:
            thermal += 1
    return thermal, active


class DiagnosticEngine:
    def diagnose(
        self,
        samples: list[SensorSnapshot],
        workload: WorkloadResult,
    ) -> list[Finding]:
        findings: list[Finding] = []

        if workload.reliability == "failed":
            findings.append(
                Finding(
                    category="driver",
                    severity="critical",
                    title="워크로드 실행이 실패했습니다",
                    evidence={"reason": workload.reason or "unknown"},
                    confidence="high",
                    recommendation="드라이버와 런타임(CUDA/PyTorch) 설치 상태를 확인하세요.",
                )
            )
            return findings

        findings.extend(self._workload_validity(samples, workload))
        findings.extend(self._thermal(samples))
        findings.extend(self._power(samples))

        if not findings:
            findings.append(
                Finding(
                    category="none",
                    severity="info",
                    title="측정 구간에서 이상 징후가 관찰되지 않았습니다",
                    evidence={},
                    confidence="medium",
                    recommendation="추가 조치가 필요하지 않습니다.",
                )
            )
        return findings

    def _workload_validity(
        self, samples: list[SensorSnapshot], workload: WorkloadResult
    ) -> list[Finding]:
        utilization = _numeric(samples, "gpu_utilization_pct")
        avg_util = sum(utilization) / len(utilization) if utilization else None
        elapsed = workload.elapsed_seconds or 0.0

        low_util = avg_util is not None and avg_util < MIN_VALID_UTILIZATION_PCT
        too_short = elapsed < MIN_VALID_ELAPSED_S
        if low_util or too_short:
            return [
                Finding(
                    category="workload",
                    severity="warning",
                    title="측정이 유효 조건을 충분히 만족하지 못했습니다",
                    evidence={
                        "gpu_utilization_avg_pct": round(avg_util, 1)
                        if avg_util is not None
                        else None,
                        "elapsed_seconds": round(elapsed, 4),
                        "min_valid_utilization_pct": MIN_VALID_UTILIZATION_PCT,
                        "min_valid_elapsed_s": MIN_VALID_ELAPSED_S,
                    },
                    confidence="medium",
                    recommendation="반복 횟수 또는 행렬 크기를 늘려 GPU 점유율과 측정 시간을 확보하세요.",
                )
            ]
        return []

    def _thermal(self, samples: list[SensorSnapshot]) -> list[Finding]:
        temps = _numeric(samples, "temperature_c")
        clocks = _numeric(samples, "graphics_clock_mhz")
        if not temps:
            return []

        temp_peak = max(temps)
        thermal_reason_samples, _ = _throttle_counts(samples)
        clock_min = min(clocks) if clocks else None
        clock_max = max(clocks) if clocks else None
        clock_dropped = (
            clock_min is not None
            and clock_max is not None
            and clock_max > 0
            and clock_min < clock_max * CLOCK_DROP_RATIO
        )
        drop_samples = (
            sum(1 for value in clocks if clock_max and value < clock_max * CLOCK_DROP_RATIO)
            if clock_max
            else 0
        )

        # High-confidence path: the driver itself reported a thermal throttle.
        if thermal_reason_samples > 0:
            return [
                Finding(
                    category="thermal",
                    severity="warning",
                    title="드라이버가 thermal throttle를 보고했습니다",
                    evidence={
                        "temperature_peak_c": temp_peak,
                        "graphics_clock_min_mhz": clock_min,
                        "throttle_samples": thermal_reason_samples,
                    },
                    confidence="high",
                    recommendation="냉각팬, 방열판, 써멀패드와 케이스 airflow를 점검하세요.",
                )
            ]

        # Inferred path: hot section coincides with a clock drop.
        if temp_peak >= HIGH_TEMPERATURE_C and clock_dropped:
            return [
                Finding(
                    category="thermal",
                    severity="warning",
                    title="고온 구간에서 graphics clock 하락이 관찰되었습니다",
                    evidence={
                        "temperature_peak_c": temp_peak,
                        "graphics_clock_min_mhz": clock_min,
                        "graphics_clock_max_mhz": clock_max,
                        "throttle_samples": drop_samples,
                    },
                    confidence="medium",
                    recommendation="냉각 상태와 케이스 airflow를 점검하세요. 반복 검사로 재현 여부를 확인하세요.",
                )
            ]

        if temp_peak >= SUSTAINED_HIGH_TEMPERATURE_C:
            return [
                Finding(
                    category="cooling",
                    severity="info",
                    title="측정 중 높은 온도가 관찰되었습니다",
                    evidence={"temperature_peak_c": temp_peak},
                    confidence="low",
                    recommendation="냉각 여유를 확인하세요. 단독으로는 결함 근거가 아닙니다.",
                )
            ]
        return []

    def _power(self, samples: list[SensorSnapshot]) -> list[Finding]:
        draws = _numeric(samples, "power_draw_w")
        limits = _numeric(samples, "power_limit_w")
        clocks = _numeric(samples, "graphics_clock_mhz")
        if not draws or not limits:
            return []

        draw_peak = max(draws)
        limit = max(limits)
        clock_max = max(clocks) if clocks else None
        clock_min = min(clocks) if clocks else None
        clock_dropped = (
            clock_min is not None
            and clock_max is not None
            and clock_max > 0
            and clock_min < clock_max * CLOCK_DROP_RATIO
        )
        if limit > 0 and draw_peak >= limit * POWER_LIMIT_RATIO and clock_dropped:
            return [
                Finding(
                    category="power",
                    severity="info",
                    title="전력 제한 부근에서 클럭이 제한되었습니다",
                    evidence={
                        "power_draw_peak_w": draw_peak,
                        "power_limit_w": limit,
                        "graphics_clock_min_mhz": clock_min,
                    },
                    confidence="medium",
                    recommendation="power limit 설정과 전원 공급 상태를 확인하세요. 정상 동작일 수 있습니다.",
                )
            ]
        return []
