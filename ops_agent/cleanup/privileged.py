"""Invoke the root-owned cleanup helper via a fixed, narrowly-scoped sudo call.

No caller-supplied path or shell string ever reaches the command line — the
helper script (deployed by the `oshvl.infra.ops_agent_sudo` role) owns all
real paths, templated in at deploy time, and accepts only a closed --action
enum plus --apply. This module only ever builds that one fixed argv shape.
"""

import subprocess
from typing import Callable

HELPER_PATH = "/opt/oshvl-ops-agent/root-helper/root_cleanup_helper.py"

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


def invoke_privileged(
    action: str, apply: bool, runner: Runner = _default_runner
) -> subprocess.CompletedProcess:
    argv = ["sudo", "-n", HELPER_PATH, "--action", action]
    if apply:
        argv.append("--apply")
    return runner(argv)
