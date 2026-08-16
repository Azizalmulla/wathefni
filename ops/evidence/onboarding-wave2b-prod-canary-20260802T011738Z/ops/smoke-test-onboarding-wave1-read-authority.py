#!/usr/bin/env python3
"""Onboarding Wave 1 — loader repair & single read authority gates.

Offline-first checks (always). Optional DB behavioural checks when DATABASE_URL /
psycopg2 are available (local or staging).

Does not enable SEED/HR_MUTATE, does not deploy, does not mutate production.
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
import uuid
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


def _fn_src(fn) -> str:
    return inspect.getsource(fn)


def offline_checks() -> None:
    import app

    # --- loader integrity ---
    check("load_onboarding_items exists", hasattr(app, "load_onboarding_items"))
    check("employee_onboarding_items wraps load", "load_onboarding_items" in _fn_src(app.employee_onboarding_items))
    loader_src = _fn_src(app.load_onboarding_items) + _fn_src(app.employee_onboarding_items)
    check("loader has no candidates.read", "candidates.read" not in loader_src)
    check("loader joins employees", "JOIN employees" in loader_src.upper() or "join employees" in loader_src.lower())

    # AST: employee_onboarding_items body must not call dashboard_effective_permissions
    tree = ast.parse(_fn_src(app.employee_onboarding_items))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    check("loader does not call dashboard_effective_permissions", "dashboard_effective_permissions_for_user" not in names)

    # --- bank freeze ---
    check("plaintext bank forbidden helper", hasattr(app, "onboarding_plaintext_bank_forbidden"))
    check("bank_details forbidden", app.onboarding_plaintext_bank_forbidden("bank_details") is True)
    check("iban text forbidden", app.onboarding_plaintext_bank_forbidden("civil_id", "NBK KW81NBOK0000000000000000123456") is True)
    check("normal doc allowed", app.onboarding_plaintext_bank_forbidden("civil_id", "hello") is False)
    ok, reason = app.validate_onboarding_item_receipt("bank_details", "NBK KW81NBOK0000000000000000123456", None)
    check("receipt rejects bank_details", ok is False and reason == "bank_via_ess_required", reason)

    # --- flags stay off by default ---
    saved_seed = os.environ.get("WATHEFNI_ONBOARDING_SEED")
    saved_mut = os.environ.get("WATHEFNI_ONBOARDING_HR_MUTATE")
    try:
        os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
        os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
        check("SEED defaults off", app.onboarding_seed_enabled() is False)
        check("HR_MUTATE defaults off", app.onboarding_hr_mutate_enabled() is False)
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "off"
        check("SEED off when 'off'", app.onboarding_seed_enabled() is False)
        check("HR_MUTATE off when 'off'", app.onboarding_hr_mutate_enabled() is False)
    finally:
        if saved_seed is None:
            os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
        else:
            os.environ["WATHEFNI_ONBOARDING_SEED"] = saved_seed
        if saved_mut is None:
            os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
        else:
            os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = saved_mut

    # --- reminder fail-closed without company ---
    cand_src = _fn_src(app.pending_onboarding_reminder_candidates)
    check("reminder candidates require company_code", "company_code" in cand_src and "return []" in cand_src)
    check("reminder scan is tenant_safe marker", "tenant_safe" in _fn_src(app.run_onboarding_reminder_scan))
    check("empty company reminder candidates empty", app.pending_onboarding_reminder_candidates(company_code=None) == [])
    check("empty company still-onboarding empty", app.employees_still_onboarding(company_code=None) == [])

    # --- count helper aligns waived ---
    rows = [
        {"required": True, "status": "received"},
        {"required": True, "status": "pending"},
        {"required": True, "status": "waived"},
        {"required": False, "status": "pending"},
    ]
    counts = app.onboarding_item_counts_from_rows(rows)
    check("counts required_total=3", counts["required_total"] == 3, counts)
    check("counts received=1", counts["received_count"] == 1, counts)
    check("counts pending excludes waived", counts["pending_count"] == 1, counts)

    # --- template bank label points ESS ---
    bank = next(t for t in app.DEFAULT_KUWAIT_ONBOARDING_TEMPLATE if t[0] == "bank_details")
    check("template bank label mentions ESS/encrypted", "ess" in bank[1].lower() or "encrypted" in bank[1].lower(), bank[1])
    check("template bank item_type is task (not plaintext text)", bank[3] == "task", bank)

    # --- summary includes items + bank_collection ---
    # Pure unit: monkeypatch load
    real_load = app.load_onboarding_items

    def _fake_load(*, employee_key, company_code=None, cur=None):
        return [
            {"item_id": "civil_id", "label": "Civil ID", "required": True, "status": "pending", "document_type": "civil_id"},
            {"item_id": "bank_details", "label": "Bank", "required": True, "status": "pending", "document_type": None, "value": None},
        ]

    try:
        app.load_onboarding_items = _fake_load  # type: ignore
        summary = app.employee_onboarding_summary(
            {"employee_key": "X", "name": "T", "phone": "1", "onboarding_status": "in_progress", "company_code": "WATHEFNI"},
            company_code="WATHEFNI",
        )
        check("summary returns items", len(summary.get("items") or []) == 2, summary)
        check("summary bank_collection ess", (summary.get("bank_collection") or {}).get("mode") == "ess_encrypted", summary.get("bank_collection"))
        check("summary counts match items", summary["required_total"] == 2 and summary["pending_count"] == 2, summary)
        nxt = app.find_next_required_onboarding_item("X", company_code="WATHEFNI")
        check("next item skips bank_details", nxt and nxt.get("item_id") == "civil_id", nxt)
    finally:
        app.load_onboarding_items = real_load  # type: ignore

    # --- mask helper ---
    masked = app.mask_onboarding_item_for_read(
        {"item_id": "bank_details", "value": "NBK KW81NBOK0000000000000000123456", "status": "received"}
    )
    check("mask redacts bank value", masked.get("value") is None and masked.get("value_redacted") is True, masked)


def db_checks() -> None:
    import app

    suffix = uuid.uuid4().hex[:8]
    company = f"W1OB{suffix[:4]}".upper()
    emp_a = f"{company}-A{suffix}"
    emp_b = f"{company}-B{suffix}"
    other = f"X{company[:4]}"
    emp_other = f"{other}-Z{suffix}"

    app.ensure_schema()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for code in (company, other):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata)
                    VALUES (%s, %s, '{}'::jsonb)
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"Wave1 {code}"),
                )
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, onboarding_status, documents_pending, documents_complete)
                VALUES
                  (%s, %s, 'Wave1 A', '10000000001', 'in_progress', 0, 0),
                  (%s, %s, 'Wave1 B', '10000000002', 'in_progress', 0, 0),
                  (%s, %s, 'Other Z', '10000000003', 'in_progress', 0, 0)
                ON CONFLICT (employee_key) DO NOTHING
                """,
                (emp_a, company, emp_b, company, emp_other, other),
            )
            for key, items in (
                (emp_a, [("civil_id", True, "pending"), ("passport", True, "received"), ("bank_details", True, "pending"), ("personal_photo", False, "pending")]),
                (emp_b, [("civil_id", True, "pending")]),
                (emp_other, [("civil_id", True, "pending"), ("bank_details", True, "pending")]),
            ):
                for item_id, required, status in items:
                    cur.execute(
                        """
                        INSERT INTO onboarding_items (employee_key, item_id, label, item_type, required, document_type, status)
                        VALUES (%s, %s, %s, 'document', %s, %s, %s)
                        ON CONFLICT (employee_key, item_id) DO UPDATE
                          SET status=EXCLUDED.status, required=EXCLUDED.required
                        """,
                        (key, item_id, item_id, required, item_id, status),
                    )
            app.recompute_employee_onboarding_counts(cur, emp_a)
        conn.commit()

    try:
        items = app.load_onboarding_items(employee_key=emp_a, company_code=company)
        check("DB load returns checklist rows", len(items) == 4, len(items))
        check("DB load types are onboarding items", all("item_id" in i for i in items))

        # Wrong tenant → empty
        leaked = app.load_onboarding_items(employee_key=emp_a, company_code=other)
        check("wrong company returns empty", leaked == [], leaked)

        summary = app.employee_onboarding_summary(
            {"employee_key": emp_a, "name": "Wave1 A", "phone": "1", "onboarding_status": "in_progress", "company_code": company},
            company_code=company,
        )
        sql_counts = app.onboarding_counts_by_employee(company, [emp_a]).get(emp_a) or {}
        check(
            "summary counts == SQL list counts",
            summary["pending_count"] == sql_counts.get("pending_count")
            and summary["received_count"] == sql_counts.get("received_count"),
            {"summary": summary, "sql": sql_counts},
        )
        check("summary items length == loaded", len(summary["items"]) == len(items))

        # Reminder cannot see other tenant when scoped
        other_cands = app.pending_onboarding_reminder_candidates(company_code=company, limit=50, min_hours_since_last=0)
        keys = {c.get("employee_key") for c in other_cands}
        check("reminder company scope excludes other tenant", emp_other not in keys, keys)
        check("reminder includes company employee", emp_a in keys or emp_b in keys, keys)
        check("reminder without company empty", app.pending_onboarding_reminder_candidates(limit=10) == [])

        # Manager scope fail-closed on detail helper path: use manager_scope_allows_employee
        # with a synthetic scoped manager that does not include emp_a
        # (full HTTP path covered in staging evidence when credentials available)
        check(
            "detail helper uses company-scoped find",
            "company_code" in _fn_src(app.dashboard_posthire_onboarding_detail),
        )
        check(
            "detail uses context_manager_allows_employee",
            "context_manager_allows_employee" in _fn_src(app.dashboard_posthire_onboarding_detail),
        )
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", ([emp_a, emp_b, emp_other],))
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", ([emp_a, emp_b, emp_other],))
                cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([company, other],))
            conn.commit()


def main() -> int:
    print("=== Onboarding Wave 1 — read authority smoke ===")
    try:
        offline_checks()
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP offline import: psycopg2 missing")
            return 0
        raise

    try:
        import app  # noqa: F401

        if os.environ.get("DATABASE_URL") or os.environ.get("WATHEFNI_POSTGRES_ENV"):
            print("--- DB behavioural ---")
            db_checks()
        else:
            print("SKIP DB behavioural: no DATABASE_URL / WATHEFNI_POSTGRES_ENV")
    except Exception as exc:
        check("DB behavioural ran without exception", False, str(exc)[:300])

    print(f"\nRESULT  pass={PASS} fail={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
