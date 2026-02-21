"""
FORESIGHT — Connection Testers

Functions to test connectivity to various external data sources.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)


async def test_connection(source_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Test connection to a data source."""
    testers = {
        "postgresql": _test_postgresql,
        "mysql": _test_mysql,
        "mongodb": _test_mongodb,
        "csv": _test_csv,
        "api": _test_api,
        "snowflake": _test_snowflake,
        "bigquery": _test_bigquery,
    }
    
    tester = testers.get(source_type)
    if not tester:
        raise ValueError(f"Unsupported source type: {source_type}")
    
    return await tester(config)


async def _test_postgresql(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test PostgreSQL connection."""
    import asyncpg
    
    conn = await asyncpg.connect(
        host=config["host"],
        port=config.get("port", 5432),
        database=config["database"],
        user=config["username"],
        password=config["password"],
        ssl=config.get("ssl_mode", "prefer"),
        timeout=10,
    )
    
    try:
        # Test query
        version = await conn.fetchval("SELECT version()")
        db_name = await conn.fetchval("SELECT current_database()")
        
        # Get table count
        tables = await conn.fetch(
            "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' LIMIT 10"
        )
        
        return {
            "version": version,
            "database": db_name,
            "tables_found": len(tables),
            "sample_tables": [f"{t['schemaname']}.{t['tablename']}" for t in tables[:5]],
        }
    finally:
        await conn.close()


async def _test_mysql(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test MySQL connection."""
    try:
        import aiomysql
        
        conn = await aiomysql.connect(
            host=config["host"],
            port=config.get("port", 3306),
            db=config["database"],
            user=config["username"],
            password=config["password"],
            timeout=10,
        )
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT VERSION()")
            version = await cur.fetchone()
            
            await cur.execute("SELECT DATABASE()")
            db_name = await cur.fetchone()
            
            await cur.execute("SHOW TABLES LIMIT 10")
            tables = await cur.fetchall()
        
        conn.close()
        
        return {
            "version": version[0] if version else None,
            "database": db_name[0] if db_name else None,
            "tables_found": len(tables),
            "sample_tables": [t[0] for t in tables[:5]],
        }
    except ImportError:
        # Fallback if aiomysql not installed
        return {"note": "aiomysql not installed, connection not verified"}


async def _test_mongodb(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test MongoDB connection."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(
            config["connection_string"],
            serverSelectionTimeoutMS=10000,
        )
        
        # Test connection
        await client.admin.command("ping")
        
        db = client[config["database"]]
        
        # Get collection list
        collections = await db.list_collection_names()
        
        # Get server info
        server_info = await client.server_info()
        
        client.close()
        
        return {
            "version": server_info.get("version"),
            "database": config["database"],
            "collections_found": len(collections),
            "sample_collections": collections[:5],
        }
    except Exception as e:
        raise Exception(f"MongoDB connection failed: {e}")


async def _test_csv(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test CSV file access."""
    import os
    import csv
    
    file_path = config["file_path"]
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"Cannot read file: {file_path}")
    
    # Try to read first few rows
    delimiter = config.get("delimiter", ",")
    encoding = config.get("encoding", "utf-8")
    has_header = config.get("has_header", True)
    
    with open(file_path, "r", encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = []
        for i, row in enumerate(reader):
            if i >= 5:
                break
            rows.append(row)
    
    file_size = os.path.getsize(file_path)
    
    return {
        "file_path": file_path,
        "file_size_bytes": file_size,
        "file_size_human": _format_bytes(file_size),
        "has_header": has_header,
        "delimiter": delimiter,
        "rows_sampled": len(rows),
        "columns": len(rows[0]) if rows else 0,
        "sample_data": rows[:3] if rows else [],
    }


async def _test_api(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test API endpoint."""
    import aiohttp
    
    base_url = config["base_url"].rstrip("/")
    auth_type = config.get("auth_type", "none")
    timeout = config.get("timeout", 30)
    
    headers = config.get("headers", {}).copy()
    
    # Add auth headers
    if auth_type == "bearer" and config.get("auth_token"):
        headers["Authorization"] = f"Bearer {config['auth_token']}"
    elif auth_type == "api_key" and config.get("api_key"):
        header_name = config.get("api_key_header", "X-API-Key")
        headers[header_name] = config["api_key"]
    
    async with aiohttp.ClientSession() as session:
        start_time = asyncio.get_event_loop().time()
        
        try:
            if auth_type == "basic" and config.get("username") and config.get("password"):
                auth = aiohttp.BasicAuth(config["username"], config["password"])
            else:
                auth = None
            
            async with session.get(
                base_url,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                
                response_text = await response.text()
                
                return {
                    "url": base_url,
                    "status_code": response.status,
                    "response_time_ms": round(elapsed_ms, 2),
                    "content_type": response.headers.get("Content-Type"),
                    "content_length": len(response_text),
                    "success": response.status < 400,
                }
        except asyncio.TimeoutError:
            raise Exception(f"Request timed out after {timeout} seconds")


async def _test_snowflake(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test Snowflake connection."""
    try:
        import snowflake.connector
        
        conn_params = {
            "account": config["account"],
            "warehouse": config["warehouse"],
            "database": config["database"],
            "schema": config["schema"],
            "user": config["username"],
            "password": config["password"],
            "role": config.get("role"),
            "login_timeout": 10,
        }
        
        conn = snowflake.connector.connect(**conn_params)
        
        cursor = conn.cursor()
        cursor.execute("SELECT current_version(), current_database(), current_schema()")
        row = cursor.fetchone()
        
        # Get tables
        cursor.execute("SHOW TABLES LIMIT 10")
        tables = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "version": row[0],
            "database": row[1],
            "schema": row[2],
            "tables_found": len(tables),
            "sample_tables": [t[1] for t in tables[:5]],
        }
    except ImportError:
        return {"note": "snowflake-connector-python not installed, connection not verified"}


async def _test_bigquery(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test BigQuery connection."""
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
        
        project_id = config["project_id"]
        dataset = config["dataset"]
        
        credentials = None
        if config.get("credentials_json"):
            creds_info = json.loads(config["credentials_json"])
            credentials = service_account.Credentials.from_service_account_info(creds_info)
        
        client = bigquery.Client(project=project_id, credentials=credentials)
        
        # Test query
        query = f"SELECT count(*) as table_count FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`"
        result = client.query(query).result()
        table_count = list(result)[0].table_count
        
        # Get sample tables
        tables = list(client.list_tables(f"{project_id}.{dataset}"))
        
        return {
            "project": project_id,
            "dataset": dataset,
            "tables_found": table_count,
            "sample_tables": [t.table_id for t in tables[:5]],
        }
    except ImportError:
        return {"note": "google-cloud-bigquery not installed, connection not verified"}


def _format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
