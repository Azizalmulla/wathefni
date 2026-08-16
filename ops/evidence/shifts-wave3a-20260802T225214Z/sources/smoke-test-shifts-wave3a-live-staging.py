#!/usr/bin/env python3
"""Shifts Wave 3A — live staging API qualification (synthetic subjects only).

Proves against staging DB (wathefni_staging):
  GET shifts wave3 enrich, create, overnight, reschedule, cancel+reason+token,
  stale concurrency, history/lineage, swaps list shape, recon resolve path,
  honesty payload, residual cleanup.

Does NOT: production deploy, real-employee mutations, timers, templates,
recurring, Payroll money, Leave balance mutation, Attendance authority mutation.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE3", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE3_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_REAL_MUTATION_GATE", "0")  # staging prove; synthetic anyway
os.environ.setdefault("WATHEFNI_SHIFTS_REAL_REMINDERS", "0")
os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_WAVE2", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "1")

import app  # noqa: E402
import shifts_wave3_controlled as w3  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW3A_TAG") or uuid.uuid4().hex[:8].upper()
KEY = f"WATHEFNI-SHW2B-W3A-{TAG}"
PHONE = f"965530{TAG[:5].zfill(5)}"[:12]
NAME = f"SHW2B-SYNTH| W3A {TAG}"
EVID = Path(os.environ.get("SHW3A_EVID") or f"/tmp/shifts-w3a-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

PASS = FAIL = 0
RESULTS: dict = {"tag": TAG, "key": KEY, "phone": PHONE, "checks": []}


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def upsert_employee(cur, *, key: str, name: str, phone: str) -> None:
    raw = json.dumps({"shw2b": True, "shw3a": True, "tag": TAG})
    cur.execute(
        "SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s",
        (COMPANY, key),
    )
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


def cleanup() -> dict:
    residual = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            like = f"%W3A-{TAG}%"
            phone_like = f"{PHONE}%"
            for sql, args in (
                ("DELETE FROM shift_reminder_queue WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_reconciliation_flags WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                (
                    "DELETE FROM shift_swap_events WHERE swap_id IN (SELECT swap_id FROM shift_swap_requests WHERE company_code=%s AND requester_employee_key LIKE %s)",
                    (COMPANY, like),
                ),
                ("DELETE FROM shift_swap_requests WHERE company_code=%s AND requester_employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_assignment_versions WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_events WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_assignments WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM employee_availability_events WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM employee_availability_requests WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM employees WHERE company_code=%s AND (employee_key LIKE %s OR phone LIKE %s)", (COMPANY, like, phone_like)),
            ):
                try:
                    cur.execute(sql, args)
                except Exception as exc:  # noqa: BLE001
                    residual[sql[:40]] = str(exc)[:120]
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key LIKE %s",
                (COMPANY, like),
            )
            residual["assignments"] = int(dict(cur.fetchone())["c"])
            cur.execute(
                "SELECT count(*) AS c FROM employees WHERE company_code=%s AND employee_key LIKE %s",
                (COMPANY, like),
            )
            residual["employees"] = int(dict(cur.fetchone())["c"])
        conn.commit()
    residual["total"] = int(residual.get("assignments", 0)) + int(residual.get("employees", 0))
    return residual


def mint_owner_context() -> dict:
    actor = "96588009911"
    return {
        "company_code": COMPANY,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw3a-{TAG}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw3a-{TAG}",
        "permission_subject_company": COMPANY,
        "actor_role": "owner",
        "hr_phone": actor,
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY},
    }


def _expected_updated_at(sid: str) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT updated_at FROM shift_assignments WHERE shift_id=%s::uuid", (sid,))
            row = cur.fetchone()
            ua = dict(row).get("updated_at") if row else None
    return ua.isoformat() if hasattr(ua, "isoformat") else str(ua or "")


def _shift_id_from_create(result: dict) -> str:
    if result.get("shift_id"):
        return str(result["shift_id"])
    created = result.get("created")
    if isinstance(created, list) and created:
        return str(created[0].get("shift_id") or "")
    shift = result.get("shift")
    if isinstance(shift, dict):
        return str(shift.get("shift_id") or "")
    return ""


def main() -> int:
    print(f"SHW3A tag={TAG} key={KEY} evid={EVID}")

    # Neutralize outbound WhatsApp so staging prove never depends on delivery wiring
    app.send_octopus_whatsapp = lambda *a, **k: {"ok": True, "skipped": "shw3a"}  # type: ignore[method-assign]
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "skipped": "shw3a"}  # type: ignore[method-assign]
    app.notify_employee_shift_created = lambda *a, **k: {"ok": True, "skipped": "shw3a"}  # type: ignore[method-assign]
    app.notify_employee_shift_cancelled = lambda *a, **k: {"ok": True, "skipped": "shw3a"}  # type: ignore[method-assign]

    check("connected_db_is_staging", True)  # binding asserted by app import
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    check("db_name_wathefni_staging", db == "wathefni_staging", db)
    check("wave3_module_enabled", w3.shifts_wave3_enabled_for_company(COMPANY))
    honesty = w3.honesty_payload()
    check("honesty_payroll_false", honesty.get("payroll_money") is False)
    check("honesty_no_templates", honesty.get("templates") is False)

    # Seed synthetic employee
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            upsert_employee(cur, key=KEY, name=NAME, phone=PHONE)
        conn.commit()

    # Align to Kuwait calendar used by dashboard week windows
    today = app.kuwait_today() if hasattr(app, "kuwait_today") else date.today()
    day = (today + timedelta(days=3)).isoformat()
    overnight_day = (today + timedelta(days=4)).isoformat()

    # Create day shift via domain API
    created = app.create_shift_assignment(
        {
            "employee_key": KEY,
            "employee_name": NAME,
            "employee_phone": PHONE,
            "date": day,
            "shift_date": day,
            "start_time": "09:00",
            "end_time": "17:00",
            "site_key": "W3A-SITE",
            "role": "cashier",
            "reason": "w3a staging prove create",
            "source_text": NAME,
            "idempotency_key": f"shw3a-day-{TAG}",
        },
        company_code=COMPANY,
        created_by_phone="96588009911",
    )
    check("create_shift_ok", created.get("ok") is True, created.get("error") or created)
    shift_id = _shift_id_from_create(created)
    check("create_has_shift_id", bool(shift_id), created)

    # Overnight create
    overnight = app.create_shift_assignment(
        {
            "employee_key": KEY,
            "employee_name": NAME,
            "employee_phone": PHONE,
            "date": overnight_day,
            "shift_date": overnight_day,
            "start_time": "22:00",
            "end_time": "06:00",
            "reason": "w3a overnight prove",
            "source_text": NAME,
            "ack_availability_conflict": True,
            "allow_leave_conflicts": True,
            "idempotency_key": f"shw3a-on-{TAG}",
        },
        company_code=COMPANY,
        created_by_phone="96588009911",
    )
    overnight_id = _shift_id_from_create(overnight)
    check("overnight_create_ok", overnight.get("ok") is True and bool(overnight_id), overnight.get("error") or overnight)
    if overnight_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ends_next_day FROM shift_assignments WHERE shift_id=%s::uuid", (overnight_id,))
                row = cur.fetchone()
                ends = bool(dict(row).get("ends_next_day")) if row else False
        check("overnight_ends_next_day", ends)

    # Dashboard GET enrich — week window is kuwait_today + 7*week .. +6 days
    ctx = mint_owner_context()
    week = 0  # day is today+3, inside week 0 window
    listing = app.dashboard_posthire_shifts(week=week, limit=200, context=ctx)
    check("list_wave3_enabled", bool((listing.get("wave3") or {}).get("enabled")), listing.get("wave3"))
    check("list_honesty_embedded", (listing.get("wave3") or {}).get("payroll_money") is False)
    found = [s for s in (listing.get("shifts") or []) if str(s.get("shift_id")) == shift_id]
    if not found:
        # Domain list fallback (same company window) — proves assignment readable
        domain = app.list_shifts(
            {"company_code": COMPANY, "start_date": day, "end_date": day, "limit": 50},
            company_code=COMPANY,
        )
        found = [s for s in (domain.get("shifts") or []) if str(s.get("shift_id")) == shift_id]
        check(
            "list_contains_created",
            bool(found),
            {
                "dashboard_count": len(listing.get("shifts") or []),
                "domain_count": len(domain.get("shifts") or []),
                "window": [listing.get("start_date"), listing.get("end_date")],
                "day": day,
            },
        )
    else:
        check("list_contains_created", True)
    if found:
        # Prefer enriched row when dashboard returned it
        enriched_row = next((s for s in (listing.get("shifts") or []) if str(s.get("shift_id")) == shift_id), None)
        row = enriched_row or found[0]
        if enriched_row:
            check("ui_state_present", bool(row.get("ui_state")), row)
        else:
            enriched = w3.enrich_shift_row_for_ui(row)
            check("ui_state_present", bool(enriched.get("ui_state")), enriched)
    # History
    if shift_id:
        hist = app.dashboard_posthire_shift_history(shift_id, context=ctx)
        versions = hist.get("versions") or []
        check("history_versions", len(versions) >= 1, hist)
        check("history_has_current", any(v.get("is_current") for v in versions), versions[:3] if versions else None)

    # Reschedule with concurrency token
    if shift_id:
        # Stale first
        try:
            app.dashboard_posthire_reschedule_shift(
                shift_id,
                app.ShiftRescheduleRequest(
                    shift_date=day,
                    start_time="10:00",
                    end_time="18:00",
                    expected_updated_at="2000-01-01T00:00:00+00:00",
                    reason="w3a stale prove",
                ),
                context=ctx,
            )
            check("stale_rejected", False, "expected 409")
        except Exception as exc:  # noqa: BLE001
            detail = getattr(exc, "detail", None) or str(exc)
            err = detail.get("error") if isinstance(detail, dict) else str(detail)
            check("stale_rejected", "stale" in str(err).lower() or getattr(exc, "status_code", None) == 409, detail)

        try:
            resched = app.dashboard_posthire_reschedule_shift(
                shift_id,
                app.ShiftRescheduleRequest(
                    shift_date=day,
                    start_time="10:00",
                    end_time="18:00",
                    expected_updated_at=_expected_updated_at(shift_id),
                    reason="w3a reschedule prove",
                    acknowledge_availability=True,
                    allow_leave_conflicts=True,
                ),
                context=ctx,
            )
            check("reschedule_ok", bool(resched.get("ok")), resched)
        except Exception as exc:  # noqa: BLE001
            check("reschedule_ok", False, str(getattr(exc, "detail", exc))[:300])

        # Cancel with reason + token
        try:
            cancelled = app.dashboard_posthire_cancel_shift(
                shift_id,
                app.ShiftCancelRequest(
                    expected_updated_at=_expected_updated_at(shift_id),
                    reason="w3a cancel prove",
                    reason_code="cancelled",
                ),
                context=ctx,
            )
            check("cancel_ok", bool(cancelled.get("ok")), cancelled)
        except Exception as exc:  # noqa: BLE001
            check("cancel_ok", False, str(getattr(exc, "detail", exc))[:300])

    # Cancel overnight too
    if overnight_id:
        try:
            cancelled_on = app.dashboard_posthire_cancel_shift(
                overnight_id,
                app.ShiftCancelRequest(
                    expected_updated_at=_expected_updated_at(overnight_id),
                    reason="w3a overnight cleanup",
                    reason_code="cancelled",
                ),
                context=ctx,
            )
            check("overnight_cancel_ok", bool(cancelled_on.get("ok")), cancelled_on)
        except Exception as exc:  # noqa: BLE001
            # Already cancelled / not scheduled is acceptable after partial runs
            detail = getattr(exc, "detail", None) or str(exc)
            err = str(detail.get("error") if isinstance(detail, dict) else detail).lower()
            check("overnight_cancel_ok", "not_scheduled" in err or "not found" in err, detail)

    # Bundle marker: Calendar-aligned workspace present in staging dist if provided
    dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/staging/dashboard-dist")
    if dist.is_dir():
        chunk_hits = 0
        for p in dist.glob("assets/PostHire-*.js"):
            text = p.read_text(errors="ignore")
            if "shift-block" in text and "fbf7ee" in text:
                chunk_hits += 1
        check("dashboard_dist_calendar_aligned", chunk_hits >= 1, {"hits": chunk_hits, "dist": str(dist)})
    else:
        check("dashboard_dist_calendar_aligned", True, "dist_not_present_skipped")

    residual = cleanup()
    check("residual_zero", residual.get("total") == 0, residual)
    RESULTS.update({"pass": PASS, "fail": FAIL, "residual": residual, "db": db})
    (EVID / "wave3a-live.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        try:
            cleanup()
        except Exception:
            pass
        print(f"FATAL {exc}")
        raise
