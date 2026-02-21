# FORESIGHT — Predictive Asset Maintenance Platform

> **Know before it breaks.**

FORESIGHT is a production-grade, multi-tenant SaaS platform that ingests real-time sensor
and maintenance data from enterprise asset management systems (SAP, Asset Suite 9),
predicts equipment failures using ML, and surfaces actionable insights via a live dashboard.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — INGESTION                                                        │
│  Sensor Simulator ──┐                                                       │
│  SAP Connector ─────┼──► Kafka (sensor-readings, maintenance-events)        │
│  Asset Suite 9 ─────┘         │                      │                     │
│                               │              MinIO (raw data lake)          │
├───────────────────────────────┼─────────────────────────────────────────────┤
│  LAYER 2 — STREAM PROCESSING  │                                             │
│  Spark Structured Streaming ◄─┘                                             │
│  • 5-min / 1-hour / 24-hour windowed aggregations                           │
│  • Threshold rule evaluation → Kafka (asset-alerts)                         │
│  • Writes to MongoDB (sensor_readings, aggregated_readings)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 3 — BATCH PROCESSING (Airflow DAGs)                                  │
│  daily_scoring_dag → feature engineering (PySpark) → ML scoring             │
│  → asset_health_scores (PostgreSQL)                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 4 — ML LAYER                                                         │
│  Random Forest + XGBoost → MLflow (experiment tracking + model registry)   │
│  weekly_retraining_dag → champion/challenger promotion                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 5 — API LAYER (FastAPI)                                              │
│  JWT auth · Tenant isolation · OpenAPI docs at /docs                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 6 — DASHBOARD (React + Recharts)                                     │
│  KPI cards · Asset heatmap · Sensor charts · Alert feed · Reports           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Ingestion | Python 3.11, Apache Kafka 3.6, Confluent Platform |
| Stream Processing | Apache Spark 3.5 Structured Streaming (PySpark) |
| Batch Processing | Apache Spark 3.5, Apache Hive 3.1 |
| Orchestration | Apache Airflow 2.8 |
| Relational DB | PostgreSQL 15 |
| Time-series DB | MongoDB 6.0 |
| Object Store | MinIO (S3-compatible) |
| ML | scikit-learn 1.4, XGBoost 2.0, MLflow 2.10, SHAP |
| API | FastAPI 0.111, Pydantic v2, python-jose JWT |
| Dashboard | React 18, Vite 5, Recharts, Tailwind CSS, shadcn/ui |
| Containers | Docker 25, Docker Compose v2 |
| Production | Kubernetes 1.29, Helm |
| CI/CD | GitHub Actions |
| Reporting | openpyxl, fpdf2 |

---

## Quick Start (Local Development)

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) — v25+
- Python 3.11+ (for running connectors and scripts locally)
- Node.js 20+ (for dashboard development)
- 16 GB RAM recommended (all services together use ~8 GB)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/foresight.git
cd foresight
cp .env.template .env
# Edit .env — change ALL passwords before running
```

### 2. Start all services

```bash
docker compose up -d
docker compose ps          # all services should show 'healthy'
```

### 3. Run database migrations

```bash
# From project root (with DATABASE_URL_SYNC in .env)
alembic -c infrastructure/migrations/alembic.ini upgrade head
```

### 4. Seed test data

```bash
python seed.py --tenant-count 2 --asset-count 30
```

### 5. Verify everything is working

```bash
pytest tests/unit/test_db.py -v
```

---

## Service URLs

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| FastAPI + Swagger UI | http://localhost:8000/docs | Use `/auth/token` to get JWT |
| React Dashboard | http://localhost:3000 | tenant1 / password123 |
| Airflow UI | http://localhost:8085 | admin / (set in .env) |
| MLflow UI | http://localhost:5000 | No auth in dev |
| Spark Master UI | http://localhost:8080 | No auth in dev |
| MinIO Console | http://localhost:9001 | minioadmin / (set in .env) |
| Kafka UI | http://localhost:8090 | No auth in dev |
| PostgreSQL | localhost:5432 | (from .env) |
| MongoDB | localhost:27017 | (from .env) |

---

## Common Commands

```bash
# Start all services
docker compose up -d

# View logs for a specific service
docker compose logs -f kafka
docker compose logs -f api

# Stop everything (preserves data volumes)
docker compose down

# Stop and wipe all data (clean slate)
docker compose down -v

# Run all tests
pytest tests/ --cov=. --cov-report=html

# Lint + format check
black --check . && flake8 .

# Type check
mypy common/ api/ --ignore-missing-imports

# Apply DB migration
alembic -c infrastructure/migrations/alembic.ini upgrade head

# Rollback one migration
alembic -c infrastructure/migrations/alembic.ini downgrade -1

# Re-seed (wipe and reseed — dev only)
python seed.py --drop-existing --tenant-count 2 --asset-count 30

# Start sensor simulator (30 assets, 1 reading/second)
python ingestion/sensor_simulator.py --assets 30 --frequency-seconds 1

# Train ML models
python ml/training/train.py --experiment foresight-v1

# Trigger Airflow DAG manually
airflow dags trigger daily_scoring_dag --conf '{"tenant_id": "11111111-1111-1111-1111-111111111111"}'

# Start dashboard dev server
cd dashboard && npm install && npm run dev

# Run load test
locust -f tests/load_test.py --host=http://localhost:8000

# Kubernetes — apply manifests
kubectl apply -f infrastructure/kubernetes/manifests/ -n foresight-dev
kubectl get pods -n foresight-dev
kubectl logs -f deployment/foresight-api -n foresight-dev
```

---

## Project Structure

```
foresight/
├── common/                    # Shared Pydantic models, config, logging
│   ├── config.py              # Centralised Settings (pydantic-settings)
│   ├── logging_config.py      # JSON/text structured logging
│   └── models.py              # SensorReading, Alert, PredictionResult, etc.
│
├── ingestion/                 # Data ingestion layer
│   ├── sensor_simulator.py    # Time-series sensor data generator → Kafka
│   ├── sap_connector.py       # SAP PM mock connector → Kafka + MinIO
│   ├── asset_suite_connector.py # Asset Suite 9 mock → Kafka + MinIO
│   └── minio_writer.py        # S3/MinIO raw data writer utility
│
├── streaming/                 # Spark Structured Streaming
│   ├── kafka_consumer.py      # Reads sensor-readings, parses schema
│   ├── aggregations.py        # Windowed aggregations (5min/1hr/24hr)
│   ├── rules_loader.py        # Loads threshold rules from PostgreSQL
│   ├── alert_engine.py        # Evaluates rules, publishes to asset-alerts
│   └── mongodb_sink.py        # Writes processed data to MongoDB
│
├── batch/                     # Airflow DAGs + PySpark batch jobs
│   ├── dags/
│   │   ├── daily_ingestion_dag.py    # Triggers SAP + Asset Suite connectors
│   │   ├── daily_scoring_dag.py      # Feature engineering → ML scoring
│   │   └── weekly_retraining_dag.py  # Retrains + promotes ML models
│   └── jobs/
│       └── feature_engineering.py    # PySpark feature engineering job
│
├── ml/                        # Machine learning layer
│   ├── training/
│   │   └── train.py           # RF + XGBoost training, MLflow logging
│   └── serving/
│       └── predictor.py       # Loads champion model, returns PredictionResult
│
├── api/                       # FastAPI application
│   ├── main.py                # App factory, CORS, lifespan hooks
│   ├── Dockerfile             # Multi-stage production image
│   ├── routers/               # One file per resource group
│   ├── models/                # Pydantic request/response schemas
│   └── middleware/            # Auth, tenant isolation, rate limiting
│
├── dashboard/                 # React + Vite frontend
│   ├── src/
│   │   ├── api/               # Axios client + typed interfaces
│   │   ├── components/        # Reusable UI components
│   │   └── pages/             # Overview, Assets, Alerts, Reports
│   └── Dockerfile             # Multi-stage production image
│
├── infrastructure/
│   ├── migrations/            # Alembic migrations (PostgreSQL)
│   ├── db/
│   │   ├── base.py            # SQLAlchemy ORM models
│   │   └── hive_ddl.py        # Hive table creation script
│   ├── docker/
│   │   ├── postgres/init.sql  # Creates airflow + mlflow DBs
│   │   └── mongodb/init.js    # Creates collections + indexes
│   ├── kubernetes/            # K8s manifests + Helm charts
│   └── terraform/             # IaC (optional, flagged when needed)
│
├── tests/
│   ├── unit/                  # Fast, no Docker required
│   └── integration/           # Require running Docker Compose stack
│
├── docs/
│   └── architecture.md        # Mermaid architecture diagram
│
├── docker-compose.yml         # All 12 local dev services
├── .env.template              # Environment variable template
├── pyproject.toml             # Black, flake8, mypy, pytest config
├── requirements.txt           # Python dependencies
├── seed.py                    # Test data seeder
└── README.md                  # This file
```

---

## Multi-Tenancy Design

Every table, Kafka message, MongoDB document, and MinIO path includes `tenant_id`.

- **PostgreSQL**: All tables have `tenant_id` column + index. Queries always filter by `tenant_id`.
- **MongoDB**: `sensor_readings` compound index is `(tenant_id, asset_id, timestamp DESC)`.
- **MinIO**: All paths follow `/raw/{tenant_id}/{source}/{YYYY}/{MM}/{DD}/`.
- **API**: JWT tokens contain `tenant_id` claim. Every endpoint extracts it via dependency injection — cross-tenant requests return `403`.
- **Airflow**: DAGs are parameterised by `tenant_id` and triggered per tenant.

---

## Environment Variables Reference

Copy `.env.template` to `.env` and fill in all values.
All variables are described inline in the template.

**Never commit `.env` — it is gitignored.**

The key variables to change from defaults:
- `POSTGRES_PASSWORD`
- `MONGO_ROOT_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `AIRFLOW__CORE__FERNET_KEY` — generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `JWT_SECRET_KEY` — minimum 32 characters
- `AIRFLOW_ADMIN_PASSWORD`

---

## Database Schema

### PostgreSQL (6 tables)

| Table | Purpose |
|-------|---------|
| `tenants` | Customer organisations + auth credentials |
| `assets` | Monitored assets (pump, turbine, transformer, etc.) |
| `asset_health_scores` | Daily ML prediction output per asset |
| `threshold_rules` | Configurable alert rules per tenant |
| `alerts` | Triggered alert events with lifecycle status |
| `maintenance_records` | Historical maintenance events from all sources |

### MongoDB (2 collections)

| Collection | Purpose |
|-----------|---------|
| `sensor_readings` | Raw time-series sensor telemetry |
| `aggregated_readings` | Spark windowed aggregation results |

Compound index: `(tenant_id: 1, asset_id: 1, timestamp: -1)`

### Hive (2 tables)

| Table | Purpose |
|-------|---------|
| `raw_sensor_data` | Partitioned raw sensor archive |
| `feature_store` | Engineered ML features per asset per day |

---

## Test Tenants (after seeding)

| Tenant | Client ID | Password | Industry |
|--------|-----------|----------|----------|
| Meridian Power & Water | `tenant1` | `password123` | Utilities |
| TransRail Infrastructure Ltd | `tenant2` | `password456` | Rail |

---

## CI/CD Pipeline

| Trigger | Action |
|---------|--------|
| Pull Request | Lint (black, flake8, mypy) + unit tests |
| Merge to `main` | Build Docker images → deploy staging → smoke test |
| Release tag | Deploy to production |
| Weekly ML retraining | Model promotion if AUC improves >1% |

---

## Contributing

1. Create a feature branch from `main`
2. Make changes — ensure `black . && flake8 . && pytest tests/unit/` all pass
3. Open a PR using the template
4. Wait for CI to pass
5. Request review

---

## Troubleshooting

**Services won't start / port conflicts**
```bash
docker compose ps          # check which services are failing
docker compose logs kafka  # check specific service logs
```

Common port conflicts: 8080 (Spark), 5432 (PostgreSQL), 27017 (MongoDB), 9000 (MinIO), 9092 (Kafka)

**`alembic upgrade head` fails**
- Ensure `DATABASE_URL_SYNC` is set in `.env`
- Ensure PostgreSQL container is healthy: `docker compose ps postgres`

**Airflow DAGs don't appear**
- Check DAG files have no import errors: `docker compose logs airflow-scheduler`
- Verify `/batch/dags/` is mounted correctly in Docker Compose volumes

**MLflow can't connect to MinIO**
- Ensure `minio-init` completed successfully: `docker compose logs minio-init`
- Check `AWS_ENDPOINT_URL` points to `http://minio:9000` (not localhost) inside Docker

---

*FORESIGHT — Know before it breaks.*
