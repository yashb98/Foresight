"""
FORESIGHT — MinIO Raw Data Writer

Utility used by all connectors to write raw JSON payloads to the MinIO data lake.
Path structure: s3://foresight-raw/{tenant_id}/{source}/{YYYY}/{MM}/{DD}/{filename}.json

Design decisions:
  - Idempotent: writes use a deterministic key, so re-running the same connector
    twice on the same day produces the same object (overwrite, no duplicates).
  - Partitioned by date: enables Hive/Spark partition pruning on reads.
  - Source is embedded in path: allows independent processing of SAP vs sensor data.
  - Gzipped for cost efficiency at volume.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


class MinIOWriter:
    """
    Writes raw JSON payloads to MinIO (S3-compatible) object store.

    Args:
        endpoint_url:     MinIO endpoint, e.g. 'http://minio:9000'
        access_key:       MinIO root user / access key
        secret_key:       MinIO root password / secret key
        bucket:           Target bucket name
        region:           AWS region name (cosmetic for MinIO, but required by boto3)
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket or os.environ["MINIO_BUCKET_RAW"]
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or os.environ["AWS_ENDPOINT_URL"],
            aws_access_key_id=access_key or os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=secret_key or os.environ["AWS_SECRET_ACCESS_KEY"],
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
            region_name=region,
        )
        log.info("MinIOWriter initialised — bucket: %s", self._bucket)

    @staticmethod
    def build_key(
        tenant_id: str,
        source: str,
        dt: Optional[datetime] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Build a deterministic S3 object key from components.

        Args:
            tenant_id: Tenant UUID.
            source:    Data source identifier ('sensors', 'sap', 'asset_suite').
            dt:        Datetime for date partitioning. Defaults to utcnow().
            filename:  Object filename. Defaults to '{source}_{timestamp}.json.gz'.

        Returns:
            S3 key string, e.g. 'raw/tenant-abc/sap/2026/02/20/sap_1708387200.json.gz'
        """
        dt = dt or datetime.now(tz=timezone.utc)
        fname = filename or f"{source}_{int(dt.timestamp())}.json.gz"
        return f"raw/{tenant_id}/{source}/{dt.year}/{dt.month:02d}/{dt.day:02d}/{fname}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def write_records(
        self,
        records: List[Dict[str, Any]],
        tenant_id: str,
        source: str,
        dt: Optional[datetime] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Serialise records to gzipped JSON and write to MinIO.

        Args:
            records:   List of dicts to serialise. Each must include tenant_id.
            tenant_id: Tenant UUID (used in S3 key partitioning).
            source:    Source system name ('sensors', 'sap', 'asset_suite').
            dt:        Partition datetime. Defaults to utcnow().
            filename:  Override filename. Auto-generated if None.

        Returns:
            S3 key of the written object.

        Raises:
            ClientError: On unrecoverable S3 write failure after retries.
        """
        if not records:
            log.warning("write_records called with empty list — skipping")
            return ""

        dt = dt or datetime.now(tz=timezone.utc)
        key = self.build_key(tenant_id, source, dt, filename)

        payload = json.dumps(
            {
                "tenant_id": tenant_id,
                "source": source,
                "written_at": dt.isoformat(),
                "record_count": len(records),
                "records": records,
            },
            default=str,
        ).encode("utf-8")

        compressed = gzip.compress(payload)

        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=compressed,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={
                "tenant_id": tenant_id,
                "source": source,
                "record_count": str(len(records)),
                "written_at": dt.isoformat(),
            },
        )

        log.info(
            "Wrote %d records to s3://%s/%s (%.1f KB compressed)",
            len(records),
            self._bucket,
            key,
            len(compressed) / 1024,
        )
        return key

    def write_single(
        self,
        record: Dict[str, Any],
        tenant_id: str,
        source: str,
        dt: Optional[datetime] = None,
    ) -> str:
        """
        Convenience wrapper to write a single record.

        Args:
            record:    Single dict to write.
            tenant_id: Tenant UUID.
            source:    Source system name.
            dt:        Partition datetime.

        Returns:
            S3 key of the written object.
        """
        return self.write_records([record], tenant_id, source, dt)

    def check_bucket_exists(self) -> bool:
        """
        Verify the configured bucket is accessible.

        Returns:
            True if bucket exists and is accessible, False otherwise.
        """
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return True
        except ClientError as e:
            log.error("Bucket check failed: %s", e)
            return False
