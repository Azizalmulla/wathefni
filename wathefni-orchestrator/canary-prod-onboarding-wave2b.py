#!/usr/bin/env python3
"""Onboarding Wave 2B — production synthetic canary (WATHEFNI only).

Keeps global ONBOARDING_SEED / ONBOARDING_HR_MUTATE off.
Mutations allowed only via WATHEFNI_ONBOARDING_SYNTHETIC_CANARY + strict
synthetic markers. Never mutates the four real checklists. Cleans up to zero.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

OUT = Path(os.environ.get("WAVE2B_CANARY_OUT", "/tmp/wave2b-prod-canary"))
OUT.mkdir(parents=True, exist_ok=True)

COMPANY = "WATHEFNI"
REAL_KEYS = [
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
]

PASS = 0
FAIL = 0
EVIDENCE: dict = {"checks": [], "ids": {}, "fingerprints": {}}


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    row = {"label": label, "pass": bool(cond), "detail": None if cond else detail}
    EVIDENCE["checks"].append(row)
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")


def fingerprint(cur, keys=None) -> list[str]:
    keys = keys or REAL_KEYS
    cur.execute(
        """
        SELECT oi.employee_key, oi.item_id, oi.required, oi.status,
               md5(coalesce(oi.value::text,'')) AS value_md5,
               coalesce(oi.reminder_count,0) AS reminder_count
        FROM onboarding_items oi
        JOIN employees e ON e.employee_key=oi.employee_key
        WHERE e.company_code=%s AND oi.employee_key = ANY(%s)
        ORDER BY oi.employee_key, oi.item_id
        """,
        (COMPANY, list(keys)),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    return sorted(
        f"{r['employee_key']}|{r['item_id']}|{r['required']}|{r['status']}|{r['value_md5']}|{r['reminder_count']}"
        for r in rows
    )


def cleanup(app, keys: list[str]) -> dict:
    deleted = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table, col in (
                ("onboarding_audit_events", "employee_key"),
                ("employee_onboarding_assignments", "employee_key"),
                ("onboarding_items", "employee_key"),
                ("file_registry", "subject_key"),
            ):
                if table == "file_registry":
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code=%s AND subject_type='employee' AND subject_key = ANY(%s)",
                        (COMPANY, keys),
                    )
                else:
                    cur.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (keys,))
                deleted[table] = cur.rowcount or 0
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            deleted["employees"] = cur.rowcount or 0
        conn.commit()
    return deleted


def main() -> int:
    if str(os.environ.get("WATHEFNI_ENV") or "").lower() not in {"production", "prod"}:
        raise SystemExit("refusing: WATHEFNI_ENV must be production")

    # Hard invariants for this canary process
    os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "off"
    os.environ["WATHEFNI_ONBOARDING_SYNTHETIC_CANARY"] = "on"
    os.environ.setdefault("WATHEFNI_ONBOARDING_SYNTHETIC_PHONE_PREFIXES", "965523")
    os.environ.setdefault("WATHEFNI_ONBOARDING_SYNTHETIC_NAME_PREFIX", "W2B-SYNTH|")

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import onboarding_wave2 as w2

    check("seed globally off", app.onboarding_seed_enabled() is False)
    check("hr_mutate globally off", app.onboarding_hr_mutate_enabled() is False)
    check("synthetic canary on", app.onboarding_synthetic_canary_enabled() is True)
    check("template 2.0.0", w2.CANONICAL_TEMPLATE_VERSION == "2.0.0")
    bank = w2.get_template_item("bank_details")
    check("bank ESS only", bank and bank.authority == "ess" and bank.collection_mode == "ess_encrypted", bank)

    app.ensure_schema()

    tag = uuid.uuid4().hex[:8]
    phone = f"965523{int(tag[:6], 16) % 100000:05d}"
    key = f"{COMPANY}-{phone}"
    phone2 = f"965523{(int(tag[:6], 16) + 7) % 100000:05d}"
    key2 = f"{COMPANY}-{phone2}"
    name = f"W2B-SYNTH|Prod Canary {tag}"
    name2 = f"W2B-SYNTH|Abandon {tag}"
    EVIDENCE["ids"] = {
        "tag": tag,
        "employee_key": key,
        "employee_key_abandon": key2,
        "phone": phone,
        "phone_abandon": phone2,
        "name": name,
    }

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            before_fp = fingerprint(cur)
            cur.execute(
                """
                SELECT count(*) AS c FROM onboarding_items oi
                JOIN employees e ON e.employee_key=oi.employee_key
                WHERE e.company_code=%s AND oi.employee_key = ANY(%s)
                """,
                (COMPANY, REAL_KEYS),
            )
            real_count = int((cur.fetchone() or {}).get("c") or 0)
        conn.commit()
    EVIDENCE["fingerprints"]["before"] = before_fp
    check("nineteen real checklist rows", real_count == 19, real_count)

    # Four reals must be refused by canary gates
    for rk in REAL_KEYS:
        real_emp = {"employee_key": rk, "company_code": COMPANY, "name": "Real", "phone": rk.split("-")[-1]}
        check(
            f"seed blocked for real {rk[-8:]}",
            app.onboarding_seed_allowed_for(real_emp) is False,
        )
        check(
            f"mutate blocked for real {rk[-8:]}",
            app.onboarding_hr_mutate_allowed_for(real_emp) is False,
        )
        blocked = app.start_onboarding(real_emp)
        check(
            f"start blocked for real {rk[-8:]}",
            isinstance(blocked, dict) and blocked.get("error") in {"synthetic_only_gate", "feature_disabled"},
            blocked,
        )

    synth_keys = [key, key2]
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for ek, ph, nm in ((key, phone, name), (key2, phone2, name2)):
                    cur.execute(
                        """
                        INSERT INTO employees
                          (employee_key, company_code, name, phone, onboarding_status,
                           documents_pending, documents_complete, start_date, raw_json)
                        VALUES (%s,%s,%s,%s,'not_started',0,0,%s,'{}'::jsonb)
                        ON CONFLICT (employee_key) DO UPDATE
                          SET name=EXCLUDED.name, phone=EXCLUDED.phone, updated_at=now()
                        """,
                        (ek, COMPANY, nm, ph, date.today() + timedelta(days=14)),
                    )
                    w2.stamp_onboarding_synthetic_markers(cur, company=COMPANY, employee_key=ek)
            conn.commit()

        emp = app.find_employee_by_key(key, company_code=COMPANY)
        emp2 = app.find_employee_by_key(key2, company_code=COMPANY)
        check("synthetic recognized", app.is_onboarding_synthetic_employee(emp) is True, emp)
        check("seed allowed synthetic", app.onboarding_seed_allowed_for(emp) is True)
        check("mutate allowed synthetic", app.onboarding_hr_mutate_allowed_for(emp) is True)

        # Delayed start (no seed yet)
        delayed = app.start_onboarding(emp, planned_start_date=date.today() + timedelta(days=10), delayed=True)
        check("delayed start", delayed.get("ok") and delayed.get("status") == "delayed", delayed)
        items = app.load_onboarding_items(employee_key=key, company_code=COMPANY)
        check("delayed no seed", len(items) == 0, len(items))

        # Reschedule to today then unattended activate
        res = app.reschedule_employee_onboarding(
            {"employee_key": key, "planned_start_date": date.today().isoformat()},
            company_code=COMPANY,
        )
        check("reschedule to today", res.get("ok") is True, res)
        activated = app.activate_delayed_onboarding_starts(company_code=COMPANY, today=date.today())
        check("unattended activate", key in (activated.get("activated") or []), activated)

        emp = app.find_employee_by_key(key, company_code=COMPANY)
        items = app.load_onboarding_items(employee_key=key, company_code=COMPANY)
        check("seeded after activate", len(items) >= 30, len(items))
        asg = None
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                asg = w2.get_assignment(cur, key)
                seeded_again = app.seed_onboarding_items(cur, emp)
            conn.commit()
        check("assignment version pinned", asg and asg.get("template_version") == "2.0.0", asg)
        check("seed idempotent", seeded_again == 0, seeded_again)

        # Duplicate start
        again = app.start_onboarding(emp, allow_restart=False)
        check("duplicate start idempotent", again.get("ok") and again.get("idempotent") is True, again)

        # Due dates + deps
        due_rows = [i for i in items if i.get("due_date")]
        check("due dates present", len(due_rows) > 0, len(due_rows))
        mark_res = app.mark_onboarding_item(
            {"employee_key": key, "item_id": "residence", "item_status": "received"},
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("dependency blocks residence", mark_res.get("error") == "dependency_unsatisfied", mark_res)

        items = app.load_onboarding_items(employee_key=key, company_code=COMPANY)
        civil = next(i for i in items if i["item_id"] == "civil_id")
        # Employee-style document upload via shared store path
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\n% wave2b synthetic civil id\n")
            tmp_path = tmp.name
        try:
            media = {"path": tmp_path, "type": "application/pdf"}
            storage = app.store_onboarding_document(employee=emp, item_id="civil_id", media=media)
            check("employee/hr document store", storage.get("ok") is True, storage)
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    app.record_employee_document_receipt(
                        cur,
                        employee=emp,
                        item_id="civil_id",
                        value="civil_id-synth.pdf",
                        media=media,
                        storage_result=storage,
                        extraction={},
                    )
                    # bump row_version via wave2 mark path alignment
                    cur.execute(
                        """
                        UPDATE onboarding_items
                        SET status='received', row_version=row_version+1, updated_at=now()
                        WHERE employee_key=%s AND item_id='civil_id'
                        RETURNING *
                        """,
                        (key,),
                    )
                    w2.record_onboarding_audit(
                        cur,
                        company_code=COMPANY,
                        employee_key=key,
                        item_id="civil_id",
                        event_type="onboarding_item_received",
                        after=dict(cur.fetchone() or {}),
                        metadata={"via": "wave2b_canary_upload"},
                    )
                    app.recompute_employee_onboarding_counts(cur, key)
                conn.commit()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # HR mark + waive + reminder
        photo = next(i for i in app.load_onboarding_items(employee_key=key, company_code=COMPANY) if i["item_id"] == "personal_photo")
        waive = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "personal_photo",
                "item_status": "waived",
                "expected_row_version": photo.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("hr waive", waive.get("ok") is True, waive)
        stale = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "personal_photo",
                "item_status": "received",
                "expected_row_version": photo.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("stale mutation fail closed", stale.get("error") == "stale_item_version", stale)

        rem = app.mark_onboarding_reminder_sent(key, company_code=COMPANY)
        check("reminder recorded", bool(rem), rem)

        # Bank plaintext rejected
        bank_block = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "bank_details",
                "item_status": "received",
                "value": "NBK KW81NBOK0000000000000000123456",
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("bank plaintext mark blocked", bank_block.get("error") == "bank_via_ess_required", bank_block)
        ok_bank, reason = app.validate_onboarding_item_receipt(
            "bank_details", "NBK KW81NBOK0000000000000000123456", None
        )
        check("bank receipt blocked", ok_bank is False and reason == "bank_via_ess_required", reason)
        check("bank forbidden helper", app.onboarding_plaintext_bank_forbidden("bank_details") is True)

        # ESS-style confirm (no plaintext value)
        bank_row = next(i for i in app.load_onboarding_items(employee_key=key, company_code=COMPANY) if i["item_id"] == "bank_details")
        bank_ok = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "bank_details",
                "item_status": "received",
                "expected_row_version": bank_row.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("bank ess confirm without plaintext", bank_ok.get("ok") is True, bank_ok)

        # Complete remaining required via mark/waive
        for item_id in ("employment_contract",):
            row = next(i for i in app.load_onboarding_items(employee_key=key, company_code=COMPANY) if i["item_id"] == item_id)
            marked = app.mark_onboarding_item(
                {
                    "employee_key": key,
                    "item_id": item_id,
                    "item_status": "received",
                    "expected_row_version": row.get("row_version"),
                },
                company_code=COMPANY,
                created_by_phone="96570000001",
            )
            check(f"mark {item_id}", marked.get("ok") is True, marked)

        # Reschedule open due dates while still in progress — reopen a pending optional then reschedule
        # Use a second delayed employee for cancel/abandon history proofs
        delayed2 = app.start_onboarding(emp2, planned_start_date=date.today() + timedelta(days=5), delayed=True)
        check("second delayed", delayed2.get("ok") is True, delayed2)
        # activate + seed emp2 then cancel
        app.reschedule_employee_onboarding(
            {"employee_key": key2, "planned_start_date": date.today().isoformat()},
            company_code=COMPANY,
        )
        app.activate_delayed_onboarding_starts(company_code=COMPANY, today=date.today())
        emp2 = app.find_employee_by_key(key2, company_code=COMPANY)
        started2 = app.start_onboarding(emp2, planned_start_date=date.today(), allow_restart=True)
        check(
            "emp2 in progress",
            bool(started2.get("ok")) and (started2.get("status") == "in_progress" or started2.get("idempotent")),
            started2,
        )
        # ensure seeded
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                app.seed_onboarding_items(cur, emp2)
            conn.commit()
        before_cancel_count = len(app.load_onboarding_items(employee_key=key2, company_code=COMPANY))
        cancel = app.cancel_employee_onboarding({"employee_key": key2, "reason": "withdrawn_canary"}, company_code=COMPANY)
        check("cancel ok", cancel.get("ok") and cancel.get("history_preserved") is True, cancel)
        after_cancel = app.load_onboarding_items(employee_key=key2, company_code=COMPANY)
        check("cancel preserves history", len(after_cancel) == before_cancel_count and len(after_cancel) > 0, len(after_cancel))
        cancel2 = app.cancel_employee_onboarding({"employee_key": key2, "reason": "again"}, company_code=COMPANY)
        check("cancel idempotent", cancel2.get("ok") and cancel2.get("idempotent") is True, cancel2)

        # Abandon on primary after proving completion path partially
        # Create a third mini path: abandon emp by resetting — use emp after marks
        abandon = app.abandon_employee_onboarding({"employee_key": key, "reason": "employment_ended_canary"}, company_code=COMPANY)
        check("abandon ok", abandon.get("ok") and abandon.get("history_preserved") is True, abandon)
        after_abandon = app.load_onboarding_items(employee_key=key, company_code=COMPANY)
        check("abandon preserves history", len(after_abandon) > 0, len(after_abandon))
        abandon2 = app.abandon_employee_onboarding({"employee_key": key, "reason": "again"}, company_code=COMPANY)
        check("abandon idempotent", abandon2.get("ok") and abandon2.get("idempotent") is True, abandon2)

        # Tenant isolation
        leaked = app.load_onboarding_items(employee_key=key, company_code="NOPE")
        check("cross-tenant empty", leaked == [], leaked)

        # Manager scope fail closed (viewer that cannot manage)
        scoped = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "passport",
                "item_status": "received",
                "viewer_phone": "96500000000",
            },
            company_code=COMPANY,
            created_by_phone="96500000000",
        )
        # abandoned terminal may also block; either fail-closed is acceptable
        check(
            "out-of-scope or terminal fail closed",
            scoped.get("ok") is False
            and scoped.get("error") in {"employee_outside_manager_scope", "onboarding_terminal", "synthetic_only_gate"},
            scoped,
        )

        # Reschedule due-date proof on a fresh delayed synthetic already cleaned — use emp2 cancelled (terminal)
        # Prove reschedule updated dues earlier: capture from emp before abandon via audit
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM onboarding_audit_events
                    WHERE employee_key = ANY(%s) AND event_type IN
                      ('onboarding_delayed','onboarding_delayed_activated','onboarding_rescheduled',
                       'onboarding_item_received','onboarding_item_waived','onboarding_cancelled','onboarding_abandoned')
                    """,
                    (synth_keys,),
                )
                audit_n = int((cur.fetchone() or {}).get("c") or 0)
        check("audit events recorded", audit_n >= 5, audit_n)

        # Due-date reschedule dedicated proof: new synthetic ephemeral
        phone3 = f"965523{(int(tag[:6], 16) + 17) % 100000:05d}"
        key3 = f"{COMPANY}-{phone3}"
        synth_keys.append(key3)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employees
                      (employee_key, company_code, name, phone, onboarding_status, start_date, raw_json)
                    VALUES (%s,%s,%s,%s,'not_started',%s,'{}'::jsonb)
                    ON CONFLICT (employee_key) DO NOTHING
                    """,
                    (key3, COMPANY, f"W2B-SYNTH|Due {tag}", phone3, date.today()),
                )
                w2.stamp_onboarding_synthetic_markers(cur, company=COMPANY, employee_key=key3)
            conn.commit()
        emp3 = app.find_employee_by_key(key3, company_code=COMPANY)
        start3 = app.start_onboarding(emp3, planned_start_date=date.today())
        check("due-proof start", start3.get("ok") is True, start3)
        items3 = app.load_onboarding_items(employee_key=key3, company_code=COMPANY)
        civil_due_before = next(i for i in items3 if i["item_id"] == "civil_id").get("due_date")
        new_start = date.today() + timedelta(days=20)
        rs = app.reschedule_employee_onboarding(
            {"employee_key": key3, "planned_start_date": new_start.isoformat()},
            company_code=COMPANY,
        )
        check("reschedule future", rs.get("ok") is True, rs)
        items3b = app.load_onboarding_items(employee_key=key3, company_code=COMPANY)
        civil_due_after = next(i for i in items3b if i["item_id"] == "civil_id").get("due_date")
        expected_due = new_start + timedelta(days=-3)
        check(
            "reschedule updates open due dates",
            str(civil_due_after)[:10] == str(expected_due)[:10] and str(civil_due_before)[:10] != str(civil_due_after)[:10],
            {"before": civil_due_before, "after": civil_due_after, "expected": expected_due},
        )

    finally:
        deleted = cleanup(app, synth_keys)
        dump("cleanup.json", deleted)
        EVIDENCE["cleanup"] = deleted
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                after_fp = fingerprint(cur)
                cur.execute(
                    """
                    SELECT count(*) AS c FROM employees
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    """,
                    (COMPANY, synth_keys),
                )
                left_emp = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT count(*) AS c FROM onboarding_items WHERE employee_key = ANY(%s)",
                    (synth_keys,),
                )
                left_items = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT count(*) AS c FROM employee_onboarding_assignments WHERE employee_key = ANY(%s)",
                    (synth_keys,),
                )
                left_asg = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT count(*) AS c FROM onboarding_audit_events WHERE employee_key = ANY(%s)",
                    (synth_keys,),
                )
                left_audit = int((cur.fetchone() or {}).get("c") or 0)
            conn.commit()
        EVIDENCE["fingerprints"]["after"] = after_fp
        check("four reals fingerprint unchanged", before_fp == after_fp, {"before_n": len(before_fp), "after_n": len(after_fp)})
        check("synthetic employees cleaned", left_emp == 0, left_emp)
        check("synthetic items cleaned", left_items == 0, left_items)
        check("synthetic assignments cleaned", left_asg == 0, left_asg)
        check("synthetic audit cleaned", left_audit == 0, left_audit)

    EVIDENCE["summary"] = {"pass": PASS, "fail": FAIL}
    dump("canary-evidence.json", EVIDENCE)
    print(f"\nRESULT pass={PASS} fail={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
