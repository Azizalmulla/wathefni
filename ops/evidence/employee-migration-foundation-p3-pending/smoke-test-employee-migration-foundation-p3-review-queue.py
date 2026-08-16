#!/usr/bin/env python3
"""Smoke: Needs review queue semantics — dedupe, supersede, approve clear, history kept."""

from __future__ import annotations

import csv
import io
import os
import sys
import uuid

ORCH = os.environ.get("ORCH_ROOT") or os.path.dirname(os.path.abspath(__file__))
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")


def _fail(msg: str) -> None:
    print(f"FAIL emf-review-queue: {msg}")
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

    if emf.CONTRACT_VERSION < "1.1.2":
        _fail(f"expected contract >= 1.1.2 got {emf.CONTRACT_VERSION}")

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    n = int(tag[:6], 16) % 1000000
    phone = f"96577{n:06d}"
    phone_dup = f"96576{n:06d}"
    ext = f"Q-{tag}"

    context = {
        "company_code": company,
        "user_id": "smoke-emf-queue",
        "email": "smoke-emf-queue@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin
    legacy.require_employee_roster_admin = lambda ctx, permission="employees.manage": company  # type: ignore[assignment]
    legacy.company_has_module = lambda code, module: False  # type: ignore[assignment]

    created_keys: list[str] = []
    batch_ids: list[str] = []
    try:
        # Clean leftover synthetic people from prior interrupted smokes.
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key FROM employees
                    WHERE company_code=%s AND (
                      name IN ('Queue Salem', 'Different Queue Name')
                      OR phone LIKE '96577%%' OR phone LIKE '96576%%'
                    )
                    """,
                    (company,),
                )
                stale = [str(dict(r)["employee_key"]) for r in (cur.fetchall() or [])]
                for ek_stale in stale:
                    cur.execute(
                        "DELETE FROM employee_source_mappings WHERE company_code=%s AND employee_key=%s",
                        (company, ek_stale),
                    )
                    cur.execute(
                        "DELETE FROM employee_import_rows WHERE company_code=%s AND employee_key=%s",
                        (company, ek_stale),
                    )
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, ek_stale),
                    )
                cur.execute(
                    """
                    DELETE FROM employee_import_batches
                    WHERE company_code=%s AND idempotency_key LIKE 'queue-retry-%%'
                    """,
                    (company,),
                )
                conn.commit()

        seed = legacy.create_company_employee(
            company,
            name="Queue Salem",
            phone=phone,
            email="queue.salem@example.com",
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
                    source_system="queue_erp",
                    external_employee_id=ext,
                    payroll_id=None,
                    batch_id=str(uuid.uuid4()),
                    row_id=str(uuid.uuid4()),
                )
                conn.commit()

        conflict_rows = [
            {
                "name": "Different Queue Name",
                "phone": phone,
                "email": "queue.conflict@example.com",
                "source_system": "queue_erp",
                "external_employee_id": ext,
            },
            # Intra-file duplicate — must NOT appear in active queue
            {
                "name": "Dup In File",
                "phone": phone_dup,
                "email": "dup1@example.com",
            },
            {
                "name": "Dup In File Two",
                "phone": phone_dup,
                "email": "dup2@example.com",
            },
            # Invalid — must NOT appear in active queue
            {
                "name": "Missing Phone Queue",
                "email": "missing@example.com",
            },
        ]

        # Three preview retries → still one active review card for this identity
        for i in range(3):
            preview = emf.preview_or_replay_import(
                legacy,
                context,
                raw=_csv(conflict_rows),
                filename=f"queue-retry-{tag}-{i}.csv",
                idempotency_key=f"queue-retry-{tag}-{i}",
            )
            batch_ids.append(str(preview["batch_id"]))
            review = emf.list_review_items(legacy, context, limit=100)
            salem_items = [it for it in review["items"] if it.get("employee_key") == ek]
            if len(salem_items) != 1:
                _fail(
                    f"retry {i}: expected 1 active card for {ek}, got {len(salem_items)} "
                    f"keys={[it.get('employee_key') for it in salem_items]}"
                )
            # No invalid / intra-file duplicate in queue
            for it in review["items"]:
                reason = str(it.get("reason") or "").lower()
                if "duplicate phone in this file" in reason:
                    _fail("intra-file duplicate leaked into active queue")
                if "missing or invalid phone" in reason:
                    _fail("invalid row leaked into active queue")
            _ok(f"preview retry {i + 1}: one active identity card")

        # Leave unresolved: still one card (newest supersedes)
        review = emf.list_review_items(legacy, context, limit=100)
        before_approve = [it for it in review["items"] if it.get("employee_key") == ek]
        if len(before_approve) != 1:
            _fail("unresolved leave should still show one card")
        active_row_id = before_approve[0].get("row_id")
        active_batch = before_approve[0].get("batch_id")

        # Ledger retains all conflict copies across retries
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM employee_import_rows
                    WHERE company_code=%s AND employee_key=%s AND status='conflict'
                      AND batch_id = ANY(%s::uuid[])
                    """,
                    (company, ek, batch_ids),
                )
                conflict_copies = int(dict(cur.fetchone())["c"])
                conn.commit()
        if conflict_copies < 3:
            _fail(f"expected >=3 ledger conflict copies, got {conflict_copies}")
        _ok("history/ledger retains repeated conflict rows")

        # Approve → moves to Approved (still visible, applyable); does not clear until apply
        approved = emf.approve_identity_name_change(
            legacy,
            context,
            batch_id=str(active_batch),
            row_id=str(active_row_id),
        )
        del approved
        review_after = emf.list_review_items(legacy, context, limit=100)
        salem_after = [it for it in review_after["items"] if it.get("employee_key") == ek]
        if len(salem_after) != 1 or not salem_after[0].get("applyable"):
            _fail(f"approved identity must stay as applyable Approved card: {salem_after}")
        _ok("approve moves to Approved (still in queue until apply)")

        # Older conflict ledger rows still exist (not deleted)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM employee_import_rows
                    WHERE company_code=%s AND employee_key=%s AND status='conflict'
                      AND batch_id = ANY(%s::uuid[])
                    """,
                    (company, ek, batch_ids),
                )
                still = int(dict(cur.fetchone())["c"])
                conn.commit()
        if still < 2:
            _fail("older conflict ledger rows must remain after approve")
        _ok("approve preserves older ledger conflict rows")

        # Apply once → clears queue for that identity
        applied = emf.apply_approved_name_change(
            legacy,
            context,
            batch_id=str(active_batch),
            row_id=str(active_row_id),
        )
        del applied
        review_applied = emf.list_review_items(legacy, context, limit=100)
        salem_gone = [it for it in review_applied["items"] if it.get("employee_key") == ek]
        if salem_gone:
            _fail(f"after apply, identity must leave Needs review: {salem_gone}")
        _ok("apply clears active queue for that identity")

        # Batch detail still exposes conflicts for history
        detail = emf.get_import_batch(legacy, context, batch_id=batch_ids[0])
        if not (detail.get("results") or {}).get("needs_review"):
            _fail("batch detail should still show historical needs_review rows")
        _ok("history/batch detail retains review rows")

        print("OK employee migration foundation P3 review queue smoke")
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
                if batch_ids:
                    cur.execute(
                        "DELETE FROM employee_import_rows WHERE company_code=%s AND batch_id = ANY(%s::uuid[])",
                        (company, batch_ids),
                    )
                    cur.execute(
                        "DELETE FROM employee_import_batches WHERE company_code=%s AND batch_id = ANY(%s::uuid[])",
                        (company, batch_ids),
                    )
                conn.commit()


if __name__ == "__main__":
    main()
