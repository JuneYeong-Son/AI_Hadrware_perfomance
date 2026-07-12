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
        return SensorSnapshot(datetime.now().astimezone(), gpu_index, values)

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
