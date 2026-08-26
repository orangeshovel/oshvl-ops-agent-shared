"""
App run-time tracker for oshvl-ops-agent's daily digest.

For each app discovered under /app-data/*/logs/, parses first/last ISO 8601
timestamps across that day's *.log files, computes the run duration, and
compares against the 30-day average.

Unlike shovel.watch's original legacy/run_time_tracker.py (which this
replaces), apps and log directories are discovered dynamically rather than a
fixed APP_LOGS list with a hardcoded per-app filename prefix — this runs
across arbitrary compute nodes with differing app footprints. Duration is
computed across ALL of that day's *.log files for an app (min first-timestamp
to max last-timestamp), not just one prefix's file, which is a superset of
the original per-prefix behavior rather than a loss of information.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[\.,]\d+)?Z?")

APP_DATA_ROOT = Path(os.getenv("APP_DATA_ROOT", "/app-data"))

LOOKBACK_DAYS = 30
MIN_DAYS_FOR_AVG = 3


def _discover_app_log_dirs(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    return {
        entry.name: entry / "logs"
        for entry in sorted(root.iterdir())
        if entry.is_dir() and (entry / "logs").is_dir()
    }


def _parse_timestamp(line: str) -> datetime | None:
    m = _TS_RE.match(line.strip())
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _duration_for_date(log_dir: Path, date: datetime) -> float | None:
    """Return duration in seconds spanning first-to-last timestamp across that date's log files."""
    date_str = date.strftime("%Y%m%d")
    first = last = None
    for log_file in sorted(log_dir.glob(f"*{date_str}.log")):
        try:
            with open(log_file, errors="replace") as f:
                for line in f:
                    ts = _parse_timestamp(line)
                    if ts is None:
                        continue
                    if first is None or ts < first:
                        first = ts
                    if last is None or ts > last:
                        last = ts
        except OSError:
            continue
    if first is None or last is None or first == last:
        return None
    return (last - first).total_seconds()


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs:02d}s"


def get_run_times(
    today: datetime | None = None, app_data_root: Path | None = None
) -> dict[str, dict]:
    """Return run time stats for each discovered app.

    Returns a dict keyed by app name, each value containing:
        last_night_secs   — float or None
        last_night_str    — formatted string or "n/a"
        avg_secs          — float or None (30-day average)
        avg_str           — formatted string or "n/a"
        delta_pct         — float or None (positive = slower, negative = faster)
    """
    root = app_data_root or APP_DATA_ROOT
    if today is None:
        today = datetime.now(tz=timezone.utc)

    result = {}
    for app_name, log_dir in _discover_app_log_dirs(root).items():
        yesterday = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

        last_night_secs = _duration_for_date(log_dir, yesterday)

        durations = []
        for i in range(2, LOOKBACK_DAYS + 2):
            day = yesterday - timedelta(days=i - 1)
            d = _duration_for_date(log_dir, day)
            if d is not None:
                durations.append(d)

        avg_secs = (sum(durations) / len(durations)) if len(durations) >= MIN_DAYS_FOR_AVG else None

        delta_pct = None
        if last_night_secs is not None and avg_secs is not None and avg_secs > 0:
            delta_pct = round((last_night_secs - avg_secs) / avg_secs * 100, 1)

        result[app_name] = {
            "last_night_secs": last_night_secs,
            "last_night_str": (
                _format_duration(last_night_secs) if last_night_secs is not None else "n/a"
            ),
            "avg_secs": avg_secs,
            "avg_str": _format_duration(avg_secs) if avg_secs is not None else "n/a",
            "delta_pct": delta_pct,
        }

    return result
