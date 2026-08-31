"""Tests for log_monitor: error-detection logic and dynamic app-dir discovery."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from ops_agent.daily_ops.log_monitor import _discover_app_log_dirs, _scan_file, scan_logs


def _write_log(lines: list[str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False)
    tmp.write("\n".join(lines) + "\n")
    tmp.close()
    return Path(tmp.name)


class TestScanFile:
    def test_detects_real_error(self):
        path = _write_log(["2026-05-15 ERROR: Something went wrong"])
        assert _scan_file(path) != []

    def test_detects_traceback(self):
        path = _write_log(["Traceback (most recent call last):"])
        assert _scan_file(path) != []

    def test_excludes_dbt_summary_line(self):
        line = "2026-05-15T21:00:36Z [info     ] Done. PASS=11 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=11"
        assert _scan_file(_write_log([line])) == []

    def test_excludes_dbt_summary_line_with_nonzero_error(self):
        line = "2026-05-15T21:00:36Z [info     ] Done. PASS=9 WARN=0 ERROR=2 SKIP=0 NO-OP=0 TOTAL=11"
        assert _scan_file(_write_log([line])) == []

    def test_excludes_log_monitor_summary_line(self):
        line = "2026-05-24T05:05:32.237Z WARNING Found 1 error line(s) in shovel.watch logs"
        assert _scan_file(_write_log([line])) == []

    def test_clean_log_returns_empty(self):
        path = _write_log(["Everything is fine", "Pipeline completed successfully"])
        assert _scan_file(path) == []

    def test_ignores_lowercase_error_in_message_text(self):
        # Regression: a DEBUG/INFO line whose free-text content happens to
        # contain the word "error" (e.g. an RSS article title logged
        # verbatim) must not be treated as an error-level line.
        line = (
            "2026-08-30T21:10:27.872Z DEBUG rssaggregator We are parsing "
            "Arbitrary code execution in QubesOS via copy-to-VM error "
            "reporting backchannel"
        )
        assert _scan_file(_write_log([line])) == []


class TestDiscoverAppLogDirs:
    def test_discovers_apps_with_logs_subdir(self, tmp_path):
        for name in ("shovel.data", "shovel.watch"):
            (tmp_path / name / "logs").mkdir(parents=True)
        (tmp_path / "no-logs-here").mkdir()

        discovered = _discover_app_log_dirs(tmp_path)

        assert set(discovered) == {"shovel.data", "shovel.watch"}
        assert discovered["shovel.data"] == tmp_path / "shovel.data" / "logs"

    def test_missing_root_returns_empty(self, tmp_path):
        assert _discover_app_log_dirs(tmp_path / "does-not-exist") == {}


class TestScanLogs:
    def test_no_errors_across_discovered_apps(self, tmp_path):
        app_log_dir = tmp_path / "myapp" / "logs"
        app_log_dir.mkdir(parents=True)
        (app_log_dir / "run_20260101.log").write_text("all good\n")

        with patch("ops_agent.daily_ops.log_monitor.send_alert") as mock_alert:
            found = scan_logs(lookback_hours=999999, app_data_root=tmp_path)

        assert found is False
        mock_alert.assert_not_called()

    def test_errors_trigger_one_alert_per_app(self, tmp_path):
        app_log_dir = tmp_path / "myapp" / "logs"
        app_log_dir.mkdir(parents=True)
        (app_log_dir / "run_20260101.log").write_text("ERROR: boom\n")

        with patch("ops_agent.daily_ops.log_monitor.send_alert") as mock_alert:
            found = scan_logs(lookback_hours=999999, app_data_root=tmp_path)

        assert found is True
        mock_alert.assert_called_once()
        _, kwargs = mock_alert.call_args
        assert kwargs["details"]["app"] == "myapp"
