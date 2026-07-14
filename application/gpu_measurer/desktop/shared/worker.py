"""Background validation worker.

Runs a controlled workload off the UI thread and reports progress with Qt
signals. The workload is cancellable: ``cancel()`` sets an event the runner
checks between iteration chunks, so a long GPU burst can be stopped without
freezing the app or saving a partial result as success.
"""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QThread, Signal

from ...models import WorkloadSpec
from ...service import GpuMeasurementService
from ...workload import WorkloadCancelled

# Stage name -> human label shown on the progress screen.
STAGE_LABELS = {
    "precheck": "사전 확인",
    "workload": "workload 실행 및 센서 수집",
    "diagnose": "진단",
    "done": "리포트 준비",
}


class ValidationWorker(QThread):
    stage_changed = Signal(str, str)          # stage key, label
    sensor_tick = Signal(dict)                # latest sensor values
    completed = Signal(object, dict)          # ValidationResult, payload
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        service: GpuMeasurementService,
        gpu_index: int,
        spec: WorkloadSpec,
        *,
        save_baseline: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._service = service
        self._gpu_index = gpu_index
        self._spec = spec
        self._save_baseline = save_baseline
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _progress(self, event: str, payload: dict[str, Any]) -> None:
        if event == "stage":
            key = payload.get("name", "")
            self.stage_changed.emit(key, STAGE_LABELS.get(key, key))
        elif event == "sample":
            self.sensor_tick.emit(payload)

    def run(self) -> None:  # executed on the worker thread
        try:
            if self._save_baseline:
                result, payload = self._service.baseline_gpu(
                    self._gpu_index,
                    self._spec,
                    progress=self._progress,
                    cancel_event=self._cancel,
                )
            else:
                result, payload = self._service.validate_gpu(
                    self._gpu_index,
                    self._spec,
                    progress=self._progress,
                    cancel_event=self._cancel,
                )
        except WorkloadCancelled:
            self.cancelled.emit()
            return
        except Exception as error:  # noqa: BLE001 - surface any failure to the UI
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.completed.emit(result, payload)
