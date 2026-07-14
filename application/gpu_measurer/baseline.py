"""Baseline storage and history.

The goal of this stage is not a comparison algorithm; it is to accumulate
reproducible records so a future measurement *can* be compared. A delta is only
produced when the two records share the same device identity, protocol, dtype,
shape, and comparable driver/runtime, and both are valid. Otherwise the history
is returned with an explicit "not comparable" reason and no invented percentage.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ValidationResult
from .serialization import finding_to_dict, workload_to_dict

IDENTITY_KEYS = [
    "name",
    "uuid",
    "pci.bus_id",
    "driver_version",
    "vbios_version",
    "memory.total",
]


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value) or "unknown"


def _identity(device: dict[str, str]) -> dict[str, str | None]:
    return {key: device.get(key) for key in IDENTITY_KEYS}


class BaselineStore:
    """File-backed baseline records grouped by GPU UUID."""

    def __init__(self, root: Path):
        self.root = root

    def _group_dir(self, gpu_uuid: str) -> Path:
        return self.root / _sanitize(gpu_uuid)

    def save(self, result: ValidationResult) -> dict[str, Any]:
        gpu_uuid = result.device.get("uuid") or "unknown"
        record = {
            "baseline_id": uuid.uuid4().hex,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "gpu_identity": _identity(result.device),
            "protocol_id": result.protocol_id,
            "workload": workload_to_dict(result.workload),
            "achieved_tflops": result.workload.achieved_tflops,
            "telemetry_summary": result.telemetry_summary,
            "findings": [finding_to_dict(finding) for finding in result.findings],
            "environment": {
                "driver_version": result.device.get("driver_version"),
                "vbios_version": result.device.get("vbios_version"),
                "workload_backend": result.environment.get("workload_backend"),
                "torch_version": result.environment.get("torch_version"),
                "cuda_version": result.environment.get("cuda_version"),
            },
        }
        group = self._group_dir(gpu_uuid)
        group.mkdir(parents=True, exist_ok=True)
        stamp = record["created_at"].replace(":", "").replace("-", "")
        path = group / f"{result.protocol_id}-{stamp}-{record['baseline_id'][:8]}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        record["_path"] = str(path)
        return record

    def all_records(self) -> list[dict[str, Any]]:
        """Every saved baseline across all GPUs (the local results database)."""
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("*/*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return records

    def load_history(self, gpu_uuid: str) -> list[dict[str, Any]]:
        group = self._group_dir(gpu_uuid)
        if not group.exists():
            return []
        records = []
        for path in group.glob("*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        records.sort(key=lambda item: item.get("created_at", ""))
        return records


def _comparable(previous: dict[str, Any], latest: dict[str, Any]) -> tuple[bool, str | None]:
    if previous.get("protocol_id") != latest.get("protocol_id"):
        return False, "protocol_id가 다릅니다"
    prev_wl = previous.get("workload", {})
    late_wl = latest.get("workload", {})
    if prev_wl.get("dtype") != late_wl.get("dtype"):
        return False, "dtype가 다릅니다"
    if prev_wl.get("shape") != late_wl.get("shape"):
        return False, "shape/configuration이 다릅니다"
    if prev_wl.get("reliability") != "valid" or late_wl.get("reliability") != "valid":
        return False, "유효(valid) 측정이 아닙니다"
    prev_driver = previous.get("gpu_identity", {}).get("driver_version")
    late_driver = latest.get("gpu_identity", {}).get("driver_version")
    if prev_driver != late_driver:
        return False, "driver/runtime 조건이 다릅니다"
    return True, None


def percent_vs_first(
    records: list[dict[str, Any]],
    *,
    protocol_id: str,
    dtype: str,
    shape: dict[str, int],
    achieved_tflops: float | None,
) -> dict[str, Any]:
    """Compare a current measurement to the *first* comparable saved baseline.

    Records are oldest-first. Returns ``available=False`` (never an invented
    number) when there is no comparable earlier baseline.
    """
    if not isinstance(achieved_tflops, (int, float)):
        return {"available": False}
    for record in records:
        workload = record.get("workload", {})
        first_tflops = record.get("achieved_tflops")
        if (
            record.get("protocol_id") == protocol_id
            and workload.get("dtype") == dtype
            and workload.get("shape") == shape
            and workload.get("reliability") == "valid"
            and isinstance(first_tflops, (int, float))
            and first_tflops > 0
        ):
            return {
                "available": True,
                "first_tflops": round(first_tflops, 3),
                "first_date": (record.get("created_at") or "")[:10],
                "percent": round(achieved_tflops / first_tflops * 100),
            }
    return {"available": False}


def compare_models(
    records: list[dict[str, Any]], *, protocol_id: str | None = None
) -> dict[str, Any]:
    """Cross-model comparison, restricted to one measurement protocol.

    Only same-protocol/dtype/size results are compared (brief §4.3), so achieved
    TFLOPS and per-iteration time are apples-to-apples. This is a fair ordering,
    not a blended value score or price ranking (those stay out of scope, §7).
    """
    valid = [
        record
        for record in records
        if record.get("workload", {}).get("reliability") == "valid"
        and isinstance(record.get("achieved_tflops"), (int, float))
    ]
    if not valid:
        return {"available": False, "protocol_id": None, "entries": []}

    if protocol_id is None:
        counts: dict[str, int] = {}
        for record in valid:
            pid = record.get("protocol_id")
            counts[pid] = counts.get(pid, 0) + 1
        protocol_id = max(counts, key=counts.get)

    subset = [record for record in valid if record.get("protocol_id") == protocol_id]

    best: dict[str, dict[str, Any]] = {}
    for record in subset:
        name = record.get("gpu_identity", {}).get("name") or "알 수 없음"
        if name not in best or record["achieved_tflops"] > best[name]["achieved_tflops"]:
            best[name] = record

    entries = []
    for name, record in best.items():
        workload = record.get("workload", {})
        iters = workload.get("measured_iterations") or 0
        elapsed = workload.get("elapsed_seconds")
        per_iter_ms = round(elapsed / iters * 1000, 3) if elapsed and iters else None
        entries.append(
            {
                "name": name,
                "achieved_tflops": round(record["achieved_tflops"], 2),
                "per_iter_ms": per_iter_ms,
                "measured_at": (record.get("created_at") or "")[:10],
            }
        )
    entries.sort(key=lambda item: item["achieved_tflops"], reverse=True)
    sample_workload = subset[0].get("workload", {})
    return {
        "available": True,
        "protocol_id": protocol_id,
        "dtype": sample_workload.get("dtype"),
        "size": sample_workload.get("shape", {}).get("m"),
        "entries": entries,
    }


def build_history_view(records: list[dict[str, Any]]) -> dict[str, Any]:
    """History for one device, with a delta only when truly comparable."""
    if not records:
        return {
            "record_count": 0,
            "records": [],
            "comparison": {
                "comparable": False,
                "reason": "아직 비교 가능한 기준선이 없습니다.",
                "delta": None,
            },
        }

    comparison: dict[str, Any] = {
        "comparable": False,
        "reason": "비교하려면 같은 프로토콜의 측정이 2회 이상 필요합니다.",
        "delta": None,
    }
    if len(records) >= 2:
        previous, latest = records[-2], records[-1]
        comparable, reason = _comparable(previous, latest)
        if comparable:
            prev_tflops = previous.get("achieved_tflops")
            late_tflops = latest.get("achieved_tflops")
            delta = None
            if isinstance(prev_tflops, (int, float)) and isinstance(late_tflops, (int, float)) and prev_tflops:
                delta = {
                    "previous_tflops": round(prev_tflops, 4),
                    "latest_tflops": round(late_tflops, 4),
                    "absolute_tflops": round(late_tflops - prev_tflops, 4),
                    "relative_pct": round((late_tflops - prev_tflops) / prev_tflops * 100, 2),
                    "protocol_id": latest.get("protocol_id"),
                }
            comparison = {"comparable": True, "reason": None, "delta": delta}
        else:
            comparison = {"comparable": False, "reason": reason, "delta": None}

    return {
        "record_count": len(records),
        "records": records,
        "comparison": comparison,
    }
