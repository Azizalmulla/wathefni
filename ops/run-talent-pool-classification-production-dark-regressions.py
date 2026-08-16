#!/usr/bin/env python3
"""Guarded production regression runner for classification-dark packaging.

Every DB-bound matrix uses its existing isolated synthetic tenants and cleanup.
Delivery is forced dry-run. Classification flags stay fully OFF and its tables
must remain empty after every pack.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time

import psycopg2
from psycopg2.extras import RealDictCursor

ORCH = pathlib.Path("/opt/wathefni/orchestrator")
EVIDENCE = pathlib.Path(os.environ["DARK_EVIDENCE"])
LOGS = EVIDENCE / "frozen-regressions"
LOGS.mkdir(parents=True, exist_ok=True)

ENV = {
    **os.environ,
    "WATHEFNI_ENV": "production",
    "WATHEFNI_ENVIRONMENT": "production",
    "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.env",
    "WATHEFNI_WORKSPACE": "/root/.openclaw/workspaces/company-wathefni",
    "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
    "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
    "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni",
    "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-production-isolation-v1",
    "WATHEFNI_DELIVERY_MODE": "dry_run",
    "WATHEFNI_CANONICAL_LIFECYCLE": "true",
    "WATHEFNI_TALENT_POOL_CLASSIFICATION": "off",
    "WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS": "",
    "WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA": "off",
    "WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL": "off",
    "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS": "off",
    "WATHEFNI_TALENT_POOL_CLASSIFICATION_UI": "off",
    "WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL": "off",
    "WATHEFNI_UNIFIED_CANDIDATES_TENANTS": "WATHEFNI",
    "WATHEFNI_BOUNDARY_ALLOW_PRODUCTION": "1",
    "WATHEFNI_C01_PROD_MATRIX_ACK": "production-isolated-c01",
    "WATHEFNI_C2_PROD_MATRIX_ACK": "production-isolated-c2",
    "ACK_C3_PRODUCTION_QUALIFY": "yes",
    "ACK_C3_PRODUCTION_READONLY": "yes",
    "ACK_RANKING_PRODUCTION_QUALIFY": "yes",
    "ACK_INTERVIEWS_PRODUCTION_QUALIFY": "yes",
    "ACK_OFFERS_HIRING_PRODUCTION_QUALIFY": "yes",
    "ACK_ASSESSMENTS_PRODUCTION_QUALIFY": "yes",
    "WATHEFNI_EMBEDDING_MODEL": "voyage-4-large",
    "WATHEFNI_RANKING_RERANK": "0",
    # Synthetic Job publishability needs an apply channel; delivery remains dry_run.
    "WATHEFNI_APPLY_WHATSAPP_NUMBER": os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER") or "96599338566",
    "WATHEFNI_DASHBOARD_SOURCE_ROOT": str(EVIDENCE / "dashboard-source"),
    "WATHEFNI_ORCHESTRATOR_SOURCE_ROOT": str(ORCH),
    "PYTHONPATH": str(ORCH),
}

PACKS = [
    ("authority", "test_candidate_communication_authority.py"),
    ("classification", "test_talent_pool_classification.py"),
    ("unified_candidates", "test_unified_candidates.py"),
    ("candidates_c0_c1", "ops/candidates-c01-production-matrix.py"),
    ("candidates_c2", "ops/candidates-c2-production-matrix.py"),
    ("candidates_c3", "ops/candidates-c3-production-matrix.py"),
    ("candidates_c3_readonly_audit", "ops/candidates-c3-production-audit.py"),
    ("jobs_stage_a", "smoke-test-jobs-phase2-stage-a-unit.py"),
    ("jobs_stage_b", "smoke-test-jobs-phase2-stage-b-unit.py"),
    ("ranking", "ops/ranking-r0-r3-production-matrix.py"),
    ("ranking_presentation", "ops/ranking-result-presentation-production-matrix.py"),
    ("reports", "ops/reports-v1-production-matrix.py"),
    ("assistant", "ops/assistant-a0a3-production-matrix.py"),
    ("assistant_jobs_ranking", "ops/assistant-jobs-ranking-ux-production-matrix.py"),
    ("interviews", "ops/interviews-production-matrix.py"),
    ("offers_hiring", "ops/offers-hiring-production-matrix.py"),
    ("assessments", "ops/assessments-on-off-production-matrix.py"),
    ("canonical_lifecycle", "smoke-test-canonical-recruiting-lifecycle.py"),
    ("inbound_email", "smoke-test-inbound-email.py"),
    ("bulk_intake", "smoke-test-bulk-cv-import.py"),
    ("tiered_intake", "smoke-test-tiered-intake.py"),
    ("communication_router", str(EVIDENCE / "harness" / "smoke-test-communication-router.py")),
    ("permissions_tenant_boundary", "ops/optional-module-boundary-production-matrix.py"),
    ("tenant_isolation", "smoke-test-tenant-isolation-harness.py"),
    ("dashboard_contract", str(EVIDENCE / "harness" / "smoke-test-dashboard-auth.py")),
    ("hr_mobile_contract", "smoke-test-mobile-action-authority.py"),
]


def db_url() -> str:
    values = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values["WATHEFNI_DATABASE_URL"]


def database_snapshot() -> dict:
    with psycopg2.connect(db_url(), cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            counts = {}
            for table in (
                "applications",
                "candidates",
                "positions",
                "application_lifecycle_events",
                "outbound_delivery_events",
                "candidate_classification_runs",
                "candidate_classification_suggestions",
                "candidate_classification_review_events",
                "talent_pool_classification_jobs",
                "taxonomy_tenant_nodes",
            ):
                cur.execute(f"SELECT count(*) AS count FROM {table}")
                counts[table] = int(cur.fetchone()["count"])
            cur.execute(
                """
                SELECT count(*) AS count FROM companies
                WHERE company_code <> 'WATHEFNI'
                """
            )
            counts["non_wathefni_companies"] = int(cur.fetchone()["count"])
            cur.execute(
                """
                SELECT count(*) AS count FROM applications
                WHERE company_code='WATHEFNI'
                """
            )
            counts["wathefni_applications"] = int(cur.fetchone()["count"])
            return counts


def classification_empty(snapshot: dict) -> bool:
    return all(
        snapshot.get(table) == 0
        for table in (
            "candidate_classification_runs",
            "candidate_classification_suggestions",
            "candidate_classification_review_events",
            "talent_pool_classification_jobs",
            "taxonomy_tenant_nodes",
        )
    )


def cleanup_known_outbound_residue(category: str, started_at: float) -> int:
    patterns = {
        "assessments": "assessments-on-off-production-matrix-v1-%",
        "permissions_tenant_boundary": "PRODBND%",
    }
    pattern = patterns.get(category)
    if not pattern:
        return 0
    with psycopg2.connect(db_url(), cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM outbound_delivery_events
                WHERE subject_key LIKE %s
                  AND created_at >= to_timestamp(%s)
                  AND status='dry_run'
                """,
                (pattern, started_at),
            )
            removed = cur.rowcount
        conn.commit()
    return int(removed)


def main() -> int:
    baseline = database_snapshot()
    results = []
    for category, relative in PACKS:
        candidate = pathlib.Path(relative)
        path = candidate if candidate.is_absolute() else ORCH / candidate
        row = {"category": category, "pack": relative, "exists": path.exists()}
        if not path.exists():
            row["status"] = "missing"
            results.append(row)
            print("MISSING", category, relative, flush=True)
            continue
        log = LOGS / f"{category}-{path.name}.log"
        started = time.time()
        with log.open("w", encoding="utf-8") as handle:
            try:
                process = subprocess.run(
                    [str(ORCH / ".venv/bin/python"), str(path)],
                    cwd=str(ORCH),
                    env=ENV,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=1800,
                )
                return_code = process.returncode
            except subprocess.TimeoutExpired:
                return_code = 124
        outbound_cleanup = cleanup_known_outbound_residue(category, started)
        snapshot = database_snapshot()
        row.update(
            {
                "status": "pass" if return_code == 0 else "fail",
                "rc": return_code,
                "elapsed_s": round(time.time() - started, 2),
                "log": str(log),
                "classification_empty_after": classification_empty(snapshot),
                "snapshot_after": snapshot,
                "synthetic_outbound_cleanup": outbound_cleanup,
            }
        )
        if not row["classification_empty_after"]:
            row["status"] = "fail"
            row["error"] = "classification_side_effect_detected"
        results.append(row)
        print(row["status"].upper(), category, relative, f"rc={return_code}", flush=True)

    final = database_snapshot()
    final_cleanup_ok = (
        final["applications"] == baseline["applications"]
        and final["candidates"] == baseline["candidates"]
        and final["positions"] == baseline["positions"]
        and final["application_lifecycle_events"] == baseline["application_lifecycle_events"]
        and final["outbound_delivery_events"] == baseline["outbound_delivery_events"]
        and final["non_wathefni_companies"] == baseline["non_wathefni_companies"]
        and final["wathefni_applications"] == baseline["wathefni_applications"]
        and classification_empty(final)
    )
    output = {
        "baseline": baseline,
        "final": final,
        "final_cleanup_ok": final_cleanup_ok,
        "pass": sum(1 for row in results if row.get("status") == "pass"),
        "fail": sum(1 for row in results if row.get("status") == "fail"),
        "missing": sum(1 for row in results if row.get("status") == "missing"),
        "results": results,
    }
    if not final_cleanup_ok:
        output["fail"] += 1
    (EVIDENCE / "frozen-production-regressions.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "pass": output["pass"],
                "fail": output["fail"],
                "missing": output["missing"],
                "final_cleanup_ok": final_cleanup_ok,
            },
            indent=2,
        )
    )
    return 0 if output["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
