"""Tests for metrics.py (moved from shovel.watch's legacy/metrics_collector.py, unchanged logic)."""

from unittest.mock import MagicMock, patch

from ops_agent.daily_ops.metrics import (
    _cpu_load,
    _disk,
    _failed_services,
    _memory,
    _uptime,
    collect_metrics,
)

FAKE_LOADAVG = "0.12 0.08 0.05 1/256 12345\n"
FAKE_MEMINFO = (
    "MemTotal:        8192000 kB\n"
    "MemFree:         1024000 kB\n"
    "MemAvailable:    4096000 kB\n"
    "SwapTotal:       2048000 kB\n"
    "SwapFree:        1024000 kB\n"
)
FAKE_UPTIME = "1234567.89 2345678.90\n"


class TestCpuLoad:
    @patch("ops_agent.daily_ops.metrics._read_proc", return_value=FAKE_LOADAVG)
    def test_cpu_load_values(self, _):
        result = _cpu_load()
        assert result["load_1"] == 0.12
        assert result["load_5"] == 0.08
        assert result["load_15"] == 0.05


class TestMemory:
    @patch("ops_agent.daily_ops.metrics._read_proc", return_value=FAKE_MEMINFO)
    def test_memory_values(self, _):
        result = _memory()
        assert result["mem_total_gb"] == round(8192000 / 1024 / 1024, 2)
        assert result["mem_pct"] > 0
        assert result["swap_used_gb"] == round(1024000 / 1024 / 1024, 2)

    @patch("ops_agent.daily_ops.metrics._read_proc", return_value=FAKE_MEMINFO)
    def test_memory_used_is_total_minus_available(self, _):
        result = _memory()
        expected_used_kb = 8192000 - 4096000
        assert result["mem_used_gb"] == round(expected_used_kb / 1024 / 1024, 2)


class TestDisk:
    def test_disk_returns_none_for_missing_mount(self):
        result = _disk("/nonexistent_mount_xyz", "test")
        assert result["disk_test_pct"] is None
        assert result["disk_test_used_gb"] is None

    def test_disk_root_returns_values(self):
        result = _disk("/", "root")
        assert result["disk_root_pct"] is not None
        assert result["disk_root_total_gb"] > 0
        assert result["disk_root_used_gb"] >= 0


class TestUptime:
    @patch("ops_agent.daily_ops.metrics._read_proc", return_value=FAKE_UPTIME)
    def test_uptime_days(self, _):
        assert "d" in _uptime()

    @patch("ops_agent.daily_ops.metrics._read_proc", return_value="3723.0 7000.0\n")
    def test_uptime_hours(self, _):
        assert _uptime() == "1h 2m"

    @patch("ops_agent.daily_ops.metrics._read_proc", return_value="90.0 180.0\n")
    def test_uptime_minutes(self, _):
        assert _uptime() == "1m"


class TestFailedServices:
    @patch("subprocess.run")
    def test_failed_services_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        assert _failed_services() == []

    @patch("subprocess.run")
    def test_failed_services_returned(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="shovel-data.service loaded failed failed Shovel Data\n", returncode=1
        )
        assert "shovel-data.service" in _failed_services()

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_failed_services_no_systemctl(self, _):
        assert _failed_services() == []


class TestCollectMetrics:
    @patch("ops_agent.daily_ops.metrics._read_proc")
    @patch("ops_agent.daily_ops.metrics._failed_services", return_value=[])
    def test_collect_metrics_returns_all_keys(self, _, mock_read):
        mock_read.side_effect = (
            lambda p: FAKE_LOADAVG if "loadavg" in p else FAKE_MEMINFO if "meminfo" in p else FAKE_UPTIME
        )
        result = collect_metrics()
        for key in (
            "load_1", "load_5", "load_15", "mem_pct", "mem_used_gb",
            "disk_root_pct", "disk_appdata_pct", "uptime_str", "failed_services",
        ):
            assert key in result, f"Missing key: {key}"
