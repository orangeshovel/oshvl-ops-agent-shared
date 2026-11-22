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


DEFAULT_TIMEOUT_S = 120
TERM_GRACE_S = 60


def invoke_privileged(
    action: str,
    apply: bool,
    runner: Runner | None = None,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """`timeout` (seconds) applies to the real subprocess call; long actions such as
    apt-upgrade pass a larger one. An explicit `runner` (tests) is used as-is."""
    argv = ["sudo", "-n", HELPER_PATH, "--action", action]
    if apply:
        argv.append("--apply")
    if runner is not None:
        return runner(argv)
    return _run_with_graceful_timeout(argv, timeout)


def _run_with_graceful_timeout(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Like subprocess.run(timeout=...), but SIGTERM first instead of SIGKILL.

    The direct child is sudo, which cannot forward SIGKILL: killing it would orphan the
    root helper (and any apt-get under it) mid-transaction. sudo does relay SIGTERM to its
    command, so ask politely, wait a grace period, and only then SIGKILL. (We cannot signal
    the root process group ourselves; the helper enforces its own shorter timeout as well.)
    """
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=TERM_GRACE_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
