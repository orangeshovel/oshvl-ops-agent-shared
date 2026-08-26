VENV = venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip

.PHONY: all venv test lint format run-daily run-cleanup run-cleanup-apply run-production clean help

all: test

venv: $(VENV)/bin/activate

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test: $(VENV)/bin/activate
	$(PYTHON) -m pytest tests/ -v

lint: $(VENV)/bin/activate
	$(PIP) install ruff==0.16.2
	$(VENV)/bin/ruff check ops_agent/
	$(VENV)/bin/ruff format --check ops_agent/

format: $(VENV)/bin/activate
	$(PIP) install ruff==0.16.2
	$(VENV)/bin/ruff check --fix ops_agent/
	$(VENV)/bin/ruff format ops_agent/

# Invoked by oshvl-ops-agent-daily.service (05:05 daily). Dry-run vs apply is
# not gated here — backup/log-monitor/metrics/run-time-tracker have no
# destructive filesystem side effects beyond what they already write to
# their own export dir + S3.
run-daily: $(VENV)/bin/activate
	$(PYTHON) -m ops_agent.daily

# Invoked by oshvl-ops-agent-cleanup.service (weekly). Dry-run by default;
# respects APPLY=true in the deployed .env.
run-cleanup: $(VENV)/bin/activate
	$(PYTHON) -m ops_agent.cli

# Manual operator convenience only — never wired to the timer.
run-cleanup-apply: $(VENV)/bin/activate
	$(PYTHON) -m ops_agent.cli --apply

run-production: run-daily

clean:
	rm -rf $(VENV)
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type d -name '.pytest_cache' -exec rm -rf {} +
	find . -type d -name '.ruff_cache' -exec rm -rf {} +

help:
	@echo "oshvl-ops-agent-shared Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make venv               - Create Python virtual environment"
	@echo "  make test               - Run tests"
	@echo "  make lint                - Run ruff check + format --check"
	@echo "  make format              - Auto-fix lint issues and format code with ruff"
	@echo "  make run-daily           - Run the daily backup/log-monitor/digest job"
	@echo "  make run-cleanup         - Run the weekly disk-cleanup job (dry-run unless APPLY=true)"
	@echo "  make run-cleanup-apply   - Force a real (non-dry-run) cleanup pass, manual use only"
	@echo "  make clean               - Remove Python artifacts"
	@echo ""
	@echo "Environment Variables (see .env.example):"
	@echo "  APPLY, LOG_DIR, REPORT_DIR, RUNNER_USER, RUNNER_HOME"
	@echo "  PG_*, S3_*, SHOVEL_BOT_*"
