"""Nightly OS package upgrade, run as root through the fixed sudo helper.

The helper (`apt-upgrade` action, deployed by the `oshvl.infra.ops_agent_sudo` role in
oshvl-ansible-shared) does `apt-get update` + `apt-get upgrade`; this module only invokes it
and parses the two marker lines it prints:

    [apt] upgraded=N kept_back=M
    [apt] reboot-required=true|false

Keep those formats in sync with the helper template.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

from ops_agent.cleanup.privileged import invoke_privileged

logger = logging.getLogger(__name__)

ACTION = "apt-upgrade"
# apt-get can wait up to 5 min for the dpkg lock, then download and install.
TIMEOUT_S = 3600

_UPGRADED_RE = re.compile(r"^\[apt\] upgraded=(\d+) kept_back=(\d+)\s*$", re.MULTILINE)
_REBOOT_RE = re.compile(r"^\[apt\] reboot-required=(true|false)\s*$", re.MULTILINE)

InvokePrivileged = Callable[..., subprocess.CompletedProcess]


@dataclass
class UpgradeResult:
    ok: bool
    upgraded: int = 0
    kept_back: int = 0
    reboot_required: bool = False
    detail: str = ""


def run_os_upgrade(
    apply: bool = True, invoke: InvokePrivileged = invoke_privileged
) -> UpgradeResult:
    """Run the privileged upgrade. Never raises: failures come back as ok=False."""
    logger.info("Running OS package upgrade (apply=%s)", apply)
    try:
        result = invoke(ACTION, apply, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return UpgradeResult(ok=False, detail=f"timed out after {TIMEOUT_S}s")
    except Exception as e:  # deliberate: the digest steps after this must still run
        logger.exception("OS package upgrade helper call raised")
        return UpgradeResult(ok=False, detail=f"could not run the helper: {e}")

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        detail = (stderr.strip() or stdout.strip())[-500:] or f"exit {result.returncode}"
        return UpgradeResult(ok=False, detail=detail)

    counts = _UPGRADED_RE.search(stdout)
    reboot = _REBOOT_RE.search(stdout)
    if counts is None or reboot is None:
        # Helper exited 0 but did not report: an old helper, or output we can't trust.
        return UpgradeResult(ok=False, detail="helper output missing [apt] summary lines")

    return UpgradeResult(
        ok=True,
        upgraded=int(counts.group(1)),
        kept_back=int(counts.group(2)),
        reboot_required=reboot.group(1) == "true",
    )
