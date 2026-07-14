from __future__ import annotations

import csv
import platform
import shutil
import subprocess
from datetime import datetime
from io import StringIO
from typing import Protocol

from .models import GpuDevice, SensorSnapshot


class CollectorError(RuntimeError):
    pass


class NvidiaSmiError(CollectorError):
    pass


class GpuCollector(Protocol):
    provider_name: str

    def is_available(self) -> bool: ...

    def list_devices(self) -> list[GpuDevice]: ...

    def static_info(self, gpu_index: int) -> dict[str, str]: ...

    def snapshot(self, gpu_index: int) -> SensorSnapshot: ...

    def environment(self) -> dict[str, str]: ...


IDENTITY_FIELDS = ["index", "name", "uuid"]

STATIC_FIELDS = [
    "index",
    "name",
    "uuid",
    "driver_version",
    "vbios_version",
    "pci.bus_id",
    "pci.device_id",
    "memory.total",
    "clocks.max.graphics",
    "clocks.max.memory",
    "compute_cap",
    "display_mode",
    "display_active",
    "compute_mode",
]

SENSOR_FIELDS = [
    "temperature.gpu",
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.free",
    "memory.total",
    "power.draw",
    "power.limit",
    "clocks.current.graphics",
    "clocks.current.memory",
    "pstate",
    "fan.speed",
    "utilization.encoder",
    "utilization.decoder",
]

SENSOR_ALIASES = {
    "temperature.gpu": "temperature_c",
    "utilization.gpu": "gpu_utilization_pct",
    "utilization.memory": "memory_controller_pct",
    "memory.used": "memory_used_mib",
    "memory.free": "memory_free_mib",
    "memory.total": "memory_total_mib",
    "power.draw": "power_draw_w",
    "power.limit": "power_limit_w",
    "clocks.current.graphics": "graphics_clock_mhz",
    "clocks.current.memory": "memory_clock_mhz",
    "pstate": "performance_state",
    "fan.speed": "fan_speed_pct",
    "utilization.encoder": "encoder_utilization_pct",
    "utilization.decoder": "decoder_utilization_pct",
}

# Best-effort fields queried separately: nvidia-smi renamed the throttle field
# across versions, and older drivers do not support it at all. A failure here
# must never break the core snapshot, so it is collected in its own call and
# falls back to ``None`` (never estimated).
THROTTLE_FIELD_CANDIDATES = [
    "clocks_event_reasons.active",
    "clocks_throttle_reasons.active",
]

# nvidia-smi active reasons bitmask (documented in nvml.h).
THROTTLE_REASON_BITS = [
    (0x0000000000000002, "applications_clocks_setting"),
    (0x0000000000000004, "sw_power_cap"),
    (0x0000000000000008, "hw_slowdown"),
    (0x0000000000000010, "sync_boost"),
    (0x0000000000000020, "sw_thermal_slowdown"),
    (0x0000000000000040, "hw_thermal_slowdown"),
    (0x0000000000000080, "hw_power_brake_slowdown"),
    (0x0000000000000100, "display_clock_setting"),
]


def decode_throttle_reasons(raw: str | None) -> list[str] | None:
    """Decode the active-throttle hex bitmask into reason names.

    Returns ``None`` when unsupported/unknown, an empty list when the GPU
    reported no active throttle reason (bitmask 0x0), and the list of active
    reasons otherwise.
    """

    if raw is None:
        return None
    text = raw.strip()
    if not text or text in {"[N/A]", "N/A", "Not Supported"}:
        return None
    try:
        mask = int(text, 16) if text.lower().startswith("0x") else int(text, 16)
    except ValueError:
        return None
    return [name for bit, name in THROTTLE_REASON_BITS if mask & bit]


def _creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_nvidia_smi(fields: list[str], gpu_index: int | None = None) -> list[dict[str, str]]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        raise NvidiaSmiError("nvidia-smi was not found. Install an NVIDIA display driver.")

    command = [
        executable,
        f"--query-gpu={','.join(fields)}",
        "--format=csv,noheader,nounits",
    ]
    if gpu_index is not None:
        command.insert(1, f"--id={gpu_index}")

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=_creation_flags(),
        timeout=10,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "nvidia-smi failed"
        raise NvidiaSmiError(message)

    rows = []
    reader = csv.reader(StringIO(completed.stdout))
    for values in reader:
        if not values:
            continue
        cleaned = [value.strip() for value in values]
        rows.append(dict(zip(fields, cleaned, strict=False)))
    return rows


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized in {"[N/A]", "N/A", "Not Supported"}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


class NvidiaCollector:
    provider_name = "nvidia-smi"

    @staticmethod
    def is_available() -> bool:
        return shutil.which("nvidia-smi") is not None

    def list_devices(self) -> list[GpuDevice]:
        devices = []
        for row in _run_nvidia_smi(IDENTITY_FIELDS):
            devices.append(
                GpuDevice(
                    index=int(row["index"]),
                    name=row["name"],
                    uuid=row["uuid"],
                )
            )
        return devices

    def static_info(self, gpu_index: int) -> dict[str, str]:
        rows = _run_nvidia_smi(STATIC_FIELDS, gpu_index)
        if not rows:
            raise NvidiaSmiError(f"GPU index {gpu_index} was not found")
        return rows[0]

    def snapshot(self, gpu_index: int) -> SensorSnapshot:
        rows = _run_nvidia_smi(SENSOR_FIELDS, gpu_index)
        if not rows:
            raise NvidiaSmiError(f"GPU index {gpu_index} was not found")

        values: dict[str, float | str | None] = {}
        for field, raw_value in rows[0].items():
            key = SENSOR_ALIASES[field]
            if field == "pstate":
                values[key] = None if raw_value in {"[N/A]", "N/A"} else raw_value
            else:
                values[key] = _number(raw_value)
        values["throttle_reasons_active"] = self._throttle_reasons(gpu_index)
        return SensorSnapshot(datetime.now().astimezone(), gpu_index, values)

    @staticmethod
    def _throttle_reasons(gpu_index: int) -> str | None:
        """Best-effort active throttle reasons; ``None`` if unsupported."""
        for field in THROTTLE_FIELD_CANDIDATES:
            try:
                rows = _run_nvidia_smi([field], gpu_index)
            except NvidiaSmiError:
                continue
            if not rows:
                continue
            reasons = decode_throttle_reasons(rows[0].get(field))
            if reasons is None:
                return None
            return ",".join(reasons) if reasons else "none"
        return None

    @staticmethod
    def environment() -> dict[str, str]:
        return {
            "os": platform.platform(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "hostname": platform.node(),
        }


class CollectorRegistry:
    def __init__(self, collectors: list[GpuCollector] | None = None):
        self.collectors = collectors or [NvidiaCollector()]

    def available(self) -> list[GpuCollector]:
        return [collector for collector in self.collectors if collector.is_available()]

    def default(self) -> GpuCollector:
        for collector in self.available():
            try:
                if collector.list_devices():
                    return collector
            except CollectorError:
                continue
        raise CollectorError("No supported GPU collector is available")


def get_default_collector() -> GpuCollector:
    return CollectorRegistry().default()
