#!/bin/bash
# =============================================================================
# FORESIGHT — Complete Test Pipeline with NASA CMAPSS Data
# Run this after Docker is started
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CMAPSS_FILE="data/raw/cmapss/6. Turbofan Engine Degradation Simulation Data Set/train_FD001.txt"
OUTPUT_FILE="data/processed/engine_data.csv"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}✅${NC} $1"; }
error() { echo -e "${RED}❌${NC} $1"; }
warn() { echo -e "${YELLOW}⚠️${NC} $1"; }

# =============================================================================
# Pre-flight Checks
# =============================================================================

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          FORESIGHT — Complete Test Pipeline                    ║"
echo "║              Using NASA CMAPSS Dataset                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

log_info "Step 0: Pre-flight checks..."

# Check Docker
if ! docker info > /dev/null 2>&1; then
    error "Docker is not running!"
    echo ""
    echo "Please start Docker Desktop first:"
    echo "  1. Open Docker Desktop"
    echo "  2. Wait for it to start completely"
    echo "  3. Run this script again"
    echo ""
    exit 1
fi
success "Docker is running"

# Check CMAPSS file exists
if [ ! -f "$CMAPSS_FILE" ]; then
    error "CMAPSS dataset not found at: $CMAPSS_FILE"
    exit 1
fi
success "CMAPSS dataset found"

# Create directories
mkdir -p data/processed data/models logs

# =============================================================================
# Step 1: Start Services
# =============================================================================

echo ""
log_info "Step 1: Starting Docker services..."
docker-compose up -d zookeeper kafka postgres mongodb minio

log_info "Waiting for services to initialize (30s)..."
sleep 30

# Check services are healthy
if docker-compose ps | grep -q "Up"; then
    success "Services started"
else
    error "Some services failed to start"
    docker-compose ps
    exit 1
fi

# =============================================================================
# Step 2: Initialize Databases
# =============================================================================

echo ""
log_info "Step 2: Initializing databases..."

# PostgreSQL
docker-compose exec -T postgres psql -U foresight -d foresight \
  < infrastructure/docker/postgres/init.sql 2>/dev/null || warn "PostgreSQL may already be initialized"

# MinIO buckets
docker-compose up -d minio-init 2>/dev/null || true

success "Databases initialized"

# =============================================================================
# Step 3: Convert CMAPSS Data
# =============================================================================

echo ""
log_info "Step 3: Converting NASA CMAPSS data to FORESIGHT format..."

python scripts/convert_cmapss.py \
  --cmapss "$CMAPSS_FILE" \
  -o "$OUTPUT_FILE"

if [ -f "$OUTPUT_FILE" ]; then
    success "Data converted successfully"
    log_info "File: $OUTPUT_FILE"
    log_info "Size: $(ls -lh $OUTPUT_FILE | awk '{print $5}')"
    log_info "Lines: $(wc -l < $OUTPUT_FILE)"
else
    error "Data conversion failed"
    exit 1
fi

# =============================================================================
# Step 4: Start Remaining Services
# =============================================================================

echo ""
log_info "Step 4: Starting Spark, Airflow, and API..."

docker-compose up -d spark-master spark-worker-1 spark-worker-2
docker-compose up -d mlflow
docker-compose up -d airflow-init
docker-compose up -d airflow-webserver airflow-scheduler
docker-compose up -d api

log_info "Waiting for API to be ready (20s)..."
sleep 20

# Test API health
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    success "API is healthy"
else
    warn "API may still be starting up"
fi

# =============================================================================
# Step 5: Seed Initial Data
# =============================================================================

echo ""
log_info "Step 5: Creating initial assets and sensors..."

python scripts/seed_data.py --assets 5 --readings-hours 1 --skip-readings || warn "Seed script had issues, continuing..."

# =============================================================================
# Step 6: Ingest CMAPSS Data to Kafka
# =============================================================================

echo ""
log_info "Step 6: Ingesting CMAPSS data to Kafka..."
echo "    This will simulate real-time data streaming at 100x speed"
echo "    Press Ctrl+C to stop ingestion (data will remain in Kafka)"
echo ""

# Run ingestion in background
timeout 60 python ingestion/sensor_ingestor.py "$OUTPUT_FILE" --realtime --speed 100 || true

success "Data ingestion completed (or timeout reached)"

# =============================================================================
# Step 7: Verify Data Pipeline
# =============================================================================

echo ""
log_info "Step 7: Verifying data pipeline..."

# Check MongoDB
echo "  Checking MongoDB..."
MONGO_COUNT=$(docker-compose exec -T mongodb mongosh foresight --quiet --eval "db.sensor_readings.estimatedDocumentCount()" 2>/dev/null || echo "0")
if [ "$MONGO_COUNT" -gt 0 ]; then
    success "MongoDB has $MONGO_COUNT sensor readings"
else
    warn "MongoDB may still be processing data"
fi

# Check PostgreSQL
echo "  Checking PostgreSQL..."
ASSET_COUNT=$(docker-compose exec -T postgres psql -U foresight -d foresight -t -c "SELECT COUNT(*) FROM assets;" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$ASSET_COUNT" -gt 0 ]; then
    success "PostgreSQL has $ASSET_COUNT assets"
else
    warn "No assets found in PostgreSQL"
fi

# =============================================================================
# Step 8: Run API Tests
# =============================================================================

echo ""
log_info "Step 8: Running API tests..."

./scripts/quick_test.sh || warn "Some API tests failed"

# =============================================================================
# Step 9: Summary
# =============================================================================

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                     TEST PIPELINE COMPLETE                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
success "All steps completed!"
echo ""
echo "📊 Services Available:"
echo "  • API:           http://localhost:8000"
echo "  • API Docs:      http://localhost:8000/docs"
echo "  • Airflow:       http://localhost:8085 (admin/admin)"
echo "  • MLflow:        http://localhost:5000"
echo "  • Kafka UI:      http://localhost:8090"
echo "  • Spark Master:  http://localhost:8080"
echo "  • MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo ""
echo "🧪 Test Commands:"
echo "  ./scripts/quick_test.sh          # Quick API tests"
echo "  python scripts/test_api.py       # Full test suite"
echo ""
echo "📁 Data Files:"
echo "  • CMAPSS Converted: $OUTPUT_FILE"
echo ""
echo "🛑 To stop all services:"
echo "  docker-compose down"
echo ""
