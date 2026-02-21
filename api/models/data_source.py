"""
FORESIGHT — Data Source Models

Models for managing external data source connections.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class DataSourceType(str, Enum):
    """Supported data source types."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    CSV = "csv"
    API = "api"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"


class ConnectionStatus(str, Enum):
    """Connection health status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    TESTING = "testing"


class DataSourceBase(BaseModel):
    """Base data source configuration."""
    name: str = Field(..., min_length=1, max_length=100)
    source_type: DataSourceType
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    host: str = Field(..., min_length=1)
    port: int = Field(..., gt=0, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    ssl_mode: str = "prefer"
    
    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v


class MongoConfig(BaseModel):
    """MongoDB connection configuration."""
    connection_string: str = Field(..., min_length=1)
    database: str = Field(..., min_length=1)


class CSVConfig(BaseModel):
    """CSV file configuration."""
    file_path: str = Field(..., min_length=1)
    delimiter: str = ","
    has_header: bool = True
    encoding: str = "utf-8"


class APIConfig(BaseModel):
    """API endpoint configuration."""
    base_url: str = Field(..., min_length=1)
    auth_type: str = "none"  # none, bearer, api_key, basic
    auth_token: Optional[str] = None
    api_key: Optional[str] = None
    api_key_header: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: int = 30


class SnowflakeConfig(BaseModel):
    """Snowflake connection configuration."""
    account: str = Field(..., min_length=1)
    warehouse: str = Field(..., min_length=1)
    database: str = Field(..., min_length=1)
    schema: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    role: Optional[str] = None


class BigQueryConfig(BaseModel):
    """BigQuery connection configuration."""
    project_id: str = Field(..., min_length=1)
    dataset: str = Field(..., min_length=1)
    credentials_json: Optional[str] = None  # Service account JSON


class DataSourceCreate(DataSourceBase):
    """Create new data source request."""
    config: Dict[str, Any] = Field(..., description="Type-specific configuration")
    
    @field_validator('config')
    @classmethod
    def validate_config(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        source_type = info.data.get('source_type')
        if not source_type:
            return v
            
        # Validate config based on source type
        try:
            if source_type == DataSourceType.POSTGRESQL:
                DatabaseConfig(**v)
            elif source_type == DataSourceType.MYSQL:
                DatabaseConfig(**v)
            elif source_type == DataSourceType.MONGODB:
                MongoConfig(**v)
            elif source_type == DataSourceType.CSV:
                CSVConfig(**v)
            elif source_type == DataSourceType.API:
                APIConfig(**v)
            elif source_type == DataSourceType.SNOWFLAKE:
                SnowflakeConfig(**v)
            elif source_type == DataSourceType.BIGQUERY:
                BigQueryConfig(**v)
        except Exception as e:
            raise ValueError(f'Invalid configuration for {source_type}: {e}')
        
        return v


class DataSourceUpdate(BaseModel):
    """Update data source request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class DataSourceResponse(DataSourceBase):
    """Data source response model."""
    id: str
    tenant_id: str
    config: Dict[str, Any]
    status: ConnectionStatus
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DataSourceListResponse(BaseModel):
    """List of data sources response."""
    total: int
    sources: list[DataSourceResponse]


class TestConnectionRequest(BaseModel):
    """Test connection request."""
    source_type: DataSourceType
    config: Dict[str, Any]


class TestConnectionResponse(BaseModel):
    """Test connection response."""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class ImportJobStatus(str, Enum):
    """Import job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportJobCreate(BaseModel):
    """Create import job request."""
    source_id: str
    target_table: str = Field(..., min_length=1)
    query: Optional[str] = None  # SQL query or filter
    mapping: Dict[str, str] = Field(default_factory=dict)  # Source -> Target column mapping
    schedule: Optional[str] = None  # Cron expression for scheduled imports


class ImportJobResponse(BaseModel):
    """Import job response."""
    id: str
    source_id: str
    tenant_id: str
    target_table: str
    status: ImportJobStatus
    query: Optional[str]
    mapping: Dict[str, str]
    schedule: Optional[str]
    records_imported: int = 0
    records_failed: int = 0
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
