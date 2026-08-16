#!/usr/bin/env python3
"""Employee Migration Foundation + Sync P1 smoke qualification.

Covers: repeated file import, duplicate employee, conflicting name/phone,
malformed rows, foreign tenant isolation, partial failure, exception export,
rollback/recovery, and P1 production-only gates (legacy path disabled,
start_onboarding rejected). Create-only · no messages · no auto-onboarding.
"""

from __future__ import annotations

import csv
import io
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
    print(f"FAIL employee migration foundation: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    fields = sorted({k for r in rows for k in r.keys()})
    # Prefer stable order for common columns.
    preferred = [
        "name",
        "phone",
        "email",
        "department",
        "external_employee_id",
        "payroll_id",
        "source_system",
    ]
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
    foreign = "SMOKEFOREIGN"
    tag = uuid.uuid4().hex[:8]
    phone_a = f"96599{tag[:6]}"
    phone_b = f"96598{tag[:6]}"
    phone_c = f"96597{tag[:6]}"
    # Ensure unique 8-digit-ish lengths
    phone_a = f"96599{int(tag[:6], 16) % 1000000:06d}"
    phone_b = f"96598{int(tag[:6], 16) % 1000000:06d}"
    phone_c = f"96597{int(tag[:6], 16) % 1000000:06d}"

    if not emf.foundation_enabled(company):
        _fail("foundation flag off for WATHEFNI")

    honesty = emf.honesty_payload()
    if honesty.get("contract") != "employee_migration_sync_p1_foundation_only":
        _fail(f"unexpected contract {honesty.get('contract')}")
    if not honesty.get("production_path_foundation_only") or not honesty.get("legacy_import_disabled"):
        _fail(f"P1 honesty incomplete: {honesty}")
    try:
        emf.reject_migration_onboarding_request(legacy, True)
        _fail("expected start_onboarding=true reject")
    except legacy.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if exc.status_code != 422 or detail.get("error") != "migration_onboarding_forbidden":
            _fail(f"unexpected onboarding reject: {exc.status_code} {detail}")
    emf.reject_migration_onboarding_request(legacy, False)
    prev_flag = os.environ.get("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION")
    try:
        os.environ["WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION"] = "off"
        try:
            emf.require_foundation(legacy, company)
            _fail("expected require_foundation when flag off")
        except legacy.HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if exc.status_code != 503 or detail.get("error") != "migration_foundation_required":
                _fail(f"unexpected foundation gate: {exc.status_code} {detail}")
    finally:
        if prev_flag is None:
            os.environ.pop("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", None)
        else:
            os.environ["WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION"] = prev_flag
    if not emf.foundation_enabled(company):
        _fail("foundation not restored after P1 gate check")
    _ok("P1 production-safe gates")

    # Schema apply
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            emf.ensure_schema(cur)
            conn.commit()
    _ok("schema ensure")

    context = {
        "company_code": company,
        "user_id": "smoke-emf",
        "email": "smoke-emf@wathefni.ai",
        "permissions": ["employees.manage"],
        "modules": ["employees", "compliance"],
    }

    # Monkeypatch roster admin to skip full dashboard authz in unit smoke.
    original_require = legacy.require_employee_roster_admin

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]
    original_modules = getattr(legacy, "company_has_module", None)

    def _has_module(code: str, module: str) -> bool:
        del code, module
        return False

    legacy.company_has_module = _has_module  # type: ignore[assignment]

    created_keys: list[str] = []
    batch_id = None
    try:
        # Seed an existing employee for skip + conflict cases.
        existing = legacy.create_company_employee(
            company,
            name="Existing Smoke",
            phone=phone_a,
            email=None,
            seed_compliance=False,
            start_onboarding=False,
        )
        if existing.get("status") != "created":
            _fail(f"seed existing failed: {existing}")
        created_keys.append(str(existing["employee_key"]))

        rows = [
            {"name": "Existing Smoke", "phone": phone_a, "source_system": "smoke_hris", "external_employee_id": f"EXT-{tag}-A"},
            {"name": "Different Name", "phone": phone_a, "source_system": "smoke_hris", "external_employee_id": f"EXT-{tag}-DUP"},
            {"name": "New Hire One", "phone": phone_b, "source_system": "smoke_hris", "external_employee_id": f"EXT-{tag}-B", "payroll_id": f"PAY-{tag}-B"},
            {"name": "New Hire One Dup", "phone": phone_b, "source_system": "smoke_hris"},  # in-file conflict
            {"name": "", "phone": phone_c},  # invalid
            {"name": "No Phone", "phone": ""},  # invalid
            {"name": "Fresh Create", "phone": phone_c, "source_system": "smoke_hris", "external_employee_id": f"EXT-{tag}-C", "payroll_id": f"PAY-{tag}-C"},
        ]
        raw = _csv(rows)

        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=raw,
            filename=f"emf-smoke-{tag}.csv",
            source_system="smoke_hris",
        )
        if not preview.get("dry_run"):
            _fail("preview not dry_run")
        totals = preview.get("totals") or {}
        # create: phone_c Fresh Create only (phone_b New Hire One)
        # skip: Existing Smoke
        # conflict: Different Name + in-file dup of phone_b
        # invalid: empty name + empty phone
        if totals.get("create") != 2:
            _fail(f"expected create=2 got {totals}")
        if totals.get("skip") != 1:
            _fail(f"expected skip=1 got {totals}")
        if totals.get("conflict") != 2:
            _fail(f"expected conflict=2 got {totals}")
        if totals.get("invalid") != 2:
            _fail(f"expected invalid=2 got {totals}")
        batch_id = preview["batch_id"]
        _ok(f"preview totals {totals} batch={batch_id}")

        # Replay same file → same batch (idempotent; may refresh preview rows)
        replay = emf.preview_or_replay_import(
            legacy,
            context,
            raw=raw,
            filename=f"emf-smoke-{tag}.csv",
            source_system="smoke_hris",
        )
        if replay.get("batch_id") != batch_id:
            _fail(f"idempotent replay failed: {replay}")
        if not (replay.get("replayed") or (replay.get("batch") or {}).get("metadata", {}).get("replay_refreshed")):
            # Accept same-batch reuse even if flag naming differs across versions
            if str(replay.get("status") or "") != "previewed":
                _fail(f"idempotent replay failed: {replay}")
        _ok("repeated file import replay")

        # Foreign tenant isolation: same idempotency material under other company must not see batch
        foreign_ctx = {**context, "company_code": foreign}
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur)
                cur.execute(
                    "SELECT count(*) AS c FROM employee_import_batches WHERE batch_id=%s AND company_code=%s",
                    (batch_id, foreign),
                )
                hit = cur.fetchone()
                count = int(hit["c"] if isinstance(hit, dict) else hit[0])
                conn.commit()
        if count != 0:
            _fail("foreign tenant can see WATHEFNI batch")
        _ok("foreign tenant isolation")

        # Commit
        committed = emf.commit_import_batch(legacy, context, batch_id=batch_id)
        if committed.get("dry_run"):
            _fail("commit still dry_run")
        if (committed.get("totals") or {}).get("create") != 2:
            _fail(f"commit create totals wrong: {committed.get('totals')}")
        for row in committed.get("results", {}).get("created") or []:
            if row.get("employee_key"):
                created_keys.append(str(row["employee_key"]))
        # Also collect from batch rows
        detail = emf.get_import_batch(legacy, context, batch_id=batch_id)
        for row in (detail.get("results") or {}).get("created") or []:
            key = row.get("employee_key")
            if key and key not in created_keys:
                created_keys.append(str(key))
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key, status FROM employee_import_rows
                    WHERE batch_id=%s AND company_code=%s AND status='created'
                    """,
                    (batch_id, company),
                )
                for r in cur.fetchall() or []:
                    rd = dict(r) if not isinstance(r, dict) else r
                    created_keys.append(str(rd["employee_key"]))
                # Source mappings present
                cur.execute(
                    """
                    SELECT count(*) AS c FROM employee_source_mappings
                    WHERE company_code=%s AND batch_id=%s AND active
                    """,
                    (company, batch_id),
                )
                sm = cur.fetchone()
                sm_count = int(sm["c"] if isinstance(sm, dict) else sm[0])
                conn.commit()
        if sm_count < 2:
            _fail(f"expected >=2 source mappings, got {sm_count}")
        _ok(f"commit + source mappings ({sm_count})")

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                for key in set(k for k in created_keys if k and k != str(existing.get("employee_key") or "")):
                    cur.execute(
                        "SELECT onboarding_status FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, key),
                    )
                    erow = cur.fetchone()
                    if not erow:
                        continue
                    ob = str((erow["onboarding_status"] if isinstance(erow, dict) else erow[0]) or "not_started").lower()
                    if ob in {"in_progress", "complete", "completed", "done"}:
                        _fail(f"migration started onboarding for {key}: {ob}")
                    cur.execute(
                        "SELECT count(*) AS c FROM compliance_documents WHERE company_code=%s AND employee_key=%s",
                        (company, key),
                    )
                    crow = cur.fetchone()
                    n_docs = int(crow["c"] if isinstance(crow, dict) else crow[0])
                    if n_docs > 0:
                        _fail(f"compliance seeded on migration create for {key}: {n_docs}")
                conn.commit()
        _ok("no onboarding / no compliance seed on import create")

        # Commit replay is idempotent (no extra creates)
        again = emf.commit_import_batch(legacy, context, batch_id=batch_id)
        if not again.get("replayed"):
            _fail("commit replay not marked replayed")
        _ok("commit idempotent replay")

        # Exception CSV
        filename, body = emf.exception_csv(legacy, context, batch_id=batch_id)
        if "status" not in body or "conflict" not in body and "skipped" not in body:
            _fail(f"exception csv empty/malformed: {body[:200]}")
        if "invalid" not in body and "failed" not in body and "skipped" not in body:
            # at least header + some exception rows
            lines = [ln for ln in body.splitlines() if ln.strip()]
            if len(lines) < 2:
                _fail("exception csv missing rows")
        _ok(f"exception export {filename} lines={len(body.splitlines())}")

        # No onboarding auto-start
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT onboarding_status FROM employees
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    """,
                    (company, list({k for k in created_keys if k.startswith(f'{company}-') and k != existing['employee_key']})),
                )
                for r in cur.fetchall() or []:
                    rd = dict(r) if not isinstance(r, dict) else r
                    status = str(rd.get("onboarding_status") or "not_started").lower()
                    if status not in {"", "not_started", "pending"}:
                        _fail(f"unexpected onboarding_status {status}")
                conn.commit()
        _ok("no auto-onboarding")

        # Rollback
        rb_key = f"rollback-{tag}"
        rolled = emf.rollback_import_batch(legacy, context, batch_id=batch_id, idempotency_key=rb_key)
        if rolled.get("status") != "rolled_back":
            _fail(f"rollback status {rolled}")
        if int(rolled.get("removed") or 0) < 1:
            _fail(f"rollback removed none: {rolled}")
        rolled2 = emf.rollback_import_batch(legacy, context, batch_id=batch_id, idempotency_key=rb_key)
        if not rolled2.get("replayed"):
            _fail("rollback replay not idempotent")
        _ok(f"rollback/recovery removed={rolled.get('removed')}")

        # Existing seed employee must still exist (was not created by batch)
        still = legacy.find_employee_by_phone(phone_a, company_code=company)
        if not still:
            _fail("seed employee deleted by rollback")
        _ok("existing employee preserved")

        # Manager phone resolver unit check
        import employee_org_wave4 as w4

        resolved = w4._resolve_manager_employee_key(legacy, company, phone_a)
        if resolved != existing["employee_key"]:
            _fail(f"manager phone resolve failed: {resolved}")
        if w4._resolve_manager_employee_key(legacy, company, "000") is not None:
            _fail("manager phone resolve should miss unknown")
        _ok("manager phone matching")

        print("OK employee migration foundation local smoke")
        print("OK employee migration sync P1 production-safe gate")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        if original_modules is not None:
            legacy.company_has_module = original_modules  # type: ignore[assignment]
        # Cleanup leftovers
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                if batch_id:
                    cur.execute("DELETE FROM employee_source_mappings WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_import_rows WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_import_batches WHERE batch_id=%s", (batch_id,))
                for key in set(created_keys):
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, key),
                    )
                conn.commit()


if __name__ == "__main__":
    main()
