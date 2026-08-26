import json

from ops_agent.cli import cleanup
from ops_agent.targets import Target


class TestCleanupCli:
    def test_dry_run_writes_report_and_does_not_delete(self, tmp_path, monkeypatch):
        stale_dir = tmp_path / "cache"
        stale_dir.mkdir()
        stale_file = stale_dir / "old.bin"
        stale_file.write_text("x")
        import os
        import time
        mtime = time.time() - 30 * 86400
        os.utime(stale_file, (mtime, mtime))

        log_dir = tmp_path / "logs"
        report_dir = tmp_path / "reports"

        fake_config = type(
            "Config",
            (),
            {
                "log_dir": str(log_dir),
                "report_dir": str(report_dir),
                "apply": False,
                "targets": [
                    Target(name="cache", description="d", base_dir=str(stale_dir), mode="age", max_age_days=7)
                ],
            },
        )()
        monkeypatch.setattr("ops_agent.cli.load_config", lambda: fake_config)

        exit_code = cleanup(argv=[])

        assert exit_code == 0
        assert stale_file.exists()  # dry-run: nothing deleted
        report_files = list(report_dir.glob("cleanup_report_*.json"))
        assert len(report_files) == 1
        data = json.loads(report_files[0].read_text())
        assert data["apply"] is False
        assert data["targets"][0]["candidates"] == 1

    def test_apply_flag_overrides_config_dry_run_default(self, tmp_path, monkeypatch):
        stale_dir = tmp_path / "cache"
        stale_dir.mkdir()
        stale_file = stale_dir / "old.bin"
        stale_file.write_text("x")
        import os
        import time
        mtime = time.time() - 30 * 86400
        os.utime(stale_file, (mtime, mtime))

        fake_config = type(
            "Config",
            (),
            {
                "log_dir": str(tmp_path / "logs"),
                "report_dir": str(tmp_path / "reports"),
                "apply": False,
                "targets": [
                    Target(name="cache", description="d", base_dir=str(stale_dir), mode="age", max_age_days=7)
                ],
            },
        )()
        monkeypatch.setattr("ops_agent.cli.load_config", lambda: fake_config)

        cleanup(argv=["--apply"])

        assert not stale_file.exists()
