#!/usr/bin/env bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-employee-schedule-history-20260809T012444Z
install -m 644 "$B/app.py" /opt/wathefni/orchestrator/app.py
# remove new smoke if rolling back fully (optional; harmless to leave)
/opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py
systemctl restart wathefni-orchestrator.service
sleep 4
systemctl is-active wathefni-orchestrator.service
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health
