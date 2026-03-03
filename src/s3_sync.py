"""S3 sync utilities for keeping the local SQLite DB in sync with S3.

When S3_BUCKET is set, mutation CLI commands automatically pull the latest DB
from S3 before running and push the updated DB back after success. This makes
S3 the single source of truth and keeps local and Lambda state consistent.

Required env vars:
    S3_BUCKET   — bucket name (e.g. jobhunter-data-prod)
    S3_DB_KEY   — object key (default: jobhunter/jobs.db)
"""

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("jobhunter.s3_sync")

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _local_db_path() -> str:
    """Derive the local DB file path from DATABASE_URL (or default)."""
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/jobs.db")
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///") :]
    return "./data/jobs.db"


def is_configured() -> bool:
    """Return True when S3_BUCKET is set and S3 sync is active."""
    return bool(os.environ.get("S3_BUCKET"))


def pull() -> bool:
    """Download the DB from S3 to the local path.

    Returns:
        True if the file was downloaded, False if not configured or not found.

    Raises:
        botocore.exceptions.ClientError on unexpected S3 errors.
    """
    bucket = os.environ.get("S3_BUCKET")
    key = os.environ.get("S3_DB_KEY", "jobhunter/jobs.db")
    if not bucket:
        return False

    local_path = _local_db_path()
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        _get_s3().download_file(bucket, key, local_path)
        logger.info("Pulled s3://%s/%s → %s", bucket, key, local_path)
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchKey", "403"):
            logger.info("No existing DB at s3://%s/%s", bucket, key)
            return False
        raise


def push() -> bool:
    """Upload the local DB to S3.

    Returns:
        True if pushed, False if not configured or local file is missing.

    Raises:
        botocore.exceptions.ClientError on unexpected S3 errors.
    """
    bucket = os.environ.get("S3_BUCKET")
    key = os.environ.get("S3_DB_KEY", "jobhunter/jobs.db")
    if not bucket:
        return False

    local_path = _local_db_path()
    if not Path(local_path).exists():
        logger.warning("Local DB not found at %s, skipping push", local_path)
        return False

    _get_s3().upload_file(local_path, bucket, key)
    logger.info("Pushed %s → s3://%s/%s", local_path, bucket, key)
    return True
