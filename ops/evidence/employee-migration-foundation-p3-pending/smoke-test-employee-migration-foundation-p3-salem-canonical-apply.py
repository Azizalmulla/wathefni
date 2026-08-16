#!/usr/bin/env python3
"""Smoke: existing Salem P3 name-change — approve → apply on canonical row.

Uses live employee_key WATHEFNI-96550010006 (ERP-EMP-1006). Resets hub name,
creates an actionable preview conflict, approves, applies, asserts same key,
queue cleared, history preserved. Never deletes historical ledger rows outside
this smoke's own batches.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import uuid

ORCH = os.environ.get("ORCH_ROOT") or os.path.dirname(os.path.abspath(__file__))
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")

EK = "WATHEFNI-96550010006"
EXT = "ERP-EMP-1006"
PHONE = "96550010006"
SOURCE = "test_erp"


def _fail(msg: str) -> None:
    print(f"FAIL emf-salem-apply: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    fields = sorted({k for r in rows for k in r})
    preferred = [
        "name",
        "phone",
        "email",
        "external_employee_id",
        "source_system",
        "payroll_id",
        "department",
        "position_title",
        "start_date",
        "manager_phone",
    ]
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
    h = emf.honesty_payload()
    if not h.get("canonical_review_apply"):
        _fail("canonical_review_apply honesty flag missing")
    if str(h.get("version")) != "1.1.4":
        _fail(f"expected contract 1.1.4 got {h.get('version')}")
    _ok("contract 1.1.4 canonical apply")

    context = {
        "company_code": company,
        "user_id": "smoke-emf-salem",
        "email": "smoke-emf-salem@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin
    legacy.require_employee_roster_admin = lambda ctx, permission="employees.manage": company  # type: ignore[assignment]
    legacy.company_has_module = lambda code, module: False  # type: ignore[assignment]

    batch_id: str | None = None
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur)
                cur.execute(
                    "SELECT employee_key, name, email, phone FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, EK),
                )
                emp = cur.fetchone()
                if not emp:
                    _fail(f"Salem employee {EK} missing on canary")
                emp = dict(emp)
                # Reset hub to pre-conflict name so material name review is real again.
                cur.execute(
                    """
                    UPDATE employees
                    SET name=%s, email=%s, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    ("Salem Aldosari", "salem.aldosari@example.com", company, EK),
                )
                # Ensure mapping exists
                cur.execute(
                    """
                    SELECT 1 FROM employee_source_mappings
                    WHERE company_code=%s AND employee_key=%s AND source_system=%s
                      AND external_employee_id=%s AND active=true
                    LIMIT 1
                    """,
                    (company, EK, SOURCE, EXT),
                )
                if not cur.fetchone():
                    emf._upsert_source_mapping(
                        cur,
                        company=company,
                        employee_key=EK,
                        source_system=SOURCE,
                        external_employee_id=EXT,
                        payroll_id="PAY-1006",
                        batch_id=str(uuid.uuid4()),
                        row_id=str(uuid.uuid4()),
                    )
                conn.commit()
        _ok("reset Salem hub name + mapping")

        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=_csv(
                [
                    {
                        "name": "Different Salem Name",
                        "phone": PHONE,
                        "email": "salem.alenezi.conflict@example.com",
                        "external_employee_id": EXT,
                        "source_system": SOURCE,
                        "payroll_id": "PAY-1006",
                        "department": "Information Technology",
                        "position_title": "IT Support Specialist",
                        "start_date": "2024-11-20",
                        "manager_phone": "96550010004",
                    }
                ]
            ),
            filename=f"salem-canonical-{tag}.csv",
            idempotency_key=f"salem-canonical-{tag}",
        )
        batch_id = str(preview["batch_id"])
        review_rows = (preview.get("results") or {}).get("needs_review") or []
        if not review_rows or not review_rows[0].get("name_identity_review"):
            _fail(f"expected name identity review: {review_rows}")
        conflict_row_id = str(review_rows[0]["row_id"])
        if str(review_rows[0].get("employee_key")) != EK:
            _fail(f"employee_key drifted: {review_rows[0].get('employee_key')}")
        _ok("preview: Salem name conflict on actionable batch")

        q1 = emf.list_review_items(legacy, context, limit=50)
        card = next((it for it in q1["items"] if it.get("employee_key") == EK), None)
        if not card or not card.get("approvable"):
            _fail(f"queue missing approvable Salem card: {card}")
        if str(card.get("canonical_row_id") or card.get("row_id")) != conflict_row_id:
            _fail(
                f"queue/card row mismatch preview={conflict_row_id} queue={card.get('canonical_row_id') or card.get('row_id')}"
            )
        if str(card.get("canonical_batch_id") or card.get("batch_id")) != batch_id:
            _fail("queue batch_id mismatch vs preview")
        _ok("queue canonical ids match preview conflict row")

        approved = emf.approve_identity_name_change(
            legacy,
            context,
            batch_id=str(card.get("canonical_batch_id") or card["batch_id"]),
            row_id=str(card.get("canonical_row_id") or card["row_id"]),
        )
        if str(approved.get("approved_row_id")) != conflict_row_id:
            _fail("approve did not keep the same row_id")
        if str(approved.get("batch_id")) != batch_id:
            _fail("approve left original batch")

        q2 = emf.list_review_items(legacy, context, limit=50)
        approved_card = next((it for it in q2["items"] if it.get("employee_key") == EK), None)
        if not approved_card or not approved_card.get("applyable"):
            _fail(f"Approved card missing/not applyable: {approved_card}")
        if str(approved_card.get("canonical_row_id")) != conflict_row_id:
            _fail(
                f"after approve, UI would point at {approved_card.get('canonical_row_id')} but approval is on {conflict_row_id}"
            )
        if str(approved_card.get("status")) != "will_update":
            _fail(f"approved card status expected will_update got {approved_card.get('status')}")
        _ok("approve stores Approved on the exact canonical row Apply will use")

        # Deliberately call Apply with a stale conflict id from another Salem ledger row —
        # server must resolve to the canonical approved-pending row.
        stale_batch = None
        stale_row = None
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.batch_id::text, r.row_id::text
                    FROM employee_import_rows r
                    JOIN employee_import_batches b ON b.batch_id=r.batch_id AND b.company_code=r.company_code
                    WHERE r.company_code=%s AND r.employee_key=%s AND r.status='conflict'
                      AND r.row_id::text <> %s
                    ORDER BY b.created_at DESC
                    LIMIT 1
                    """,
                    (company, EK, conflict_row_id),
                )
                stale = cur.fetchone()
                if stale:
                    stale = dict(stale)
                    stale_batch, stale_row = stale["batch_id"], stale["row_id"]
                conn.commit()

        apply_batch = stale_batch or batch_id
        apply_row = stale_row or conflict_row_id
        applied = emf.apply_approved_name_change(
            legacy,
            context,
            batch_id=str(apply_batch),
            row_id=str(apply_row),
        )
        if applied.get("dry_run"):
            _fail("apply must not be dry_run")
        if str(applied.get("applied_employee_key")) != EK:
            _fail(f"employee_key not retained: {applied.get('applied_employee_key')}")
        # Canonical row should be the one that was applied
        if str(applied.get("applied_row_id")) != conflict_row_id and not applied.get("replayed"):
            # When resolving from stale ids, applied_row_id should be the canonical approved row
            if str(applied.get("applied_row_id")) != conflict_row_id:
                _fail(
                    f"apply must land on approved canonical row {conflict_row_id}, got {applied.get('applied_row_id')}"
                )
        _ok("apply resolves to canonical approved row (stale ids safe)")

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key, name, email FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, EK),
                )
                after = dict(cur.fetchone())
                if after["employee_key"] != EK:
                    _fail("employee_key changed")
                if str(after.get("name")) != "Different Salem Name":
                    _fail(f"name not applied: {after}")
                cur.execute(
                    """
                    SELECT status, detail FROM employee_import_rows
                    WHERE company_code=%s AND batch_id=%s AND row_id=%s
                    """,
                    (company, batch_id, conflict_row_id),
                )
                ledger = dict(cur.fetchone())
                detail = ledger.get("detail") or {}
                if isinstance(detail, str):
                    detail = json.loads(detail)
                if str(ledger.get("status")) != "updated":
                    _fail(f"canonical row not updated: {ledger}")
                if not detail.get("name_change_approved") or not detail.get("name_change_applied"):
                    _fail(f"missing approval/apply stamps: {detail}")
                if not detail.get("changes") and not detail.get("applied_changes"):
                    _fail("missing before/after in history detail")
                conn.commit()
        _ok("employee updated once; same key; history stamps present")

        # Idempotent second apply
        again = emf.apply_approved_name_change(
            legacy,
            context,
            batch_id=batch_id,
            row_id=conflict_row_id,
        )
        if not again.get("replayed"):
            _fail("second apply must be idempotent")
        _ok("apply idempotent")

        q3 = emf.list_review_items(legacy, context, limit=50)
        still = [it for it in q3["items"] if it.get("employee_key") == EK]
        if still:
            _fail(f"Salem must leave Needs review after apply: {still}")
        _ok("queue cleared for Salem")

        hist = emf.get_import_batch(legacy, context, batch_id=batch_id)
        updated = (hist.get("results") or {}).get("updated") or []
        hit = [r for r in updated if str(r.get("row_id")) == conflict_row_id]
        if not hit:
            _fail("batch history missing applied Salem row")
        if not hit[0].get("name_change_approved") or not hit[0].get("name_change_applied"):
            _fail(f"history missing approval/apply flags: {hit[0]}")
        _ok("history preserves approval + apply + before/after")

        print("OK employee migration foundation P3 Salem canonical apply smoke")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        if batch_id:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    # Remove only this smoke's batch rows (preserve older audit ledger).
                    cur.execute(
                        """
                        DELETE FROM employee_import_rows
                        WHERE company_code=%s AND batch_id IN (
                          SELECT batch_id FROM employee_import_batches
                          WHERE company_code=%s AND idempotency_key=%s
                        )
                        """,
                        (company, company, f"salem-canonical-{tag}"),
                    )
                    cur.execute(
                        """
                        DELETE FROM employee_import_batches
                        WHERE company_code=%s AND idempotency_key=%s
                        """,
                        (company, f"salem-canonical-{tag}"),
                    )
                    conn.commit()


if __name__ == "__main__":
    main()
