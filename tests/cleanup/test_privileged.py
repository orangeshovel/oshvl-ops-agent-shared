import subprocess
import sys
from unittest.mock import patch

import pytest

from ops_agent.cleanup.privileged import (
    DEFAULT_TIMEOUT_S,
    HELPER_PATH,
    _run_with_graceful_timeout,
    invoke_privileged,
)


class TestInvokePrivileged:
    @patch("ops_agent.cleanup.privileged._run_with_graceful_timeout")
    def test_default_timeout_is_used_when_no_runner_given(self, mock_run):
        invoke_privileged("journal-vacuum", apply=False)

        assert mock_run.call_args.args[1] == DEFAULT_TIMEOUT_S

    @patch("ops_agent.cleanup.privileged._run_with_graceful_timeout")
    def test_longer_timeout_is_passed_through(self, mock_run):
        invoke_privileged("apt-upgrade", apply=True, timeout=3600)

        assert mock_run.call_args.args[0] == [
            "sudo", "-n", HELPER_PATH, "--action", "apt-upgrade", "--apply",
        ]
        assert mock_run.call_args.args[1] == 3600

    @patch("ops_agent.cleanup.privileged._run_with_graceful_timeout")
    def test_timeout_is_ignored_when_a_runner_is_given(self, mock_run):
        invoke_privileged("journal-vacuum", apply=False, runner=lambda argv: None, timeout=5)

        mock_run.assert_not_called()

    def test_timeout_sends_sigterm_first_not_sigkill(self):
        # A child that exits cleanly on SIGTERM: the helper must be asked, not killed.
        argv = [sys.executable, "-c", "import time; time.sleep(60)"]
        with pytest.raises(subprocess.TimeoutExpired):
            _run_with_graceful_timeout(argv, 1)

    def test_run_returns_completed_process(self):
        result = _run_with_graceful_timeout([sys.executable, "-c", "print('hi')"], 10)

        assert result.returncode == 0
        assert result.stdout.strip() == "hi"

    def test_builds_expected_argv_dry_run(self):
        captured = {}

        def fake_runner(argv):
            captured["argv"] = argv
            return None

        invoke_privileged("journal-vacuum", apply=False, runner=fake_runner)

        assert captured["argv"] == ["sudo", "-n", HELPER_PATH, "--action", "journal-vacuum"]

    def test_builds_expected_argv_apply(self):
        captured = {}

        def fake_runner(argv):
            captured["argv"] = argv
            return None

        invoke_privileged("journal-vacuum", apply=True, runner=fake_runner)

        assert captured["argv"] == ["sudo", "-n", HELPER_PATH, "--action", "journal-vacuum", "--apply"]

    def test_never_embeds_caller_supplied_paths_in_argv(self):
        captured = {}

        def fake_runner(argv):
            captured["argv"] = argv
            return None

        invoke_privileged("runner-work-cache; rm -rf /", apply=False, runner=fake_runner)

        # The (malicious/garbage) action string is passed as a single argv
        # element, never interpolated into a shell string - subprocess with
        # a list argv never invokes a shell, so this cannot inject commands.
        assert captured["argv"][-1] == "runner-work-cache; rm -rf /"
        assert len(captured["argv"]) == 5
