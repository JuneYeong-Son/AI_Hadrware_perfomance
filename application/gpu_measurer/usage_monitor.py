"""Cumulative usage observations and honest 'abuse' indicators.

Two honesty boundaries drive this module:

1. nvidia-smi exposes no lifetime throttle/usage counters (and consumer GeForce
   cards have no ECC counters). So we can only accumulate what *this app observed
   while it was running*. The persisted log therefore says "이 앱이 관찰한 이후",
   never "GPU 제조 이후".

2. Mining history, exact age, and physical wear cannot be proven from sensors
   (brief §7/§12 forbid asserting them). ``abuse_indicators`` returns observable
   facts with an explicit "단정 아님" note — never a verdict.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value) or "unknown"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class UsageMonitor:
    """Per-GPU persistent log of observed throttling and peak temperature."""

    def __init__(self, root: Path):
        self.root = root

    def _path(self, gpu_uuid: str) -> Path:
        return self.root / f"{_sanitize(gpu_uuid)}.json"

    def load(self, gpu_uuid: str) -> dict[str, Any]:
        path = self._path(gpu_uuid)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def record(self, gpu_uuid: str, values: dict[str, Any]) -> None:
        """Fold one sensor snapshot into the cumulative log."""
        data = self.load(gpu_uuid)
        now = _now_iso()
        data.setdefault("gpu_uuid", gpu_uuid)
        data.setdefault("first_observed_at", now)
        data["last_observed_at"] = now

        throttle = values.get("throttle_reasons_active")
        if throttle is not None:
            data["supported"] = True
            data["observation_count"] = data.get("observation_count", 0) + 1
            if isinstance(throttle, str) and throttle not in ("", "none"):
                data["throttled_count"] = data.get("throttled_count", 0) + 1
                reasons = data.setdefault("reason_counts", {})
                for reason in throttle.split(","):
                    reasons[reason] = reasons.get(reason, 0) + 1
        else:
            data.setdefault("supported", data.get("supported", False))

        temp = values.get("temperature_c")
        if isinstance(temp, (int, float)):
            data["peak_temperature_c"] = max(data.get("peak_temperature_c") or 0.0, float(temp))

        self.root.mkdir(parents=True, exist_ok=True)
        self._path(gpu_uuid).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def summary(self, gpu_uuid: str) -> dict[str, Any]:
        data = self.load(gpu_uuid)
        observations = data.get("observation_count", 0)
        throttled = data.get("throttled_count", 0)
        reason_counts = data.get("reason_counts", {})
        # Thermal throttle is the concerning kind; power-cap under load is normal.
        thermal = sum(count for name, count in reason_counts.items() if "thermal" in name)
        return {
            "has_data": bool(data),
            "supported": data.get("supported", False),
            "first_observed_at": data.get("first_observed_at"),
            "last_observed_at": data.get("last_observed_at"),
            "observation_count": observations,
            "throttled_count": throttled,
            "thermal_count": thermal,
            "throttle_ratio_pct": round(throttled / observations * 100, 1) if observations else None,
            "reason_counts": reason_counts,
            "peak_temperature_c": data.get("peak_temperature_c"),
        }


def _numeric(telemetry: dict[str, Any], field: str, agg: str) -> float | None:
    stats = telemetry.get(field)
    if not stats:
        return None
    value = stats.get(agg)
    return float(value) if isinstance(value, (int, float)) else None


def abuse_indicators(
    *,
    findings: list[dict[str, Any]],
    telemetry: dict[str, Any],
    performance: dict[str, Any],
    rated_max_graphics_clock: float | None,
    usage: dict[str, Any],
) -> dict[str, Any]:
    """Observable-only indicators for a used-GPU health check.

    Returns a list of indicators, each with a status of "ok" (관찰상 양호),
    "watch" (확인 권장), or "info" (참고). Never concludes mining/age.
    """
    indicators: list[dict[str, Any]] = []
    categories = {f.get("category") for f in findings}

    # 1) 발열 / 열 쓰로틀
    peak_temp = _numeric(telemetry, "temperature_c", "max")
    thermal = "thermal" in categories or "cooling" in categories
    indicators.append(
        {
            "label": "발열·냉각",
            "value": f"검사 중 최고 {peak_temp:.0f}°C" if peak_temp is not None else "확인 불가",
            "status": "watch" if thermal else "ok",
            "detail": "고온·열 쓰로틀이 관찰되면 냉각 열화(장기 혹사 가능성)의 참고 신호예요."
            if thermal
            else "검사 중 열로 인한 성능 제한은 관찰되지 않았어요.",
        }
    )

    # 2) 부스트 클럭 유지
    clock_max = _numeric(telemetry, "graphics_clock_mhz", "max")
    if clock_max is not None and rated_max_graphics_clock:
        reached = clock_max >= rated_max_graphics_clock * 0.9
        power_or_thermal = bool(categories & {"thermal", "power", "cooling"})
        indicators.append(
            {
                "label": "부스트 클럭 유지",
                "value": f"검사 중 최고 {clock_max:.0f} / 정격 {rated_max_graphics_clock:.0f} MHz",
                "status": "ok" if reached else ("info" if power_or_thermal else "watch"),
                "detail": "정격 부스트에 근접했어요." if reached else "정격 부스트에 못 미쳤어요 (냉각·전원 또는 열화 참고).",
                "tooltip": (
                    "부스트 클럭 유지란?<br><br>"
                    "GPU는 부하가 걸리면 ‘부스트 클럭’까지 속도를<br>"
                    "끌어올려요. 검사(부하) 중 정격 부스트에<br>"
                    "근접하면 정상이에요.<br><br>"
                    "정격보다 많이 낮으면 → 전력 제한(고부하에서<br>"
                    "정상)일 수도, 냉각 열화 등 다른 원인일 수도<br>"
                    "있어 <b>추적이 필요한 참고 신호</b>예요."
                ),
            }
        )

    # 3) 성능 (사양 대비)
    if performance.get("peak_utilization_status") == "ok":
        pct = performance.get("peak_utilization_pct")
        within = performance.get("within_normal_range")
        indicators.append(
            {
                "label": "성능 (사양 대비)",
                "value": f"{pct:.0f}%" if pct is not None else "확인 불가",
                "status": "ok" if within else "watch",
                "detail": "이 검사의 정상 범위 안이에요." if within else "정상 범위보다 낮아요 (재검사·상태 확인 권장).",
            }
        )

    # 4) 누적 쓰로틀 (이 앱 관찰 이후) — 열 쓰로틀 위주로 판단.
    if usage.get("has_data") and usage.get("observation_count"):
        thermal = usage.get("thermal_count", 0)
        if thermal > 0:
            status = "watch"
            detail = f"이 중 온도(열) 쓰로틀 {thermal}회 관찰 — 냉각 상태 확인 권장."
        else:
            status = "info"
            detail = "대부분 전력 제한이라 고부하에서 정상일 수 있어요. 열 쓰로틀은 관찰되지 않았어요."
        indicators.append(
            {
                "label": "누적 쓰로틀 (이 앱 관찰 이후)",
                "value": f"{usage['throttled_count']}/{usage['observation_count']}회"
                + (f" · 열 {thermal}회" if thermal else ""),
                "status": status,
                "detail": detail,
            }
        )

    note = (
        "센서만으로는 채굴 이력이나 사용 기간을 확인할 수 없어요. "
        "아래는 참고 관찰값이며, 최종 판단은 사용자 몫입니다."
    )
    return {"note": note, "indicators": indicators}
