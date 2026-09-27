"""
Log monitor for oshvl-ops-agent.

Scans every app's /app-data/{app}/logs/ directory for ERROR-level lines
written in the last N hours, and sends a shovel.bot alert grouped by app if
any errors are found.

Unlike shovel.watch's original legacy/log_monitor.py (which this replaces),
app log directories are discovered dynamically by listing /app-data/*/logs/
rather than a fixed dict — this runs across arbitrary compute nodes with
differing app footprints, so it can't hardcode sibling app names.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from ops_agent.daily_ops.notify import send_alert

logger = logging.getLogger(__name__)

APP_DATA_ROOT = Path(os.getenv("APP_DATA_ROOT", "/app-data"))

# "ERROR"/"CRITICAL"/"FATAL" match a line's log level (all apps in this fleet
# use Python's %(levelname)s, which is always uppercase). Deliberately no
# lowercase "error" pattern: a lowercase, space-bounded "error" matches
# anywhere in a line's free-text message too, not just level markers, so it
# flagged unrelated DEBUG/INFO lines whose content happened to contain that
# word (e.g. rss-aggregator/nibbler logging an article title verbatim that
# contained "error" as a substring).
ERROR_PATTERNS = ["ERROR", "Traceback", "CRITICAL", "FATAL"]

# Lines containing these patterns are excluded even if they match ERROR_PATTERNS.
# Used to suppress false positives from stats summaries (e.g. dbt "ERROR=0" lines).
EXCLUDE_PATTERNS = [
    "PASS=",  # dbt run summary: "Done. PASS=11 WARN=0 ERROR=0 SKIP=0 ..."
    "error line(s)",  # this module's own "Found N error line(s) ..." summaries
]


def _discover_app_log_dirs(root: Path) -> dict[str, Path]:
    """Return {app_name: log_dir} for every app with an existing logs/ dir under root."""
    if not root.exists():
        return {}
    result = {}
    for entry in sorted(root.iterdir()):
        log_dir = entry / "logs"
        try:
            if entry.is_dir() and log_dir.is_dir():
                result[entry.name] = log_dir
        except PermissionError as exc:
            logger.warning("Skipping %s: %s", entry, exc)
    return result


def _file_is_recent(path: Path, cutoff: datetime) -> bool:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return mtime >= cutoff
    except OSError:
        return False


def _scan_file(path: Path) -> list[str]:
    matches = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if any(pattern in line for pattern in EXCLUDE_PATTERNS):
                    continue
                if any(pattern in line for pattern in ERROR_PATTERNS):
                    matches.append(line.rstrip())
    except OSError as exc:
        logger.warning("Could not read log file %s: %s", path, exc)
    return matches


def scan_logs(lookback_hours: int = 24, app_data_root: Path | None = None) -> bool:
    """Scan every discovered app's log directory for errors in the last lookback_hours.

    Sends a shovel.bot alert per app that has errors. Returns True if any errors were found.
    """
    root = app_data_root or APP_DATA_ROOT
    cutoff = datetime.now() - timedelta(hours=lookback_hours)
    any_errors = False

    for app_name, log_dir in _discover_app_log_dirs(root).items():
        app_errors: dict[str, list[str]] = {}

        for log_file in sorted(log_dir.glob("*.log")):
            if not _file_is_recent(log_file, cutoff):
                continue
            lines = _scan_file(log_file)
            if lines:
                app_errors[log_file.name] = lines

        if not app_errors:
            logger.info("No errors found in %s logs", app_name)
            continue

        any_errors = True
        total = sum(len(v) for v in app_errors.values())
        logger.warning("Found %d error line(s) in %s logs", total, app_name)

        summary_lines = []
        for filename, lines in app_errors.items():
            summary_lines.append(f"[{filename}] ({len(lines)} error(s))")
            for line in lines[:3]:
                summary_lines.append(f"  {line[:200]}")
            if len(lines) > 3:
                summary_lines.append(f"  ... and {len(lines) - 3} more")

        message = "\n".join(summary_lines)

        send_alert(
            severity="error",
            title=f"Errors detected in {app_name} logs",
            message=message,
            details={"app": app_name, "error_count": total, "lookback_hours": lookback_hours},
        )

    return any_errors
