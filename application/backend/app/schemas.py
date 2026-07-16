"""Pydantic request/response models (API contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Auth -------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    display_name: str
    created_at: datetime


# --- Devices ----------------------------------------------------------------
class DeviceRegisterRequest(BaseModel):
    # Client-side hash of a stable hardware id (e.g. sha256 of the GPU UUID).
    fingerprint: str = Field(min_length=8, max_length=128)
    gpu_name: str = Field(default="", max_length=200)
    label: str = Field(default="", max_length=120)


class DeviceOut(BaseModel):
    id: int
    public_code: str
    gpu_name: str
    label: str
    fingerprint_masked: str
    created_at: datetime


# --- Measurements -----------------------------------------------------------
class MeasurementSubmit(BaseModel):
    device_public_code: str
    gpu_name: str = Field(max_length=200)
    protocol_id: str = Field(max_length=64)
    achieved_tflops: float
    dtype: str = "float32"
    matrix_size: int | None = None
    peak_tflops: float | None = None
    peak_utilization_pct: float | None = None
    reliability: str = "valid"
    driver_version: str | None = None
    torch_version: str | None = None
    cuda_version: str | None = None
    timing_source: str | None = None
    telemetry_summary: dict[str, Any] | None = None
    # Optional full engine document, retained for auditing.
    raw: dict[str, Any] | None = None


class MeasurementOut(BaseModel):
    id: int
    verify_code: str
    gpu_name: str
    dtype: str
    matrix_size: int | None
    protocol_id: str
    achieved_tflops: float
    peak_tflops: float | None
    peak_utilization_pct: float | None
    reliability: str
    created_at: datetime


class SubmitResponse(BaseModel):
    measurement: MeasurementOut
    verify_code: str
    device_public_code: str
    share_url: str
    signature: str


class VerifyResponse(BaseModel):
    """Public, tamper-evident view of a recorded measurement."""

    verify_code: str
    integrity: str  # "server-recorded"
    submitted_by: str  # display name
    device_public_code: str
    device_fingerprint_masked: str
    gpu_name: str
    dtype: str
    matrix_size: int | None
    protocol_id: str
    achieved_tflops: float
    peak_tflops: float | None
    peak_utilization_pct: float | None
    reliability: str
    driver_version: str | None
    recorded_at: datetime
    payload_hash: str
    signature: str


# --- Analytics --------------------------------------------------------------
class ModelStat(BaseModel):
    gpu_name: str
    protocol_id: str
    dtype: str
    sample_count: int
    avg_tflops: float
    median_tflops: float
    p10_tflops: float
    p90_tflops: float
    max_tflops: float


class PercentileResponse(BaseModel):
    gpu_name: str
    protocol_id: str
    your_tflops: float
    percentile: float  # 0-100, higher = faster than more peers
    sample_count: int
    median_tflops: float
