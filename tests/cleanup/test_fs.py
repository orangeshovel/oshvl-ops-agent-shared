import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from ops_agent.cleanup.fs import (
    human_size,
    iter_paths_beyond_newest_n,
    iter_stale_paths,
    path_size_bytes,
)


def _touch_with_mtime(path: Path, days_ago: int):
    path.write_text("x" * 10)
    mtime = time.time() - days_ago * 86400
    os.utime(path, (mtime, mtime))


class TestIterStalePaths:
    def test_returns_only_paths_older_than_max_age(self, tmp_path):
        old_file = tmp_path / "old.txt"
        new_file = tmp_path / "new.txt"
        _touch_with_mtime(old_file, days_ago=10)
        _touch_with_mtime(new_file, days_ago=1)

        stale = list(iter_stale_paths(tmp_path, max_age_days=5))

        assert stale == [old_file]

    def test_missing_base_dir_yields_nothing(self, tmp_path):
        assert list(iter_stale_paths(tmp_path / "does-not-exist", max_age_days=1)) == []

    def test_boundary_exactly_at_cutoff_is_not_stale(self, tmp_path):
        f = tmp_path / "boundary.txt"
        now = datetime(2026, 1, 10)
        _touch_with_mtime(f, days_ago=0)
        os.utime(f, (now.timestamp() - 5 * 86400, now.timestamp() - 5 * 86400))

        stale = list(iter_stale_paths(tmp_path, max_age_days=5, now=now))

        assert stale == []


class TestIterPathsBeyondNewestN:
    def test_keeps_newest_n_and_yields_the_rest(self, tmp_path):
        paths = []
        for i in range(5):
            p = tmp_path / f"v{i}"
            _touch_with_mtime(p, days_ago=5 - i)  # v4 newest, v0 oldest
            paths.append(p)

        beyond = list(iter_paths_beyond_newest_n(tmp_path, keep_newest_n=2))

        assert set(beyond) == {paths[0], paths[1], paths[2]}

    def test_keep_more_than_exist_yields_nothing(self, tmp_path):
        _touch_with_mtime(tmp_path / "only.txt", days_ago=1)

        assert list(iter_paths_beyond_newest_n(tmp_path, keep_newest_n=10)) == []


class TestPathSizeBytes:
    def test_file_size(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("hello")
        assert path_size_bytes(f) == 5

    def test_directory_size_is_recursive_sum(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.txt").write_text("12345")
        (tmp_path / "sub" / "b.txt").write_text("1234567890")

        assert path_size_bytes(tmp_path) == 15


class TestHumanSize:
    def test_bytes(self):
        assert human_size(500) == "500.0B"

    def test_megabytes(self):
        assert human_size(5 * 1024 * 1024) == "5.0MB"
