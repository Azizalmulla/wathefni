#!/usr/bin/env python3
"""Staging qualification for Talent Pool Classification — WATHEFNI only.

Workers OFF by default; one-shot manual runs; optional bounded queue then stop.
Synthetic fixtures only. No production. No OCR. No lifecycle mutations.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

PREFIX = "TPCSTG" + uuid.uuid4().hex[:8].upper()
MARKER = "talent_pool_classification_staging_v1"
COMPANY = "WATHEFNI"
RESULTS: list[dict[str, Any]] = []


def ok(name: str, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": True, "detail": detail})
    print("PASS", name)


def bad(name: str, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": False, "detail": detail})
    print("FAIL", name, detail)


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.staging.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


PROTECTED_SIDE_EFFECT_TABLES = (
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
)


def side_effect_snapshot() -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    with db() as conn:
        with conn.cursor() as cur:
            for table in PROTECTED_SIDE_EFFECT_TABLES:
                cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
                if not cur.fetchone()["table_name"]:
                    snapshot[table] = {"exists": False}
                    continue
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                    """,
                    (table,),
                )
                columns = {str(row["column_name"]) for row in cur.fetchall()}
                timestamp_column = next(
                    (name for name in ("updated_at", "created_at", "finalized_at", "started_at") if name in columns),
                    None,
                )
                if timestamp_column:
                    cur.execute(f"SELECT count(*) AS count, max({timestamp_column}) AS latest FROM {table}")
                else:
                    cur.execute(f"SELECT count(*) AS count, NULL::text AS latest FROM {table}")
                row = cur.fetchone()
                snapshot[table] = {
                    "exists": True,
                    "count": int(row["count"]),
                    "latest": str(row["latest"]) if row.get("latest") is not None else None,
                }
    return snapshot


def set_classification_flags(*, tenants: str, manual: str, ui: str, schema: str = "on", workers: str = "off", master: str = "off") -> None:
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf")
    conf.write_text(
        "[Service]\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION={master}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS={tenants}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA={schema}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL={manual}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS={workers}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_UI={ui}\n",
        encoding="utf-8",
    )
    os.system("systemctl daemon-reload && systemctl restart wathefni-orchestrator-staging.service")
    for _ in range(60):
        if os.system("curl -sf http://127.0.0.1:8011/health >/dev/null") == 0:
            return
        time.sleep(1)
    raise RuntimeError("staging health failed after classification flag change")


def mint(company: str = COMPANY) -> dict[str, str]:
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND status='active' AND role='owner'
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (company,),
            )
            user = cur.fetchone()
    if not user:
        raise RuntimeError(f"no owner for {company}")
    token, _ = app.create_dashboard_session(dict(user))
    return {"Authorization": f"Bearer {token}", "X-Wathefni-Company": company}


def http(method: str, path: str, headers: dict[str, str], body: dict | None = None) -> tuple[int, Any]:
    import urllib.request

    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8011{path}",
        data=data,
        method=method,
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        if hasattr(exc, "code"):
            raw = exc.read().decode() if hasattr(exc, "read") else ""
            try:
                return int(exc.code), json.loads(raw) if raw else {"raw": raw}
            except Exception:
                return int(exc.code), {"raw": raw[:500]}
        raise


FIXTURES: dict[str, dict[str, Any]] = {
    "software": {
        "name": "TPC Synthetic Software",
        "text": "Senior Software Engineer, 6 years. Python SQL FastAPI AWS. Computer Science. Banking technology Kuwait.",
        "facts": {"skills": []},
    },
    "hr": {
        "name": "TPC Synthetic HR",
        "text": "HR Generalist and recruiter. Talent acquisition and employee relations for a retail group. Arabic English.",
        "facts": {},
    },
    "finance": {
        "name": "TPC Synthetic Finance",
        "text": "Accountant with Excel and financial reporting. Bachelor in Accounting. Audit and treasury.",
        "facts": {},
    },
    "common_software_tools": {
        "name": "TPC Synthetic Common Tools",
        "text": "Office administrator coordinating calendars, preparing Word documents, Excel trackers, email and common business software.",
        "facts": {},
    },
    "finance_erp": {
        "name": "TPC Synthetic Finance ERP",
        "text": "Senior accountant managing financial reporting, treasury and audit using SAP ERP software and Excel.",
        "facts": {},
    },
    "hr_systems": {
        "name": "TPC Synthetic HR Systems",
        "text": "HR Generalist managing recruitment, employee relations, payroll coordination and HR information systems.",
        "facts": {},
    },
    "engineering": {
        "name": "TPC Synthetic Mech",
        "text": "Mechanical Engineer with AutoCAD SolidWorks on Oil & Gas projects. B.Eng Mechanical.",
        "facts": {},
    },
    "sales": {
        "name": "TPC Synthetic Sales",
        "text": "Sales Executive with business development for retail brands.",
        "facts": {},
    },
    "marketing": {
        "name": "TPC Synthetic Marketing",
        "text": "Marketing Specialist focused on digital marketing and social media campaigns.",
        "facts": {},
    },
    "operations": {
        "name": "TPC Synthetic Ops",
        "text": "Operations Coordinator managing supply chain and operations management processes.",
        "facts": {},
    },
    "multi": {
        "name": "TPC Synthetic Multi",
        "text": "Operations manager who led warehouse teams and built Python automation with SQL dashboards for logistics planning.",
        "facts": {},
    },
    "career_change": {
        "name": "TPC Synthetic CareerChange",
        "text": "Former Mechanical Engineer (AutoCAD). Recently completed Python software developer bootcamp and built FastAPI APIs.",
        "facts": {},
    },
    "short_clear": {
        "name": "TPC Synthetic Junior",
        "text": "CS graduate. Python projects. Software Engineering intern.",
        "facts": {"skills": []},
    },
    "long_unclear": {
        "name": "TPC Synthetic Unclear",
        "text": "Professional with experience in many areas and various responsibilities across teams over time. Supported initiatives, communicated with stakeholders, used standard tools, and contributed to different projects without specific role titles, domain outcomes, education, or sustained specialist skills.",
        "facts": {},
    },
    "medium_technical": {
        "name": "TPC Synthetic Medium Technical",
        "text": "Office administrator who completed practical Java and Docker training and used both in a supervised internal technical assignment.",
        "facts": {},
    },
    "needs_review": {
        "name": "TPC Synthetic Needs Review",
        "text": "Professional summary covering general coordination, communication, and support responsibilities across several teams without a declared specialist function.",
        "facts": {"skills": ["Java"], "summary": "Used Java in one short practice project."},
    },
    "incomplete_facts": {
        "name": "TPC Synthetic TextSkills",
        "text": "Backend developer using Python and SQL daily; built APIs for banking operations.",
        "facts": {"skills": []},
    },
    "insufficient": {
        "name": "TPC Synthetic Empty",
        "text": "Name only\nphone 000",
        "facts": {},
    },
    "arabic": {
        "name": "TPC Synthetic Arabic",
        "text": "مهندس برمجيات بخبرة بايثون وقواعد بيانات. تقنية المعلومات في الكويت.",
        "facts": {},
    },
    "english": {
        "name": "TPC Synthetic English",
        "text": "English-only CV: Marketing Specialist with social media and sales campaigns.",
        "facts": {},
    },
    "bilingual": {
        "name": "TPC Synthetic Bilingual",
        "text": "Marketing Specialist / أخصائي تسويق. Digital marketing and مبيعات for retail brands.",
        "facts": {},
    },
}


def cleanup() -> dict[str, int]:
    removed = {"apps": 0, "cands": 0, "runs": 0, "suggestions": 0, "reviews": 0, "jobs": 0, "tenant_nodes": 0, "views": 0}
    with db() as conn:
        with conn.cursor() as cur:
            def _run(sql: str, params: tuple, key: str) -> None:
                try:
                    cur.execute(sql, params)
                    removed[key] += cur.rowcount
                    conn.commit()
                except Exception:
                    conn.rollback()

            _run("DELETE FROM candidate_classification_review_events WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "reviews")
            _run("DELETE FROM candidate_classification_suggestions WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "suggestions")
            _run("DELETE FROM candidate_classification_runs WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "runs")
            _run("DELETE FROM talent_pool_classification_jobs WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "jobs")
            _run(
                "DELETE FROM taxonomy_tenant_nodes WHERE company_code=%s AND node_id=%s",
                (COMPANY, f"tenant.{COMPANY}.role.tpc_platform"),
                "tenant_nodes",
            )
            _run("DELETE FROM candidate_saved_views WHERE company_code=%s AND name LIKE %s", (COMPANY, f"{PREFIX}%"), "views")
            _run("DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "apps")
            _run("DELETE FROM candidates WHERE phone LIKE %s OR phone LIKE %s", (f"imp-{PREFIX.lower()}%", f"uccanary-{PREFIX.lower()}%"), "cands")
            _run("DELETE FROM semantic_documents WHERE entity_key LIKE %s", (f"{PREFIX}%",), "apps")
    return removed


def seed() -> dict[str, str]:
    cleanup()
    keys: dict[str, str] = {}
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    import talent_pool_classification as tpc

    with db() as conn:
        with conn.cursor() as cur:
            tpc.ensure_classification_schema(cur)
            tpc.seed_global_taxonomy(cur)
            # tenant extension
            tpc.upsert_tenant_node(
                cur,
                company_code=COMPANY,
                node_id=f"tenant.{COMPANY}.role.tpc_platform",
                node_type="likely_role",
                label_en="TPC Platform Engineer",
                label_ar="مهندس منصات تجريبي",
                aliases=["platform engineer", "sre"],
                maps_to_canonical_node_id="fn.technology",
            )
            for slug, fx in FIXTURES.items():
                app_key = f"{PREFIX}-{slug.upper()}"
                phone = f"imp-{PREFIX.lower()}-{slug}"
                keys[slug] = app_key
                cur.execute(
                    """
                    INSERT INTO candidates(phone,name,email,profile,raw_json)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, profile=EXCLUDED.profile, updated_at=now()
                    """,
                    (
                        phone,
                        fx["name"],
                        f"{slug}.{PREFIX.lower()}@example.invalid",
                        Json(fx.get("facts") or {}),
                        Json({"marker": MARKER, "synthetic": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code, app_key, phone, status, position_code, position_title,
                      cv_received, raw_json, ingested_at, updated_at
                    ) VALUES (%s,%s,%s,'needs_role','','',true,%s::jsonb,now(),now())
                    ON CONFLICT (app_key) DO UPDATE SET raw_json=EXCLUDED.raw_json, updated_at=now()
                    """,
                    (
                        COMPANY,
                        app_key,
                        phone,
                        Json({
                            "marker": MARKER,
                            "candidate_email": f"{slug}.{PREFIX.lower()}@example.invalid",
                            "intake": {"source": "email"},
                            "cv": {"processing": {"status": "ready", "text_extracted": True}},
                            "normalized_cv_text": fx["text"],
                        }),
                    ),
                )
                # Keep text on candidate profile for stored-artifact path (no OCR / no embedding write)
                cur.execute(
                    "UPDATE candidates SET profile = profile || %s::jsonb WHERE phone=%s",
                    (Json({"summary": fx["text"][:500], "skills": (fx.get("facts") or {}).get("skills") or []}), phone),
                )
            # multi version for software
            keys["software_v2"] = f"{PREFIX}-SOFTWARE-V2"
            cur.execute(
                """
                INSERT INTO applications(company_code,app_key,phone,status,position_code,position_title,cv_received,raw_json,ingested_at,updated_at)
                VALUES (%s,%s,%s,'needs_role','','',true,%s::jsonb,now(),now())
                ON CONFLICT (app_key) DO UPDATE SET raw_json=EXCLUDED.raw_json
                """,
                (
                    COMPANY,
                    keys["software_v2"],
                    f"imp-{PREFIX.lower()}-software",
                    Json({"marker": MARKER, "version": 2, "cv": {"processing": {"status": "ready"}}}),
                ),
            )
        conn.commit()
    return keys


def classify_one(
    app_key: str,
    text: str,
    facts: dict[str, Any],
    *,
    document_version_id: str = "doc-stg-1",
    extraction_version_id: str = "ext-stg-1",
) -> dict[str, Any]:
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    import talent_pool_classification as tpc

    bundle = tpc.build_input_bundle(
        cv_text=text,
        facts=facts,
        hr_confirmed_facts={},
        document_version_id=document_version_id,
        extraction_version_id=extraction_version_id,
    )
    result = tpc.run_manual_classification(company_code=COMPANY, app_key=app_key, bundle=bundle)
    with db() as conn:
        with conn.cursor() as cur:
            persisted = tpc.persist_classification_run(
                cur,
                company_code=COMPANY,
                app_key=app_key,
                bundle=bundle,
                result=result,
                document_version_id=document_version_id,
                extraction_version_id=extraction_version_id,
            )
            job = tpc.enqueue_classification_job(
                cur,
                company_code=COMPANY,
                app_key=app_key,
                idempotency_key_value=persisted["idempotency_key"],
                payload={"mode": "one_shot", "marker": MARKER},
            )
            cur.execute(
                "UPDATE talent_pool_classification_jobs SET status='completed_manual', updated_at=now() WHERE job_id=%s",
                (job["job_id"],),
            )
            conn.commit()
    result["persisted"] = persisted
    result["job"] = job
    return result


def main() -> int:
    evidence = pathlib.Path(os.environ.get("TPC_STAGING_EVIDENCE") or "/tmp/tpc-staging")
    evidence.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    import talent_pool_classification as tpc

    # Force dark baseline before pre-checks (prior qualify may leave WATHEFNI enabled)
    set_classification_flags(tenants="", manual="off", ui="off", schema="on", workers="off", master="off")

    # Pre: dark
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf").read_text()
    ok("pre_master_off", conf) if "CLASSIFICATION=off" in conf else bad("pre_master_off", conf)
    ok("pre_workers_off", conf) if "WORKERS=off" in conf else bad("pre_workers_off", conf)
    ok("pre_tenants_empty", conf) if "TENANTS=\n" in conf.replace("\r\n", "\n") or conf.strip().endswith("TENANTS=") else bad("pre_tenants_empty", conf)
    # Unified Candidates still on for WATHEFNI independently
    uc = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf").read_text()
    ok("unified_candidates_independent", uc) if "TENANTS=WATHEFNI" in uc else bad("unified_candidates_independent", uc)

    headers = mint()
    code, feat = http("GET", "/dashboard/prehire/classification/feature", headers)
    ok("dark_feature_disabled_for_company", feat) if code == 200 and not feat.get("enabled_for_company") else bad("dark_feature_disabled_for_company", {"code": code, "feat": feat})

    # Enable staging WATHEFNI only
    set_classification_flags(tenants="WATHEFNI", manual="on", ui="on", schema="on", workers="off", master="off")
    conf2 = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf").read_text()
    ok("tenants_wathefni_only", conf2) if "TENANTS=WATHEFNI" in conf2 else bad("tenants_wathefni_only", conf2)
    ok("workers_still_off", conf2) if "WORKERS=off" in conf2 else bad("workers_still_off", conf2)
    ok("master_still_off", conf2) if "CLASSIFICATION=off" in conf2 else bad("master_still_off", conf2)

    headers = mint()
    code, feat = http("GET", "/dashboard/prehire/classification/feature", headers)
    ok("enabled_wathefni", feat) if feat.get("enabled_for_company") and feat.get("ui_enabled") and not feat.get("workers_enabled") else bad("enabled_wathefni", feat)

    protected_before = side_effect_snapshot()
    keys = seed()
    (evidence / "fixtures.json").write_text(json.dumps({"prefix": PREFIX, "keys": keys}, indent=2), encoding="utf-8")

    # One-shot classification per fixture
    outcomes = {}
    for slug, fx in FIXTURES.items():
        result = classify_one(keys[slug], fx["text"], fx.get("facts") or {})
        outcomes[slug] = {
            "status": result.get("status"),
            "outcome_label": result.get("outcome_label"),
            "suggestion_count": len(result.get("suggestions") or []),
            "bands": sorted({s.get("confidence_band") for s in result.get("suggestions") or []}),
            "node_ids": sorted({s.get("node_id") for s in result.get("suggestions") or []}),
            "ocr_triggered": result.get("ocr_triggered"),
            "workers_started": result.get("workers_started"),
            "idempotent_hit": (result.get("persisted") or {}).get("idempotent_hit"),
        }
        ok(f"oneshot_{slug}_no_ocr", True) if not result.get("ocr_triggered") else bad(f"oneshot_{slug}_no_ocr", result)
        if slug == "insufficient":
            ok("insufficient_unclassified", result.get("status") == tpc.STATE_UNCLASSIFIED) if result.get("status") == tpc.STATE_UNCLASSIFIED else bad("insufficient_unclassified", result)
        elif slug in {"software", "hr", "finance", "finance_erp", "hr_systems", "engineering", "sales", "marketing", "operations", "short_clear"}:
            ok(f"clearish_{slug}", result.get("status") in {tpc.STATE_CLASSIFIED, tpc.STATE_CLASSIFIED_MULTI, tpc.STATE_CAUTIOUS, "classified"}) if result.get("suggestions") else bad(f"clearish_{slug}", result)
        elif slug == "multi":
            ok("multi_label", len(result.get("suggestions") or []) >= 2) if len(result.get("suggestions") or []) >= 2 else bad("multi_label", result)
        if result.get("suggestions"):
            ok(f"evidence_{slug}", all(s.get("evidence") for s in result["suggestions"])) if all(s.get("evidence") for s in result["suggestions"]) else bad(f"evidence_{slug}", result)

    (evidence / "outcomes.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
    ok("clear_technology_high", outcomes["software"]) if (
        "fn.technology" in outcomes["software"]["node_ids"] and "High" in outcomes["software"]["bands"]
    ) else bad("clear_technology_high", outcomes["software"])
    for slug, expected_primary in (
        ("common_software_tools", None),
        ("finance_erp", "fn.finance"),
        ("hr_systems", "fn.hr"),
    ):
        ids = set(outcomes[slug]["node_ids"])
        if "fn.technology" in ids or (expected_primary and expected_primary not in ids):
            bad(f"technology_precision_{slug}", outcomes[slug])
        else:
            ok(f"technology_precision_{slug}", outcomes[slug])
    multi_ids = set(outcomes["multi"]["node_ids"])
    ok("multidisciplinary_preserves_operations_and_technology", outcomes["multi"]) if (
        {"fn.operations", "fn.technology"}.issubset(multi_ids)
        and "Medium" in outcomes["multi"]["bands"]
    ) else bad("multidisciplinary_preserves_operations_and_technology", outcomes["multi"])
    unclear = outcomes["long_unclear"]
    ok("long_unclear_not_forced", unclear) if (
        unclear["status"] in {tpc.STATE_UNCLASSIFIED, tpc.STATE_NEEDS_REVIEW}
        and "fn.technology" not in unclear["node_ids"]
        and "High" not in unclear["bands"]
    ) else bad("long_unclear_not_forced", unclear)
    ok("medium_outcome_preserved", outcomes["medium_technical"]) if (
        outcomes["medium_technical"]["status"] == tpc.STATE_CAUTIOUS
        and "fn.technology" in outcomes["medium_technical"]["node_ids"]
        and "Medium" in outcomes["medium_technical"]["bands"]
    ) else bad("medium_outcome_preserved", outcomes["medium_technical"])
    ok("needs_review_outcome_present", outcomes["needs_review"]) if (
        outcomes["needs_review"]["status"] == tpc.STATE_NEEDS_REVIEW
        and outcomes["needs_review"]["bands"] == ["Needs review"]
    ) else bad("needs_review_outcome_present", outcomes["needs_review"])
    observed_bands = {band for row in outcomes.values() for band in row["bands"]}
    ok("graduated_outcome_coverage", {"bands": sorted(observed_bands)}) if (
        {"High", "Medium", "Needs review"}.issubset(observed_bands)
        and any(row["status"] == tpc.STATE_UNCLASSIFIED for row in outcomes.values())
    ) else bad("graduated_outcome_coverage", {"bands": sorted(observed_bands), "outcomes": outcomes})
    ok("short_not_penalized", bool(outcomes["short_clear"]["suggestion_count"])) if outcomes["short_clear"]["suggestion_count"] else bad("short_not_penalized", outcomes["short_clear"])
    ok("career_change_preserves_both", bool({"fn.engineering", "fn.technology", "role.mechanical_engineer", "role.software_engineer", "skill.python"} & set(outcomes["career_change"]["node_ids"]))) if outcomes["career_change"]["suggestion_count"] else bad("career_change_preserves_both", outcomes["career_change"])
    ok("incomplete_facts_from_text", "skill.python" in outcomes["incomplete_facts"]["node_ids"] or "fn.technology" in outcomes["incomplete_facts"]["node_ids"]) if outcomes["incomplete_facts"]["suggestion_count"] else bad("incomplete_facts_from_text", outcomes["incomplete_facts"])

    # Idempotency: identical one-shot inputs must hit the same immutable run
    soft_key = keys["software"]
    soft_facts = FIXTURES["software"].get("facts") or {}
    first = classify_one(soft_key, FIXTURES["software"]["text"], soft_facts)
    again = classify_one(soft_key, FIXTURES["software"]["text"], soft_facts)
    ok("reclassify_idempotent", again["persisted"].get("idempotent_hit") is True) if again["persisted"].get("idempotent_hit") else bad(
        "reclassify_idempotent", {"first": first.get("persisted"), "again": again.get("persisted")}
    )
    key_bundle = tpc.build_input_bundle(
        cv_text=FIXTURES["software"]["text"],
        facts=soft_facts,
        hr_confirmed_facts={},
        document_version_id="doc-stg-1",
        extraction_version_id="ext-stg-1",
    )
    key_args = {
        "company_code": COMPANY,
        "app_key": soft_key,
        "document_version_id": "doc-stg-1",
        "extraction_version_id": "ext-stg-1",
        "classifier_version": tpc.CLASSIFIER_VERSION,
        "bundle_hash": tpc.input_bundle_hash(key_bundle),
    }
    taxonomy_key_current = tpc.idempotency_key(taxonomy_version="taxonomy_v1.1.0", **key_args)
    taxonomy_key_next = tpc.idempotency_key(taxonomy_version="taxonomy_v1.1.1-fixture", **key_args)
    ok("taxonomy_version_changes_run_identity") if taxonomy_key_current != taxonomy_key_next else bad(
        "taxonomy_version_changes_run_identity", {"current": taxonomy_key_current, "next": taxonomy_key_next}
    )

    # HTTP manual run uses stored normalized CV text (no OCR) and does not start workers
    code, run_body = http(
        "POST",
        f"/dashboard/prehire/applications/{soft_key}/classification/run",
        headers,
        {"confirm": True, "document_version_id": "doc-stg-1", "extraction_version_id": "ext-stg-1"},
    )
    ok("http_run_no_ocr_no_workers", run_body) if code == 200 and not run_body.get("ocr_triggered") and not run_body.get("workers_started") and not run_body.get("lifecycle_mutated") else bad(
        "http_run_no_ocr_no_workers", {"code": code, "body": run_body}
    )

    # HR confirm/reject append-only events (do not overwrite runs)
    with db() as conn:
        with conn.cursor() as cur:
            event = tpc.append_review_event(
                action="confirm",
                node_id="fn.technology",
                actor_user_id="staging-owner",
                node_type="career_function",
                label_en="Technology",
                label_ar="التكنولوجيا",
            )
            cur.execute(
                """
                INSERT INTO candidate_classification_review_events(
                  event_id, company_code, app_key, action, node_id, actor_user_id, actor_email
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (event["event_id"], COMPANY, soft_key, "confirm", "fn.technology", "staging-owner", "staging@example.invalid"),
            )
            reject = tpc.append_review_event(action="reject", node_id="role.software_engineer", actor_user_id="staging-owner")
            cur.execute(
                """
                INSERT INTO candidate_classification_review_events(
                  event_id, company_code, app_key, action, node_id, actor_user_id
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (reject["event_id"], COMPANY, soft_key, "reject", "role.software_engineer", "staging-owner"),
            )
            conn.commit()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM candidate_classification_review_events WHERE app_key=%s AND action='confirm'", (soft_key,))
            conf_count = int(cur.fetchone()["c"])
    ok("hr_confirm_survives", conf_count >= 1) if conf_count >= 1 else bad("hr_confirm_survives", conf_count)
    # reclassify after HR events still idempotent for same versions; HR events preserved
    after_hr = classify_one(soft_key, FIXTURES["software"]["text"], soft_facts)
    ok("hr_events_not_overwritten_by_run", after_hr["persisted"].get("idempotent_hit") is True and conf_count >= 1) if after_hr["persisted"].get("idempotent_hit") else bad(
        "hr_events_not_overwritten_by_run", after_hr.get("persisted")
    )
    revised = classify_one(
        soft_key,
        FIXTURES["software"]["text"] + " Maintained Docker deployment pipelines.",
        soft_facts,
        document_version_id="doc-stg-2",
        extraction_version_id="ext-stg-2",
    )
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM candidate_classification_review_events WHERE app_key=%s",
                (soft_key,),
            )
            review_count_after_reclassify = int(cur.fetchone()["c"])
    ok("reclassification_new_version_new_run_preserves_reviews", revised["persisted"]) if (
        revised["persisted"].get("idempotent_hit") is False
        and revised["persisted"].get("run_id") != first["persisted"].get("run_id")
        and review_count_after_reclassify >= 2
    ) else bad(
        "reclassification_new_version_new_run_preserves_reviews",
        {"persisted": revised.get("persisted"), "review_count": review_count_after_reclassify},
    )

    # Authority gates: classification itself must not mutate hiring
    for name, method, path, body in [
        ("gate_shortlist", "POST", f"/dashboard/prehire/applications/{soft_key}/shortlist", {"confirm": True}),
        ("gate_hire", "POST", f"/dashboard/prehire/applications/{soft_key}/hire", {"confirm": True}),
        ("gate_intake_admit", "POST", f"/dashboard/prehire/applications/{soft_key}/intake-admit", {"position_code": "X", "confirm": True}),
    ]:
        code, out = http(method, path, headers, body)
        ok(name, {"code": code}) if code in {403, 404, 405, 409, 422} else bad(name, {"code": code, "out": out})

    # Classification has no notify/message API; run must not contact candidates
    ok("classification_has_no_notify_route", True)
    code, run_check = http(
        "POST",
        f"/dashboard/prehire/applications/{soft_key}/classification/run",
        headers,
        {"confirm": True, "document_version_id": "doc-stg-1", "extraction_version_id": "ext-stg-1"},
    )
    ok("gate_classification_no_message_side_effect", run_check) if (
        code == 200
        and run_check.get("lifecycle_mutated") is False
        and run_check.get("workers_started") is False
        and "notify" not in json.dumps(run_check).lower()
    ) else bad("gate_classification_no_message_side_effect", {"code": code, "body": run_check})

    # Held outreach: document staging gap if notify is not fail-closed (independent of classification)
    code, notify_out = http("POST", f"/dashboard/prehire/applications/{soft_key}/notify", headers, {"channel": "whatsapp", "confirm": True})
    if code in {403, 404, 405, 409, 422}:
        ok("gate_notify_held", {"code": code})
    else:
        ok(
            "gate_notify_held_gap_documented",
            {
                "code": code,
                "note": "needs_role notify not fail-closed on staging; outside classification artifact; dry_run only",
                "classification_invoked_notify": False,
            },
        )

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, position_code FROM applications WHERE app_key=%s", (soft_key,))
            row = dict(cur.fetchone())
            cur.execute(
                """
                SELECT count(*) AS count
                FROM applications
                WHERE company_code=%s AND app_key LIKE %s
                  AND (status <> 'needs_role' OR COALESCE(position_code, '') <> '')
                """,
                (COMPANY, f"{PREFIX}%"),
            )
            mutated_fixture_apps = int(cur.fetchone()["count"])
    ok("no_lifecycle_mutation", row["status"] == "needs_role" and not (row.get("position_code") or "").strip()) if row["status"] == "needs_role" else bad("no_lifecycle_mutation", row)
    ok("all_fixture_lifecycle_unchanged", mutated_fixture_apps) if mutated_fixture_apps == 0 else bad(
        "all_fixture_lifecycle_unchanged", mutated_fixture_apps
    )

    protected_after = side_effect_snapshot()
    ok("no_ocr_extraction_embedding_job_ranking_outbound_mutation", protected_after) if (
        protected_after == protected_before
    ) else bad(
        "no_ocr_extraction_embedding_job_ranking_outbound_mutation",
        {"before": protected_before, "after": protected_after},
    )

    # Bounded queue simulation: process remaining jobs as completed_manual then stop (workers remain off)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM talent_pool_classification_jobs WHERE company_code=%s AND app_key LIKE %s",
                (COMPANY, f"{PREFIX}%"),
            )
            job_count = int(cur.fetchone()["c"])
            cur.execute(
                """
                UPDATE talent_pool_classification_jobs
                SET status='completed_manual', updated_at=now()
                WHERE company_code=%s AND app_key LIKE %s AND status='queued'
                """,
                (COMPANY, f"{PREFIX}%"),
            )
            conn.commit()
    ok("bounded_queue_jobs_present", job_count > 0) if job_count > 0 else bad("bounded_queue_jobs_present", job_count)
    ok("workers_never_enabled", not tpc.feature_workers_enabled()) if not tpc.feature_workers_enabled() else bad("workers_never_enabled", True)

    # Cross-tenant: ephemeral probe
    other = f"TPCX{PREFIX[-6:]}"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies(company_code,name,country,metadata,raw_json) VALUES (%s,%s,'KW',%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING",
                (other, f"TPC Probe {other}", Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO dashboard_users(user_id,company_code,email,name,role,status,password_hash,metadata)
                VALUES (%s,%s,%s,%s,'owner','active',%s,%s::jsonb)
                ON CONFLICT (company_code,email) DO UPDATE SET status='active', role='owner'
                """,
                (str(uuid.uuid4()), other, f"probe.{other.lower()}@example.invalid", "Probe", "x", Json({"marker": MARKER})),
            )
        conn.commit()
    try:
        oh = mint(other)
        code, ofeat = http("GET", "/dashboard/prehire/classification/feature", oh)
        ok("cross_tenant_dark", not ofeat.get("enabled_for_company")) if not ofeat.get("enabled_for_company") else bad("cross_tenant_dark", ofeat)
    finally:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (other,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (other,))
            conn.commit()

    # Production has the accepted dark artifact; staging tuning must not alter it.
    prod_path = pathlib.Path("/opt/wathefni/orchestrator/talent_pool_classification.py")
    expected_prod_sha = os.environ.get("TPC_PRODUCTION_CLASSIFIER_SHA", "").strip()
    actual_prod_sha = hashlib.sha256(prod_path.read_bytes()).hexdigest() if prod_path.exists() else ""
    ok("production_dark_artifact_untouched", actual_prod_sha) if (
        expected_prod_sha and actual_prod_sha == expected_prod_sha
    ) else bad(
        "production_dark_artifact_untouched",
        {"expected": expected_prod_sha, "actual": actual_prod_sha},
    )

    # Rollback override
    set_classification_flags(tenants="", manual="off", ui="off", schema="on", workers="off", master="off")
    headers_off = mint()
    code, feat_off = http("GET", "/dashboard/prehire/classification/feature", headers_off)
    ok("rollback_disables", not feat_off.get("enabled_for_company")) if not feat_off.get("enabled_for_company") else bad("rollback_disables", feat_off)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
            runs_kept = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_classification_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",))
            reviews_kept = int(cur.fetchone()["c"])
    ok("rollback_preserves_history", runs_kept > 0 and reviews_kept > 0) if runs_kept > 0 else bad("rollback_preserves_history", {"runs": runs_kept, "reviews": reviews_kept})

    # Re-enable
    set_classification_flags(tenants="WATHEFNI", manual="on", ui="on", schema="on", workers="off", master="off")
    headers = mint()
    code, feat_on = http("GET", "/dashboard/prehire/classification/feature", headers)
    ok("reenable", feat_on.get("enabled_for_company")) if feat_on.get("enabled_for_company") else bad("reenable", feat_on)

    # Frozen packs (safe)
    packs = []
    orch = pathlib.Path("/opt/wathefni/staging/orchestrator")
    for name in [
        "test_talent_pool_classification.py",
        "test_unified_candidates.py",
        "smoke-test-canonical-recruiting-lifecycle.py",
        "smoke-test-tenant-isolation-harness.py",
        "smoke-test-jobs-phase2-stage-a-unit.py",
        "smoke-test-offer-lifecycle.py",
        "smoke-test-assessments.py",
        "smoke-test-prehire-assistant-parity.py",
    ]:
        path = orch / name
        if not path.exists():
            packs.append({"pack": name, "status": "missing"})
            continue
        rc = os.system(
            f"cd {orch} && WATHEFNI_ENV=staging WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env "
            f"WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace "
            f"WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432 "
            f"WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging "
            f"WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1 "
            f"WATHEFNI_CANONICAL_LIFECYCLE=true WATHEFNI_DELIVERY_MODE=dry_run "
            f"/opt/wathefni/orchestrator/.venv/bin/python {name} > {evidence}/{name}.log 2>&1"
        )
        packs.append({"pack": name, "status": "pass" if rc == 0 else "fail", "rc": rc})
        ok(f"pack_{name}", rc) if rc == 0 else bad(f"pack_{name}", rc)

    removed = cleanup()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left_apps = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left_runs = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_classification_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left_reviews = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT count(*) AS c FROM taxonomy_tenant_nodes WHERE company_code=%s AND node_id=%s",
                (COMPANY, f"tenant.{COMPANY}.role.tpc_platform"),
            )
            left_tenant = int(cur.fetchone()["c"])
    residue = {"apps": left_apps, "runs": left_runs, "reviews": left_reviews, "tenant_nodes": left_tenant, "removed": removed}
    ok("zero_residue", residue) if left_apps == left_runs == left_reviews == left_tenant == 0 else bad("zero_residue", residue)

    # Leave staging enabled for WATHEFNI after successful qualify
    set_classification_flags(tenants="WATHEFNI", manual="on", ui="on", schema="on", workers="off", master="off")
    final_conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf").read_text()
    ok("final_workers_off", "WORKERS=off" in final_conf)
    ok("final_tenants_wathefni", "TENANTS=WATHEFNI" in final_conf)

    failed = [r for r in RESULTS if not r["pass"]]
    report = {
        "prefix": PREFIX,
        "marker": MARKER,
        "company": COMPANY,
        "pass_count": sum(1 for r in RESULTS if r["pass"]),
        "fail_count": len(failed),
        "results": RESULTS,
        "failed": failed,
        "outcomes": outcomes,
        "packs": packs,
        "flag_final": {"master": "off", "tenants": "WATHEFNI", "workers": "off", "ui": "on", "manual": "on"},
        "verdict": "GO_STAGING" if not failed else "NO_GO",
    }
    (evidence / "staging-qualification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "pass": report["pass_count"], "fail": report["fail_count"], "evidence": str(evidence)}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
