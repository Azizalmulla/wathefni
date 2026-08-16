#!/usr/bin/env python3
"""Employee Migration Foundation — manager resolution + P0–P2 regression smoke."""

from __future__ import annotations

import csv
import io
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")


def _fail(msg: str) -> None:
    print(f"FAIL employee migration foundation manager: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    preferred = [
        "name",
        "phone",
        "email",
        "department",
        "external_employee_id",
        "payroll_id",
        "source_system",
        "manager_phone",
    ]
    fields = sorted({k for r in rows for k in r.keys()})
    fieldnames = [f for f in preferred if f in fields] + [f for f in fields if f not in preferred]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    import employee_migration_foundation as emf
    import app as legacy

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    n = int(tag[:6], 16) % 1000000
    phone_mgr = f"96591{n:06d}"
    phone_a = f"96592{n:06d}"
    phone_b = f"96593{n:06d}"
    phone_c = f"96594{n:06d}"
    phone_d = f"96595{n:06d}"
    phone_unknown = f"96596{n:06d}"

    context = {
        "company_code": company,
        "user_id": "smoke-emf-mgr",
        "email": "smoke-emf-mgr@wathefni.ai",
        "permissions": ["employees.manage"],
        "modules": ["employees"],
    }
    original_require = legacy.require_employee_roster_admin
    original_modules = getattr(legacy, "company_has_module", None)

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]
    legacy.company_has_module = lambda *_a, **_k: False  # type: ignore[assignment]

    created_keys: list[str] = []
    batch_ids: list[str] = []
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur)
                conn.commit()

        # Seed tenant manager
        mgr = legacy.create_company_employee(
            company,
            name="Tenant Manager Seed",
            phone=phone_mgr,
            seed_compliance=False,
            start_onboarding=False,
        )
        if mgr.get("status") != "created":
            _fail(f"seed manager failed: {mgr}")
        created_keys.append(str(mgr["employee_key"]))

        rows = [
            # manager already in tenant
            {
                "name": "Reports To Tenant",
                "phone": phone_a,
                "manager_phone": phone_mgr,
                "source_system": "smoke_hris",
                "external_employee_id": f"EXT-{tag}-A",
                "payroll_id": f"PAY-{tag}-A",
            },
            # manager earlier in same file (phone_a)
            {
                "name": "Reports To Earlier",
                "phone": phone_b,
                "manager_phone": phone_a,
                "source_system": "smoke_hris",
                "external_employee_id": f"EXT-{tag}-B",
            },
            # manager later in same file (phone_d) → unresolved warning
            {
                "name": "Reports To Later",
                "phone": phone_c,
                "manager_phone": phone_d,
                "source_system": "smoke_hris",
                "external_employee_id": f"EXT-{tag}-C",
            },
            # later manager person
            {
                "name": "Later Manager Person",
                "phone": phone_d,
                "source_system": "smoke_hris",
                "external_employee_id": f"EXT-{tag}-D",
            },
            # unresolved manager
            {
                "name": "Unknown Manager Test",
                "phone": f"96597{n:06d}",
                "manager_phone": phone_unknown,
                "source_system": "smoke_hris",
                "external_employee_id": f"EXT-{tag}-U",
                "payroll_id": f"PAY-{tag}-U",
            },
            # duplicate phone conflict
            {
                "name": "Dup Phone",
                "phone": phone_a,
                "manager_phone": phone_mgr,
                "source_system": "smoke_hris",
                "external_employee_id": f"EXT-{tag}-DUP",
            },
            # invalid
            {"name": "Missing Phone", "phone": "", "source_system": "smoke_hris"},
        ]
        raw = _csv(rows)
        preview = emf.preview_or_replay_import(
            legacy, context, raw=raw, filename=f"mgr-smoke-{tag}.csv", source_system="smoke_hris"
        )
        batch_ids.append(preview["batch_id"])
        totals = preview["totals"]
        if totals.get("create") != 5:
            _fail(f"create totals {totals}")
        if totals.get("conflict") != 1:
            _fail(f"conflict totals {totals}")
        if totals.get("invalid") != 1:
            _fail(f"invalid totals {totals}")
        if int(totals.get("warnings") or 0) < 2:
            _fail(f"expected >=2 warnings (later+unknown), got {totals}")

        by_name = {r["name"]: r for bucket in preview["results"].values() for r in bucket}
        tenant_row = by_name["Reports To Tenant"]
        if not tenant_row.get("manager_resolved") or tenant_row.get("manager_source") != "tenant":
            _fail(f"tenant manager resolve: {tenant_row}")
        earlier_row = by_name["Reports To Earlier"]
        if not earlier_row.get("manager_resolved") or earlier_row.get("manager_source") != "batch_earlier":
            _fail(f"earlier manager resolve: {earlier_row}")
        later_row = by_name["Reports To Later"]
        if later_row.get("manager_resolved") is not False or not later_row.get("warnings"):
            _fail(f"later manager should warn: {later_row}")
        if later_row.get("status") not in {"will_create", None} and preview["results"]["created"]:
            # still in created bucket
            pass
        unknown_row = by_name["Unknown Manager Test"]
        if unknown_row.get("manager_resolved") is not False:
            _fail(f"unknown manager should be unresolved: {unknown_row}")
        if unknown_row.get("external_employee_id") != f"EXT-{tag}-U":
            _fail("external id not exposed in preview")
        if unknown_row.get("payroll_id") != f"PAY-{tag}-U":
            _fail("payroll id not exposed in preview")
        if unknown_row.get("source_system") != "smoke_hris":
            _fail("source_system not exposed in preview")
        _ok(f"preview manager cases totals={totals}")

        # Exception export includes unresolved manager warning rows
        _fn, body = emf.exception_csv(legacy, context, batch_id=preview["batch_id"])
        if "Unknown Manager Test" not in body or "manager_phone" not in body:
            _fail(f"exception csv missing unresolved manager: {body[:400]}")
        if "Reports To Later" not in body:
            _fail("exception csv missing later-manager warning row")
        _ok("exception export includes unresolved managers")

        # Replay preview refresh still same idempotency key (previewed refreshes)
        preview2 = emf.preview_or_replay_import(
            legacy, context, raw=raw, filename=f"mgr-smoke-{tag}.csv", source_system="smoke_hris"
        )
        if preview2["batch_id"] != preview["batch_id"]:
            _fail("idempotency key produced new batch on preview refresh")
        if int((preview2.get("totals") or {}).get("warnings") or 0) < 2:
            _fail("preview refresh lost warnings")
        _ok("preview refresh idempotency")

        committed = emf.commit_import_batch(legacy, context, batch_id=preview["batch_id"])
        if committed.get("dry_run"):
            _fail("commit dry_run")
        # Tenant manager applied on Reports To Tenant
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key, raw_json FROM employees
                    WHERE company_code=%s AND phone=%s
                    """,
                    (company, phone_a),
                )
                emp_a = dict(cur.fetchone())
                created_keys.append(str(emp_a["employee_key"]))
                raw_json = emp_a.get("raw_json") or {}
                if isinstance(raw_json, str):
                    import json as J

                    raw_json = J.loads(raw_json)
                if raw_json.get("manager_employee_key") != mgr["employee_key"]:
                    _fail(f"tenant manager not stamped on commit: {raw_json}")
                cur.execute(
                    """
                    SELECT employee_key, raw_json FROM employees
                    WHERE company_code=%s AND phone=%s
                    """,
                    (company, phone_b),
                )
                emp_b = dict(cur.fetchone())
                created_keys.append(str(emp_b["employee_key"]))
                raw_b = emp_b.get("raw_json") or {}
                if isinstance(raw_b, str):
                    import json as J

                    raw_b = J.loads(raw_b)
                if raw_b.get("manager_employee_key") != emp_a["employee_key"]:
                    _fail(f"earlier-batch manager not stamped: {raw_b}")
                cur.execute(
                    """
                    SELECT employee_key, raw_json FROM employees
                    WHERE company_code=%s AND phone=%s
                    """,
                    (company, phone_c),
                )
                emp_c = dict(cur.fetchone())
                created_keys.append(str(emp_c["employee_key"]))
                raw_c = emp_c.get("raw_json") or {}
                if isinstance(raw_c, str):
                    import json as J

                    raw_c = J.loads(raw_c)
                if raw_c.get("manager_employee_key"):
                    _fail(f"later-manager should remain unset: {raw_c}")
                if not raw_c.get("manager_unresolved"):
                    _fail(f"later-manager unresolved flag missing: {raw_c}")
                # Collect remaining created phones
                for ph in (phone_d, f"96597{n:06d}"):
                    cur.execute(
                        "SELECT employee_key FROM employees WHERE company_code=%s AND phone=%s",
                        (company, ph),
                    )
                    hit = cur.fetchone()
                    if hit:
                        created_keys.append(str(dict(hit)["employee_key"]))
                conn.commit()
        _ok("commit manager apply / unset")

        again = emf.commit_import_batch(legacy, context, batch_id=preview["batch_id"])
        if not again.get("replayed"):
            _fail("commit replay")
        _ok("commit idempotent replay")

        rolled = emf.rollback_import_batch(
            legacy, context, batch_id=preview["batch_id"], idempotency_key=f"rb-{tag}"
        )
        if rolled.get("status") != "rolled_back" or int(rolled.get("removed") or 0) < 1:
            _fail(f"rollback failed: {rolled}")
        _ok(f"rollback removed={rolled.get('removed')}")

        # Exact fixture file smoke (preview only — do not confirm user batch)
        fixture = Path(os.environ.get("EMF_FIXTURE_XLSX") or "/Users/azizalmulla/Downloads/wathefni_employee_import_full_test.xlsx")
        if fixture.exists():
            raw_x = fixture.read_bytes()
            fx = emf.preview_or_replay_import(
                legacy,
                context,
                raw=raw_x,
                filename=fixture.name,
                source_system=None,
                idempotency_key=f"fixture-mgr-fix-{tag}",
            )
            batch_ids.append(fx["batch_id"])
            fx_totals = fx["totals"]
            # 7 creates, 2 conflict, 1 invalid, >=1 warning (Unknown Manager)
            if fx_totals.get("create") != 7 or fx_totals.get("conflict") != 2 or fx_totals.get("invalid") != 1:
                _fail(f"fixture totals unexpected: {fx_totals}")
            if int(fx_totals.get("warnings") or 0) < 1:
                _fail(f"fixture missing unresolved manager warning: {fx_totals}")
            unknown = next(
                (r for r in fx["results"]["created"] if r["name"] == "Unknown Manager Test"),
                None,
            )
            if not unknown or unknown.get("manager_resolved") is not False:
                _fail(f"fixture Unknown Manager Test not warned: {unknown}")
            if unknown.get("manager_phone") != "96559999999":
                _fail(f"fixture manager_phone not stored: {unknown}")
            if unknown.get("external_employee_id") != "ERP-EMP-1009":
                _fail("fixture ext id missing in preview detail")
            # Fahad reports to Noura earlier in file
            fahad = next((r for r in fx["results"]["created"] if r["name"] == "Fahad Alenezi"), None)
            if not fahad or not fahad.get("manager_resolved") or fahad.get("manager_source") != "batch_earlier":
                _fail(f"fixture Fahad earlier-manager: {fahad}")
            _fn, fx_csv = emf.exception_csv(legacy, context, batch_id=fx["batch_id"])
            if "Unknown Manager Test" not in fx_csv or "96559999999" not in fx_csv:
                _fail("fixture exception csv missing unknown manager")
            # Do not commit fixture — leave preview-only synthetic batch for cleanup
            _ok(f"exact fixture preview OK batch={fx['batch_id']} totals={fx_totals}")
        else:
            _ok("fixture xlsx not present — skipped exact-file lane")

        print("OK employee migration foundation manager smoke")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        if original_modules is not None:
            legacy.company_has_module = original_modules  # type: ignore[assignment]
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                for bid in batch_ids:
                    cur.execute("DELETE FROM employee_source_mappings WHERE batch_id=%s", (bid,))
                    cur.execute("DELETE FROM employee_import_rows WHERE batch_id=%s", (bid,))
                    cur.execute("DELETE FROM employee_import_batches WHERE batch_id=%s", (bid,))
                for key in set(created_keys):
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, key),
                    )
                # Also delete any leftover phones from smoke create that weren't rolled back
                for ph in (
                    phone_mgr,
                    phone_a,
                    phone_b,
                    phone_c,
                    phone_d,
                    f"96597{n:06d}",
                ):
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND phone=%s",
                        (company, ph),
                    )
                conn.commit()


if __name__ == "__main__":
    main()
