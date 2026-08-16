#!/usr/bin/env python3
"""PT5 — Succession + mobility staging DB journeys."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PT5{_N:05d}"[:12].upper()
HR = f"9657500{_N:05d}"
EMP = f"{COMPANY}-PT5-{SUFFIX}"
EMP_PHONE = f"9657501{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    pt5 succession mobility — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "on"
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6
    import talent_succession_intel_pt5 as pt5

    try:
        import app
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c5.ensure_talent_profile_c5_schema(cur)
            c6.ensure_talent_succession_c6_schema(cur)
            pt5.ensure_talent_succession_intel_pt5_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now()) ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PT5 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, EMP, EMP_PHONE, "PT5 Emp", date(2036, 1, 1), date(2036, 1, 1)),
            )
            c5.enable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="c5")
            c6.enable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="c6")
            empty_role = c6.designate_critical_role(
                cur, company_code=COMPANY, actor_phone=HR, canonical_role_key=f"EMPTY-{SUFFIX}",
                title_en="Empty", title_ar="فارغ", reason="empty",
            )
            covered = c6.designate_critical_role(
                cur, company_code=COMPANY, actor_phone=HR, canonical_role_key=f"ONE-{SUFFIX}",
                title_en="One successor", title_ar="خلف واحد", reason="one",
            )
            plan = c6.create_succession_plan(
                cur, company_code=COMPANY, actor_phone=HR,
                critical_role_id=str(covered["critical_role"]["critical_role_id"]), reason="plan",
            )
            nom = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=str(plan["plan"]["plan_id"]),
                employee_key=EMP, rationale="only one", readiness="ready_now",
                has_sensitive_permission=True, reason="nom",
            )
            check("nominate", nom.get("ok") is True, nom)
            intel = pt5.succession_intelligence(cur, company_code=COMPANY)
            check("intel ok", intel.get("ok") is True, intel)
            uncovered = intel.get("uncovered_critical_roles") or []
            check("empty role uncovered", any(r.get("critical_role_id") == str(empty_role["critical_role"]["critical_role_id"]) for r in uncovered), uncovered)
            single = intel.get("single_successor") or []
            check("single-successor risk", any(r.get("critical_role_id") == str(covered["critical_role"]["critical_role_id"]) for r in single), single)
            one = next(r for r in intel.get("roles") or [] if r.get("critical_role_id") == str(covered["critical_role"]["critical_role_id"]))
            check("does not invent candidates", one.get("successor_count") == 1 and one.get("invented_candidates") is False, one)
            check("bench score none", one.get("bench_score") is None, one)
            check("bench counts present", one.get("ready_now_count") == 1, one)
            c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                dimension_kind="mobility_preference", title_en="Lateral finance", source="employee_declared",
                reason="interest",
            )
            mob = pt5.discover_mobility(cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, reason="discover")
            check("mobility ok", mob.get("ok") is True, mob)
            check("advisory only", mob.get("is_not_application") is True and mob.get("candidate_created") is False, mob)
            check("no employment mutate", mob.get("employment_mutated") is False, mob)
            handoff = pt5.refer_to_internal_opportunity(
                cur, company_code=COMPANY, match_id=str((mob.get("matches") or [{}])[0].get("match_id") or uuid.uuid4()), reason="handoff"
            )
            check("no silent application", handoff.get("application_created") is not True, handoff)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT5_SUCCESSION_MOBILITY_INTELLIGENCE_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
