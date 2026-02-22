# FORESIGHT — Deployment Guide

Complete deployment instructions for the AssetPulse predictive maintenance platform.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Production Deployment](#production-deployment)
5. [Data Ingestion](#data-ingestion)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **Docker** (v24.0+) and **Docker Compose** (v2.20+)
- **Python** (v3.11+) - for local development
- **Git**

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32+ GB |
| Disk | 50 GB SSD | 100+ GB SSD |

---

## Quick Start

### 1. Clone and Setup

```bash
cd /Users/yashbishnoi/Downloads/Foresight

# Copy environment configuration
cp .env.template .env

# Edit configuration (optional)
nano .env
```

### 2. Start the Platform

```bash
# Using the startup script
chmod +x scripts/start.sh
./scripts/start.sh

# Or manually with Docker Compose
docker-compose up -d
```

### 3. Verify Services

Wait 1-2 minutes for all services to start, then verify:

```bash
# Check all services are running
docker-compose ps

# Test API health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

### 4. Seed Sample Data

```bash
# Install Python dependencies
pip install asyncpg kafka-python

# Seed with sample data
python scripts/seed_data.py --assets 10 --readings-hours 24
```

---

## Configuration

### Environment Variables

Key configuration options in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | Secret for JWT tokens | (required) |
| `POSTGRES_PASSWORD` | PostgreSQL password | foresight |
| `MONGO_ROOT_PASSWORD` | MongoDB password | admin |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | localhost:29092 |
| `MLFLOW_TRACKING_URI` | MLflow server URL | http://localhost:5000 |

### Service Ports

| Service | Port | URL |
|---------|------|-----|
| FastAPI | 8000 | http://localhost:8000 |
| Airflow | 8085 | http://localhost:8085 |
| MLflow | 5000 | http://localhost:5000 |
| Kafka UI | 8090 | http://localhost:8090 |
| Spark Master | 8080 | http://localhost:8080 |
| MinIO Console | 9001 | http://localhost:9001 |
| PostgreSQL | 5432 | localhost:5432 |
| MongoDB | 27017 | localhost:27017 |
| Kafka | 9092 | localhost:29092 |

---

## Data Ingestion

### Option 1: CSV File Ingestion

Prepare a CSV file with sensor data:

```csv
timestamp,asset_id,sensor_id,sensor_type,value,unit
2024-01-15T10:00:00Z,ASSET-1000,SNS-ASSET-1000-TEMP,temperature,75.5,celsius
2024-01-15T10:00:00Z,ASSET-1000,SNS-ASSET-1000-VIB,vibration,5.2,mm/s
```

Ingest the data:

```bash
python ingestion/sensor_ingestor.py data/your_sensors.csv --realtime --speed 10
```

### Option 2: Real-time Sensor Integration

For production sensors, configure your IoT gateway to publish to Kafka:

```python
from kafka import KafkaProducer
import json

producer = KafkaProducer(bootstrap_servers='localhost:29092')

reading = {
    "timestamp": "2024-01-15T10:00:00Z",
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "asset_id": "ASSET-1000",
    "sensor_id": "SNS-001",
    "sensor_type": "temperature",
    "value": 75.5,
    "unit": "celsius"
}

producer.send("sensor_readings", json.dumps(reading).encode())
```

### Option 3: SAP/Asset Suite Integration

Configure connectors in the ingestion module:

```python
# ingestion/sap_connector.py
from ingestion.sap_connector import SAPConnector

sap = SAPConnector(
    host="sap-server.company.com",
    system_number="00",
    client="100"
)

# Sync equipment master data
sap.sync_equipment_to_foresight()
```

---

## Production Deployment

### Docker Compose Production Profile

```bash
# Use production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Kubernetes Deployment

```bash
# Build and push images
docker build -t your-registry/foresight-api:latest ./api
docker push your-registry/foresight-api:latest

# Deploy with Helm
cd infrastructure/kubernetes/helm/foresight
helm upgrade --install foresight . \
  --namespace foresight \
  --values values-production.yaml
```

### Key Production Considerations

1. **Security**
   - Change all default passwords
   - Enable TLS/SSL certificates
   - Configure proper firewall rules
   - Use secrets management (AWS Secrets Manager, HashiCorp Vault)

2. **High Availability**
   - Run multiple Kafka brokers (3+)
   - Use PostgreSQL replication
   - Deploy multiple API replicas
   - Configure MongoDB replica set

3. **Monitoring**
   - Enable Prometheus metrics
   - Set up Grafana dashboards
   - Configure log aggregation (ELK/Loki)
   - Set up alerting (PagerDuty, Slack)

---

## Monitoring

### Service Health Checks

```bash
# API health
curl http://localhost:8000/health

# Database connectivity
curl http://localhost:8000/health/ready

# Airflow health
curl http://localhost:8085/health

# Spark Master
curl http://localhost:8080/json/
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f spark-master
docker-compose logs -f airflow-scheduler
```

### Metrics Endpoints

- **API**: `http://localhost:8000/metrics` (Prometheus)
- **Spark**: `http://localhost:8080/metrics`
- **Airflow**: Built-in statsd metrics

---

## Troubleshooting

### Common Issues

#### 1. Services fail to start

```bash
# Check Docker resources
docker system df
docker system prune -a

# Restart services
docker-compose down
docker-compose up -d
```

#### 2. Database connection errors

```bash
# Verify PostgreSQL is running
docker-compose exec postgres pg_isready -U foresight

# Check logs
docker-compose logs postgres

# Reset database (WARNING: data loss)
docker-compose down -v
docker-compose up -d postgres
```

#### 3. Kafka connection issues

```bash
# List Kafka topics
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Check consumer groups
docker-compose exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --list
```

#### 4. MLflow not tracking experiments

```bash
# Check MLflow can access S3/MinIO
docker-compose exec mlflow mc ls local/mlflow

# Verify database connection
docker-compose exec mlflow mlflow db upgrade
```

### Getting Help

- **API Documentation**: http://localhost:8000/docs
- **GitHub Issues**: Create an issue in the repository
- **Logs**: Check `docker-compose logs` for error details

---

## Next Steps

1. **Create your first asset**: Use the API at `/assets/{tenant_id}`
2. **Set up alert rules**: Configure at `/alerts/{tenant_id}/rules`
3. **View the dashboard**: Access the React dashboard at http://localhost:5173
4. **Schedule pipelines**: Configure Airflow DAGs at http://localhost:8085
5. **Train ML models**: Trigger model training via the weekly DAG

---

## API Quick Reference

### Authentication

```bash
# Get token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@assetpulse.local","password":"admin123"}'

# Use token
curl http://localhost:8000/assets/{tenant_id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Create Asset

```bash
curl -X POST http://localhost:8000/assets/{tenant_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "PUMP-001",
    "name": "Main Process Pump",
    "asset_type": "pump",
    "criticality": "critical",
    "location": "Building A"
  }'
```

### Get Health Prediction

```bash
curl -X POST http://localhost:8000/predict/{tenant_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"asset_id": "ASSET-UUID-HERE"}'
```

---

**Version**: 1.0.0  
**Last Updated**: 2024
