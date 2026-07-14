"""Controlled GPU compute workloads.

Sensor collection (``collector.py``) answers *what state is the GPU in*.
This module answers a different question: *how much real compute does the GPU
deliver right now* under a controlled workload. The two are intentionally
separate components so that a value never silently mixes a sensor reading with a
benchmark number.

A ``GpuWorkloadRunner`` allocates data on the device once and repeats a matrix
multiplication inside the GPU, timing it with GPU events so that host-to-device
copies and file I/O do not dominate the measurement. A ``FakeWorkloadRunner`` is
provided so the whole pipeline is unit-testable without a real GPU.
"""

from __future__ import annotations

import hashlib
from typing import Callable, Protocol

from .models import WorkloadResult, WorkloadSpec

CancelCheck = Callable[[], bool]


class WorkloadError(RuntimeError):
    pass


class WorkloadCancelled(RuntimeError):
    """Raised when a running workload is cancelled by the user."""


def protocol_id(spec: WorkloadSpec) -> str:
    """Stable id for a measurement protocol.

    Two measurements are only comparable when this id matches. It deliberately
    excludes iteration counts (they change timing precision, not the protocol)
    and includes everything that changes the meaning of the number.
    """

    canonical = "|".join(
        [
            spec.name,
            spec.dtype,
            f"size={spec.size}",
            spec.flop_convention,
        ]
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"gemm-{digest[:12]}"


class GpuWorkloadRunner(Protocol):
    backend_name: str

    def is_available(self) -> bool: ...

    def run(
        self,
        spec: WorkloadSpec,
        gpu_index: int,
        cancel_check: CancelCheck | None = None,
    ) -> WorkloadResult: ...


class TorchCudaWorkloadRunner:
    """Runs a controlled GEMM on an NVIDIA GPU via PyTorch CUDA.

    Timing uses ``torch.cuda.Event`` so the measured window is GPU work only.
    For ``float32`` we disable TF32 so the number is real FP32 throughput rather
    than Ampere's TF32 path.
    """

    backend_name = "torch-cuda"

    _DTYPES = {
        "float32": "float32",
        "float16": "float16",
        "bfloat16": "bfloat16",
    }

    def is_available(self) -> bool:
        try:
            import torch
        except ImportError:
            return False
        return bool(torch.cuda.is_available())

    def run(
        self,
        spec: WorkloadSpec,
        gpu_index: int,
        cancel_check: CancelCheck | None = None,
    ) -> WorkloadResult:
        try:
            import torch
        except ImportError as error:  # pragma: no cover - guarded by is_available
            raise WorkloadError("PyTorch is not installed") from error

        if spec.dtype not in self._DTYPES:
            raise WorkloadError(f"Unsupported dtype for torch backend: {spec.dtype}")

        base = WorkloadResult(
            workload_name=spec.name,
            backend=self.backend_name,
            dtype=spec.dtype,
            shape=spec.shape,
            warmup_iterations=spec.warmup_iterations,
            measured_iterations=spec.measured_iterations,
            elapsed_seconds=None,
            operation_count=None,
            achieved_tflops=None,
            flop_convention=spec.flop_convention,
            timing_source="cuda_event",
            device_name=None,
            reliability="failed",
        )

        if not torch.cuda.is_available():
            base.reason = "CUDA is not available"
            return base

        try:
            device = torch.device(f"cuda:{gpu_index}")
            torch_dtype = getattr(torch, self._DTYPES[spec.dtype])
            # Measure true FP32 rather than the TF32 fast path on Ampere+.
            torch.backends.cuda.matmul.allow_tf32 = spec.dtype != "float32"

            base.device_name = torch.cuda.get_device_name(device)

            a = torch.randn(spec.size, spec.size, device=device, dtype=torch_dtype)
            b = torch.randn(spec.size, spec.size, device=device, dtype=torch_dtype)
            c = torch.empty(spec.size, spec.size, device=device, dtype=torch_dtype)

            if cancel_check and cancel_check():
                raise WorkloadCancelled("cancelled before workload")

            for _ in range(spec.warmup_iterations):
                torch.matmul(a, b, out=c)
            torch.cuda.synchronize(device)

            # Check for cancellation between small chunks so the timed GPU burst
            # stays interruptible without polluting the measured window.
            chunk = max(1, spec.measured_iterations // 20)
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            done = 0
            while done < spec.measured_iterations:
                if cancel_check and cancel_check():
                    torch.cuda.synchronize(device)
                    raise WorkloadCancelled("cancelled during workload")
                step = min(chunk, spec.measured_iterations - done)
                for _ in range(step):
                    torch.matmul(a, b, out=c)
                done += step
            end.record()
            torch.cuda.synchronize(device)

            elapsed_seconds = start.elapsed_time(end) / 1000.0
            operation_count = spec.operation_count(spec.measured_iterations)

            base.elapsed_seconds = elapsed_seconds
            base.operation_count = operation_count
            if elapsed_seconds > 0:
                base.achieved_tflops = operation_count / elapsed_seconds / 1e12
                base.reliability = "valid"
            else:
                base.reason = "measured elapsed time was not positive"
                base.reliability = "inconclusive"

            del a, b, c
            torch.cuda.empty_cache()
            return base
        except WorkloadCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - report any backend failure
            base.reliability = "failed"
            base.reason = f"{type(error).__name__}: {error}"
            return base


class FakeWorkloadRunner:
    """Deterministic runner for tests and GPU-less environments.

    Produces a plausible ``WorkloadResult`` without touching hardware so the
    orchestrator, diagnostics, and report builder can be exercised in CI.
    """

    backend_name = "fake"

    def __init__(
        self,
        achieved_tflops: float = 12.0,
        *,
        available: bool = True,
        device_name: str = "Fake GPU",
        reliability: str = "valid",
    ):
        self._achieved_tflops = achieved_tflops
        self._available = available
        self._device_name = device_name
        self._reliability = reliability

    def is_available(self) -> bool:
        return self._available

    def run(
        self,
        spec: WorkloadSpec,
        gpu_index: int,
        cancel_check: CancelCheck | None = None,
    ) -> WorkloadResult:
        if cancel_check and cancel_check():
            raise WorkloadCancelled("cancelled before workload")
        operation_count = spec.operation_count(spec.measured_iterations)
        elapsed_seconds = (
            operation_count / (self._achieved_tflops * 1e12)
            if self._achieved_tflops > 0
            else 0.0
        )
        return WorkloadResult(
            workload_name=spec.name,
            backend=self.backend_name,
            dtype=spec.dtype,
            shape=spec.shape,
            warmup_iterations=spec.warmup_iterations,
            measured_iterations=spec.measured_iterations,
            elapsed_seconds=elapsed_seconds,
            operation_count=operation_count,
            achieved_tflops=self._achieved_tflops,
            flop_convention=spec.flop_convention,
            timing_source="fake",
            device_name=self._device_name,
            reliability=self._reliability,
        )


def get_default_workload_runner() -> GpuWorkloadRunner:
    """Return a real GPU runner when possible, else the fake runner.

    The fake runner reports ``is_available() == False`` here so callers can tell
    that no true GPU workload backend was found instead of silently measuring
    nothing.
    """

    torch_runner = TorchCudaWorkloadRunner()
    if torch_runner.is_available():
        return torch_runner
    return FakeWorkloadRunner(available=False)
