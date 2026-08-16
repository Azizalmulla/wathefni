#!/usr/bin/env python3
"""Seed disposable Inbox fixtures for Employee App visual + interaction QA.

Target: WATHEFNI-96550010001 (Noura) — already on the employee-app allowlist.
Aziz/Talal are never touched. Rows tagged metadata.fixture for cleanup.

Inserts into employee_messages (+ optional employee_notification_reads) using
only _APP_INBOX_FLOWS. Bank is not an Inbox flow and is not seeded here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _pds  # noqa: E402

_pds.activate_fixture_tooling_from_argv()
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

COMPANY = os.environ["WATHEFNI_COMPANY_CODE"]
KEY = f"{COMPANY}-96550010001"
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}
TAG = "inbox-visual-fixture"
STAMP = os.environ.get("INBOX_VISUAL_STAMP") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _guard() -> None:
    if KEY in PROTECTED:
        raise SystemExit(f"refusing protected canary key {KEY}")


def cleanup() -> dict[str, Any]:
    _guard()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM employee_notification_reads
                WHERE company_code=%s AND employee_key=%s
                  AND message_id IN (
                    SELECT message_id FROM employee_messages
                    WHERE company_code=%s AND employee_key=%s
                      AND COALESCE(metadata->>'fixture','') = %s
                  )
                """,
                (COMPANY, KEY, COMPANY, KEY, TAG),
            )
            reads = cur.rowcount
            cur.execute(
                """
                DELETE FROM employee_messages
                WHERE company_code=%s AND employee_key=%s
                  AND COALESCE(metadata->>'fixture','') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            messages = cur.rowcount
        conn.commit()
    return {
        "employee_key": KEY,
        "deleted_messages": messages,
        "deleted_reads": reads,
        "stamp": STAMP,
    }


def _specs(now: datetime) -> list[dict[str, Any]]:
    """Unread first cluster, then Updates volume, then Account activity."""
    rows: list[dict[str, Any]] = []

    def add(
        *,
        hours_ago: float,
        flow: str,
        template_key: str,
        body: str | None,
        path: str,
        unread: bool,
        sensitivity: str = "preview",
        extra_meta: dict[str, Any] | None = None,
        body_ar: str | None = None,
    ) -> None:
        meta: dict[str, Any] = {
            "fixture": TAG,
            "stamp": STAMP,
            "deep_link": {"path": path},
        }
        if body_ar:
            meta["body_ar"] = body_ar
        if extra_meta:
            meta.update(extra_meta)
        rows.append(
            {
                "created_at": now - timedelta(hours=hours_ago),
                "flow": flow,
                "template_key": template_key,
                "body": body,
                "unread": unread,
                "sensitivity": sensitivity,
                "metadata": meta,
            }
        )

    # —— Unread (scan + tap stress) ——
    add(
        hours_ago=1.5,
        flow="leave_decision",
        template_key="leave_request_approved",
        body="Your annual leave from 12 Aug to 14 Aug has been approved.",
        body_ar="تمت الموافقة على إجازتك السنوية من 12 أغسطس إلى 14 أغسطس.",
        path="/(tabs)/leave",
        unread=True,
    )
    add(
        hours_ago=3,
        flow="leave_decision",
        template_key="leave_request_pending",
        body="Your leave request for 20–21 Aug is waiting for HR review.",
        body_ar="طلب إجازتك لـ 20–21 أغسطس قيد مراجعة الموارد البشرية.",
        path="/(tabs)/leave",
        unread=True,
    )
    add(
        hours_ago=5,
        flow="payroll",
        template_key="payslip_ready",
        body="Your payslip for July 2026 is ready to view in the app.",
        body_ar="كشف راتبك لشهر يوليو 2026 جاهز للعرض في التطبيق.",
        path="/payslips",
        unread=True,
        extra_meta={"payslip_id": f"fixture-payslip-{STAMP}"},
    )
    add(
        hours_ago=8,
        flow="compliance",
        template_key="compliance_document_expiring",
        body="Your Civil ID expires on 30 Sep 2026. Renew and upload the updated copy.",
        body_ar="ينتهي البطاقة المدنية في 30 سبتمبر 2026. يرجى التجديد ورفع النسخة المحدثة.",
        path="/documents",
        unread=True,
    )
    add(
        hours_ago=12,
        flow="compliance",
        template_key="compliance_document_required",
        body="HR needs your residence permit to keep your file complete.",
        body_ar="يحتاج قسم الموارد البشرية إلى إذن الإقامة لإكمال ملفك.",
        path="/documents",
        unread=True,
    )
    add(
        hours_ago=18,
        flow="shift",
        template_key="shift_rescheduled",
        body="Your shift moved to Sunday 10 Aug, 09:00–17:00 at Head Office.",
        body_ar="تم نقل مناوبتك إلى الأحد 10 أغسطس، 09:00–17:00 في المكتب الرئيسي.",
        path="/(tabs)/schedule",
        unread=True,
    )
    add(
        hours_ago=26,
        flow="onboarding",
        template_key="onboarding_reminder",
        body="A few onboarding steps are still open. Finish them when you can.",
        body_ar="لا تزال بعض خطوات الانضمام مفتوحة. أكملها عندما يتسنى لك.",
        path="/onboarding",
        unread=True,
    )
    add(
        hours_ago=30,
        flow="shift",
        template_key="shift_assigned",
        body="You have a shift on Tuesday 11 Aug from 08:00–16:00.",
        body_ar="لديك مناوبة يوم الثلاثاء 11 أغسطس من 08:00–16:00.",
        path="/(tabs)/schedule",
        unread=True,
    )

    # —— Updates (read) — density + Show more ——
    update_specs = [
        (40, "payroll", "payslip_ready", "Your payslip for June 2026 is ready.", "/payslips"),
        (48, "leave_decision", "leave_request_rejected", "Your leave request for 1–2 Jul was not approved.", "/(tabs)/leave"),
        (56, "shift", "shift_cancelled", "Your shift on 28 Jul has been cancelled.", "/(tabs)/schedule"),
        (64, "compliance", "compliance_document_required", "Please send your passport copy when you can.", "/documents"),
        (72, "onboarding", "employee_onboarding_welcome", "Welcome — your onboarding checklist is ready.", "/onboarding"),
        (80, "shift", "shift_reminder", "Reminder: your shift starts tomorrow at 09:00.", "/(tabs)/schedule"),
        (96, "payroll", "payslip_ready", "Your payslip for May 2026 is ready.", "/payslips"),
        (110, "leave_decision", "leave_request_approved", "Your sick leave for 15 Jun was approved.", "/(tabs)/leave"),
        (124, "shift", "shift_assigned", "You have a shift on 22 Jun from 10:00–18:00.", "/(tabs)/schedule"),
        (140, "compliance", "compliance_document_expiring", "Your passport expires on 12 Dec 2026.", "/documents"),
        (156, "onboarding", "onboarding_reminder", "Finish remaining onboarding documents.", "/onboarding"),
        (172, "payroll", "payslip_ready", "Your payslip for April 2026 is ready.", "/payslips"),
        (188, "leave_decision", "leave_request_approved", "Your leave from 3–5 May was approved.", "/(tabs)/leave"),
        (204, "shift", "shift_rescheduled", "Friday shift moved to 14:00–22:00.", "/(tabs)/schedule"),
        (220, "compliance", "compliance_document_required", "Employment contract copy still needed.", "/documents"),
        (236, "payroll", "payslip_ready", "Your payslip for March 2026 is ready.", "/payslips"),
        (252, "shift", "shift_assigned", "Weekend coverage shift on 12 Apr, 12:00–20:00.", "/(tabs)/schedule"),
        (268, "leave_decision", "leave_request_rejected", "Leave for 18 Mar was not approved.", "/(tabs)/leave"),
        (284, "onboarding", "onboarding_reminder", "Bank details step is still incomplete.", "/onboarding"),
        (300, "shift", "shift_cancelled", "Evening shift on 2 Mar was cancelled.", "/(tabs)/schedule"),
        (320, "payroll", "payslip_ready", "Your payslip for February 2026 is ready.", "/payslips"),
        (340, "compliance", "compliance_document_expiring", "Work permit renewal window opens soon.", "/documents"),
    ]
    for hours, flow, template, body, path in update_specs:
        add(
            hours_ago=float(hours),
            flow=flow,
            template_key=template,
            body=body,
            path=path,
            unread=False,
        )

    # —— Account activity (read app_activation — only newest non-hidden is projected) ——
    add(
        hours_ago=6,
        flow="app_activation",
        template_key="app_activation",
        body=None,
        path="/notifications",
        unread=False,
        sensitivity="metadata_only",
    )
    # Older activation — will be inbox_hidden so it does not flood Unread/Account.
    add(
        hours_ago=400,
        flow="app_activation",
        template_key="app_activation",
        body=None,
        path="/notifications",
        unread=False,
        sensitivity="metadata_only",
        extra_meta={
            "inbox_hidden": True,
            "inbox_hidden_reason": "superseded_by_newer_activation",
        },
    )

    return rows


def seed() -> dict[str, Any]:
    _guard()
    emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or {}
    if not emp:
        raise SystemExit(f"missing synthetic employee {KEY}")

    cleanup()

    now = datetime.now(timezone.utc)
    specs = _specs(now)
    inserted: list[str] = []
    unread_ids: list[str] = []

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for spec in specs:
                message_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO employee_messages
                      (message_id, company_code, employee_key, flow, template_key,
                       criticality, sensitivity, locale, status, body_preview,
                       dedupe_key, metadata, created_at, updated_at)
                    VALUES
                      (%s,%s,%s,%s,%s,'standard',%s,'en','delivered',%s,%s,%s,%s,%s)
                    """,
                    (
                        message_id,
                        COMPANY,
                        KEY,
                        spec["flow"],
                        spec["template_key"],
                        spec["sensitivity"],
                        spec["body"],
                        f"inbox-visual:{TAG}:{message_id}",
                        Json(spec["metadata"]),
                        spec["created_at"],
                        spec["created_at"],
                    ),
                )
                inserted.append(message_id)
                if spec["unread"]:
                    unread_ids.append(message_id)
                else:
                    cur.execute(
                        """
                        INSERT INTO employee_notification_reads
                          (company_code, employee_key, message_id, read_at)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (employee_key, message_id) DO UPDATE SET read_at=EXCLUDED.read_at
                        """,
                        (COMPANY, KEY, message_id, spec["created_at"] + timedelta(minutes=30)),
                    )
        conn.commit()

    # Ensure app access + fresh activation for physical login
    if not emp.get("app_access_enabled"):
        import employee_app_access as access

        access.set_employee_app_access(
            legacy,
            {
                "company_code": COMPANY,
                "user_id": "inbox-visual-fixture",
                "actor_user_id": "inbox-visual-fixture",
                "email": "inbox-visual-fixture@wathefni.ai",
                "permissions": ["employees.manage", "onboarding.manage"],
            },
            employee_key=KEY,
            enabled=True,
            reason="inbox-visual-fixture",
            deliver_invite=False,
        )
        emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or emp

    invite, code = legacy.create_employee_app_invite(
        COMPANY, emp, created_by_user_id="inbox-visual-fixture"
    )

    phone = legacy.digits(emp.get("phone"))
    ctx = {
        "company_code": COMPANY,
        "employee_key": KEY,
        "employee": emp,
        "phone": phone,
        "session_id": f"inbox-visual-{STAMP}",
        "actor_employee_key": KEY,
        "actor_user_id": f"employee_app:{KEY}",
        "actor_phone": phone,
        "actor_email": emp.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {
            "role": "employee",
            "company_code": COMPANY,
            "phone": phone,
            "name": emp.get("name") or "",
        },
    }
    page = legacy.app_notifications(locale="en", context=ctx)
    notes = page.get("notifications") or []
    unread = int(page.get("unread") or 0)
    flows = sorted({str(n.get("flow") or "") for n in notes})
    has_system = any(str(n.get("flow") or "") == "app_activation" for n in notes)
    ok = (
        len(inserted) >= 30
        and unread >= 6
        and len(notes) >= 25
        and "leave_decision" in flows
        and "payroll" in flows
        and "compliance" in flows
        and "shift" in flows
        and "onboarding" in flows
        and has_system
    )
    return {
        "ok": ok,
        "stamp": STAMP,
        "employee_key": KEY,
        "name": emp.get("name"),
        "phone": phone,
        "activation_code": code,
        "invite_expires_at": str(invite.get("expires_at") or ""),
        "seeded_count": len(inserted),
        "projected_count": len(notes),
        "unread": unread,
        "flows": flows,
        "protected_untouched": sorted(PROTECTED),
        "note": "Bank is not an Inbox flow; onboarding covers bank-step messaging when entitled.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        print(json.dumps(cleanup(), indent=2))
        return 0
    result = seed()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
