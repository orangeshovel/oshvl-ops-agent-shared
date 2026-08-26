"""Disk-cleanup orchestration: turns Target definitions into a dry-run or real cleanup pass."""

import logging
import shutil
from pathlib import Path
from typing import Callable

from ops_agent import fs
from ops_agent.privileged import invoke_privileged as _default_invoke_privileged
from ops_agent.report import RunReport, TargetReport
from ops_agent.runner_state import runner_is_idle
from ops_agent.targets import Target

logger = logging.getLogger(__name__)

InvokePrivileged = Callable[..., object]

# Lines the root helper prints for each path it did or would touch. Used to
# recover a candidate count from its stdout, since the privileged path has no
# other way to report structured counts back to this process. bytes_reclaimed
# stays 0 for privileged targets -- the helper doesn't report sizes.
_CANDIDATE_LINE_MARKERS = ("would delete ", "deleting ", "candidate orphaned home")


def _count_privileged_candidates(stdout: str) -> int:
    return sum(
        1
        for line in stdout.splitlines()
        if any(marker in line for marker in _CANDIDATE_LINE_MARKERS)
    )


def _candidates(target: Target) -> list[Path]:
    base = Path(target.base_dir)
    if target.mode == "age":
        return list(fs.iter_stale_paths(base, target.max_age_days))
    return list(fs.iter_paths_beyond_newest_n(base, target.keep_newest_n))


def _delete(path: Path) -> int:
    size = fs.path_size_bytes(path)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    return size


def run_target(
    target: Target,
    apply: bool,
    invoke_privileged: InvokePrivileged = _default_invoke_privileged,
) -> TargetReport:
    if target.requires_runner_idle and not runner_is_idle():
        return TargetReport(
            name=target.name, status="skipped_busy", detail="runner has an in-flight job"
        )

    if target.requires_sudo:
        result = invoke_privileged(target.privileged_action, apply)
        stdout = getattr(result, "stdout", "") or ""
        status = "applied" if apply else "dry_run"
        return TargetReport(
            name=target.name,
            status=status,
            candidates=_count_privileged_candidates(stdout),
            detail=stdout.strip()[:500],
        )

    candidates = _candidates(target)

    if target.report_only:
        return TargetReport(
            name=target.name,
            status="dry_run",
            candidates=len(candidates),
            detail="; ".join(str(p) for p in candidates)[:500],
        )

    if apply:
        reclaimed = 0
        for path in candidates:
            try:
                reclaimed += _delete(path)
            except OSError as exc:
                logger.warning("failed to delete %s: %s", path, exc)
        status = "applied"
    else:
        reclaimed = sum(fs.path_size_bytes(p) for p in candidates)
        status = "dry_run"

    return TargetReport(
        name=target.name, status=status, candidates=len(candidates), bytes_reclaimed=reclaimed
    )


def run_all(targets: list[Target], apply: bool) -> RunReport:
    report = RunReport(apply=apply)
    for target in targets:
        report.add(run_target(target, apply))
    return report
