"""Theoretical peak reference for known GPU models.

Per the brief §5, a "사양 대비 %" (peak_utilization) may only be shown when the
theoretical peak has a clear source. This table lists FP32 (non-tensor, shader)
theoretical peak throughput at boost clock, from published NVIDIA/TechPowerUp
specs. It is a manufacturer *ceiling*, not an expected result: a healthy GPU
running an untuned GEMM reaches well below it, so the number is presented as
"사양(이론 최대) 대비", never as a health verdict.

Only FP32 is covered here (the default workload dtype). For other dtypes, or for
a model not in this table, peak_utilization stays ``not_comparable`` rather than
being estimated.
"""

from __future__ import annotations

from .benchmarks import normalize_gpu_name

REFERENCE_SOURCE = "NVIDIA/TechPowerUp 사양 (FP32 shader peak, boost clock)"

# Typical "사양 대비 %" a *healthy* GPU reaches on the default FP32 GEMM protocol.
# This is a property of the untuned torch.matmul FP32 workload (cuBLAS SGEMM
# efficiency on consumer GPUs with TF32 off), NOT an empirical health threshold
# derived from accumulated data. It is shown only as a rough guide so a normal
# ~55% is not misread as a fault. If the workload protocol changes, this range
# must be revisited.
FP32_GEMM_NORMAL_RANGE_PCT = (40, 70)

# Rough load-temperature guide for consumer NVIDIA GPUs. Most GeForce cards begin
# thermal throttling around 83°C and hard-limit near 90–93°C, so under a compute
# load "보통 ~80°C 이하, 83°C 이상은 쓰로틀링 주의" is a reasonable guide (a general
# guide, not a per-model verdict).
LOAD_TEMPERATURE_NORMAL_MAX_C = 80
LOAD_TEMPERATURE_THROTTLE_WATCH_C = 83

# Keyed by human model name; normalized on load so lookups are vendor/-punctuation
# insensitive. Values are TFLOPS.
_FP32_PEAK_TFLOPS_RAW = {
    # GeForce RTX 30 series (Ampere)
    "GeForce RTX 3060": 12.7,
    "GeForce RTX 3060 Ti": 16.2,
    "GeForce RTX 3070": 20.3,
    "GeForce RTX 3070 Ti": 21.7,
    "GeForce RTX 3080": 29.8,
    "GeForce RTX 3080 Ti": 34.1,
    "GeForce RTX 3090": 35.6,
    "GeForce RTX 3090 Ti": 40.0,
    # GeForce RTX 40 series (Ada)
    "GeForce RTX 4060": 15.1,
    "GeForce RTX 4060 Ti": 22.1,
    "GeForce RTX 4070": 29.1,
    "GeForce RTX 4070 Ti": 40.1,
    "GeForce RTX 4080": 48.7,
    "GeForce RTX 4090": 82.6,
    # GeForce RTX 20 series (Turing)
    "GeForce RTX 2060": 6.5,
    "GeForce RTX 2070": 7.5,
    "GeForce RTX 2080": 10.1,
    "GeForce RTX 2080 Ti": 13.4,
    # Workstation / data center (common in used market)
    "RTX A2000": 8.0,
    "RTX A4000": 19.2,
    "RTX A4500": 23.7,
    "RTX A5000": 27.8,
    "RTX A6000": 38.7,
    "Tesla T4": 8.1,
    "A100": 19.5,
}

FP32_PEAK_TFLOPS = {
    normalize_gpu_name(name): value for name, value in _FP32_PEAK_TFLOPS_RAW.items()
}


def theoretical_peak_tflops(
    gpu_name: str | None, dtype: str
) -> tuple[float | None, str | None]:
    """Return (peak_tflops, source) when it is safe to compare, else (None, None).

    Only float32 is supported; unknown models and other dtypes return None so the
    caller keeps peak_utilization at ``not_comparable`` instead of inventing one.
    """
    if not gpu_name or dtype != "float32":
        return None, None
    peak = FP32_PEAK_TFLOPS.get(normalize_gpu_name(gpu_name))
    if peak is None:
        return None, None
    return peak, REFERENCE_SOURCE
