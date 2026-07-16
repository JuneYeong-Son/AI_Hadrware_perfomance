"""Database models: users, their registered machines, and measurements.

Provenance model: every machine gets a per-device HMAC secret (never leaves the
server) and a short, human-shareable ``public_code``. Every submitted
measurement is hashed and signed with its device secret, so a shared result can
be looked up on the public verify endpoint and checked against forgery.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    # Bumped on logout to invalidate every previously issued token at once.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    devices: Mapped[list["Device"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"
    # The same physical GPU may be re-registered by a new owner (second-hand
    # sale); uniqueness is per (owner, fingerprint), while public_code is global.
    __table_args__ = (
        UniqueConstraint("owner_id", "fingerprint", name="uq_owner_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Client-computed hash of a stable hardware id (e.g. GPU UUID). The raw id
    # never reaches the server.
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    public_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    hmac_secret: Mapped[str] = mapped_column(String(128))
    gpu_name: Mapped[str] = mapped_column(String(200), default="")
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    owner: Mapped["User"] = relationship(back_populates="devices")
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short, shareable authenticity code for this single result.
    verify_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)

    # Core comparable fields (mirrors the engine's ValidationResult).
    gpu_name: Mapped[str] = mapped_column(String(200), index=True)
    dtype: Mapped[str] = mapped_column(String(32), default="float32")
    matrix_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_id: Mapped[str] = mapped_column(String(64), index=True)
    achieved_tflops: Mapped[float] = mapped_column(Float, index=True)
    peak_tflops: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability: Mapped[str] = mapped_column(String(20), default="valid", index=True)

    driver_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    torch_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cuda_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timing_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    telemetry_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Integrity: sha256 over the canonical core fields, and its HMAC signature
    # under the device secret.
    payload_hash: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    owner: Mapped["User"] = relationship(back_populates="measurements")
    device: Mapped["Device"] = relationship(back_populates="measurements")
