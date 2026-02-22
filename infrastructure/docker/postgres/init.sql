-- =============================================================================
-- FORESIGHT — PostgreSQL Initialization Script
-- Multi-tenant predictive maintenance platform schema
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- TENANTS TABLE (Multi-tenancy root)
-- =============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    contact_email VARCHAR(255),
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- USERS TABLE (Per-tenant users with JWT auth)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'analyst', -- admin, analyst, operator, viewer
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

-- =============================================================================
-- ASSETS TABLE (Equipment/machinery being monitored)
-- =============================================================================
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id VARCHAR(100) NOT NULL,  -- External asset ID from SAP/Asset Suite
    name VARCHAR(255) NOT NULL,
    description TEXT,
    asset_type VARCHAR(100) NOT NULL, -- pump, motor, turbine, compressor, etc.
    category VARCHAR(100),            -- rotating, static, electrical, etc.
    manufacturer VARCHAR(255),
    model VARCHAR(255),
    serial_number VARCHAR(255),
    location VARCHAR(255),
    department VARCHAR(255),
    criticality VARCHAR(20) DEFAULT 'medium', -- critical, high, medium, low
    install_date DATE,
    purchase_cost DECIMAL(15, 2),
    status VARCHAR(50) DEFAULT 'operational', -- operational, maintenance, decommissioned
    parent_asset_id UUID REFERENCES assets(id),
    sap_equipment_number VARCHAR(100),
    asset_suite_id VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, asset_id)
);

-- =============================================================================
-- SENSORS TABLE (IoT sensors attached to assets)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sensors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    sensor_id VARCHAR(100) NOT NULL,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    sensor_type VARCHAR(100) NOT NULL, -- vibration, temperature, pressure, flow, etc.
    unit VARCHAR(50),                  -- celsius, bar, rpm, mm/s, etc.
    sampling_rate INTEGER DEFAULT 60,  -- seconds between readings
    min_threshold DECIMAL(10, 3),
    max_threshold DECIMAL(10, 3),
    calibration_date DATE,
    location_on_asset VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    kafka_topic VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, sensor_id)
);

-- =============================================================================
-- ALERT RULES TABLE (Threshold-based alerting)
-- =============================================================================
CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,  -- NULL = apply to all assets
    sensor_type VARCHAR(100),  -- NULL = apply to all sensors
    metric VARCHAR(100) NOT NULL, -- temperature, vibration_x, pressure, etc.
    operator VARCHAR(10) NOT NULL, -- >, <, >=, <=, ==, between
    threshold_value DECIMAL(10, 3),
    threshold_value_high DECIMAL(10, 3), -- for 'between' operator
    duration_seconds INTEGER DEFAULT 0, -- must breach for this long
    severity VARCHAR(20) DEFAULT 'warning', -- info, warning, critical, emergency
    is_active BOOLEAN DEFAULT true,
    auto_create_work_order BOOLEAN DEFAULT false,
    notification_channels JSONB DEFAULT '[]', -- email, slack, sms
    cooldown_minutes INTEGER DEFAULT 30, -- don't alert again within this window
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- ALERTS TABLE (Triggered alerts)
-- =============================================================================
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rule_id UUID REFERENCES alert_rules(id),
    asset_id UUID NOT NULL REFERENCES assets(id),
    sensor_id UUID REFERENCES sensors(id),
    alert_type VARCHAR(50) NOT NULL, -- threshold, anomaly, prediction
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(50) DEFAULT 'open', -- open, acknowledged, resolved, ignored
    title VARCHAR(500) NOT NULL,
    description TEXT,
    metric_name VARCHAR(100),
    metric_value DECIMAL(10, 3),
    threshold_value DECIMAL(10, 3),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by UUID REFERENCES users(id),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by UUID REFERENCES users(id),
    resolution_notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- MAINTENANCE RECORDS TABLE (Work orders, maintenance history)
-- =============================================================================
CREATE TABLE IF NOT EXISTS maintenance_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    work_order_number VARCHAR(100),
    record_type VARCHAR(50) NOT NULL, -- preventive, corrective, predictive, inspection
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'scheduled', -- scheduled, in_progress, completed, cancelled
    priority VARCHAR(20) DEFAULT 'medium', -- low, medium, high, emergency
    scheduled_date TIMESTAMP WITH TIME ZONE,
    started_date TIMESTAMP WITH TIME ZONE,
    completed_date TIMESTAMP WITH TIME ZONE,
    technician_name VARCHAR(255),
    technician_id VARCHAR(100),
    cost_parts DECIMAL(12, 2),
    cost_labor DECIMAL(12, 2),
    cost_total DECIMAL(12, 2),
    downtime_hours DECIMAL(8, 2),
    parts_replaced JSONB DEFAULT '[]',
    findings TEXT,
    recommendations TEXT,
    sap_notification_number VARCHAR(100),
    asset_suite_work_order_id VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- HEALTH SCORES TABLE (ML-generated asset health predictions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS health_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    score DECIMAL(5, 2) NOT NULL CHECK (score >= 0 AND score <= 100),
    predicted_failure_probability DECIMAL(5, 4), -- 0.0 to 1.0
    predicted_failure_date DATE,
    risk_level VARCHAR(20), -- low, medium, high, critical
    model_version VARCHAR(50),
    features_used JSONB,
    top_contributing_features JSONB,
    recommendation TEXT,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    valid_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- FEATURE STORE (ML features for training and inference)
-- =============================================================================
CREATE TABLE IF NOT EXISTS feature_store (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    feature_date DATE NOT NULL,
    
    -- Rolling statistics (7-day)
    temp_avg_7d DECIMAL(10, 3),
    temp_max_7d DECIMAL(10, 3),
    temp_std_7d DECIMAL(10, 3),
    vibration_avg_7d DECIMAL(10, 3),
    vibration_max_7d DECIMAL(10, 3),
    vibration_std_7d DECIMAL(10, 3),
    
    -- Rolling statistics (30-day)
    temp_avg_30d DECIMAL(10, 3),
    temp_max_30d DECIMAL(10, 3),
    vibration_avg_30d DECIMAL(10, 3),
    vibration_max_30d DECIMAL(10, 3),
    
    -- Maintenance features
    days_since_maintenance INTEGER,
    maintenance_count_90d INTEGER,
    total_downtime_hours_90d DECIMAL(8, 2),
    
    -- Derived features
    days_in_operation INTEGER,
    age_days INTEGER,
    criticality_score INTEGER,
    
    -- Target variable (for training)
    failed_within_30d BOOLEAN,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, asset_id, feature_date)
);

-- =============================================================================
-- MODEL REGISTRY (Track deployed ML models)
-- =============================================================================
CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_name VARCHAR(255) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    mlflow_run_id VARCHAR(100),
    mlflow_model_uri VARCHAR(500),
    model_type VARCHAR(100), -- xgboost, random_forest, etc.
    parameters JSONB,
    metrics JSONB, -- accuracy, precision, recall, f1, auc
    feature_importance JSONB,
    training_data_start DATE,
    training_data_end DATE,
    is_champion BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    deployed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, model_name, model_version)
);

-- =============================================================================
-- AUDIT LOG (For compliance and debugging)
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    table_name VARCHAR(100) NOT NULL,
    record_id UUID,
    action VARCHAR(50) NOT NULL, -- create, update, delete, login, etc.
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- Tenant isolation indexes
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_assets_tenant ON assets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sensors_tenant ON sensors(tenant_id);
CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_tenant ON maintenance_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_health_scores_tenant ON health_scores(tenant_id);

-- Common query patterns
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_criticality ON assets(criticality);
CREATE INDEX IF NOT EXISTS idx_sensors_asset ON sensors(asset_id);
CREATE INDEX IF NOT EXISTS idx_alerts_asset ON alerts(asset_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_maintenance_asset ON maintenance_records(asset_id);
CREATE INDEX IF NOT EXISTS idx_health_scores_asset ON health_scores(asset_id);
CREATE INDEX IF NOT EXISTS idx_health_scores_computed ON health_scores(computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_feature_store_asset_date ON feature_store(asset_id, feature_date);

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to all tables with updated_at column
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_assets_updated_at BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sensors_updated_at BEFORE UPDATE ON sensors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_alert_rules_updated_at BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_maintenance_records_updated_at BEFORE UPDATE ON maintenance_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_feature_store_updated_at BEFORE UPDATE ON feature_store
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- SEED DATA (Default tenant and admin user)
-- =============================================================================

-- Insert default tenant
INSERT INTO tenants (id, name, slug, description, contact_email)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    'Default Organization',
    'default',
    'Default tenant for initial setup',
    'admin@assetpulse.local'
)
ON CONFLICT (slug) DO NOTHING;

-- Insert admin user (password: admin123 - bcrypt hashed)
INSERT INTO users (id, tenant_id, email, hashed_password, full_name, role)
VALUES (
    '550e8400-e29b-41d4-a716-446655440001',
    '550e8400-e29b-41d4-a716-446655440000',
    'admin@assetpulse.local',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA.qGZvKG6G',
    'System Administrator',
    'admin'
)
ON CONFLICT (tenant_id, email) DO NOTHING;

-- =============================================================================
-- GRANTS (if needed for specific roles)
-- =============================================================================
-- Add specific grants here if using non-superuser roles

-- End of initialization script
