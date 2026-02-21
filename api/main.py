"""
FORESIGHT FastAPI Application — Entry Point

Wires up all routers, middleware, and startup/shutdown lifecycle hooks.
Runs on uvicorn with async SQLAlchemy sessions and JWT-based tenant isolation.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import alerts, assets, predictions, reports, rules

log = logging.getLogger("foresight.api")


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager.
    Runs startup logic before yield, teardown logic after.
    """
    log.info("FORESIGHT API starting up — environment=%s", os.getenv("ENVIRONMENT", "development"))

    # Pre-warm the SQLAlchemy engine so first requests don't pay connection cost
    try:
        from api.dependencies import get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: None)
        log.info("Database connection pool initialised.")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not pre-warm DB pool (non-fatal in dev): %s", exc)

    # Pre-load the champion ML model into memory for fast inference
    try:
        from ml.serving.predictor import ModelPredictor as Predictor

        app.state.predictor = Predictor()
        log.info("Champion ML model loaded into app.state.predictor.")
    except Exception as exc:  # noqa: BLE001
        log.warning("ML model not loaded (non-fatal in dev): %s", exc)
        app.state.predictor = None

    yield

    log.info("FORESIGHT API shutting down...")
    try:
        from api.dependencies import get_engine

        engine = get_engine()
        await engine.dispose()
        log.info("Database connection pool disposed.")
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FORESIGHT Predictive Asset Maintenance API",
    description=(
        "Multi-tenant SaaS API for predictive asset failure detection. "
        "Provides real-time health scores, ML predictions, and alert management "
        "for utilities, rail, oil & gas, and infrastructure operators."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# CORS Middleware
# ─────────────────────────────────────────────────────────────────────────────

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request Timing + Tenant Logging Middleware
# ─────────────────────────────────────────────────────────────────────────────


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next) -> Response:
    """
    Adds X-Process-Time header to every response and emits structured access logs.
    """
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1_000
    response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
    log.info(
        "method=%s path=%s status=%d duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Global Exception Handlers
# ─────────────────────────────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Let FastAPI handle HTTPExceptions normally (401, 403, 404, 422, etc.)
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None) or {},
        )
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal error occurred. Please try again."},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────


app.include_router(assets.router, prefix="/assets", tags=["Assets"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(predictions.router, prefix="/predict", tags=["Predictions"])
app.include_router(rules.router, prefix="/rules", tags=["Alert Rules"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])


# ─────────────────────────────────────────────────────────────────────────────
# System Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["System"], summary="System health check")
async def health_check() -> dict:
    """
    Returns overall API health status including downstream connectivity checks.
    """
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        from api.dependencies import get_engine
        from sqlalchemy import text

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"

    # MongoDB
    try:
        import motor.motor_asyncio as motor

        mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        client = motor.AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=2000)
        await client.admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["mongodb"] = f"error: {exc}"

    overall = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "service": "foresight-api",
        "version": "0.1.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "checks": checks,
    }


@app.get("/", tags=["System"], include_in_schema=False)
async def root() -> dict:
    return {"service": "FORESIGHT Predictive Asset Maintenance API", "docs": "/docs"}
