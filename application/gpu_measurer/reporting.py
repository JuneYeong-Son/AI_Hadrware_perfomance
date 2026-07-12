from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .benchmarks import BenchmarkRepository
from .collector import GpuCollector
from .models import MeasurementResult, SensorSnapshot


SUMMARY_FIELDS = [
    "temperature_c",
    "gpu_utilization_pct",
    "memory_controller_pct",
    "memory_used_mib",
    "power_draw_w",
    "graphics_clock_mhz",
    "memory_clock_mhz",
]


def summarize_snapshots(samples: list[SensorSnapshot]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for field in SUMMARY_FIELDS:
        values = [
            float(sample.values[field])
            for sample in samples
            if isinstance(sample.values.get(field), (int, float))
        ]
        if not values:
            continue
        summary[field] = {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }
    return summary


def run_measurement(
    collector: GpuCollector,
    benchmarks: BenchmarkRepository,
    gpu_index: int,
    duration_seconds: float = 5.0,
    interval_seconds: float = 1.0,
) -> MeasurementResult:
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration and interval must be positive")

    started_at = datetime.now().astimezone()
    gpu = collector.static_info(gpu_index)
    samples = []
    started_clock = time.monotonic()
    next_sample_at = 0.0
    while True:
        samples.append(collector.snapshot(gpu_index))
        elapsed = time.monotonic() - started_clock
        if elapsed >= duration_seconds:
            break
        next_sample_at = min(duration_seconds, next_sample_at + interval_seconds)
        time.sleep(max(0.0, next_sample_at - elapsed))
    finished_at = datetime.now().astimezone()
    return MeasurementResult(
        started_at=started_at,
        finished_at=finished_at,
        gpu=gpu,
        benchmark=benchmarks.match(gpu["name"]),
        samples=samples,
        summary=summarize_snapshots(samples),
        environment=collector.environment(),
    )


def write_log(result: MeasurementResult, output: Path, author: str = "Codex") -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# GPU Measurer execution report",
        "",
        "[report]",
        f"author={author}",
        f"started_at={result.started_at.isoformat(timespec='seconds')}",
        f"finished_at={result.finished_at.isoformat(timespec='seconds')}",
        f"duration_seconds={(result.finished_at - result.started_at).total_seconds():.2f}",
        f"sample_count={len(result.samples)}",
        "",
        "[gpu]",
    ]
    for key in [
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
    ]:
        value = "[redacted]" if key == "uuid" else result.gpu.get(key, "N/A")
        lines.append(f"{key}={value}")

    lines.extend(["", "[benchmark_reference]"])
    lines.append(f"exact_match={str(result.benchmark.exact).lower()}")
    if result.benchmark.passmark:
        for key, value in result.benchmark.passmark.items():
            lines.append(f"passmark.{key}={value}")
    if result.benchmark.compute:
        for key, value in result.benchmark.compute.items():
            lines.append(f"compute.{key}={value}")
    if result.benchmark.suggestions:
        for index, (name, score) in enumerate(result.benchmark.suggestions, start=1):
            lines.append(f"nearest.{index}={name} ({score:.3f})")

    lines.extend(["", "[sensor_summary]"])
    for field, stats in result.summary.items():
        lines.append(
            f"{field}=min:{stats['min']:.2f},avg:{stats['avg']:.2f},max:{stats['max']:.2f}"
        )

    lines.extend(["", "[environment]"])
    for key, value in result.environment.items():
        if key == "hostname":
            value = "[redacted]"
        lines.append(f"{key}={value}")

    lines.extend(["", "[samples]"])
    sample_fields = ["timestamp", *SUMMARY_FIELDS, "performance_state"]
    lines.append(",".join(sample_fields))
    for sample in result.samples:
        values = [sample.timestamp.isoformat(timespec="seconds")]
        values.extend(str(sample.values.get(field, "")) for field in sample_fields[1:])
        lines.append(",".join(values))

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
