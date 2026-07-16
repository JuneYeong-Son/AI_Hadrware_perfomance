"""FastAPI application entrypoint.

Run locally:
    cd application/backend
    pip install -r requirements.txt
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs for the interactive API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import analytics, auth, devices, measurements


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # MVP schema management. Swap for Alembic migrations before production.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="GPU-Perf API",
    version="0.1.0",
    summary="Accounts, machine-signed measurement provenance, and cross-user "
    "GPU performance analytics.",
    lifespan=lifespan,
)

_origins = (
    ["*"]
    if settings.cors_origins.strip() == "*"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gpu-perf-api"}


app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(measurements.router)
app.include_router(analytics.router)
