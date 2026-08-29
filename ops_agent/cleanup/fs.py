"""Filesystem helpers for disk-cleanup candidate discovery.

Pure, Path-based, and take an injectable `now` so callers can test age-based
logic against real (tiny) temp files without mocking the filesystem itself.
"""

from datetime import datetime
from pathlib import Path
from typing import Iterator


def path_size_bytes(path: Path) -> int:
    """Return the total size of path — recursive if it's a directory."""
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.lstat().st_size
    return total


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def iter_stale_paths(base: Path, max_age_days: int, now: datetime | None = None) -> Iterator[Path]:
    """Yield direct children of base whose mtime is older than max_age_days."""
    if not base.exists():
        return
    now = now or datetime.now()
    cutoff = now.timestamp() - max_age_days * 86400
    for child in sorted(base.iterdir()):
        try:
            if child.lstat().st_mtime < cutoff:
                yield child
        except OSError:
            continue


def iter_paths_beyond_newest_n(base: Path, keep_newest_n: int) -> Iterator[Path]:
    """Yield direct children of base beyond the keep_newest_n most recently modified."""
    if not base.exists():
        return
    dated: list[tuple[float, Path]] = []
    for child in base.iterdir():
        try:
            dated.append((child.lstat().st_mtime, child))
        except OSError:
            continue
    dated.sort(key=lambda pair: pair[0], reverse=True)
    for _, child in dated[keep_newest_n:]:
        yield child
