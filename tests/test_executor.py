import os
import time
from pathlib import Path

import pytest

from ops_agent.executor import run_all, run_target
from ops_agent.targets import Target


def _touch_with_mtime(path: Path, days_ago: int):
    path.write_text("x" * 100)
    mtime = time.time() - days_ago * 86400
    os.utime(path, (mtime, mtime))


class TestRunTargetPlainPath:
    def test_dry_run_never_deletes(self, tmp_path, monkeypatch):
        stale = tmp_path / "stale.txt"
        _touch_with_mtime(stale, days_ago=30)

        def boom(*a, **kw):
            raise AssertionError("dry run must never call a real delete")

        monkeypatch.setattr("shutil.rmtree", boom)
        monkeypatch.setattr("pathlib.Path.unlink", boom)

        target = Target(name="t", description="d", base_dir=str(tmp_path), mode="age", max_age_days=7)
        report = run_target(target, apply=False)

        assert report.status == "dry_run"
        assert report.candidates == 1
        assert stale.exists()

    def test_apply_deletes_real_stale_file(self, tmp_path):
        stale = tmp_path / "stale.txt"
        _touch_with_mtime(stale, days_ago=30)

        target = Target(name="t", description="d", base_dir=str(tmp_path), mode="age", max_age_days=7)
        report = run_target(target, apply=True)

        assert report.status == "applied"
        assert report.candidates == 1
        assert not stale.exists()

    def test_keep_newest_n_mode(self, tmp_path):
        for i in range(3):
            _touch_with_mtime(tmp_path / f"v{i}", days_ago=3 - i)

        target = Target(name="t", description="d", base_dir=str(tmp_path), mode="keep_newest_n", keep_newest_n=1)
        report = run_target(target, apply=True)

        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 1
        assert report.candidates == 2


class TestRunTargetPrivileged:
    def test_privileged_target_never_spawns_real_sudo(self, tmp_path):
        calls = []

        def fake_invoke_privileged(action, apply):
            calls.append((action, apply))
            return type("R", (), {"stdout": "ok"})()

        target = Target(
            name="root-pip-cache", description="d", base_dir="/home/runner/.cache/pip",
            mode="age", max_age_days=30, requires_sudo=True, privileged_action="root-pip-cache",
        )

        report = run_target(target, apply=True, invoke_privileged=fake_invoke_privileged)

        assert calls == [("root-pip-cache", True)]
        assert report.status == "applied"


class TestRunTargetRunnerIdleGate:
    def test_skips_when_runner_busy(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ops_agent.executor.runner_is_idle", lambda: False)

        target = Target(
            name="runner-work-cache", description="d", base_dir=str(tmp_path),
            mode="age", max_age_days=1, requires_runner_idle=True,
        )
        report = run_target(target, apply=True)

        assert report.status == "skipped_busy"

    def test_proceeds_when_runner_idle(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ops_agent.executor.runner_is_idle", lambda: True)
        _touch_with_mtime(tmp_path / "stale", days_ago=10)

        target = Target(
            name="runner-work-cache", description="d", base_dir=str(tmp_path),
            mode="age", max_age_days=1, requires_runner_idle=True,
        )
        report = run_target(target, apply=True)

        assert report.status == "applied"


class TestRunTargetReportOnly:
    def test_report_only_never_deletes_even_with_apply(self, tmp_path):
        _touch_with_mtime(tmp_path / "orphan-home", days_ago=100)

        target = Target(
            name="list-orphaned-homes", description="d", base_dir=str(tmp_path),
            mode="age", max_age_days=1, report_only=True,
        )
        report = run_target(target, apply=True)

        assert report.status == "dry_run"
        assert (tmp_path / "orphan-home").exists()


class TestRunAll:
    def test_produces_one_report_entry_per_target(self, tmp_path):
        targets = [
            Target(name="a", description="d", base_dir=str(tmp_path), mode="age", max_age_days=1),
            Target(name="b", description="d", base_dir=str(tmp_path), mode="age", max_age_days=1),
        ]
        run_report = run_all(targets, apply=False)

        assert [t.name for t in run_report.targets] == ["a", "b"]
        assert run_report.apply is False
