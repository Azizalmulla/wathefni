#!/usr/bin/env python3
"""Smoke: P3 review-application flow.

preview → confirm safe rows → approve unresolved name change → apply approved
change → employee updated once → queue cleared → audit/history preserved.
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
    print(f"FAIL emf-apply-flow: {msg}")
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
    phone_safe = f"96571{n:06d}"
    phone_conflict = f"96572{n:06d}"
    ext_safe = f"AF-SAFE-{tag}"
    ext_conflict = f"AF-CONF-{tag}"

    h = emf.honesty_payload()
    if not h.get("approved_name_change_apply_once"):
        _fail("honesty flag approved_name_change_apply_once missing")
    if str(h.get("version")) != "1.1.4":
        _fail(f"expected contract 1.1.4 got {h.get('version')}")
    _ok("contract 1.1.4 apply-once honesty")

    context = {
        "company_code": company,
        "user_id": "smoke-emf-apply",
        "email": "smoke-emf-apply@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin
    legacy.require_employee_roster_admin = lambda ctx, permission="employees.manage": company  # type: ignore[assignment]
    legacy.company_has_module = lambda code, module: False  # type: ignore[assignment]

    created_keys: list[str] = []
    batch_id: str | None = None
    try:
        # Seed safe-update person + name-conflict person
        for name, phone, email, ext in [
            ("Apply Safe Person", phone_safe, "apply.safe@example.com", ext_safe),
            ("Apply Conflict Person", phone_conflict, "apply.old@example.com", ext_conflict),
        ]:
            seed = legacy.create_company_employee(
                company,
                name=name,
                phone=phone,
                email=email,
                seed_compliance=False,
                start_onboarding=False,
            )
            if seed.get("status") != "created":
                _fail(f"seed failed for {name}: {seed}")
            ek = str(seed["employee_key"])
            created_keys.append(ek)
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    emf.ensure_schema(cur)
                    emf._upsert_source_mapping(
                        cur,
                        company=company,
                        employee_key=ek,
                        source_system="apply_erp",
                        external_employee_id=ext,
                        payroll_id=None,
                        batch_id=str(uuid.uuid4()),
                        row_id=str(uuid.uuid4()),
                    )
                    conn.commit()

        ek_safe, ek_conflict = created_keys[0], created_keys[1]

        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=_csv(
                [
                    {
                        "name": "Apply Safe Person",
                        "phone": phone_safe,
                        "email": "apply.safe.updated@example.com",
                        "source_system": "apply_erp",
                        "external_employee_id": ext_safe,
                    },
                    {
                        "name": "Totally Different Apply Name",
                        "phone": phone_conflict,
                        "email": "apply.new@example.com",
                        "source_system": "apply_erp",
                        "external_employee_id": ext_conflict,
                    },
                ]
            ),
            filename=f"apply-flow-{tag}.csv",
            idempotency_key=f"apply-flow-{tag}",
        )
        batch_id = str(preview["batch_id"])
        totals = preview.get("totals") or {}
        if int(totals.get("update") or 0) != 1:
            _fail(f"expected safe update=1 got {totals}")
        if int(totals.get("review") if totals.get("review") is not None else totals.get("conflict") or 0) != 1:
            _fail(f"expected review=1 got {totals}")
        _ok("preview: 1 safe update + 1 name conflict")

        # Confirm safe rows only — conflict remains; batch stays actionable (partial)
        committed = emf.commit_import_batch(legacy, context, batch_id=batch_id)
        if committed.get("replayed"):
            _fail("first confirm must not replay")
        if str(committed.get("status")) != "partial":
            _fail(f"expected partial after safe confirm with remaining conflict, got {committed.get('status')}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, email FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, ek_safe),
                )
                safe_row = dict(cur.fetchone())
                cur.execute(
                    "SELECT name, email FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, ek_conflict),
                )
                conflict_row = dict(cur.fetchone())
                conn.commit()
        if str(safe_row.get("email")) != "apply.safe.updated@example.com":
            _fail(f"safe row not updated: {safe_row}")
        if str(conflict_row.get("name")) != "Apply Conflict Person":
            _fail(f"conflict person must not update on first confirm: {conflict_row}")
        _ok("confirm safe rows; conflict person unchanged; batch partial")

        review = emf.list_review_items(legacy, context, limit=100)
        pending = [it for it in review["items"] if it.get("employee_key") == ek_conflict]
        if len(pending) != 1 or not pending[0].get("approvable"):
            _fail(f"expected one approvable conflict card: {pending}")
        if str(pending[0].get("batch_id")) != batch_id:
            _fail("review card left original batch")
        row_id = str(pending[0]["row_id"])

        approved = emf.approve_identity_name_change(
            legacy,
            context,
            batch_id=batch_id,
            row_id=row_id,
        )
        if str(approved.get("batch_id")) != batch_id:
            _fail("approve must keep original batch")
        if not approved.get("apply_still_required"):
            _fail("apply_still_required missing after approve")
        review2 = emf.list_review_items(legacy, context, limit=100)
        approved_cards = [it for it in review2["items"] if it.get("employee_key") == ek_conflict]
        if len(approved_cards) != 1 or not approved_cards[0].get("applyable"):
            _fail(f"approved card must stay visible and applyable: {approved_cards}")
        if approved_cards[0].get("outcome") != "Approved":
            _fail(f"expected outcome Approved got {approved_cards[0].get('outcome')}")
        _ok("approve keeps original batch; Approved card ready to apply")

        # Re-upload must NOT silently inherit approval onto a new batch
        other = emf.preview_or_replay_import(
            legacy,
            context,
            raw=_csv(
                [
                    {
                        "name": "Totally Different Apply Name",
                        "phone": phone_conflict,
                        "email": "apply.new@example.com",
                        "source_system": "apply_erp",
                        "external_employee_id": ext_conflict,
                    }
                ]
            ),
            filename=f"apply-flow-reup-{tag}.csv",
            idempotency_key=f"apply-flow-reup-{tag}",
        )
        other_id = str(other["batch_id"])
        if other_id == batch_id:
            _fail("re-upload should create a distinct batch for different content key")
        other_review = (other.get("results") or {}).get("needs_review") or []
        if not other_review or other_review[0].get("name_change_approved"):
            _fail("approval must not transfer to unrelated future batch")
        # Active queue should still prefer the original approved-pending (newer conflict supersedes —
        # re-upload creates newer conflict). For this smoke we apply the ORIGINAL batch, not the re-up.
        # Clean the re-upload conflict from competing by not applying it; apply original explicitly.
        _ok("re-upload does not inherit approval onto new batch")

        applied = emf.apply_approved_name_change(
            legacy,
            context,
            batch_id=batch_id,
            row_id=row_id,
        )
        if applied.get("dry_run"):
            _fail("apply must not be dry_run")
        if str(applied.get("applied_employee_key")) != ek_conflict:
            _fail(f"applied wrong employee: {applied}")

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, email FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, ek_conflict),
                )
                after = dict(cur.fetchone())
                # Employee updated once (name + email from approved changes)
                if str(after.get("name")) != "Totally Different Apply Name":
                    _fail(f"name not applied: {after}")
                if str(after.get("email")) != "apply.new@example.com":
                    _fail(f"email not applied: {after}")
                # Ledger row shows applied audit fields
                cur.execute(
                    """
                    SELECT status, detail FROM employee_import_rows
                    WHERE company_code=%s AND batch_id=%s AND row_id=%s
                    """,
                    (company, batch_id, row_id),
                )
                ledger = dict(cur.fetchone())
                detail = ledger.get("detail") or {}
                if isinstance(detail, str):
                    import json

                    detail = json.loads(detail)
                if str(ledger.get("status")) != "updated":
                    _fail(f"ledger status not updated: {ledger}")
                if not detail.get("name_change_approved") or not detail.get("name_change_applied"):
                    _fail(f"missing approval/application stamps: {detail}")
                if not detail.get("name_change_approved_by") or not detail.get("name_change_approved_at"):
                    _fail(f"missing approval actor/time: {detail}")
                if not detail.get("name_change_applied_by") or not detail.get("name_change_applied_at"):
                    _fail(f"missing apply actor/time: {detail}")
                if not detail.get("applied_changes") and not detail.get("changes"):
                    _fail(f"missing before/after: {detail}")
                # Apply again → idempotent, no double update
                again = emf.apply_approved_name_change(
                    legacy,
                    context,
                    batch_id=batch_id,
                    row_id=row_id,
                )
                if not again.get("replayed"):
                    _fail("second apply must be idempotent replay")
                conn.commit()

        review3 = emf.list_review_items(legacy, context, limit=100)
        # Original identity should be cleared; re-upload conflict may still show for same ek
        # (newer unresolved conflict supersedes applied). That is correct — approval didn't transfer.
        # Assert original approved row is gone as applyable.
        still_applyable = [
            it
            for it in review3["items"]
            if it.get("employee_key") == ek_conflict and it.get("batch_id") == batch_id and it.get("applyable")
        ]
        if still_applyable:
            _fail(f"original batch applyable card must clear: {still_applyable}")
        _ok("apply updates once; audit stamps; queue clears for original batch")

        detail_batch = emf.get_import_batch(legacy, context, batch_id=batch_id)
        updated_rows = (detail_batch.get("results") or {}).get("updated") or []
        applied_hist = [
            r
            for r in updated_rows
            if r.get("row_id") == row_id or r.get("employee_key") == ek_conflict
        ]
        if not applied_hist:
            _fail("history/batch detail missing applied row")
        hist = applied_hist[0]
        if not hist.get("name_change_approved") or not hist.get("name_change_applied"):
            _fail(f"history missing approval/application flags: {hist}")
        if not (hist.get("changes") or hist.get("detail", {}).get("applied_changes")):
            _fail(f"history missing before/after: {hist}")
        _ok("history retains approval, application, actor/time, before/after")

        print("OK employee migration foundation P3 apply-flow smoke")
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
                cur.execute(
                    """
                    DELETE FROM employee_import_rows
                    WHERE company_code=%s
                      AND batch_id IN (
                        SELECT batch_id FROM employee_import_batches
                        WHERE company_code=%s AND idempotency_key LIKE %s
                      )
                    """,
                    (company, company, f"apply-flow-%{tag}%"),
                )
                # Also clean exact prefixes used
                cur.execute(
                    """
                    DELETE FROM employee_import_rows
                    WHERE company_code=%s
                      AND batch_id IN (
                        SELECT batch_id FROM employee_import_batches
                        WHERE company_code=%s AND (
                          idempotency_key = %s OR idempotency_key = %s
                        )
                      )
                    """,
                    (company, company, f"apply-flow-{tag}", f"apply-flow-reup-{tag}"),
                )
                cur.execute(
                    """
                    DELETE FROM employee_import_batches
                    WHERE company_code=%s AND (
                      idempotency_key = %s OR idempotency_key = %s
                    )
                    """,
                    (company, f"apply-flow-{tag}", f"apply-flow-reup-{tag}"),
                )
                conn.commit()


if __name__ == "__main__":
    main()
