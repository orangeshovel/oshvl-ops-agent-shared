"""
Server metrics collector for oshvl-ops-agent's daily digest.

Reads system metrics directly from /proc and systemctl — no extra packages
required. Moved from orangeshovel's apps/shovel.watch/legacy/metrics_collector.py,
unchanged — this was already fully host-generic.
"""

import shutil
import subprocess
from pathlib import Path


def _read_proc(path: str) -> str:
    return Path(path).read_text()


def collect_metrics() -> dict:
    """Collect current server health metrics.

    Returns a dict with keys:
        load_1, load_5, load_15   — CPU load averages
        mem_used_gb, mem_total_gb, mem_pct
        swap_used_gb, swap_total_gb
        disk_root_used_gb, disk_root_total_gb, disk_root_pct
        disk_appdata_used_gb, disk_appdata_total_gb, disk_appdata_pct
        uptime_str                — human-readable uptime
        failed_services           — list of failed systemd service names
    """
    metrics = {}
    metrics.update(_cpu_load())
    metrics.update(_memory())
    metrics.update(_disk("/", "root"))
    metrics.update(_disk("/app-data", "appdata"))
    metrics["uptime_str"] = _uptime()
    metrics["failed_services"] = _failed_services()
    return metrics


def _cpu_load() -> dict:
    parts = _read_proc("/proc/loadavg").split()
    return {
        "load_1": float(parts[0]),
        "load_5": float(parts[1]),
        "load_15": float(parts[2]),
    }


def _memory() -> dict:
    info = {}
    for line in _read_proc("/proc/meminfo").splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:")):
            key, val = line.split(":", 1)
            info[key.strip()] = int(val.strip().split()[0])  # kB

    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    used = total - available
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    swap_used = swap_total - swap_free

    mem_pct = round(used / total * 100, 1) if total else 0
    return {
        "mem_used_gb": round(used / 1024 / 1024, 2),
        "mem_total_gb": round(total / 1024 / 1024, 2),
        "mem_pct": mem_pct,
        "swap_used_gb": round(swap_used / 1024 / 1024, 2),
        "swap_total_gb": round(swap_total / 1024 / 1024, 2),
    }


def _disk(mount: str, key_prefix: str) -> dict:
    try:
        usage = shutil.disk_usage(mount)
    except FileNotFoundError:
        return {
            f"disk_{key_prefix}_used_gb": None,
            f"disk_{key_prefix}_total_gb": None,
            f"disk_{key_prefix}_pct": None,
        }
    used_gb = round(usage.used / 1024**3, 1)
    total_gb = round(usage.total / 1024**3, 1)
    pct = round(usage.used / usage.total * 100, 1) if usage.total else 0
    return {
        f"disk_{key_prefix}_used_gb": used_gb,
        f"disk_{key_prefix}_total_gb": total_gb,
        f"disk_{key_prefix}_pct": pct,
    }


def _uptime() -> str:
    seconds = float(_read_proc("/proc/uptime").split()[0])
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _failed_services() -> list[str]:
    try:
        result = subprocess.run(
            ["systemctl", "--failed", "--no-legend", "--plain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        services = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                services.append(parts[0])
        return services
    except (subprocess.SubprocessError, FileNotFoundError):
        return []
