"""Tests for os_upgrade.py — the caller side of the root helper's apt-upgrade action."""

import subprocess
from unittest.mock import MagicMock

from ops_agent.daily_ops.os_upgrade import ACTION, TIMEOUT_S, run_os_upgrade


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


GOOD_OUTPUT = (
    "12 upgraded, 0 newly installed, 0 to remove and 2 not upgraded.\n"
    "[apt] upgraded=12 kept_back=2\n"
    "[apt] reboot-required=true\n"
)


class TestRunOsUpgrade:
    def test_parses_counts_and_reboot_flag(self):
        invoke = MagicMock(return_value=_completed(GOOD_OUTPUT))

        result = run_os_upgrade(apply=True, invoke=invoke)

        assert result.ok is True
        assert result.upgraded == 12
        assert result.kept_back == 2
        assert result.reboot_required is True

    def test_reboot_not_required(self):
        out = "[apt] upgraded=0 kept_back=0\n[apt] reboot-required=false\n"
        result = run_os_upgrade(invoke=MagicMock(return_value=_completed(out)))

        assert result.ok is True
        assert result.upgraded == 0
        assert result.reboot_required is False

    def test_invokes_the_fixed_action_with_apply_and_long_timeout(self):
        invoke = MagicMock(return_value=_completed(GOOD_OUTPUT))

        run_os_upgrade(apply=True, invoke=invoke)

        invoke.assert_called_once_with(ACTION, True, timeout=TIMEOUT_S)
        assert ACTION == "apt-upgrade"
        assert TIMEOUT_S > 120  # must outlast the privileged-call default

    def test_nonzero_exit_is_a_failure_with_stderr_detail(self):
        invoke = MagicMock(return_value=_completed("", "E: Unable to lock", returncode=1))

        result = run_os_upgrade(invoke=invoke)

        assert result.ok is False
        assert "Unable to lock" in result.detail

    def test_old_helper_without_the_action_is_a_failure(self):
        stderr = "error: argument --action: invalid choice: 'apt-upgrade'"
        result = run_os_upgrade(invoke=MagicMock(return_value=_completed("", stderr, 2)))

        assert result.ok is False
        assert "invalid choice" in result.detail

    def test_exit_zero_without_summary_lines_is_not_trusted(self):
        result = run_os_upgrade(invoke=MagicMock(return_value=_completed("all good\n")))

        assert result.ok is False
        assert "summary" in result.detail

    def test_timeout_is_reported_not_raised(self):
        invoke = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="sudo", timeout=TIMEOUT_S))

        result = run_os_upgrade(invoke=invoke)

        assert result.ok is False
        assert "timed out" in result.detail

    def test_unexpected_error_is_reported_not_raised(self):
        result = run_os_upgrade(invoke=MagicMock(side_effect=FileNotFoundError("sudo")))

        assert result.ok is False
        assert "could not run" in result.detail
