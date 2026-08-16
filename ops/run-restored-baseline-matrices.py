#!/usr/bin/env python3
"""Run restored-baseline staging matrices; write JSON summary."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ORCH = Path("/opt/wathefni/staging/orchestrator")
EVIDENCE = Path(os.environ.get("REQUAL_EVIDENCE", "/tmp/uc-requal"))
EVIDENCE.mkdir(parents=True, exist_ok=True)

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
    # Candidates
    ("candidates_c01", "ops/candidates-c01-staging-matrix.py", {"C01_STAGING_REPORT": str(EVIDENCE / "candidates-c01-staging-matrix.json")}),
    ("candidates_c2_schema", "ops/candidates-c2-schema-verify.py", {}),
    ("candidates_c2", "ops/candidates-c2-staging-matrix.py", {}),
    ("candidates_c3_schema", "ops/candidates-c3-schema-verify.py", {}),
    ("candidates_c3", "ops/candidates-c3-staging-matrix.py", {}),
    # Ranking
    ("ranking_r0_r3", "ops/ranking-r0-r3-staging-matrix.py", {}),
    ("ranking_presentation", "ops/ranking-result-presentation-staging-matrix.py", {}),
    # Reports
    ("reports_v1", "ops/reports-v1-staging-matrix.py", {}),
    # Interviews
    ("interviews", "ops/interviews-staging-matrix.py", {}),
]


def run_one(name: str, rel: str, extra_env: dict) -> dict:
    path = ORCH / rel
    log = EVIDENCE / f"{name}.log"
    report = {
        "name": name,
        "path": rel,
        "exists": path.exists(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not path.exists():
        report.update({"status": "missing", "rc": 127})
        print(f"MISSING {name}")
        return report
    env = {**ENV, **extra_env}
    t0 = time.time()
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            ["/opt/wathefni/orchestrator/.venv/bin/python", str(path)],
            cwd=str(ORCH),
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
    elapsed = round(time.time() - t0, 2)
    report.update({"status": "pass" if proc.returncode == 0 else "fail", "rc": proc.returncode, "elapsed_s": elapsed, "log": str(log)})
    print(f"{report['status'].upper()} {name} rc={proc.returncode} {elapsed}s")
    return report


def main() -> int:
    selected = sys.argv[1:] or [p[0] for p in PACKS]
    results = []
    for name, rel, extra in PACKS:
        if name not in selected and selected != [p[0] for p in PACKS]:
            # allow subset by name
            if name not in selected:
                continue
        results.append(run_one(name, rel, extra))
    out = {
        "evidence": str(EVIDENCE),
        "results": results,
        "pass": sum(1 for r in results if r.get("status") == "pass"),
        "fail": sum(1 for r in results if r.get("status") == "fail"),
        "missing": sum(1 for r in results if r.get("status") == "missing"),
    }
    (EVIDENCE / "matrix-run.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("pass", "fail", "missing", "evidence")}, indent=2))
    return 0 if out["fail"] == 0 and out["missing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
