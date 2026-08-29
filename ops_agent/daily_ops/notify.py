"""
shovel.bot notification helper for oshvl-ops-agent.

Reads connection settings from environment variables:
  SHOVEL_BOT_URL      - Base URL of shovel.bot API (e.g. https://api.shovel.bot)
  SHOVEL_BOT_API_KEY  - API key generated via /shovel apikey generate
  SHOVEL_BOT_CHANNEL  - Default Slack channel (e.g. #notifications)

This is a deliberate duplicate of shovel.watch's own notify.py, not a shared
library dependency — consistent with this ecosystem's existing convention of
duplicating small per-repo glue (e.g. ci_notify.sh, each app's pyproject.toml
ruff config) rather than introducing cross-repo coupling for ~100 lines of code.
send_nightly_digest drops the endpoint_results parameter the original had —
endpoint health is shovel.watch product surface with its own independent
15-minute alerting, not this tool's concern.
"""

import logging
import os
import socket
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv(".env")

_SHOVEL_BOT_URL = os.getenv("SHOVEL_BOT_URL", "").rstrip("/")
_SHOVEL_BOT_API_KEY = os.getenv("SHOVEL_BOT_API_KEY", "")
_SHOVEL_BOT_CHANNEL = os.getenv("SHOVEL_BOT_CHANNEL", "#notifications")

logger = logging.getLogger(__name__)


def send_alert(severity: str, title: str, message: str, details: dict | None = None) -> bool:
    """Post a notification to Slack via shovel.bot.

    Returns True on success, False on failure (logs the error but does not raise).
    """
    if not _SHOVEL_BOT_URL or not _SHOVEL_BOT_API_KEY:
        logger.warning("SHOVEL_BOT_URL or SHOVEL_BOT_API_KEY not set — skipping notification")
        return False

    payload = {
        "channel": _SHOVEL_BOT_CHANNEL,
        "app": "oshvl-ops-agent",
        "severity": severity,
        "title": title,
        "message": message,
    }
    if details:
        payload["details"] = details

    try:
        response = requests.post(
            f"{_SHOVEL_BOT_URL}/notifications",
            json=payload,
            headers={"Authorization": f"Bearer {_SHOVEL_BOT_API_KEY}"},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send shovel.bot notification: %s", exc)
        return False


def _health_emoji(pct: float | None, warn: int = 80, critical: int = 90) -> str:
    if pct is None:
        return ""
    if pct >= critical:
        return "🚨"
    if pct >= warn:
        return "⚠️"
    return "✅"


def _delta_str(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "—"
    sign = "+" if delta_pct > 0 else ""
    suffix = " 🚀" if delta_pct <= -10 else ""
    return f"{sign}{delta_pct}%{suffix}"


def send_nightly_digest(metrics: dict, run_times: dict) -> bool:
    """Post a nightly server health digest to Slack via shovel.bot.

    Returns True on success, False on failure (logs the error but does not raise).
    """
    if not _SHOVEL_BOT_URL or not _SHOVEL_BOT_API_KEY:
        logger.warning("SHOVEL_BOT_URL or SHOVEL_BOT_API_KEY not set — skipping digest")
        return False

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    hostname = os.getenv("HOSTNAME") or socket.gethostname()

    failed = metrics.get("failed_services", [])
    failed_str = ", ".join(failed) + " 🚨" if failed else "None ✅"

    mem_pct = metrics.get("mem_pct")
    disk_root_pct = metrics.get("disk_root_pct")
    disk_appdata_pct = metrics.get("disk_appdata_pct")

    lines = [
        f"🖥️ *Server Health — {hostname}* | {date_str}",
        "",
        "*System*",
        f"• CPU load (1/5/15m): {metrics.get('load_1')} / {metrics.get('load_5')} / "
        f"{metrics.get('load_15')}",
        f"• Memory: {metrics.get('mem_used_gb')} GB / {metrics.get('mem_total_gb')} GB "
        f"({mem_pct}%) {_health_emoji(mem_pct)}",
        f"• Disk (/): {metrics.get('disk_root_used_gb')} GB / "
        f"{metrics.get('disk_root_total_gb')} GB ({disk_root_pct}%) {_health_emoji(disk_root_pct)}",
        f"• Disk (/app-data): {metrics.get('disk_appdata_used_gb')} GB / "
        f"{metrics.get('disk_appdata_total_gb')} GB ({disk_appdata_pct}%) "
        f"{_health_emoji(disk_appdata_pct)}",
        f"• Uptime: {metrics.get('uptime_str', 'n/a')}",
        f"• Failed services: {failed_str}",
        "",
        "*App Run Times — last night vs 30-day avg*",
    ]

    for app_name, stats in run_times.items():
        last = stats.get("last_night_str", "n/a")
        avg = stats.get("avg_str", "n/a")
        delta = _delta_str(stats.get("delta_pct"))
        avg_part = f"avg: {avg}, {delta}" if avg != "n/a" else "no avg yet"
        lines.append(f"• {app_name:<18} {last:<10} ({avg_part})")

    message = "\n".join(lines)

    payload = {
        "channel": _SHOVEL_BOT_CHANNEL,
        "app": "oshvl-ops-agent",
        "severity": "info",
        "title": f"Server Health — {hostname} | {date_str}",
        "message": message,
        # Custom blocks, skipping shovel.bot's default header block (which
        # would otherwise render `title` as its own bold line above this
        # message — redundant with the "Server Health — {hostname}" line
        # `message` already opens with).
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "*oshvl-ops-agent* | INFO"}],
            },
        ],
    }

    try:
        response = requests.post(
            f"{_SHOVEL_BOT_URL}/notifications",
            json=payload,
            headers={"Authorization": f"Bearer {_SHOVEL_BOT_API_KEY}"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Nightly digest sent to shovel.bot")
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send nightly digest: %s", exc)
        return False
