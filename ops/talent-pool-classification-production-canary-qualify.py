#!/usr/bin/env python3
"""Guarded production canary for internal WATHEFNI classification only.

Synthetic records, explicit manual runs, workers OFF, deterministic cleanup.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

COMPANY = "WATHEFNI"
PREFIX = "TPCCAN" + uuid.uuid4().hex[:8].upper()
MARKER = "talent_pool_classification_production_canary_v1"
ORCH = pathlib.Path("/opt/wathefni/orchestrator")
EVIDENCE = pathlib.Path(os.environ["TPC_CANARY_EVIDENCE"])
CONF = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf")
RESULTS: list[dict[str, Any]] = []

EXPECTED_CLASSIFIER_SHA = "d97bae99e9d181daaadd384e070951902fa35243d14c92776bd20b712de0505b"
PROTECTED_TABLES = (
    "positions",
    "application_lifecycle_events",
    "ranking_runs",
    "ranking_run_items",
    "outbound_delivery_events",
    "cv_extraction_cache",
    "cv_extraction_finalizations",
    "cv_extraction_leases",
    "cv_extraction_runs",
    "embedding_reindex_events",
    "embedding_reindex_runs",
    "semantic_documents",
    "candidate_interviews",
    "employment_offers",
    "employees",
    "application_cv_fact_snapshots",
)

FIXTURES: dict[str, dict[str, Any]] = {
    "technology": {
        "text": "Senior Software Engineer with 6 years building Python FastAPI services on AWS. Computer Science degree.",
        "facts": {"skills": []},
    },
    "hr": {
        "text": "HR Generalist and recruiter managing talent acquisition and employee relations. Fluent Arabic and English.",
        "facts": {},
    },
    "finance": {
        "text": "Accountant with financial reporting, audit, treasury and Excel. Bachelor in Accounting.",
        "facts": {},
    },
    "operations": {
        "text": "Operations Coordinator managing supply chain and operations management processes.",
        "facts": {},
    },
    "common_tools": {
        "text": "Office administrator coordinating calendars, Word documents, Excel trackers, email and common business software.",
        "facts": {},
    },
    "finance_erp": {
        "text": "Senior accountant managing financial reporting, treasury and audit using SAP ERP software and Excel.",
        "facts": {},
    },
    "hr_systems": {
        "text": "HR Generalist managing recruitment, employee relations, payroll coordination and HR information systems.",
        "facts": {},
    },
    "multi": {
        "text": "Operations manager who led warehouse teams and built Python automation with SQL dashboards for logistics planning.",
        "facts": {},
    },
    "career_change": {
        "text": "Former Mechanical Engineer. Completed a software developer bootcamp, built Python and FastAPI projects, and completed a backend internship.",
        "facts": {},
    },
    "short_clear": {
        "text": "CS graduate. Python projects. Software Engineering intern.",
        "facts": {"skills": []},
    },
    "long_unclear": {
        "text": "Professional with experience in many areas and various responsibilities across teams over time. Supported initiatives, communicated with stakeholders, used standard tools, and contributed to different projects without specific role titles, domain outcomes, education, or sustained specialist skills.",
        "facts": {},
    },
    "arabic": {
        "text": "مهندس برمجيات بخبرة في بايثون وقواعد البيانات وبناء تطبيقات تقنية.",
        "facts": {},
    },
    "english": {
        "text": "English-only CV: Marketing Specialist with social media and sales campaigns.",
        "facts": {},
    },
    "bilingual": {
        "text": "Marketing Specialist / أخصائي تسويق. Digital marketing and مبيعات for retail brands.",
        "facts": {},
    },
    "incomplete_facts": {
        "text": "Backend developer using Python and SQL daily; built APIs for banking operations.",
        "facts": {"skills": []},
    },
    "insufficient": {
        "text": "Name only\nphone 000",
        "facts": {},
    },
    "medium": {
        "text": "Office administrator who completed practical Java and Docker training and used both in a supervised internal technical assignment.",
        "facts": {},
    },
    "needs_review": {
        "text": "Professional summary covering general coordination, communication, and support responsibilities across several teams without a declared specialist function.",
        "facts": {"skills": ["Java"], "summary": "Used Java in one short practice project."},
    },
}


def record(name: str, passed: bool, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": bool(passed), "detail": detail})
    print("PASS" if passed else "FAIL", name, flush=True)


def require(name: str, condition: bool, detail: Any = None) -> None:
    record(name, condition, detail)
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def database_url() -> str:
    values: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values["WATHEFNI_DATABASE_URL"]


def db():
    return psycopg2.connect(database_url(), cursor_factory=RealDictCursor)


def set_flags(*, tenants: str, schema: str, manual: str, ui: str) -> None:
    values = {
        "WATHEFNI_TALENT_POOL_CLASSIFICATION": "off",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS": tenants,
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA": schema,
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL": manual,
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS": "off",
        "WATHEFNI_TALENT_POOL_CLASSIFICATION_UI": ui,
    }
    CONF.write_text(
        "[Service]\n" + "".join(f"Environment={key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    os.environ.update(values)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "wathefni-orchestrator.service"], check=True)
    for _ in range(90):
        if subprocess.run(
            ["curl", "-sf", "http://127.0.0.1:8010/health"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("production health failed after flag change")


def snapshot() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with db() as conn:
        with conn.cursor() as cur:
            for table in PROTECTED_TABLES:
                cur.execute("SELECT to_regclass(%s) AS name", (f"public.{table}",))
                if not cur.fetchone()["name"]:
                    result[table] = {"exists": False}
                    continue
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                    (table,),
                )
                columns = {row["column_name"] for row in cur.fetchall()}
                timestamp_column = next(
                    (column for column in ("updated_at", "created_at", "finalized_at", "started_at") if column in columns),
                    None,
                )
                if timestamp_column:
                    cur.execute(f"SELECT count(*) AS count, max({timestamp_column}) AS latest FROM {table}")
                else:
                    cur.execute(f"SELECT count(*) AS count, NULL::text AS latest FROM {table}")
                row = cur.fetchone()
                result[table] = {
                    "exists": True,
                    "count": int(row["count"]),
                    "latest": str(row["latest"]) if row.get("latest") is not None else None,
                }
    return result


def mint() -> dict[str, str]:
    sys.path.insert(0, str(ORCH))
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND status='active' AND role='owner'
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (COMPANY,),
            )
            user = cur.fetchone()
    if not user:
        raise RuntimeError("no active WATHEFNI owner")
    token, _ = app.create_dashboard_session(dict(user))
    return {"Authorization": f"Bearer {token}", "X-Wathefni-Company": COMPANY}


def http(
    method: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:8010{path}",
        data=data,
        method=method,
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:500]}


def seed() -> dict[str, str]:
    keys: dict[str, str] = {}
    with db() as conn:
        with conn.cursor() as cur:
            for index, (slug, fixture) in enumerate(FIXTURES.items(), start=1):
                app_key = f"{PREFIX}-{slug.upper()}"
                phone = f"imp-{PREFIX.lower()}-{index:02d}"
                keys[slug] = app_key
                cur.execute(
                    """
                    INSERT INTO candidates(phone,name,email,profile,raw_json)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                    """,
                    (
                        phone,
                        f"TPC Canary Synthetic {slug}",
                        f"{slug}.{PREFIX.lower()}@example.invalid",
                        Json(fixture["facts"]),
                        Json({"marker": MARKER, "prefix": PREFIX, "synthetic": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code,app_key,phone,status,current_step,position_code,position_title,
                      cv_received,data_source,raw_json,ingested_at,updated_at
                    ) VALUES (%s,%s,%s,'needs_role','needs_role','','',true,'production_canary',%s::jsonb,now(),now())
                    """,
                    (
                        COMPANY,
                        app_key,
                        phone,
                        Json(
                            {
                                "marker": MARKER,
                                "prefix": PREFIX,
                                "synthetic": True,
                                "normalized_cv_text": fixture["text"],
                                "cv": {"processing": {"status": "ready", "text_extracted": True}},
                            }
                        ),
                    ),
                )
        conn.commit()
    return keys


def cleanup() -> dict[str, int]:
    removed: dict[str, int] = {}
    with db() as conn:
        with conn.cursor() as cur:
            statements = (
                ("saved_views", "DELETE FROM candidate_saved_views WHERE company_code=%s AND name LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("reviews", "DELETE FROM candidate_classification_review_events WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("suggestions", "DELETE FROM candidate_classification_suggestions WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("runs", "DELETE FROM candidate_classification_runs WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("jobs", "DELETE FROM talent_pool_classification_jobs WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("tenant_nodes", "DELETE FROM taxonomy_tenant_nodes WHERE company_code=%s AND node_id LIKE %s", (COMPANY, f"tenant.{COMPANY}.tpccan%")),
                ("semantic", "DELETE FROM semantic_documents WHERE company_code=%s AND entity_key LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("applications", "DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%")),
                ("candidates", "DELETE FROM candidates WHERE phone LIKE %s", (f"imp-{PREFIX.lower()}-%",)),
            )
            for name, sql, params in statements:
                cur.execute(sql, params)
                removed[name] = cur.rowcount
        conn.commit()
    return removed


def sidecar_counts() -> dict[str, int]:
    with db() as conn:
        with conn.cursor() as cur:
            result = {}
            for table in (
                "candidate_classification_runs",
                "candidate_classification_suggestions",
                "candidate_classification_review_events",
                "talent_pool_classification_jobs",
                "taxonomy_tenant_nodes",
            ):
                cur.execute(f"SELECT count(*) AS count FROM {table}")
                result[table] = int(cur.fetchone()["count"])
            return result


def write_ux_html(outcomes: dict[str, Any], profiles: dict[str, Any], saved_view: dict[str, Any]) -> None:
    rows = []
    for slug, outcome in outcomes.items():
        chip = (profiles.get(slug) or {}).get("chip")
        rows.append(
            "<tr>"
            f"<td>{html.escape(slug)}</td>"
            f"<td>{html.escape(str(outcome['status']))}</td>"
            f"<td>{html.escape(', '.join(outcome['bands']) or '—')}</td>"
            f"<td>{html.escape(str(chip)) if chip else '<span class=muted>hidden</span>'}</td>"
            "</tr>"
        )
    technology_profile = json.dumps(profiles.get("technology"), indent=2, default=str, ensure_ascii=False)
    EVIDENCE.joinpath("ux-production-canary.html").write_text(
        """<!doctype html><meta charset="utf-8"><title>TPC production canary UX</title>
<style>body{font:14px/1.4 system-ui;margin:28px;background:#f4f1eb;color:#15201c}
table{border-collapse:collapse;width:100%;background:#fff}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left}
.muted{color:#777}.panel{background:#fff;padding:18px;margin-top:22px;border:1px solid #d5d0c8}
pre{white-space:pre-wrap;font-size:12px}</style>
<h1>Unified Candidates — internal WATHEFNI classification canary</h1>
<p>Production synthetic records. One compact chip only when current High evidence allows it.</p>
<table><tr><th>Fixture</th><th>Outcome</th><th>Bands</th><th>Compact chip</th></tr>"""
        + "\n".join(rows)
        + "</table><div class=panel><h2>Saved classification view</h2><pre>"
        + html.escape(json.dumps(saved_view, indent=2, default=str))
        + "</pre></div><div class=panel><h2>Classification profile: evidence, versions, authority and history</h2><pre>"
        + html.escape(technology_profile)
        + "</pre></div>",
        encoding="utf-8",
    )


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "WATHEFNI_ENV": "production",
            "WATHEFNI_ENVIRONMENT": "production",
            "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.env",
            "WATHEFNI_WORKSPACE": "/root/.openclaw/workspaces/company-wathefni",
            "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
            "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
            "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni",
            "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-production-isolation-v1",
            "WATHEFNI_DELIVERY_MODE": "dry_run",
        }
    )
    cleanup()
    baseline = snapshot()
    keys: dict[str, str] = {}
    leave_enabled = False
    report: dict[str, Any] = {}
    try:
        require(
            "exact_v12_classifier_deployed",
            subprocess.run(
                ["sha256sum", str(ORCH / "talent_pool_classification.py")],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()[0]
            == EXPECTED_CLASSIFIER_SHA,
        )
        set_flags(tenants=COMPANY, schema="on", manual="on", ui="on")
        sys.path.insert(0, str(ORCH))
        import app
        import candidate_communication_authority as communication_authority
        import talent_pool_classification as tpc
        import unified_candidates as uc

        require("classifier_version_v12", tpc.CLASSIFIER_VERSION == "classifier.deterministic_v1.2")
        feature = tpc.feature_status(COMPANY)
        require(
            "wathefni_only_canary_flags",
            feature["enabled_for_company"]
            and feature["allowed_tenants"] == [COMPANY]
            and feature["manual_enabled"]
            and feature["ui_enabled"]
            and feature["schema_enabled"]
            and not feature["master_enabled"]
            and not feature["workers_enabled"],
            feature,
        )
        require("external_tenant_disabled", not tpc.feature_enabled_for_company("EXTERNAL"))
        unified_runtime = {
            "WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL": "off",
            "WATHEFNI_UNIFIED_CANDIDATES_TENANTS": COMPANY,
        }
        unified_status = uc.feature_status(COMPANY, unified_runtime)
        require(
            "unified_candidates_unchanged",
            not unified_status.get("master_enabled")
            and unified_status.get("enabled_for_company")
            and unified_status.get("allowed_tenants") == [COMPANY],
            unified_status,
        )
        require(
            "persistent_worker_inactive",
            subprocess.run(
                ["systemctl", "is-active", "wathefni-talent-pool-classification-worker.service"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            != "active",
        )

        headers = mint()
        keys = seed()
        outcomes: dict[str, Any] = {}
        latencies: list[float] = []
        successes = 0
        failures = 0
        for slug, app_key in keys.items():
            started = time.perf_counter()
            code, body = http(
                "POST",
                f"/dashboard/prehire/applications/{app_key}/classification/run",
                headers,
                {
                    "confirm": True,
                    "document_version_id": "doc-canary-v1",
                    "extraction_version_id": "ext-canary-v1",
                },
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            latencies.append(latency_ms)
            if code == 200 and body.get("ok"):
                successes += 1
            else:
                failures += 1
            require(f"manual_run_{slug}", code == 200 and body.get("ok"), {"code": code, "body": body})
            result = body["result"]
            suggestions = result.get("suggestions") or []
            outcomes[slug] = {
                "status": result.get("status"),
                "outcome_label": result.get("outcome_label"),
                "bands": sorted({str(item.get("confidence_band")) for item in suggestions}),
                "node_ids": sorted({str(item.get("node_id")) for item in suggestions}),
                "suggestions": suggestions,
                "latency_ms": latency_ms,
                "ocr_triggered": body.get("ocr_triggered"),
                "workers_started": body.get("workers_started"),
                "run_id": (body.get("persisted") or {}).get("run_id"),
            }
            require(f"evidence_{slug}", all(item.get("evidence") for item in suggestions))
            require(f"no_ocr_or_worker_{slug}", not body.get("ocr_triggered") and not body.get("workers_started"))

        require(
            "clear_technology_high",
            "fn.technology" in outcomes["technology"]["node_ids"] and "High" in outcomes["technology"]["bands"],
            outcomes["technology"],
        )
        for slug, expected in (("common_tools", None), ("finance_erp", "fn.finance"), ("hr_systems", "fn.hr")):
            nodes = set(outcomes[slug]["node_ids"])
            require(
                f"technology_precision_{slug}",
                "fn.technology" not in nodes and (expected is None or expected in nodes),
                outcomes[slug],
            )
        require(
            "multidisciplinary_secondary_technology_medium",
            {"fn.operations", "fn.technology"}.issubset(outcomes["multi"]["node_ids"])
            and "Medium" in outcomes["multi"]["bands"],
            outcomes["multi"],
        )
        require("short_clear_not_penalized", "fn.technology" in outcomes["short_clear"]["node_ids"])
        require("career_change_preserved", "fn.technology" in outcomes["career_change"]["node_ids"])
        require(
            "long_unclear_not_forced",
            outcomes["long_unclear"]["status"] in {tpc.STATE_UNCLASSIFIED, tpc.STATE_NEEDS_REVIEW}
            and "fn.technology" not in outcomes["long_unclear"]["node_ids"],
            outcomes["long_unclear"],
        )
        require(
            "raw_text_recovers_grounded_technology",
            "fn.technology" in outcomes["incomplete_facts"]["node_ids"],
            outcomes["incomplete_facts"],
        )
        require("medium_behavior", outcomes["medium"]["status"] == tpc.STATE_CAUTIOUS)
        require("needs_review_behavior", outcomes["needs_review"]["status"] == tpc.STATE_NEEDS_REVIEW)
        require("unclassified_behavior", outcomes["insufficient"]["status"] == tpc.STATE_UNCLASSIFIED)
        require("arabic_labels_work", bool(outcomes["arabic"]["node_ids"]))
        require("english_labels_work", bool(outcomes["english"]["node_ids"]))
        require("bilingual_labels_work", bool(outcomes["bilingual"]["node_ids"]))
        require(
            "multi_label_not_forced_single",
            outcomes["multi"]["status"] == tpc.STATE_CLASSIFIED_MULTI
            and len(outcomes["multi"]["node_ids"]) > 1,
        )
        require(
            "no_candidate_quality_judgment",
            all(
                token not in json.dumps(outcomes, ensure_ascii=False).lower()
                for token in ("poor candidate", "weak candidate", "cv quality")
            ),
        )

        technology_key = keys["technology"]
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT suggestion_id,node_id FROM candidate_classification_suggestions
                    WHERE company_code=%s AND app_key=%s AND state='active'
                    """,
                    (COMPANY, technology_key),
                )
                suggestion_ids = {row["node_id"]: str(row["suggestion_id"]) for row in cur.fetchall()}

        reviews = (
            {
                "action": "confirm",
                "node_id": "fn.technology",
                "suggestion_id": suggestion_ids.get("fn.technology"),
                "node_type": "career_function",
                "label_en": "Technology",
                "label_ar": "التكنولوجيا",
                "reason": "Internal production canary confirmation",
            },
            {
                "action": "reject",
                "node_id": "role.software_engineer",
                "suggestion_id": suggestion_ids.get("role.software_engineer"),
                "reason": "Internal production canary rejection",
            },
            {
                "action": "add",
                "node_id": "lang.english",
                "node_type": "language",
                "label_en": "English",
                "label_ar": "الإنجليزية",
                "reason": "Internal production canary add",
            },
            {
                "action": "correct",
                "node_id": "lang.arabic",
                "previous_node_id": "lang.english",
                "node_type": "language",
                "label_en": "Arabic",
                "label_ar": "العربية",
                "reason": "Internal production canary correction",
            },
        )
        review_results = []
        for review in reviews:
            code, body = http(
                "POST",
                f"/dashboard/prehire/applications/{technology_key}/classification/review",
                headers,
                {**review, "confirm": True},
            )
            require(f"hr_{review['action']}", code == 200 and body.get("ok"), {"code": code, "body": body})
            review_results.append(body)

        code, first_profile_body = http(
            "GET",
            f"/dashboard/prehire/applications/{technology_key}/classification",
            headers,
        )
        require("profile_before_reclassify", code == 200 and first_profile_body.get("ok"))
        first_profile = first_profile_body["classification"]
        require(
            "hr_authority_layers_distinct",
            all(item.get("authority") == "hr_confirmed" for item in first_profile["confirmed"])
            and all(item.get("authority") == "ai_suggested" for item in first_profile["ai_suggested"]),
            first_profile,
        )
        require("rejected_suggestion_not_current", "role.software_engineer" not in {item["node_id"] for item in first_profile["ai_suggested"]})
        require("review_history_append_only", len(first_profile["history"]) == 4)

        code, rerun = http(
            "POST",
            f"/dashboard/prehire/applications/{technology_key}/classification/run",
            headers,
            {
                "confirm": True,
                "document_version_id": "doc-canary-v2",
                "extraction_version_id": "ext-canary-v2",
            },
        )
        require(
            "reclassification_new_immutable_run",
            code == 200
            and rerun.get("ok")
            and not (rerun.get("persisted") or {}).get("idempotent_hit")
            and (rerun.get("persisted") or {}).get("run_id") != outcomes["technology"]["run_id"],
            rerun,
        )
        code, profile_after_body = http(
            "GET",
            f"/dashboard/prehire/applications/{technology_key}/classification",
            headers,
        )
        profile_after = profile_after_body.get("classification") or {}
        require("profile_after_reclassify", code == 200 and bool(profile_after))
        require(
            "confirmed_survives_reclassification",
            "fn.technology" in {item["node_id"] for item in profile_after["confirmed"]},
            profile_after,
        )
        require(
            "rejected_does_not_return",
            "role.software_engineer" not in {item["node_id"] for item in profile_after["ai_suggested"]},
            profile_after,
        )
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id,document_version_id,extraction_version_id,taxonomy_version,classifier_version,created_at
                    FROM candidate_classification_runs
                    WHERE company_code=%s AND app_key=%s ORDER BY created_at
                    """,
                    (COMPANY, technology_key),
                )
                run_history = [dict(row) for row in cur.fetchall()]
        require(
            "old_runs_auditable_with_versions",
            len(run_history) == 2
            and {row["document_version_id"] for row in run_history} == {"doc-canary-v1", "doc-canary-v2"}
            and all(row["taxonomy_version"] and row["classifier_version"] for row in run_history),
            run_history,
        )

        profiles: dict[str, Any] = {}
        for slug in ("technology", "medium", "needs_review", "insufficient", "multi"):
            code, body = http(
                "GET",
                f"/dashboard/prehire/applications/{keys[slug]}/classification",
                headers,
            )
            require(f"profile_{slug}", code == 200 and body.get("ok"))
            profiles[slug] = body["classification"]
        require("high_compact_chip_only", bool(profiles["technology"].get("chip")))
        for slug in ("medium", "needs_review", "insufficient"):
            require(f"no_row_chip_{slug}", profiles[slug].get("chip") is None, profiles[slug])
        require(
            "profile_evidence_confidence_versions_history",
            bool(profiles["technology"]["ai_suggested"])
            and all(item.get("evidence") and item.get("confidence_band") for item in profiles["technology"]["ai_suggested"])
            and profiles["technology"].get("taxonomy_version")
            and profiles["technology"].get("classifier_version")
            and len(profiles["technology"].get("history") or []) == 4,
        )
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS count FROM information_schema.columns
                    WHERE table_schema='public' AND table_name IN ('applications','candidates')
                      AND column_name ILIKE '%classification%'
                    """
                )
                permanent_columns = int(cur.fetchone()["count"])
        require("no_permanent_candidate_table_columns", permanent_columns == 0)

        view_name = f"{PREFIX} Technology High"
        code, saved = http(
            "POST",
            "/dashboard/prehire/candidates/saved-views",
            headers,
            {
                "name": view_name,
                "filters": {
                    "classification_node_ids": ["fn.technology"],
                    "classification_confidence": ["High"],
                    "classification_authority": "confirmed_or_ai",
                },
            },
        )
        require("classification_saved_view_created", code == 200 and saved.get("ok"), saved)
        code, listed = http("GET", "/dashboard/prehire/candidates/saved-views", headers)
        saved_rows = listed.get("views") or []
        require(
            "classification_saved_view_roundtrip",
            code == 200
            and any(
                row.get("name") == view_name
                and "fn.technology" in ((row.get("filters") or {}).get("classification_node_ids") or [])
                for row in saved_rows
            ),
            listed,
        )
        query = urllib.parse.urlencode(
            {"view": "talent_pool", "q": "TPC Canary Synthetic", "limit": 100}
        )
        code, candidates = http("GET", f"/dashboard/prehire/applications?{query}", headers)
        candidate_rows = candidates.get("applications") or candidates.get("items") or []
        require(
            "unified_candidates_search_keeps_canary_rows",
            code == 200 and len(candidate_rows) >= len(FIXTURES),
            {"code": code, "count": len(candidate_rows), "keys": sorted(candidates.keys())},
        )

        held = {
            "app_key": technology_key,
            "company_code": COMPANY,
            "status": "needs_role",
            "data_source": "production_canary",
            "raw_json": {"synthetic": True},
        }
        held_decision = communication_authority.evaluate_candidate_communication_authority(
            held,
            expected_company_code=COMPANY,
            kind="notify",
        )
        require("held_communication_authority_fail_closed", not held_decision.get("allowed"), held_decision)
        outbound_before = snapshot()["outbound_delivery_events"]
        code, notify = http(
            "POST",
            f"/dashboard/prehire/applications/{technology_key}/notify",
            headers,
            {"channel": "whatsapp", "confirm": True},
        )
        require("held_notify_route_fail_closed", code in {403, 404, 409, 422}, {"code": code, "body": notify})
        require("held_notify_no_outbound", snapshot()["outbound_delivery_events"] == outbound_before)

        for name, path, body in (
            ("shortlist", f"/dashboard/prehire/applications/{technology_key}/shortlist", {"confirm": True}),
            ("reject", f"/dashboard/prehire/applications/{technology_key}/reject", {"confirm": True}),
            ("intake_admit", f"/dashboard/prehire/applications/{technology_key}/intake-admit", {"position_code": "NOPE", "confirm": True}),
            ("hire", f"/dashboard/prehire/applications/{technology_key}/hire", {"confirm": True}),
        ):
            code, response = http("POST", path, headers, body)
            require(f"classification_cannot_{name}", code in {403, 404, 405, 409, 422}, {"code": code, "body": response})

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS count FROM applications
                    WHERE company_code=%s AND app_key LIKE %s
                      AND (status <> 'needs_role' OR COALESCE(position_code,'') <> '')
                    """,
                    (COMPANY, f"{PREFIX}%"),
                )
                mutated_apps = int(cur.fetchone()["count"])
        require("no_job_or_lifecycle_assignment", mutated_apps == 0)

        feature_endpoint = next(
            route.endpoint
            for route in app.app.routes
            if getattr(route, "path", None) == "/dashboard/prehire/classification/taxonomy"
            and "GET" in getattr(route, "methods", set())
        )
        try:
            feature_endpoint(context={"company_code": "EXTERNAL"})
        except app.HTTPException as exc:
            require(
                "cross_tenant_classification_fails_closed",
                exc.status_code == 404
                and isinstance(exc.detail, dict)
                and exc.detail.get("error") == "talent_pool_classification_disabled",
                exc.detail,
            )
        else:
            require("cross_tenant_classification_fails_closed", False, "unexpected success")

        protected_after = snapshot()
        require(
            "no_ocr_extraction_embedding_lifecycle_job_ranking_outbound_fact_mutation",
            protected_after == baseline,
            {"before": baseline, "after": protected_after},
        )

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS count FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
                run_count = int(cur.fetchone()["count"])
                cur.execute(
                    "SELECT status,count(*) AS count FROM candidate_classification_runs WHERE app_key LIKE %s GROUP BY status",
                    (f"{PREFIX}%",),
                )
                run_states = {row["status"]: int(row["count"]) for row in cur.fetchall()}
                cur.execute(
                    "SELECT action,count(*) AS count FROM candidate_classification_review_events WHERE app_key LIKE %s GROUP BY action",
                    (f"{PREFIX}%",),
                )
                review_metrics = {row["action"]: int(row["count"]) for row in cur.fetchall()}
        technology_count = sum("fn.technology" in row["node_ids"] for row in outcomes.values())
        needs_count = sum(row["status"] == tpc.STATE_NEEDS_REVIEW for row in outcomes.values())
        unclassified_count = sum(row["status"] == tpc.STATE_UNCLASSIFIED for row in outcomes.values())
        monitoring = {
            "fixture_count": len(outcomes),
            "run_count": run_count,
            "success_count": successes,
            "failure_count": failures,
            "run_states": run_states,
            "latency_ms": {
                "min": min(latencies),
                "max": max(latencies),
                "mean": round(statistics.fmean(latencies), 2),
                "median": round(statistics.median(latencies), 2),
            },
            "technology_suggestion_count": technology_count,
            "technology_suggestion_rate": round(technology_count / len(outcomes), 4),
            "needs_review_count": needs_count,
            "needs_review_rate": round(needs_count / len(outcomes), 4),
            "unclassified_count": unclassified_count,
            "unclassified_rate": round(unclassified_count / len(outcomes), 4),
            "hr_actions": review_metrics,
            "ocr_trigger_count": 0,
            "worker_start_count": 0,
            "protected_mutation_count": 0,
        }

        write_ux_html(outcomes, {**profiles, "technology": profile_after}, saved)

        # Rollback proof: UI/manual/tenant disappear while Unified Candidates and history remain.
        set_flags(tenants="", schema="off", manual="off", ui="off")
        headers_off = mint()
        code, feature_off = http("GET", "/dashboard/prehire/classification/feature", headers_off)
        require("rollback_classification_feature_off", code == 200 and not feature_off.get("enabled_for_company"))
        code, hidden = http(
            "GET",
            f"/dashboard/prehire/applications/{technology_key}/classification",
            headers_off,
        )
        require("rollback_classification_ui_disappears", code == 404, hidden)
        code, candidates_off = http("GET", f"/dashboard/prehire/applications?{query}", headers_off)
        require("rollback_unified_candidates_healthy", code == 200)
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS count FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
                history_during_off = int(cur.fetchone()["count"])
        require("rollback_history_preserved", history_during_off == run_count)

        set_flags(tenants=COMPANY, schema="on", manual="on", ui="on")
        headers = mint()
        code, feature_on = http("GET", "/dashboard/prehire/classification/feature", headers)
        require("reenable_wathefni_only", code == 200 and feature_on.get("enabled_for_company"))
        code, restored = http(
            "GET",
            f"/dashboard/prehire/applications/{technology_key}/classification",
            headers,
        )
        require(
            "reenable_returns_without_rewrite",
            code == 200
            and restored.get("ok")
            and (restored.get("classification") or {}).get("classifier_version") == tpc.CLASSIFIER_VERSION,
        )
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS count FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
                require("reenable_run_count_unchanged", int(cur.fetchone()["count"]) == run_count)

        removed = cleanup()
        residual = sidecar_counts()
        require("zero_synthetic_classification_residue", all(value == 0 for value in residual.values()), residual)
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS count FROM applications WHERE app_key LIKE %s",
                    (f"{PREFIX}%",),
                )
                left_apps = int(cur.fetchone()["count"])
                cur.execute(
                    "SELECT count(*) AS count FROM candidates WHERE phone LIKE %s",
                    (f"imp-{PREFIX.lower()}-%",),
                )
                left_candidates = int(cur.fetchone()["count"])
        require("zero_synthetic_candidate_residue", left_apps == 0 and left_candidates == 0)
        require("protected_state_restored_after_cleanup", snapshot() == baseline)
        final_feature = tpc.feature_status(COMPANY)
        require(
            "final_wathefni_only_workers_off",
            final_feature["enabled_for_company"]
            and final_feature["allowed_tenants"] == [COMPANY]
            and not final_feature["workers_enabled"],
            final_feature,
        )
        leave_enabled = True
        report = {
            "prefix": PREFIX,
            "marker": MARKER,
            "classifier_version": tpc.CLASSIFIER_VERSION,
            "classifier_sha256": EXPECTED_CLASSIFIER_SHA,
            "outcomes": outcomes,
            "review_results": review_results,
            "run_history": run_history,
            "profiles": profiles,
            "saved_view": saved,
            "monitoring": monitoring,
            "protected_before": baseline,
            "protected_after": protected_after,
            "cleanup": removed,
            "residual": residual,
            "flag_final": final_feature,
        }
    except Exception as exc:
        record("unhandled_canary_error", False, f"{type(exc).__name__}:{exc}")
    finally:
        if not leave_enabled:
            try:
                cleanup()
            finally:
                set_flags(tenants="", schema="off", manual="off", ui="off")

    failed = [row for row in RESULTS if not row["pass"]]
    report.update(
        {
            "pass_count": sum(row["pass"] for row in RESULTS),
            "fail_count": len(failed),
            "results": RESULTS,
            "failed": failed,
            "verdict": "GO_INTERNAL_CANARY" if not failed and leave_enabled else "NO_GO",
        }
    )
    EVIDENCE.joinpath("production-canary-qualification.json").write_text(
        json.dumps(report, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "pass": report["pass_count"],
                "fail": report["fail_count"],
                "evidence": str(EVIDENCE),
            },
            indent=2,
        )
    )
    return 0 if report["verdict"] == "GO_INTERNAL_CANARY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
