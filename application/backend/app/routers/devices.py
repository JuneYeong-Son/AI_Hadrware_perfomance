"""Machine registration. Each machine gets a shareable public code plus a
server-only HMAC secret used to sign its measurements."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import security
from ..database import get_db
from ..deps import get_current_user
from ..models import Device, User
from ..schemas import DeviceOut, DeviceRegisterRequest

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _mask(fingerprint: str) -> str:
    return f"{fingerprint[:6]}…{fingerprint[-4:]}" if len(fingerprint) > 12 else "…"


def _to_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        public_code=device.public_code,
        gpu_name=device.gpu_name,
        label=device.label,
        fingerprint_masked=_mask(device.fingerprint),
        created_at=device.created_at,
    )


def _unique_public_code(db: Session) -> str:
    while True:
        code = security.random_code(prefix="NV-")
        if db.scalar(select(Device).where(Device.public_code == code)) is None:
            return code


@router.post("/register", response_model=DeviceOut)
def register_device(
    body: DeviceRegisterRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceOut:
    # Idempotent per (owner, fingerprint): re-registering returns the same code.
    existing = db.scalar(
        select(Device).where(
            Device.owner_id == user.id, Device.fingerprint == body.fingerprint
        )
    )
    if existing is not None:
        if body.gpu_name:
            existing.gpu_name = body.gpu_name
        if body.label:
            existing.label = body.label
        db.commit()
        db.refresh(existing)
        return _to_out(existing)

    device = Device(
        owner_id=user.id,
        fingerprint=body.fingerprint,
        public_code=_unique_public_code(db),
        hmac_secret=security.new_device_secret(),
        gpu_name=body.gpu_name,
        label=body.label,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return _to_out(device)


@router.get("", response_model=list[DeviceOut])
def list_devices(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DeviceOut]:
    devices = db.scalars(
        select(Device).where(Device.owner_id == user.id).order_by(Device.created_at)
    ).all()
    return [_to_out(d) for d in devices]
