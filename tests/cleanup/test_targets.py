import pytest

from ops_agent.cleanup.targets import Target, load_targets


class TestTarget:
    def test_valid_age_target(self):
        t = Target(name="a", description="d", base_dir="/tmp", mode="age", max_age_days=7)
        assert t.max_age_days == 7

    def test_valid_keep_newest_n_target(self):
        t = Target(name="a", description="d", base_dir="/tmp", mode="keep_newest_n", keep_newest_n=3)
        assert t.keep_newest_n == 3

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="invalid mode"):
            Target(name="a", description="d", base_dir="/tmp", mode="bogus")

    def test_age_mode_without_max_age_days_raises(self):
        with pytest.raises(ValueError, match="requires max_age_days"):
            Target(name="a", description="d", base_dir="/tmp", mode="age")

    def test_keep_newest_n_mode_without_keep_newest_n_raises(self):
        with pytest.raises(ValueError, match="requires keep_newest_n"):
            Target(name="a", description="d", base_dir="/tmp", mode="keep_newest_n")

    def test_requires_sudo_without_privileged_action_raises(self):
        with pytest.raises(ValueError, match="privileged_action"):
            Target(
                name="a", description="d", base_dir="/tmp", mode="age",
                max_age_days=1, requires_sudo=True,
            )

    def test_requires_sudo_with_privileged_action_is_valid(self):
        t = Target(
            name="a", description="d", base_dir="/tmp", mode="age",
            max_age_days=1, requires_sudo=True, privileged_action="root-pip-cache",
        )
        assert t.privileged_action == "root-pip-cache"


class TestLoadTargets:
    def test_loads_multiple_targets(self):
        raw = [
            {"name": "a", "description": "d", "base_dir": "/tmp/a", "mode": "age", "max_age_days": 30},
            {"name": "b", "description": "d", "base_dir": "/tmp/b", "mode": "keep_newest_n", "keep_newest_n": 3},
        ]
        targets = load_targets(raw)
        assert [t.name for t in targets] == ["a", "b"]

    def test_duplicate_name_raises(self):
        raw = [
            {"name": "a", "description": "d", "base_dir": "/tmp/a", "mode": "age", "max_age_days": 30},
            {"name": "a", "description": "d2", "base_dir": "/tmp/b", "mode": "age", "max_age_days": 1},
        ]
        with pytest.raises(ValueError, match="duplicate target name"):
            load_targets(raw)
