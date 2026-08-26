"""Declarative disk-cleanup target definitions, loaded from a per-host targets.yml."""

from dataclasses import dataclass

VALID_MODES = ("age", "keep_newest_n")


@dataclass(frozen=True)
class Target:
    name: str
    description: str
    base_dir: str
    mode: str
    max_age_days: int | None = None
    keep_newest_n: int | None = None
    requires_sudo: bool = False
    privileged_action: str | None = None
    requires_runner_idle: bool = False
    report_only: bool = False

    def __post_init__(self):
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"target {self.name!r}: invalid mode {self.mode!r}, must be one of {VALID_MODES}"
            )
        if self.mode == "age" and self.max_age_days is None:
            raise ValueError(f"target {self.name!r}: mode 'age' requires max_age_days")
        if self.mode == "keep_newest_n" and self.keep_newest_n is None:
            raise ValueError(f"target {self.name!r}: mode 'keep_newest_n' requires keep_newest_n")
        if self.requires_sudo and not self.privileged_action:
            raise ValueError(
                f"target {self.name!r}: requires_sudo=True but no privileged_action set"
            )


def load_targets(raw: list[dict]) -> list[Target]:
    """Build and validate Target objects from parsed targets.yml content."""
    targets = []
    seen: set[str] = set()
    for entry in raw:
        target = Target(**entry)
        if target.name in seen:
            raise ValueError(f"duplicate target name: {target.name!r}")
        seen.add(target.name)
        targets.append(target)
    return targets
