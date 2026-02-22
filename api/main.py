# =============================================================================
# FORESIGHT API — Main FastAPI Application
# =============================================================================

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routers import auth, assets, alerts, predictions, reports, realtime
from api.dependencies import close_postgres_pool, close_mongo_client, get_postgres_pool
from common.config import settings
from common.logging_config import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)


# =============================================================================
# Lifespan Event Handler
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting up FORESIGHT API...")
    try:
        # Initialize database pools
        await get_postgres_pool()
        logger.info("Database pool initialized")
        
        # Start Kafka-to-WebSocket streaming bridge
        from api.routers.streaming_ws import start_streaming_bridge, stop_streaming_bridge
        start_streaming_bridge()
        logger.info("Streaming bridge started")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down FORESIGHT API...")
    try:
        from api.routers.streaming_ws import stop_streaming_bridge
        stop_streaming_bridge()
    except:
        pass
    await close_postgres_pool()
    await close_mongo_client()
    logger.info("Cleanup completed")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="FORESIGHT — Predictive Asset Maintenance API",
    description="""
    Multi-tenant SaaS platform for predictive maintenance and asset health monitoring.
    
    ## Features
    
    - **Asset Management**: Register and monitor industrial assets
    - **Sensor Integration**: Real-time sensor data ingestion
    - **Health Predictions**: ML-based failure prediction
    - **Alerting**: Configurable threshold and anomaly alerts
    - **Maintenance Tracking**: Work order and maintenance history
    - **Reporting**: Comprehensive analytics and dashboards
    
    ## Authentication
    
    All endpoints require JWT authentication. Obtain a token via `/auth/token`.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# =============================================================================
# Middleware
# =============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    import time
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s"
    )
    
    return response


# =============================================================================
# Exception Handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


# =============================================================================
# Routers
# =============================================================================

app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(alerts.router)
app.include_router(predictions.router)
app.include_router(reports.router)
app.include_router(realtime.router)

# Serve static files (for real-time test dashboard)
app.mount("/static", StaticFiles(directory="dashboard/public"), name="static")


# =============================================================================
# Health Check Endpoints
# =============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": asyncio.get_event_loop().time()
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness probe for Kubernetes."""
    try:
        # Check database connectivity
        pool = await get_postgres_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(e)}
        )


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/", tags=["Root"])
async def root():
    """API root with basic information."""
    return {
        "name": "FORESIGHT API",
        "version": "1.0.0",
        "description": "Predictive Asset Maintenance Platform",
        "documentation": "/docs",
        "health": "/health"
    }


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
