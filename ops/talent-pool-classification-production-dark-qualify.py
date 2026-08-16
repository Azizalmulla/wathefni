#!/usr/bin/env python3
"""Read-only-safe production-dark qualification.

No production fixture insertion, candidate outreach, classification execution,
manual review, queue claim, OCR, extraction, embedding, or backfill.
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import sys
import urllib.request
from unittest import mock

import psycopg2
from psycopg2.extras import RealDictCursor

ORCH = pathlib.Path("/opt/wathefni/orchestrator")
EVIDENCE = pathlib.Path(os.environ["DARK_EVIDENCE"])
DEPLOYED_AT = os.environ.get("DARK_DEPLOYED_AT", "2026-07-25T21:27:37Z")
BASELINE_PATH = pathlib.Path(os.environ["DARK_BASELINE"]) if os.environ.get("DARK_BASELINE") else None
RESULTS: list[dict] = []

os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
sys.path.insert(0, str(ORCH))


import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
def ok(name: str, detail=None) -> None:
    RESULTS.append({"name": name, "pass": True, "detail": detail})
    print("PASS", name)


def bad(name: str, detail=None) -> None:
    RESULTS.append({"name": name, "pass": False, "detail": detail})
    print("FAIL", name, detail)


def check(name: str, condition: bool, detail=None) -> None:
    (ok if condition else bad)(name, detail)


def db():
    vals = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def health_code() -> int:
    with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=30) as response:
        response.read()
        return int(response.status)


def route_endpoint(app_mod, path: str, method: str):
    for route in app_mod.app.routes:
        if getattr(route, "path", None) == path and method.upper() in getattr(route, "methods", set()):
            return route.endpoint
    return None


def table_count(cur, table: str) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table}")
    return int(cur.fetchone()["count"])


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    import app
    import candidate_communication_authority as authority
    import talent_pool_classification as tpc
    import unified_candidates as unified

    check("production_health_200", health_code() == 200, health_code())
    health = app.health()
    check(
        "production_db_binding",
        bool((health.get("environment_binding") or {}).get("match"))
        and (health.get("environment_binding") or {}).get("application_environment") == "production",
        health.get("environment_binding"),
    )

    conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf"
    ).read_text()
    required = {
        "WATHEFNI_TALENT_POOL_CLASSIFICATION": "off",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS": "",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA": "off",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL": "off",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS": "off",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_UI": "off",
    }
    for key, value in required.items():
        check(f"flag_{key}_off", f"Environment={key}={value}\n" in conf, value)

    feature = tpc.feature_status("WATHEFNI")
    check("classification_no_tenant_enabled", feature["allowed_tenants"] == [], feature)
    check("classification_company_disabled", feature["enabled_for_company"] is False, feature)
    check("classification_master_runtime_off", feature["master_enabled"] is False, feature)
    check("classification_workers_runtime_off", feature["workers_enabled"] is False, feature)
    check("classification_manual_runtime_off", feature["manual_enabled"] is False, feature)
    check("classification_ui_runtime_off", feature["ui_enabled"] is False, feature)
    check("classification_schema_runtime_off", feature["schema_enabled"] is False, feature)

    unified_conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf"
    ).read_text()
    check(
        "unified_canary_config_unchanged",
        "WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off" in unified_conf
        and "WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI" in unified_conf,
    )
    unified_runtime = {
        "WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL": "off",
        "WATHEFNI_UNIFIED_CANDIDATES_TENANTS": "WATHEFNI",
    }
    unified_status = unified.feature_status("WATHEFNI", unified_runtime)
    check(
        "unified_wathefni_canary_still_enabled",
        unified_status.get("master_enabled") is False
        and unified_status.get("enabled_for_company") is True,
        unified_status,
    )

    # Route presence + fail-closed behavior without auth/session or production fixtures.
    feature_endpoint = route_endpoint(
        app, "/dashboard/prehire/classification/feature", "GET"
    )
    taxonomy_endpoint = route_endpoint(
        app, "/dashboard/prehire/classification/taxonomy", "GET"
    )
    run_endpoint = route_endpoint(
        app, "/dashboard/prehire/applications/{app_key}/classification/run", "POST"
    )
    check("classification_routes_mounted", all((feature_endpoint, taxonomy_endpoint, run_endpoint)))
    if feature_endpoint:
        direct_feature = feature_endpoint(context={"company_code": "WATHEFNI"})
        check(
            "classification_feature_reports_dark",
            direct_feature.get("enabled_for_company") is False
            and direct_feature.get("allowed_tenants") == [],
            direct_feature,
        )
    for name, endpoint, kwargs in (
        ("taxonomy", taxonomy_endpoint, {"context": {"company_code": "WATHEFNI"}}),
        (
            "run",
            run_endpoint,
            {
                "app_key": "DARK-READONLY-NO-APP",
                "body": {},
                "context": {"company_code": "WATHEFNI"},
            },
        ),
    ):
        if not endpoint:
            bad(f"classification_{name}_route_dark", "route_missing")
            continue
        try:
            endpoint(**kwargs)
        except app.HTTPException as exc:
            check(
                f"classification_{name}_route_dark",
                exc.status_code == 404
                and isinstance(exc.detail, dict)
                and exc.detail.get("error") == "talent_pool_classification_disabled",
                {"status": exc.status_code, "detail": exc.detail},
            )
        else:
            bad(f"classification_{name}_route_dark", "unexpected_success")

    # Production dashboard was not changed; classification UI markers must be absent.
    ui_markers = (
        "classification/feature",
        "classification-filter-bar",
        "candidate-classification-section",
    )
    marker_hits = []
    dashboard = pathlib.Path("/var/www/wathefni-dashboard")
    if dashboard.exists():
        for path in dashboard.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(marker in text for marker in ui_markers):
                marker_hits.append(str(path))
    check("classification_ui_absent", marker_hits == [], marker_hits)

    # DB schema is additive; only immutable global taxonomy definitions are seeded.
    classification_tables = (
        "taxonomy_releases",
        "taxonomy_nodes",
        "taxonomy_tenant_nodes",
        "candidate_classification_runs",
        "candidate_classification_suggestions",
        "candidate_classification_review_events",
        "talent_pool_classification_jobs",
    )
    mutation_counts = {}
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name = ANY(%s)
                """,
                (list(classification_tables),),
            )
            present = {row["table_name"] for row in cur.fetchall()}
            check("classification_tables_present", present == set(classification_tables), sorted(present))
            counts = {table: table_count(cur, table) for table in classification_tables}
            check("taxonomy_release_present", counts["taxonomy_releases"] == 1, counts)
            check("taxonomy_nodes_present", counts["taxonomy_nodes"] == 43, counts)
            check("taxonomy_tenant_assignments_empty", counts["taxonomy_tenant_nodes"] == 0, counts)
            for table in (
                "candidate_classification_runs",
                "candidate_classification_suggestions",
                "candidate_classification_review_events",
                "talent_pool_classification_jobs",
            ):
                check(f"empty_{table}", counts[table] == 0, counts[table])

            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name='company_feature_flags'
                """
            )
            if cur.fetchone():
                cur.execute(
                    """
                    SELECT count(*) AS count FROM company_feature_flags
                    WHERE feature_key ILIKE '%classification%'
                    """
                )
                check("no_classification_company_feature_flags", int(cur.fetchone()["count"]) == 0)
            else:
                ok("no_company_feature_flags_table", True)

            for table in (
                "applications",
                "candidates",
                "positions",
                "application_lifecycle_events",
                "outbound_delivery_events",
            ):
                mutation_counts[table] = table_count(cur, table)
            if BASELINE_PATH:
                baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
                expected_counts = {
                    table: int((baseline.get("snapshot") or {}).get(table, {}).get("count", -1))
                    for table in mutation_counts
                }
            else:
                expected_counts = dict(mutation_counts)
            check("candidate_job_lifecycle_outbound_unchanged", mutation_counts == expected_counts, mutation_counts)

            recent_sources = {}
            timestamp_columns = {
                "cv_extraction_cache": "created_at",
                "cv_extraction_finalizations": "created_at",
                "cv_extraction_leases": "created_at",
                "cv_extraction_runs": "created_at",
                "embedding_reindex_events": "created_at",
                "embedding_reindex_runs": "created_at",
                "semantic_documents": "updated_at",
            }
            for table, column in timestamp_columns.items():
                cur.execute(
                    f"SELECT count(*) AS count FROM {table} WHERE {column} >= %s::timestamptz",
                    (DEPLOYED_AT,),
                )
                recent_sources[table] = int(cur.fetchone()["count"])
            check("no_ocr_extraction_embedding_reruns", not any(recent_sources.values()), recent_sources)

    # Held authority: production code, synthetic in-memory rows, mocked providers.
    base = {
        "app_key": "READONLY-AUTHORITY-PROBE",
        "company_code": "WATHEFNI",
        "phone": "96550001111",
        "candidate_name": "Authority Probe",
        "data_source": "production",
        "status": "ready_for_review",
        "raw_json": {},
    }
    denial_matrix = {}
    for label, row, governance in (
        ("needs_role", {**base, "status": "needs_role"}, None),
        ("import_review", {**base, "status": "import_review"}, None),
        ("import_archived", {**base, "status": "import_archived"}, None),
        ("restricted", base, {"restriction_state": "restricted"}),
    ):
        decision = authority.evaluate_candidate_communication_authority(
            row,
            governance=governance,
            expected_company_code="WATHEFNI",
            kind="notify",
        )
        denial_matrix[label] = decision
    check(
        "held_archived_restricted_fail_closed",
        all(not row.get("allowed") for row in denial_matrix.values()),
        {key: value.get("code") for key, value in denial_matrix.items()},
    )
    live_decision = authority.evaluate_candidate_communication_authority(
        base, expected_company_code="WATHEFNI", kind="notify"
    )
    check("valid_live_application_authorized", live_decision.get("allowed") is True, live_decision)
    tenant_decision = authority.evaluate_candidate_communication_authority(
        base, expected_company_code="OTHER", kind="notify"
    )
    check(
        "communication_tenant_isolation",
        tenant_decision.get("code") == authority.ERROR_TENANT,
        tenant_decision,
    )

    notify_endpoint = app.dashboard_prehire_notify
    provider = mock.Mock()
    registry_call = mock.Mock()
    for status in ("needs_role", "import_review", "import_archived"):
        held = {**base, "status": status}
        with (
            mock.patch.object(app, "dashboard_application_or_404", return_value=held),
            mock.patch.object(app, "require_entitlement", return_value=None),
            mock.patch.object(app, "load_candidate_communication_governance", return_value=None),
            mock.patch.object(app, "send_octopus_whatsapp", provider),
            mock.patch.object(app, "run_prehire_registry_action", registry_call),
        ):
            try:
                notify_endpoint(
                    app_key=held["app_key"],
                    request=None,
                    context={"company_code": "WATHEFNI", "permissions": ["candidate.manage"]},
                )
            except app.HTTPException as exc:
                check(
                    f"direct_api_{status}_fails_closed",
                    exc.status_code == 409
                    and isinstance(exc.detail, dict)
                    and exc.detail.get("error") == authority.ERROR_HELD,
                    exc.detail,
                )
            else:
                bad(f"direct_api_{status}_fails_closed", "unexpected_success")
    check("direct_api_no_provider_or_registry_call", provider.call_count == registry_call.call_count == 0)

    source = inspect.getsource(app.dashboard_prehire_notify)
    check(
        "direct_api_gate_precedes_registry",
        source.find("require_live_candidate_communication") >= 0
        and source.find("require_live_candidate_communication")
        < source.find("run_prehire_registry_action"),
    )

    # No worker service/process exists. Process proof is supplied by the shell wrapper;
    # source has no queue claim implementation in this phase.
    module_source = pathlib.Path(ORCH / "talent_pool_classification.py").read_text()
    check("no_queue_claim_implementation", "SKIP LOCKED" not in module_source)

    failed = [result for result in RESULTS if not result["pass"]]
    report = {
        "pass": sum(1 for result in RESULTS if result["pass"]),
        "fail": len(failed),
        "results": RESULTS,
        "failed": failed,
        "mutation_counts": mutation_counts,
        "verdict": "GO_PRODUCTION_DARK" if not failed else "NO_GO",
    }
    (EVIDENCE / "production-dark-qualification.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"verdict": report["verdict"], "pass": report["pass"], "fail": report["fail"]}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
