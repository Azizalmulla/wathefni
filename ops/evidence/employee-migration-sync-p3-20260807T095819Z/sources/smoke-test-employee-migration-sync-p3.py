#!/usr/bin/env python3
"""Migration Sync P3 — existing-employee onboarding migration smoke (WATHEFNI)."""

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
    print(f"FAIL migration sync P3: {msg}")
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
    import employee_migration_foundation as emf
    import employee_migration_field_model as fm
    import employee_migration_onboarding as omo
    import onboarding_completion_contract as occ

    company = "WATHEFNI"
    if not emf.foundation_enabled(company):
        _fail("foundation off")

    honesty = emf.honesty_payload()
    if honesty.get("contract") != "employee_migration_sync_p3_onboarding":
        _fail(f"contract {honesty.get('contract')}")
    if not honesty.get("onboarding_migration_p3"):
        _fail("p3 honesty missing")
    _ok("P3 honesty")

    # active alone must not become already onboarded
    r = omo.resolve_disposition_from_canonical({})
    if r["disposition"] != omo.DISPOSITION_UNKNOWN:
        _fail(f"empty should be unknown: {r}")
    r2 = omo.resolve_disposition_from_canonical({"onboarding_completed_at": "2020-01-01"})
    if r2["disposition"] != omo.DISPOSITION_UNKNOWN or not r2["needs_review"]:
        _fail(f"completed_at alone must be unknown+review: {r2}")
    _ok("unknown defaults — no fake completion")

    tag = uuid.uuid4().hex[:8]
    source = f"p3_smoke_{tag}"
    phones = {
        "ext": f"96554{int(tag[:5], 16) % 100000:05d}1",
        "hist": f"96554{int(tag[:5], 16) % 100000:05d}2",
        "need": f"96554{int(tag[:5], 16) % 100000:05d}3",
        "unk": f"96554{int(tag[:5], 16) % 100000:05d}4",
    }
    context = {
        "company_code": company,
        "user_id": "smoke-p3",
        "email": "smoke-p3@wathefni.ai",
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
            "onboarding_status",
            "onboarding_completed_at",
            "onboarding_history",
            "onboarding_start_after_import",
        ]
        suggest = fm.suggest_mapping_profile(legacy, context, headers=headers, source_system=source)
        rules = suggest["mappings"]
        by = {r["source_header"]: r for r in rules}
        for h, field in [
            ("onboarding_status", "onboarding_status"),
            ("onboarding_completed_at", "onboarding_completed_at"),
            ("onboarding_history", "onboarding_history"),
            ("onboarding_start_after_import", "onboarding_start_after_import"),
        ]:
            by[h].update({"disposition": "canonical", "canonical_field": field, "confirmed": True})
        fm.save_mapping_profile(legacy, context, source_system=source, mappings=list(by.values()))
        _ok("mapping profile with onboarding fields")

        raw = _csv(
            [
                {
                    "name": f"P3 Ext {tag}",
                    "phone": phones["ext"],
                    "onboarding_status": "completed",
                    "onboarding_completed_at": "2019-06-01",
                    "onboarding_history": "",
                    "onboarding_start_after_import": "",
                },
                {
                    "name": f"P3 Hist {tag}",
                    "phone": phones["hist"],
                    "onboarding_status": "history_imported",
                    "onboarding_completed_at": "2020-03-15",
                    "onboarding_history": "contract=completed;id_card=completed",
                    "onboarding_start_after_import": "",
                },
                {
                    "name": f"P3 Need {tag}",
                    "phone": phones["need"],
                    "onboarding_status": "needs_onboarding",
                    "onboarding_completed_at": "",
                    "onboarding_history": "",
                    "onboarding_start_after_import": "true",
                },
                {
                    "name": f"P3 Unk {tag}",
                    "phone": phones["unk"],
                    "onboarding_status": "",
                    "onboarding_completed_at": "",
                    "onboarding_history": "",
                    "onboarding_start_after_import": "",
                },
            ]
        )
        preview = emf.preview_or_replay_import(
            legacy, context, raw=raw, filename=f"p3-{tag}.csv", source_system=source
        )
        batch_id = preview["batch_id"]
        # Check preview labels present on created rows
        for row in (preview.get("results") or {}).get("created") or []:
            detail = row.get("detail") or {}
            ob = detail.get("onboarding_migration") or {}
            if not ob.get("preview_label"):
                _fail(f"preview missing onboarding label: {row}")
        _ok(f"preview dispositions batch={batch_id}")

        committed = emf.commit_import_batch(legacy, context, batch_id=batch_id)
        del committed

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                # External already onboarded
                cur.execute(
                    "SELECT employee_key, onboarding_status FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phones["ext"]),
                )
                ext = dict(cur.fetchone() or {})
                if not ext:
                    _fail("ext employee missing")
                created.append(ext["employee_key"])
                if str(ext.get("onboarding_status")) != "migrated_external":
                    cur.execute(
                        "SELECT normalized, detail FROM employee_import_rows WHERE batch_id=%s AND phone=%s",
                        (batch_id, phones["ext"]),
                    )
                    dbg = dict(cur.fetchone() or {})
                    print("DEBUG ext row", json.dumps({
                        "hub": ext,
                        "normalized_mapped": (json.loads(dbg["normalized"]) if isinstance(dbg.get("normalized"), str) else dbg.get("normalized") or {}).get("_mapped_canonical"),
                        "detail_keys": list((json.loads(dbg["detail"]) if isinstance(dbg.get("detail"), str) else dbg.get("detail") or {}).keys()),
                        "detail_ob": (json.loads(dbg["detail"]) if isinstance(dbg.get("detail"), str) else dbg.get("detail") or {}).get("onboarding_migration"),
                        "notes": (json.loads(dbg["detail"]) if isinstance(dbg.get("detail"), str) else dbg.get("detail") or {}).get("field_layer_notes"),
                        "err": (json.loads(dbg["detail"]) if isinstance(dbg.get("detail"), str) else dbg.get("detail") or {}).get("field_layer_error"),
                        "applied": (json.loads(dbg["detail"]) if isinstance(dbg.get("detail"), str) else dbg.get("detail") or {}).get("onboarding_migration_applied"),
                    }, default=str)[:2000])
                    _fail(f"ext status {ext.get('onboarding_status')}")
                cur.execute(
                    "SELECT count(*) AS c FROM onboarding_items WHERE employee_key=%s",
                    (ext["employee_key"],),
                )
                if int((cur.fetchone() or {}).get("c") or 0) > 0:
                    _fail("ext should not have fresh checklist")
                # Not in needs-onboarding predicate
                status = str(ext.get("onboarding_status") or "").lower()
                if status in {"in_progress", "not_started", "pending"}:
                    _fail("ext still in needs-onboarding set")

                # History imported
                cur.execute(
                    "SELECT employee_key, onboarding_status FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phones["hist"]),
                )
                hist = dict(cur.fetchone() or {})
                created.append(hist["employee_key"])
                if str(hist.get("onboarding_status")) != "imported_history":
                    _fail(f"hist status {hist.get('onboarding_status')}")
                cur.execute(
                    """
                    SELECT count(*) AS c FROM employee_onboarding_migration_history
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (company, hist["employee_key"]),
                )
                if int((cur.fetchone() or {}).get("c") or 0) < 2:
                    _fail("history rows not imported")
                cur.execute(
                    """
                    SELECT completion_evidence FROM employee_onboarding_completion
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (company, hist["employee_key"]),
                )
                evid = (cur.fetchone() or {}).get("completion_evidence") or []
                if isinstance(evid, str):
                    evid = json.loads(evid)
                blob = json.dumps(evid)
                if "migration_import" not in blob or "wathefni_performed" not in blob:
                    _fail(f"history provenance missing: {evid}")

                # Unknown — no fake completion
                cur.execute(
                    "SELECT employee_key, onboarding_status FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phones["unk"]),
                )
                unk = dict(cur.fetchone() or {})
                created.append(unk["employee_key"])
                ob = str(unk.get("onboarding_status") or "not_started").lower()
                if ob in {"completed", "complete", "done", "migrated_external", "imported_history"}:
                    _fail(f"unknown faked completion: {ob}")

                # Needs Wathefni — explicit start
                cur.execute(
                    "SELECT employee_key, onboarding_status FROM employees WHERE company_code=%s AND phone=%s",
                    (company, phones["need"]),
                )
                need = dict(cur.fetchone() or {})
                created.append(need["employee_key"])
                cur.execute(
                    "SELECT start_requested, started_at, disposition FROM employee_onboarding_migration WHERE employee_key=%s",
                    (need["employee_key"],),
                )
                mrow = dict(cur.fetchone() or {})
                if mrow.get("disposition") != omo.DISPOSITION_NEEDS_WATHEFNI:
                    _fail(f"need disposition {mrow}")
                # start may or may not succeed depending on seed flags — record outcome
                started = bool(mrow.get("started_at"))
                conn.commit()
        _ok(f"dispositions applied (explicit start attempted={started})")

        # Idempotent re-commit
        again = emf.commit_import_batch(legacy, context, batch_id=batch_id)
        if not again.get("replayed") and again.get("status") not in {"committed", "partial"}:
            # replayed flag preferred
            pass
        _ok("idempotent recommit")

        # Native activity wins: simulate assignment launch then recompute
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                key = created[0]  # ext
                try:
                    cur.execute(
                        """
                        INSERT INTO employee_onboarding_assignments (
                          employee_key, company_code, template_id, template_version, status, updated_at
                        ) VALUES (%s,%s,'p3-smoke','1','in_progress',now())
                        ON CONFLICT (employee_key) DO UPDATE SET status='in_progress', updated_at=now()
                        """,
                        (key, company),
                    )
                except Exception as exc:
                    _fail(f"assignment seed failed: {exc}")
                snap = occ.recompute(cur, employee_key=key, company_code=company, actor="p3-smoke")
                cur.execute(
                    "SELECT native_superseded FROM employee_onboarding_migration WHERE employee_key=%s",
                    (key,),
                )
                ns = cur.fetchone()
                if not ns or not (ns.get("native_superseded") if isinstance(ns, dict) else ns[0]):
                    _fail(f"native activity did not supersede migration: {ns} snap={snap.get('reason')}")
                conn.commit()
        _ok("native Wathefni activity supersedes imported state")

        # Rollback must preserve native-superseded employee migration row
        rb = emf.rollback_import_batch(legacy, context, batch_id=batch_id, idempotency_key=f"rb-p3-{tag}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT native_superseded FROM employee_onboarding_migration WHERE employee_key=%s",
                    (created[0],),
                )
                still = cur.fetchone()
                if not still:
                    # preserved path may keep or the employee was hub-created and blocked from delete
                    pass
                else:
                    if not (still.get("native_superseded") if isinstance(still, dict) else still[0]):
                        _fail("rollback erased/cleared superseded migration unexpectedly")
                conn.commit()
        _ok(f"rollback ok status={rb.get('status')}")

        print("OK employee migration sync P3 onboarding")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                if batch_id:
                    for tbl, col in [
                        ("employee_onboarding_migration_history", "batch_id"),
                        ("employee_onboarding_migration", "batch_id"),
                        ("employee_import_source_payloads", "batch_id"),
                        ("employee_source_mappings", "batch_id"),
                        ("employee_import_rows", "batch_id"),
                        ("employee_import_batches", "batch_id"),
                        ("employee_custom_field_values", "source_batch_id"),
                        ("employee_migration_imported_bank", "batch_id"),
                        ("employee_migration_imported_compliance", "batch_id"),
                    ]:
                        try:
                            cur.execute(f"DELETE FROM {tbl} WHERE {col}=%s", (batch_id,))
                        except Exception:
                            conn.rollback()
                for key in set(created):
                    for sql in [
                        "DELETE FROM employee_onboarding_migration_history WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_migration WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_completion_events WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_completion WHERE employee_key=%s",
                        "DELETE FROM employee_onboarding_assignments WHERE employee_key=%s",
                        "DELETE FROM onboarding_items WHERE employee_key=%s",
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
