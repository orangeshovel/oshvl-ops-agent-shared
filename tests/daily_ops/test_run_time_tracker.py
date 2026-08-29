"""Tests for run_time_tracker: timestamp parsing and dynamic app-dir discovery."""

from datetime import datetime, timezone

from ops_agent.daily_ops.run_time_tracker import (
    _duration_for_date,
    _format_duration,
    _parse_timestamp,
    get_run_times,
)

ISO_LINE_START = "2026-05-15T21:10:29.966Z INFO myapp Starting\n"
ISO_LINE_END = "2026-05-15T21:10:48.134Z INFO myapp Finished\n"  # +18.168s


class TestParseTimestamp:
    def test_iso_8601_with_millis_z(self):
        ts = _parse_timestamp("2026-05-15T21:10:29.966Z INFO something")
        assert ts is not None
        assert ts.year == 2026
        assert ts.second == 29

    def test_iso_8601_no_millis(self):
        assert _parse_timestamp("2026-05-15T21:10:29Z INFO something") is not None

    def test_non_timestamp_line(self):
        assert _parse_timestamp("  some random text") is None

    def test_empty_line(self):
        assert _parse_timestamp("") is None


class TestDurationForDate:
    def test_duration_across_a_single_matching_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "run_20260515.log").write_text(ISO_LINE_START + ISO_LINE_END)

        duration = _duration_for_date(log_dir, datetime(2026, 5, 15))

        assert duration is not None
        assert 18 <= duration <= 20

    def test_duration_spans_multiple_files_for_the_same_date(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "fetch_20260515.log").write_text(ISO_LINE_START)
        (log_dir / "meltano_20260515.log").write_text(ISO_LINE_END)

        duration = _duration_for_date(log_dir, datetime(2026, 5, 15))

        assert duration is not None
        assert 18 <= duration <= 20

    def test_no_matching_files_returns_none(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        assert _duration_for_date(log_dir, datetime(2026, 5, 15)) is None

    def test_single_timestamp_returns_none(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "run_20260515.log").write_text(ISO_LINE_START)
        assert _duration_for_date(log_dir, datetime(2026, 5, 15)) is None


class TestFormatDuration:
    def test_under_a_minute(self):
        assert _format_duration(45) == "45s"

    def test_minutes_and_seconds(self):
        assert _format_duration(125) == "2m 05s"

    def test_one_minute_exact(self):
        assert _format_duration(60) == "1m 00s"


class TestGetRunTimes:
    def test_discovers_apps_and_reports_last_night_duration(self, tmp_path):
        (tmp_path / "shovel.data" / "logs").mkdir(parents=True)
        (tmp_path / "shovel.data" / "logs" / "meltano_20260515.log").write_text(
            "2026-05-15T21:00:00.000Z INFO start\n2026-05-15T21:00:30.000Z INFO end\n"
        )
        today = datetime(2026, 5, 16, 6, 0, 0, tzinfo=timezone.utc)

        result = get_run_times(today=today, app_data_root=tmp_path)

        assert "shovel.data" in result
        assert result["shovel.data"]["last_night_secs"] == 30.0
        assert result["shovel.data"]["last_night_str"] == "30s"

    def test_no_log_returns_na(self, tmp_path):
        (tmp_path / "empty-app" / "logs").mkdir(parents=True)
        today = datetime(2026, 5, 16, 6, 0, 0, tzinfo=timezone.utc)

        result = get_run_times(today=today, app_data_root=tmp_path)

        stats = result["empty-app"]
        assert stats["last_night_secs"] is None
        assert stats["last_night_str"] == "n/a"

    def test_missing_root_returns_empty_dict(self, tmp_path):
        today = datetime(2026, 5, 16, 6, 0, 0, tzinfo=timezone.utc)
        assert get_run_times(today=today, app_data_root=tmp_path / "nope") == {}
