#!/usr/bin/env python3
"""
oshvl-ops-agent daily job — disk cleanup, database backup, log monitoring, and
server health digest.

Runs in sequence:
  1. Disk cleanup (prune unbounded caches; dry-run unless APPLY=true / --apply)
  2. Database backup (PostgreSQL → gzip → S3) — skipped silently, no alert, on
     any host with no PG_HOST configured (backup isn't set up everywhere this
     job runs)
  3. OS package upgrade (apt-get upgrade via the root helper) — only on hosts that set
     APT_UPGRADE=true; skipped everywhere else
  4. Log monitor (scan all app logs for errors, alert via shovel.bot)
  5. Metrics + run-time collection
  6. Nightly digest send

Cleanup runs first so disk pressure is relieved before the backup/export step
runs. It was originally its own weekly job (ops_agent/cli.py, driven by a
separate oshvl-ops-agent-cleanup.timer) — folded in here so there's a single
daily cadence instead of two independently-scheduled jobs.

Replaces orangeshovel's apps/shovel.watch/shovel_watch.py — endpoint checks
are dropped from this orchestration since they're genuine shovel.watch
product surface with their own independent 15-minute timer, not a
compute-node housekeeping concern.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from ops_agent.cleanup.config import load_config
from ops_agent.cleanup.executor import run_all
from ops_agent.cleanup.report import RunReport
from ops_agent.daily_ops.backup import run_backup, setup_logging
from ops_agent.daily_ops.log_monitor import scan_logs
from ops_agent.daily_ops.metrics import collect_metrics
from ops_agent.daily_ops.notify import send_alert, send_nightly_digest
from ops_agent.daily_ops.os_upgrade import run_os_upgrade
from ops_agent.daily_ops.run_time_tracker import get_run_times

logger = logging.getLogger(__name__)


def _run_cleanup(args: argparse.Namespace) -> RunReport:
    config = load_config()
    apply = args.apply or config.apply
    logger.info("Starting cleanup pass (apply=%s, %d targets)", apply, len(config.targets))

    report = run_all(config.targets, apply)

    Path(config.report_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = Path(config.report_dir) / f"cleanup_report_{timestamp}.json"
    report_file.write_text(report.to_json())

    for line in report.summary_lines():
        logger.info(line)

    return report


def _run_os_upgrade_step() -> bool:
    """Upgrade OS packages if this host opted in (APT_UPGRADE=true). Returns True on
    success or when skipped, False if the upgrade failed."""
    if os.getenv("APT_UPGRADE", "false").strip().lower() != "true":
        logger.info("APT_UPGRADE not enabled — skipping OS package upgrade")
        return True

    result = run_os_upgrade(apply=True)
    if not result.ok:
        logger.error("OS package upgrade failed: %s", result.detail)
        send_alert(
            severity="error",
            title="oshvl-ops-agent: OS package upgrade failed",
            message="The nightly apt upgrade did not complete successfully. Check logs.",
            details={"error": result.detail},
        )
        return False

    logger.info(
        "OS package upgrade complete: %d upgraded, %d kept back, reboot required: %s",
        result.upgraded,
        result.kept_back,
        result.reboot_required,
    )
    if result.reboot_required:
        send_alert(
            severity="warning",
            title="oshvl-ops-agent: reboot required",
            message=(
                "Package upgrades are installed but a reboot is needed to apply them "
                "(e.g. a new kernel). Reboot at a convenient time."
            ),
            details={"upgraded_tonight": result.upgraded},
        )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="oshvl-ops-agent: daily cleanup + backup + log monitoring + digest"
    )
    parser.add_argument("--log-dir", default=os.getenv("LOG_DIR", "./logs"))
    parser.add_argument("--export-dir", default=os.getenv("EXPORT_DIR", "./exports"))
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument(
        "--apply", action="store_true", help="Actually delete (in addition to APPLY=true in .env)"
    )
    args = parser.parse_args(argv)

    setup_logging(args.log_dir)
    logger.info("oshvl-ops-agent daily job starting")

    _run_cleanup(args)

    if os.getenv("PG_HOST"):
        backup_ok = run_backup(args.log_dir, args.export_dir, args.keep_days)
        if not backup_ok:
            send_alert(
                severity="error",
                title="oshvl-ops-agent: backup failed",
                message=(
                    "The nightly database backup did not complete successfully. "
                    "Check logs for details."
                ),
                details={"log_dir": args.log_dir},
            )
    else:
        logger.info("PG_HOST not set — skipping database backup (not configured for this host)")
        backup_ok = True

    upgrade_ok = _run_os_upgrade_step()

    logger.info("Scanning app logs for errors...")
    scan_logs(lookback_hours=args.lookback_hours)

    logger.info("Collecting server metrics...")
    metrics = collect_metrics()
    run_times = get_run_times()

    send_nightly_digest(metrics, run_times)

    logger.info("oshvl-ops-agent daily job completed")

    return 0 if backup_ok and upgrade_ok else 1


if __name__ == "__main__":
    sys.exit(main())
