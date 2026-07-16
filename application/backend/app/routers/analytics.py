"""Cross-user performance analytics.

Comparability rule (mirrors the measurement engine): results are only pooled
within the same ``protocol_id``, and only ``reliability == "valid"`` rows count.
Percentiles are computed in Python so this works identically on SQLite.
"""

from __future__ import annotations

from statistics import mean, median

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Measurement, User
from ..schemas import MeasurementOut, ModelStat, PercentileResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in 0..100)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac


def _valid_rows(db: Session, protocol_id: str | None, gpu_name: str | None):
    stmt = select(Measurement).where(Measurement.reliability == "valid")
    if protocol_id:
        stmt = stmt.where(Measurement.protocol_id == protocol_id)
    if gpu_name:
        stmt = stmt.where(Measurement.gpu_name == gpu_name)
    return db.scalars(stmt).all()


@router.get("/models", response_model=list[ModelStat])
def model_stats(
    protocol_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ModelStat]:
    rows = _valid_rows(db, protocol_id, None)
    # Group by the fields that make results comparable.
    groups: dict[tuple[str, str, str], list[float]] = {}
    for m in rows:
        groups.setdefault((m.gpu_name, m.protocol_id, m.dtype), []).append(
            m.achieved_tflops
        )
    stats: list[ModelStat] = []
    for (gpu_name, proto, dtype), values in groups.items():
        values.sort()
        stats.append(
            ModelStat(
                gpu_name=gpu_name,
                protocol_id=proto,
                dtype=dtype,
                sample_count=len(values),
                avg_tflops=round(mean(values), 4),
                median_tflops=round(median(values), 4),
                p10_tflops=round(_percentile(values, 10), 4),
                p90_tflops=round(_percentile(values, 90), 4),
                max_tflops=round(max(values), 4),
            )
        )
    stats.sort(key=lambda s: s.sample_count, reverse=True)
    return stats


@router.get("/leaderboard", response_model=list[MeasurementOut])
def leaderboard(
    gpu_name: str | None = Query(default=None),
    protocol_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[MeasurementOut]:
    stmt = (
        select(Measurement)
        .where(Measurement.reliability == "valid")
        .order_by(Measurement.achieved_tflops.desc())
        .limit(limit)
    )
    if gpu_name:
        stmt = stmt.where(Measurement.gpu_name == gpu_name)
    if protocol_id:
        stmt = stmt.where(Measurement.protocol_id == protocol_id)
    rows = db.scalars(stmt).all()
    return [
        MeasurementOut(
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
        for m in rows
    ]


@router.get("/me/percentile", response_model=PercentileResponse)
def my_percentile(
    measurement_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PercentileResponse:
    mine = db.get(Measurement, measurement_id)
    if mine is None or mine.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Measurement not found."
        )
    peers = _valid_rows(db, mine.protocol_id, mine.gpu_name)
    values = sorted(m.achieved_tflops for m in peers)
    if not values:
        # Your own valid result should be in here; guard anyway.
        values = [mine.achieved_tflops]
    at_or_below = sum(1 for v in values if v <= mine.achieved_tflops)
    percentile = round(at_or_below / len(values) * 100, 1)
    return PercentileResponse(
        gpu_name=mine.gpu_name,
        protocol_id=mine.protocol_id,
        your_tflops=mine.achieved_tflops,
        percentile=percentile,
        sample_count=len(values),
        median_tflops=round(median(values), 4),
    )
