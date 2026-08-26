"""CLI entrypoint for the weekly disk-cleanup job (`make run-cleanup`)."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from ops_agent.config import load_config
from ops_agent.executor import run_all

logger = logging.getLogger(__name__)


def _setup_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"cleanup_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
    )


def cleanup(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="oshvl-ops-agent: weekly compute-node disk cleanup"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually delete (in addition to APPLY=true in .env)"
    )
    args = parser.parse_args(argv)

    config = load_config()
    _setup_logging(config.log_dir)

    apply = args.apply or config.apply
    logger.info("Starting cleanup run (apply=%s, %d targets)", apply, len(config.targets))

    report = run_all(config.targets, apply)

    Path(config.report_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = Path(config.report_dir) / f"cleanup_report_{timestamp}.json"
    report_file.write_text(report.to_json())

    for line in report.summary_lines():
        logger.info(line)

    return 0


if __name__ == "__main__":
    sys.exit(cleanup())
