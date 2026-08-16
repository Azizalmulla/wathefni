#!/usr/bin/env python3
"""Final frozen sweep for restored-baseline requalification."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ORCH = Path("/opt/wathefni/staging/orchestrator")
EVIDENCE = Path(os.environ["REQUAL_EVIDENCE"])
ENV = {
    **os.environ,
    "WATHEFNI_ENV": "staging",
    "WATHEFNI_ENVIRONMENT": "staging",
    "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.staging.env",
    "WATHEFNI_WORKSPACE": "/opt/wathefni/staging/workspace",
    "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
    "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
    "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni_staging",
    "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-staging-hr2-isolation-v1",
    "WATHEFNI_DASHBOARD_DIST": "/opt/wathefni/staging/dashboard-dist",
    "WATHEFNI_DELIVERY_MODE": "dry_run",
    "WATHEFNI_CANONICAL_LIFECYCLE": "true",
    "PYTHONPATH": str(ORCH),
}

PACKS = [
    "smoke-test-canonical-recruiting-lifecycle.py",
    "smoke-test-jobs-phase2-stage-a-unit.py",
    "smoke-test-jobs-phase1.py",
    "smoke-test-offer-lifecycle.py",
    "smoke-test-assessments.py",
    "smoke-test-prehire-assistant-parity.py",
    "smoke-test-inbound-email.py",
    "smoke-test-bulk-cv-import.py",
    "smoke-test-tiered-intake.py",
    "smoke-test-tenant-isolation-harness.py",
    "smoke-test-hr2a-mobile-data.py",
    "test_unified_candidates.py",
]


def main() -> int:
    results = []
    for name in PACKS:
        path = ORCH / name
        log = EVIDENCE / f"sweep-{name}.log"
        row = {"pack": name, "exists": path.exists()}
        if not path.exists():
            row["status"] = "missing"
            print("MISSING", name)
            results.append(row)
            continue
        t0 = time.time()
        with log.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(
                ["/opt/wathefni/orchestrator/.venv/bin/python", str(path)],
                cwd=str(ORCH),
                env=ENV,
                stdout=fh,
                stderr=subprocess.STDOUT,
                text=True,
            )
        row.update({"status": "pass" if proc.returncode == 0 else "fail", "rc": proc.returncode, "elapsed_s": round(time.time() - t0, 2), "log": str(log)})
        print(row["status"].upper(), name, f"rc={proc.returncode}")
        results.append(row)
    out = {
        "pass": sum(1 for r in results if r.get("status") == "pass"),
        "fail": sum(1 for r in results if r.get("status") == "fail"),
        "missing": sum(1 for r in results if r.get("status") == "missing"),
        "results": results,
    }
    (EVIDENCE / "final-sweep.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("pass", "fail", "missing")}, indent=2))
    return 0 if out["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
