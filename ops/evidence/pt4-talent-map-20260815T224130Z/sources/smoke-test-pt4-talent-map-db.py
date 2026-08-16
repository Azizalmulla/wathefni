#!/usr/bin/env python3
"""PT4 — Talent Map staging DB journeys."""
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
COMPANY = f"PT4{_N:05d}"[:12].upper()
HR = f"9657400{_N:05d}"
EMP = f"{COMPANY}-PT4-{SUFFIX}"
EMP_PHONE = f"9657401{_N:05d}"


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
    print("    pt4 talent map — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "on"
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    import talent_map_pt4 as pt4
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6

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
            pt4.ensure_talent_map_pt4_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now()) ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PT4 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, EMP, EMP_PHONE, "PT4 Emp", date(2036, 1, 1), date(2036, 1, 1)),
            )
            check("enable", c5.enable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="c5").get("ok") is True)
            c6.enable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="c6")
            c5.ensure_talent_profile(cur, company_code=COMPANY, employee_key=EMP, actor_phone=HR)
            fw = c5.create_potential_framework(
                cur, company_code=COMPANY, actor_phone=HR, name_en="G",
                dimensions=[{"key": "l", "label_en": "L", "label_ar": "ل"}],
                scale_points=[{"code": "high", "label_en": "H", "label_ar": "ع"}],
                reason="fw",
            )
            c5.submit_potential_assessment(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                framework_id=str(fw["framework"]["framework_id"]), rationale="high",
                dimension_scores={"l": "high"}, resulting_level="high",
                has_sensitive_permission=True, reason="pot",
            )
            m1 = pt4.build_map(cur, company_code=COMPANY, lens="perf_x_potential")
            m2 = pt4.build_map(cur, company_code=COMPANY, lens="potential_x_readiness")
            check("map ok", m1.get("ok") is True, m1)
            check("second lens ok", m2.get("ok") is True, m2)
            p1 = next((p for p in m1.get("placements") or [] if p.get("employee_key") == EMP), None)
            p2 = next((p for p in m2.get("placements") or [] if p.get("employee_key") == EMP), None)
            check("placement exists", p1 is not None, m1)
            check("missing perf is unknown", bool(p1 and p1.get("unknown") is True), p1)
            check("not stuffed in middle", bool(p1 and p1.get("cell") is None and p1.get("forced_middle") is False), p1)
            check(
                "same canonical potential",
                bool(p1 and p2 and p1["canonical_facts"]["human_potential"] == p2["canonical_facts"]["human_potential"] == "high"),
                (p1, p2),
            )
            check(
                "same designated hipo",
                bool(p1 and p2 and p1["canonical_facts"]["designated_hipo"] is False and p2["canonical_facts"]["designated_hipo"] is False),
            )
            why = pt4.get_placement_why(cur, company_code=COMPANY, employee_key=EMP, lens="perf_x_potential")
            check("why present", why.get("ok") is True, why)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT4_DYNAMIC_TALENT_MAP_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
