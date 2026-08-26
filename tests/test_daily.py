"""Tests for daily.py orchestration (replaces shovel.watch's shovel_watch.py)."""

from unittest.mock import patch

from ops_agent.daily import main


class TestDailyMain:
    @patch("ops_agent.daily.send_nightly_digest", return_value=True)
    @patch("ops_agent.daily.get_run_times", return_value={})
    @patch("ops_agent.daily.collect_metrics", return_value={})
    @patch("ops_agent.daily.scan_logs", return_value=False)
    @patch("ops_agent.daily.send_alert")
    @patch("ops_agent.daily.run_backup", return_value=True)
    @patch("ops_agent.daily.setup_logging")
    def test_success_path_returns_zero_and_skips_failure_alert(
        self, mock_setup, mock_backup, mock_alert, mock_scan, mock_metrics, mock_run_times, mock_digest, tmp_path
    ):
        exit_code = main(["--log-dir", str(tmp_path)])

        assert exit_code == 0
        mock_alert.assert_not_called()
        mock_digest.assert_called_once()

    @patch("ops_agent.daily.send_nightly_digest", return_value=True)
    @patch("ops_agent.daily.get_run_times", return_value={})
    @patch("ops_agent.daily.collect_metrics", return_value={})
    @patch("ops_agent.daily.scan_logs", return_value=False)
    @patch("ops_agent.daily.send_alert")
    @patch("ops_agent.daily.run_backup", return_value=False)
    @patch("ops_agent.daily.setup_logging")
    def test_backup_failure_sends_alert_and_returns_nonzero(
        self, mock_setup, mock_backup, mock_alert, mock_scan, mock_metrics, mock_run_times, mock_digest, tmp_path
    ):
        exit_code = main(["--log-dir", str(tmp_path)])

        assert exit_code == 1
        mock_alert.assert_called_once()
        assert "backup failed" in mock_alert.call_args[1]["title"]
