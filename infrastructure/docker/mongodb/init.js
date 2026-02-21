// =============================================================================
// FORESIGHT — MongoDB Initialisation Script
// Creates the foresight database, application user, and sensor_readings
// collection with the correct compound index.
// Runs once on first container start via docker-entrypoint-initdb.d/
// =============================================================================

// Switch to admin to create the app user
db = db.getSiblingDB("admin");

// Create application user with readWrite on foresight DB
db.createUser({
  user: "foresight_user",
  pwd: "change_me_mongo_password",   // overridden by MONGO_ROOT_PASSWORD in prod
  roles: [
    { role: "readWrite", db: "foresight" },
    { role: "dbAdmin", db: "foresight" }
  ]
});

// Switch to the foresight application database
db = db.getSiblingDB("foresight");

// -------------------------------------------------------------------------
// sensor_readings collection
// Partition key:   (tenant_id, asset_id)
// Clustering key:  timestamp DESC
// Never query without tenant_id — will cause full collection scan at scale.
// -------------------------------------------------------------------------
db.createCollection("sensor_readings", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenant_id", "asset_id", "timestamp", "metric_name", "value"],
      properties: {
        tenant_id:   { bsonType: "string", description: "Tenant UUID — required" },
        asset_id:    { bsonType: "string", description: "Asset UUID — required" },
        timestamp:   { bsonType: "date",   description: "Reading timestamp — required" },
        metric_name: { bsonType: "string", description: "temperature|vibration|pressure|rpm" },
        value:       { bsonType: "double", description: "Raw sensor measurement" },
        unit:        { bsonType: "string", description: "degC|mm_s|bar|rpm" },
        quality_flag:{ bsonType: "string", description: "good|degraded|suspect" }
      }
    }
  },
  validationAction: "warn"   // warn in dev; set to "error" in production
});

// Primary compound index — most queries will hit this
db.sensor_readings.createIndex(
  { tenant_id: 1, asset_id: 1, timestamp: -1 },
  { name: "idx_tenant_asset_timestamp", background: true }
);

// Secondary index for metric-based queries within a tenant
db.sensor_readings.createIndex(
  { tenant_id: 1, metric_name: 1, timestamp: -1 },
  { name: "idx_tenant_metric_timestamp", background: true }
);

// TTL index — auto-delete raw readings older than 90 days (keeps collection lean)
// Comment out if you need longer retention.
db.sensor_readings.createIndex(
  { timestamp: 1 },
  { name: "idx_ttl_90days", expireAfterSeconds: 7776000, background: true }
);

// -------------------------------------------------------------------------
// aggregated_readings collection — windowed aggregation results from Spark
// -------------------------------------------------------------------------
db.createCollection("aggregated_readings");
db.aggregated_readings.createIndex(
  { tenant_id: 1, asset_id: 1, window_start: -1, window_size: 1 },
  { name: "idx_agg_tenant_asset_window", background: true }
);

print("MongoDB init complete: sensor_readings and aggregated_readings collections ready.");
