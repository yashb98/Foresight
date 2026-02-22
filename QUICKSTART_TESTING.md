# FORESIGHT — Quick Start Testing

Get the platform running and tested in 10 minutes.

---

## 🚀 Step 1: Start the Platform

```bash
cd /Users/yashbishnoi/Downloads/Foresight

# Start all services
./scripts/start.sh

# Wait 2-3 minutes for all services to start
```

Verify services are running:
```bash
docker-compose ps
```

---

## 🧪 Step 2: Run Quick Tests

### Option A: Bash Script (Fastest)

```bash
# Test with curl + jq
./scripts/quick_test.sh
```

### Option B: Python Test Suite (Comprehensive)

```bash
# Install dependencies
pip install requests jq

# Run full test suite
python scripts/test_api.py
```

---

## 📊 Step 3: Add Test Data

### Choose Your Data Source:

#### A) Use NASA CMAPSS Dataset (Real Engine Data)

```bash
# Convert CMAPSS data
python scripts/convert_cmapss.py \
  --cmapss "data/raw/cmapss/6. Turbofan Engine Degradation Simulation Data Set/train_FD001.txt" \
  -o data/processed/engine_data.csv

# Ingest to Kafka
python ingestion/sensor_ingestor.py data/processed/engine_data.csv --realtime --speed 100
```

**What you get:** 100 aircraft engines with temperature, pressure, RPM data

---

#### B) Generate Synthetic Data (Quickest)

```bash
# Generate 10 assets, 24 hours of data
python scripts/seed_data.py --assets 10 --readings-hours 24
```

**What you get:** Pumps/motors with temperature, vibration, pressure sensors

---

#### C) Create Your Own CSV

```bash
# Generate template
python scripts/convert_cmapss.py --generate --assets 3 --hours 1

# File created at: data/processed/sensor_readings.csv

# Ingest it
python ingestion/sensor_ingestor.py data/processed/sensor_readings.csv
```

---

## ✅ Step 4: Verify Data Flow

### Check API Has Data

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@assetpulse.local","password":"admin123"}' \
  | jq -r '.access_token')

# Check assets
curl -s http://localhost:8000/assets/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" | jq '.total'

# Should show: 10 (or however many you created)
```

### Check MongoDB Has Sensor Data

```bash
# Count sensor readings
docker-compose exec mongodb mongosh foresight --eval \
  "db.sensor_readings.estimatedDocumentCount()"

# Should show: 1000+ documents
```

### Check Kafka Has Messages

```bash
# List topics
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Should show: sensor_readings
```

---

## 📈 Step 5: Explore Features

### 1. View API Documentation

```bash
open http://localhost:8000/docs
```

### 2. Check Dashboard Data

```bash
curl -s http://localhost:8000/reports/550e8400-e29b-41d4-a716-446655440000/dashboard \
  -H "Authorization: Bearer $TOKEN" | jq
```

### 3. Get Health Predictions

```bash
# First, get an asset ID
ASSET_ID=$(curl -s http://localhost:8000/assets/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')

# Get prediction
curl -s -X POST http://localhost:8000/predict/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"asset_id\": \"$ASSET_ID\"}" | jq
```

### 4. View Airflow DAGs

```bash
open http://localhost:8085
# Login: admin / admin
```

### 5. View MLflow

```bash
open http://localhost:5000
```

---

## 🐛 Troubleshooting

### "Connection refused" errors

```bash
# Check if API is running
docker-compose ps api

# Check logs
docker-compose logs api | tail -20

# Restart if needed
docker-compose restart api
```

### No data appearing

```bash
# Verify Kafka topic exists
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Check MongoDB
docker-compose exec mongodb mongosh foresight --eval "show collections"
```

### Authentication fails

```bash
# Re-initialize database
docker-compose exec -T postgres psql -U foresight \
  < infrastructure/docker/postgres/init.sql
```

---

## 📊 Test Data Summary

| Data Source | Records | Assets | Sensors | Best For |
|-------------|---------|--------|---------|----------|
| CMAPSS (train_FD001) | ~20,000 | 100 | 21/engine | ML training, anomaly detection |
| Seed data (default) | ~2,880 | 10 | 4/asset | Quick functional testing |
| Custom CSV | Variable | Custom | Custom | Your specific use case |

---

## 🎯 What to Test

### Essential API Endpoints

| Endpoint | Test With | Expected Result |
|----------|-----------|-----------------|
| `GET /health` | curl | `{"status": "healthy"}` |
| `POST /auth/token` | curl | JWT token returned |
| `GET /assets/{tenant}` | curl | List of assets |
| `POST /assets/{tenant}` | curl | Created asset object |
| `GET /reports/{tenant}/dashboard` | curl | Dashboard data JSON |
| `POST /predict/{tenant}` | curl | Health score + recommendation |

### Data Pipeline Verification

| Component | Check Command | Expected |
|-----------|---------------|----------|
| Kafka | List topics | `sensor_readings` exists |
| MongoDB | Count documents | 1000+ readings |
| PostgreSQL | Query assets | Assets exist |
| Spark | Check UI | Streaming job active |

---

## ✅ Success Checklist

After following this guide, verify:

- [ ] All Docker containers running (`docker-compose ps`)
- [ ] API responds at `http://localhost:8000/health`
- [ ] Can login and get JWT token
- [ ] Assets created in database
- [ ] Sensor data in MongoDB
- [ ] Dashboard API returns data
- [ ] Health predictions work
- [ ] Airflow UI accessible
- [ ] MLflow UI accessible

---

## 🚀 Next Steps

1. **Connect real sensors**: Edit `ingestion/sensor_ingestor.py` for your data source
2. **Train ML models**: Trigger the weekly DAG in Airflow
3. **Set up alerts**: Create alert rules via API
4. **Customize dashboard**: Modify the React frontend

---

## 📚 Resources

- **Full Testing Guide**: `TESTING_GUIDE.md`
- **Deployment Guide**: `DEPLOYMENT.md`
- **API Docs**: `http://localhost:8000/docs`
- **Project Summary**: `PROJECT_SUMMARY.md`

---

**Time to complete**: ~10 minutes  
**Prerequisites**: Docker, Docker Compose, Python 3.11+
