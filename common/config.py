# =============================================================================
# FORESIGHT — Configuration
# Environment-based configuration using Pydantic Settings
# =============================================================================

import os
from typing import List, Optional

from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # =============================================================================
    # Application
    # =============================================================================
    
    APP_NAME: str = "FORESIGHT"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")
    
    # =============================================================================
    # Security
    # =============================================================================
    
    JWT_SECRET_KEY: str = Field(default="change-me-in-production")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRATION_SECONDS: int = Field(default=3600)
    
    # =============================================================================
    # Database — PostgreSQL
    # =============================================================================
    
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="foresight")
    POSTGRES_USER: str = Field(default="foresight")
    POSTGRES_PASSWORD: str = Field(default="foresight")
    
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_SYNC: Optional[str] = None
    
    @validator("DATABASE_URL", pre=True, always=True)
    def assemble_database_url(cls, v, values):
        """Build async database URL from components."""
        if v:
            return v
        return (
            f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}"
            f"@{values.get('POSTGRES_HOST')}:{values.get('POSTGRES_PORT')}"
            f"/{values.get('POSTGRES_DB')}"
        )
    
    @validator("DATABASE_URL_SYNC", pre=True, always=True)
    def assemble_sync_database_url(cls, v, values):
        """Build sync database URL from components."""
        if v:
            return v
        return (
            f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}"
            f"@{values.get('POSTGRES_HOST')}:{values.get('POSTGRES_PORT')}"
            f"/{values.get('POSTGRES_DB')}"
        )
    
    # =============================================================================
    # Database — MongoDB
    # =============================================================================
    
    MONGO_HOST: str = Field(default="localhost")
    MONGO_PORT: int = Field(default=27017)
    MONGO_DB: str = Field(default="foresight")
    MONGO_ROOT_USER: str = Field(default="admin")
    MONGO_ROOT_PASSWORD: str = Field(default="admin")
    MONGO_URI: Optional[str] = None
    
    @validator("MONGO_URI", pre=True, always=True)
    def assemble_mongo_uri(cls, v, values):
        """Build MongoDB URI from components."""
        if v:
            return v
        return (
            f"mongodb://{values.get('MONGO_ROOT_USER')}:{values.get('MONGO_ROOT_PASSWORD')}"
            f"@{values.get('MONGO_HOST')}:{values.get('MONGO_PORT')}"
        )
    
    # =============================================================================
    # Message Queue — Kafka
    # =============================================================================
    
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:29092")
    KAFKA_TOPIC_SENSOR_READINGS: str = Field(default="sensor_readings")
    KAFKA_TOPIC_ALERTS: str = Field(default="alerts")
    
    # =============================================================================
    # Object Storage — MinIO / S3
    # =============================================================================
    
    MINIO_HOST: str = Field(default="localhost")
    MINIO_PORT: int = Field(default=9000)
    MINIO_ROOT_USER: str = Field(default="minioadmin")
    MINIO_ROOT_PASSWORD: str = Field(default="minioadmin")
    MINIO_BUCKET_RAW: str = Field(default="foresight-raw")
    MINIO_BUCKET_PROCESSED: str = Field(default="foresight-processed")
    MINIO_BUCKET_MODELS: str = Field(default="foresight-models")
    
    AWS_ACCESS_KEY_ID: str = Field(default="minioadmin")
    AWS_SECRET_ACCESS_KEY: str = Field(default="minioadmin")
    AWS_ENDPOINT_URL: str = Field(default="http://localhost:9000")
    
    @validator("AWS_ENDPOINT_URL", pre=True, always=True)
    def assemble_endpoint_url(cls, v, values):
        """Build MinIO endpoint URL."""
        if v and not v.startswith("http://localhost"):
            return v
        return f"http://{values.get('MINIO_HOST')}:{values.get('MINIO_PORT')}"
    
    # =============================================================================
    # MLflow
    # =============================================================================
    
    MLFLOW_TRACKING_URI: str = Field(default="http://localhost:5000")
    MLFLOW_BACKEND_STORE_URI: Optional[str] = None
    MLFLOW_ARTIFACT_STORE: str = Field(default="s3://mlflow")
    MLFLOW_S3_ENDPOINT_URL: str = Field(default="http://localhost:9000")
    
    @validator("MLFLOW_BACKEND_STORE_URI", pre=True, always=True)
    def assemble_mlflow_backend(cls, v, values):
        """Build MLflow backend URI."""
        if v:
            return v
        return (
            f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}"
            f"@{values.get('POSTGRES_HOST')}:{values.get('POSTGRES_PORT')}"
            f"/{values.get('POSTGRES_DB')}"
        )
    
    # =============================================================================
    # Apache Airflow
    # =============================================================================
    
    AIRFLOW__CORE__SQL_ALCHEMY_CONN: Optional[str] = None
    AIRFLOW__CORE__FERNET_KEY: str = Field(default="")
    AIRFLOW__WEBSERVER__SECRET_KEY: str = Field(default="foresight-secret-key")
    AIRFLOW_ADMIN_USERNAME: str = Field(default="admin")
    AIRFLOW_ADMIN_PASSWORD: str = Field(default="admin")
    AIRFLOW_ADMIN_EMAIL: str = Field(default="admin@assetpulse.local")
    AIRFLOW__LOGGING__LOGGING_LEVEL: str = Field(default="INFO")
    
    @validator("AIRFLOW__CORE__SQL_ALCHEMY_CONN", pre=True, always=True)
    def assemble_airflow_db(cls, v, values):
        """Build Airflow database connection."""
        if v:
            return v
        return (
            f"postgresql+psycopg2://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}"
            f"@{values.get('POSTGRES_HOST')}:{values.get('POSTGRES_PORT')}"
            f"/{values.get('POSTGRES_DB')}"
        )
    
    # =============================================================================
    # Spark
    # =============================================================================
    
    SPARK_MASTER_URL: str = Field(default="spark://spark-master:7077")
    SPARK_WORKER_MEMORY: str = Field(default="2g")
    SPARK_WORKER_CORES: int = Field(default=2)
    
    # =============================================================================
    # CORS
    # =============================================================================
    
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # =============================================================================
    # Logging
    # =============================================================================
    
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    
    # =============================================================================
    # Feature Engineering
    # =============================================================================
    
    FEATURE_STORE_TABLE: str = Field(default="feature_store")
    FEATURE_LOOKBACK_DAYS: int = Field(default=90)
    
    # =============================================================================
    # Model Serving
    # =============================================================================
    
    MODEL_PATH: str = Field(default="/app/ml/models/champion_model.pkl")
    MODEL_CACHE_TTL: int = Field(default=300)  # 5 minutes
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings
