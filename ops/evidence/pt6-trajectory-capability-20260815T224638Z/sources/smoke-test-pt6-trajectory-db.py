#!/usr/bin/env python3
"""PT6 — Trajectory + holder-dependency staging DB journeys."""
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
COMPANY = f"PT6{_N:05d}"[:12].upper()
HR = f"9657600{_N:05d}"
EMP = f"{COMPANY}-PT6-{SUFFIX}"
EMP_PHONE = f"9657601{_N:05d}"


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
    print("    pt6 trajectory — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    import talent_profile_c5 as c5
    import talent_trajectory_pt6 as pt6

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
            pt6.ensure_talent_trajectory_pt6_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now()) ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PT6 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, EMP, EMP_PHONE, "PT6 Emp", date(2036, 1, 1), date(2036, 1, 1)),
            )
            c5.enable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="c5")
            none = pt6.evaluate_trajectory(cur, company_code=COMPANY, employee_key=EMP, reason="no policy")
            check("no policy → no label", none.get("label") is None and none.get("reason") == "policy_not_published", none)
            pub = pt6.publish_trajectory_policy(cur, company_code=COMPANY, actor_phone=HR, reason="publish")
            check("publish policy", pub.get("ok") is True, pub)
            short = pt6.evaluate_trajectory(cur, company_code=COMPANY, employee_key=EMP, reason="short history")
            check("insufficient history → no label", short.get("label") is None and short.get("reason") == "insufficient_history", short)
            claimed = c5.claim_skill(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                skill_code="UNIQUE", name_en="Unique", reason="claim",
            )
            c5.verify_skill(cur, company_code=COMPANY, actor_phone=HR, skill_id=str(claimed["skill"]["skill_id"]), reason="verify")
            before = pt6.capability_facts(cur, company_code=COMPANY)
            dep = pt6.holder_dependency(cur, company_code=COMPANY, employee_key=EMP)
            after = pt6.capability_facts(cur, company_code=COMPANY)
            check("holder dep changes analytic coverage", "UNIQUE" in (dep.get("vulnerable_capabilities") or []), dep)
            check("employment not mutated", dep.get("employment_mutated") is False, dep)
            check("baseline coverage unchanged after dep", before.get("capability_coverage") == after.get("capability_coverage"), (before, after))
            cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
            status = str(dict(cur.fetchone() or {}).get("employment_status") or "")
            check("employee still active", status == "active", status)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
