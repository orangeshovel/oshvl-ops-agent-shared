from ops_agent.runner_state import runner_is_idle


class TestRunnerIsIdle:
    def test_idle_when_no_worker_process(self):
        assert runner_is_idle(process_lister=lambda: ["/bin/bash run.sh", "sshd"]) is True

    def test_busy_when_worker_process_present(self):
        assert runner_is_idle(process_lister=lambda: ["/opt/actions-runner/bin/Runner.Worker"]) is False

    def test_idle_on_empty_process_list(self):
        assert runner_is_idle(process_lister=lambda: []) is True
