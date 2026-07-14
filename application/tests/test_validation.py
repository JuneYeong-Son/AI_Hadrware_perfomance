from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


APPLICATION = Path(__file__).resolve().parents[1]
ROOT = APPLICATION.parent
sys.path.insert(0, str(APPLICATION))

from gpu_measurer.baseline import (
    BaselineStore,
    build_history_view,
    compare_models,
    percent_vs_first,
)
from gpu_measurer.benchmarks import BenchmarkRepository
from gpu_measurer.collector import decode_throttle_reasons
from gpu_measurer.diagnostics import DiagnosticEngine
from gpu_measurer.gpu_reference import theoretical_peak_tflops
from gpu_measurer.models import GpuDevice, SensorSnapshot, WorkloadSpec
from gpu_measurer.report_builder import verdict
from gpu_measurer.service import GpuMeasurementService
from gpu_measurer.usage_monitor import UsageMonitor, abuse_indicators
from gpu_measurer.workload import FakeWorkloadRunner, protocol_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeCollector:
    provider_name = "fake"

    def __init__(self, sensor_values: dict | None = None):
        self._sensor_values = sensor_values or {
            "temperature_c": 55.0,
            "gpu_utilization_pct": 96.0,
            "graphics_clock_mhz": 1900.0,
            "power_draw_w": 150.0,
            "power_limit_w": 200.0,
            "throttle_reasons_active": "none",
        }

    def is_available(self) -> bool:
        return True

    def list_devices(self) -> list[GpuDevice]:
        return [GpuDevice(0, "Fake GPU", "GPU-fake-uuid")]

    def static_info(self, gpu_index: int) -> dict[str, str]:
        return {
            "index": str(gpu_index),
            "name": "Fake GPU",
            "uuid": "GPU-fake-uuid",
            "driver_version": "999.99",
            "vbios_version": "1.0",
            "memory.total": "8192",
            "compute_cap": "8.6",
        }

    def snapshot(self, gpu_index: int) -> SensorSnapshot:
        return SensorSnapshot(_now(), gpu_index, dict(self._sensor_values))

    def environment(self) -> dict[str, str]:
        return {"os": "test", "hostname": "private-host"}


def _make_service(baseline_root: Path, runner: FakeWorkloadRunner) -> GpuMeasurementService:
    benchmarks = BenchmarkRepository(ROOT / "data" / "static" / "benchmarks")
    return GpuMeasurementService(
        FakeCollector(),
        benchmarks,
        workload_runner=runner,
        baseline_store=BaselineStore(baseline_root),
    )


class ProtocolTests(unittest.TestCase):
    def test_protocol_id_is_stable(self) -> None:
        self.assertEqual(protocol_id(WorkloadSpec()), protocol_id(WorkloadSpec()))

    def test_protocol_id_changes_with_dtype(self) -> None:
        self.assertNotEqual(
            protocol_id(WorkloadSpec(dtype="float32")),
            protocol_id(WorkloadSpec(dtype="float16")),
        )

    def test_operation_count_uses_multiply_add_as_two(self) -> None:
        spec = WorkloadSpec(size=8)
        self.assertEqual(spec.operation_count(1), 2 * 8 * 8 * 8)


class FakeRunnerTests(unittest.TestCase):
    def test_fake_runner_reports_requested_tflops(self) -> None:
        spec = WorkloadSpec(size=1024, measured_iterations=10)
        result = FakeWorkloadRunner(achieved_tflops=20.0).run(spec, 0)
        self.assertEqual(result.reliability, "valid")
        self.assertEqual(result.operation_count, 2 * 1024**3 * 10)
        self.assertAlmostEqual(result.achieved_tflops, 20.0, places=6)


class DiagnosticsTests(unittest.TestCase):
    def _samples(self, values: dict) -> list[SensorSnapshot]:
        return [SensorSnapshot(_now(), 0, values)]

    def test_thermal_reason_reported_by_driver(self) -> None:
        samples = self._samples(
            {
                "temperature_c": 86.0,
                "graphics_clock_mhz": 1200.0,
                "gpu_utilization_pct": 99.0,
                "throttle_reasons_active": "hw_thermal_slowdown",
            }
        )
        runner_result = FakeWorkloadRunner(achieved_tflops=10.0).run(WorkloadSpec(), 0)
        findings = DiagnosticEngine().diagnose(samples, runner_result)
        self.assertTrue(any(f.category == "thermal" and f.confidence == "high" for f in findings))

    def test_low_utilization_flags_workload_invalid(self) -> None:
        samples = self._samples(
            {"temperature_c": 45.0, "gpu_utilization_pct": 5.0, "graphics_clock_mhz": 1900.0}
        )
        runner_result = FakeWorkloadRunner(achieved_tflops=10.0).run(WorkloadSpec(), 0)
        findings = DiagnosticEngine().diagnose(samples, runner_result)
        self.assertTrue(any(f.category == "workload" for f in findings))

    def test_failed_workload_yields_driver_finding(self) -> None:
        runner_result = FakeWorkloadRunner(reliability="failed").run(WorkloadSpec(), 0)
        runner_result.reason = "boom"
        findings = DiagnosticEngine().diagnose([], runner_result)
        self.assertEqual(findings[0].category, "driver")

    def test_clean_run_reports_no_anomaly(self) -> None:
        samples = self._samples(
            {"temperature_c": 55.0, "gpu_utilization_pct": 97.0, "graphics_clock_mhz": 1900.0}
        )
        runner_result = FakeWorkloadRunner(achieved_tflops=10.0).run(WorkloadSpec(), 0)
        findings = DiagnosticEngine().diagnose(samples, runner_result)
        self.assertEqual([f.category for f in findings], ["none"])


class ThrottleDecodeTests(unittest.TestCase):
    def test_decode_none_and_unsupported(self) -> None:
        self.assertIsNone(decode_throttle_reasons(None))
        self.assertIsNone(decode_throttle_reasons("[N/A]"))
        self.assertEqual(decode_throttle_reasons("0x0000000000000000"), [])

    def test_decode_thermal_bit(self) -> None:
        self.assertIn("hw_thermal_slowdown", decode_throttle_reasons("0x0000000000000040"))


class ReferenceTests(unittest.TestCase):
    def test_known_model_fp32_has_peak_and_source(self) -> None:
        peak, source = theoretical_peak_tflops("NVIDIA GeForce RTX 3060 Ti", "float32")
        self.assertEqual(peak, 16.2)
        self.assertIsNotNone(source)

    def test_unknown_model_is_not_comparable(self) -> None:
        self.assertEqual(theoretical_peak_tflops("Mystery GPU 9000", "float32"), (None, None))

    def test_non_fp32_is_not_comparable(self) -> None:
        self.assertEqual(theoretical_peak_tflops("NVIDIA GeForce RTX 3060 Ti", "float16"), (None, None))


class PercentVsFirstTests(unittest.TestCase):
    def _record(self, tflops: float, dtype: str = "float32") -> dict:
        spec = WorkloadSpec(dtype=dtype)
        return {
            "protocol_id": protocol_id(spec),
            "created_at": "2026-01-01T00:00:00",
            "achieved_tflops": tflops,
            "workload": {"dtype": dtype, "shape": spec.shape, "reliability": "valid"},
        }

    def test_percent_against_first_comparable(self) -> None:
        records = [self._record(10.0), self._record(9.0)]
        result = percent_vs_first(
            records,
            protocol_id=protocol_id(WorkloadSpec()),
            dtype="float32",
            shape=WorkloadSpec().shape,
            achieved_tflops=8.0,
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["percent"], 80)  # 8.0 / 10.0

    def test_no_comparable_record_is_unavailable(self) -> None:
        result = percent_vs_first(
            [self._record(10.0, dtype="float16")],
            protocol_id=protocol_id(WorkloadSpec()),
            dtype="float32",
            shape=WorkloadSpec().shape,
            achieved_tflops=8.0,
        )
        self.assertFalse(result["available"])


class UsageMonitorTests(unittest.TestCase):
    def test_accumulates_throttle_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor = UsageMonitor(Path(tmp))
            monitor.record("GPU-x", {"throttle_reasons_active": "none", "temperature_c": 50.0})
            monitor.record("GPU-x", {"throttle_reasons_active": "sw_power_cap", "temperature_c": 70.0})
            monitor.record("GPU-x", {"throttle_reasons_active": "hw_thermal_slowdown", "temperature_c": 85.0})
            summary = monitor.summary("GPU-x")
            self.assertEqual(summary["observation_count"], 3)
            self.assertEqual(summary["throttled_count"], 2)
            self.assertEqual(summary["peak_temperature_c"], 85.0)
            self.assertEqual(summary["reason_counts"]["sw_power_cap"], 1)

    def test_unsupported_throttle_is_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor = UsageMonitor(Path(tmp))
            monitor.record("GPU-y", {"throttle_reasons_active": None, "temperature_c": 40.0})
            summary = monitor.summary("GPU-y")
            self.assertFalse(summary["supported"])
            self.assertEqual(summary["observation_count"], 0)


class AbuseIndicatorTests(unittest.TestCase):
    def test_thermal_finding_flags_cooling_watch(self) -> None:
        report = abuse_indicators(
            findings=[{"category": "thermal"}],
            telemetry={"temperature_c": {"max": 86.0}, "graphics_clock_mhz": {"max": 1500.0}},
            performance={"peak_utilization_status": "ok", "peak_utilization_pct": 55.0, "within_normal_range": True},
            rated_max_graphics_clock=1900.0,
            usage={"has_data": False},
        )
        cooling = next(i for i in report["indicators"] if i["label"] == "발열·냉각")
        self.assertEqual(cooling["status"], "watch")
        self.assertIn("채굴", report["note"])  # honest disclaimer present

    def test_clean_run_is_ok(self) -> None:
        report = abuse_indicators(
            findings=[{"category": "none"}],
            telemetry={"temperature_c": {"max": 62.0}, "graphics_clock_mhz": {"max": 1850.0}},
            performance={"peak_utilization_status": "ok", "peak_utilization_pct": 55.0, "within_normal_range": True},
            rated_max_graphics_clock=1900.0,
            usage={"has_data": False},
        )
        cooling = next(i for i in report["indicators"] if i["label"] == "발열·냉각")
        self.assertEqual(cooling["status"], "ok")


class CompareModelsTests(unittest.TestCase):
    def _record(self, name: str, tflops: float, elapsed: float = 4.0) -> dict:
        spec = WorkloadSpec()
        return {
            "protocol_id": protocol_id(spec),
            "created_at": "2026-07-14T00:00:00",
            "achieved_tflops": tflops,
            "gpu_identity": {"name": name},
            "workload": {
                "dtype": "float32",
                "shape": spec.shape,
                "reliability": "valid",
                "measured_iterations": spec.measured_iterations,
                "elapsed_seconds": elapsed,
            },
        }

    def test_orders_by_achieved_tflops_and_computes_per_iter(self) -> None:
        report = compare_models(
            [self._record("RTX 3060 Ti", 8.9), self._record("RTX 4090", 40.0, elapsed=1.0)]
        )
        self.assertTrue(report["available"])
        self.assertEqual([e["name"] for e in report["entries"]], ["RTX 4090", "RTX 3060 Ti"])
        # per-iteration time = elapsed / iterations * 1000 ms
        self.assertAlmostEqual(
            report["entries"][0]["per_iter_ms"],
            1.0 / WorkloadSpec().measured_iterations * 1000,
            places=3,
        )

    def test_keeps_best_per_model_and_ignores_invalid(self) -> None:
        invalid = self._record("RTX 3070", 99.0)
        invalid["workload"]["reliability"] = "failed"
        report = compare_models(
            [self._record("RTX 3070", 20.0), self._record("RTX 3070", 22.0), invalid]
        )
        names = [e["name"] for e in report["entries"]]
        self.assertEqual(names.count("RTX 3070"), 1)
        self.assertEqual(report["entries"][0]["achieved_tflops"], 22.0)


class ServiceValidationTests(unittest.TestCase):
    def test_validate_returns_all_required_areas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _make_service(Path(tmp), FakeWorkloadRunner(achieved_tflops=15.0))
            result, payload = service.validate_gpu(0)
            for key in [
                "device",
                "environment",
                "workload",
                "performance",
                "telemetry_summary",
                "findings",
                "baseline",
                "limitations",
            ]:
                self.assertIn(key, payload)
            self.assertEqual(result.workload.reliability, "valid")
            self.assertEqual(verdict(result), "통과")
            # theoretical peak source is unknown -> not_comparable, never invented
            self.assertEqual(payload["performance"]["peak_utilization_status"], "not_comparable")

    def test_baseline_then_history_delta_when_comparable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _make_service(Path(tmp), FakeWorkloadRunner(achieved_tflops=15.0))
            service.baseline_gpu(0)
            service.workload_runner = FakeWorkloadRunner(achieved_tflops=12.0)
            service.baseline_gpu(0)
            history = service.read_gpu_history(0)
            self.assertEqual(history["record_count"], 2)
            self.assertTrue(history["comparison"]["comparable"])
            delta = history["comparison"]["delta"]
            self.assertEqual(
                {delta["previous_tflops"], delta["latest_tflops"]}, {15.0, 12.0}
            )

    def test_history_not_comparable_across_dtypes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _make_service(Path(tmp), FakeWorkloadRunner(achieved_tflops=15.0))
            service.baseline_gpu(0, WorkloadSpec(dtype="float32"))
            service.baseline_gpu(0, WorkloadSpec(dtype="float16"))
            history = service.read_gpu_history(0)
            self.assertEqual(history["record_count"], 2)
            self.assertFalse(history["comparison"]["comparable"])

    def test_invalid_measurement_is_not_stored_as_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _make_service(Path(tmp), FakeWorkloadRunner(reliability="failed"))
            _result, payload = service.baseline_gpu(0)
            self.assertFalse(payload["baseline_saved"])
            self.assertEqual(service.read_gpu_history(0)["record_count"], 0)


if __name__ == "__main__":
    unittest.main()
