import json

from ops_agent.cleanup.report import RunReport, TargetReport


class TestRunReport:
    def test_to_json_round_trips(self):
        report = RunReport(apply=False)
        report.add(TargetReport(name="bun-cache", status="dry_run", candidates=3, bytes_reclaimed=1024))

        parsed = json.loads(report.to_json())

        assert parsed["apply"] is False
        assert parsed["targets"][0]["name"] == "bun-cache"
        assert parsed["targets"][0]["bytes_reclaimed"] == 1024

    def test_summary_lines_include_target_name_and_status(self):
        report = RunReport(apply=True)
        report.add(TargetReport(name="pip-cache", status="applied", candidates=2, bytes_reclaimed=2048))

        lines = report.summary_lines()

        assert any("pip-cache" in line and "applied" in line for line in lines)

    def test_summary_lines_include_detail_when_present(self):
        report = RunReport()
        report.add(TargetReport(name="x", status="skipped_busy", detail="runner has an in-flight job"))

        lines = report.summary_lines()

        assert any("runner has an in-flight job" in line for line in lines)
