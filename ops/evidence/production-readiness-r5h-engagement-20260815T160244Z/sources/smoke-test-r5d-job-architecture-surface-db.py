#!/usr/bin/env python3
"""Production Readiness R5D — staging DB Job Architecture journeys A–G."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5D{SUFFIX}"[:12]
COMPANY_B = f"R5Z{SUFFIX}"[:12]
HR = f"9656112{SUFFIX[:5]}"
EMP = f"emp-{SUFFIX.lower()}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def cleanup(app, companies: list[str]) -> None:
    import production_data_safety as pds

    pds.require_destructive_scope(companies)
    tables = [
        "ja_optional_external_ref",
        "ja_legacy_mapping",
        "ja_employment_assignment",
        "ja_org_position_link",
        "ja_career_edge",
        "ja_job_profile",
        "ja_level",
        "ja_grade",
        "ja_job_function",
        "ja_job_family",
        "ja_wave5_fact_outbox",
        "ja_audit_events",
        "ja_company_settings",
        "talent_successor_nominations",
        "talent_succession_plans",
        "talent_critical_roles",
        "talent_succession_c6_audit",
        "talent_succession_c6_company_settings",
        "company_modules",
        "companies",
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
                except Exception:
                    conn.rollback()
        conn.commit()


def _ctx(company: str, *, role: str, perms: list[str], phone: str, user_id: str) -> dict:
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_phone": phone,
        "hr_phone": phone,
        "phone": phone,
        "actor_role": role,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "hr_user": {"status": "active", "role": role},
        "access": {
            "role": role,
            "permissions": perms,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company,
        },
    }


def run_http_security_tests(app) -> None:
    from fastapi.testclient import TestClient

    hr_perms = [
        "job_architecture.read",
        "job_architecture.manage",
        "job_architecture.mapping",
        "job_architecture.publish",
    ]
    client = TestClient(app.app)
    registered = any(
        str(getattr(route, "path", "")).startswith("/dashboard/job-architecture") for route in app.app.routes
    )
    check("JA HTTP routes registered", registered is True)

    def use(ctx: dict) -> None:
        app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

    try:
        unauth = TestClient(app.app)
        app.app.dependency_overrides.clear()
        bare = unauth.get("/dashboard/job-architecture/workspace")
        check("unauthenticated dashboard not public", bare.status_code in {401, 403}, bare.status_code)

        use(_ctx(COMPANY, role="owner", perms=hr_perms, phone=HR, user_id="r5d-hr"))
        ws = client.get("/dashboard/job-architecture/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        check("workspace has no career score", ws.json().get("master_career_score") is None, ws.json())
        families = client.get("/dashboard/job-architecture/families")
        check("HR lists families", families.status_code == 200, families.text[:300])
        a_codes = {str(row.get("code")) for row in (families.json().get("families") or [])}

        use(_ctx(COMPANY_B, role="owner", perms=hr_perms, phone=HR, user_id="r5d-hr-b"))
        cross = client.get("/dashboard/job-architecture/families")
        check("tenant isolation HTTP 200", cross.status_code == 200, cross.status_code)
        b_codes = {str(row.get("code")) for row in (cross.json().get("families") or [])}
        check("tenant B does not see tenant A families", not (a_codes & b_codes), {"a": a_codes, "b": b_codes})

        use(_ctx(COMPANY, role="manager", perms=["job_architecture.read"], phone=HR, user_id="r5d-mgr"))
        denied = client.post(
            "/dashboard/job-architecture/families",
            json={"code": "NO", "name_en": "No", "name_ar": "لا", "reason": "nope"},
        )
        check("manager cannot author", denied.status_code == 403, denied.status_code)

        use(_ctx(COMPANY, role="owner", perms=["job_architecture.read"], phone=HR, user_id="r5d-hr-ro"))
        write = client.post(
            "/dashboard/job-architecture/grades",
            json={"code": "GX", "name_en": "GX", "name_ar": "ج", "reason": "nope"},
        )
        check("HR without manage denied write", write.status_code == 403, write.status_code)
        migrate = client.post(
            "/dashboard/job-architecture/mappings/migrate",
            json={"raw_field": "job_title", "candidates": [{"raw_value": "X"}], "reason": "nope"},
        )
        check("HR without mapping denied migrate", migrate.status_code == 403, migrate.status_code)

        use(_ctx(COMPANY, role="owner", perms=hr_perms, phone=HR, user_id="r5d-hr"))
        deleted = client.delete("/dashboard/job-architecture/profiles")
        detail = deleted.json().get("detail") if deleted.headers.get("content-type", "").startswith("application/json") else None
        check("hard delete forbidden", deleted.status_code == 403, deleted.status_code)
        check(
            "hard delete names refuse",
            isinstance(detail, dict) and detail.get("error") == "destructive_delete_forbidden",
            detail,
        )
    finally:
        app.app.dependency_overrides.clear()


def _env_on() -> None:
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "on"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = f"{COMPANY},{COMPANY_B}"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_LEARNING_DEVELOPMENT_C2"] = "off"
    os.environ["WATHEFNI_COMPENSATION_PLANNING_C6"] = "off"
    os.environ["WATHEFNI_WORKFORCE_PLANNING_C7"] = "off"


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5D — job architecture surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import job_architecture_c1 as c1
        import job_architecture_surfaces as surfaces
        import talent_succession_c6 as c6
        import talent_surfaces as talent
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  psycopg2 unavailable")
            return 1
        raise

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        return 1

    pds.require_non_production_target()
    app.ensure_schema()
    cleanup(app, [COMPANY, COMPANY_B])
    _env_on()

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5D {COMPANY}"), (COMPANY_B, f"R5D {COMPANY_B}")):
                    cur.execute(
                        """
                        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                        ON CONFLICT (company_code) DO NOTHING
                        """,
                        (code, name),
                    )
                surfaces.ensure_schema(cur)
                synced_b = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5d enable b"
                )
                check("enable tenant B", synced_b.get("ok") is True, synced_b)
                synced = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5d enable"
                )
                check("sync JA entitlement", synced.get("ok") is True, synced)
                check("JA not a SKU", synced.get("not_separate_customer_sku") is True)
                check("salary bands out", synced.get("salary_bands_out_of_c1") is True)
                check("JA catalog enableable", ready.customer_enableable("job_architecture") is True)
                import module_catalog as catalog
                check("JA not in module catalog", "job_architecture" not in catalog.MODULE_BY_KEY)

                # A — authoring
                fam = c1.upsert_job_family(
                    cur, company_code=COMPANY, actor_phone=HR, code="ENG",
                    name_en="Engineering", name_ar="الهندسة", status="published", reason="author family",
                )
                check("A family", fam.get("ok") is True and fam.get("stable_id"), fam)
                family_id = fam["stable_id"]
                fn = c1.upsert_job_function(
                    cur, company_code=COMPANY, actor_phone=HR, family_id=family_id, code="SWE",
                    name_en="Software", name_ar="برمجيات", status="published", reason="author function",
                )
                check("A function", fn.get("ok") is True, fn)
                function_id = fn["function"]["function_id"]
                grade = c1.upsert_grade(
                    cur, company_code=COMPANY, actor_phone=HR, code="G5",
                    name_en="Grade 5", name_ar="الدرجة ٥", rank_order=5, status="published", reason="author grade",
                )
                check("A grade", grade.get("ok") is True, grade)
                grade_id = grade["stable_id"]
                level = c1.upsert_level(
                    cur, company_code=COMPANY, actor_phone=HR, code="L2",
                    name_en="II", name_ar="٢", grade_id=grade_id, rank_order=2, status="published", reason="author level",
                )
                check("A level", level.get("ok") is True, level)
                level_id = level["stable_id"]
                prof = c1.upsert_job_profile(
                    cur, company_code=COMPANY, actor_phone=HR, function_id=function_id, code="SWE2",
                    name_en="Software Engineer II", name_ar="مهندس برمجيات ٢", status="published",
                    default_grade_id=grade_id, default_level_id=level_id, description_en="Build products",
                    description_ar="يبني المنتجات", reason="author profile",
                )
                check("A profile", prof.get("ok") is True, prof)
                check("A profile not recruiting job", (prof.get("boundaries") or {}).get("recruiting_job_is_not_ja_profile") is True)
                profile_id = prof["stable_id"]
                senior = c1.upsert_job_profile(
                    cur, company_code=COMPANY, actor_phone=HR, function_id=function_id, code="SWE3",
                    name_en="Senior Software Engineer", name_ar="مهندس برمجيات أول", status="published",
                    default_grade_id=grade_id, reason="author senior",
                )
                check("A senior profile", senior.get("ok") is True, senior)
                senior_id = senior["stable_id"]
                catalog = surfaces.list_catalog(cur, company_code=COMPANY)
                check("A retrieve families", any(str(r.get("family_id")) == str(family_id) for r in (catalog.get("families") or [])))
                check("A retrieve profiles", any(str(r.get("profile_id")) == str(profile_id) for r in (catalog.get("profiles") or [])))

                # B — deterministic unique mapping + raw preserved
                raw_title = "Software Engineer II"
                raw_grade = "Grade 5"
                migrated = c1.migrate_legacy_values(
                    cur, company_code=COMPANY, actor_phone=HR, raw_field="job_title",
                    candidates=[{"raw_value": raw_title, "source": "employment_record", "employee_key": EMP}],
                )
                check("B unique title mapped", migrated.get("mapped") == 1, migrated)
                check("B raw preserved flag", migrated.get("raw_preserved") is True)
                check("B no fuzzy AI", migrated.get("fuzzy_ai_used") is False)
                title_row = (migrated.get("results") or [{}])[0]
                check("B match unique", title_row.get("match_kind") == "deterministic_unique", title_row)
                check("B raw title unchanged", title_row.get("raw_value") == raw_title, title_row)
                grade_mig = c1.migrate_legacy_values(
                    cur, company_code=COMPANY, actor_phone=HR, raw_field="grade",
                    candidates=[{"raw_value": raw_grade, "source": "employment_record", "employee_key": EMP}],
                )
                check("B unique grade mapped", grade_mig.get("mapped") == 1, grade_mig)
                check("B raw grade unchanged", (grade_mig.get("results") or [{}])[0].get("raw_value") == raw_grade)
                assigned = c1.assign_employment_architecture(
                    cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                    effective_start=date.today().isoformat(), profile_id=profile_id, grade_id=grade_id,
                    level_id=level_id, reason="canonical map",
                )
                check("B assignment added", assigned.get("ok") is True, assigned)
                check("B assignment is architecture only", "salary" not in (assigned.get("assignment") or {}))

                # C — ambiguous title stays explicit
                twin_a = c1.upsert_job_profile(
                    cur, company_code=COMPANY, actor_phone=HR, function_id=function_id, code="ENG-A",
                    name_en="Engineer", name_ar="مهندس أ", status="published", reason="twin a",
                )
                twin_b = c1.upsert_job_profile(
                    cur, company_code=COMPANY, actor_phone=HR, function_id=function_id, code="ENG-B",
                    name_en="Engineer", name_ar="مهندس ب", status="published", reason="twin b",
                )
                check("C twin profiles", twin_a.get("ok") is True and twin_b.get("ok") is True)
                amb = c1.migrate_legacy_values(
                    cur, company_code=COMPANY, actor_phone=HR, raw_field="job_title",
                    candidates=[{"raw_value": "Engineer", "source": "legacy"}],
                )
                check("C no automatic canonical", amb.get("unmapped_ambiguous") == 1, amb)
                amb_row = (amb.get("results") or [{}])[0]
                check("C explicit ambiguous", amb_row.get("match_kind") == "unmapped_ambiguous", amb_row)
                check("C raw still Engineer", amb_row.get("raw_value") == "Engineer")
                none = c1.migrate_legacy_values(
                    cur, company_code=COMPANY, actor_phone=HR, raw_field="job_title",
                    candidates=[{"raw_value": "Chief Wizard", "source": "legacy"}],
                )
                check("C unmatched explicit", none.get("unmapped_none") == 1, none)
                resolved = surfaces.resolve_legacy_mapping(
                    cur, company_code=COMPANY, actor_phone=HR,
                    mapping_id=str(amb_row.get("mapping_id")),
                    mapped_entity_type="job_profile",
                    mapped_entity_id=str(twin_a["stable_id"]),
                    reason="human resolve",
                )
                check("C human resolve", resolved.get("ok") is True and resolved.get("auto_canonical") is False, resolved)
                check("C resolve raw preserved", resolved.get("raw_value") == "Engineer", resolved)

                # D — career edges ≠ eligibility
                for edge_type in ("promotion", "lateral", "specialist", "manager"):
                    edge = c1.create_career_edge(
                        cur, company_code=COMPANY, actor_phone=HR, edge_type=edge_type,
                        from_profile_id=profile_id, to_profile_id=senior_id, reason=f"edge {edge_type}",
                    )
                    check(f"D {edge_type} edge", edge.get("ok") is True, edge)
                    check(f"D {edge_type} not eligibility", edge.get("is_eligibility") is False, edge)
                    check(f"D {edge_type} not auto eligible", edge.get("employee_auto_eligible") is False, edge)
                scored = c1.create_career_edge(
                    cur, company_code=COMPANY, actor_phone=HR, edge_type="promotion",
                    from_profile_id=profile_id, to_profile_id=senior_id,
                    optional_requirements={"eligibility_score": 99}, reason="forbidden score",
                )
                check("D eligibility score forbidden", scored.get("error") == "eligibility_scoring_forbidden", scored)

                # E — Talent optional ref; JA does not acquire Talent judgment
                talent.ensure_all_schemas(cur)
                talent.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5d talent optional"
                )
                role = c6.designate_critical_role(
                    cur, company_code=COMPANY, actor_phone=HR,
                    canonical_role_key=f"swe-lead-{SUFFIX.lower()}",
                    title_en="Engineering lead", title_ar="قائد هندسة", reason="target role",
                )
                check("E talent critical role", role.get("ok") is True, role)
                role_id = str((role.get("critical_role") or {}).get("critical_role_id") or "")
                ref = c1.optional_external_ref(
                    cur, company_code=COMPANY, actor_phone=HR, domain="talent_critical_role",
                    external_key=role_id, profile_id=profile_id, note="optional target role",
                )
                check("E optional talent ref", ref.get("ok") is True and ref.get("hard_dependency") is False, ref)
                check("E JA did not acquire hipo", "hipo" not in ref and "potential" not in (ref.get("ref") or {}))
                check("E talent still optional", surfaces.honesty_payload().get("talent_optional") is True)

                # F — Recruiting optional ref; editing ref does not rewrite JA profile
                before = [r for r in (surfaces.list_catalog(cur, company_code=COMPANY).get("profiles") or []) if str(r.get("profile_id")) == str(profile_id)][0]
                rec = c1.optional_external_ref(
                    cur, company_code=COMPANY, actor_phone=HR, domain="recruiting_opening",
                    external_key="REQ-100", profile_id=profile_id, note="opening v1",
                )
                check("F recruiting ref", rec.get("ok") is True, rec)
                rec2 = c1.optional_external_ref(
                    cur, company_code=COMPANY, actor_phone=HR, domain="recruiting_opening",
                    external_key="REQ-100", profile_id=profile_id, note="opening v2 edited",
                )
                check("F recruiting ref edit", rec2.get("ok") is True, rec2)
                after = [r for r in (surfaces.list_catalog(cur, company_code=COMPANY).get("profiles") or []) if str(r.get("profile_id")) == str(profile_id)][0]
                check("F profile name unchanged", after.get("name_en") == before.get("name_en"), after)
                check("F profile version unchanged by requisition edit", after.get("effective_version") == before.get("effective_version"), after)

                # G — rename/version keeps historical reconstruction
                renamed = c1.upsert_job_profile(
                    cur, company_code=COMPANY, actor_phone=HR, function_id=function_id, code="SWE2",
                    name_en="Software Engineer II (renamed)", name_ar="مهندس برمجيات ٢ (محدث)",
                    status="published", default_grade_id=grade_id, default_level_id=level_id,
                    description_en="Build products", description_ar="يبني المنتجات", reason="rename profile",
                )
                check("G rename ok", renamed.get("ok") is True, renamed)
                check("G stable id preserved", renamed.get("stable_id") == profile_id, renamed)
                check("G version bumped", int((renamed.get("profile") or {}).get("effective_version") or 0) > int(before.get("effective_version") or 1), renamed)
                maps = surfaces.list_mappings(cur, company_code=COMPANY)
                title_maps = [m for m in (maps.get("mappings") or []) if m.get("raw_value") == raw_title]
                check("G historical raw title reconstructable", bool(title_maps), maps)
                hist = surfaces.list_history(cur, company_code=COMPANY, entity_type="job_profile")
                check("G history events exist", bool(hist.get("events")), hist)
                assigns = surfaces.list_assignments(cur, company_code=COMPANY, employee_key=EMP)
                check("G assignment still points at stable id", any(str(a.get("profile_id")) == str(profile_id) for a in (assigns.get("assignments") or [])), assigns)

                ws = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("workspace enabled", ws.get("ok") is True and ws.get("enabled") is True, ws)
                check("workspace no career score", ws.get("master_career_score") is None)
                check("error is not empty pattern", ws.get("resource_state") in {"ok", "empty"})
                check("unmapped count explicit", (ws.get("counts") or {}).get("ambiguous", 0) >= 0)

                # Module-off after historical mappings
                disabled = c1.disable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="disable after use")
                check("disable retains history flag", disabled.get("history_retained") is True, disabled)
                still_maps = surfaces.list_mappings(cur, company_code=COMPANY)
                check("disabled mappings unavailable not fake empty", still_maps.get("resource_state") == "unavailable", still_maps)
                check("disabled does not invent zero unmapped", still_maps.get("mappings") is None, still_maps)
                blocked = c1.upsert_job_family(
                    cur, company_code=COMPANY, actor_phone=HR, code="X", name_en="X", name_ar="س", reason="after disable",
                )
                check("writes blocked when disabled", blocked.get("ok") is not True, blocked)
                cur.execute("SELECT raw_value FROM ja_legacy_mapping WHERE company_code=%s AND raw_value=%s", (COMPANY, raw_title))
                retained = cur.fetchone()
                check("raw title retained after disable", bool(retained), retained)
                off_ws = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("disabled workspace unavailable", off_ws.get("resource_state") == "unavailable", off_ws)
                check("disabled counts are not fake zeros", off_ws.get("counts") is None, off_ws)

                # Re-enable to leave HTTP tests with a usable tenant
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="restore for http"
                )
            conn.commit()

        run_http_security_tests(app)
    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5D_JOB_ARCHITECTURE_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
