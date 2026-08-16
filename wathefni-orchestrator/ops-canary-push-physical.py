#!/usr/bin/env python3
"""Safe canary-only Employee App push physical trigger.

Sends ONE synthetic Inbox+push event for Aziz or Talal without mutating leave,
shifts, payroll, bank, or onboarding business rows. Uses unique dedupe keys
prefixed with canary_push_phys: so retries are intentional duplicates only when
asked.

Usage (on prod host with systemd env):
  EVENT=leave_approved EMPLOYEE=aziz DUPE=0 .venv/bin/python ops-canary-push-physical.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta

os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, "/opt/wathefni/orchestrator")

EMPLOYEES = {
    "aziz": "WATHEFNI-96599338566",
    "talal": "WATHEFNI-96550252254",
}

EVENTS = {
    "leave_approved": {
        "flow": "leave_decision",
        "template_key": "leave_request_approved",
        "email_subject": "Update on your leave request",
        "text": "Your leave request for {date_text} has been approved.",
        "variables": lambda: {
            "start_date": (date.today() + timedelta(days=14)).isoformat(),
            "end_date": (date.today() + timedelta(days=16)).isoformat(),
            "date_text": f"{(date.today() + timedelta(days=14)).isoformat()} to {(date.today() + timedelta(days=16)).isoformat()}",
        },
    },
    "leave_rejected": {
        "flow": "leave_decision",
        "template_key": "leave_request_rejected",
        "email_subject": "Update on your leave request",
        "text": "Your leave request for {date_text} was not approved.",
        "variables": lambda: {
            "start_date": (date.today() + timedelta(days=21)).isoformat(),
            "end_date": (date.today() + timedelta(days=21)).isoformat(),
            "date_text": (date.today() + timedelta(days=21)).isoformat(),
        },
    },
    "shift_assigned": {
        "flow": "shift",
        "template_key": "shift_assigned",
        "email_subject": "Your shift schedule",
        "text": "You have a shift on {shift_date} from {shift_time}.",
        "variables": lambda: {
            "shift_date": (date.today() + timedelta(days=3)).isoformat(),
            "shift_time": "09:00",
            "location": "Canary site",
        },
    },
    "shift_cancelled_same_day": {
        "flow": "shift",
        "template_key": "shift_cancelled",
        "email_subject": "A shift was cancelled",
        "text": "Your shift on {shift_date} has been cancelled.",
        "variables": lambda: {"shift_date": date.today().isoformat()},
    },
    "shift_reminder": {
        "flow": "shift",
        "template_key": "shift_reminder",
        "email_subject": "Shift reminder",
        "text": "Reminder: your shift starts on {shift_date} at {shift_time}.",
        "variables": lambda: {
            "shift_date": date.today().isoformat(),
            "shift_time": "17:00",
        },
    },
    "document_required": {
        "flow": "compliance",
        "template_key": "compliance_document_required",
        "email_subject": "A document HR needs from you",
        "text": "Please send an up-to-date copy of your Civil ID.",
        "variables": lambda: {"document_type": "Civil ID"},
    },
    "document_expiring": {
        "flow": "compliance",
        "template_key": "compliance_document_expiring",
        "email_subject": "A document is expiring soon",
        "text": "Your passport is expiring soon.",
        "variables": lambda: {
            "document_type": "Passport",
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    },
    "payslip_ready": {
        "flow": "payroll",
        "template_key": "payslip_ready",
        "direct_push": True,
        "variables": lambda: {
            "period": f"{date.today().strftime('%B %Y')} canary",
            "payslip_id": f"canary-slip-{uuid.uuid4().hex[:8]}",
        },
    },
    "onboarding_reminder": {
        "flow": "onboarding",
        "template_key": "onboarding_reminder",
        "email_subject": "A reminder to finish your onboarding",
        "text": "A quick reminder to finish your onboarding steps.",
        "variables": lambda: {},
    },
    "bank_correction": {
        "flow": "bank",
        "template_key": "bank_correction_required",
        "email_subject": "Bank details need attention",
        "text": "Your bank details need a correction. Please open Bank in the OctoHR app.",
        "variables": lambda: {"deep_link": {"path": "/bank"}},
    },
    "app_activation_should_not_push": {
        "flow": "app_activation",
        "template_key": "app_activation",
        "email_subject": "Your OctoHR app activation code",
        "text": "Your WATHEFNI app activation code is 000000. It expires in 24 hours.",
        "variables": lambda: {
            "code": "000000",
            "company_name": "WATHEFNI",
            "expiry_hours": 24,
        },
        "expect_no_push": True,
    },
}


def main() -> int:
    import app

    who = (os.environ.get("EMPLOYEE") or "aziz").strip().lower()
    event = (os.environ.get("EVENT") or "").strip()
    stamp = (os.environ.get("STAMP") or uuid.uuid4().hex[:10]).strip()
    force_dupe = (os.environ.get("DUPE") or "0").strip() == "1"

    if who not in EMPLOYEES:
        print(json.dumps({"ok": False, "error": "employee_must_be_aziz_or_talal"}))
        return 2
    if event not in EVENTS:
        print(json.dumps({"ok": False, "error": "unknown_event", "allowed": sorted(EVENTS)}))
        return 2

    emp_key = EMPLOYEES[who]
    tokens = app.active_push_tokens_for("WATHEFNI", emp_key)
    spec = EVENTS[event]
    variables = spec["variables"]()
    dedupe = f"canary_push_phys:{event}:{stamp}"
    if force_dupe:
        # Re-use prior stamp intentionally to prove dedupe/collapse
        dedupe = f"canary_push_phys:{event}:{stamp}"

    employee = {
        "employee_key": emp_key,
        "company_code": "WATHEFNI",
        "name": who.title(),
        "phone": "",
        "email": "",
    }
    # Enrich contact for ladder fallbacks (should not WA if no phone — push only path)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT employee_key, company_code, name, phone, email FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
                ("WATHEFNI", emp_key),
            )
            row = cur.fetchone()
            if row:
                employee = dict(row)

    result: dict = {
        "ok": False,
        "employee_key": emp_key,
        "event": event,
        "dedupe": dedupe,
        "active_tokens": len(tokens),
        "push_enabled": app.push_notifications_enabled(),
    }

    if not tokens and not spec.get("expect_no_push"):
        result["error"] = "push_token_missing"
        print(json.dumps(result, default=str))
        return 3

    if spec.get("direct_push"):
        import employee_push_tray as tray

        title, body = tray.tray_copy(
            "payslip_ready",
            variables={"period": variables["period"]},
        )
        # Inbox insert (safe synthetic) — dedupe check, no unique constraint required
        message_id = str(uuid.uuid4())
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM employee_messages WHERE company_code=%s AND dedupe_key=%s LIMIT 1",
                    ("WATHEFNI", dedupe),
                )
                if cur.fetchone():
                    result.update({"ok": False, "error": "dedupe_exists", "dedupe": dedupe})
                    print(json.dumps(result, default=str))
                    return 5
                cur.execute(
                    """
                    INSERT INTO employee_messages
                      (message_id, company_code, employee_key, flow, template_key, criticality,
                       sensitivity, locale, status, body_preview, dedupe_key, metadata)
                    VALUES (%s,%s,%s,'payroll','payslip_ready','standard','preview','en','delivered',%s,%s,%s::jsonb)
                    """,
                    (
                        message_id,
                        "WATHEFNI",
                        emp_key,
                        f"Your payslip for {variables['period']} is ready to view in the app."[:280],
                        dedupe,
                        json.dumps(
                            {
                                "deep_link": {"path": "/payslips", "payslip_id": variables["payslip_id"]},
                                "payslip_id": variables["payslip_id"],
                                "period": variables["period"],
                                "canary_physical": True,
                            }
                        ),
                    ),
                )
            conn.commit()
        push = app.send_outbound_push(
            company_code="WATHEFNI",
            employee_key=emp_key,
            title=title,
            body=body,
            flow="payroll",
            subject_type="employee",
            subject_key=emp_key,
            message_kind="payslip_ready",
            template_key="payslip_ready",
            dedupe_key=dedupe,
            deep_link={"path": "/payslips", "payslip_id": variables["payslip_id"]},
            variables=variables,
        )
        result.update({"ok": bool(push.get("ok")), "channel": "push", "push": push, "message_id": message_id})
        print(json.dumps(result, default=str))
        return 0 if push.get("ok") else 4

    text = spec["text"].format(**variables) if "{" in spec["text"] else spec["text"]
    send = app.deliver_employee_notification(
        employee,
        flow=spec["flow"],
        template_key=spec["template_key"],
        text=text,
        email_subject=spec["email_subject"],
        company_code="WATHEFNI",
        variables=variables,
        dedupe_key=dedupe,
        extra={"canary_physical": True, "stamp": stamp},
    )
    result.update(
        {
            "ok": bool(send.get("ok")),
            "delivery_status": send.get("delivery_status"),
            "channel": send.get("channel"),
            "message_id": send.get("message_id"),
            "send": {k: send.get(k) for k in ("ok", "delivery_status", "channel", "throttled", "error")},
        }
    )
    if spec.get("expect_no_push"):
        # Pass when we did NOT deliver via push
        no_push = str(send.get("channel") or "") != "push" and str(send.get("delivery_status") or "") != "delivered_push"
        result["expect_no_push"] = True
        result["ok"] = no_push or (send.get("channel") in {"whatsapp_session", "whatsapp_template", "email", None})
        result["assert_channel_not_push"] = no_push
    print(json.dumps(result, default=str))
    return 0 if result.get("ok") else 4


if __name__ == "__main__":
    raise SystemExit(main())
