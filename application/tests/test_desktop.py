from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Qt must run headless in CI: pick the offscreen platform before any QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APPLICATION = Path(__file__).resolve().parents[1]
ROOT = APPLICATION.parent
sys.path.insert(0, str(APPLICATION))

try:
    from PySide6.QtWidgets import QApplication

    HAS_QT = True
except ImportError:
    HAS_QT = False

from gpu_measurer.baseline import BaselineStore
from gpu_measurer.benchmarks import BenchmarkRepository
from gpu_measurer.models import GpuDevice, SensorSnapshot
from gpu_measurer.service import GpuMeasurementService
from gpu_measurer.workload import FakeWorkloadRunner


class _FakeCollector:
    provider_name = "fake"

    def is_available(self) -> bool:
        return True

    def list_devices(self) -> list[GpuDevice]:
        return [GpuDevice(0, "Fake GPU", "GPU-fake-uuid")]

    def static_info(self, gpu_index: int) -> dict[str, str]:
        return {"index": str(gpu_index), "name": "Fake GPU", "uuid": "GPU-fake-uuid",
                "driver_version": "1.0", "memory.total": "8192", "compute_cap": "8.6"}

    def snapshot(self, gpu_index: int) -> SensorSnapshot:
        return SensorSnapshot(
            datetime.now(timezone.utc),
            gpu_index,
            {"temperature_c": 55.0, "gpu_utilization_pct": 96.0, "graphics_clock_mhz": 1900.0,
             "power_draw_w": 150.0, "power_limit_w": 200.0, "throttle_reasons_active": "none"},
        )

    def environment(self) -> dict[str, str]:
        return {"os": "test", "hostname": "host"}


def _fake_service(tmp: Path) -> GpuMeasurementService:
    return GpuMeasurementService(
        _FakeCollector(),
        BenchmarkRepository(ROOT / "data" / "static" / "benchmarks"),
        workload_runner=FakeWorkloadRunner(achieved_tflops=15.0),
        baseline_store=BaselineStore(tmp),
    )


@unittest.skipUnless(HAS_QT, "PySide6 not installed")
class DesktopSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_gpu_check_window_builds_and_lists_device(self) -> None:
        from gpu_measurer.desktop.buyer.main_window import GpuCheckWindow
        from gpu_measurer.desktop.shared.service_adapter import UiServiceAdapter

        with tempfile.TemporaryDirectory() as tmp:
            adapter = UiServiceAdapter.from_service(_fake_service(Path(tmp)))
            window = GpuCheckWindow(adapter)
            self.app.processEvents()
            # Three tabs: GPU 정보 / 벤치마크 / 모델 비교
            self.assertEqual(window.tabs.count(), 3)
            self.assertIn("Fake GPU", window.device_label.text())
            self.assertTrue(window.start_button.isEnabled())
            # Info tab live refresh populates without error.
            window.tabs.setCurrentWidget(window.info_tab)
            window._refresh_info()
            self.assertNotEqual(window.info_live["temperature_c"].text(), "—")
            window.close()

    def test_gpu_ops_window_builds_table(self) -> None:
        from gpu_measurer.desktop.operator.main_window import GpuOpsWindow
        from gpu_measurer.desktop.shared.service_adapter import UiServiceAdapter

        with tempfile.TemporaryDirectory() as tmp:
            service = _fake_service(Path(tmp))
            # Seed one baseline so the table/history path is exercised.
            service.baseline_gpu(0)
            adapter = UiServiceAdapter.from_service(service)
            window = GpuOpsWindow(adapter)
            self.app.processEvents()
            self.assertEqual(window.table.rowCount(), 1)
            self.assertEqual(window.table.item(0, 1).text(), "Fake GPU")
            window.close()

    def test_not_ready_adapter_disables_actions(self) -> None:
        from gpu_measurer.desktop.buyer.main_window import GpuCheckWindow
        from gpu_measurer.desktop.shared.service_adapter import UiServiceAdapter

        window = GpuCheckWindow(UiServiceAdapter(None, "no collector"))
        self.app.processEvents()
        self.assertFalse(window.start_button.isEnabled())
        window.close()


if __name__ == "__main__":
    unittest.main()
