#!/bin/bash
# =============================================================================
# FORESIGHT — Startup Script
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Main
# =============================================================================

log_info "Starting FORESIGHT platform..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker first."
    exit 1
fi

# Check for .env file
if [ ! -f .env ]; then
    log_warn ".env file not found. Copying from .env.template..."
    cp .env.template .env
    log_info "Please review and customize the .env file before continuing."
fi

# Create necessary directories
log_info "Creating data directories..."
mkdir -p data/raw data/processed data/models
mkdir -p logs/airflow logs/spark logs/api

# Start infrastructure services
log_info "Starting infrastructure services..."
docker-compose up -d zookeeper kafka postgres mongodb minio

# Wait for services to be healthy
log_info "Waiting for services to be healthy..."
sleep 10

# Initialize databases
log_info "Initializing databases..."
docker-compose exec -T postgres psql -U foresight -d foresight < infrastructure/docker/postgres/init.sql 2>/dev/null || true

# Initialize MinIO buckets
log_info "Initializing MinIO buckets..."
docker-compose up -d minio-init

# Start Spark
log_info "Starting Apache Spark..."
docker-compose up -d spark-master spark-worker-1 spark-worker-2

# Start MLflow
log_info "Starting MLflow..."
docker-compose up -d mlflow

# Start Airflow
log_info "Starting Apache Airflow..."
docker-compose up -d airflow-init
docker-compose up -d airflow-webserver airflow-scheduler

# Start API
log_info "Starting FastAPI..."
docker-compose up -d api

log_info "==================================================================="
log_info "FORESIGHT platform is starting up!"
log_info "==================================================================="
log_info ""
log_info "Services will be available at:"
log_info "  - API:           http://localhost:8000"
log_info "  - API Docs:      http://localhost:8000/docs"
log_info "  - Airflow:       http://localhost:8085 (admin/admin)"
log_info "  - MLflow:        http://localhost:5000"
log_info "  - Kafka UI:      http://localhost:8090"
log_info "  - Spark Master:  http://localhost:8080"
log_info "  - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
log_info ""
log_info "Default login: admin@assetpulse.local / admin123"
log_info ""
log_info "==================================================================="

# Check service health
log_info "Checking service health..."
sleep 5

if curl -s http://localhost:8000/health > /dev/null; then
    log_info "✅ API is healthy"
else
    log_warn "⚠️  API health check failed - may still be starting up"
fi

log_info ""
log_info "To view logs: docker-compose logs -f [service]"
log_info "To stop: docker-compose down"
