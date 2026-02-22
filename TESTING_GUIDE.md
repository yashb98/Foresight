# FORESIGHT — Testing Guide

Complete guide for testing the AssetPulse platform with real data.

---

## 📊 Test Data Options

### Option 1: NASA CMAPSS Dataset (Recommended)

You already have this! It's real turbofan engine degradation data.

```bash
# Convert CMAPSS to FORESIGHT format
python scripts/convert_cmapss.py \
  --cmapss "data/raw/cmapss/6. Turbofan Engine Degradation Simulation Data Set/train_FD001.txt" \
  -o data/processed/cmapss_converted.csv

# Ingest the data
python ingestion/sensor_ingestor.py data/processed/cmapss_converted.csv
```

**What's in CMAPSS:**
- 100 aircraft engines
- 21 sensor readings per engine
- Temperature, pressure, RPM data
- Failure data for ML training

---

### Option 2: Generate Synthetic Test Data

```bash
# Generate 5 assets with 24 hours of data
python scripts/convert_cmapss.py --generate --assets 5 --hours 24

# Or use the seed script (creates assets + data)
python scripts/seed_data.py --assets 10 --readings-hours 24
```

**Generated data includes:**
- Temperature sensors (60-90°C)
- Vibration sensors (2-12 mm/s)
- Pressure sensors (10-45 bar)
- Flow sensors (50-180 m³/h)

---

### Option 3: Create Your Own CSV

Create a file `my_sensors.csv`:

```csv
timestamp,tenant_id,asset_id,sensor_id,sensor_type,value,unit
2024-01-15T10:00:00Z,550e8400-e29b-41d4-a716-446655440000,PUMP-1000,PUMP-1000-TEMP,temperature,75.5,celsius
2024-01-15T10:00:00Z,550e8400-e29b-41d4-a716-446655440000,PUMP-1000,PUMP-1000-VIB,vibration,5.2,mm/s
2024-01-15T10:00:00Z,550e8400-e29b-41d4-a716-446655440000,PUMP-1000,PUMP-1000-PRES,pressure,30.1,bar
2024-01-15T10:05:00Z,550e8400-e29b-41d4-a716-446655440000,PUMP-1000,PUMP-1000-TEMP,temperature,76.1,celsius
2024-01-15T10:05:00Z,550e8400-e29b-41d4-a716-446655440000,PUMP-1000,PUMP-1000-VIB,vibration,5.4,mm/s
```

Ingest it:
```bash
python ingestion/sensor_ingestor.py my_sensors.csv
```

---

### Option 4: Real-time Data via API

Send data directly to Kafka using Python:

```python
from kafka import KafkaProducer
import json
from datetime import datetime
import time

producer = KafkaProducer(
    bootstrap_servers='localhost:29092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Send sensor reading
reading = {
    "timestamp": datetime.utcnow().isoformat(),
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "asset_id": "PUMP-1000",
    "sensor_id": "PUMP-1000-TEMP",
    "sensor_type": "temperature",
    "value": 78.5,
    "unit": "celsius",
    "quality": "good"
}

producer.send('sensor_readings', reading)
producer.flush()
```

---

## 🧪 Testing APIs

### Quick Test Script

```bash
# Run comprehensive API tests
python scripts/test_api.py
```

This tests:
- ✅ Health checks
- ✅ Authentication
- ✅ Asset CRUD
- ✅ Sensor management
- ✅ Maintenance records
- ✅ Alert rules
- ✅ Predictions
- ✅ Reports

---

### Manual API Testing

#### 1. Health Check

```bash
curl http://localhost:8000/health
```

Expected: `{"status": "healthy"}`

---

#### 2. Login

```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@assetpulse.local",
    "password": "admin123"
  }'
```

Save the token:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@assetpulse.local","password":"admin123"}' \
  | jq -r '.access_token')
```

---

#### 3. Create an Asset

```bash
curl -X POST http://localhost:8000/assets/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "PUMP-001",
    "name": "Main Process Pump",
    "asset_type": "pump",
    "criticality": "critical",
    "manufacturer": "Grundfos",
    "location": "Building A",
    "department": "Production"
  }'
```

---

#### 4. Add Sensors to Asset

```bash
curl -X POST http://localhost:8000/assets/550e8400-e29b-41d4-a716-446655440000/PUMP-001/sensors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": "PUMP-001-TEMP",
    "name": "Motor Temperature",
    "sensor_type": "temperature",
    "unit": "celsius",
    "min_threshold": 20,
    "max_threshold": 90
  }'
```

---

#### 5. Create Alert Rule

```bash
curl -X POST http://localhost:8000/alerts/550e8400-e29b-41d4-a716-446655440000/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Temperature Alert",
    "metric": "temperature",
    "operator": ">",
    "threshold_value": 85,
    "severity": "warning"
  }'
```

---

#### 6. Get Health Prediction

```bash
curl -X POST http://localhost:8000/predict/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "YOUR-ASSET-UUID",
    "features": {
      "temp_avg_7d": 80.5,
      "vibration_avg_7d": 6.2,
      "days_since_maintenance": 30
    }
  }'
```

---

#### 7. Get Dashboard Data

```bash
curl http://localhost:8000/reports/550e8400-e29b-41d4-a716-446655440000/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🔄 End-to-End Test Workflow

### Complete Test Scenario

```bash
# 1. Start the platform
./scripts/start.sh

# 2. Wait for services (check with)
docker-compose ps

# 3. Generate test data
python scripts/seed_data.py --assets 5 --readings-hours 48

# 4. Run API tests
python scripts/test_api.py

# 5. Check streaming pipeline
curl http://localhost:8000/reports/550e8400-e29b-41d4-a716-446655440000/summary

# 6. Trigger Airflow DAG manually (optional)
curl -X POST http://localhost:8085/api/v1/dags/daily_feature_pipeline/dagRuns \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{"conf": {}}'
```

---

## 📋 Testing Checklist

### Infrastructure
- [ ] All Docker containers running
- [ ] PostgreSQL accepting connections
- [ ] MongoDB accepting connections
- [ ] Kafka brokers healthy
- [ ] Spark Master UI accessible
- [ ] Airflow webserver responding
- [ ] MLflow tracking server up

### API Functionality
- [ ] Health endpoints respond
- [ ] Authentication works
- [ ] Can create assets
- [ ] Can add sensors
- [ ] Can create maintenance records
- [ ] Can create alert rules
- [ ] Can list/query alerts
- [ ] Predictions return scores
- [ ] Reports generate correctly

### Data Pipeline
- [ ] Can ingest CSV data
- [ ] Kafka receives messages
- [ ] Spark processes streams
- [ ] MongoDB stores aggregations
- [ ] Airflow DAGs run successfully
- [ ] Features are computed
- [ ] Health scores are generated

### Streaming
- [ ] Real-time sensor data flows
- [ ] 5-minute aggregations created
- [ ] 1-hour aggregations created
- [ ] Alerts trigger on thresholds
- [ ] Data in MongoDB time-series collections

---

## 🐛 Common Test Issues

### Issue: "Connection refused" to API

**Fix:**
```bash
# Check if API is running
docker-compose ps api

# Check logs
docker-compose logs api

# Restart API
docker-compose restart api
```

### Issue: "No such file" for test data

**Fix:**
```bash
# Create directories
mkdir -p data/processed data/raw

# Generate test data
python scripts/convert_cmapss.py --generate
```

### Issue: Kafka not receiving messages

**Fix:**
```bash
# Check Kafka topics
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Create topic if needed
docker-compose exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --create --topic sensor_readings \
  --partitions 6 --replication-factor 1
```

### Issue: Authentication fails

**Fix:**
```bash
# Check database has admin user
docker-compose exec postgres psql -U foresight -d foresight \
  -c "SELECT email FROM users;"

# If empty, re-run init
docker-compose exec -T postgres psql -U foresight \
  < infrastructure/docker/postgres/init.sql
```

---

## 📈 Load Testing

Test with k6 (install first: `brew install k6`):

```bash
# Run load test
k6 run tests/load/load_test.js
```

Or simple curl loop:

```bash
# Simple load test
for i in {1..100}; do
  curl -s http://localhost:8000/health > /dev/null
  echo "Request $i"
done
```

---

## 🔍 Verification Commands

```bash
# Check all services
docker-compose ps

# View API logs
docker-compose logs -f api

# Check database tables
docker-compose exec postgres psql -U foresight -d foresight -c "\dt"

# Check MongoDB collections
docker-compose exec mongodb mongosh foresight --eval "show collections"

# Check Kafka consumer groups
docker-compose exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --list

# View Airflow DAGs
curl -u admin:admin http://localhost:8085/api/v1/dags
```

---

## ✅ Success Criteria

Your setup is working if:

1. ✅ `curl http://localhost:8000/health` returns `{"status": "healthy"}`
2. ✅ You can login and get a JWT token
3. ✅ You can create assets via API
4. ✅ Sensor data appears in MongoDB after ingestion
5. ✅ Spark UI shows active streaming jobs
6. ✅ Airflow DAGs complete successfully
7. ✅ Health predictions return scores
8. ✅ Dashboard data loads correctly

---

## 📚 Next Steps

After testing:

1. **Add real sensors**: Configure MQTT or OPC-UA connectors
2. **Connect SAP**: Set up SAP PM connector credentials
3. **Train ML models**: Let weekly DAG run or trigger manually
4. **Configure alerts**: Set up email/Slack notifications
5. **Customize dashboard**: Modify React frontend for your needs

---

**Need help?** Check logs with `docker-compose logs [service]`
