"""
FORESIGHT — Data Importers for various source types.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from api.data_import.engine import save_records
from infrastructure.db.base import DataSource, ImportJob

log = logging.getLogger(__name__)


class BaseImporter:
    """Base class for data importers."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        """Import data from source. Override in subclasses."""
        raise NotImplementedError


class PostgreSQLImporter(BaseImporter):
    """Importer for PostgreSQL databases."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        import asyncpg
        
        config = source.config
        conn = await asyncpg.connect(
            host=config["host"],
            port=config.get("port", 5432),
            database=config["database"],
            user=config["username"],
            password=config["password"],
            ssl=config.get("ssl_mode", "prefer"),
        )
        
        try:
            query = job.query or f"SELECT * FROM {job.target_table} LIMIT 10000"
            rows = await conn.fetch(query)
            
            records = [dict(row) for row in rows]
            imported = await save_records(db, records, job.target_table, job.mapping)
            
            return {
                "records_imported": imported,
                "records_failed": len(records) - imported,
            }
        finally:
            await conn.close()


class MySQLImporter(BaseImporter):
    """Importer for MySQL databases."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        try:
            import aiomysql
            
            config = source.config
            conn = await aiomysql.connect(
                host=config["host"],
                port=config.get("port", 3306),
                db=config["database"],
                user=config["username"],
                password=config["password"],
            )
            
            async with conn.cursor(aiomysql.DictCursor) as cur:
                query = job.query or f"SELECT * FROM {job.target_table} LIMIT 10000"
                await cur.execute(query)
                rows = await cur.fetchall()
                
                imported = await save_records(db, rows, job.target_table, job.mapping)
                
                return {
                    "records_imported": imported,
                    "records_failed": len(rows) - imported,
                }
            
            conn.close()
        except ImportError:
            raise RuntimeError("aiomysql not installed")


class MongoDBImporter(BaseImporter):
    """Importer for MongoDB."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        from motor.motor_asyncio import AsyncIOMotorClient
        
        config = source.config
        client = AsyncIOMotorClient(config["connection_string"], serverSelectionTimeoutMS=30000)
        
        try:
            database = client[config["database"]]
            collection = job.target_table
            
            filter_query = {}
            if job.query:
                filter_query = json.loads(job.query)
            
            cursor = database[collection].find(filter_query).limit(10000)
            rows = await cursor.to_list(length=None)
            
            # Convert ObjectId to string
            for row in rows:
                if "_id" in row:
                    row["_id"] = str(row["_id"])
            
            imported = await save_records(db, rows, job.target_table, job.mapping)
            
            return {
                "records_imported": imported,
                "records_failed": len(rows) - imported,
            }
        finally:
            client.close()


class CSVImporter(BaseImporter):
    """Importer for CSV files."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        config = source.config
        file_path = config["file_path"]
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")
        has_header = config.get("has_header", True)
        
        records = []
        with open(file_path, "r", encoding=encoding, newline="") as f:
            if has_header:
                reader = csv.DictReader(f, delimiter=delimiter)
                records = list(reader)
            else:
                reader = csv.reader(f, delimiter=delimiter)
                rows = list(reader)
                if rows:
                    headers = [f"column_{i}" for i in range(len(rows[0]))]
                    records = [
                        {headers[i]: value for i, value in enumerate(row)}
                        for row in rows
                    ]
        
        imported = await save_records(db, records, job.target_table, job.mapping)
        
        return {
            "records_imported": imported,
            "records_failed": len(records) - imported,
        }


class APIImporter(BaseImporter):
    """Importer for REST APIs."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        import aiohttp
        
        config = source.config
        base_url = config["base_url"].rstrip("/")
        auth_type = config.get("auth_type", "none")
        timeout = config.get("timeout", 30)
        
        headers = config.get("headers", {}).copy()
        
        if auth_type == "bearer" and config.get("auth_token"):
            headers["Authorization"] = f"Bearer {config['auth_token']}"
        elif auth_type == "api_key" and config.get("api_key"):
            header_name = config.get("api_key_header", "X-API-Key")
            headers[header_name] = config["api_key"]
        
        async with aiohttp.ClientSession() as session:
            url = f"{base_url}"
            if job.query:
                url = f"{url}?{job.query}"
            
            auth = None
            if auth_type == "basic" and config.get("username"):
                auth = aiohttp.BasicAuth(config["username"], config["password"])
            
            async with session.get(
                url,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                records = data
                if isinstance(data, dict):
                    records = data.get("data") or data.get("results") or data.get("items") or [data]
                
                if not isinstance(records, list):
                    records = [records]
                
                imported = await save_records(db, records, job.target_table, job.mapping)
                
                return {
                    "records_imported": imported,
                    "records_failed": len(records) - imported,
                }


class SnowflakeImporter(BaseImporter):
    """Importer for Snowflake."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        try:
            import snowflake.connector
            
            config = source.config
            conn = snowflake.connector.connect(
                account=config["account"],
                warehouse=config["warehouse"],
                database=config["database"],
                schema=config["schema"],
                user=config["username"],
                password=config["password"],
                role=config.get("role"),
            )
            
            query = job.query or f"SELECT * FROM {job.target_table} LIMIT 10000"
            cursor = conn.cursor()
            cursor.execute(query)
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            records = [
                {columns[i]: value for i, value in enumerate(row)}
                for row in rows
            ]
            
            imported = await save_records(db, records, job.target_table, job.mapping)
            
            cursor.close()
            conn.close()
            
            return {
                "records_imported": imported,
                "records_failed": len(records) - imported,
            }
        except ImportError:
            raise RuntimeError("snowflake-connector-python not installed")


class BigQueryImporter(BaseImporter):
    """Importer for Google BigQuery."""
    
    async def import_data(self, db: AsyncSession, source: DataSource, job: ImportJob) -> Dict[str, Any]:
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
            
            config = source.config
            project_id = config["project_id"]
            dataset = config["dataset"]
            
            credentials = None
            if config.get("credentials_json"):
                creds_info = json.loads(config["credentials_json"])
                credentials = service_account.Credentials.from_service_account_info(creds_info)
            
            client = bigquery.Client(project=project_id, credentials=credentials)
            
            query = job.query or f"SELECT * FROM `{project_id}.{dataset}.{job.target_table}` LIMIT 10000"
            result = client.query(query).result()
            
            records = [dict(row) for row in result]
            
            imported = await save_records(db, records, job.target_table, job.mapping)
            
            return {
                "records_imported": imported,
                "records_failed": len(records) - imported,
            }
        except ImportError:
            raise RuntimeError("google-cloud-bigquery not installed")
