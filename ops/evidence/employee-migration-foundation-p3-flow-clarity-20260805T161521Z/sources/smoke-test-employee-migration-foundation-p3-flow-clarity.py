#!/usr/bin/env python3
"""Smoke: Migration & Sync flow clarity — route order + approve messaging.

Does not depend on prior fixture apply state. Builds a one-off material-name
review row, approves it, and asserts confirm-still-required messaging.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import uuid
from typing import Any

ORCH = os.environ.get("ORCH_ROOT") or os.path.dirname(os.path.abspath(__file__))
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")


def _fail(msg: str) -> None:
    print(f"FAIL emf-flow-clarity: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    fields = sorted({k for r in rows for k in r})
    preferred = ["name", "phone", "email", "external_employee_id", "source_system"]
    fieldnames = [f for f in preferred if f in fields] + [f for f in fields if f not in preferred]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    import employee_migration_foundation as emf
    import app as legacy

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    n = int(tag[:6], 16) % 1000000
    phone = f"96588{n:06d}"
    ext = f"FLOW-{tag}"

    paths = [getattr(r, "path", "") for r in legacy.app.routes]
    ib_idx = next((i for i, p in enumerate(paths) if p == "/dashboard/posthire/employees/import-batches"), -1)
    detail_idx = next(
        (i for i, p in enumerate(paths) if p == "/dashboard/posthire/employees/{employee_key}"),
        -1,
    )
    if ib_idx < 0 or detail_idx < 0 or ib_idx > detail_idx:
        _fail(f"import-batches route must precede employee_key (ib={ib_idx} detail={detail_idx})")
    _ok("route order import-batches before {employee_key}")

    context = {
        "company_code": company,
        "user_id": "smoke-emf-flow",
        "email": "smoke-emf-flow@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin
    legacy.require_employee_roster_admin = lambda ctx, permission="employees.manage": company  # type: ignore[assignment]
    legacy.company_has_module = lambda code, module: False  # type: ignore[assignment]

    created_keys: list[str] = []
    try:
        seed = legacy.create_company_employee(
            company,
            name="Flow Clarity Person",
            phone=phone,
            email="flow.old@example.com",
            seed_compliance=False,
            start_onboarding=False,
        )
        if seed.get("status") != "created":
            _fail(f"seed failed: {seed}")
        ek = str(seed["employee_key"])
        created_keys.append(ek)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur)
                emf._upsert_source_mapping(
                    cur,
                    company=company,
                    employee_key=ek,
                    source_system="flow_erp",
                    external_employee_id=ext,
                    payroll_id=None,
                    batch_id=str(uuid.uuid4()),
                    row_id=str(uuid.uuid4()),
                )
                conn.commit()

        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=_csv(
                [
                    {
                        "name": "Completely Different Name",
                        "phone": phone,
                        "email": "flow.new@example.com",
                        "source_system": "flow_erp",
                        "external_employee_id": ext,
                    }
                ]
            ),
            filename=f"flow-clarity-{tag}.csv",
            idempotency_key=f"flow-clarity-{tag}",
        )
        totals = preview.get("totals") or {}
        if int(totals.get("review") if totals.get("review") is not None else totals.get("conflict") or 0) != 1:
            _fail(f"expected review=1 got {totals}")
        if int(totals.get("update") or 0) != 0:
            _fail(f"material name must not auto-update: {totals}")
        review = preview["results"]["needs_review"]
        if not review or not review[0].get("name_identity_review"):
            _fail(f"missing name identity review: {review}")
        row_id = review[0].get("row_id")
        approved = emf.approve_identity_name_change(
            legacy,
            context,
            batch_id=preview["batch_id"],
            row_id=str(row_id),
        )
        if approved.get("batch_id") != preview["batch_id"]:
            _fail("batch context lost after approve")
        if not approved.get("confirm_still_required"):
            _fail("confirm_still_required missing")
        msg = str(approved.get("message") or "")
        if "Confirm import is still required" not in msg:
            _fail(f"unclear approve message: {msg}")
        at = approved.get("totals") or {}
        if int(at.get("review") or 0) != 0 or int(at.get("update") or 0) != 1:
            _fail(f"after approve expected update=1 review=0 got {at}")
        updated = approved["results"].get("updated") or []
        if not any(r.get("name_change_approved") for r in updated):
            _fail("approved flag missing on updated row")
        _ok("approve keeps batch, moves out of review, confirm still required")

        # Helpers that previously 404'd as employee_key=import-*
        review_list = emf.list_review_items(legacy, context, limit=20)
        batches = emf.list_import_batches(legacy, context, limit=5)
        if not isinstance(review_list.get("items"), list):
            _fail("review list broken")
        if not batches.get("ok"):
            _fail("batches list broken")
        _ok("review/history helpers")

        print("OK employee migration foundation P3 flow clarity smoke")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                for ek in set(created_keys):
                    cur.execute(
                        "DELETE FROM employee_source_mappings WHERE company_code=%s AND employee_key=%s",
                        (company, ek),
                    )
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, ek),
                    )
                # Clean synthetic preview batches for this smoke tag only.
                cur.execute(
                    """
                    DELETE FROM employee_import_rows
                    WHERE company_code=%s
                      AND batch_id IN (
                        SELECT batch_id FROM employee_import_batches
                        WHERE company_code=%s AND idempotency_key LIKE %s
                      )
                    """,
                    (company, company, "flow-clarity-%"),
                )
                cur.execute(
                    """
                    DELETE FROM employee_import_batches
                    WHERE company_code=%s AND idempotency_key LIKE %s
                    """,
                    (company, "flow-clarity-%"),
                )
                conn.commit()


if __name__ == "__main__":
    main()
