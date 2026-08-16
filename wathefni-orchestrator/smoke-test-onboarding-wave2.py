#!/usr/bin/env python3
"""Onboarding Wave 2 — staging/local operational completeness smoke.

Covers: template/versioning, seed idempotency, mark concurrency, dependencies,
due dates, delayed start, reschedule, cancel, bank ESS freeze, tenant fail-closed.
Does not touch production four-real checklists.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    print("=== Onboarding Wave 2 smoke ===")
    import onboarding_wave2 as w2
    import app

    # Offline template / model
    check("template version 2.0.0", w2.CANONICAL_TEMPLATE_VERSION == "2.0.0")
    bank = w2.get_template_item("bank_details")
    check("bank is ESS authority", bank and bank.authority == "ess" and bank.collection_mode == "ess_encrypted", bank)
    mirrors = [i for i in w2.DEFAULT_KUWAIT_V2 if i.authority == "compliance_mirror"]
    check("compliance mirrors present", len(mirrors) >= 4, len(mirrors))
    check("deps on first_day_checklist", bool(w2.get_template_item("first_day_checklist").depends_on))
    check("transition model has cancelled", "cancelled" in w2.transition_model()["states"])
    plan = w2.plan_legacy_migration([])
    check("migration plan read-only", plan.get("applied") is False and plan["policy"]["production_apply"] is False)
    check("plan mode read_only", plan.get("mode") == "read_only_plan")

    # Flags: this smoke enables SEED/HR_MUTATE only in-process for synthetic work
    saved_seed = os.environ.get("WATHEFNI_ONBOARDING_SEED")
    saved_mut = os.environ.get("WATHEFNI_ONBOARDING_HR_MUTATE")
    os.environ["WATHEFNI_ONBOARDING_SEED"] = "on"
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "on"
    check("seed on for synthetic", app.onboarding_seed_enabled() is True)
    check("hr mutate on for synthetic", app.onboarding_hr_mutate_enabled() is True)

    if not (os.environ.get("DATABASE_URL") or os.environ.get("WATHEFNI_POSTGRES_ENV")):
        print("SKIP DB behavioural: no database env")
        _restore(saved_seed, saved_mut)
        print(f"RESULT pass={PASS} fail={FAIL}")
        return 1 if FAIL else 0

    app.ensure_schema()
    suffix = uuid.uuid4().hex[:8]
    company = f"W2OB{suffix[:4]}".upper()
    emp = f"{company}-SYN{suffix}"
    other = f"X{company[:4]}"
    emp_other = f"{other}-Z{suffix}"

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for code in (company, other):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata) VALUES (%s,%s,'{}'::jsonb) ON CONFLICT DO NOTHING",
                    (code, f"Wave2 {code}"),
                )
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, onboarding_status, documents_pending, documents_complete, start_date)
                VALUES (%s,%s,'Wave2 Syn',%s,'not_started',0,0,%s)
                ON CONFLICT (employee_key) DO NOTHING
                """,
                (emp, company, f"96570{suffix[:6]}", date.today() + timedelta(days=7)),
            )
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, onboarding_status)
                VALUES (%s,%s,'Other',%s,'not_started') ON CONFLICT DO NOTHING
                """,
                (emp_other, other, f"96571{suffix[:6]}"),
            )
        conn.commit()

    try:
        employee = {"employee_key": emp, "company_code": company, "name": "Wave2 Syn", "phone": "1", "onboarding_status": "not_started", "start_date": date.today() + timedelta(days=7)}

        # Delayed start
        delayed = app.start_onboarding(employee, planned_start_date=date.today() + timedelta(days=7), delayed=True)
        check("delayed start ok", delayed.get("ok") and delayed.get("status") == "delayed", delayed)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                items = app.load_onboarding_items(employee_key=emp, company_code=company, cur=cur)
        check("delayed does not seed yet", len(items) == 0, len(items))

        # Activate delayed early via reschedule to today then activate
        res = app.reschedule_employee_onboarding(
            {"employee_key": emp, "planned_start_date": date.today().isoformat()},
            company_code=company,
        )
        check("reschedule ok", res.get("ok") is True, res)

        # Start in progress + seed
        started = app.start_onboarding(employee, planned_start_date=date.today(), delayed=False, allow_restart=True)
        check("start in_progress", started.get("ok") and started.get("status") == "in_progress", started)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                items = app.load_onboarding_items(employee_key=emp, company_code=company, cur=cur)
                seeded = len(items)
                seeded2 = app.seed_onboarding_items(cur, employee)
                asg = w2.get_assignment(cur, emp)
            conn.commit()
        check("seeded template rows", seeded > 10, seeded)
        check("seed idempotent", seeded2 == 0, seeded2)
        check("assignment pinned version", asg and asg.get("template_version") == "2.0.0", asg)
        bank_row = next((i for i in items if i.get("item_id") == "bank_details"), None)
        check("bank collection_mode ess", bank_row and bank_row.get("collection_mode") == "ess_encrypted", bank_row)
        due_rows = [i for i in items if i.get("due_date")]
        check("due dates populated", len(due_rows) > 0, len(due_rows))

        # Duplicate start idempotent
        again = app.start_onboarding(employee, allow_restart=False)
        check("duplicate start idempotent", again.get("ok") and again.get("idempotent") is True, again)

        # Dependency: residence blocked until civil_id
        mark_res = app.mark_onboarding_item(
            {"employee_key": emp, "item_id": "residence", "item_status": "received"},
            company_code=company,
            created_by_phone=None,
        )
        check("dependency blocks residence", mark_res.get("ok") is False and mark_res.get("error") == "dependency_unsatisfied", mark_res)

        items = app.load_onboarding_items(employee_key=emp, company_code=company)
        civil = next(i for i in items if i["item_id"] == "civil_id")
        mark_civil = app.mark_onboarding_item(
            {"employee_key": emp, "item_id": "civil_id", "item_status": "received", "expected_row_version": civil.get("row_version")},
            company_code=company,
            created_by_phone="96570000000",
        )
        check("mark civil received", mark_civil.get("ok") is True, mark_civil)
        check("audit event on mark", bool(mark_civil.get("audit_event_id")), mark_civil)

        # Stale version fail closed (reuse pre-mark version)
        stale = app.mark_onboarding_item(
            {"employee_key": emp, "item_id": "civil_id", "item_status": "waived", "expected_row_version": civil.get("row_version")},
            company_code=company,
            created_by_phone="96570000000",
        )
        check("stale mark fail closed", stale.get("ok") is False and stale.get("error") == "stale_item_version", stale)

        # Waive + bank freeze
        photo = next(i for i in app.load_onboarding_items(employee_key=emp, company_code=company) if i["item_id"] == "personal_photo")
        waive = app.mark_onboarding_item(
            {"employee_key": emp, "item_id": "personal_photo", "item_status": "waived", "expected_row_version": photo.get("row_version")},
            company_code=company,
            created_by_phone="96570000000",
        )
        check("waive ok", waive.get("ok") is True, waive)
        bank_block = app.mark_onboarding_item(
            {"employee_key": emp, "item_id": "bank_details", "item_status": "received", "value": "NBK KW81NBOK0000000000000000123456"},
            company_code=company,
            created_by_phone="96570000000",
        )
        check("bank plaintext mark blocked", bank_block.get("error") == "bank_via_ess_required", bank_block)
        ok_bank, reason = app.validate_onboarding_item_receipt("bank_details", "NBK KW81NBOK0000000000000000123456", None)
        check("bank receipt blocked", ok_bank is False and reason == "bank_via_ess_required", reason)

        # Tenant isolation
        leaked = app.load_onboarding_items(employee_key=emp, company_code=other)
        check("wrong tenant empty", leaked == [], leaked)

        # Cancel preserves history
        cancel = app.cancel_employee_onboarding({"employee_key": emp, "reason": "withdrawn"}, company_code=company)
        check("cancel ok", cancel.get("ok") and cancel.get("history_preserved") is True, cancel)
        after_cancel = app.load_onboarding_items(employee_key=emp, company_code=company)
        check("cancel keeps rows", len(after_cancel) > 0, len(after_cancel))
        restart_blocked = app.start_onboarding(employee, allow_restart=False)
        check("restart blocked when cancelled", restart_blocked.get("ok") is False, restart_blocked)

        # Migration plan for empty/synthetic shape
        mig = w2.plan_legacy_migration([
            {"employee_key": "WATHEFNI-96599411617", "name": "Brian", "item_id": "personal_photo", "status": "pending", "reminder_count": 0},
        ])
        brian = next(e for e in mig["employees"] if e["employee_key"].endswith("411617"))
        check("brian partial flagged", brian.get("brian_partial") is True, brian)

    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM onboarding_audit_events WHERE employee_key=%s", (emp,))
                cur.execute("DELETE FROM employee_onboarding_assignments WHERE employee_key=%s", (emp,))
                cur.execute("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", ([emp, emp_other],))
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", ([emp, emp_other],))
                cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([company, other],))
            conn.commit()
        _restore(saved_seed, saved_mut)

    print(f"\nRESULT pass={PASS} fail={FAIL}")
    return 1 if FAIL else 0


def _restore(saved_seed, saved_mut):
    if saved_seed is None:
        os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
    else:
        os.environ["WATHEFNI_ONBOARDING_SEED"] = saved_seed
    if saved_mut is None:
        os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
    else:
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = saved_mut


if __name__ == "__main__":
    raise SystemExit(main())
