"""Detect whether the GitHub Actions runner on this host is mid-job.

Used to gate cleanup targets that touch the runner's `_work` tool cache —
clearing that mid-job would corrupt an in-flight workflow run.
"""

import subprocess
from typing import Callable

ProcessLister = Callable[[], list[str]]


def _default_ps_lister() -> list[str]:
    result = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True, timeout=10)
    return result.stdout.splitlines()


def runner_is_idle(process_lister: ProcessLister = _default_ps_lister) -> bool:
    """Return True if no GitHub Actions job worker process is currently running."""
    return not any("Runner.Worker" in line for line in process_lister())
