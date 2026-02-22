// =============================================================================
// FORESIGHT — MongoDB Initialization Script
// Time-series sensor data and raw readings
// =============================================================================

// Switch to foresight database
db = db.getSiblingDB('foresight');

// =============================================================================
// SENSOR READINGS COLLECTION (Time-series)
// =============================================================================

// Create time-series collection for sensor readings
// This is optimized for high-volume insertions and time-based queries
if (!db.getCollectionNames().includes('sensor_readings')) {
    db.createCollection('sensor_readings', {
        timeseries: {
            timeField: 'timestamp',
            metaField: 'metadata',
            granularity: 'seconds'
        },
        expireAfterSeconds: 7776000  // 90 days TTL
    });
}

// Create indexes for common query patterns
db.sensor_readings.createIndex({ 'metadata.tenant_id': 1, 'metadata.asset_id': 1, 'timestamp': -1 });
db.sensor_readings.createIndex({ 'metadata.tenant_id': 1, 'metadata.sensor_id': 1, 'timestamp': -1 });
db.sensor_readings.createIndex({ 'metadata.tenant_id': 1, 'timestamp': -1 });
db.sensor_readings.createIndex({ 'metadata.asset_id': 1, 'timestamp': -1 });

// =============================================================================
// AGGREGATED READINGS COLLECTION (5-min, 1-hour, 1-day windows)
// =============================================================================

// 5-minute aggregations
db.createCollection('sensor_aggregations_5min');
db.sensor_aggregations_5min.createIndex({ tenant_id: 1, asset_id: 1, window_start: -1 });
db.sensor_aggregations_5min.createIndex({ tenant_id: 1, window_start: -1 });
db.sensor_aggregations_5min.createIndex({ window_start: 1 }, { expireAfterSeconds: 2592000 }); // 30 days

// 1-hour aggregations
db.createCollection('sensor_aggregations_1h');
db.sensor_aggregations_1h.createIndex({ tenant_id: 1, asset_id: 1, window_start: -1 });
db.sensor_aggregations_1h.createIndex({ tenant_id: 1, window_start: -1 });
db.sensor_aggregations_1h.createIndex({ window_start: 1 }, { expireAfterSeconds: 7776000 }); // 90 days

// 1-day aggregations
db.createCollection('sensor_aggregations_1d');
db.sensor_aggregations_1d.createIndex({ tenant_id: 1, asset_id: 1, window_start: -1 });
db.sensor_aggregations_1d.createIndex({ tenant_id: 1, window_start: -1 });
// No TTL on daily aggregations - keep indefinitely

// =============================================================================
// STREAMING CHECKPOINTS (For Kafka/Spark exactly-once processing)
// =============================================================================

db.createCollection('streaming_checkpoints');
db.streaming_checkpoints.createIndex({ checkpoint_id: 1 }, { unique: true });
db.streaming_checkpoints.createIndex({ updated_at: 1 }, { expireAfterSeconds: 604800 }); // 7 days

// =============================================================================
// RAW INGESTED DATA (Landing zone for ETL)
// =============================================================================

db.createCollection('raw_ingested_data');
db.raw_ingested_data.createIndex({ tenant_id: 1, source: 1, ingested_at: -1 });
db.raw_ingested_data.createIndex({ ingested_at: 1 }, { expireAfterSeconds: 604800 }); // 7 days

// =============================================================================
-- SAMPLE DOCUMENT SCHEMAS (for reference)
-- =============================================================================

/*
sensor_readings document:
{
    timestamp: ISODate("2024-01-15T10:30:00Z"),
    metadata: {
        tenant_id: "550e8400-e29b-41d4-a716-446655440000",
        asset_id: "asset-001",
        sensor_id: "sensor-temp-001",
        sensor_type: "temperature"
    },
    value: 85.5,
    unit: "celsius",
    quality: "good",  // good, bad, uncertain
    anomalies: {
        is_anomaly: false,
        score: 0.12
    }
}

sensor_aggregations_5min document:
{
    tenant_id: "550e8400-e29b-41d4-a716-446655440000",
    asset_id: "asset-001",
    sensor_type: "temperature",
    window_start: ISODate("2024-01-15T10:30:00Z"),
    window_end: ISODate("2024-01-15T10:35:00Z"),
    readings_count: 300,
    avg_value: 85.2,
    min_value: 82.1,
    max_value: 88.5,
    std_dev: 1.23,
    alerts_triggered: 2
}
*/

// =============================================================================
// USER AND PERMISSIONS (if not using admin)
// =============================================================================

// Create foresight user with appropriate permissions (optional, for production)
// Uncomment and modify as needed:
/*
db.createUser({
    user: "foresight_app",
    pwd: "secure_password_here",
    roles: [
        { role: "readWrite", db: "foresight" },
        { role: "dbAdmin", db: "foresight" }
    ]
});
*/

print('MongoDB initialization completed successfully');
