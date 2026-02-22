# =============================================================================
# FORESIGHT — Daily Feature Engineering DAG
# Computes features from raw sensor data for ML training and inference
# =============================================================================

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.mongo.hooks.mongo import MongoHook
import pandas as pd
import logging

# Setup logging
logger = logging.getLogger(__name__)

# =============================================================================
# Default Arguments
# =============================================================================

default_args = {
    'owner': 'foresight',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# =============================================================================
# Feature Engineering Functions
# =============================================================================

def extract_sensor_aggregations(**context):
    """Extract aggregated sensor data from MongoDB."""
    execution_date = context['execution_date']
    logger.info(f"Extracting sensor aggregations for {execution_date}")
    
    # Connect to MongoDB
    mongo_hook = MongoHook(mongo_conn_id='foresight_mongo')
    db = mongo_hook.get_conn().foresight
    
    # Get data for the last day
    start_time = execution_date - timedelta(days=1)
    
    # Query 1-hour aggregations
    pipeline = [
        {
            '$match': {
                'window_start': {
                    '$gte': start_time,
                    '$lt': execution_date
                }
            }
        },
        {
            '$group': {
                '_id': {
                    'tenant_id': '$tenant_id',
                    'asset_id': '$asset_id',
                    'sensor_type': '$sensor_type'
                },
                'avg_value': {'$avg': '$avg_value'},
                'max_value': {'$max': '$max_value'},
                'min_value': {'$min': '$min_value'},
                'readings_count': {'$sum': '$readings_count'}
            }
        }
    ]
    
    results = list(db.sensor_aggregations_1h.aggregate(pipeline))
    
    # Convert to DataFrame
    data = []
    for r in results:
        data.append({
            'tenant_id': r['_id']['tenant_id'],
            'asset_id': r['_id']['asset_id'],
            'sensor_type': r['_id']['sensor_type'],
            'avg_value': r['avg_value'],
            'max_value': r['max_value'],
            'min_value': r['min_value'],
            'readings_count': r['readings_count']
        })
    
    df = pd.DataFrame(data)
    
    # Push to XCom
    context['ti'].xcom_push(key='sensor_data', value=df.to_json())
    
    logger.info(f"Extracted {len(df)} sensor aggregation records")
    return f"Extracted {len(df)} records"


def extract_maintenance_data(**context):
    """Extract maintenance records from PostgreSQL."""
    execution_date = context['execution_date']
    logger.info(f"Extracting maintenance data for {execution_date}")
    
    pg_hook = PostgresHook(postgres_conn_id='foresight_postgres')
    
    # Get maintenance data for last 90 days
    start_time = execution_date - timedelta(days=90)
    
    sql = """
        SELECT 
            tenant_id,
            asset_id,
            COUNT(*) as maintenance_count,
            SUM(downtime_hours) as total_downtime,
            MAX(completed_date) as last_maintenance_date
        FROM maintenance_records
        WHERE completed_date >= %s
        GROUP BY tenant_id, asset_id
    """
    
    df = pg_hook.get_pandas_df(sql, parameters=(start_time,))
    
    context['ti'].xcom_push(key='maintenance_data', value=df.to_json())
    
    logger.info(f"Extracted {len(df)} maintenance records")
    return f"Extracted {len(df)} records"


def compute_features(**context):
    """Compute features from sensor and maintenance data."""
    execution_date = context['execution_date']
    logger.info(f"Computing features for {execution_date}")
    
    ti = context['ti']
    
    # Get data from XCom
    sensor_json = ti.xcom_pull(task_ids='extract_sensor_aggregations', key='sensor_data')
    maintenance_json = ti.xcom_pull(task_ids='extract_maintenance_data', key='maintenance_data')
    
    sensor_df = pd.read_json(sensor_json) if sensor_json else pd.DataFrame()
    maint_df = pd.read_json(maintenance_json) if maintenance_json else pd.DataFrame()
    
    # Get all assets from PostgreSQL
    pg_hook = PostgresHook(postgres_conn_id='foresight_postgres')
    assets_df = pg_hook.get_pandas_df("SELECT id as asset_id, tenant_id, asset_type FROM assets")
    
    if assets_df.empty:
        logger.warning("No assets found")
        return "No assets to process"
    
    features_list = []
    
    for _, asset in assets_df.iterrows():
        asset_id = asset['asset_id']
        tenant_id = asset['tenant_id']
        
        # Filter sensor data for this asset
        asset_sensors = sensor_df[
            (sensor_df['asset_id'] == str(asset_id)) & 
            (sensor_df['tenant_id'] == str(tenant_id))
        ]
        
        # Filter maintenance data
        asset_maint = maint_df[
            (maint_df['asset_id'] == str(asset_id)) & 
            (maint_df['tenant_id'] == str(tenant_id))
        ]
        
        # Temperature features
        temp_data = asset_sensors[asset_sensors['sensor_type'] == 'temperature']
        temp_avg_7d = temp_data['avg_value'].mean() if not temp_data.empty else None
        temp_max_7d = temp_data['max_value'].max() if not temp_data.empty else None
        temp_std_7d = temp_data['avg_value'].std() if not temp_data.empty else None
        
        # Vibration features
        vib_data = asset_sensors[asset_sensors['sensor_type'] == 'vibration']
        vib_avg_7d = vib_data['avg_value'].mean() if not vib_data.empty else None
        vib_max_7d = vib_data['max_value'].max() if not vib_data.empty else None
        vib_std_7d = vib_data['avg_value'].std() if not vib_data.empty else None
        
        # Maintenance features
        maint_count = asset_maint['maintenance_count'].sum() if not asset_maint.empty else 0
        total_downtime = asset_maint['total_downtime'].sum() if not asset_maint.empty else 0
        
        last_maint = asset_maint['last_maintenance_date'].max() if not asset_maint.empty else None
        days_since_maint = (execution_date - last_maint).days if last_maint else 365
        
        # Asset age (placeholder - would use install_date)
        age_days = 365  # Default
        
        features_list.append({
            'tenant_id': str(tenant_id),
            'asset_id': str(asset_id),
            'feature_date': execution_date.date(),
            'temp_avg_7d': temp_avg_7d,
            'temp_max_7d': temp_max_7d,
            'temp_std_7d': temp_std_7d,
            'vibration_avg_7d': vib_avg_7d,
            'vibration_max_7d': vib_max_7d,
            'vibration_std_7d': vib_std_7d,
            'days_since_maintenance': days_since_maint,
            'maintenance_count_90d': int(maint_count),
            'total_downtime_hours_90d': total_downtime,
            'age_days': age_days,
        })
    
    features_df = pd.DataFrame(features_list)
    
    # Push to XCom
    context['ti'].xcom_push(key='features', value=features_df.to_json())
    
    logger.info(f"Computed features for {len(features_df)} assets")
    return f"Computed features for {len(features_df)} assets"


def store_features(**context):
    """Store computed features in PostgreSQL feature store."""
    execution_date = context['execution_date']
    logger.info(f"Storing features for {execution_date}")
    
    ti = context['ti']
    features_json = ti.xcom_pull(task_ids='compute_features', key='features')
    
    if not features_json:
        logger.warning("No features to store")
        return "No features to store"
    
    features_df = pd.read_json(features_json)
    
    pg_hook = PostgresHook(postgres_conn_id='foresight_postgres')
    
    # Insert features
    rows_inserted = 0
    for _, row in features_df.iterrows():
        try:
            pg_hook.run("""
                INSERT INTO feature_store (
                    tenant_id, asset_id, feature_date,
                    temp_avg_7d, temp_max_7d, temp_std_7d,
                    vibration_avg_7d, vibration_max_7d, vibration_std_7d,
                    days_since_maintenance, maintenance_count_90d,
                    total_downtime_hours_90d, age_days
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, asset_id, feature_date) DO UPDATE SET
                    temp_avg_7d = EXCLUDED.temp_avg_7d,
                    temp_max_7d = EXCLUDED.temp_max_7d,
                    temp_std_7d = EXCLUDED.temp_std_7d,
                    vibration_avg_7d = EXCLUDED.vibration_avg_7d,
                    vibration_max_7d = EXCLUDED.vibration_max_7d,
                    vibration_std_7d = EXCLUDED.vibration_std_7d,
                    days_since_maintenance = EXCLUDED.days_since_maintenance,
                    maintenance_count_90d = EXCLUDED.maintenance_count_90d,
                    total_downtime_hours_90d = EXCLUDED.total_downtime_hours_90d,
                    updated_at = NOW()
            """, parameters=(
                row['tenant_id'], row['asset_id'], row['feature_date'],
                row.get('temp_avg_7d'), row.get('temp_max_7d'), row.get('temp_std_7d'),
                row.get('vibration_avg_7d'), row.get('vibration_max_7d'), row.get('vibration_std_7d'),
                row.get('days_since_maintenance'), row.get('maintenance_count_90d'),
                row.get('total_downtime_hours_90d'), row.get('age_days')
            ))
            rows_inserted += 1
        except Exception as e:
            logger.error(f"Error inserting features for {row.get('asset_id')}: {e}")
    
    logger.info(f"Stored features for {rows_inserted} assets")
    return f"Stored {rows_inserted} feature records"


def generate_health_predictions(**context):
    """Generate health predictions for all assets."""
    import requests
    import json
    
    execution_date = context['execution_date']
    logger.info(f"Generating health predictions for {execution_date}")
    
    pg_hook = PostgresHook(postgres_conn_id='foresight_postgres')
    
    # Get assets with features
    assets = pg_hook.get_records("""
        SELECT DISTINCT a.id, a.tenant_id
        FROM assets a
        JOIN feature_store f ON a.id = f.asset_id
        WHERE f.feature_date = %s
    """, parameters=(execution_date.date(),))
    
    if not assets:
        logger.info("No assets to predict")
        return "No predictions made"
    
    # Call API for batch prediction
    api_url = "http://api:8000/predict"
    predictions_made = 0
    
    for asset_id, tenant_id in assets:
        try:
            response = requests.post(
                f"{api_url}/{tenant_id}",
                json={"asset_id": str(asset_id)},
                timeout=30
            )
            if response.status_code == 200:
                predictions_made += 1
            else:
                logger.warning(f"Prediction failed for {asset_id}: {response.status_code}")
        except Exception as e:
            logger.error(f"Error predicting for {asset_id}: {e}")
    
    logger.info(f"Generated {predictions_made} predictions")
    return f"Generated {predictions_made} predictions"


# =============================================================================
# DAG Definition
# =============================================================================

with DAG(
    'daily_feature_pipeline',
    default_args=default_args,
    description='Daily feature engineering and health scoring pipeline',
    schedule_interval='0 2 * * *',  # Run at 2 AM daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['feature_engineering', 'ml', 'daily'],
    max_active_runs=1,
) as dag:
    
    # Task 1: Extract sensor aggregations from MongoDB
    extract_sensors = PythonOperator(
        task_id='extract_sensor_aggregations',
        python_callable=extract_sensor_aggregations,
    )
    
    # Task 2: Extract maintenance data from PostgreSQL
    extract_maintenance = PythonOperator(
        task_id='extract_maintenance_data',
        python_callable=extract_maintenance_data,
    )
    
    # Task 3: Compute features
    compute = PythonOperator(
        task_id='compute_features',
        python_callable=compute_features,
    )
    
    # Task 4: Store features
    store = PythonOperator(
        task_id='store_features',
        python_callable=store_features,
    )
    
    # Task 5: Generate predictions
    predict = PythonOperator(
        task_id='generate_predictions',
        python_callable=generate_health_predictions,
    )
    
    # Define dependencies
    [extract_sensors, extract_maintenance] >> compute >> store >> predict
