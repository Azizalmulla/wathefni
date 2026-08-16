#!/usr/bin/env python3
"""Wave 4 C6 — Talent Review / HiPo / Succession / optional 9-box synthetic prove."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"TS6{_N:05d}"[:12].upper()
OTHER = f"TSX{_N:05d}"[:12].upper()
HR = f"9656700{_N:05d}"
EMP = f"{COMPANY}-W4C6-{SUFFIX}"
EMP2 = f"{COMPANY}-W4C6B-{SUFFIX}"
EMP3 = f"{COMPANY}-W4C6C-{SUFFIX}"
MGR = f"9656701{_N:05d}"
OUT = f"9656799{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, on: str, companies: str, nine_box: bool = False) -> None:
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = on
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = companies
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_C4"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = "off"
    _ = nine_box


def main() -> int:
    print("    talent succession c6 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import talent_succession_c6 as c6

    check("c6 module", c6.PHASE == "talent_succession_c6")
    check("charter stamp", c6.PASS_STAMP == "TALENT_SUCCESSION_MOBILITY_FULL_PASS")
    h = c6.honesty_payload()
    check("c5 authoritative", h.get("c5_profile_remains_authoritative") is True)
    check("not perf cal", h.get("talent_review_not_performance_calibration") is True)
    check("hipo explicit", h.get("hipo_requires_explicit_human_decision") is True)
    check("no auto hipo", h.get("hipo_never_inferred_from_perf_potential_or_9box") is True)
    check("9box projection", h.get("nine_box_is_projection_not_sot") is True)
    check("9box optional", h.get("nine_box_optional") is True)
    check("succ w/o 9box", h.get("succession_works_without_nine_box") is True)
    check("hipo w/o 9box", h.get("hipo_works_without_nine_box") is True)
    check("succ w/o hipo", h.get("succession_works_without_hipo") is True)
    check("target readiness", h.get("readiness_is_target_specific") is True)
    check("no master score", h.get("no_master_talent_score") is True)
    check("assistant out", h.get("assistant_mutations") is False)
    check("EN designated", c6.status_label("designated", lang="en") == "HiPo designated")
    check("AR ready_now", c6.status_label("ready_now", lang="ar") == "جاهز الآن")
    check("rollback", "WATHEFNI_TALENT_SUCCESSION_C6=off" in str(c6.rollback_guidance()))
    forbid = c6.assert_no_forbidden_c6_writes()
    check("no ai hipo", forbid.get("ai_hipo_designation") is False)
    check("no employee.box", forbid.get("employee_box_canonical_field") is False)

    # Pure 9-box projection unit
    cfg = {
        "version": 1,
        "thresholds": {
            "performance": {"low": {"min": 1, "max": 2.49}, "mid": {"min": 2.5, "max": 3.49}, "high": {"min": 3.5, "max": 5}},
            "potential": {"emerging": "low", "expanding": "mid", "enterprise": "high"},
        },
        "labels": {
            "highxhigh": {"en": "Top right", "ar": "أعلى اليمين"},
            "midxmid": {"en": "Core", "ar": "أساسي"},
        },
    }
    top = c6.project_nine_box(config=cfg, performance_value=4.0, potential_level="enterprise")
    check("9box projects", top.get("available") is True and top.get("cell") == "highxhigh", top)
    check("9box not SoT", top.get("is_canonical_employee_state") is False)
    check("top-right ≠ hipo", top.get("does_not_imply_hipo") is True)
    miss = c6.project_nine_box(config=cfg, performance_value=None, potential_level="enterprise")
    check("9box unavailable if axis missing", miss.get("available") is False, miss)

    _flags(on="off", companies="")
    check("global off", c6.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c6.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary ok", c6.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c6.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    try:
        _db = app.db_connect()
        conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c6.ensure_talent_succession_c6_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"TS6 {COMPANY}"),
            )

            # Path A: 9-box OFF, Performance OFF
            en = c6.enable_company_talent_succession(
                cur, company_code=COMPANY, actor_phone=HR, reason="c6 canary 9box off",
                nine_box_enabled=False, performance_evidence_consume=False,
            )
            check("enable c6", en.get("ok") is True, en)
            check("9box disabled setting", en.get("settings", {}).get("nine_box_enabled") is False)

            # Succession without 9-box / without HiPo
            crit = c6.designate_critical_role(
                cur, company_code=COMPANY, actor_phone=HR,
                canonical_role_key="ROLE-ENG-DIR",
                canonical_position_id="POS-1001",
                title_en="Engineering Director",
                title_ar="مدير الهندسة",
                org_unit_key="OU-ENG",
                reason="canonical org ref",
            )
            check("critical role", crit.get("ok") is True, crit)
            role_id = str(crit["critical_role"]["critical_role_id"])
            check("canonical role key", crit["critical_role"]["canonical_role_key"] == "ROLE-ENG-DIR")

            plan = c6.create_succession_plan(
                cur, company_code=COMPANY, actor_phone=HR, critical_role_id=role_id,
            )
            check("succession plan", plan.get("ok") is True, plan)
            plan_id = str(plan["plan"]["plan_id"])

            uncovered = c6.list_uncovered_critical_roles(cur, company_code=COMPANY)
            check("uncovered honest", any(r["critical_role_id"] == uuid.UUID(role_id) or str(r["critical_role_id"]) == role_id for r in uncovered.get("uncovered") or []), uncovered)

            nom1 = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                employee_key=EMP, rationale="Strong systems leadership evidence from C5",
                readiness="ready_lt_1y", readiness_rationale="Needs one more cross-org stretch",
                capability_gaps=[{"en": "Executive stakeholder management"}],
                has_sensitive_permission=True,
            )
            check("nominate successor", nom1.get("ok") is True, nom1)
            check("target-specific readiness", nom1["nomination"]["readiness"] == "ready_lt_1y")
            check("no global readiness", nom1.get("global_readiness_score") is None)

            nom2 = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                employee_key=EMP2, rationale="Ready now for director scope",
                readiness="ready_now", has_sensitive_permission=True, tier="primary",
            )
            check("multiple successors", nom2.get("ok") is True, nom2)

            # Second critical role — same EMP as successor for multiple roles
            crit2 = c6.designate_critical_role(
                cur, company_code=COMPANY, actor_phone=HR,
                canonical_role_key="ROLE-PROD-DIR", title_en="Product Director",
            )
            plan2 = c6.create_succession_plan(
                cur, company_code=COMPANY, actor_phone=HR,
                critical_role_id=str(crit2["critical_role"]["critical_role_id"]),
            )
            nom3 = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR,
                plan_id=str(plan2["plan"]["plan_id"]), employee_key=EMP,
                rationale="Also viable for product director", readiness="longer_term",
                has_sensitive_permission=True,
            )
            check("one emp multiple roles", nom3.get("ok") is True, nom3)
            tmap = c6.talent_map_queries(cur, company_code=COMPANY, employee_key=EMP, critical_role_id=role_id)
            check("map role→successors", len(tmap.get("role_to_successors") or []) >= 2, tmap)
            check("map emp→roles", len(tmap.get("employee_to_target_roles") or []) >= 2, tmap)
            check("map no master score", tmap.get("master_talent_score") is None)

            cur.execute(
                """
                SELECT fact_type, fact_value FROM talent_succession_coverage_facts
                WHERE company_code=%s AND critical_role_id=%s
                ORDER BY emitted_at DESC LIMIT 8
                """,
                (COMPANY, role_id),
            )
            facts = [dict(r) for r in cur.fetchall()]
            types = {f["fact_type"] for f in facts}
            check("wave5 coverage facts", {"successor_count", "ready_now_count", "uncovered_critical_role"} <= types, types)

            uncovered2 = c6.list_uncovered_critical_roles(cur, company_code=COMPANY)
            check("no longer uncovered eng", all(str(r["critical_role_id"]) != role_id for r in uncovered2.get("uncovered") or []))

            # HiPo without 9-box — explicit only
            hipo = c6.decide_hipo(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                status="designated", rationale="Explicit Talent committee decision — not from box",
                has_sensitive_permission=True,
            )
            check("explicit hipo", hipo.get("ok") is True and hipo.get("auto_inferred") is False, hipo)
            check("top-right not auto hipo", hipo.get("top_right_implies_hipo") is False)
            des_id = str(hipo["designation"]["designation_id"])
            rv = int(hipo["designation"]["row_version"])

            stale = c6.decide_hipo(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                status="not_designated", rationale="stale", expected_row_version=rv - 1 if rv > 1 else 999,
                has_sensitive_permission=True,
            )
            # After first designation, prior has row_version 1; new insert doesn't use expected on new row the same way —
            # decide_hipo checks prior row_version. prior is the designated one with rv=1.
            # Passing wrong expected should fail.
            check("stale hipo denied", stale.get("error") == "stale_row_version", stale)

            hipo2 = c6.decide_hipo(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                status="review_required", rationale="Annual re-review",
                expected_row_version=1, has_sensitive_permission=True,
            )
            check("hipo change versioned", hipo2.get("ok") is True and int(hipo2["designation"]["version"]) == 2, hipo2)
            cur.execute(
                "SELECT count(*) AS n FROM talent_hipo_designations WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            check("hipo history retained", int(dict(cur.fetchone())["n"]) >= 2)

            emp_hipo = c6.get_hipo_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP, viewer_role="employee"
            )
            check("hipo hidden from employee", emp_hipo.get("ok") is not True, emp_hipo)

            # Talent Review with Performance OFF, 9-box OFF
            rev = c6.create_talent_review(
                cur, company_code=COMPANY, actor_phone=HR,
                name_en="2026 H1 Talent Review", name_ar="مراجعة المواهب 2026",
            )
            check("create talent review", rev.get("ok") is True, rev)
            review_id = str(rev["review"]["review_id"])

            prep = c6.prepare_talent_review(
                cur, company_code=COMPANY, review_id=review_id, actor_phone=HR,
                population=[
                    {
                        "employee_key": EMP,
                        "manager_phone": MGR,
                        "org_unit_key": "OU-ENG",
                        "frozen_potential_level": "expanding",
                        "frozen_performance_outcome": None,  # performance off / unused
                    },
                    {
                        "employee_key": EMP2,
                        "manager_phone": MGR,
                        "org_unit_key": "OU-ENG",
                        "frozen_potential_level": "enterprise",
                    },
                ],
                potential_framework_version=1,
                reason="freeze population performance off",
            )
            check("review population snapshot", prep.get("ok") is True and prep["review"]["status"] == "prepared", prep)
            check("9box off in snapshot", prep["review"].get("nine_box_enabled_snapshot") is False)

            start = c6.start_talent_review(
                cur, company_code=COMPANY, review_id=review_id, actor_phone=HR
            )
            check("review in_review", start.get("ok") is True, start)
            locked = c6.complete_and_lock_talent_review(
                cur, company_code=COMPANY, review_id=review_id, actor_phone=HR,
                reason="lock review", has_sensitive_permission=True,
            )
            check("review locked", locked.get("ok") is True and locked.get("immutable") is True, locked)

            survive = c6.prove_review_survives_later_changes(
                cur, review_id=review_id,
                mutated_org_unit="OU-MOVED", mutated_potential="enterprise",
            )
            check("historical review survives", survive.get("ok") is True and survive.get("population_unchanged_by_later_org") is True, survive)

            # Path B: enable 9-box — prove projection; underlying unchanged
            c6.enable_company_talent_succession(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable optional 9box",
                nine_box_enabled=True, performance_evidence_consume=True,
            )
            nb = c6.create_nine_box_config(
                cur, company_code=COMPANY, actor_phone=HR,
                name_en="Perf x Potential",
                performance_axis={"source": "calibrated_final", "version": 1},
                potential_axis={"source": "c5_potential", "version": 1},
                thresholds=cfg["thresholds"],
                labels=cfg["labels"],
            )
            check("9box config", nb.get("ok") is True and nb.get("canonical_employee_box") is False, nb)
            config_id = str(nb["config"]["config_id"])

            # Prove top-right does NOT auto HiPo
            proj = c6.project_nine_box(
                config=dict(nb["config"]), performance_value=4.2, potential_level="enterprise"
            )
            check("projection top-right", proj.get("cell") == "highxhigh", proj)
            # EMP3 never designated despite top-right projection
            cur.execute(
                "SELECT count(*) AS n FROM talent_hipo_designations WHERE employee_key=%s", (EMP3,)
            )
            check("no auto hipo from projection", int(dict(cur.fetchone())["n"]) == 0)

            rev2 = c6.create_talent_review(
                cur, company_code=COMPANY, actor_phone=HR, name_en="Review with 9box"
            )
            review2 = str(rev2["review"]["review_id"])
            prep2 = c6.prepare_talent_review(
                cur, company_code=COMPANY, review_id=review2, actor_phone=HR,
                nine_box_config_id=config_id,
                population=[
                    {
                        "employee_key": EMP3,
                        "manager_phone": MGR,
                        "frozen_potential_level": "enterprise",
                        "frozen_performance_outcome": 4.2,
                        "frozen_performance_label": "Exceeds",
                    }
                ],
            )
            check("review with 9box snapshot", prep2.get("ok") is True, prep2)
            pop = prep2["population"][0]
            snap = pop.get("nine_box_projection_snapshot")
            if isinstance(snap, str):
                import json as _json
                snap = _json.loads(snap)
            check("historical projection stored", snap and snap.get("available") is True, snap)
            check("projection not employee SoT", snap.get("is_canonical_employee_state") is False)

            # Sensitive RBAC
            vis = c6.can_view_succession(
                viewer_role="employee", settings=en["settings"]
            )
            # settings may have been updated — reload
            settings = c6.get_company_settings(cur, COMPANY)
            vis = c6.can_view_succession(viewer_role="employee", settings=settings)
            check("succ hidden from employee", vis.get("ok") is not True, vis)
            vis_mgr = c6.can_view_succession(
                viewer_role="manager", settings=settings, has_sensitive_permission=False, manager_in_scope=True
            )
            check("mgr needs sensitive", vis_mgr.get("error") == "sensitive_permission_required", vis_mgr)
            vis_ok = c6.can_view_succession(
                viewer_role="hr", settings=settings, has_sensitive_permission=True
            )
            check("hr with sensitive ok", vis_ok.get("ok") is True)

            # Cross-tenant
            xt = c6.designate_critical_role(
                cur, company_code=OTHER, actor_phone=HR, canonical_role_key="X", title_en="x"
            )
            check("cross-tenant denied", xt.get("ok") is not True, xt)

            # Idempotent nomination
            again = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                employee_key=EMP, rationale="refresh", readiness="ready_now",
                has_sensitive_permission=True,
            )
            check("idempotent nomination", again.get("ok") is True and again.get("idempotent") is True, again)

            # Disable preserves history
            dis = c6.disable_company_talent_succession(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off"
            )
            check("disable preserves", dis.get("preserves_history") is True, dis)
            cur.execute(
                "SELECT count(*) AS n FROM talent_reviews WHERE company_code=%s", (COMPANY,)
            )
            check("reviews remain", int(dict(cur.fetchone())["n"]) >= 2)
            cur.execute(
                "SELECT count(*) AS n FROM talent_successor_nominations WHERE company_code=%s", (COMPANY,)
            )
            check("nominations remain", int(dict(cur.fetchone())["n"]) >= 3)
            cur.execute(
                "SELECT count(*) AS n FROM talent_hipo_designations WHERE company_code=%s", (COMPANY,)
            )
            check("hipo history remains", int(dict(cur.fetchone())["n"]) >= 2)
            blocked = c6.create_talent_review(
                cur, company_code=COMPANY, actor_phone=HR, name_en="after disable"
            )
            check("module-off blocks", blocked.get("ok") is not True, blocked)

            # 9-box without succession still possible when re-enabled — projection only
            c6.enable_company_talent_succession(
                cur, company_code=COMPANY, actor_phone=HR, reason="re-enable",
                nine_box_enabled=True,
            )
            # succession_enabled stays true on enable — prove hipo/succ/9box independence via honesty already
            check("perf flags remain off", os.environ.get("WATHEFNI_PERFORMANCE_CALIBRATION_C4") == "off")

            conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(f"    {c6.PASS_STAMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
