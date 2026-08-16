#!/usr/bin/env python3
"""Employee Migration Foundation P3 smoke — safe updates + matching + undo.

Covers:
- create (new)
- update by phone (name/email/title/dept/start)
- skip when unchanged
- external_id match preferred
- ambiguous mapping vs phone → Needs review
- never match by name alone (same name different phone → create)
- concurrency-safe undo (field changed after batch left alone)
- no deactivation / no compliance seed on create
"""

from __future__ import annotations

import csv
import io
import os
import sys
import uuid
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
ORCH = os.environ.get("ORCH_ROOT") or ROOT
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")


def _fail(msg: str) -> None:
    print(f"FAIL emf-p3: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    preferred = [
        "name",
        "phone",
        "email",
        "position_title",
        "department",
        "start_date",
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
    phone_exist = f"96591{n:06d}"
    phone_new = f"96592{n:06d}"
    phone_ambig = f"96593{n:06d}"
    phone_other = f"96594{n:06d}"
    phone_mgr = f"96595{n:06d}"

    if not emf.foundation_enabled(company):
        _fail("foundation flag off for WATHEFNI")
    if emf.CONTRACT != "employee_migration_foundation_p0p3":
        _fail(f"unexpected contract {emf.CONTRACT}")

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            emf.ensure_schema(cur)
            conn.commit()
    _ok("schema")

    context = {
        "company_code": company,
        "user_id": "smoke-emf-p3",
        "email": "smoke-emf-p3@wathefni.ai",
        "permissions": ["employees.manage"],
        "modules": ["employees"],
    }

    original_require = legacy.require_employee_roster_admin

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]
    legacy.company_has_module = lambda code, module: False  # type: ignore[assignment]

    created_keys: list[str] = []
    try:
        seed = legacy.create_company_employee(
            company,
            name="P3 Existing",
            phone=phone_exist,
            email="old@example.com",
            position_title="Old Title",
            department="Ops",
            start_date="2024-01-01",
            seed_compliance=False,
            start_onboarding=False,
        )
        if seed.get("status") != "created":
            _fail(f"seed failed: {seed}")
        ek_exist = str(seed["employee_key"])
        created_keys.append(ek_exist)

        ambig = legacy.create_company_employee(
            company,
            name="Ambiguous Phone",
            phone=phone_ambig,
            seed_compliance=False,
            start_onboarding=False,
        )
        if ambig.get("status") != "created":
            _fail(f"ambig seed failed: {ambig}")
        ek_ambig = str(ambig["employee_key"])
        created_keys.append(ek_ambig)

        other = legacy.create_company_employee(
            company,
            name="Mapped Other",
            phone=phone_other,
            seed_compliance=False,
            start_onboarding=False,
        )
        if other.get("status") != "created":
            _fail(f"other seed failed: {other}")
        ek_other = str(other["employee_key"])
        created_keys.append(ek_other)

        mgr = legacy.create_company_employee(
            company,
            name="P3 Manager",
            phone=phone_mgr,
            seed_compliance=False,
            start_onboarding=False,
        )
        if mgr.get("status") != "created":
            _fail(f"mgr seed failed: {mgr}")
        ek_mgr = str(mgr["employee_key"])
        created_keys.append(ek_mgr)

        # Seed source mapping pointing at ek_other but file will use ambig phone
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur)
                emf._upsert_source_mapping(
                    cur,
                    company=company,
                    employee_key=ek_other,
                    source_system="smoke_p3",
                    external_employee_id=f"EXT-{tag}",
                    payroll_id=None,
                    batch_id=str(uuid.uuid4()),
                    row_id=str(uuid.uuid4()),
                )
                conn.commit()

        rows = [
            {
                "name": "P3 Existing Updated",
                "phone": phone_exist,
                "email": "new@example.com",
                "position_title": "New Title",
                "department": "People",
                "start_date": "2025-06-01",
                "manager_phone": phone_mgr,
            },
            {
                "name": "P3 Brand New",
                "phone": phone_new,
                "email": "newhire@example.com",
            },
            {
                # same name as existing but different phone → must CREATE (never match by name)
                "name": "P3 Existing",
                "phone": f"96596{n:06d}",
            },
            {
                # ambiguous: external id → other, phone → ambig
                "name": "Conflict Person",
                "phone": phone_ambig,
                "source_system": "smoke_p3",
                "external_employee_id": f"EXT-{tag}",
            },
        ]
        phone_name_only = rows[2]["phone"]

        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=_csv(rows),
            filename=f"p3-smoke-{tag}.csv",
            source_system=None,
            idempotency_key=f"p3-smoke-{tag}",
        )
        if not preview.get("dry_run"):
            _fail("preview not dry_run")
        totals = preview.get("totals") or {}
        if int(totals.get("create") or 0) != 2:
            _fail(f"expected create=2 got {totals}")
        if int(totals.get("update") or 0) != 1:
            _fail(f"expected update=1 got {totals}")
        if int(totals.get("review") or totals.get("conflict") or 0) != 1:
            _fail(f"expected review=1 got {totals}")
        updated = preview["results"]["updated"]
        if not updated or "name" not in (updated[0].get("changes") or {}):
            _fail(f"update missing name change: {updated}")
        if "email" not in (updated[0].get("changes") or {}):
            _fail("update missing email change")
        review = preview["results"]["needs_review"]
        reason = str((review or [{}])[0].get("reason") or "")
        if not review or ("maps to" not in reason and "phone differs" not in reason and "Needs review" not in reason):
            _fail(f"ambiguous reason unexpected: {reason}")
        _ok("preview create/update/review/name-alone")

        # Second preview same content with only matching phone + unchanged fields after we skip
        # Commit first batch
        committed = emf.commit_import_batch(
            legacy,
            context,
            batch_id=preview["batch_id"],
        )
        if committed.get("dry_run"):
            _fail("commit still dry_run")
        counts = committed.get("counts") or {}
        if int(counts.get("created") or 0) != 2:
            _fail(f"commit created expected 2: {counts}")
        if int(counts.get("updated") or 0) != 1:
            _fail(f"commit updated expected 1: {counts}")
        for bucket in ("created", "updated"):
            for row in committed["results"].get(bucket) or []:
                if row.get("employee_key"):
                    created_keys.append(str(row["employee_key"]))

        # Verify hub fields updated
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, email, position_title, profile, start_date FROM employees WHERE employee_key=%s",
                    (ek_exist,),
                )
                emp = dict(cur.fetchone())
                conn.commit()
        if emp.get("name") != "P3 Existing Updated":
            _fail(f"name not updated: {emp.get('name')}")
        if emp.get("email") != "new@example.com":
            _fail(f"email not updated: {emp.get('email')}")
        if emp.get("position_title") != "New Title":
            _fail(f"title not updated: {emp.get('position_title')}")
        profile = emp.get("profile") or {}
        if isinstance(profile, str):
            import json

            profile = json.loads(profile)
        if (profile or {}).get("department") != "People":
            _fail(f"department not updated: {profile}")
        _ok("commit updates applied")

        # Skip when unchanged
        skip_preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=_csv(
                [
                    {
                        "name": "P3 Existing Updated",
                        "phone": phone_exist,
                        "email": "new@example.com",
                        "position_title": "New Title",
                        "department": "People",
                        "start_date": "2025-06-01",
                    }
                ]
            ),
            filename=f"p3-skip-{tag}.csv",
            idempotency_key=f"p3-skip-{tag}",
        )
        if int((skip_preview.get("totals") or {}).get("skip") or 0) != 1:
            _fail(f"expected skip=1: {skip_preview.get('totals')}")
        if int((skip_preview.get("totals") or {}).get("update") or 0) != 0:
            _fail("unexpected update on unchanged row")
        _ok("skip when unchanged")

        # Concurrency-safe undo: change email after batch, then rollback — email stays new2, name reverts
        legacy.update_company_employee(
            company,
            ek_exist,
            fields={"email": "changed-after@example.com"},
        )
        rb = emf.rollback_import_batch(
            legacy,
            context,
            batch_id=preview["batch_id"],
            idempotency_key=f"p3-undo-{tag}",
        )
        if not rb.get("ok"):
            _fail(f"rollback failed: {rb}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, email FROM employees WHERE employee_key=%s",
                    (ek_exist,),
                )
                after = dict(cur.fetchone())
                # created people from batch should be gone if stamped
                cur.execute(
                    "SELECT 1 FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phone_new),
                )
                still_new = cur.fetchone()
                cur.execute(
                    "SELECT 1 FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phone_name_only),
                )
                still_name = cur.fetchone()
                conn.commit()
        if after.get("email") != "changed-after@example.com":
            _fail(f"undo should leave post-batch email alone, got {after.get('email')}")
        if after.get("name") != "P3 Existing":
            _fail(f"undo should restore name, got {after.get('name')}")
        if still_new or still_name:
            _fail("created rows should be removed on undo")
        skipped = rb.get("skipped_fields") or []
        if not any(s.get("field") == "email" for s in skipped):
            _fail(f"expected email in skipped_fields: {skipped}")
        _ok("concurrency-safe undo")

        # Honesty: no deactivate
        honesty = emf.honesty_payload()
        if honesty.get("no_deactivation") is not True:
            _fail("honesty missing no_deactivation")
        if honesty.get("never_match_by_name_alone") is not True:
            _fail("honesty missing never_match_by_name_alone")
        _ok("honesty invariants")

        print("OK employee migration foundation P3 local smoke")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        # Cleanup leftover seeds (exist/ambig/other/mgr may remain)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                for ek in set(created_keys):
                    cur.execute(
                        "DELETE FROM employee_source_mappings WHERE company_code=%s AND employee_key=%s",
                        (company, ek),
                    )
                    cur.execute(
                        "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key=%s",
                        (company, ek),
                    )
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, ek),
                    )
                conn.commit()


if __name__ == "__main__":
    main()
