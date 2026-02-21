"""
FORESIGHT FastAPI Application — Entry Point

Wires up all routers, middleware, and startup/shutdown lifecycle hooks.
The actual endpoint implementations live in api/routers/.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Placeholder imports — routers are built fully on Day 5
# from api.routers import assets, alerts, predictions, rules, reports, auth

log = logging.getLogger("foresight.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager.
    Runs startup logic before yield, teardown logic after.
    """
    log.info("FORESIGHT API starting up...")
    # TODO Day 5: initialise DB connection pools, load ML model
    yield
    log.info("FORESIGHT API shutting down...")


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

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"], summary="System health check")
async def health_check() -> dict:
    """
    Returns overall API health status.
    Full downstream service checks (DB, Mongo, Kafka, MLflow) are added on Day 5.
    """
    return {
        "status": "healthy",
        "service": "foresight-api",
        "version": "0.1.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


# Routers wired up on Day 5
# app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
# app.include_router(assets.router, prefix="/assets", tags=["Assets"])
# app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
# app.include_router(predictions.router, prefix="/predict", tags=["Predictions"])
# app.include_router(rules.router, prefix="/rules", tags=["Rules"])
# app.include_router(reports.router, prefix="/reports", tags=["Reports"])
