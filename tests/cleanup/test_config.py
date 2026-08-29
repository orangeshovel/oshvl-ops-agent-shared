from ops_agent.cleanup.config import load_config


class TestLoadConfig:
    def test_apply_defaults_false_when_unset(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APPLY", raising=False)
        monkeypatch.chdir(tmp_path)

        config = load_config(targets_path=str(tmp_path / "missing-targets.yml"))

        assert config.apply is False
        assert config.targets == []

    def test_apply_true_parsed_case_insensitively(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPLY", "True")
        monkeypatch.chdir(tmp_path)

        config = load_config(targets_path=str(tmp_path / "missing-targets.yml"))

        assert config.apply is True

    def test_loads_targets_yaml(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APPLY", raising=False)
        targets_file = tmp_path / "targets.yml"
        targets_file.write_text(
            "- name: bun-cache\n"
            "  description: bun install cache\n"
            "  base_dir: /home/runner/.bun/install/cache\n"
            "  mode: age\n"
            "  max_age_days: 14\n"
        )

        config = load_config(targets_path=str(targets_file))

        assert len(config.targets) == 1
        assert config.targets[0].name == "bun-cache"
