from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


APPLICATION = Path(__file__).resolve().parents[1]
ROOT = APPLICATION.parent
sys.path.insert(0, str(APPLICATION))

from gpu_measurer.benchmarks import BenchmarkRepository, normalize_gpu_name
from gpu_measurer.collector import CollectorRegistry
from gpu_measurer.models import BenchmarkMatch, GpuDevice, MeasurementResult, SensorSnapshot
from gpu_measurer.reporting import summarize_snapshots
from gpu_measurer.serialization import measurement_to_dict, redact_sensitive_data, response_envelope
from gpu_measurer.service import GpuMeasurementService


class BenchmarkTests(unittest.TestCase):
    def test_normalize_removes_vendor_and_punctuation(self) -> None:
        self.assertEqual(normalize_gpu_name("NVIDIA GeForce RTX 3060 Ti"), "geforce rtx 3060 ti")

    def test_exact_passmark_match(self) -> None:
        repository = BenchmarkRepository(ROOT / "data" / "static" / "benchmarks")
        match = repository.match("NVIDIA GeForce RTX 3060 Ti")
        self.assertTrue(match.exact)
        self.assertEqual(match.passmark["G3Dmark"], "20206")

    def test_missing_model_has_suggestions_but_no_false_match(self) -> None:
        repository = BenchmarkRepository(ROOT / "data" / "static" / "benchmarks")
        match = repository.match("NVIDIA GeForce RTX 4060 Laptop GPU")
        self.assertFalse(match.exact)
        self.assertGreater(len(match.suggestions), 0)


class ReportingTests(unittest.TestCase):
    def test_summary_ignores_unavailable_values(self) -> None:
        samples = [
            SensorSnapshot(datetime.now(), 0, {"temperature_c": 40.0, "gpu_utilization_pct": 10.0}),
            SensorSnapshot(datetime.now(), 0, {"temperature_c": 50.0, "gpu_utilization_pct": None}),
        ]
        summary = summarize_snapshots(samples)
        self.assertEqual(summary["temperature_c"]["avg"], 45.0)
        self.assertEqual(summary["gpu_utilization_pct"]["avg"], 10.0)

    def test_measurement_serialization_is_json_ready(self) -> None:
        started = datetime(2026, 7, 13, tzinfo=timezone.utc)
        sample = SensorSnapshot(started, 0, {"temperature_c": 42.0})
        result = MeasurementResult(
            started_at=started,
            finished_at=started + timedelta(seconds=1),
            gpu={"name": "Test GPU"},
            benchmark=BenchmarkMatch("Test GPU"),
            samples=[sample],
            summary={"temperature_c": {"min": 42.0, "avg": 42.0, "max": 42.0}},
            environment={"os": "test"},
        )
        payload = measurement_to_dict(result)
        self.assertEqual(payload["duration_seconds"], 1.0)
        self.assertEqual(payload["samples"][0]["values"]["temperature_c"], 42.0)

    def test_response_envelope_has_stable_contract(self) -> None:
        payload = response_envelope({"status": "ready"}, "fake")
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["error"])

    def test_sensitive_identifiers_are_redacted_for_automation(self) -> None:
        payload = redact_sensitive_data(
            {"uuid": "GPU-secret", "environment": {"hostname": "private-pc"}}
        )
        self.assertEqual(payload["uuid"], "[redacted]")
        self.assertEqual(payload["environment"]["hostname"], "[redacted]")


class ServiceTests(unittest.TestCase):
    def test_service_accepts_a_vendor_neutral_collector(self) -> None:
        class FakeCollector:
            provider_name = "fake"

            def is_available(self) -> bool:
                return True

            def list_devices(self) -> list[GpuDevice]:
                return [GpuDevice(0, "Test GPU", "GPU-test")]

            def static_info(self, gpu_index: int) -> dict[str, str]:
                return {"index": str(gpu_index), "name": "Test GPU"}

            def snapshot(self, gpu_index: int) -> SensorSnapshot:
                return SensorSnapshot(datetime.now(timezone.utc), gpu_index, {"temperature_c": 40.0})

            def environment(self) -> dict[str, str]:
                return {"os": "test"}

        collector = CollectorRegistry([FakeCollector()]).default()
        repository = BenchmarkRepository(ROOT / "data" / "static" / "benchmarks")
        service = GpuMeasurementService(collector, repository)
        self.assertEqual(service.provider_name, "fake")
        self.assertEqual(service.list_devices()[0]["name"], "Test GPU")
        self.assertEqual(service.inspect_device(0)["gpu"]["index"], "0")


if __name__ == "__main__":
    unittest.main()
