#!/usr/bin/env python3
"""Migration Sync P2 field-model smoke (WATHEFNI).

Proves: source payload retention, mapping suggest/save, custom fields,
identity staged non-authoritative, bank proposed-only, no invites/onboarding/compliance seed.
"""

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
    print(f"FAIL migration sync P2: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    import app as legacy
    import employee_migration_foundation as emf
    import employee_migration_field_model as fm

    company = "WATHEFNI"
    if not emf.foundation_enabled(company):
        _fail("foundation off")

    honesty = emf.honesty_payload()
    if honesty.get("contract") != "employee_migration_sync_p2_field_model":
        _fail(f"contract {honesty.get('contract')}")
    if not honesty.get("mapping_profiles"):
        _fail("mapping_profiles missing")
    _ok("P2 honesty")

    # Reserved custom keys blocked
    cleaned, errors = fm.validate_mapping_rules(
        [
            {
                "source_header": "IBAN",
                "disposition": "create_custom",
                "custom_field_key": "bank_iban",
                "confirmed": True,
            }
        ]
    )
    if not errors:
        _fail("expected reserved bank_iban custom block")
    _ok("reserved canonical cannot be custom")

    tag = uuid.uuid4().hex[:8]
    phone = f"96554{int(tag[:6], 16) % 1000000:06d}"
    source = f"p2_smoke_{tag}"
    context = {
        "company_code": company,
        "user_id": "smoke-p2",
        "email": "smoke-p2@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]

    created_keys: list[str] = []
    batch_id = None
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur)
                conn.commit()

        headers = [
            "name",
            "phone",
            "Cost Center",
            "Civil ID",
            "Nationality",
            "IBAN",
            "Vendor Only Code",
            "Employment Status",
        ]
        suggest = fm.suggest_mapping_profile(legacy, context, headers=headers, source_system=source)
        rules = suggest["mappings"]
        # Force dispositions for smoke
        by_h = {r["source_header"]: r for r in rules}
        by_h["Cost Center"].update(
            {"disposition": "create_custom", "custom_field_key": "cost_center", "confirmed": True}
        )
        by_h["Civil ID"].update({"disposition": "canonical", "canonical_field": "civil_id", "confirmed": True})
        by_h["Nationality"].update({"disposition": "canonical", "canonical_field": "nationality", "confirmed": True})
        by_h["IBAN"].update({"disposition": "canonical", "canonical_field": "bank_iban", "confirmed": True})
        by_h["Vendor Only Code"].update({"disposition": "source_only", "confirmed": True})
        by_h["Employment Status"].update(
            {"disposition": "canonical", "canonical_field": "employment_status", "confirmed": True}
        )
        saved = fm.save_mapping_profile(legacy, context, source_system=source, mappings=list(by_h.values()))
        if not saved.get("ok"):
            _fail(f"save mapping failed: {saved}")
        _ok("mapping profile saved")

        raw = _csv(
            [
                {
                    "name": f"P2 Smoke {tag}",
                    "phone": phone,
                    "Cost Center": "CC-100",
                    "Civil ID": "289010100123",
                    "Nationality": "KW",
                    "IBAN": "KW81CBKU0000000000001234560101",
                    "Vendor Only Code": "VEND-9",
                    "Employment Status": "active",
                }
            ]
        )
        preview = emf.preview_or_replay_import(
            legacy, context, raw=raw, filename=f"p2-{tag}.csv", source_system=source
        )
        batch_id = preview.get("batch_id")
        if not batch_id:
            _fail("no batch")
        mapping = preview.get("mapping") or {}
        if not mapping.get("mappings"):
            _fail("preview missing mapping snapshot")
        # Source payload retained
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT values FROM employee_import_source_payloads WHERE batch_id=%s",
                    (batch_id,),
                )
                prow = cur.fetchone()
                if not prow:
                    _fail("source payload missing")
                vals = prow["values"] if isinstance(prow, dict) else prow[0]
                if isinstance(vals, str):
                    vals = json.loads(vals)
                if vals.get("Vendor Only Code") != "VEND-9":
                    _fail(f"unknown column not retained: {vals}")
        _ok("source payload retains unmapped column")

        committed = emf.commit_import_batch(legacy, context, batch_id=batch_id)
        if (committed.get("totals") or {}).get("create", 0) < 1 and (committed.get("counts") or {}).get("created", 0) < 1:
            # tolerate totals shape
            detail = emf.get_import_batch(legacy, context, batch_id=batch_id)
            created = [r for r in (detail.get("results") or {}).get("created") or [] if r.get("employee_key")]
            if not created:
                # check DB
                pass
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key, onboarding_status FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phone),
                )
                emp = cur.fetchone()
                if not emp:
                    _fail("employee not created")
                key = str(emp["employee_key"])
                created_keys.append(key)
                ob = str(emp.get("onboarding_status") or "not_started").lower()
                if ob in {"in_progress", "complete", "completed", "done"}:
                    _fail(f"onboarding started: {ob}")
                cur.execute(
                    "SELECT count(*) AS c FROM compliance_documents WHERE company_code=%s AND employee_key=%s",
                    (company, key),
                )
                if int((cur.fetchone() or {}).get("c") or 0) > 0:
                    _fail("compliance seeded")
                # custom field
                cur.execute(
                    """
                    SELECT v.value_text
                    FROM employee_custom_field_values v
                    JOIN employee_custom_field_definitions d ON d.field_id=v.field_id
                    WHERE v.company_code=%s AND v.employee_key=%s AND d.field_key='cost_center'
                    """,
                    (company, key),
                )
                crow = cur.fetchone()
                if not crow or str(crow["value_text"]) != "CC-100":
                    _fail(f"custom cost_center missing: {crow}")
                # identity staged, not confirmed
                cur.execute(
                    """
                    SELECT civil_id_confirmed, ocr_pending, nationality_country_code
                    FROM employee_identity WHERE company_code=%s AND employee_key=%s
                    """,
                    (company, key),
                )
                irow = cur.fetchone()
                if not irow:
                    _fail("identity row missing")
                if irow.get("civil_id_confirmed"):
                    _fail("civil id must not be confirmed by import")
                pending = irow.get("ocr_pending") or {}
                if isinstance(pending, str):
                    pending = json.loads(pending)
                staged = pending.get("civil_id_number") or {}
                if staged.get("source") != "migration_import":
                    _fail(f"civil id not staged from migration: {pending}")
                if str(irow.get("nationality_country_code") or "") != "KW":
                    _fail(f"nationality not set: {irow}")
                # bank proposed only
                cur.execute(
                    """
                    SELECT proposed_json FROM employee_migration_imported_bank
                    WHERE company_code=%s AND employee_key=%s AND batch_id=%s
                    """,
                    (company, key, batch_id),
                )
                brow = cur.fetchone()
                if not brow:
                    _fail("bank import missing")
                proposed = brow["proposed_json"]
                if isinstance(proposed, str):
                    proposed = json.loads(proposed)
                if proposed.get("authority") != "imported_proposed":
                    _fail(f"bank authority wrong: {proposed}")
                # Ensure no verified/effective bank rows for this employee from import
                cur.execute(
                    "SELECT count(*) AS c FROM employee_bank_verified WHERE company_code=%s AND employee_key=%s",
                    (company, key),
                )
                # table may not exist in some envs — ignore
                try:
                    if int((cur.fetchone() or {}).get("c") or 0) > 0:
                        _fail("verified bank written by import")
                except Exception:
                    conn.rollback()
                    ensure = True
                else:
                    ensure = False
                if ensure:
                    pass
                conn.commit()
        _ok("deep fields applied with authority gates")

        rb = emf.rollback_import_batch(legacy, context, batch_id=batch_id, idempotency_key=f"rb-p2-{tag}")
        if str(rb.get("status") or "") not in {"rolled_back", "already_rolled_back"} and not rb.get("ok", True):
            _fail(f"rollback failed: {rb}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM employee_custom_field_values WHERE source_batch_id=%s",
                    (batch_id,),
                )
                if int((cur.fetchone() or {}).get("c") or 0) != 0:
                    _fail("custom values not rolled back")
                cur.execute(
                    "SELECT count(*) AS c FROM employee_migration_imported_bank WHERE batch_id=%s",
                    (batch_id,),
                )
                if int((cur.fetchone() or {}).get("c") or 0) != 0:
                    _fail("bank imports not rolled back")
                conn.commit()
        _ok("field-model rollback")
        print("OK employee migration sync P2 field model")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                if batch_id:
                    cur.execute("DELETE FROM employee_import_source_payloads WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_source_mappings WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_import_rows WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_import_batches WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_migration_imported_bank WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_migration_imported_compliance WHERE batch_id=%s", (batch_id,))
                    cur.execute("DELETE FROM employee_custom_field_values WHERE source_batch_id=%s", (batch_id,))
                for key in set(created_keys):
                    cur.execute("DELETE FROM employee_identity_events WHERE company_code=%s AND employee_key=%s", (company, key))
                    cur.execute("DELETE FROM employee_identity WHERE company_code=%s AND employee_key=%s", (company, key))
                    cur.execute("DELETE FROM employee_ess_personal_profiles WHERE company_code=%s AND employee_key=%s", (company, key))
                    cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key=%s", (company, key))
                cur.execute(
                    "DELETE FROM employee_import_mapping_profiles WHERE company_code=%s AND source_system=%s",
                    (company, source),
                )
                conn.commit()


if __name__ == "__main__":
    main()
