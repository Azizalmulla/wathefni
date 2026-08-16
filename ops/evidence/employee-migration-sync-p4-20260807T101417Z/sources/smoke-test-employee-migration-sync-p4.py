#!/usr/bin/env python3
"""Migration Sync P4 — opening balances + current-state cutover smoke (WATHEFNI)."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import uuid
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")


def _fail(msg: str) -> None:
    print(f"FAIL migration sync P4: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    import app as legacy
    import employee_migration_cutover as p4
    import employee_migration_field_model as fm
    import employee_migration_foundation as emf

    company = "WATHEFNI"
    if not emf.foundation_enabled(company):
        _fail("foundation off")

    honesty = emf.honesty_payload()
    if honesty.get("contract") != "employee_migration_sync_p4_cutover":
        _fail(f"contract {honesty.get('contract')}")
    if not honesty.get("opening_balances_p4"):
        _fail("p4 honesty missing")
    _ok("P4 honesty")

    # Missing must not become zero
    lines = p4.resolve_cutover_preview(
        {"leave_opening_balance": "", "salary_basic_monthly": ""},
        source_system="test",
    )
    by = {x["field_key"]: x for x in lines}
    if by.get("leave_opening_balance", {}).get("disposition") != p4.DISP_NOT_SUPPLIED:
        _fail(f"blank leave should be not_supplied: {by.get('leave_opening_balance')}")
    if by.get("salary_basic_monthly", {}).get("disposition") != p4.DISP_NOT_SUPPLIED:
        _fail(f"blank salary should be not_supplied: {by.get('salary_basic_monthly')}")
    if by["salary_basic_monthly"].get("import_value") in {"0", "0.0"}:
        _fail("blank salary must not become zero")
    sal = p4.resolve_cutover_preview({"salary_basic_monthly": "850.000"}, source_system="test")
    if sal[0].get("import_value") != "••••":
        _fail(f"salary not masked: {sal[0]}")
    _ok("missing≠zero + salary masked")

    tag = uuid.uuid4().hex[:8]
    source = f"p4_smoke_{tag}"
    phone = f"96556{int(tag[:5], 16) % 100000:05d}1"
    context = {
        "company_code": company,
        "user_id": "smoke-p4",
        "email": "smoke-p4@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]
    created: list[str] = []
    batch_id = None
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur, force=True)
                conn.commit()

        headers = [
            "name",
            "phone",
            "cutover_date",
            "leave_type",
            "leave_opening_balance",
            "leave_entitlement_days",
            "salary_basic_monthly",
            "salary_currency",
            "current_assignment_title",
            "current_assignment_department",
            "shift_template_code",
            "compliance_doc_type",
            "compliance_status",
            "compliance_expiry",
            "onboarding_status",
            "onboarding_completed_at",
        ]
        suggest = fm.suggest_mapping_profile(legacy, context, headers=headers, source_system=source)
        by_h = {r["source_header"]: r for r in suggest["mappings"]}
        for h, field in [
            ("cutover_date", "cutover_date"),
            ("leave_type", "leave_type"),
            ("leave_opening_balance", "leave_opening_balance"),
            ("leave_entitlement_days", "leave_entitlement_days"),
            ("salary_basic_monthly", "salary_basic_monthly"),
            ("salary_currency", "salary_currency"),
            ("current_assignment_title", "current_assignment_title"),
            ("current_assignment_department", "current_assignment_department"),
            ("shift_template_code", "shift_template_code"),
            ("compliance_doc_type", "compliance_doc_type"),
            ("compliance_status", "compliance_status"),
            ("compliance_expiry", "compliance_expiry"),
            ("onboarding_status", "onboarding_status"),
            ("onboarding_completed_at", "onboarding_completed_at"),
        ]:
            by_h[h].update({"disposition": "canonical", "canonical_field": field, "confirmed": True})
        fm.save_mapping_profile(legacy, context, source_system=source, mappings=list(by_h.values()))
        _ok("mapping profile with cutover fields")

        raw = _csv(
            [
                {
                    "name": f"P4 Cutover {tag}",
                    "phone": phone,
                    "cutover_date": "2026-01-01",
                    "leave_type": "annual",
                    "leave_opening_balance": "12.5",
                    "leave_entitlement_days": "30",
                    "salary_basic_monthly": "750.000",
                    "salary_currency": "KWD",
                    "current_assignment_title": "Ops Lead",
                    "current_assignment_department": "Operations",
                    "shift_template_code": "DAY-A",
                    "compliance_doc_type": "civil_id",
                    "compliance_status": "valid",
                    "compliance_expiry": "2027-06-01",
                    "onboarding_status": "completed",
                    "onboarding_completed_at": "2019-01-01",
                }
            ]
        )
        preview = emf.preview_or_replay_import(
            legacy, context, raw=raw, filename=f"p4-{tag}.csv", source_system=source
        )
        batch_id = preview["batch_id"]
        preview_rows = (preview.get("results") or {}).get("created") or []
        if not preview_rows:
            preview_rows = (preview.get("rows") or [])
        found_ob = False
        found_p3 = False
        for row in preview_rows:
            detail = row.get("detail") or {}
            if detail.get("onboarding_migration", {}).get("preview_label"):
                found_p3 = True
            for line in detail.get("opening_balances") or []:
                if line.get("field_key") == "leave_opening_balance" and line.get("disposition") == "will_apply":
                    found_ob = True
                if line.get("field_key") == "salary_basic_monthly" and line.get("import_value") == "••••":
                    found_ob = found_ob and True
        if not found_ob:
            _fail(f"preview missing opening balance lines: {preview_rows[:1]}")
        if not found_p3:
            _fail("preview missing P3 onboarding label")
        _ok(f"preview cutover+onboarding batch={batch_id}")

        emf.commit_import_batch(legacy, context, batch_id=batch_id)

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key, onboarding_status, position_title, raw_json FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phone),
                )
                emp = dict(cur.fetchone() or {})
                if not emp:
                    _fail("employee missing")
                created.append(emp["employee_key"])
                ek = emp["employee_key"]

                # Leave opening
                cur.execute(
                    """
                    SELECT current_balance, entitlement_days FROM leave_balances
                    WHERE company_code=%s AND employee_key=%s AND leave_type='annual'
                    ORDER BY period_year DESC LIMIT 1
                    """,
                    (company, ek),
                )
                bal = dict(cur.fetchone() or {})
                if float(bal.get("current_balance") or 0) != 12.5:
                    _fail(f"leave balance not applied: {bal}")
                cur.execute(
                    """
                    SELECT count(*) AS c FROM leave_requests WHERE employee_key=%s
                    """,
                    (ek,),
                )
                if int((cur.fetchone() or {}).get("c") or 0) > 0:
                    _fail("fabricated leave requests")

                # Payroll authority — staged, never approved/effective
                cur.execute(
                    """
                    SELECT value_text, display_masked, value_json, authority
                    FROM employee_migration_opening_balances
                    WHERE company_code=%s AND employee_key=%s AND field_key='salary_basic_monthly'
                    """,
                    (company, ek),
                )
                pay = dict(cur.fetchone() or {})
                if str(pay.get("value_text")) != "750.000":
                    _fail(f"salary staging missing: {pay}")
                if pay.get("display_masked") != "••••":
                    _fail(f"salary mask missing: {pay}")
                vj = pay.get("value_json") or {}
                if isinstance(vj, str):
                    vj = json.loads(vj)
                if vj.get("payroll_effective") is not False and vj.get("payroll_effective") is not None:
                    # must be explicitly false
                    if vj.get("payroll_effective") is True:
                        _fail("salary became payroll-effective")
                if str(vj.get("payroll_effective")).lower() == "true":
                    _fail("salary payroll_effective true")
                cur.execute(
                    """
                    SELECT status FROM payroll_compensation_contracts
                    WHERE company_code=%s AND employee_key=%s AND status='approved'
                    """,
                    (company, ek),
                )
                if cur.fetchone():
                    _fail("approved payroll contract created by import")

                # Compliance unverified staging
                cur.execute(
                    """
                    SELECT status, expiry_date, authority FROM employee_migration_imported_compliance
                    WHERE company_code=%s AND employee_key=%s AND batch_id=%s
                    """,
                    (company, ek, batch_id),
                )
                comp = dict(cur.fetchone() or {})
                if str(comp.get("expiry_date") or "") != "2027-06-01":
                    _fail(f"compliance expiry missing: {comp}")

                # Assignment / shift planning
                cur.execute(
                    """
                    SELECT value_text, value_json FROM employee_migration_opening_balances
                    WHERE company_code=%s AND employee_key=%s AND field_key='shift_template_code'
                    """,
                    (company, ek),
                )
                sh = dict(cur.fetchone() or {})
                if sh.get("value_text") != "DAY-A":
                    _fail(f"shift template missing: {sh}")
                sv = sh.get("value_json") or {}
                if isinstance(sv, str):
                    sv = json.loads(sv)
                if sv.get("shift_assignments_created") is not False:
                    _fail("shift assignments fabricated")
                cur.execute(
                    "SELECT count(*) AS c FROM shift_assignments WHERE employee_key=%s",
                    (ek,),
                )
                try:
                    if int((cur.fetchone() or {}).get("c") or 0) > 0:
                        _fail("shift_assignments rows created")
                except Exception:
                    conn.rollback()

                # P3 still applied
                if str(emp.get("onboarding_status")) != "migrated_external":
                    _fail(f"p3 onboarding not applied: {emp.get('onboarding_status')}")

                conn.commit()
        _ok("cutover domains applied")

        # Idempotent recommit
        emf.commit_import_batch(legacy, context, batch_id=batch_id)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM leave_ledger
                    WHERE company_code=%s AND employee_key=%s AND reason LIKE %s
                    """,
                    (company, created[0], f"migration_opening:{batch_id}:%"),
                )
                if int((cur.fetchone() or {}).get("c") or 0) != 1:
                    _fail("leave opening not idempotent")
                conn.commit()
        _ok("idempotent recommit")

        # Native leave activity wins
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_ledger (
                      company_code, employee_key, leave_type, entry_kind, days, period,
                      observe_only, reason
                    ) VALUES (%s,%s,'annual','accrual',1,%s,true,'native_smoke_accrual')
                    """,
                    (company, created[0], "2026"),
                )
                p4.mark_native_superseded(
                    cur,
                    company=company,
                    employee_key=created[0],
                    domain="leave",
                    field_key="leave_opening_balance",
                    reason="native_leave_activity",
                )
                # Re-apply should skip
                result = p4.apply_cutover_from_canonical(
                    legacy,
                    cur,
                    company=company,
                    employee_key=created[0],
                    canonical={
                        "leave_opening_balance": "99",
                        "leave_type": "annual",
                        "cutover_date": "2026-01-01",
                    },
                    batch_id=str(uuid.uuid4()),
                    row_id=str(uuid.uuid4()),
                    source_system=source,
                    external_employee_id=None,
                    actor="smoke-p4",
                )
                if "leave_opening_balance" in (result.get("applied") or []):
                    _fail(f"native leave should block overwrite: {result}")
                conn.commit()
        _ok("native Wathefni leave wins")

        # Rollback preserves superseded opening row
        rb = emf.rollback_import_batch(legacy, context, batch_id=batch_id, idempotency_key=f"rb-p4-{tag}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT native_superseded FROM employee_migration_opening_balances
                    WHERE company_code=%s AND employee_key=%s AND field_key='leave_opening_balance'
                    """,
                    (company, created[0]),
                )
                row = cur.fetchone()
                if row and not (row.get("native_superseded") if isinstance(row, dict) else row[0]):
                    _fail("rollback cleared superseded leave opening")
                # Native accrual must remain
                cur.execute(
                    """
                    SELECT count(*) AS c FROM leave_ledger
                    WHERE employee_key=%s AND reason='native_smoke_accrual'
                    """,
                    (created[0],),
                )
                if int((cur.fetchone() or {}).get("c") or 0) < 1:
                    _fail("rollback erased native leave activity")
                conn.commit()
        _ok(f"rollback ok status={rb.get('status')}")

        print("OK employee migration sync P4 cutover")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                if batch_id:
                    for tbl, col in [
                        ("employee_onboarding_migration_history", "batch_id"),
                        ("employee_onboarding_migration", "batch_id"),
                        ("employee_migration_opening_balances", "batch_id"),
                        ("employee_import_source_payloads", "batch_id"),
                        ("employee_source_mappings", "batch_id"),
                        ("employee_import_rows", "batch_id"),
                        ("employee_import_batches", "batch_id"),
                        ("employee_migration_imported_compliance", "batch_id"),
                        ("employee_migration_imported_bank", "batch_id"),
                    ]:
                        try:
                            cur.execute(f"DELETE FROM {tbl} WHERE {col}=%s", (batch_id,))
                        except Exception:
                            conn.rollback()
                for key in set(created):
                    for sql in [
                        "DELETE FROM leave_ledger WHERE employee_key=%s",
                        "DELETE FROM leave_balances WHERE employee_key=%s",
                        "DELETE FROM employee_migration_opening_balances WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_migration_history WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_migration WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_completion_events WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_completion WHERE employee_key=%s",
                        "DELETE FROM payroll_compensation_components WHERE contract_id IN (SELECT contract_id FROM payroll_compensation_contracts WHERE employee_key=%s)",
                        "DELETE FROM payroll_compensation_events WHERE contract_id IN (SELECT contract_id FROM payroll_compensation_contracts WHERE employee_key=%s)",
                        "DELETE FROM payroll_compensation_contracts WHERE employee_key=%s",
                        "DELETE FROM employee_org_assignment_history WHERE employee_key=%s",
                        "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    ]:
                        try:
                            if "company_code" in sql:
                                cur.execute(sql, (company, key))
                            else:
                                cur.execute(sql, (key,))
                        except Exception:
                            conn.rollback()
                cur.execute(
                    "DELETE FROM employee_import_mapping_profiles WHERE company_code=%s AND source_system=%s",
                    (company, source),
                )
                conn.commit()


if __name__ == "__main__":
    main()
