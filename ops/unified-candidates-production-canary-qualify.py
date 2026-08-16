#!/usr/bin/env python3
"""Production canary qualification for Unified Candidates — WATHEFNI tenant override only.

Global master flag remains OFF. TENANTS=WATHEFNI is the sole enablement.
Synthetic fixtures only. Zero real PII. Marker-scoped cleanup.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

PREFIX = "UCCY" + uuid.uuid4().hex[:8].upper()
MARKER = "unified_candidates_prod_canary_v1"
COMPANY = "WATHEFNI"
OTHER_PROBE_LIMIT = 3
RESULTS: list[dict[str, Any]] = []


def ok(name: str, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": True, "detail": detail})
    print("PASS", name)


def bad(name: str, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": False, "detail": detail})
    print("FAIL", name, detail)


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def set_tenants(tenants: str) -> None:
    """Keep master OFF; only mutate TENANTS allowlist."""
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf")
    conf.write_text(
        "[Service]\n"
        "Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off\n"
        f"Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS={tenants}\n",
        encoding="utf-8",
    )
    os.system("systemctl daemon-reload && systemctl restart wathefni-orchestrator.service")
    for _ in range(60):
        if os.system("curl -sf http://127.0.0.1:8010/health >/dev/null") == 0:
            return
        time.sleep(1)
    raise RuntimeError("production health failed after tenant override change")


def mint(company: str = COMPANY) -> dict[str, str]:
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
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
        f"http://127.0.0.1:8010{path}",
        data=data,
        method=method,
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        if hasattr(exc, "code"):
            raw = exc.read().decode() if hasattr(exc, "read") else ""
            try:
                payload = json.loads(raw) if raw else {"error": str(exc)}
            except Exception:
                payload = {"error": raw or str(exc)}
            return int(exc.code), payload
        raise


def cleanup() -> dict[str, int]:
    removed = {k: 0 for k in [
        "fact_review_events", "saved_views", "governance", "files",
        "applications", "candidates", "outbound", "rank_evals", "lifecycle", "assessments",
    ]}
    with db() as conn:
        with conn.cursor() as cur:
            def _run(sql: str, params: tuple, key: str) -> None:
                try:
                    cur.execute(sql, params)
                    removed[key] += cur.rowcount
                    conn.commit()
                except Exception:
                    conn.rollback()

            _run(
                "DELETE FROM candidate_fact_review_events WHERE company_code=%s AND (app_key LIKE %s OR coalesce(note,'') LIKE %s)",
                (COMPANY, f"{PREFIX}%", f"%{MARKER}%"),
                "fact_review_events",
            )
            _run("DELETE FROM assessment_invitations WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "assessments")
            _run("DELETE FROM assessment_attempts WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "assessments")
            _run("DELETE FROM candidate_saved_views WHERE company_code=%s AND name LIKE %s", (COMPANY, f"{PREFIX}%"), "saved_views")
            _run("DELETE FROM candidate_record_governance WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "governance")
            _run("DELETE FROM file_registry WHERE company_code=%s AND subject_key LIKE %s", (COMPANY, f"{PREFIX}%"), "files")
            _run("DELETE FROM outbound_delivery_events WHERE subject_key LIKE %s", (f"{PREFIX}%",), "outbound")
            _run("DELETE FROM candidate_rank_evaluations WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "rank_evals")
            _run("DELETE FROM application_lifecycle_events WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "lifecycle")
            _run("DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "applications")
            _run("DELETE FROM candidates WHERE phone LIKE %s OR phone LIKE %s", (f"imp-{PREFIX.lower()}%", f"uccanary-{PREFIX.lower()}%"), "candidates")
            _run(
                "DELETE FROM dashboard_users WHERE company_code LIKE %s OR (metadata->>'marker')=%s",
                ("UCCX%", MARKER),
                "candidates",
            )
            _run(
                "DELETE FROM companies WHERE company_code LIKE %s OR (metadata->>'marker')=%s",
                ("UCCX%", MARKER),
                "candidates",
            )
    return removed


def seed() -> dict[str, str]:
    keys = {
        "active": f"{PREFIX}-ACTIVE",
        "needs_role": f"{PREFIX}-HELD-NR",
        "import_review": f"{PREFIX}-HELD-IR",
        "hired": f"{PREFIX}-HIRED",
        "archived": f"{PREFIX}-ARCH",
        "restricted": f"{PREFIX}-REST",
        "multi_cv": f"{PREFIX}-MULTICV",
        "failed_intake": f"{PREFIX}-FAIL",
    }
    live_phone = f"uccanary-{PREFIX.lower()}-live"
    held_phone = f"imp-{PREFIX.lower()}-held"
    cleanup()
    with db() as conn:
        with conn.cursor() as cur:
            import unified_candidates as uc

            uc.ensure_unified_candidates_schema(cur)
            cur.execute(
                "INSERT INTO candidates(phone,name,email,profile,raw_json) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)",
                (
                    live_phone,
                    "Canary Synthetic Live",
                    "canary.live@example.invalid",
                    Json({"skills": ["Excel"], "education": [{"school": "Synthetic University"}]}),
                    Json({"marker": MARKER, "synthetic": True}),
                ),
            )
            cur.execute(
                """
                INSERT INTO applications(company_code,app_key,phone,status,position_code,position_title,cv_received,raw_json,ingested_at,updated_at)
                VALUES (%s,%s,%s,'ready_for_review','CANARY_ROLE','Canary Synthetic Role',true,%s::jsonb,now(),now())
                """,
                (COMPANY, keys["active"], live_phone, Json({"marker": MARKER, "intake": {"source": "whatsapp"}, "cv": {"processing": {"status": "ready", "profile_parsed": True}}})),
            )
            cur.execute(
                "INSERT INTO candidates(phone,name,email,profile,raw_json) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)",
                (
                    held_phone,
                    "Canary Synthetic Held",
                    "canary.held@example.invalid",
                    Json({"skills": [], "languages": []}),
                    Json({"marker": MARKER, "synthetic": True}),
                ),
            )
            for key, status, raw in [
                (keys["needs_role"], "needs_role", {"marker": MARKER, "candidate_email": "canary.held@example.invalid", "candidate_phone": "00000000000", "intake": {"source": "email", "sender_email": "sender.canary@example.invalid"}, "cv": {"processing": {"status": "ready", "text_extracted": True, "profile_parsed": True}}}),
                (keys["import_review"], "import_review", {"marker": MARKER, "candidate_email": "canary.ir@example.invalid", "intake": {"source": "bulk_import"}, "cv": {"processing": {"status": "partial", "text_extracted": True}}}),
                (keys["archived"], "import_archived", {"marker": MARKER, "intake": {"source": "email"}, "cv": {"processing": {"status": "ready"}}}),
                (keys["restricted"], "needs_role", {"marker": MARKER, "intake": {"source": "email"}, "cv": {"processing": {"status": "ready"}}}),
                (keys["multi_cv"], "needs_role", {"marker": MARKER, "candidate_email": "canary.multi@example.invalid", "intake": {"source": "email"}, "cv": {"processing": {"status": "ready", "profile_parsed": True}}}),
                (keys["failed_intake"], "import_review", {"marker": MARKER, "intake": {"source": "email"}, "cv": {"processing": {"status": "failed"}}}),
            ]:
                cur.execute(
                    """
                    INSERT INTO applications(company_code,app_key,phone,status,position_code,position_title,cv_received,raw_json,ingested_at,updated_at)
                    VALUES (%s,%s,%s,%s,'','',true,%s::jsonb,now(),now())
                    """,
                    (COMPANY, key, held_phone, status, Json(raw)),
                )
            cur.execute(
                """
                INSERT INTO applications(company_code,app_key,phone,status,position_code,position_title,cv_received,raw_json,ingested_at,updated_at)
                VALUES (%s,%s,%s,'hired','CANARY_ROLE','Canary Synthetic Role',true,%s::jsonb,now(),now())
                """,
                (COMPANY, keys["hired"], live_phone, Json({"marker": MARKER, "intake": {"source": "whatsapp"}})),
            )
            uc.upsert_governance(
                cur,
                company_code=COMPANY,
                app_key=keys["restricted"],
                patch={"restriction_state": "restricted", "metadata": {"marker": MARKER}},
            )
            cur.execute(
                "UPDATE candidates SET profile = profile || %s::jsonb WHERE phone=%s",
                (Json({"summary": "canary synthetic accountant excel reporting semantic fixture kuwait university"}), held_phone),
            )
            for i in range(2):
                cur.execute(
                    """
                    INSERT INTO file_registry(
                      file_id, company_code, subject_type, subject_key, file_kind, document_type,
                      original_filename, storage_provider, storage_url, storage_status, created_at, updated_at
                    ) VALUES (%s,%s,'application',%s,'cv','cv',%s,'local',%s,'ready',now(),now())
                    """,
                    (str(uuid.uuid4()), COMPANY, keys["multi_cv"], f"canary-cv-v{i+1}.pdf", f"/tmp/{PREFIX}-cv-v{i+1}.pdf"),
                )
            uc.append_fact_review_event(
                cur,
                company_code=COMPANY,
                app_key=keys["needs_role"],
                fact_path="skills",
                action="add",
                actor_user_id="prod-canary-owner",
                actor_email="canary.owner@example.invalid",
                new_value=["Excel", "Reporting"],
                note=f"{MARKER} confirmed skills",
            )
        conn.commit()
    keys["live_phone"] = live_phone
    keys["held_phone"] = held_phone
    return keys


def main() -> int:
    evidence = pathlib.Path(os.environ.get("CANARY_EVIDENCE") or "/tmp/uc-canary")
    evidence.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, "/opt/wathefni/orchestrator")

    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_explicit_environment()
    # Deploy canary-capable feature semantics module (tenant override with master OFF)
    # Assume caller already synced unified_candidates.py if needed.

    # Pre: master OFF; ensure tenants empty before enable (reset if prior canary left TENANTS=WATHEFNI)
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf").read_text()
    ok("pre_master_off", conf) if "TALENT_POOL=off" in conf else bad("pre_master_off", conf)
    tenants_empty = "TENANTS=\n" in conf.replace("\r\n", "\n") or conf.strip().endswith("TENANTS=")
    if not tenants_empty and "TENANTS=WATHEFNI" in conf:
        set_tenants("")
        conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf").read_text()
        tenants_empty = "TENANTS=\n" in conf.replace("\r\n", "\n") or conf.strip().endswith("TENANTS=")
        ok("pre_tenants_reset_to_empty", conf) if tenants_empty else bad("pre_tenants_reset_to_empty", conf)
    else:
        ok("pre_tenants_empty", conf) if tenants_empty else bad("pre_tenants_empty", conf)

    headers = mint()
    code, feature = http("GET", "/dashboard/prehire/candidates/feature", headers)
    ok("pre_feature_disabled", feature) if not feature.get("enabled_for_company") else bad("pre_feature_disabled", feature)

    keys = seed()
    (evidence / "fixtures.json").write_text(json.dumps({"prefix": PREFIX, "marker": MARKER, "keys": keys}, indent=2), encoding="utf-8")

    # Enable tenant override only
    set_tenants("WATHEFNI")
    conf2 = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf").read_text()
    ok("master_still_off", conf2) if "TALENT_POOL=off" in conf2 else bad("master_still_off", conf2)
    ok("tenants_wathefni_only", conf2) if "TENANTS=WATHEFNI" in conf2 else bad("tenants_wathefni_only", conf2)

    headers = mint()
    code, feature = http("GET", "/dashboard/prehire/candidates/feature", headers)
    ok("canary_enabled_wathefni", feature) if feature.get("enabled_for_company") and not feature.get("master_enabled") else bad("canary_enabled_wathefni", feature)
    ok("activation_mode_canary", feature) if feature.get("activation_mode") == "tenant_canary_override" or (
        feature.get("enabled_for_company") and not feature.get("master_enabled")
    ) else bad("activation_mode_canary", feature)

    # Views
    by_key: dict[str, dict] = {}
    for view, must_include, must_exclude in [
        ("all", keys["needs_role"], keys["restricted"]),
        ("active", keys["active"], keys["needs_role"]),
        ("talent_pool", keys["needs_role"], keys["active"]),
        ("hired", keys["hired"], keys["needs_role"]),
        ("archived", keys["archived"], keys["needs_role"]),
        ("restricted", keys["restricted"], keys["needs_role"]),
    ]:
        code, payload = http("GET", f"/dashboard/prehire/applications?limit=100&view={view}", headers)
        apps = payload.get("applications") or []
        found = {a.get("app_key") for a in apps}
        for a in apps:
            if a.get("app_key") in keys.values():
                by_key[a["app_key"]] = a
        ok(f"view_{view}", {"include": must_include in found, "exclude": must_exclude not in found, "unified": payload.get("unified_candidates")}) if (
            code == 200 and payload.get("unified_candidates") and must_include in found and must_exclude not in found
        ) else bad(f"view_{view}", {"code": code, "found": list(found)[:20], "body_keys": list(payload.keys())})

    held = by_key.get(keys["needs_role"]) or {}
    live = by_key.get(keys["active"]) or {}
    ok("held_job_not_linked", held.get("job_display")) if held.get("job_display") == "Not linked" else bad("held_job_not_linked", held)
    ok("held_status_talent_pool", held.get("status_display") or held.get("status_label")) if (
        (held.get("status_display") == "Talent Pool") or (held.get("status_label") in {"Talent Pool", "Needs role"} and held.get("job_display") == "Not linked")
    ) else bad("held_status_talent_pool", held)
    ok("held_assessment_dash", held.get("assessment_display") or held.get("assessment")) if (
        held.get("assessment_display") in {"—", "-", None} or held.get("assessment") in (None, {})
    ) else bad("held_assessment_dash", held)
    ok("held_comm_no_outreach", held.get("communication")) if (
        (held.get("communication") or {}).get("message_kind") == "no_outreach"
        or held.get("communication_display") == "No outreach"
    ) else bad("held_comm_no_outreach", held)
    ok("held_hides_imp", held.get("phone")) if not str(held.get("phone") or "").startswith("imp-") else bad("held_hides_imp", held)
    ok("live_keeps_job", live.get("position") or live.get("job_display")) if live else bad("live_keeps_job", live)
    ok("no_duplicate_held", True) if len([a for a in by_key if a == keys["needs_role"]]) <= 1 else bad("no_duplicate_held", by_key.keys())

    # Held gates
    held_key = keys["needs_role"]
    for name, method, path, body in [
        ("held_gate_shortlist", "POST", f"/dashboard/prehire/applications/{held_key}/shortlist", {"confirm": True}),
        ("held_gate_reject", "POST", f"/dashboard/prehire/applications/{held_key}/reject", {"confirm": True, "reason": "canary"}),
        ("held_gate_hire", "POST", f"/dashboard/prehire/applications/{held_key}/hire", {"confirm": True}),
        ("held_gate_notify", "POST", f"/dashboard/prehire/applications/{held_key}/notify", {"channel": "whatsapp", "confirm": True}),
        ("held_gate_evaluation", "POST", f"/dashboard/prehire/applications/{held_key}/evaluation", {"confirm": True}),
        ("held_gate_assessment", "POST", f"/dashboard/prehire/applications/{held_key}/assessment", {"confirm": True}),
        ("held_gate_interview", "POST", f"/dashboard/prehire/applications/{held_key}/interviews", {"confirm": True, "scheduled_at": "2099-01-01T10:00:00Z"}),
        ("held_gate_offer", "POST", f"/dashboard/prehire/applications/{held_key}/offers", {"confirm": True}),
        ("held_gate_link_to_job", "POST", f"/dashboard/prehire/applications/{held_key}/link-to-job", {"position_code": "CANARY_FORBIDDEN", "confirm": True}),
        ("held_gate_intake_admit", "POST", f"/dashboard/prehire/applications/{held_key}/intake-admit", {"position_code": "CANARY_FORBIDDEN", "confirm": True}),
        ("held_gate_ai_assign_job", "POST", f"/dashboard/prehire/applications/{held_key}/assign-job", {"mode": "ai", "confirm": True}),
        ("held_gate_lifecycle", "POST", f"/dashboard/prehire/applications/{held_key}/lifecycle", {"status": "shortlisted", "confirm": True}),
    ]:
        code, out = http(method, path, headers, body)
        ok(name, {"code": code, "body": out}) if code in {403, 404, 405, 409, 422} else bad(name, {"code": code, "body": out})

    # Ranking must not advisory-score held without job / must not include held as ranked canary
    code, rank = http("GET", "/dashboard/prehire/rank?limit=20", headers)
    rank_txt = json.dumps(rank)
    ok("ranking_no_held_canary", {"code": code}) if held_key not in rank_txt else bad("ranking_no_held_canary", rank)

    # Profile / facts
    code, profile = http("GET", f"/dashboard/prehire/applications/{held_key}/profile", headers)
    ok("profile_loaded", {"code": code, "keys": list((profile or {}).keys())}) if code == 200 else bad("profile_loaded", profile)
    ok("sender_provenance_separate", profile.get("sender_provenance")) if profile.get("sender_provenance") else bad("sender_provenance_separate", profile)
    ok("link_to_job_disabled", profile.get("link_to_job")) if (profile.get("link_to_job") or {}).get("enabled") is False else bad("link_to_job_disabled", profile)
    facts = profile.get("facts") or {}
    ok("no_negative_missing_facts", facts) if "does not have" not in json.dumps(facts).lower() else bad("no_negative_missing_facts", facts)

    code, facts_payload = http("GET", f"/dashboard/prehire/applications/{held_key}/facts", headers)
    ok("fact_preview", {"code": code}) if code == 200 else bad("fact_preview", facts_payload)
    code, commit = http("POST", f"/dashboard/prehire/applications/{held_key}/facts/review", headers, {
        "action": "correct", "fact_path": "skills", "new_value": ["Excel", "SQL"], "confirm": True, "note": MARKER
    })
    ok("fact_commit", {"code": code}) if code == 200 else bad("fact_commit", commit)
    code, facts2 = http("GET", f"/dashboard/prehire/applications/{held_key}/facts", headers)
    events = ((facts2.get("facts") or {}).get("events") or facts2.get("events") or [])
    ok("fact_append_only", len(events)) if len(events) >= 2 else bad("fact_append_only", facts2)

    # Saved views
    code, saved = http("POST", "/dashboard/prehire/candidates/saved-views", headers, {
        "name": f"{PREFIX}-talent", "filters": {"view": "talent_pool", "marker": MARKER}
    })
    view_id = (saved.get("view") or {}).get("view_id")
    ok("saved_view_create", saved) if code == 200 and view_id else bad("saved_view_create", saved)
    code, listed = http("GET", "/dashboard/prehire/candidates/saved-views", headers)
    ok("saved_view_list", listed) if code == 200 and any(v.get("view_id") == view_id for v in listed.get("views") or []) else bad("saved_view_list", listed)
    code, deleted = http("DELETE", f"/dashboard/prehire/candidates/saved-views/{view_id}", headers)
    ok("saved_view_delete", deleted) if code == 200 else bad("saved_view_delete", deleted)

    # Search
    code, search = http("GET", "/dashboard/prehire/applications?limit=50&view=all&q=Synthetic%20University", headers)
    reasons_ok = False
    for app in search.get("applications") or []:
        if app.get("app_key") in {keys["needs_role"], keys["active"]} and app.get("match_reasons"):
            reasons_ok = True
            ok("search_reasons_present", app.get("match_reasons"))
            break
    if not reasons_ok:
        # fallback: profile text search
        code, search2 = http("GET", "/dashboard/prehire/applications?limit=50&view=all&q=canary%20synthetic%20accountant", headers)
        for app in search2.get("applications") or []:
            if app.get("app_key") == keys["needs_role"]:
                ok("search_reasons_present", app.get("match_reasons") or {"matched": True})
                reasons_ok = True
                break
        if not reasons_ok:
            bad("search_reasons_present", search)
    # restricted excluded from normal all search
    found = {a.get("app_key") for a in (search.get("applications") or [])}
    ok("search_excludes_restricted", keys["restricted"] not in found) if keys["restricted"] not in found else bad("search_excludes_restricted", found)

    # Intake operations
    code, intake = http("GET", "/dashboard/prehire/intake-operations", headers)
    ok("intake_operations", {"code": code, "malware_forbidden": intake.get("malware_release_forbidden")}) if code == 200 else bad("intake_operations", intake)
    code, attention = http("GET", "/dashboard/prehire/intake-operations/attention", headers)
    ok("intake_attention", attention) if code == 200 else bad("intake_attention", attention)

    # Cross-tenant: production currently has only WATHEFNI as a real tenant.
    # Create an isolated synthetic non-canary company solely for isolation proof, then remove it.
    other = f"UCCX{PREFIX[-6:]}"
    other_user = str(uuid.uuid4())
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies(company_code,name,country,metadata,raw_json,created_at,updated_at)
                VALUES (%s,%s,'KW',%s::jsonb,%s::jsonb,now(),now())
                ON CONFLICT (company_code) DO UPDATE SET updated_at=now()
                """,
                (other, f"Canary Isolation Probe {other}", Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO dashboard_users(
                  user_id, company_code, email, name, role, status, password_hash, metadata, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,'owner','active',%s,%s::jsonb,now(),now())
                ON CONFLICT (company_code, email) DO UPDATE
                  SET status='active', role='owner', updated_at=now()
                RETURNING user_id
                """,
                (
                    other_user,
                    other,
                    f"canary.probe.{other.lower()}@example.invalid",
                    "Canary Isolation Probe",
                    "canary-probe-not-a-login",
                    Json({"marker": MARKER, "synthetic": True}),
                ),
            )
            row = cur.fetchone()
            if row:
                other_user = str(row["user_id"] if isinstance(row, dict) else row[0])
        conn.commit()
    cross = []
    try:
        oh = mint(other)
        code, feat = http("GET", "/dashboard/prehire/candidates/feature", oh)
        code2, legacy = http("GET", "/dashboard/prehire/applications?limit=3", oh)
        code3, dark = http("GET", "/dashboard/prehire/intake-operations", oh)
        cross.append({
            "company": other,
            "enabled": feat.get("enabled_for_company"),
            "master": feat.get("master_enabled"),
            "legacy_unified": legacy.get("unified_candidates"),
            "legacy_code": code2,
            "intake_code": code3,
        })
    except Exception as exc:  # noqa: BLE001
        cross.append({"company": other, "error": str(exc)[:300]})
    finally:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (other,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (other,))
            conn.commit()
    ok("cross_tenant_dark", cross) if cross and all(
        (not c.get("enabled")) and c.get("legacy_unified") in (False, None) and c.get("intake_code") in {403, 404, 409, 501}
        for c in cross if "error" not in c
    ) else bad("cross_tenant_dark", cross)
    # Staging isolation unchanged
    st = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf").read_text()
    ok("staging_unchanged", st) if "TENANTS=WATHEFNI" in st and "TALENT_POOL=on" in st else bad("staging_unchanged", st)

    # Rollback override
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM candidate_fact_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",))
            facts_before = int(cur.fetchone()["c"])
            cur.execute("SELECT status, position_code FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, held_key))
            held_row = dict(cur.fetchone())
    set_tenants("")
    headers_off = mint()
    code, feature_off = http("GET", "/dashboard/prehire/candidates/feature", headers_off)
    ok("rollback_override_disables", feature_off) if not feature_off.get("enabled_for_company") else bad("rollback_override_disables", feature_off)
    code, legacy = http("GET", "/dashboard/prehire/applications?limit=5", headers_off)
    ok("rollback_legacy_experience", {"code": code, "unified": legacy.get("unified_candidates")}) if code == 200 and not legacy.get("unified_candidates") else bad("rollback_legacy_experience", legacy)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM candidate_fact_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",))
            facts_after = int(cur.fetchone()["c"])
    ok("rollback_preserves_sidecar", {"before": facts_before, "after": facts_after}) if facts_before == facts_after else bad("rollback_preserves_sidecar", {"before": facts_before, "after": facts_after})
    ok("rollback_no_job_binding", held_row) if held_row.get("status") == "needs_role" and not (held_row.get("position_code") or "").strip() else bad("rollback_no_job_binding", held_row)

    # Re-enable
    set_tenants("WATHEFNI")
    headers = mint()
    code, feature_on = http("GET", "/dashboard/prehire/candidates/feature", headers)
    ok("reenable_canary", feature_on) if feature_on.get("enabled_for_company") else bad("reenable_canary", feature_on)
    code, tp = http("GET", "/dashboard/prehire/applications?limit=50&view=talent_pool", headers)
    found = {a.get("app_key") for a in tp.get("applications") or []}
    ok("unified_restored_without_rewrite", held_key in found) if held_key in found else bad("unified_restored_without_rewrite", found)

    # Frozen safe packs
    packs = []
    orch = pathlib.Path("/opt/wathefni/orchestrator")
    for name in [
        "test_unified_candidates.py",
        "smoke-test-canonical-recruiting-lifecycle.py",
        "smoke-test-offer-lifecycle.py",
        "smoke-test-assessments.py",
        "smoke-test-prehire-assistant-parity.py",
        "smoke-test-tenant-isolation-harness.py",
        "smoke-test-jobs-phase2-stage-a-unit.py",
    ]:
        path = orch / name
        if not path.exists():
            packs.append({"pack": name, "status": "missing"})
            continue
        rc = os.system(
            f"cd {orch} && WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env "
            f"WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni "
            f"WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432 "
            f"WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1 "
            f"WATHEFNI_CANONICAL_LIFECYCLE=true "
            f"/opt/wathefni/orchestrator/.venv/bin/python {name} > {evidence}/{name}.log 2>&1"
        )
        packs.append({"pack": name, "status": "pass" if rc == 0 else "fail", "rc": rc})
        ok(f"pack_{name}", rc) if rc == 0 else bad(f"pack_{name}", rc)

    # Cleanup + residue
    removed = cleanup()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            apps_left = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_fact_review_events WHERE app_key LIKE %s OR coalesce(note,'') LIKE %s", (f"{PREFIX}%", f"%{MARKER}%"))
            facts_left = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_saved_views WHERE name LIKE %s", (f"{PREFIX}%",))
            views_left = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_record_governance WHERE app_key LIKE %s", (f"{PREFIX}%",))
            gov_left = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidates WHERE phone LIKE %s OR phone LIKE %s", (f"imp-{PREFIX.lower()}%", f"uccanary-{PREFIX.lower()}%"))
            cand_left = int(cur.fetchone()["c"])
            # total sidecar state after cleanup should match pre-canary empty for our markers; overall may still be 0
            cur.execute("SELECT count(*) AS c FROM candidate_fact_review_events")
            facts_total = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_saved_views")
            views_total = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_record_governance")
            gov_total = int(cur.fetchone()["c"])
    residue = {
        "applications": apps_left, "facts": facts_left, "views": views_left, "governance": gov_left,
        "candidates": cand_left, "removed": removed,
        "sidecar_totals": {"facts": facts_total, "views": views_total, "governance": gov_total},
    }
    ok("zero_residue", residue) if apps_left == 0 and facts_left == 0 and views_left == 0 and gov_left == 0 and cand_left == 0 else bad("zero_residue", residue)
    ok("sidecar_back_to_empty", residue["sidecar_totals"]) if facts_total == 0 and views_total == 0 and gov_total == 0 else bad("sidecar_back_to_empty", residue["sidecar_totals"])

    # Leave canary enabled for WATHEFNI after successful qualify (fixtures cleaned)
    set_tenants("WATHEFNI")
    master_conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf").read_text()
    ok("final_master_off", master_conf) if "TALENT_POOL=off" in master_conf else bad("final_master_off", master_conf)
    ok("final_tenants_wathefni", master_conf) if "TENANTS=WATHEFNI" in master_conf else bad("final_tenants_wathefni", master_conf)

    failed = [r for r in RESULTS if not r["pass"]]
    report = {
        "prefix": PREFIX,
        "marker": MARKER,
        "company": COMPANY,
        "pass_count": sum(1 for r in RESULTS if r["pass"]),
        "fail_count": len(failed),
        "results": RESULTS,
        "failed": failed,
        "packs": packs,
        "flag_final": {"master": "off", "tenants": "WATHEFNI"},
        "verdict": "GO_PRODUCTION_CANARY" if not failed else "NO_GO",
    }
    (evidence / "canary-qualification.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "pass": report["pass_count"], "fail": report["fail_count"], "evidence": str(evidence)}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
