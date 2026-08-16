#!/usr/bin/env python3
"""Frozen staging regressions for complete Talent Pool Classification UI phase.

Does not touch production. Classification workers remain OFF.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time

ORCH = pathlib.Path("/opt/wathefni/staging/orchestrator")
EVIDENCE = pathlib.Path(os.environ["TPC_UI_EVIDENCE"])
LOGS = EVIDENCE / "frozen-regressions"
LOGS.mkdir(parents=True, exist_ok=True)

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
    ("unified_candidates", "ops/unified-candidates-staging-qualify.py"),
    ("classification_unit", "test_talent_pool_classification.py"),
    ("candidates_c01", "ops/candidates-c01-staging-matrix.py"),
    ("candidates_c2", "ops/candidates-c2-staging-matrix.py"),
    ("candidates_c3", "ops/candidates-c3-staging-matrix.py"),
    ("jobs_optional_boundary", "ops/optional-module-boundary-staging-matrix.py"),
    ("ranking_r0_r3", "ops/ranking-r0-r3-staging-matrix.py"),
    ("reports_v1", "ops/reports-v1-staging-matrix.py"),
    ("assistant_a0a3", "ops/assistant-a0a3-staging-matrix.py"),
    ("interviews", "ops/interviews-staging-matrix.py"),
    ("offers_hiring", "ops/offers-hiring-staging-matrix.py"),
    ("assessments_on_off", "ops/assessments-on-off-staging-matrix.py"),
]


def classification_residue() -> dict:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    vals = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.staging.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    out = {}
    with psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            for table in (
                "candidate_classification_runs",
                "candidate_classification_suggestions",
                "candidate_classification_review_events",
                "talent_pool_classification_jobs",
            ):
                cur.execute(
                    f"SELECT count(*) AS c FROM {table} WHERE app_key LIKE 'TPC%%' OR app_key LIKE 'TPCUI%%' OR app_key LIKE 'TPCSHOT%%' OR app_key LIKE 'TPCSTG%%'"
                )
                out[table] = int(cur.fetchone()["c"])
    return out


def run_one(name: str, rel: str) -> dict:
    path = ORCH / rel
    log = LOGS / f"{name}.log"
    report = {"name": name, "path": rel, "exists": path.exists()}
    if not path.exists():
        report.update({"status": "missing", "rc": 127})
        print("MISSING", name)
        return report
    env = {
        **ENV,
        "C01_STAGING_REPORT": str(LOGS / "candidates-c01-staging-matrix.json"),
        "OPTIONAL_MODULE_BOUNDARY_REPORT": str(LOGS / "optional-module-boundary.json"),
    }
    t0 = time.time()
    with log.open("w", encoding="utf-8") as fh:
        if rel.endswith(".py") and rel.startswith("test_"):
            cmd = ["/opt/wathefni/orchestrator/.venv/bin/python", "-m", "unittest", rel.replace(".py", ""), "-q"]
            cwd = str(ORCH)
        else:
            cmd = ["/opt/wathefni/orchestrator/.venv/bin/python", str(path)]
            cwd = str(ORCH)
        proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)
    report.update(
        {
            "status": "pass" if proc.returncode == 0 else "fail",
            "rc": proc.returncode,
            "elapsed_s": round(time.time() - t0, 2),
            "log": str(log),
        }
    )
    print(f"{report['status'].upper()} {name} rc={proc.returncode} {report['elapsed_s']}s")
    return report


def main() -> int:
    pre = classification_residue()
    results = [run_one(name, rel) for name, rel in PACKS]
    post = classification_residue()
    summary = {
        "pass_count": sum(1 for r in results if r.get("status") == "pass"),
        "fail_count": sum(1 for r in results if r.get("status") != "pass"),
        "results": results,
        "synthetic_residue_pre": pre,
        "synthetic_residue_post": post,
        "zero_residue": all(v == 0 for v in post.values()),
    }
    (LOGS / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("pass_count", "fail_count", "zero_residue", "synthetic_residue_post")}, indent=2))
    return 0 if summary["fail_count"] == 0 and summary["zero_residue"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
