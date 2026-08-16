#!/usr/bin/env python3
"""Run the cheapest deterministic canonical-truth proof for each release domain.

The tests use API/domain actions plus canonical DB assertions and secondary
surface projections. They deliberately do not turn every control into a slow
browser test. A skipped DB proof is a failure in this staging-only matrix.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ORCH = REPO / "wathefni-orchestrator"
ORCH = Path(os.environ.get("WATHEFNI_ORCHESTRATOR_ROOT", DEFAULT_ORCH)).resolve()
TEST_ROOT = Path(os.environ.get("WATHEFNI_MATRIX_TEST_ROOT", ORCH)).resolve()

MATRIX = (
    ("Recruiting", "smoke-test-prehire-registry-parity.py"),
    ("Interviews", "smoke-test-interview-workflow-live.py"),
    ("Onboarding", "smoke-test-onboarding-dashboard.py"),
    ("Attendance", "smoke-test-attendance-truth-c1.py"),
    ("Shifts", "smoke-test-shift-management.py"),
    ("Payroll/Payslips", "smoke-test-payroll-payslip-wave3.py"),
    ("Documents", "smoke-test-document-hub.py"),
    ("Performance/OKRs", "smoke-test-r5b-performance-surface-db.py"),
    ("Talent", "smoke-test-r5c-talent-surface-db.py"),
    ("Learning", "smoke-test-r5e-learning-surface-db.py"),
    ("Benefits", "smoke-test-r5f-benefits-surface-db.py"),
    ("Employee Relations", "smoke-test-r5g-employee-relations-surface-db.py"),
    ("Engagement", "smoke-test-r5h-engagement-surface-db.py"),
    ("Compensation Planning", "smoke-test-r5i-compensation-planning-surface-db.py"),
    ("Workforce Planning", "smoke-test-r5j-workforce-planning-surface-db.py"),
    ("Setup/module composition", "smoke-test-r6-setup-self-service-db.py"),
)

DB_SKIP_MARKERS = (
    "SKIP: psycopg2",
    "SKIP DB:",
    "database unavailable",
    "DB tests skipped",
)


def main() -> int:
    env = os.environ.copy()
    env.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")
    env.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    env["PYTHONPATH"] = f"{ORCH}:{env.get('PYTHONPATH', '')}".rstrip(":")
    failures: list[str] = []
    print(f"    CROSS-SURFACE DOMAIN MATRIX  tests={len(MATRIX)}")
    for domain, filename in MATRIX:
        path = TEST_ROOT / filename
        if not path.is_file():
            print(f"      FAIL  {domain}: missing {path}")
            failures.append(domain)
            continue
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=ORCH,
            env=env,
            text=True,
            capture_output=True,
            timeout=300,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        skipped = next((marker for marker in DB_SKIP_MARKERS if marker.lower() in output.lower()), None)
        if proc.returncode == 0 and not skipped:
            print(f"      PASS  {domain}: {filename}")
        else:
            reason = f"exit={proc.returncode}" if not skipped else skipped
            print(f"      FAIL  {domain}: {filename} ({reason})")
            print(output[-4000:])
            failures.append(domain)
    print(f"\n    CROSS_SURFACE_DOMAIN_MATRIX_{'PASS' if not failures else 'FAIL'}  {len(MATRIX) - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
