"""Structured reporting for a cleanup run — JSON for the report file, human lines for logs."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from ops_agent.fs import human_size


@dataclass
class TargetReport:
    name: str
    status: str  # "dry_run", "applied", "skipped_busy"
    candidates: int = 0
    bytes_reclaimed: int = 0
    detail: str = ""


@dataclass
class RunReport:
    apply: bool = False
    started_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    targets: list[TargetReport] = field(default_factory=list)

    def add(self, target_report: TargetReport) -> None:
        self.targets.append(target_report)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def summary_lines(self) -> list[str]:
        mode = "apply" if self.apply else "dry-run"
        lines = [f"ops-agent cleanup report ({mode}) — {self.started_at}"]
        for t in self.targets:
            lines.append(
                f"  {t.name:<24} {t.status:<12} candidates={t.candidates:<4} "
                f"reclaimed={human_size(t.bytes_reclaimed)}"
            )
            if t.detail:
                lines.append(f"    {t.detail}")
        return lines
