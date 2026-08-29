"""Tests for backup.py — net-new coverage; no equivalent existed in shovel.watch."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ops_agent.daily_ops.backup import (
    cleanup_old_exports,
    compress_file,
    export_database,
    run_backup,
    upload_to_s3,
)


class TestExportDatabase:
    @patch("subprocess.run")
    def test_calls_pg_dump_with_expected_args(self, mock_run, tmp_path):
        sql_file = tmp_path / "mydb_20260101_000000.sql"

        def fake_run(*a, **kw):
            sql_file.write_text("-- dump")
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_run
        with patch("ops_agent.daily_ops.backup.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260101_000000"
            export_database("dbhost", "5432", "mydb", "dbuser", "secret", str(tmp_path))

        args = mock_run.call_args[0][0]
        assert args[0] == "pg_dump"
        assert "-h" in args and "dbhost" in args
        assert mock_run.call_args[1]["env"]["PGPASSWORD"] == "secret"

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "pg_dump", stderr="boom"))
    def test_raises_on_dump_failure(self, mock_run, tmp_path):
        with pytest.raises(subprocess.CalledProcessError):
            export_database("dbhost", "5432", "mydb", "dbuser", "secret", str(tmp_path))


class TestCompressFile:
    def test_compresses_and_removes_original(self, tmp_path):
        sql_file = tmp_path / "dump.sql"
        sql_file.write_text("some sql content" * 100)

        gz_file = compress_file(sql_file)

        assert gz_file.exists()
        assert gz_file.name == "dump.sql.gz"
        assert not sql_file.exists()


class TestUploadToS3:
    @patch("boto3.client")
    def test_uploads_with_standard_ia_storage_class(self, mock_client_factory, tmp_path):
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        f = tmp_path / "dump.sql.gz"
        f.write_text("x")

        upload_to_s3(f, "my-bucket", "us-east-1")

        mock_client.upload_file.assert_called_once()
        args, kwargs = mock_client.upload_file.call_args
        assert args[1] == "my-bucket"
        assert kwargs["ExtraArgs"] == {"StorageClass": "STANDARD_IA"}


class TestCleanupOldExports:
    def test_removes_only_files_older_than_keep_days(self, tmp_path):
        import os
        import time

        old = tmp_path / "old.sql.gz"
        new = tmp_path / "new.sql.gz"
        old.write_text("x")
        new.write_text("x")
        old_mtime = time.time() - 10 * 86400
        os.utime(old, (old_mtime, old_mtime))

        cleanup_old_exports(str(tmp_path), days_to_keep=7)

        assert not old.exists()
        assert new.exists()


class TestRunBackup:
    def test_missing_required_env_vars_returns_false(self, monkeypatch, tmp_path):
        for var in ("PG_HOST", "PG_DATABASE", "PG_USER", "PG_PASSWORD", "S3_BUCKET"):
            monkeypatch.delenv(var, raising=False)

        assert run_backup(str(tmp_path / "logs"), str(tmp_path / "exports")) is False

    @patch("ops_agent.daily_ops.backup.upload_to_s3")
    @patch("ops_agent.daily_ops.backup.compress_file")
    @patch("ops_agent.daily_ops.backup.export_database")
    def test_full_workflow_returns_true_on_success(
        self, mock_export, mock_compress, mock_upload, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("PG_HOST", "dbhost")
        monkeypatch.setenv("PG_DATABASE", "mydb")
        monkeypatch.setenv("PG_USER", "dbuser")
        monkeypatch.setenv("PG_PASSWORD", "secret")
        monkeypatch.setenv("S3_BUCKET", "my-bucket")

        sql_file = tmp_path / "mydb.sql"
        gz_file = tmp_path / "mydb.sql.gz"
        sql_file.write_text("x")
        gz_file.write_text("x")
        mock_export.return_value = sql_file
        mock_compress.return_value = gz_file

        result = run_backup(str(tmp_path / "logs"), str(tmp_path))

        assert result is True
        mock_upload.assert_called_once()

    @patch("ops_agent.daily_ops.backup.export_database", side_effect=RuntimeError("boom"))
    def test_exception_during_export_returns_false(self, _, monkeypatch, tmp_path):
        monkeypatch.setenv("PG_HOST", "dbhost")
        monkeypatch.setenv("PG_DATABASE", "mydb")
        monkeypatch.setenv("PG_USER", "dbuser")
        monkeypatch.setenv("PG_PASSWORD", "secret")
        monkeypatch.setenv("S3_BUCKET", "my-bucket")

        assert run_backup(str(tmp_path / "logs"), str(tmp_path)) is False
