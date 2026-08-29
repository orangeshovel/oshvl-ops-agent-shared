"""Configuration loading: .env scalars via os.getenv(), plus a structured targets.yml.

targets.yml is the one deliberate exception to this codebase's .env-only config
convention — the cleanup target list is inherently structured data (a list of
records), not a flat scalar, so it's deployed separately by Ansible as plain YAML.
"""

import os
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv

from ops_agent.cleanup.targets import Target, load_targets

load_dotenv(".env")


@dataclass
class Config:
    # cleanup job
    apply: bool = False
    log_dir: str = "./logs"
    report_dir: str = "./reports"
    runner_user: str = ""
    runner_home: str = ""
    targets: list[Target] = field(default_factory=list)

    # daily job
    pg_host: str = ""
    pg_port: str = "5432"
    pg_database: str = ""
    pg_user: str = ""
    pg_password: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    shovel_bot_url: str = ""
    shovel_bot_api_key: str = ""
    shovel_bot_channel: str = "#notifications"


def _load_targets_yaml(path: str) -> list[Target]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        raw = yaml.safe_load(f) or []
    return load_targets(raw)


def load_config(targets_path: str = "targets.yml") -> Config:
    return Config(
        apply=os.getenv("APPLY", "false").strip().lower() == "true",
        log_dir=os.getenv("LOG_DIR", "./logs"),
        report_dir=os.getenv("REPORT_DIR", "./reports"),
        runner_user=os.getenv("RUNNER_USER", ""),
        runner_home=os.getenv("RUNNER_HOME", ""),
        targets=_load_targets_yaml(targets_path),
        pg_host=os.getenv("PG_HOST", ""),
        pg_port=os.getenv("PG_PORT", "5432"),
        pg_database=os.getenv("PG_DATABASE", ""),
        pg_user=os.getenv("PG_USER", ""),
        pg_password=os.getenv("PG_PASSWORD", ""),
        s3_bucket=os.getenv("S3_BUCKET", ""),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        shovel_bot_url=os.getenv("SHOVEL_BOT_URL", ""),
        shovel_bot_api_key=os.getenv("SHOVEL_BOT_API_KEY", ""),
        shovel_bot_channel=os.getenv("SHOVEL_BOT_CHANNEL", "#notifications"),
    )
