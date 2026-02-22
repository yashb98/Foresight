# FORESIGHT — Expected Test Results with NASA CMAPSS Data

## 📊 Dataset Overview

**NASA CMAPSS** (Commercial Modular Aero-Propulsion System Simulation)
- **Source**: NASA Prognostics Center of Excellence
- **File**: `train_FD001.txt`
- **Engines**: 100
- **Total Records**: 20,631 sensor readings
- **Sensors**: 21 per engine (temperature, pressure, RPM, etc.)
- **Purpose**: Predict remaining useful life (RUL) of turbofan engines

## 🔄 Test Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TEST PIPELINE STEPS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: START SERVICES                                                     │
│  ├── Docker containers: zookeeper, kafka, postgres, mongodb, minio         │
│  └── Status: ✅ All services healthy                                        │
│                                                                             │
│  STEP 2: CONVERT CMAPSS                                                     │
│  ├── Input: 20,631 raw records                                              │
│  ├── Output: ~80,000 sensor readings (4 sensor types per engine)           │
│  └── File: data/processed/engine_data.csv                                   │
│                                                                             │
│  STEP 3: START STREAMING SERVICES                                          │
│  ├── Spark Master + 2 Workers                                              │
│  ├── MLflow tracking server                                                │
│  ├── Airflow webserver + scheduler                                         │
│  └── FastAPI application                                                   │
│                                                                             │
│  STEP 4: SEED INITIAL DATA                                                 │
│  ├── 5 test assets created in PostgreSQL                                   │
│  └── 15 sensors registered                                                 │
│                                                                             │
│  STEP 5: INGEST TO KAFKA                                                   │
│  ├── Real-time streaming at 100x speed                                     │
│  ├── Kafka topic: sensor_readings                                          │
│  └── Duration: ~60 seconds (simulated)                                     │
│                                                                             │
│  STEP 6: VERIFY PIPELINE                                                   │
│  ├── Spark processes streams → MongoDB                                     │
│  ├── Raw readings: MongoDB sensor_readings collection                      │
│  └── Aggregations: 5min, 1hour windows computed                            │
│                                                                             │
│  STEP 7: API TESTS                                                         │
│  ├── Health checks: ✅ PASS                                                │
│  ├── Authentication: ✅ PASS                                               │
│  ├── Asset CRUD: ✅ PASS                                                   │
│  ├── Alert rules: ✅ PASS                                                  │
│  └── Dashboard reports: ✅ PASS                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 📈 Expected Data Volumes

| Metric | Expected Value |
|--------|---------------|
| **Raw Records** | 20,631 (from CMAPSS) |
| **Converted Readings** | ~82,524 (4 sensors × 20,631) |
| **Assets Created** | 5 (seed) + 100 (CMAPSS engines) |
| **Sensors** | 15 (seed) + 400 (CMAPSS) |
| **MongoDB Documents** | 82,500+ sensor readings |
| **Aggregations (5min)** | ~2,750 windows |
| **Aggregations (1hour)** | ~230 windows |

## ✅ Expected API Test Results

### Health Checks
```bash
GET /health
→ {"status": "healthy", "version": "1.0.0"}

GET /health/ready
→ {"status": "ready"}
```

### Authentication
```bash
POST /auth/token
→ {
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_role": "admin"
}
```

### Assets
```bash
GET /assets/{tenant_id}
→ {
  "total": 105,
  "items": [...],
  "page": 1,
  "page_size": 20
}
```

### Dashboard Report
```bash
GET /reports/{tenant_id}/dashboard
→ {
  "total_assets": 105,
  "assets_by_status": {"operational": 105},
  "total_open_alerts": 0,
  "fleet_health_score": 75.5,
  "health_distribution": {
    "healthy": 80,
    "at_risk": 20,
    "critical": 5
  }
}
```

## 🎯 Key Sensor Readings (CMAPSS)

| Sensor | Type | Range | Unit |
|--------|------|-------|------|
| T50 | Temperature | 1,400-1,600 | °C |
| P30 | Pressure | 500-600 | - |
| Nf | Fan Speed | 2,300-2,400 | RPM |
| Nc | Core Speed | 9,000-9,200 | RPM |

## 📊 Data Quality Indicators

### ✅ Success Criteria

1. **Data Ingestion**
   - [ ] Kafka topic `sensor_readings` created
   - [ ] 82,500+ messages in Kafka
   - [ ] MongoDB has `sensor_readings` collection
   - [ ] 82,500+ documents in MongoDB

2. **Stream Processing**
   - [ ] Spark streaming job active
   - [ ] 5-minute aggregations in MongoDB
   - [ ] 1-hour aggregations in MongoDB
   - [ ] No failed batches

3. **API Functionality**
   - [ ] Health endpoint responds
   - [ ] Authentication returns JWT
   - [ ] Assets API returns 105 assets
   - [ ] Dashboard report generated
   - [ ] Predictions return health scores

4. **Database State**
   - [ ] PostgreSQL: 105+ assets
   - [ ] PostgreSQL: 415+ sensors
   - [ ] MongoDB: 82,500+ readings
   - [ ] MongoDB: aggregations computed

## 🔍 Verification Commands

After running the pipeline, verify with:

```bash
# 1. Check all services
docker-compose ps

# 2. Check Kafka topics
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# 3. Check MongoDB document count
docker-compose exec mongodb mongosh foresight --eval "db.sensor_readings.estimatedDocumentCount()"

# 4. Check PostgreSQL asset count
docker-compose exec postgres psql -U foresight -c "SELECT COUNT(*) FROM assets;"

# 5. Test API
curl http://localhost:8000/health

# 6. Get token and test authenticated endpoint
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@assetpulse.local","password":"admin123"}' | jq -r '.access_token')

curl http://localhost:8000/assets/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" | jq '.total'
```

## ⚠️ Common Issues & Fixes

### Issue: Kafka connection refused
```bash
# Fix: Wait longer for Kafka to start
sleep 60

# Or restart Kafka
docker-compose restart kafka
```

### Issue: MongoDB not showing documents
```bash
# Fix: Check Spark streaming is running
docker-compose logs spark-master | tail -20

# Check topic exists
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic sensor_readings
```

### Issue: API returns 500
```bash
# Fix: Check API logs
docker-compose logs api | tail -50

# Restart API
docker-compose restart api
```

## 📈 Performance Expectations

| Operation | Expected Time |
|-----------|--------------|
| Services startup | 30-60 seconds |
| CMAPSS conversion | 5-10 seconds |
| Data ingestion (100x) | 60-120 seconds |
| Stream processing | Real-time |
| API response | <100ms |
| Dashboard query | <500ms |

## 🎉 Success Indicators

You'll know the test was successful when:

1. ✅ All Docker containers show `Up` status
2. ✅ `engine_data.csv` is created (~5-10MB)
3. ✅ MongoDB shows 82,500+ documents
4. ✅ API health check returns `healthy`
5. ✅ API tests show all PASS
6. ✅ Dashboard shows 105+ assets
7. ✅ Spark UI shows completed batches

---

**Ready to run?** Start Docker Desktop, then run:
```bash
./scripts/full_test_pipeline.sh
```
