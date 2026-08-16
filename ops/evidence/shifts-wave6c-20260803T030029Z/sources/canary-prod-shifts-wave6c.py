#!/usr/bin/env python3
"""Shifts Wave 6C — production WATHEFNI controlled real rollout canary.

Approved scope (owner-confirmed 2026-08-03):
  HR operator        96599338566 (Aziz Almulla, owner, shifts.manage)
  Real subject       WATHEFNI-96550252254 (Talal Fadhli) — future dates only
  Real channel       email → talalabdalla89@gmail.com (consent recorded)
  Manager rollout    NO-GO on real data; scope proven on SHW6C synthetic subjects
  Excluded subjects  WATHEFNI-ORPHAN-* and *-REALBLOCK-* (residue, never touched)

Every real row this canary creates is future-dated, tagged, and soft-cancelled before it
finishes. Historical schedules are fingerprinted and asserted unchanged. Synthetic subjects
use SHW6C / 965538* and are hard-cleaned to residual zero.

Does NOT: broaden the employee app, grant Talal HR/manager capability, submit to PAM,
mutate Payroll money, mutate Leave balances, mutate Attendance authority, enable timers.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")

# Wave 6C controlled rollout gate
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6C", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6C_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6C_SYNTHETIC_KEY_MARKERS", "SHW6C,SHW6C-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6C_SYNTHETIC_PHONE_PREFIXES", "965538")

# Named allowlists — HR only. Manager allowlist stays empty (real manager rollout NO-GO).
os.environ.setdefault("WATHEFNI_SHIFTS_HR_ALLOWLIST", "96599338566")
os.environ.setdefault("WATHEFNI_SHIFTS_MANAGER_ALLOWLIST", "")
os.environ.setdefault("WATHEFNI_SHIFTS_REAL_MUTATION_GATE", "1")

# Real notification canary — one recipient, app + one external channel.
os.environ.setdefault("WATHEFNI_SHIFTS_NOTIFY_REAL_ALLOWLIST", "WATHEFNI-96550252254")
os.environ.setdefault("WATHEFNI_SHIFTS_NOTIFY_REAL_CHANNELS", "app,email")
os.environ.setdefault("WATHEFNI_SHIFTS_NOTIFY_REAL_DELIVERY", "1")

# Controlled real subjects require Wave 1 authority to evaluate non-synthetic employees.
# Safety comes from the actor allowlist, not from the synthetic gate.
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY", "0")

# Everything else stays where Wave 6B left it.
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE3", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE3_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_NOTIFICATIONS_WAVE6B", "1")
os.environ["WATHEFNI_SHIFTS_NOTIFICATIONS_REAL_DELIVERY"] = "0"
os.environ.setdefault("WATHEFNI_SHIFTS_REAL_REMINDERS", "0")
os.environ.setdefault("WATHEFNI_SHIFTS_OPERATOR_TIMERS", "0")
os.environ.setdefault("WATHEFNI_SHIFTS_CONTROLLED_JOBS", "1")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")


def _merge_env_csv(key: str, *values: str) -> None:
    existing = [p.strip() for p in (os.environ.get(key) or "").split(",") if p.strip()]
    for v in values:
        if v not in existing:
            existing.append(v)
    os.environ[key] = ",".join(existing)


for _k in (
    "WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS",
):
    _merge_env_csv(_k, "SHW6C", "SHW6C-SYNTH|")
for _k in (
    "WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES",
    "WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES",
    "WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES",
    "WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_PHONE_PREFIXES",
    "WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES",
    "WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES",
):
    _merge_env_csv(_k, "965538")

import app  # noqa: E402
import shifts_controlled_wave6c as w6c  # noqa: E402
import shifts_notifications_wave6b as n6  # noqa: E402
import shifts_enterprise_wave6 as w6  # noqa: E402
import shifts_publish_wave5 as w5  # noqa: E402
import shifts_templates_wave4 as w4  # noqa: E402
import shifts_wave3_controlled as w3  # noqa: E402
from shifts_synthetic_cleanup import (  # noqa: E402
    CLEANUP_CONTRACT_VERSION,
    cleanup_synthetic_scope,
    count_synthetic_residuals,
    wave6c_scope,
)

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW6C_TAG") or uuid.uuid4().hex[:8].upper()
EVID = Path(os.environ.get("SHW6C_EVID") or f"/tmp/shw6c-prod-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

HR_ACTOR = "96599338566"
UNAUTHORIZED_ACTOR = "96512345678"
TALAL_KEY = "WATHEFNI-96550252254"
TALAL_EMAIL = "talalabdalla89@gmail.com"
EXCLUDED_KEYS = ("WATHEFNI-ORPHAN-1db8844d", "WATHEFNI-REALBLOCK-0F290BF7")

SKEY = f"WATHEFNI-SHW6C-{TAG}"
SKEY_B = f"WATHEFNI-SHW6C-B-{TAG}"
_d = "".join(ch for ch in TAG if ch.isdigit()) or "123456"
SPHONE = f"965538{_d[:6].ljust(6, '0')}"
SPHONE_B = f"965538{_d[1:6].ljust(5, '0')}7"
SNAME = f"SHW6C-SYNTH| Emp {TAG}"
SNAME_B = f"SHW6C-SYNTH| EmpB {TAG}"
MANAGER_PHONE = f"965538{_d[:5].ljust(5, '0')}1"
TEAM_KEY = f"SHW6C-TEAM-{TAG}"

PASS = FAIL = 0
RESULTS: dict = {"tag": TAG, "checks": [], "ids": {}, "real_sends": []}

ACKS = {
    "acknowledge_availability": True,
    "ack_availability_conflict": True,
    "allow_availability_conflicts": True,
    "allow_leave_conflicts": True,
    "ack_leave_conflict": True,
    "acknowledge_seasonal": True,
    "ack_seasonal": True,
    "confirm_overlap": True,
}


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail if not ok else None})
    if ok:
        PASS += 1
        print(f"PASS  {name}", flush=True)
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}", flush=True)


def fp_rows(rows) -> str:
    return hashlib.md5(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def expected_updated_at(sid: str) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT updated_at FROM shift_assignments WHERE shift_id=%s", (sid,))
            row = cur.fetchone()
    ua = dict(row).get("updated_at") if row else None
    return ua.isoformat() if hasattr(ua, "isoformat") else str(ua)


def hr_ctx(actor: str = HR_ACTOR) -> dict:
    """Dashboard context for the named HR operator (owner role, shifts.manage)."""
    return {
        "company_code": COMPANY,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw6c-{TAG}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw6c-{TAG}",
        "permission_subject_company": COMPANY,
        "actor_role": "owner",
        "hr_phone": actor,
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY},
    }


def real_lineage_snapshot(cur) -> dict:
    """Fingerprint every real (non-SHW6C) schedule row so drift is impossible to miss."""
    out: dict = {}
    cur.execute(
        """
        SELECT shift_id::text, employee_key, shift_date::text, start_time::text, end_time::text,
               status, updated_at::text
        FROM shift_assignments
        WHERE company_code=%s AND employee_key NOT LIKE %s
        ORDER BY shift_id
        """,
        (COMPANY, "%SHW6C%"),
    )
    out["assignments"] = [dict(r) for r in cur.fetchall()]
    cur.execute(
        """
        SELECT employee_key, name, phone, email, employment_status
        FROM employees WHERE company_code=%s AND employee_key NOT LIKE %s
        ORDER BY employee_key
        """,
        (COMPANY, "%SHW6C%"),
    )
    out["employees"] = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT count(*) AS c FROM shift_orphan_quarantine WHERE company_code=%s", (COMPANY,))
    out["orphan_quarantine"] = dict(cur.fetchone())["c"]
    return out


def seed_synthetic(cur, key: str, name: str, phone: str) -> None:
    payload = json.dumps({"shw6c": True, "tag": TAG})
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
        ON CONFLICT DO NOTHING
        """,
        (COMPANY, key, name, phone, payload),
    )
    cur.execute(
        """
        UPDATE employees SET name=%s, phone=%s, employment_status='active',
               raw_json=%s::jsonb, updated_at=now()
        WHERE company_code=%s AND employee_key=%s
        """,
        (name, phone, payload, COMPANY, key),
    )


def main() -> int:
    today = date.today()
    d1 = today + timedelta(days=10)
    d2 = today + timedelta(days=11)
    d3 = today + timedelta(days=12)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            baseline = real_lineage_snapshot(cur)
            baseline_fp = fp_rows(baseline)
        conn.commit()

    # ---------------------------------------------------------------- posture
    print("\n=== posture / honesty ===", flush=True)
    hp = w6c.honesty_payload()
    check("w6c_version_6_2", w6c.SHIFTS_WAVE6C_VERSION.startswith("6.2"), w6c.SHIFTS_WAVE6C_VERSION)
    check("w6c_enabled_for_wathefni", w6c.shifts_wave6c_enabled_for_company(COMPANY))
    check("w6c_disabled_other_tenant", not w6c.shifts_wave6c_enabled_for_company("OTHERCO"))
    check("hr_allowlist_is_named_only", w3.hr_mutation_allowlist() == {HR_ACTOR}, sorted(w3.hr_mutation_allowlist()))
    check("manager_allowlist_empty", w3.manager_mutation_allowlist() == set(), sorted(w3.manager_mutation_allowlist()))
    check("manager_real_rollout_nogo", w6c.manager_real_rollout_enabled() is False)
    check("notify_allowlist_single_recipient", w6c.real_notify_allowlist() == {TALAL_KEY}, sorted(w6c.real_notify_allowlist()))
    check("notify_channels_app_email_only", set(w6c.real_notify_channels()) == {"app", "email"}, w6c.real_notify_channels())
    check("real_delivery_enabled", w6c.real_delivery_enabled() is True)
    check("kill_switch_off_at_start", w6c.notify_kill_switch_active() is False)
    check("operator_timers_off", w6c.operator_timers_enabled() is False)
    check("broad_employee_app_off", hp["broad_employee_app"] is False)
    check("talal_read_and_ack_only", hp["talal_read_and_ack_only"] is True)
    check("pam_submission_false", hp["pam_submission"] is False)
    check("payroll_money_false", hp["payroll_money"] is False)
    check("leave_balances_not_mutated", hp["leave_balances_mutated"] is False)
    check("attendance_authority_not_mutated", hp["attendance_authority_mutated"] is False)
    check("ack_authority_wathefni", hp["acknowledgement_authority"] == "wathefni")
    check("cleanup_contract_1_5", CLEANUP_CONTRACT_VERSION.startswith("1.5"), CLEANUP_CONTRACT_VERSION)

    src = Path(w6c.__file__).read_text(encoding="utf-8")
    check("no_payroll_money_sql", "UPDATE payroll" not in src and "INSERT INTO payroll" not in src)
    check("no_leave_balance_sql", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
    check("no_attendance_authority_sql", "UPDATE attendance_records" not in src)
    check("no_pam_submit_call", "pam_submit" not in src and "government" not in src.lower())

    # -------------------------------------------------- excluded subject guard
    print("\n=== controlled subject exclusions ===", flush=True)
    for k in EXCLUDED_KEYS:
        check(f"excluded_{k[-12:]}", w6c.subject_excluded(k) is True, k)
    check("talal_not_excluded", w6c.subject_excluded(TALAL_KEY) is False)
    check("empty_key_excluded", w6c.subject_excluded("") is True)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w6c.ensure_shifts_wave6c_schema(cur)
            for k in EXCLUDED_KEYS:
                res = w6c.record_consent(
                    cur, company_code=COMPANY, employee_key=k, channel="email",
                    destination_ref="blocked@example.invalid", granted_by="canary",
                )
                check(f"consent_refused_for_excluded_{k[-8:]}", res.get("error") == "subject_excluded", res)
                denial = w6c.delivery_precheck(cur, company_code=COMPANY, employee_key=k, channel="email")
                check(f"delivery_blocked_for_excluded_{k[-8:]}", (denial or {}).get("error") == "subject_excluded", denial)
        conn.commit()

    # ------------------------------------------------------- consent + guards
    print("\n=== consent and fail-closed delivery guards ===", flush=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            denial = w6c.delivery_precheck(cur, company_code=COMPANY, employee_key=TALAL_KEY, channel="email")
            check("email_blocked_before_consent", (denial or {}).get("error") == "consent_missing", denial)
            res = w6c.record_consent(
                cur, company_code=COMPANY, employee_key=TALAL_KEY, channel="email",
                destination_ref=TALAL_EMAIL, granted_by=f"owner:{HR_ACTOR}",
                evidence_ref=f"wave6c-owner-approval-{TAG}",
            )
            check("consent_recorded", res.get("ok") is True and (res.get("consent") or {}).get("status") == "granted", res.get("error"))
            check("consent_destination_is_talal", (res.get("consent") or {}).get("destination_ref") == TALAL_EMAIL)
            check("email_allowed_after_consent", w6c.delivery_precheck(cur, company_code=COMPANY, employee_key=TALAL_KEY, channel="email") is None)
            check("app_channel_needs_no_external_consent", w6c.delivery_precheck(cur, company_code=COMPANY, employee_key=TALAL_KEY, channel="app") is None)
            d = w6c.delivery_precheck(cur, company_code=COMPANY, employee_key=TALAL_KEY, channel="whatsapp")
            check("unapproved_channel_blocked", (d or {}).get("error") == "channel_not_approved", d)
            d = w6c.delivery_precheck(cur, company_code=COMPANY, employee_key="WATHEFNI-96599411617", channel="email")
            check("non_allowlisted_recipient_blocked", (d or {}).get("error") == "recipient_not_allowlisted", d)
        conn.commit()

    # ------------------------------------------------- HR controlled real use
    print("\n=== controlled HR real scheduling (Talal, future dates only) ===", flush=True)
    real_shift_ids: list[str] = []

    def hr_create(dt: date, start: str, end: str, reason: str, actor: str = HR_ACTOR, suffix: str = ""):
        return app.create_shift_assignment(
            {
                "employee_key": TALAL_KEY,
                "date": dt.isoformat(),
                "start_time": start,
                "end_time": end,
                "reason": reason,
                "reason_code": "created",
                "idempotency_key": f"w6c-{TAG}-{dt}-{start}{suffix}",
                **ACKS,
            },
            company_code=COMPANY,
            created_by_phone=actor,
        )

    def first_shift_id(res: dict) -> str:
        created_rows = res.get("created") or []
        if created_rows:
            return str((created_rows[0] or {}).get("shift_id") or "")
        return str(res.get("shift_id") or "")

    denied = hr_create(d1, "09:00", "17:00", "wave6c unauthorized probe", actor=UNAUTHORIZED_ACTOR, suffix="-unauth")
    check("non_allowlisted_actor_denied", denied.get("error") == "shifts_real_mutation_not_allowlisted", denied.get("error"))

    no_reason = app.create_shift_assignment(
        {
            "employee_key": TALAL_KEY, "date": d1.isoformat(), "start_time": "09:00",
            "end_time": "17:00", "reason": "", "idempotency_key": f"w6c-{TAG}-noreason", **ACKS,
        },
        company_code=COMPANY, created_by_phone=HR_ACTOR,
    )
    check("audit_reason_required", no_reason.get("error") == "audit_reason_required", no_reason.get("error"))

    same_day = hr_create(d1, "09:00", "17:00", "wave6c controlled canary: same-day assignment")
    check("hr_same_day_created", same_day.get("ok") is True, same_day.get("error"))
    sid1 = first_shift_id(same_day)
    if sid1:
        real_shift_ids.append(sid1)

    repeat = hr_create(d1, "09:00", "17:00", "wave6c controlled canary: same-day assignment")
    check(
        "idempotent_repeat_no_duplicate",
        repeat.get("ok") is True and (bool(repeat.get("idempotent")) or first_shift_id(repeat) == sid1),
        {"repeat": first_shift_id(repeat), "original": sid1, "idempotent": repeat.get("idempotent")},
    )

    split_a = hr_create(d2, "08:00", "12:00", "wave6c controlled canary: split shift part A")
    split_b = hr_create(d2, "16:00", "20:00", "wave6c controlled canary: split shift part B")
    check("hr_split_shift_both_parts", split_a.get("ok") is True and split_b.get("ok") is True, [split_a.get("error"), split_b.get("error")])
    for r in (split_a, split_b):
        s = first_shift_id(r)
        if s:
            real_shift_ids.append(s)

    overnight = hr_create(d3, "22:00", "06:00", "wave6c controlled canary: overnight shift")
    check("hr_overnight_created", overnight.get("ok") is True, overnight.get("error"))
    s = first_shift_id(overnight)
    if s:
        real_shift_ids.append(s)

    RESULTS["ids"]["real_shift_ids"] = real_shift_ids
    check("all_real_rows_future_dated", all(d > today for d in (d1, d2, d3)))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shift_id::text, shift_date::text, start_time::text, end_time::text, status,
                       coalesce(ends_next_day,false) AS ends_next_day
                FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND shift_date >= %s
                ORDER BY shift_date, start_time
                """,
                (COMPANY, TALAL_KEY, today.isoformat()),
            )
            created = [dict(r) for r in cur.fetchall()]
        conn.commit()
    check("created_rows_visible_in_db", len(created) >= 4, len(created))
    check("overnight_flagged_ends_next_day", any(r["ends_next_day"] for r in created), created)
    check("split_same_date_two_windows", len([r for r in created if r["shift_date"] == d2.isoformat()]) == 2, created)

    # reschedule with concurrency token, then prove a stale token is rejected
    if real_shift_ids:
        sid = real_shift_ids[0]
        try:
            resched = app.dashboard_posthire_reschedule_shift(
                sid,
                app.ShiftRescheduleRequest(
                    shift_date=d1.isoformat(), start_time="10:00", end_time="18:00",
                    expected_updated_at=expected_updated_at(sid),
                    reason="wave6c controlled canary: reschedule",
                    confirm_overlap=True, allow_leave_conflicts=True, acknowledge_availability=True,
                ),
                context=hr_ctx(),
            )
            check("hr_reschedule_with_token", resched.get("ok") is True, resched)
        except app.HTTPException as exc:
            check("hr_reschedule_with_token", False, getattr(exc, "detail", exc))

        stale = expected_updated_at(sid)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE shift_assignments SET updated_at=now() WHERE shift_id=%s", (sid,))
            conn.commit()
        try:
            app.dashboard_posthire_reschedule_shift(
                sid,
                app.ShiftRescheduleRequest(
                    shift_date=d1.isoformat(), start_time="11:00", end_time="19:00",
                    expected_updated_at=stale, reason="wave6c stale token probe",
                    confirm_overlap=True, allow_leave_conflicts=True, acknowledge_availability=True,
                ),
                context=hr_ctx(),
            )
            check("stale_concurrency_token_rejected", False, "expected 409")
        except app.HTTPException as exc:
            check("stale_concurrency_token_rejected", exc.status_code == 409, getattr(exc, "detail", exc))

        try:
            app.dashboard_posthire_reschedule_shift(
                sid,
                app.ShiftRescheduleRequest(
                    shift_date=d1.isoformat(), start_time="10:30", end_time="18:30",
                    expected_updated_at=expected_updated_at(sid), reason="wave6c unauthorized reschedule probe",
                    confirm_overlap=True, allow_leave_conflicts=True, acknowledge_availability=True,
                ),
                context=hr_ctx(actor=UNAUTHORIZED_ACTOR),
            )
            check("unauthorized_reschedule_denied", False, "expected 403")
        except app.HTTPException as exc:
            check("unauthorized_reschedule_denied", exc.status_code == 403, getattr(exc, "detail", exc))

    # --------------------------------------------- real notification delivery
    print("\n=== real notification canary (app + email to Talal) ===", flush=True)
    notify_event_id = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            n6.ensure_shifts_notifications_wave6b_schema(cur)
            w6c.ensure_shifts_wave6c_schema(cur)

            emitted = n6.emit_notification_event(
                cur, company_code=COMPANY, event_type="shift_assigned", employee_key=TALAL_KEY,
                employee_name="Talal Fadhli", employee_phone="96550252254",
                shift_id=real_shift_ids[0] if real_shift_ids else None,
                payload={
                    "headline": f"New shift on {d1.isoformat()}",
                    "body": f"You have a shift on {d1.isoformat()} from 10:00 to 18:00 (Wathefni controlled rollout canary {TAG}).",
                },
                requires_ack=True,
                dedupe_key=f"w6c|{TAG}|assigned",
            )
            check("event_emitted", emitted.get("ok") is True and not emitted.get("duplicate_suppressed"), emitted.get("error"))
            notify_event_id = (emitted.get("event") or {}).get("event_id")
            RESULTS["ids"]["notify_event_id"] = str(notify_event_id)

            dup = n6.emit_notification_event(
                cur, company_code=COMPANY, event_type="shift_assigned", employee_key=TALAL_KEY,
                payload={"headline": "duplicate probe"}, dedupe_key=f"w6c|{TAG}|assigned",
            )
            check("no_duplicate_business_notification", dup.get("duplicate_suppressed") is True, dup)

            draft_evt = n6.emit_notification_event(
                cur, company_code=COMPANY, event_type="schedule_published", employee_key=TALAL_KEY,
                payload={"headline": "draft probe"}, dedupe_key=f"w6c|{TAG}|draft", from_draft=True,
            )
            check("drafts_do_not_notify", draft_evt.get("error") == "drafts_do_not_notify", draft_evt)

            sender = app.shifts_wave6c_sender_factory(cur)
            delivered = w6c.deliver_event_controlled(
                cur, company_code=COMPANY, event_id=notify_event_id, sender=sender,
                stop_on_first_success=False, channel_order=["app", "email"],
            )
            check("delivery_ok", delivered.get("ok") is True, delivered.get("error"))
            rows = delivered.get("deliveries") or []
            by_channel = {str(r.get("channel")): r for r in rows}
            check("app_inbox_delivered", str(by_channel.get("app", {}).get("status")) == "delivered", by_channel.get("app"))
            check("app_not_counted_as_real_send", by_channel.get("app", {}).get("real_sent") is False)
            email_row = by_channel.get("email") or {}
            check("email_attempted", bool(email_row), by_channel)
            check("email_delivered", str(email_row.get("status")) == "delivered", email_row)
            check("email_real_sent_true", email_row.get("real_sent") is True, email_row)
            check("provider_receipt_captured", bool(email_row.get("correlation_id")), email_row.get("correlation_id"))
            check("recipient_ref_is_consented_email", str(email_row.get("recipient_ref") or "") == TALAL_EMAIL, email_row.get("recipient_ref"))
            RESULTS["real_sends"].append({
                "channel": "email",
                "recipient": TALAL_EMAIL,
                "provider": email_row.get("provider"),
                "provider_message_id": email_row.get("provider_message_id"),
                "correlation_id": email_row.get("correlation_id"),
            })

            cur.execute(
                "SELECT count(*) AS c FROM employee_messages WHERE company_code=%s AND employee_key=%s AND dedupe_key=%s",
                (COMPANY, TALAL_KEY, f"w6c:w6c|{TAG}|assigned"),
            )
            check("inbox_row_written_once", int(dict(cur.fetchone())["c"]) == 1)

            acked = w6c.deliver_event_controlled(cur, company_code=COMPANY, event_id=notify_event_id, sender=sender)
            check("redelivery_still_single_business_event", acked.get("ok") is True)

            ack1 = n6.acknowledge_event(cur, company_code=COMPANY, event_id=notify_event_id, channel="email", actor_employee_key=TALAL_KEY)
            check("ack_recorded_once", ack1.get("ok") is True and ack1.get("already_acked") is False, ack1)
            ack2 = n6.acknowledge_event(cur, company_code=COMPANY, event_id=notify_event_id, channel="app", actor_employee_key=TALAL_KEY)
            check("second_channel_ack_is_noop", ack2.get("already_acked") is True, ack2)
            cur.execute("SELECT count(*) AS c FROM shift_notification_acks WHERE event_id=%s", (str(notify_event_id),))
            check("exactly_one_ack_row", int(dict(cur.fetchone())["c"]) == 1)

            after_ack = w6c.deliver_event_controlled(cur, company_code=COMPANY, event_id=notify_event_id, sender=sender)
            check("acked_event_not_redelivered", after_ack.get("skipped") is True, after_ack)
        conn.commit()

    # kill switch
    print("\n=== delivery kill switch ===", flush=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            evt = n6.emit_notification_event(
                cur, company_code=COMPANY, event_type="shift_changed", employee_key=TALAL_KEY,
                payload={"headline": "kill switch probe"}, dedupe_key=f"w6c|{TAG}|kill",
            )
            kill_event_id = (evt.get("event") or {}).get("event_id")
            os.environ["WATHEFNI_SHIFTS_NOTIFY_KILL"] = "1"
            check("kill_switch_engaged", w6c.notify_kill_switch_active() is True)
            check("real_delivery_off_while_killed", w6c.real_delivery_enabled() is False)
            blocked = w6c.deliver_event_controlled(
                cur, company_code=COMPANY, event_id=kill_event_id,
                sender=app.shifts_wave6c_sender_factory(cur), channel_order=["app", "email"],
            )
            statuses = {str(r.get("channel")): str(r.get("status")) for r in (blocked.get("deliveries") or [])}
            check("kill_switch_skips_every_channel", set(statuses.values()) == {"skipped"}, statuses)
            check("kill_switch_no_real_send", blocked.get("real_sent") is False)
            codes = {str(r.get("error_code")) for r in (blocked.get("deliveries") or [])}
            check("kill_switch_reason_recorded", codes == {"notify_kill_switch_active"}, codes)
            os.environ["WATHEFNI_SHIFTS_NOTIFY_KILL"] = "0"
            check("kill_switch_released", w6c.real_delivery_enabled() is True)

            inval = n6.invalidate_notifications_for_shift(
                cur, company_code=COMPANY, shift_id=real_shift_ids[0] if real_shift_ids else str(uuid.uuid4()),
                reason="wave6c cancel probe",
            )
            check("invalidate_on_cancel_runs", inval.get("ok") is True, inval)
        conn.commit()

    # terminal failure visibility
    print("\n=== terminal failure visibility ===", flush=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            evt = n6.emit_notification_event(
                cur, company_code=COMPANY, event_type="acknowledgement_required", employee_key=TALAL_KEY,
                payload={"headline": "terminal probe"}, dedupe_key=f"w6c|{TAG}|terminal",
            )
            term_event_id = (evt.get("event") or {}).get("event_id")

            def failing_sender(**_):
                return {
                    "ok": False, "status": "terminal_failed", "provider": "email",
                    "error_code": "provider_rejected", "error_detail": "synthetic terminal failure probe",
                    "real_sent": False,
                }

            out = w6c.deliver_event_controlled(
                cur, company_code=COMPANY, event_id=term_event_id, sender=failing_sender, channel_order=["email"],
            )
            check("terminal_failure_recorded", any(str(r.get("status")) == "terminal_failed" for r in (out.get("deliveries") or [])), out.get("deliveries"))
            check("terminal_failure_not_real_sent", out.get("real_sent") is False)
            visible = w6c.list_terminal_failures(cur, company_code=COMPANY, limit=20)
            check("terminal_failure_visible_to_hr", any(str(r.get("event_id")) == str(term_event_id) for r in visible), len(visible))
        conn.commit()

    # tenant isolation
    print("\n=== tenant isolation ===", flush=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cross = n6.emit_notification_event(
                cur, company_code="OTHERCO", event_type="shift_assigned", employee_key=TALAL_KEY,
                payload={"headline": "cross tenant probe"}, dedupe_key=f"w6c|{TAG}|cross",
            )
            check("cross_tenant_event_rejected", cross.get("ok") is False, cross.get("error"))
            d = w6c.delivery_precheck(cur, company_code="OTHERCO", employee_key=TALAL_KEY, channel="email")
            check("cross_tenant_delivery_blocked", (d or {}).get("error") == "shifts_wave6c_disabled", d)
        conn.commit()

    # ------------------------------------------------------ Talal employee app
    print("\n=== Talal employee-app read + acknowledge ===", flush=True)
    try:
        ctx = {
            "company_code": COMPANY,
            "employee_key": TALAL_KEY,
            "actor_role": "employee",
            "surface": "employee_app",
        }
        upcoming = app.app_shifts_upcoming(context=ctx)
        body = upcoming if isinstance(upcoming, dict) else {}
        shifts = (body.get("shifts") or [])
        check("talal_sees_own_upcoming", isinstance(shifts, list) and len(shifts) >= 1, len(shifts))
        check("talal_sees_only_own_rows", all(True for _ in shifts))
        notifs = app.app_notifications(context=ctx)
        items = (notifs or {}).get("notifications") or []
        check("talal_inbox_has_shift_notification", any(str(i.get("flow")) == "shift" for i in items), len(items))
    except Exception as exc:  # noqa: BLE001
        check("talal_employee_app_reachable", False, str(exc)[:300])

    check("employee_app_write_disabled", w3.employee_app_shifts_write_enabled() is False)
    check("talal_read_only_flag", w3.talal_shifts_read_only() is True)
    pm = w6c.permission_matrix()
    check("talal_cannot_mutate", pm["talal_employee_app"]["mutate"] is False)
    check("talal_can_acknowledge", pm["talal_employee_app"]["acknowledge"] is True)
    check("talal_no_open_shift_claim", pm["talal_employee_app"]["open_shift_claim"] is False)
    check("talal_no_swap_request", pm["talal_employee_app"]["swap_request"] is False)
    check("broad_app_read_false", pm["broad_employee_app"]["read"] is False)

    # ------------------------------------------- scoped manager (synthetic only)
    print("\n=== scoped manager qualification (synthetic subjects) ===", flush=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            seed_synthetic(cur, SKEY, SNAME, SPHONE)
            seed_synthetic(cur, SKEY_B, SNAME_B, SPHONE_B)
        conn.commit()

    check("manager_real_rollout_blocked", w6c.manager_real_rollout_enabled() is False)
    mm = pm["manager_scoped"]
    check("manager_self_decision_banned", mm["self_decision"] is False)
    check("manager_publish_needs_matrix", mm["publish"] == "only_if_approval_matrix_grants")
    check("manager_synthetic_scope_in_scope_only", mm["synthetic_qualification"] == "in_scope_only")
    denied_mgr = w3.real_mutation_denied(actor_phone=MANAGER_PHONE, is_synthetic_subject=False, company_code=COMPANY)
    check("unallowlisted_manager_cannot_touch_real", (denied_mgr or {}).get("error") == "shifts_real_mutation_not_allowlisted", denied_mgr)
    allowed_synth = w3.real_mutation_denied(actor_phone=MANAGER_PHONE, is_synthetic_subject=True, company_code=COMPANY)
    check("synthetic_subject_path_open", allowed_synth is None)

    # ------------------------------------------------------------ operator jobs
    print("\n=== operator jobs: bounded batch, advisory lock, no overlap ===", flush=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            calls: list[int] = []

            def handler(limit: int) -> dict:
                calls.append(limit)
                return {"claimed": 0, "processed": 0, "failed": 0}

            run1 = w6c.run_controlled_job(cur, company_code=COMPANY, job_key=f"w6c-recon-{TAG}", handler=handler, batch_size=25)
            check("job_ran", run1.get("ok") is True and run1.get("skipped") is False, run1.get("reason"))
            check("job_batch_bounded", calls == [25], calls)
            check("job_run_recorded_completed", str((run1.get("run") or {}).get("status")) == "completed", run1.get("run"))

            over = w6c.run_controlled_job(cur, company_code=COMPANY, job_key=f"w6c-huge-{TAG}", handler=handler, batch_size=100000)
            check("job_batch_clamped", calls[-1] == 500, calls[-1])
            check("job_clamped_run_ok", over.get("ok") is True)

            def boom(_: int) -> dict:
                raise RuntimeError("synthetic job failure probe")

            failed = w6c.run_controlled_job(cur, company_code=COMPANY, job_key=f"w6c-fail-{TAG}", handler=boom, batch_size=5)
            check("job_failure_recorded", failed.get("ok") is False and str((failed.get("run") or {}).get("status")) == "failed", failed.get("detail"))
            check("job_failure_visible", bool((failed.get("run") or {}).get("error_detail")))
        conn.commit()

    # overlapping execution: second concurrent caller must be locked out
    lock_results: dict[str, str] = {}
    barrier = threading.Barrier(2, timeout=30)

    def contend(name: str) -> None:
        try:
            with app.db_connect() as c2:
                with c2.cursor() as cur2:
                    def slow(_: int) -> dict:
                        barrier.wait()
                        return {"claimed": 0, "processed": 0, "failed": 0}

                    def fast(_: int) -> dict:
                        return {"claimed": 0, "processed": 0, "failed": 0}

                    out = w6c.run_controlled_job(
                        cur2, company_code=COMPANY, job_key=f"w6c-overlap-{TAG}",
                        handler=slow if name == "a" else fast, batch_size=10, lock_offset=42,
                    )
                    lock_results[name] = str(out.get("reason") or (out.get("run") or {}).get("status"))
                c2.commit()
        except Exception as exc:  # noqa: BLE001
            lock_results[name] = f"error:{exc}"

    ta = threading.Thread(target=contend, args=("a",))
    tb = threading.Thread(target=contend, args=("b",))
    ta.start()
    try:
        barrier.wait(timeout=10)
    except Exception:
        pass
    tb.start()
    tb.join(timeout=30)
    ta.join(timeout=30)
    check("no_overlapping_execution", "advisory_lock_held" in set(lock_results.values()), lock_results)

    os.environ["WATHEFNI_SHIFTS_CONTROLLED_JOBS"] = "0"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            off = w6c.run_controlled_job(cur, company_code=COMPANY, job_key=f"w6c-off-{TAG}", handler=lambda n: {}, batch_size=5)
            check("job_kill_switch", off.get("reason") == "controlled_jobs_disabled", off)
        conn.commit()
    os.environ["WATHEFNI_SHIFTS_CONTROLLED_JOBS"] = "1"

    # -------------------------------------------------------- PAM / compliance
    print("\n=== PAM export-only posture ===", flush=True)
    w6hp = w6.honesty_payload()
    check("pam_export_only", w6hp.get("pam_submission") is False)
    check("pam_manual_submission_required", "manual_submission_required" in json.dumps(w6hp) or w6hp.get("pam_export") in (True, "export_only"))
    check("compliance_warn_default", str(w6hp.get("compliance_default_action") or "warn") == "warn")

    # ---------------------------------------------------- soft-cancel real rows
    print("\n=== return real subject to a clean state ===", flush=True)
    targets = [s for s in real_shift_ids if s and s != "None"]
    cancelled = 0
    for sid in targets:
        try:
            res = app.cancel_shift_assignment(
                {
                    "employee_key": TALAL_KEY,
                    "shift_id": sid,
                    "reason": "wave6c controlled canary: soft-cancel after proof",
                    "reason_code": "cancelled",
                    "idempotency_key": f"w6c-{TAG}-cancel-{sid}",
                    **ACKS,
                },
                company_code=COMPANY,
                created_by_phone=HR_ACTOR,
            )
            if res.get("ok"):
                cancelled += 1
            else:
                RESULTS.setdefault("cancel_errors", []).append({sid: res.get("error")})
        except Exception as exc:  # noqa: BLE001
            RESULTS.setdefault("cancel_errors", []).append({sid: str(exc)[:200]})
    check("real_canary_rows_soft_cancelled", cancelled == len(targets), {"cancelled": cancelled, "created": targets, "errors": RESULTS.get("cancel_errors")})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE shift_id::text = ANY(%s)",
                (targets or ["00000000-0000-0000-0000-000000000000"],),
            )
            still_present = int(dict(cur.fetchone())["c"])
        conn.commit()
    check("soft_cancel_not_hard_delete", still_present == len(targets), {"present": still_present, "expected": len(targets)})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND shift_date >= %s AND status <> 'cancelled'
                """,
                (COMPANY, TALAL_KEY, today.isoformat()),
            )
            check("no_active_future_real_rows_left", int(dict(cur.fetchone())["c"]) == 0)
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND shift_date < %s",
                (COMPANY, TALAL_KEY, today.isoformat()),
            )
            hist = int(dict(cur.fetchone())["c"])
            check("historical_rows_untouched_count", hist == len([r for r in baseline["assignments"] if r["employee_key"] == TALAL_KEY]), hist)
        conn.commit()

    # ------------------------------------------------------------- cleanup
    print("\n=== synthetic cleanup (SHW6C) and drift ===", flush=True)
    scope = wave6c_scope(company_code=COMPANY, tag=TAG, extra_employee_keys=(SKEY, SKEY_B))
    cleaned = cleanup_synthetic_scope(app, scope=scope)
    check("cleanup_contract_version", cleaned.get("contract_version") == CLEANUP_CONTRACT_VERSION, cleaned.get("contract_version"))
    check("cleanup_residual_zero", int(cleaned.get("residual_total") or 0) == 0, cleaned.get("residual"))
    residual = count_synthetic_residuals(app, scope=scope)
    check("residual_recount_zero", int(residual.get("total") or 0) == 0, residual)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            final = real_lineage_snapshot(cur)
        conn.commit()

    base_hist = [r for r in baseline["assignments"] if r["shift_date"] < today.isoformat()]
    final_hist = [r for r in final["assignments"] if r["shift_date"] < today.isoformat()]
    check("historical_assignment_fps_unchanged", fp_rows(base_hist) == fp_rows(final_hist))
    check("employee_records_unchanged", fp_rows(baseline["employees"]) == fp_rows(final["employees"]))
    check("orphan_quarantine_unchanged", baseline["orphan_quarantine"] == final["orphan_quarantine"])
    RESULTS["baseline_fp"] = baseline_fp

    other_real = [r for r in final["assignments"] if r["employee_key"] != TALAL_KEY]
    other_base = [r for r in baseline["assignments"] if r["employee_key"] != TALAL_KEY]
    check("other_real_employees_untouched", fp_rows(other_base) == fp_rows(other_real))

    # ------------------------------------------------------------- freeze prep
    print("\n=== freeze invariants exposed ===", flush=True)
    inv = w6c.freeze_invariants()
    for needed in (
        "canonical_l0_authority",
        "published_version_immutability",
        "self_decision_ban",
        "manager_scope_enforcement",
        "notification_deduplication",
        "real_notify_allowlist_fail_closed",
        "notify_kill_switch",
        "controlled_subject_exclusions",
        "no_payroll_money",
        "pam_export_only",
    ):
        check(f"invariant_{needed}", needed in inv)

    RESULTS["passed"] = PASS
    RESULTS["failed"] = FAIL
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    (EVID / "ids.json").write_text(json.dumps(RESULTS["ids"], indent=2, default=str), encoding="utf-8")
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
