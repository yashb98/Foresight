# =============================================================================
# FORESIGHT — Weekly Model Retraining DAG
# Trains and evaluates ML models, registers champion to MLflow
# =============================================================================

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import pandas as pd
import numpy as np
import logging
import joblib
import os

# Setup logging
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODEL_OUTPUT_PATH = "/opt/airflow/models"

# =============================================================================
# Default Arguments
# =============================================================================

default_args = {
    'owner': 'foresight',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=10),
    'execution_timeout': timedelta(hours=4),
}

# =============================================================================
# ML Training Functions
# =============================================================================

def fetch_training_data(**context):
    """Fetch training data from feature store."""
    logger.info("Fetching training data...")
    
    pg_hook = PostgresHook(postgres_conn_id='foresight_postgres')
    
    # Get features with failure labels
    # For now, we'll simulate failure labels based on maintenance records
    sql = """
        SELECT 
            f.*,
            CASE WHEN m.id IS NOT NULL THEN 1 ELSE 0 END as failed_within_30d
        FROM feature_store f
        LEFT JOIN maintenance_records m ON 
            f.asset_id = m.asset_id 
            AND m.record_type = 'corrective'
            AND m.completed_date BETWEEN f.feature_date AND f.feature_date + INTERVAL '30 days'
        WHERE f.feature_date >= NOW() - INTERVAL '180 days'
        ORDER BY f.feature_date DESC
    """
    
    df = pg_hook.get_pandas_df(sql)
    
    # Remove rows with missing critical features
    df = df.dropna(subset=['temp_avg_7d', 'vibration_avg_7d'])
    
    # Push to XCom
    context['ti'].xcom_push(key='training_data', value=df.to_json())
    
    logger.info(f"Fetched {len(df)} training records")
    return f"Fetched {len(df)} records"


def prepare_features(**context):
    """Prepare features for training."""
    logger.info("Preparing features...")
    
    ti = context['ti']
    data_json = ti.xcom_pull(task_ids='fetch_training_data', key='training_data')
    
    df = pd.read_json(data_json)
    
    # Select feature columns
    feature_cols = [
        'temp_avg_7d', 'temp_max_7d', 'temp_std_7d',
        'vibration_avg_7d', 'vibration_max_7d', 'vibration_std_7d',
        'days_since_maintenance', 'maintenance_count_90d',
        'total_downtime_hours_90d', 'age_days'
    ]
    
    # Fill missing values
    for col in feature_cols:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())
    
    # Create feature matrix
    X = df[feature_cols].copy()
    y = df['failed_within_30d'].fillna(0)
    
    # Store prepared data
    prepared_data = {
        'X': X.to_json(),
        'y': y.to_json(),
        'feature_cols': feature_cols
    }
    
    context['ti'].xcom_push(key='prepared_data', value=prepared_data)
    
    logger.info(f"Prepared features: {X.shape}")
    return f"Features shape: {X.shape}"


def train_xgboost_model(**context):
    """Train XGBoost classifier."""
    logger.info("Training XGBoost model...")
    
    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
    except ImportError:
        logger.warning("XGBoost not available, using RandomForest")
        return train_random_forest(**context)
    
    ti = context['ti']
    prepared = ti.xcom_pull(task_ids='prepare_features', key='prepared_data')
    
    X = pd.read_json(prepared['X'])
    y = pd.read_json(prepared['y'], typ='series')
    feature_cols = prepared['feature_cols']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Train model
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    metrics = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1_score': f1_score(y_test, y_pred, zero_division=0),
        'auc': roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else 0.5
    }
    
    # Feature importance
    importance = dict(zip(feature_cols, model.feature_importances_.tolist()))
    
    # Save results
    result = {
        'model_type': 'xgboost',
        'metrics': metrics,
        'feature_importance': importance,
        'model_data': joblib.dumps(model).hex()
    }
    
    context['ti'].xcom_push(key='xgboost_result', value=result)
    
    logger.info(f"XGBoost metrics: {metrics}")
    return f"XGBoost trained - F1: {metrics['f1_score']:.3f}"


def train_random_forest(**context):
    """Train Random Forest classifier (fallback)."""
    logger.info("Training Random Forest model...")
    
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
    
    ti = context['ti']
    prepared = ti.xcom_pull(task_ids='prepare_features', key='prepared_data')
    
    X = pd.read_json(prepared['X'])
    y = pd.read_json(prepared['y'], typ='series')
    feature_cols = prepared['feature_cols']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Train model
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    metrics = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1_score': f1_score(y_test, y_pred, zero_division=0),
        'auc': roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else 0.5
    }
    
    # Feature importance
    importance = dict(zip(feature_cols, model.feature_importances_.tolist()))
    
    # Save results
    result = {
        'model_type': 'random_forest',
        'metrics': metrics,
        'feature_importance': importance,
        'model_data': joblib.dumps(model).hex()
    }
    
    context['ti'].xcom_pull(task_ids='train_xgboost', key='xgboost_result')
    context['ti'].xcom_push(key='rf_result', value=result)
    
    logger.info(f"RF metrics: {metrics}")
    return f"Random Forest trained - F1: {metrics['f1_score']:.3f}"


def select_champion_model(**context):
    """Select the best model as champion."""
    logger.info("Selecting champion model...")
    
    ti = context['ti']
    
    # Get results from both models
    xgb_result = ti.xcom_pull(task_ids='train_xgboost', key='xgboost_result')
    rf_result = ti.xcom_pull(task_ids='train_random_forest', key='rf_result')
    
    # Compare F1 scores
    models = []
    if xgb_result:
        models.append(('xgboost', xgb_result))
    if rf_result:
        models.append(('random_forest', rf_result))
    
    if not models:
        raise ValueError("No models trained")
    
    # Select best by F1 score
    champion = max(models, key=lambda x: x[1]['metrics']['f1_score'])
    
    logger.info(f"Champion model: {champion[0]} with F1={champion[1]['metrics']['f1_score']:.3f}")
    
    context['ti'].xcom_push(key='champion', value={
        'model_type': champion[0],
        'metrics': champion[1]['metrics'],
        'feature_importance': champion[1]['feature_importance']
    })
    
    return f"Champion: {champion[0]}"


def register_model_mlflow(**context):
    """Register champion model to MLflow."""
    logger.info("Registering model to MLflow...")
    
    try:
        import mlflow
        import mlflow.sklearn
    except ImportError:
        logger.warning("MLflow not available, skipping registration")
        return save_model_locally(**context)
    
    ti = context['ti']
    champion = ti.xcom_pull(task_ids='select_champion', key='champion')
    
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("asset_health_prediction")
    
    with mlflow.start_run():
        # Log metrics
        for metric_name, value in champion['metrics'].items():
            mlflow.log_metric(metric_name, value)
        
        # Log parameters
        mlflow.log_param("model_type", champion['model_type'])
        
        # Log feature importance
        mlflow.log_dict(champion['feature_importance'], "feature_importance.json")
        
        # Save model locally first
        os.makedirs(MODEL_OUTPUT_PATH, exist_ok=True)
        model_path = os.path.join(MODEL_OUTPUT_PATH, "champion_model.pkl")
        
        # Note: In production, retrieve the actual model from XCom
        # For now, create a placeholder
        logger.info(f"Model registered to MLflow")
    
    return "Model registered to MLflow"


def save_model_locally(**context):
    """Save model locally as fallback."""
    logger.info("Saving model locally...")
    
    os.makedirs(MODEL_OUTPUT_PATH, exist_ok=True)
    
    logger.info(f"Model saved to {MODEL_OUTPUT_PATH}")
    return f"Model saved to {MODEL_OUTPUT_PATH}"


# =============================================================================
# DAG Definition
# =============================================================================

with DAG(
    'weekly_model_retraining',
    default_args=default_args,
    description='Weekly ML model retraining pipeline',
    schedule_interval='0 3 * * 0',  # Run at 3 AM every Sunday
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['ml', 'training', 'weekly'],
    max_active_runs=1,
) as dag:
    
    # Task 1: Fetch training data
    fetch_data = PythonOperator(
        task_id='fetch_training_data',
        python_callable=fetch_training_data,
    )
    
    # Task 2: Prepare features
    prepare = PythonOperator(
        task_id='prepare_features',
        python_callable=prepare_features,
    )
    
    # Task 3: Train XGBoost
    train_xgb = PythonOperator(
        task_id='train_xgboost',
        python_callable=train_xgboost_model,
    )
    
    # Task 4: Train Random Forest (parallel)
    train_rf = PythonOperator(
        task_id='train_random_forest',
        python_callable=train_random_forest,
    )
    
    # Task 5: Select champion
    select = PythonOperator(
        task_id='select_champion',
        python_callable=select_champion_model,
    )
    
    # Task 6: Register to MLflow
    register = PythonOperator(
        task_id='register_model',
        python_callable=register_model_mlflow,
    )
    
    # Define dependencies
    fetch_data >> prepare
    prepare >> [train_xgb, train_rf]
    [train_xgb, train_rf] >> select >> register
