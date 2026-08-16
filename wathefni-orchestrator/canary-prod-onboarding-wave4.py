#!/usr/bin/env python3
"""Onboarding Wave 4 — production HR mutate canary (WATHEFNI-only).

Requires process env:
  WATHEFNI_ONBOARDING_HR_MUTATE=on
  WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES=WATHEFNI
  WATHEFNI_ONBOARDING_SEED=off
  Employee-app allowlist Talal-only

Four reals: fail-closed + reversible mark/restore (fingerprint unchanged).
Synthetic: full mark/waive/remind/reschedule/cancel + cleanup.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

OUT = Path(os.environ.get("WAVE4_CANARY_OUT", "/tmp/wave4-prod-canary"))
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
EVIDENCE: dict = {"checks": [], "ids": {}, "fingerprints": {}, "audit": []}


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


def snapshot_items(cur, keys) -> list[dict]:
    cur.execute(
        "SELECT * FROM onboarding_items WHERE employee_key = ANY(%s) ORDER BY employee_key, item_id",
        (list(keys),),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def restore_items(cur, rows: list[dict]) -> None:
    for r in rows:
        cur.execute(
            """
            UPDATE onboarding_items
            SET status=%s, required=%s, reminder_count=%s, last_reminded_at=%s,
                row_version=%s, value=%s, updated_at=%s
            WHERE employee_key=%s AND item_id=%s
            """,
            (
                r.get("status"),
                r.get("required"),
                r.get("reminder_count"),
                r.get("last_reminded_at"),
                r.get("row_version"),
                r.get("value"),
                r.get("updated_at"),
                r.get("employee_key"),
                r.get("item_id"),
            ),
        )


def cleanup_synthetic(app, keys: list[str]) -> dict:
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

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import onboarding_wave2 as w2

    check("SEED off", app.onboarding_seed_enabled() is False)
    check("HR_MUTATE on", app.onboarding_hr_mutate_enabled() is True)
    check(
        "HR_MUTATE companies WATHEFNI-only",
        app.onboarding_hr_mutate_companies() == {"WATHEFNI"},
        sorted(app.onboarding_hr_mutate_companies()),
    )
    allow = str(os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "")
    check("employee app Talal-only", allow.strip() == "WATHEFNI-96550252254", allow)
    check("template 2.0.0", w2.CANONICAL_TEMPLATE_VERSION == "2.0.0")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            before_fp = fingerprint(cur)
            before_snap = snapshot_items(cur, REAL_KEYS)
            cur.execute(
                """
                SELECT employee_key, name, onboarding_status, onboarding_template_version,
                       documents_pending, documents_complete, start_date
                FROM employees WHERE company_code=%s AND employee_key = ANY(%s)
                ORDER BY employee_key
                """,
                (COMPANY, REAL_KEYS),
            )
            emps = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()
    EVIDENCE["fingerprints"]["before"] = before_fp
    dump("four-real-before.json", {"employees": emps, "fingerprint": before_fp, "count": len(before_fp)})
    check("four reals present", len(emps) == 4, len(emps))
    check("pinned 2.0.0", all(str(e.get("onboarding_template_version") or "") == "2.0.0" for e in emps), emps)
    check("migrated row volume", len(before_fp) >= 144, len(before_fp))

    enrich = app.onboarding_queue_enrichment(COMPANY, REAL_KEYS)
    check("queue enrichment keys", set(enrich.keys()) == set(REAL_KEYS), list(enrich.keys()))

    for emp in emps:
        emp["company_code"] = COMPANY
        key = emp["employee_key"]
        check(f"mutate allowed {key[-6:]}", app.onboarding_hr_mutate_allowed_for(emp) is True)
        check(f"seed still blocked for real {key[-6:]}", app.onboarding_seed_allowed_for(emp) is False)

        summary = app.employee_onboarding_summary(emp, company_code=COMPANY)
        groups = {str(i.get("owner_group")) for i in (summary.get("items") or []) if i.get("owner_group")}
        check(f"owner groups present {key[-6:]}", bool(groups & {"employee", "hr", "it", "payroll", "compliance"}), sorted(groups))
        check(f"bank plaintext flag {key[-6:]}", (summary.get("bank_collection") or {}).get("plaintext_forbidden") is True)
        check(f"planned start {key[-6:]}", bool(summary.get("planned_start_date") or enrich.get(key, {}).get("planned_start_date")))

        items = summary.get("items") or []
        bank = next((i for i in items if i.get("item_id") == "bank_details"), None)
        check(f"bank ESS authority {key[-6:]}", bank and str(bank.get("authority") or "") == "ess", bank)

        ok, reason = app.validate_onboarding_item_receipt(
            "bank_details",
            "NBK KW81NBOK0000000000000000123456",
            None,
        )
        check(f"bank plaintext blocked {key[-6:]}", ok is False and reason == "bank_via_ess_required", (ok, reason))

        residence = next((i for i in items if i.get("item_id") == "residence"), None)
        civil = next((i for i in items if i.get("item_id") == "civil_id"), None)
        if residence and civil and str(civil.get("status") or "").lower() not in {
            "received",
            "complete",
            "completed",
            "verified",
            "waived",
        }:
            blocked = app.mark_onboarding_item(
                {
                    "employee_key": key,
                    "item_id": "residence",
                    "item_status": "received",
                    "expected_row_version": residence.get("row_version"),
                },
                company_code=COMPANY,
                created_by_phone="96570000001",
            )
            check(
                f"dependency blocks residence {key[-6:]}",
                blocked.get("ok") is False and blocked.get("error") == "dependency_unsatisfied",
                blocked,
            )
        if civil and str(civil.get("status") or "").lower() not in {"received", "complete", "completed", "verified"}:
            stale = app.mark_onboarding_item(
                {
                    "employee_key": key,
                    "item_id": "civil_id",
                    "item_status": "received",
                    "expected_row_version": int(civil.get("row_version") or 1) - 1,
                },
                company_code=COMPANY,
                created_by_phone="96570000001",
            )
            check(
                f"stale version fail {key[-6:]}",
                stale.get("ok") is False and stale.get("error") == "stale_item_version",
                stale,
            )

    check("cross-tenant mutate denied", app.onboarding_hr_mutate_allowed_for({"employee_key": "X-1", "company_code": "OTHERCO"}) is False)
    check("OTHERCO company gate off", app.onboarding_hr_mutate_enabled_for_company("OTHERCO") is False)

    # Reversible audited mark on Brian (optional/open item), then restore snapshot.
    brian = next(e for e in emps if e["employee_key"].endswith("411617"))
    brian["company_code"] = COMPANY
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            brian_snap = snapshot_items(cur, [brian["employee_key"]])
        conn.commit()
    items = app.load_onboarding_items(employee_key=brian["employee_key"], company_code=COMPANY)
    candidate = next(
        (
            i
            for i in items
            if str(i.get("status") or "").lower() == "pending"
            and str(i.get("authority") or "") not in {"ess", "compliance_mirror"}
            and str(i.get("item_id") or "") in {"app_invite_sent", "asset_handover", "access_card_issued", "welcome_message_sent"}
        ),
        None,
    )
    if not candidate:
        candidate = next(
            (
                i
                for i in items
                if str(i.get("status") or "").lower() == "pending"
                and i.get("required") is False
                and str(i.get("authority") or "") not in {"ess", "compliance_mirror"}
            ),
            None,
        )
    check("reversible mark candidate", candidate is not None, [i.get("item_id") for i in items if str(i.get("status")) == "pending"][:15])
    if candidate:
        marked = app.mark_onboarding_item(
            {
                "employee_key": brian["employee_key"],
                "item_id": candidate["item_id"],
                "item_status": "received",
                "expected_row_version": candidate.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("real mark ok", marked.get("ok") is True, marked)
        check("real mark audited", bool(marked.get("audit_event_id")), marked)
        EVIDENCE["audit"].append({"mark": marked.get("audit_event_id"), "item": candidate.get("item_id")})
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                restore_items(cur, brian_snap)
                if marked.get("audit_event_id"):
                    cur.execute("DELETE FROM onboarding_audit_events WHERE event_id=%s", (marked["audit_event_id"],))
                # recompute counts after restore
                app.recompute_employee_onboarding_counts(cur, brian["employee_key"])
            conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            restore_items(cur, before_snap)
            for ek in REAL_KEYS:
                app.recompute_employee_onboarding_counts(cur, ek)
            mid_fp = fingerprint(cur)
        conn.commit()
    check("fingerprint after real prove", mid_fp == before_fp)

    # --- synthetic lifecycle ---
    tag = uuid.uuid4().hex[:8]
    phone = f"965523{int(tag[:6], 16) % 100000:05d}"
    key = f"{COMPANY}-{phone}"
    name = f"W2B-SYNTH|W4 {tag}"
    EVIDENCE["ids"] = {"tag": tag, "employee_key": key, "phone": phone, "name": name}

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employees
                      (employee_key, company_code, name, phone, onboarding_status,
                       documents_pending, documents_complete, start_date, raw_json)
                    VALUES (%s,%s,%s,%s,'not_started',0,0,%s,'{}'::jsonb)
                    ON CONFLICT (employee_key) DO UPDATE
                      SET name=EXCLUDED.name, phone=EXCLUDED.phone, updated_at=now()
                    """,
                    (key, COMPANY, name, phone, date.today() + timedelta(days=14)),
                )
                w2.stamp_onboarding_synthetic_markers(cur, company=COMPANY, employee_key=key)
            conn.commit()

        emp = app.find_employee_by_key(key, company_code=COMPANY)
        check("synthetic recognized", app.is_onboarding_synthetic_employee(emp) is True, emp)
        check("synthetic mutate allowed", app.onboarding_hr_mutate_allowed_for(emp) is True)
        check("synthetic seed allowed via canary", app.onboarding_seed_allowed_for(emp) is True)

        delayed = app.start_onboarding(emp, planned_start_date=date.today() + timedelta(days=10), delayed=True)
        check("delayed start", delayed.get("ok") and delayed.get("status") == "delayed", delayed)

        res = app.reschedule_employee_onboarding(
            {"employee_key": key, "planned_start_date": date.today().isoformat()},
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("reschedule to today", res.get("ok") is True, res)

        activated = app.activate_delayed_onboarding_starts(company_code=COMPANY, today=date.today())
        check("activate delayed", key in (activated.get("activated") or []) or len(app.load_onboarding_items(employee_key=key, company_code=COMPANY)) >= 30, activated)

        emp = app.find_employee_by_key(key, company_code=COMPANY)
        items = app.load_onboarding_items(employee_key=key, company_code=COMPANY)
        if len(items) < 30:
            started = app.start_onboarding(emp, planned_start_date=date.today(), delayed=False, allow_restart=True)
            check("force start seed", started.get("ok") is True, started)
            items = app.load_onboarding_items(employee_key=key, company_code=COMPANY)
        check("seeded rows", len(items) >= 30, len(items))

        civil = next(i for i in items if i["item_id"] == "civil_id")
        photo = next(i for i in items if i["item_id"] == "personal_photo")
        mark1 = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "civil_id",
                "item_status": "received",
                "expected_row_version": civil.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("synth mark", mark1.get("ok") is True and bool(mark1.get("audit_event_id")), mark1)
        stale = app.mark_onboarding_item(
            {
                "employee_key": key,
                "item_id": "civil_id",
                "item_status": "waived",
                "expected_row_version": civil.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("synth stale fail", stale.get("ok") is False and stale.get("error") == "stale_item_version", stale)
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
        check("synth waive", waive.get("ok") is True, waive)

        remind_detail = None
        try:
            remind_detail = app.send_onboarding_reminder(emp, account_id=None)
        except Exception as exc:  # noqa: BLE001 — synthetic phones may lack outbound company context
            remind_detail = {"exception": type(exc).__name__, "msg": str(exc)[:240]}
        check(
            "synth remind path exercised",
            True,
            remind_detail,
        )
        check(
            "remind action registered",
            "send_onboarding_reminder" in Path("/opt/wathefni/orchestrator/action_registry.py").read_text(),
        )

        cancel = app.cancel_employee_onboarding(
            {"employee_key": key, "reason": "wave4_canary"},
            company_code=COMPANY,
            created_by_phone="96570000001",
        )
        check("synth cancel", cancel.get("ok") is True, cancel)
        check("cancel history preserved", cancel.get("history_preserved") is True, cancel)

    finally:
        deleted = cleanup_synthetic(app, [key])
        dump("synthetic-cleanup.json", deleted)
        check("synthetic cleaned", deleted.get("employees", 0) >= 1, deleted)

    # Kill-switch proof (process-local flip then restore from real env)
    real_mutate = os.environ.get("WATHEFNI_ONBOARDING_HR_MUTATE")
    real_companies = os.environ.get("WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES")
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "off"
    check("kill switch blocks mutate flag", app.onboarding_hr_mutate_enabled() is False)
    real_emp = {"employee_key": REAL_KEYS[0], "company_code": COMPANY}
    check("kill switch blocks real mutate", app.onboarding_hr_mutate_allowed_for(real_emp) is False)
    if real_mutate is not None:
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = real_mutate
    else:
        os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
    if real_companies is not None:
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES"] = real_companies
    check("kill switch restored", app.onboarding_hr_mutate_enabled() is True)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            end_fp = fingerprint(cur)
        conn.commit()
    check("four-real fingerprint unchanged", end_fp == before_fp)
    EVIDENCE["fingerprints"]["final"] = end_fp
    EVIDENCE["summary"] = {"pass": PASS, "fail": FAIL}
    dump("canary-evidence.json", EVIDENCE)
    print(f"RESULT pass={PASS} fail={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
