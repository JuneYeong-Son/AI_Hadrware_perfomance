"""UI-facing adapter over GpuMeasurementService.

The windows talk only to this adapter. It builds the service, tolerates a
missing collector/GPU (returning an explicit not-ready state instead of raising),
and exposes exactly the read operations the screens need. Long-running
validation goes through ``ValidationWorker`` (see ``worker.py``), not this
adapter, so the UI thread never blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...collector import CollectorError, get_default_collector
from ...service import GpuMeasurementService, build_service

APPLICATION_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = APPLICATION_ROOT.parent


class UiServiceAdapter:
    def __init__(self, service: GpuMeasurementService | None, error: str | None = None):
        self.service = service
        self.error = error

    @property
    def is_ready(self) -> bool:
        return self.service is not None

    @property
    def provider(self) -> str:
        return self.service.provider_name if self.service else "unavailable"

    @classmethod
    def create(cls) -> "UiServiceAdapter":
        try:
            collector = get_default_collector()
        except CollectorError as error:
            return cls(None, str(error))
        service = build_service(REPO_ROOT, collector)
        return cls(service)

    @classmethod
    def from_service(cls, service: GpuMeasurementService) -> "UiServiceAdapter":
        """Used by headless tests with a fake collector-backed service."""
        return cls(service)

    def list_devices(self) -> list[dict[str, Any]]:
        if not self.service:
            return []
        try:
            return self.service.list_devices()
        except CollectorError:
            return []

    def inspect(self, gpu_index: int) -> dict[str, Any] | None:
        if not self.service:
            return None
        try:
            return self.service.inspect_device(gpu_index)
        except CollectorError:
            return None

    def snapshot(self, gpu_index: int) -> dict[str, Any] | None:
        if not self.service:
            return None
        try:
            _snapshot, payload = self.service.current_snapshot(gpu_index)
            return payload
        except CollectorError:
            return None

    def save_result_as_baseline(self, result) -> dict[str, Any]:
        if not self.service:
            return {"saved": False, "note": "서비스를 사용할 수 없습니다."}
        try:
            return self.service.save_result_as_baseline(result)
        except ValueError as error:
            return {"saved": False, "note": str(error)}

    def record_usage(self, gpu_uuid: str, values: dict[str, Any]) -> None:
        if self.service:
            try:
                self.service.record_usage(gpu_uuid, values)
            except (CollectorError, OSError):
                pass

    def usage_summary(self, gpu_uuid: str) -> dict[str, Any]:
        if not self.service:
            return {"has_data": False}
        return self.service.usage_summary(gpu_uuid)

    def abuse_check(self, result) -> dict[str, Any]:
        if not self.service:
            return {"note": "", "indicators": []}
        return self.service.abuse_check(result)

    def compare_models(self, protocol_id: str | None = None) -> dict[str, Any]:
        if not self.service:
            return {"available": False, "protocol_id": None, "entries": []}
        return self.service.compare_models(protocol_id)

    def history(self, gpu_index: int) -> dict[str, Any]:
        if not self.service:
            return {"record_count": 0, "records": [], "comparison": {"comparable": False}}
        try:
            return self.service.read_gpu_history(gpu_index)
        except (CollectorError, ValueError):
            return {"record_count": 0, "records": [], "comparison": {"comparable": False}}
