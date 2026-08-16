#!/usr/bin/env bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-employee-payslips-pagination-20260809T011927Z
install -m 644 "$B/app.py" "$B/payroll_payslip_wave3.py" /opt/wathefni/orchestrator/
/opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py /opt/wathefni/orchestrator/payroll_payslip_wave3.py
systemctl restart wathefni-orchestrator.service
sleep 4
systemctl is-active wathefni-orchestrator.service
