#!/usr/bin/env python3
"""
oshvl-ops-agent daily job — database backup, log monitoring, and server health digest.

Runs in sequence:
  1. Database backup (PostgreSQL → gzip → S3)
  2. Log monitor (scan all app logs for errors, alert via shovel.bot)
  3. Metrics + run-time collection
  4. Nightly digest send

Replaces orangeshovel's apps/shovel.watch/shovel_watch.py — endpoint checks
are dropped from this orchestration since they're genuine shovel.watch
product surface with their own independent 15-minute timer, not a
compute-node housekeeping concern.
"""

import argparse
import logging
import os
import sys

from ops_agent.backup import run_backup, setup_logging
from ops_agent.log_monitor import scan_logs
from ops_agent.metrics import collect_metrics
from ops_agent.notify import send_alert, send_nightly_digest
from ops_agent.run_time_tracker import get_run_times

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="oshvl-ops-agent: daily backup + log monitoring + digest"
    )
    parser.add_argument("--log-dir", default=os.getenv("LOG_DIR", "./logs"))
    parser.add_argument("--export-dir", default=os.getenv("EXPORT_DIR", "./exports"))
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--lookback-hours", type=int, default=24)
    args = parser.parse_args(argv)

    setup_logging(args.log_dir)
    logger.info("oshvl-ops-agent daily job starting")

    backup_ok = run_backup(args.log_dir, args.export_dir, args.keep_days)
    if not backup_ok:
        send_alert(
            severity="error",
            title="oshvl-ops-agent: backup failed",
            message=(
                "The nightly database backup did not complete successfully. Check logs for details."
            ),
            details={"log_dir": args.log_dir},
        )

    logger.info("Scanning app logs for errors...")
    scan_logs(lookback_hours=args.lookback_hours)

    logger.info("Collecting server metrics...")
    metrics = collect_metrics()
    run_times = get_run_times()

    send_nightly_digest(metrics, run_times)

    logger.info("oshvl-ops-agent daily job completed")

    return 0 if backup_ok else 1


if __name__ == "__main__":
    sys.exit(main())
