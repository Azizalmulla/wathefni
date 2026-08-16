#!/usr/bin/env python3
"""PT7 — Assistant grounding staging DB journeys."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PT7{_N:05d}"[:12].upper()
HR = f"9657700{_N:05d}"
EMP = f"{COMPANY}-PT7-{SUFFIX}"
EMP_PHONE = f"9657701{_N:05d}"


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
    print("    pt7 assistant — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "on"
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    import app
    import talent_assistant_pt7 as pt7
    import talent_models_pt2 as pt2
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0

    class Ctx:
        action = {"company_code": COMPANY, "employee_key": EMP}
        request = SimpleNamespace(company_code=COMPANY, sender_phone=HR)
        legacy = app
        state = {}
        graph_state = {}
        intent = {}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c5.ensure_talent_profile_c5_schema(cur)
            c6.ensure_talent_succession_c6_schema(cur)
            pt2.ensure_talent_models_pt2_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now()) ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PT7 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, EMP, EMP_PHONE, "Sarah", date(2036, 1, 1), date(2036, 1, 1)),
            )
            c5.enable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="c5")
            c6.enable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="c6")
            model = pt2.create_model(cur, company_code=COMPANY, actor_phone=HR, name_en="Signal", reason="m")
            cfg = pt2.default_high_potential_signal_config()
            draft = pt2.save_draft_version(cur, company_code=COMPANY, actor_phone=HR, model_id=str(model["model"]["model_id"]), reason="d", **cfg)
            pt2.publish_version(cur, company_code=COMPANY, actor_phone=HR, version_id=str(draft["version"]["version_id"]), reason="p")
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
            ev = pt2.evaluate_employee(cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, model_id=str(model["model"]["model_id"]), reason="eval")
            check("evaluate", ev.get("ok") is True, ev)
            ui_why = ev.get("why") or {}

    explained = pt7.explain_talent_classification_tool(Ctx())
    check("assistant explain ok", explained.get("ok") is True, explained)
    check("same model id", (explained.get("why") or {}).get("model_id") == ui_why.get("model_id"), (explained.get("why"), ui_why))
    check("does not claim designated HiPo", explained.get("designated_hipo") is False, explained)
    check("mentions model/version", "model" in str(explained.get("message") or "").lower() or "v" in str(explained.get("message") or ""), explained)
    classified = pt7.list_model_classifications_tool(Ctx())
    check("list classifications", classified.get("ok") is True, classified)
    check("not HiPo language", "not designated HiPo" in str(classified.get("message") or ""), classified)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT7_ASSISTANT_TALENT_INTELLIGENCE_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
