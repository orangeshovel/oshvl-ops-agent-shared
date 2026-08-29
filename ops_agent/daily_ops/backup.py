#!/usr/bin/env python3
"""Database backup utility - exports PostgreSQL to S3.

Moved from orangeshovel's apps/shovel.watch/legacy/backup.py: fully
host-generic already (config is entirely env-var driven), no changes needed
beyond the module's new home.
"""

import gzip
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ISOFormatter(logging.Formatter):
    """Log formatter that emits ISO 8601 timestamps with milliseconds and UTC offset."""

    def formatTime(self, record, datefmt=None):
        from datetime import timezone

        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"


def setup_logging(log_dir):
    """Configure logging with date-suffixed log file."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"backup_{datetime.now().strftime('%Y%m%d')}.log"

    _fmt = ISOFormatter("%(asctime)s %(levelname)s %(message)s")
    _file_handler = logging.FileHandler(log_file)
    _file_handler.setFormatter(_fmt)
    _console_handler = logging.StreamHandler(sys.stdout)
    _console_handler.setFormatter(_fmt)
    logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
    logger.info(f"Logging to {log_file}")


def export_database(db_host, db_port, db_name, db_user, db_password, export_dir):
    """Export PostgreSQL database to SQL file."""
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_file = export_dir / f"{db_name}_{timestamp}.sql"

    logger.info(f"Exporting database: {db_name}")

    env = os.environ.copy()
    env["PGPASSWORD"] = db_password

    try:
        subprocess.run(
            [
                "pg_dump",
                "-h",
                db_host,
                "-p",
                db_port,
                "-U",
                db_user,
                "-d",
                db_name,
                "-f",
                str(sql_file),
                "--verbose",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        file_size = sql_file.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"Export completed: {sql_file.name} ({file_size:.1f} MB)")
        return sql_file

    except subprocess.CalledProcessError as e:
        logger.error(f"Database export failed: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during export: {e}")
        raise


def compress_file(sql_file):
    """Compress SQL file with gzip."""
    logger.info(f"Compressing: {sql_file.name}")

    gz_file = Path(str(sql_file) + ".gz")

    try:
        with open(sql_file, "rb") as f_in:
            with gzip.open(gz_file, "wb") as f_out:
                f_out.writelines(f_in)

        sql_file.unlink()

        file_size = gz_file.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"Compression completed: {gz_file.name} ({file_size:.1f} MB)")
        return gz_file

    except Exception as e:
        logger.error(f"Compression failed: {e}")
        raise


def upload_to_s3(file_path, bucket_name, region):
    """Upload file to S3 bucket."""
    s3_key = f"backups/{file_path.name}"

    logger.info(f"Uploading to S3: {s3_key}")

    try:
        s3_client = boto3.client("s3", region_name=region)

        s3_client.upload_file(
            str(file_path),
            bucket_name,
            s3_key,
            ExtraArgs={"StorageClass": "STANDARD_IA"},
        )

        file_size = file_path.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"Upload complete: {file_size:.1f} MB")
        logger.info(f"S3 URL: s3://{bucket_name}/{s3_key}")

    except ClientError as e:
        logger.error(f"S3 upload failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        raise


def cleanup_old_exports(export_dir, days_to_keep=7):
    """Remove local export files older than specified days."""
    logger.info(f"Cleaning up exports older than {days_to_keep} days")

    export_dir = Path(export_dir)
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)

    removed_count = 0
    for file_path in export_dir.glob("*.sql.gz"):
        if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_date:
            logger.info(f"Removing old export: {file_path.name}")
            file_path.unlink()
            removed_count += 1

    if removed_count > 0:
        logger.info(f"Removed {removed_count} old export(s)")
    else:
        logger.info("No old exports to remove")


def run_backup(log_dir, export_dir, keep_days=7):
    """Run the full backup workflow. Returns True on success, False on failure."""
    db_host = os.getenv("PG_HOST")
    db_port = os.getenv("PG_PORT", "5432")
    db_name = os.getenv("PG_DATABASE")
    db_user = os.getenv("PG_USER")
    db_password = os.getenv("PG_PASSWORD")
    s3_bucket = os.getenv("S3_BUCKET")
    s3_region = os.getenv("S3_REGION", "us-east-1")

    required_vars = {
        "PG_HOST": db_host,
        "PG_DATABASE": db_name,
        "PG_USER": db_user,
        "PG_PASSWORD": db_password,
        "S3_BUCKET": s3_bucket,
    }

    missing_vars = [key for key, value in required_vars.items() if not value]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False

    try:
        logger.info("Starting database backup")
        logger.info(f"Database: {db_name} on {db_host}")
        logger.info(f"S3 Bucket: {s3_bucket}")

        sql_file = export_database(db_host, db_port, db_name, db_user, db_password, export_dir)
        gz_file = compress_file(sql_file)
        upload_to_s3(gz_file, s3_bucket, s3_region)
        cleanup_old_exports(export_dir, keep_days)

        logger.info("Backup completed successfully")
        return True

    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False
