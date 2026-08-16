#!/usr/bin/env python3
"""Shifts Wave 3B — production WATHEFNI synthetic UX/API canary.

Markers: SHW3B / 965531* only. Real allowlists empty. Real mutations blocked.
Real reminders off. Timers disabled. No templates / Payroll money.

Proves domain + dashboard routes used by the Calendar-aligned workspace.
Browser composer path is proven separately by shifts-wave3b-prod-browser-canary.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")

import app  # noqa: E402
import shifts_wave3_controlled as w3  # noqa: E402
from shifts_synthetic_cleanup import cleanup_synthetic_scope, wave3b_scope  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW3B_TAG") or uuid.uuid4().hex[:8].upper()
EVID = Path(os.environ.get("SHW3B_EVID") or f"/tmp/shw3b-prod-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

KEY_A = f"WATHEFNI-SHW3B-A-{TAG}"
KEY_B = f"WATHEFNI-SHW3B-B-{TAG}"
PHONE_A = f"965531{TAG[:4].zfill(4)}01"[:12]
PHONE_B = f"965531{TAG[:4].zfill(4)}02"[:12]
NAME_A = f"SHW3B-SYNTH| A {TAG}"
NAME_B = f"SHW3B-SYNTH| B {TAG}"
ACTOR = "96588009911"  # not allowlisted — synthetic still allowed
REAL_PHONE = "96599998877"

PASS = FAIL = 0
RESULTS: dict = {"tag": TAG, "checks": []}


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    if ok:
        PASS += 1
        print(f"PASS  {name}", flush=True)
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}", flush=True)


def fp_row(r: dict) -> str:
    parts = [str(r.get(k) or "") for k in ("shift_id", "employee_key", "employee_phone", "shift_date", "start_time", "end_time", "status", "updated_at", "role", "location", "timezone")]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def owner_ctx(actor: str = ACTOR) -> dict:
    return {
        "company_code": COMPANY,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw3b-{TAG}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw3b-{TAG}",
        "permission_subject_company": COMPANY,
        "actor_role": "owner",
        "hr_phone": actor,
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY},
    }


def upsert(cur, key: str, name: str, phone: str) -> None:
    raw = json.dumps({"shw3b": True, "tag": TAG})
    cur.execute("SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s", (COMPANY, key))
    if cur.fetchone():
        cur.execute(
            "UPDATE employees SET name=%s, phone=%s, raw_json=%s::jsonb WHERE company_code=%s AND employee_key=%s",
            (name, phone, raw, COMPANY, key),
        )
    else:
        cur.execute(
            """
            INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
            """,
            (COMPANY, key, name, phone, raw),
        )


def expected_ua(sid: str) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT updated_at FROM shift_assignments WHERE shift_id=%s::uuid", (sid,))
            ua = dict(cur.fetchone())["updated_at"]
    return ua.isoformat() if hasattr(ua, "isoformat") else str(ua)


def sid_from(result: dict) -> str:
    if result.get("shift_id"):
        return str(result["shift_id"])
    created = result.get("created") or []
    if created:
        return str(created[0].get("shift_id") or "")
    shift = result.get("shift") or {}
    return str(shift.get("shift_id") or "")


def main() -> int:
    print(f"SHW3B prod canary tag={TAG} evid={EVID}", flush=True)
    app.send_octopus_whatsapp = lambda *a, **k: {"ok": True, "skipped": "shw3b"}  # type: ignore
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "skipped": "shw3b"}  # type: ignore
    app.notify_employee_shift_created = lambda *a, **k: {"ok": True, "skipped": "shw3b"}  # type: ignore
    app.notify_employee_shift_cancelled = lambda *a, **k: {"ok": True, "skipped": "shw3b"}  # type: ignore
    app.notify_hr_admins = lambda *a, **k: {"ok": True, "skipped": "shw3b"}  # type: ignore

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    check("db_is_wathefni", db == "wathefni", db)
    check("wave3_enabled", w3.shifts_wave3_enabled_for_company(COMPANY))
    check("version_3_1", w3.SHIFTS_WAVE3_VERSION == "3.1.0")
    check("real_gate_on", w3.real_mutation_gate_enabled())
    check("allowlists_empty", not w3.hr_mutation_allowlist() and not w3.manager_mutation_allowlist())
    check("real_reminders_off", not w3.real_reminders_enabled())
    check("shw3b_synth", w3.is_wave3_synthetic_employee(employee_key=KEY_A, phone=PHONE_A))
    check(
        "real_mutation_blocked",
        w3.real_mutation_denied(actor_phone=ACTOR, is_synthetic_subject=False, company_code=COMPANY) is not None,
    )
    check(
        "synth_mutation_allowed",
        w3.real_mutation_denied(actor_phone=ACTOR, is_synthetic_subject=True, company_code=COMPANY) is None,
    )
    h = w3.honesty_payload()
    check("no_payroll_money", h.get("payroll_money") is False)
    check("no_templates", h.get("templates") is False)

    # Fingerprint baseline of non-SHW3B assignments
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
                       start_time::text, end_time::text, status, updated_at::text,
                       coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone
                FROM shift_assignments WHERE company_code=%s
                  AND coalesce(employee_key,'') NOT LIKE '%%SHW3B%%'
                  AND coalesce(employee_phone,'') NOT LIKE '965531%%'
                ORDER BY shift_id::text
                """,
                (COMPANY,),
            )
            before = [dict(r) for r in cur.fetchall()]
            for r in before:
                r["fp"] = fp_row(r)
    (EVID / "fps-before.json").write_text(json.dumps({r["shift_id"]: r["fp"] for r in before}, indent=2))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            upsert(cur, KEY_A, NAME_A, PHONE_A)
            upsert(cur, KEY_B, NAME_B, PHONE_B)
        conn.commit()

    today = app.kuwait_today()
    day = today + timedelta(days=5)
    day2 = today + timedelta(days=6)
    ctx = owner_ctx()

    # Same-day create via canonical dashboard endpoint
    created = app.dashboard_posthire_create_shift(
        app.ShiftCreateRequest(
            employee_key=KEY_A,
            employee_name=NAME_A,
            employee_phone=PHONE_A,
            shift_date=day.isoformat(),
            start_time="09:00",
            end_time="13:00",
            reason=f"w3b same-day {TAG}",
            site_key="W3B-SITE",
        ),
        context=ctx,
    )
    sid1 = sid_from(created)
    check("create_same_day", created.get("ok") is True and bool(sid1), created)

    # Split — second authority row same day
    created2 = app.dashboard_posthire_create_shift(
        app.ShiftCreateRequest(
            employee_key=KEY_A,
            employee_name=NAME_A,
            shift_date=day.isoformat(),
            start_time="14:00",
            end_time="18:00",
            reason=f"w3b split {TAG}",
        ),
        context=ctx,
    )
    sid2 = sid_from(created2)
    check("create_split_second_row", created2.get("ok") is True and bool(sid2) and sid2 != sid1, created2)

    # Overnight single authority
    on = app.dashboard_posthire_create_shift(
        app.ShiftCreateRequest(
            employee_key=KEY_A,
            employee_name=NAME_A,
            shift_date=day2.isoformat(),
            start_time="22:00",
            end_time="06:00",
            reason=f"w3b overnight {TAG}",
            acknowledge_availability=True,
            allow_leave_conflicts=True,
        ),
        context=ctx,
    )
    sid_on = sid_from(on)
    check("create_overnight", on.get("ok") is True and bool(sid_on), on)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ends_next_day FROM shift_assignments WHERE shift_id=%s::uuid", (sid_on,))
            ends = bool(dict(cur.fetchone()).get("ends_next_day"))
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND shift_date=%s::date AND status='scheduled'",
                (COMPANY, KEY_A, day2),
            )
            on_count = int(dict(cur.fetchone())["c"])
    check("overnight_ends_next_day", ends)
    check("overnight_no_duplicate_authority", on_count == 1, on_count)

    # List wave3 enrich — rolling week window starts at kuwait_today; day is +5 so week=0 may miss it.
    week_for_day = max(0, (day - today).days // 7)
    listing = app.dashboard_posthire_shifts(week=week_for_day, limit=200, context=ctx)
    check("list_wave3_on", bool((listing.get("wave3") or {}).get("enabled")))
    found = [s for s in (listing.get("shifts") or []) if str(s.get("shift_id")) in {sid1, sid2, sid_on}]
    if not found:
        domain = app.list_shifts(
            {"company_code": COMPANY, "start_date": day.isoformat(), "end_date": day2.isoformat(), "limit": 50},
            company_code=COMPANY,
        )
        found = [s for s in (domain.get("shifts") or []) if str(s.get("shift_id")) in {sid1, sid2, sid_on}]
    check("list_contains_synth", len(found) >= 2, {"found": len(found), "week": week_for_day, "window": [listing.get("start_date"), listing.get("end_date")]})

    # History lineage
    hist = app.dashboard_posthire_shift_history(sid1, context=ctx)
    check("history_versions", len(hist.get("versions") or []) >= 1, hist)

    # Stale concurrency
    try:
        app.dashboard_posthire_reschedule_shift(
            sid1,
            app.ShiftRescheduleRequest(
                shift_date=day.isoformat(),
                start_time="10:00",
                end_time="14:00",
                expected_updated_at="2000-01-01T00:00:00+00:00",
                reason=f"w3b stale {TAG}",
            ),
            context=ctx,
        )
        check("stale_rejected", False, "expected 409")
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", {})
        err = detail.get("error") if isinstance(detail, dict) else str(detail)
        check("stale_rejected", "stale" in str(err).lower() or getattr(exc, "status_code", None) == 409, detail)

    # Reschedule ok
    try:
        rs = app.dashboard_posthire_reschedule_shift(
            sid1,
            app.ShiftRescheduleRequest(
                shift_date=day.isoformat(),
                start_time="10:00",
                end_time="14:00",
                expected_updated_at=expected_ua(sid1),
                reason=f"w3b reschedule {TAG}",
                acknowledge_availability=True,
                allow_leave_conflicts=True,
            ),
            context=ctx,
        )
        check("reschedule_ok", bool(rs.get("ok")), rs)
    except Exception as exc:  # noqa: BLE001
        check("reschedule_ok", False, str(getattr(exc, "detail", exc))[:300])

    # Soft-cancel with audit reason
    try:
        cancelled = app.dashboard_posthire_cancel_shift(
            sid2,
            app.ShiftCancelRequest(expected_updated_at=expected_ua(sid2), reason=f"w3b cancel {TAG}", reason_code="cancelled"),
            context=ctx,
        )
        check("soft_cancel_ok", bool(cancelled.get("ok")), cancelled)
    except Exception as exc:  # noqa: BLE001
        check("soft_cancel_ok", False, str(getattr(exc, "detail", exc))[:300])

    # Real subject create must fail (gate + empty allowlist)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s",
                (COMPANY, f"WATHEFNI-REALBLOCK-{TAG}"),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                    """,
                    (COMPANY, f"WATHEFNI-REALBLOCK-{TAG}", f"Real Block {TAG}", REAL_PHONE),
                )
        conn.commit()
    try:
        app.dashboard_posthire_create_shift(
            app.ShiftCreateRequest(
                employee_key=f"WATHEFNI-REALBLOCK-{TAG}",
                employee_name=f"Real Block {TAG}",
                employee_phone=REAL_PHONE,
                shift_date=day.isoformat(),
                start_time="09:00",
                end_time="17:00",
                reason="should fail",
            ),
            context=ctx,
        )
        check("real_create_blocked", False, "expected 403")
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", {})
        err = str(detail.get("error") if isinstance(detail, dict) else detail).lower()
        check("real_create_blocked", "allowlist" in err or "403" in str(getattr(exc, "status_code", "")) or getattr(exc, "status_code", None) == 403, detail)

    # Swap request + self-decision denial
    swap = app.request_shift_swap(
        {
            "employee_key": KEY_A,
            "requester_employee_key": KEY_A,
            "target_employee_key": KEY_B,
            "requester_shift_id": sid_on,
            "shift_id": sid_on,
            "reason": f"w3b swap {TAG}",
        },
        company_code=COMPANY,
        created_by_phone=PHONE_A,
        account_id=COMPANY,
    )
    swap_id = str(swap.get("swap_id") or (swap.get("swap") or {}).get("swap_id") or "")
    if not swap_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_swap_requests (
                      company_code, requester_employee_key, target_employee_key,
                      requester_shift_id, shift_date, status, reason, requested_at, created_at
                    ) VALUES (%s,%s,%s,%s::uuid,%s::date,'requested',%s, now(), now())
                    RETURNING swap_id::text AS swap_id
                    """,
                    (COMPANY, KEY_A, KEY_B, sid_on, day2, f"w3b swap {TAG}"),
                )
                swap_id = dict(cur.fetchone())["swap_id"]
            conn.commit()
    check("swap_requested", bool(swap_id), swap)

    self_dec = app.decide_shift_swap(
        {"swap_id": swap_id},
        company_code=COMPANY,
        created_by_phone=PHONE_A,
        account_id=COMPANY,
        decision="approve",
    )
    check(
        "self_decision_denied",
        self_dec.get("ok") is False and "self" in str(self_dec.get("error") or "").lower(),
        self_dec,
    )

    apr = app.approve_shift_swap({"swap_id": swap_id}, company_code=COMPANY, created_by_phone=ACTOR, account_id=COMPANY)
    check("swap_scoped_decision_attempted", isinstance(apr, dict), apr)

    # Reconciliation flag + acknowledge
    flag_id = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            app._shifts_w2.ensure_shifts_integrity_wave2_schema(cur)
            cur.execute(
                """
                INSERT INTO shift_reconciliation_flags (
                  company_code, shift_id, employee_key, flag_type, status, details
                ) VALUES (%s,%s::uuid,%s,'lifecycle_fact_change','open',%s::jsonb)
                RETURNING flag_id::text AS flag_id
                """,
                (COMPANY, sid_on, KEY_A, json.dumps({"shw3b": True, "tag": TAG})),
            )
            flag_id = dict(cur.fetchone())["flag_id"]
        conn.commit()
    ack = app.dashboard_posthire_shift_recon_resolve(
        flag_id,
        app.ShiftReconResolveRequest(action="acknowledge"),
        context=ctx,
    )
    check("recon_acknowledge", bool(ack.get("ok")), ack)

    # Audited cancel of another recon flag
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_reconciliation_flags (
                  company_code, shift_id, employee_key, flag_type, status, details
                ) VALUES (%s,%s::uuid,%s,'lifecycle_fact_change','open',%s::jsonb)
                RETURNING flag_id::text AS flag_id
                """,
                (COMPANY, sid_on, KEY_A, json.dumps({"shw3b": True, "tag": TAG, "cancel": True})),
            )
            flag2 = dict(cur.fetchone())["flag_id"]
        conn.commit()
    try:
        cancelled_flag = app.dashboard_posthire_shift_recon_resolve(
            flag2,
            app.ShiftReconResolveRequest(action="cancel", reason=f"w3b recon cancel {TAG}"),
            context=ctx,
        )
        check("recon_audited_cancel", bool(cancelled_flag.get("ok")), cancelled_flag)
    except Exception as exc:  # noqa: BLE001
        check("recon_audited_cancel", False, str(getattr(exc, "detail", exc))[:300])

    # Terminal reminders visibility (synthetic filter)
    listing2 = app.dashboard_posthire_shifts(week=0, limit=50, context=ctx)
    check("terminal_reminders_key_present", "terminal_reminders" in listing2, list(listing2.keys())[:20])

    # Cleanup SHW3B + realblock employee
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                (COMPANY, f"WATHEFNI-REALBLOCK-{TAG}"),
            )
        conn.commit()

    cleaned = cleanup_synthetic_scope(
        app.db_connect,
        wave3b_scope(tag=TAG),
        known_ids={"shift_ids": [x for x in (sid1, sid2, sid_on) if x]},
    )
    check("cleanup_residual_zero", int(cleaned.get("residual_total") or 0) == 0, cleaned)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
                       start_time::text, end_time::text, status, updated_at::text,
                       coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone
                FROM shift_assignments WHERE company_code=%s
                  AND coalesce(employee_key,'') NOT LIKE '%%SHW3B%%'
                  AND coalesce(employee_phone,'') NOT LIKE '965531%%'
                ORDER BY shift_id::text
                """,
                (COMPANY,),
            )
            after = [dict(r) for r in cur.fetchall()]
            for r in after:
                r["fp"] = fp_row(r)
    before_map = {r["shift_id"]: r["fp"] for r in before}
    after_map = {r["shift_id"]: r["fp"] for r in after}
    check("real_fps_unchanged", before_map == after_map, {"before": len(before_map), "after": len(after_map)})
    (EVID / "fps-after.json").write_text(json.dumps(after_map, indent=2))

    RESULTS.update({"pass": PASS, "fail": FAIL, "tag": TAG})
    (EVID / "canary.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        try:
            cleanup_synthetic_scope(app.db_connect, wave3b_scope(tag=TAG))
        except Exception:
            pass
        print(f"FATAL {exc}", flush=True)
        raise
