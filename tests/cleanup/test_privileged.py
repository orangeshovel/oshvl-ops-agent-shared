from unittest.mock import patch

from ops_agent.cleanup.privileged import DEFAULT_TIMEOUT_S, HELPER_PATH, invoke_privileged


class TestInvokePrivileged:
    @patch("subprocess.run")
    def test_default_timeout_is_used_when_no_runner_given(self, mock_run):
        invoke_privileged("journal-vacuum", apply=False)

        assert mock_run.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT_S

    @patch("subprocess.run")
    def test_longer_timeout_is_passed_through(self, mock_run):
        invoke_privileged("apt-upgrade", apply=True, timeout=3600)

        assert mock_run.call_args.args[0] == [
            "sudo", "-n", HELPER_PATH, "--action", "apt-upgrade", "--apply",
        ]
        assert mock_run.call_args.kwargs["timeout"] == 3600

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
