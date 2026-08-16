#!/usr/bin/env python3
"""Provision a second WATHEFNI employee-app canary for Aziz Mobile QA.

Creates a synthetic employee on Aziz's phone, seeds employee-safe fixtures,
extends EMPLOYEE_APP allowlist (Talal preserved), and returns a one-time
activation code. Does not touch Talal's employee row.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

COMPANY = "WATHEFNI"
PHONE = "96599338566"
EMP_KEY = f"{COMPANY}-{PHONE}"
NAME = "W5C-SYNTH|Aziz Mobile QA"
TALAL = "WATHEFNI-96550252254"
ALLOWLIST = f"{TALAL},{EMP_KEY}"
DROPINS = [
    "/etc/systemd/system/wathefni-orchestrator.service.d/zz-employee-final-controlled-rollout.conf",
    "/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzz-shifts-wave6c-controlled.conf",
]


def main() -> int:
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

    import app
    from psycopg2.extras import Json

    today = date.today()
    meta = {
        "source": "employee_mobile_qa_canary",
        "synthetic": True,
        "qa_label": "Aziz Mobile QA",
        "do_not_use_for_payroll": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # --- 1) Ensure synthetic employee (never touch Talal) ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key, name, phone FROM employees WHERE employee_key=%s FOR UPDATE", (TALAL,))
            talal = dict(cur.fetchone() or {})
            if not talal or talal.get("phone") != "96550252254":
                raise SystemExit("REFUSE: Talal canary row missing/unexpected")

            cur.execute("SELECT * FROM employees WHERE employee_key=%s FOR UPDATE", (EMP_KEY,))
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE employees SET
                      name=%s,
                      phone=%s,
                      employment_status='active',
                      email=%s,
                      position_title=%s,
                      start_date=COALESCE(start_date, %s),
                      profile = COALESCE(profile, '{}'::jsonb) || %s::jsonb,
                      raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
                      updated_at=now()
                    WHERE employee_key=%s AND company_code=%s
                    RETURNING *
                    """,
                    (
                        NAME,
                        PHONE,
                        "aziz+mobile-qa@wathefni.internal",
                        "Mobile QA Tester",
                        today - timedelta(days=14),
                        Json({"department": "Internal QA", "synthetic": True, "qa": "employee_mobile"}),
                        Json(meta),
                        EMP_KEY,
                        COMPANY,
                    ),
                )
                emp = dict(cur.fetchone())
                action = "updated"
            else:
                # Alias collision guard: refuse if another employee already owns this phone.
                cur.execute(
                    "SELECT employee_key, name, phone FROM employees WHERE company_code=%s AND phone=%s AND employee_key<>%s",
                    (COMPANY, PHONE, EMP_KEY),
                )
                collision = cur.fetchone()
                if collision:
                    raise SystemExit(f"REFUSE: phone already owned by {dict(collision)}")
                cur.execute(
                    """
                    INSERT INTO employees (
                      employee_key, phone, company_code, name, email, position_title,
                      start_date, employment_status, onboarding_status, profile, raw_json, updated_at
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,'active','not_started',%s,%s, now()
                    )
                    RETURNING *
                    """,
                    (
                        EMP_KEY,
                        PHONE,
                        COMPANY,
                        NAME,
                        "aziz+mobile-qa@wathefni.internal",
                        "Mobile QA Tester",
                        today - timedelta(days=14),
                        Json({"department": "Internal QA", "synthetic": True, "qa": "employee_mobile"}),
                        Json(meta),
                    ),
                )
                emp = dict(cur.fetchone())
                action = "created"
        conn.commit()

    print(json.dumps({"employee_action": action, "employee_key": EMP_KEY, "phone": PHONE, "name": NAME}))

    # --- 2) Seed onboarding (shared Wave2 authority) ---
    try:
        start = app.start_onboarding(
            {"employee_key": EMP_KEY, "allow_restart": True},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        print(json.dumps({"onboarding_start": {"ok": bool(start.get("ok")), "status": start.get("status") or start.get("error")}}))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"onboarding_start": {"ok": False, "error": str(exc)[:200]}}))

    # --- 3) Seed shifts / leave / attendance / notifications (employee-scoped only) ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Clear prior QA fixtures for this key only (idempotent re-run)
            for sql in (
                "DELETE FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND metadata->>'qa'='employee_mobile'",
                "DELETE FROM leave_requests WHERE company_code=%s AND employee_key=%s AND metadata->>'qa'='employee_mobile'",
                "DELETE FROM attendance_records WHERE company_code=%s AND employee_key=%s AND metadata->>'qa'='employee_mobile'",
                "DELETE FROM employee_messages WHERE company_code=%s AND employee_key=%s AND metadata->>'qa'='employee_mobile'",
            ):
                cur.execute(sql, (COMPANY, EMP_KEY))

            # Today + upcoming shifts
            for offset, start_t, end_t, loc in (
                (0, "09:00", "17:00", "WATHEFNI HQ — QA Desk"),
                (1, "10:00", "18:00", "WATHEFNI HQ — QA Desk"),
                (3, "09:00", "13:00", "Remote — QA"),
            ):
                cur.execute(
                    """
                    INSERT INTO shift_assignments (
                      company_code, employee_key, employee_phone, employee_name,
                      shift_date, start_time, end_time, role, location, status, metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,'QA Tester',%s,'scheduled',%s)
                    """,
                    (
                        COMPANY,
                        EMP_KEY,
                        PHONE,
                        NAME,
                        today + timedelta(days=offset),
                        start_t,
                        end_t,
                        loc,
                        Json({**meta, "qa": "employee_mobile"}),
                    ),
                )

            # Leave: one approved past, one requested future
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  start_date, end_date, leave_type, status, reason, metadata, chargeable_days
                ) VALUES
                (%s,%s,%s,%s,%s,%s,'annual','approved','Synthetic QA approved leave',%s,1),
                (%s,%s,%s,%s,%s,%s,'sick','requested','Synthetic QA sick request',%s,1)
                """,
                (
                    COMPANY, EMP_KEY, PHONE, NAME, today - timedelta(days=10), today - timedelta(days=10),
                    Json({**meta, "qa": "employee_mobile"}),
                    COMPANY, EMP_KEY, PHONE, NAME, today + timedelta(days=7), today + timedelta(days=7),
                    Json({**meta, "qa": "employee_mobile"}),
                ),
            )

            # Attendance last 5 weekdays-ish
            for i, status in enumerate(["present", "present", "late", "present", "absent"]):
                cur.execute(
                    """
                    INSERT INTO attendance_records (
                      company_code, employee_key, employee_phone, employee_name,
                      attendance_date, status, late_minutes, notes, metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        COMPANY,
                        EMP_KEY,
                        PHONE,
                        NAME,
                        today - timedelta(days=i + 1),
                        status,
                        12 if status == "late" else 0,
                        "Synthetic QA attendance fixture",
                        Json({**meta, "qa": "employee_mobile"}),
                    ),
                )

            # Inbox notifications (flows the app surfaces)
            for flow, template, preview in (
                ("shift", "shift_assigned", "Synthetic: your QA shift was scheduled."),
                ("leave_decision", "leave_approved", "Synthetic: annual leave approved for QA fixture."),
                ("onboarding", "onboarding_reminder", "Synthetic: complete your QA onboarding checklist."),
                ("compliance", "document_expiry", "Synthetic: compliance reminder for Mobile QA."),
            ):
                cur.execute(
                    """
                    INSERT INTO employee_messages (
                      company_code, employee_key, flow, template_key, criticality, sensitivity,
                      locale, target_phone, status, body_preview, channel_used, delivered_at,
                      dedupe_key, metadata
                    ) VALUES (
                      %s,%s,%s,%s,'standard','preview','en',%s,'delivered',%s,'app', now(),
                      %s, %s
                    )
                    """,
                    (
                        COMPANY,
                        EMP_KEY,
                        flow,
                        template,
                        PHONE,
                        preview,
                        f"mobile-qa:{EMP_KEY}:{flow}:{uuid.uuid4().hex[:8]}",
                        Json({**meta, "qa": "employee_mobile"}),
                    ),
                )
        conn.commit()

    # --- 4) Extend allowlist (Talal kept) ---
    for path in DROPINS:
        if not os.path.exists(path):
            print(json.dumps({"allowlist_file_missing": path}))
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        old = "Environment=WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254"
        new = f"Environment=WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST={ALLOWLIST}"
        if EMP_KEY in text and "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST" in text:
            # already contains qa key somehow — normalize line
            lines = []
            for line in text.splitlines():
                if line.startswith("Environment=WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST="):
                    lines.append(new)
                else:
                    lines.append(line)
            text2 = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        elif old in text:
            text2 = text.replace(old, new)
        else:
            # append if key present with different formatting
            if "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=" in text:
                lines = []
                for line in text.splitlines():
                    if "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=" in line:
                        lines.append(new)
                    else:
                        lines.append(line)
                text2 = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            else:
                text2 = text.rstrip("\n") + "\n" + new + "\n"
        if text2 != text:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text2)
            print(json.dumps({"allowlist_updated": path, "value": ALLOWLIST}))
        else:
            print(json.dumps({"allowlist_unchanged": path}))

    os.system("systemctl daemon-reload && systemctl restart wathefni-orchestrator")
    # Wait for health
    import time
    import urllib.request

    healthy = False
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=2) as resp:
                if resp.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(1)
    print(json.dumps({"orchestrator_healthy": healthy}))

    # Reload allowlist helpers in this process by re-reading env from systemd is hard;
    # set local env then re-import check via os.environ for invite creation.
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ALLOWLIST
    os.environ["WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"

    # Force re-read by calling after env set (functions read os.environ live)
    app.assert_employee_app_allowlisted(TALAL)
    app.assert_employee_app_allowlisted(EMP_KEY)
    print(json.dumps({"allowlist_assert": "ok", "keys": [TALAL, EMP_KEY]}))

    # --- 5) Issue activation invite + return plaintext code once ---
    employee = app.find_employee_by_key(EMP_KEY, company_code=COMPANY)
    if not employee:
        raise SystemExit("employee missing after create")
    invite, code = app.create_employee_app_invite(COMPANY, employee, created_by_phone=PHONE, created_by_user_id="mobile-qa-seed")
    # Mark disclosed for audit trail without HR task path
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employee_app_invites SET code_disclosed_at=now(), updated_at=now() WHERE invite_id=%s",
                (invite.get("invite_id"),),
            )
        conn.commit()

    # Confirm Talal unchanged
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key, name, phone FROM employees WHERE employee_key=%s", (TALAL,))
            talal_after = dict(cur.fetchone())
            cur.execute(
                "SELECT count(*) AS n FROM shift_assignments WHERE employee_key=%s AND metadata->>'qa'='employee_mobile'",
                (EMP_KEY,),
            )
            shifts_n = int(dict(cur.fetchone())["n"])
            cur.execute(
                "SELECT count(*) AS n FROM onboarding_items WHERE employee_key=%s",
                (EMP_KEY,),
            )
            onb_n = int(dict(cur.fetchone())["n"])

    # Mint session smoke (does not consume invite)
    session = app.create_employee_session(COMPANY, EMP_KEY, PHONE)
    token = session.get("access_token") or session.get("token")
    import urllib.request as ur

    def http_get(path: str) -> int:
        req = ur.Request(
            f"http://127.0.0.1:8010{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with ur.urlopen(req, timeout=30) as resp:
            return int(resp.status)

    me_st = http_get("/app/me")
    paths = {
        "onboarding": http_get("/app/onboarding"),
        "leave": http_get("/app/leave"),
        "shifts_today": http_get("/app/shifts/today"),
        "attendance": http_get("/app/attendance"),
        "notifications": http_get("/app/notifications?limit=10"),
        "documents": http_get("/app/documents"),
        "profile": http_get("/app/profile"),
    }

    result = {
        "ok": True,
        "phone_digits": PHONE,
        "phone_display": f"+{PHONE}",
        "activation_code": code,
        "invite_id": str(invite.get("invite_id")),
        "expires_at": str(invite.get("expires_at")),
        "employee_key": EMP_KEY,
        "company_code": COMPANY,
        "name": NAME,
        "talal_preserved": talal_after,
        "seed_counts": {"shifts_qa": shifts_n, "onboarding_items": onb_n},
        "api_smoke": {"me": me_st, **paths},
        "allowlist": ALLOWLIST,
        "authority": {
            "payroll_money": False,
            "hiring_admin": False,
            "manager": False,
            "employee_ess_only": True,
        },
    }
    print("AZIZ_MOBILE_QA_CANARY_READY")
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
