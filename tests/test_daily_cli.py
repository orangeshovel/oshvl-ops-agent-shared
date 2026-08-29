"""Tests for daily_cli.py orchestration (cleanup, then backup/log-monitor/metrics/digest)."""

import argparse
import json
from unittest.mock import patch

from ops_agent.cleanup.targets import Target
from ops_agent.daily_cli import _run_cleanup, main


def _fake_config(**overrides):
    defaults = {
        "log_dir": "./logs",
        "report_dir": "./reports",
        "apply": False,
        "targets": [],
    }
    defaults.update(overrides)
    return type("Config", (), defaults)()


class TestRunCleanup:
    def test_dry_run_writes_report_and_does_not_delete(self, tmp_path, monkeypatch):
        stale_dir = tmp_path / "cache"
        stale_dir.mkdir()
        stale_file = stale_dir / "old.bin"
        stale_file.write_text("x")
        import os
        import time

        mtime = time.time() - 30 * 86400
        os.utime(stale_file, (mtime, mtime))

        report_dir = tmp_path / "reports"

        fake_config = _fake_config(
            report_dir=str(report_dir),
            targets=[
                Target(
                    name="cache",
                    description="d",
                    base_dir=str(stale_dir),
                    mode="age",
                    max_age_days=7,
                )
            ],
        )
        monkeypatch.setattr("ops_agent.daily_cli.load_config", lambda: fake_config)

        report = _run_cleanup(argparse.Namespace(apply=False))

        assert stale_file.exists()  # dry-run: nothing deleted
        report_files = list(report_dir.glob("cleanup_report_*.json"))
        assert len(report_files) == 1
        data = json.loads(report_files[0].read_text())
        assert data["apply"] is False
        assert data["targets"][0]["candidates"] == 1
        assert report.apply is False

    def test_apply_flag_overrides_config_dry_run_default(self, tmp_path, monkeypatch):
        stale_dir = tmp_path / "cache"
        stale_dir.mkdir()
        stale_file = stale_dir / "old.bin"
        stale_file.write_text("x")
        import os
        import time

        mtime = time.time() - 30 * 86400
        os.utime(stale_file, (mtime, mtime))

        fake_config = _fake_config(
            report_dir=str(tmp_path / "reports"),
            targets=[
                Target(
                    name="cache",
                    description="d",
                    base_dir=str(stale_dir),
                    mode="age",
                    max_age_days=7,
                )
            ],
        )
        monkeypatch.setattr("ops_agent.daily_cli.load_config", lambda: fake_config)

        _run_cleanup(argparse.Namespace(apply=True))

        assert not stale_file.exists()


class TestDailyCliMain:
    @patch("ops_agent.daily_cli.load_config")
    @patch("ops_agent.daily_cli.send_nightly_digest", return_value=True)
    @patch("ops_agent.daily_cli.get_run_times", return_value={})
    @patch("ops_agent.daily_cli.collect_metrics", return_value={})
    @patch("ops_agent.daily_cli.scan_logs", return_value=False)
    @patch("ops_agent.daily_cli.send_alert")
    @patch("ops_agent.daily_cli.run_backup", return_value=True)
    @patch("ops_agent.daily_cli.setup_logging")
    def test_success_path_returns_zero_and_skips_failure_alert(
        self,
        mock_setup,
        mock_backup,
        mock_alert,
        mock_scan,
        mock_metrics,
        mock_run_times,
        mock_digest,
        mock_load_config,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setenv("PG_HOST", "dbhost")
        mock_load_config.return_value = _fake_config(report_dir=str(tmp_path / "reports"))

        exit_code = main(["--log-dir", str(tmp_path)])

        assert exit_code == 0
        mock_backup.assert_called_once()
        mock_alert.assert_not_called()
        mock_digest.assert_called_once()

    @patch("ops_agent.daily_cli.load_config")
    @patch("ops_agent.daily_cli.send_nightly_digest", return_value=True)
    @patch("ops_agent.daily_cli.get_run_times", return_value={})
    @patch("ops_agent.daily_cli.collect_metrics", return_value={})
    @patch("ops_agent.daily_cli.scan_logs", return_value=False)
    @patch("ops_agent.daily_cli.send_alert")
    @patch("ops_agent.daily_cli.run_backup", return_value=False)
    @patch("ops_agent.daily_cli.setup_logging")
    def test_backup_failure_sends_alert_and_returns_nonzero(
        self,
        mock_setup,
        mock_backup,
        mock_alert,
        mock_scan,
        mock_metrics,
        mock_run_times,
        mock_digest,
        mock_load_config,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setenv("PG_HOST", "dbhost")
        mock_load_config.return_value = _fake_config(report_dir=str(tmp_path / "reports"))

        exit_code = main(["--log-dir", str(tmp_path)])

        assert exit_code == 1
        mock_alert.assert_called_once()
        assert "backup failed" in mock_alert.call_args[1]["title"]

    @patch("ops_agent.daily_cli.load_config")
    @patch("ops_agent.daily_cli.send_nightly_digest", return_value=True)
    @patch("ops_agent.daily_cli.get_run_times", return_value={})
    @patch("ops_agent.daily_cli.collect_metrics", return_value={})
    @patch("ops_agent.daily_cli.scan_logs", return_value=False)
    @patch("ops_agent.daily_cli.send_alert")
    @patch("ops_agent.daily_cli.run_backup")
    @patch("ops_agent.daily_cli.setup_logging")
    def test_no_pg_host_skips_backup_silently_and_returns_zero(
        self,
        mock_setup,
        mock_backup,
        mock_alert,
        mock_scan,
        mock_metrics,
        mock_run_times,
        mock_digest,
        mock_load_config,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.delenv("PG_HOST", raising=False)
        mock_load_config.return_value = _fake_config(report_dir=str(tmp_path / "reports"))

        exit_code = main(["--log-dir", str(tmp_path)])

        assert exit_code == 0
        mock_backup.assert_not_called()
        mock_alert.assert_not_called()
        mock_digest.assert_called_once()
