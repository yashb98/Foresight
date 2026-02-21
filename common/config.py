"""
FORESIGHT — Centralised configuration loader.

All configuration is read from environment variables.
Provides a single Settings object imported by every module.
Pydantic BaseSettings validates types and raises clear errors for missing vars.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Project ---
    environment: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"

    # --- PostgreSQL ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "foresight"
    postgres_user: str = "foresight_user"
    postgres_password: str
    database_url: str  # async DSN (asyncpg)
    database_url_sync: str  # sync DSN (psycopg2) — used by Alembic / Airflow

    # --- MongoDB ---
    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    mongo_db: str = "foresight"
    mongo_root_user: str = "root"
    mongo_root_password: str
    mongo_uri: str

    # --- Kafka ---
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_sensor_data: str = "sensor-readings"
    kafka_topic_alerts: str = "asset-alerts"
    kafka_topic_maintenance: str = "maintenance-events"
    kafka_consumer_group: str = "foresight-streaming"
    kafka_replication_factor: int = 1
    kafka_num_partitions: int = 6

    # --- MinIO / S3 ---
    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str
    minio_bucket_raw: str = "foresight-raw"
    minio_bucket_processed: str = "foresight-processed"
    minio_bucket_models: str = "foresight-models"
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_endpoint_url: str = "http://minio:9000"
    aws_default_region: str = "us-east-1"

    # --- Spark ---
    spark_master_url: str = "spark://spark-master:7077"
    spark_driver_memory: str = "1g"
    spark_executor_memory: str = "1g"

    # --- MLflow ---
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_artifact_store: str = "s3://foresight-models/mlflow"
    mlflow_backend_store_uri: str

    # --- FastAPI / Auth ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"

    # --- ML ---
    model_champion_metric: str = "roc_auc"
    model_min_improvement_threshold: float = 0.01
    failure_prediction_window_7d: int = 7
    failure_prediction_window_30d: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        """Accept comma-separated string from env."""
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list for FastAPI middleware."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """True when running in production environment."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """True when running in development environment."""
        return self.environment.lower() == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings singleton.

    Using lru_cache ensures environment variables are read once at startup.
    Call get_settings() everywhere — do not instantiate Settings() directly.
    """
    return Settings()
