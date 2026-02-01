"""Cloud storage client for R2 (primary) and S3 (backup)."""

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Lazy import boto3 to avoid hard dependency
_boto3 = None


def _get_boto3():
    """Lazy import boto3."""
    global _boto3
    if _boto3 is None:
        try:
            import boto3
            _boto3 = boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for network features. "
                "Install with: pip install boto3"
            )
    return _boto3


class CloudStorageConfig(BaseModel):
    """Configuration for cloud storage."""

    # R2 (primary - Cloudflare edge-optimized)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "brainbot-network"

    # S3 (backup - cold storage)
    s3_access_key_id: str = ""  # Can be same as R2 if using same credentials
    s3_secret_access_key: str = ""
    s3_bucket: str = "brainbot-backup"
    s3_region: str = "us-east-1"

    # Behavior
    enable_s3_backup: bool = True
    backup_on_write: bool = False  # If True, write to S3 on every write

    @property
    def r2_endpoint(self) -> str:
        """Get R2 endpoint URL."""
        if not self.r2_account_id:
            return ""
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def is_configured(self) -> bool:
        """Check if R2 is configured."""
        return bool(
            self.r2_account_id
            and self.r2_access_key_id
            and self.r2_secret_access_key
        )


class StorageClient:
    """
    Unified client for R2 and S3 storage.

    R2 is used as primary storage (edge-optimized, fast).
    S3 is used as cold backup (optional).
    """

    def __init__(self, config: CloudStorageConfig):
        """
        Initialize storage client.

        Args:
            config: Cloud storage configuration
        """
        self.config = config
        self._r2_client = None
        self._s3_client = None

    @property
    def r2_client(self):
        """Get or create R2 client."""
        if self._r2_client is None:
            if not self.config.is_configured:
                raise ValueError("R2 is not configured")

            boto3 = _get_boto3()
            self._r2_client = boto3.client(
                "s3",
                endpoint_url=self.config.r2_endpoint,
                aws_access_key_id=self.config.r2_access_key_id,
                aws_secret_access_key=self.config.r2_secret_access_key,
                region_name="auto",
            )
        return self._r2_client

    @property
    def s3_client(self):
        """Get or create S3 client."""
        if self._s3_client is None:
            if not self.config.s3_access_key_id:
                # Use same credentials as R2
                access_key = self.config.r2_access_key_id
                secret_key = self.config.r2_secret_access_key
            else:
                access_key = self.config.s3_access_key_id
                secret_key = self.config.s3_secret_access_key

            boto3 = _get_boto3()
            self._s3_client = boto3.client(
                "s3",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=self.config.s3_region,
            )
        return self._s3_client

    def write(
        self,
        key: str,
        data: Union[str, bytes, dict],
        backup: bool = False,
        content_type: Optional[str] = None,
    ) -> bool:
        """
        Write data to R2 (and optionally S3).

        Args:
            key: Object key (path in bucket)
            data: Data to write (str, bytes, or dict for JSON)
            backup: If True, also write to S3
            content_type: Optional content type

        Returns:
            True if successful
        """
        # Prepare data
        if isinstance(data, dict):
            body = json.dumps(data, indent=2, default=str).encode("utf-8")
            content_type = content_type or "application/json"
        elif isinstance(data, str):
            body = data.encode("utf-8")
            content_type = content_type or "text/plain"
        else:
            body = data
            content_type = content_type or "application/octet-stream"

        try:
            # Write to R2
            self.r2_client.put_object(
                Bucket=self.config.r2_bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            logger.debug(f"Wrote to R2: {key}")

            # Optionally backup to S3
            should_backup = backup or self.config.backup_on_write
            if should_backup and self.config.enable_s3_backup:
                try:
                    self.s3_client.put_object(
                        Bucket=self.config.s3_bucket,
                        Key=key,
                        Body=body,
                        ContentType=content_type,
                    )
                    logger.debug(f"Backed up to S3: {key}")
                except Exception as e:
                    logger.warning(f"S3 backup failed for {key}: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to write {key}: {e}")
            return False

    def read(
        self,
        key: str,
        fallback_to_s3: bool = True,
    ) -> Optional[bytes]:
        """
        Read data from R2 (with S3 fallback).

        Args:
            key: Object key
            fallback_to_s3: If True, try S3 if R2 fails

        Returns:
            Data as bytes, or None if not found
        """
        try:
            response = self.r2_client.get_object(
                Bucket=self.config.r2_bucket,
                Key=key,
            )
            return response["Body"].read()
        except Exception as e:
            logger.debug(f"R2 read failed for {key}: {e}")

            if fallback_to_s3 and self.config.enable_s3_backup:
                try:
                    response = self.s3_client.get_object(
                        Bucket=self.config.s3_bucket,
                        Key=key,
                    )
                    logger.debug(f"Fell back to S3 for {key}")
                    return response["Body"].read()
                except Exception as e2:
                    logger.debug(f"S3 fallback failed for {key}: {e2}")

            return None

    def read_json(
        self,
        key: str,
        fallback_to_s3: bool = True,
    ) -> Optional[dict]:
        """Read and parse JSON data."""
        data = self.read(key, fallback_to_s3)
        if data is None:
            return None

        try:
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to parse JSON from {key}: {e}")
            return None

    def read_text(
        self,
        key: str,
        fallback_to_s3: bool = True,
    ) -> Optional[str]:
        """Read data as text."""
        data = self.read(key, fallback_to_s3)
        if data is None:
            return None

        try:
            return data.decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to decode text from {key}: {e}")
            return None

    def delete(self, key: str, also_s3: bool = False) -> bool:
        """
        Delete object from R2 (and optionally S3).

        Args:
            key: Object key
            also_s3: If True, also delete from S3

        Returns:
            True if successful
        """
        try:
            self.r2_client.delete_object(
                Bucket=self.config.r2_bucket,
                Key=key,
            )
            logger.debug(f"Deleted from R2: {key}")

            if also_s3 and self.config.enable_s3_backup:
                try:
                    self.s3_client.delete_object(
                        Bucket=self.config.s3_bucket,
                        Key=key,
                    )
                    logger.debug(f"Deleted from S3: {key}")
                except Exception as e:
                    logger.warning(f"S3 delete failed for {key}: {e}")

            return True
        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}")
            return False

    def list_keys(
        self,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[str]:
        """
        List object keys with prefix.

        Args:
            prefix: Key prefix to filter by
            max_keys: Maximum number of keys to return

        Returns:
            List of object keys
        """
        try:
            response = self.r2_client.list_objects_v2(
                Bucket=self.config.r2_bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )

            keys = []
            for obj in response.get("Contents", []):
                keys.append(obj["Key"])

            return keys
        except Exception as e:
            logger.error(f"Failed to list keys with prefix {prefix}: {e}")
            return []

    def exists(self, key: str) -> bool:
        """Check if object exists in R2."""
        try:
            self.r2_client.head_object(
                Bucket=self.config.r2_bucket,
                Key=key,
            )
            return True
        except Exception:
            return False

    def get_metadata(self, key: str) -> Optional[dict]:
        """Get object metadata."""
        try:
            response = self.r2_client.head_object(
                Bucket=self.config.r2_bucket,
                Key=key,
            )
            return {
                "content_type": response.get("ContentType"),
                "content_length": response.get("ContentLength"),
                "last_modified": response.get("LastModified"),
                "etag": response.get("ETag"),
            }
        except Exception:
            return None

    def backup_to_s3(self, key: str) -> bool:
        """
        Backup a specific object from R2 to S3.

        Args:
            key: Object key to backup

        Returns:
            True if successful
        """
        if not self.config.enable_s3_backup:
            return False

        data = self.read(key, fallback_to_s3=False)
        if data is None:
            return False

        try:
            # Get content type from R2
            metadata = self.get_metadata(key)
            content_type = metadata.get("content_type") if metadata else "application/octet-stream"

            self.s3_client.put_object(
                Bucket=self.config.s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            logger.info(f"Backed up to S3: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to backup {key} to S3: {e}")
            return False

    def test_connection(self) -> dict:
        """
        Test R2 and S3 connections.

        Returns:
            Dict with connection status
        """
        result = {
            "r2": {"connected": False, "error": None},
            "s3": {"connected": False, "error": None},
        }

        # Test R2 (use head_bucket instead of list_buckets for bucket-scoped tokens)
        try:
            self.r2_client.head_bucket(Bucket=self.config.r2_bucket)
            result["r2"]["connected"] = True
        except Exception as e:
            result["r2"]["error"] = str(e)

        # Test S3
        if self.config.enable_s3_backup:
            try:
                self.s3_client.head_bucket(Bucket=self.config.s3_bucket)
                result["s3"]["connected"] = True
            except Exception as e:
                result["s3"]["error"] = str(e)

        return result
