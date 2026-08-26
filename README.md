# oshvl-ops-agent-shared

Compute-node housekeeping tool shared across the `orangeshovel`, `lonebirchlab`,
and `projectunmute` self-hosted compute nodes. Deployed by the shared
`oshvl.infra.deploy_ops_agent` Ansible playbook (in `oshvl-ansible-shared`),
not by a playbook in this repo — this repo has no self-hosted runner of its
own and no deploy workflow.

## What it does

Two independent jobs, one deployed app:

- **Daily** (`make run-daily`, `oshvl-ops-agent-daily.timer`, 05:05 local): database
  backup (PostgreSQL → gzip → S3), cross-app log-error scanning + alerting via
  shovel.bot, server metrics collection, per-app run-time tracking, and a
  nightly Slack digest. This is the generalized continuation of what used to
  be orangeshovel's `apps/shovel.watch/legacy/` + `shovel_watch.py` — moved
  here because it was already fully generic compute-node housekeeping, not
  shovel.watch product logic, and needed to run on every org's node, not just
  orangeshovel's.
- **Cleanup** (`make run-cleanup`, `oshvl-ops-agent-cleanup.timer`, weekly): prunes
  unbounded caches that fill the (typically small) root disk on a self-hosted
  runner box — bun/pip package caches, GitHub Actions runner tool cache,
  old Claude Code CLI version binaries, systemd journal — plus a read-only
  report of orphaned/dead runner home directories (never auto-deleted).
  Dry-run by default; a per-host `APPLY=true` in the deployed `.env` is
  required to actually delete anything.

## Why one repo, not one per org

Each org's compute node hits the identical disk-pressure problem
independently. Shipping this once here and deploying it via a single shared,
version-pinned Ansible playbook avoids the alternative — three
hand-maintained copies that drift, the same problem `setup_compute_master.yml`
already has across the three product repos for node bootstrap.

## Privilege model

Runs as its own unprivileged `ops-agent` service user (in `service-accounts`,
like every other app in this ecosystem). The cleanup job's few operations that
need root — touching another user's `/home/*`, `/var/log/journal`,
`/root/.cache` — go through a narrowly-scoped sudoers grant
(`oshvl.infra.ops_agent_sudo`): exactly one fixed, root-owned helper script,
not a blanket root service or a raw-verb sudoers whitelist. See that role's
README for the full rationale.

## Local development

```bash
cp .env.example .env    # fill in for local testing; never commit this file
make venv
make test
make lint
```

`make run-cleanup` reads `targets.yml` in the current directory (see
`targets.yml.example` for the schema) — in production this is deployed by
Ansible with real per-host paths.

## Repo layout

```
ops_agent/
├── cli.py, config.py              # cleanup job entrypoint + config loading
├── targets.py, fs.py, runner_state.py, privileged.py, executor.py, report.py
│                                   # cleanup job internals
├── backup.py, log_monitor.py, metrics.py, run_time_tracker.py, notify.py
│                                   # daily job internals (moved from shovel.watch/legacy/)
└── daily.py                        # daily job orchestrator
tests/                              # pytest, one file per module above
```
