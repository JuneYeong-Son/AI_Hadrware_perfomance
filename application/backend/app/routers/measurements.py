"""Submit measurements (signed by the owning machine) and verify shared ones.

The verify endpoints are public and require no auth: anyone holding a shared
code can confirm a result is server-recorded and read its canonical numbers,
which is what makes a shared benchmark tamper-evident.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import security
from ..database import get_db
from ..deps import get_current_user
from ..models import Device, Measurement, User
from ..schemas import (
    MeasurementOut,
    MeasurementSubmit,
    SubmitResponse,
    VerifyResponse,
)

router = APIRouter(tags=["measurements"])


def _mask(fingerprint: str) -> str:
    return f"{fingerprint[:6]}…{fingerprint[-4:]}" if len(fingerprint) > 12 else "…"


def _to_out(m: Measurement) -> MeasurementOut:
    return MeasurementOut(
        id=m.id,
        verify_code=m.verify_code,
        gpu_name=m.gpu_name,
        dtype=m.dtype,
        matrix_size=m.matrix_size,
        protocol_id=m.protocol_id,
        achieved_tflops=m.achieved_tflops,
        peak_tflops=m.peak_tflops,
        peak_utilization_pct=m.peak_utilization_pct,
        reliability=m.reliability,
        created_at=m.created_at,
    )


def _unique_verify_code(db: Session) -> str:
    while True:
        code = security.random_code(prefix="M-", groups=2, group_len=4)
        if db.scalar(select(Measurement).where(Measurement.verify_code == code)) is None:
            return code


@router.post("/api/measurements", response_model=SubmitResponse)
def submit_measurement(
    body: MeasurementSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmitResponse:
    device = db.scalar(
        select(Device).where(
            Device.owner_id == user.id,
            Device.public_code == body.device_public_code,
        )
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found for this account. Register it first.",
        )

    verify_code = _unique_verify_code(db)
    core = {
        "gpu_name": body.gpu_name,
        "dtype": body.dtype,
        "matrix_size": body.matrix_size,
        "protocol_id": body.protocol_id,
        "achieved_tflops": body.achieved_tflops,
        "reliability": body.reliability,
        "device_fingerprint": device.fingerprint,
        "verify_code": verify_code,
    }
    payload_hash = security.canonical_hash(core)
    signature = security.sign(device.hmac_secret, payload_hash)

    measurement = Measurement(
        verify_code=verify_code,
        owner_id=user.id,
        device_id=device.id,
        gpu_name=body.gpu_name,
        dtype=body.dtype,
        matrix_size=body.matrix_size,
        protocol_id=body.protocol_id,
        achieved_tflops=body.achieved_tflops,
        peak_tflops=body.peak_tflops,
        peak_utilization_pct=body.peak_utilization_pct,
        reliability=body.reliability,
        driver_version=body.driver_version,
        torch_version=body.torch_version,
        cuda_version=body.cuda_version,
        timing_source=body.timing_source,
        telemetry_summary=body.telemetry_summary,
        payload=body.raw,
        payload_hash=payload_hash,
        signature=signature,
    )
    db.add(measurement)
    db.commit()
    db.refresh(measurement)

    return SubmitResponse(
        measurement=_to_out(measurement),
        verify_code=verify_code,
        device_public_code=device.public_code,
        share_url=f"/api/verify/{verify_code}",
        signature=signature,
    )


@router.get("/api/measurements", response_model=list[MeasurementOut])
def my_measurements(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[MeasurementOut]:
    rows = db.scalars(
        select(Measurement)
        .where(Measurement.owner_id == user.id)
        .order_by(Measurement.created_at.desc())
    ).all()
    return [_to_out(m) for m in rows]


@router.get("/api/verify/{verify_code}", response_model=VerifyResponse)
def verify_measurement(
    verify_code: str, db: Session = Depends(get_db)
) -> VerifyResponse:
    m = db.scalar(select(Measurement).where(Measurement.verify_code == verify_code))
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No measurement with this code. It may be forged or was deleted.",
        )
    return VerifyResponse(
        verify_code=m.verify_code,
        integrity="server-recorded",
        submitted_by=m.owner.display_name,
        device_public_code=m.device.public_code,
        device_fingerprint_masked=_mask(m.device.fingerprint),
        gpu_name=m.gpu_name,
        dtype=m.dtype,
        matrix_size=m.matrix_size,
        protocol_id=m.protocol_id,
        achieved_tflops=m.achieved_tflops,
        peak_tflops=m.peak_tflops,
        peak_utilization_pct=m.peak_utilization_pct,
        reliability=m.reliability,
        driver_version=m.driver_version,
        recorded_at=m.created_at,
        payload_hash=m.payload_hash,
        signature=m.signature,
    )


@router.get("/api/verify/device/{public_code}", response_model=list[VerifyResponse])
def verify_device(public_code: str, db: Session = Depends(get_db)) -> list[VerifyResponse]:
    device = db.scalar(select(Device).where(Device.public_code == public_code))
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown machine code."
        )
    rows = db.scalars(
        select(Measurement)
        .where(Measurement.device_id == device.id)
        .order_by(Measurement.created_at.desc())
    ).all()
    return [
        VerifyResponse(
            verify_code=m.verify_code,
            integrity="server-recorded",
            submitted_by=m.owner.display_name,
            device_public_code=device.public_code,
            device_fingerprint_masked=_mask(device.fingerprint),
            gpu_name=m.gpu_name,
            dtype=m.dtype,
            matrix_size=m.matrix_size,
            protocol_id=m.protocol_id,
            achieved_tflops=m.achieved_tflops,
            peak_tflops=m.peak_tflops,
            peak_utilization_pct=m.peak_utilization_pct,
            reliability=m.reliability,
            driver_version=m.driver_version,
            recorded_at=m.created_at,
            payload_hash=m.payload_hash,
            signature=m.signature,
        )
        for m in rows
    ]
