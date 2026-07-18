from __future__ import annotations

import uuid

from psycopg2.extras import Json

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    suffix = uuid.uuid4().hex[:10]
    employee_key = f"smoke-notification-emp-{suffix}"
    app_key = f"9655559{suffix[:4]}-WATHEFNI-SMOKE-NOTIFICATION-{suffix}"
    phone = f"9655559{suffix[:4]}"
    sent_delivery_id = f"smoke-normal-reminder-sent-{suffix}"
    failed_reminder_id = f"smoke-reminder-failed-{suffix}"
    closed_delivery_id = f"smoke-closed-delivery-{suffix}"
    company = "WATHEFNI"

    original_notify_hr_admins = app.notify_hr_admins
    original_pending_candidates = app.pending_onboarding_reminder_candidates
    original_send_onboarding_reminder = app.send_onboarding_reminder
    captures: list[dict] = []
    original_module_rows: list[dict] = []

    def fake_notify_hr_admins(**kwargs):
        captures.append(kwargs)
        return {"ok": True, "message": kwargs.get("message"), "fake": True}

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT module_key, enabled, settings FROM company_modules WHERE company_code=%s AND module_key IN ('onboarding','compliance')",
                    (company,),
                )
                original_module_rows = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'onboarding',true,'notification_policy_smoke',%s,now()),
                           (%s,'compliance',true,'notification_policy_smoke',%s,now())
                    ON CONFLICT (company_code, module_key)
                    DO UPDATE SET settings=company_modules.settings || EXCLUDED.settings,
                                  enabled=true,
                                  updated_at=now()
                    """,
                    (
                        company,
                        Json({"automation_enabled": True}),
                        company,
                        Json({"automation_enabled": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO employees (employee_key, phone, company_code, name, onboarding_status, documents_pending, documents_complete, raw_json)
                    VALUES (%s,%s,%s,%s,'in_progress',2,0,%s)
                    """,
                    (employee_key, phone, company, "Smoke Notification Employee", Json({"smoke": True, "suffix": suffix})),
                )
                cur.execute(
                    """
                    INSERT INTO onboarding_items (employee_key, item_id, label, item_type, required, document_type, status, raw_json)
                    VALUES (%s,'civil_id','Civil ID','document',true,'civil_id','pending',%s),
                           (%s,'passport','Passport','document',true,'passport','pending',%s)
                    """,
                    (employee_key, Json({"smoke": True}), employee_key, Json({"smoke": True})),
                )
                cur.execute(
                    """
                    INSERT INTO candidates (phone, name, email, active_company_code, active_position_code, raw_json)
                    VALUES (%s,'Smoke Candidate','smoke@example.com',%s,'SMOKE_NOTIFICATION',%s)
                    """,
                    (phone, company, Json({"smoke": True, "suffix": suffix})),
                )
                cur.execute(
                    """
                    INSERT INTO applications (app_key, phone, company_code, position_code, position_title, status, current_step, screening_status, raw_json, created_at, updated_at, data_source, data_source_detail)
                    VALUES (%s,%s,%s,'SMOKE_NOTIFICATION','Smoke Notification','screening','screening','pending',%s,CURRENT_DATE,CURRENT_DATE,'production','temporary_notification_policy_smoke')
                    """,
                    (app_key, phone, company, Json({"smoke": True, "suffix": suffix})),
                )
                cur.execute(
                    """
                    INSERT INTO outbound_delivery_events
                    (delivery_id, channel, account_id, target_phone, target_conversation_id, message_kind, subject_type, subject_key, status, message_text, last_error, payload, sent_at, failed_at)
                    VALUES
                    (%s,'octopus','default',%s,'1','onboarding_reminder','employee',%s,'sent','Normal reminder sent',NULL,%s,now(),NULL),
                    (%s,'octopus','default',%s,'2','onboarding_reminder','employee',%s,'failed','Reminder failed','conversation_closed',%s,NULL,now()),
                    (%s,'octopus','default',%s,'3','text','application',%s,'failed','Candidate notification failed','conversation_closed',%s,NULL,now())
                    """,
                    (
                        sent_delivery_id,
                        phone,
                        employee_key,
                        Json({"smoke": True}),
                        failed_reminder_id,
                        phone,
                        employee_key,
                        Json({"smoke": True}),
                        closed_delivery_id,
                        phone,
                        app_key,
                        Json({"smoke": True}),
                    ),
                )
            conn.commit()

        payload = app.dashboard_prehire_notifications(context={"company_code": company})
        rows = payload.get("notifications") or []
        action_items = payload.get("action_items") or []
        kinds = {item.get("kind") for item in action_items}
        delivery_ids = {row.get("delivery_id") for row in rows}

        assert_true(sent_delivery_id not in delivery_ids, "normal sent reminder must not appear in notification center")
        assert_true(closed_delivery_id in delivery_ids, "closed WhatsApp delivery issue must appear in delivery exceptions")
        assert_true("failed_onboarding_reminders" in kinds, "failed reminders must appear as grouped action item")
        assert_true("closed_conversations" in kinds, "closed conversations must appear as grouped action item")
        assert_true(payload.get("notification_policy", {}).get("normal_reminder") == "log_only", "normal reminders must be log-only")

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS count FROM outbound_delivery_events WHERE delivery_id=%s AND message_kind=%s AND status=%s",
                    (sent_delivery_id, "onboarding_reminder", "sent"),
                )
                assert_true(int((cur.fetchone() or {}).get("count") or 0) == 1, "normal reminder must remain in activity log")

        app.notify_hr_admins = fake_notify_hr_admins
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE onboarding_items SET status='received' WHERE employee_key=%s AND item_id='civil_id'", (employee_key,))
                cur.execute("UPDATE employees SET documents_pending=1, documents_complete=1 WHERE employee_key=%s", (employee_key,))
            conn.commit()

        employee = {"employee_key": employee_key, "phone": phone, "company_code": company, "name": "Smoke Notification Employee"}
        app.notify_hr_onboarding_received(employee=employee, item_id="civil_id", account_id="default")
        assert_true(
            any("sent" in str(item.get("message", "")).lower() and "still missing" in str(item.get("message", "")).lower() for item in captures),
            "document submitted should notify HR",
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE onboarding_items SET status='received' WHERE employee_key=%s", (employee_key,))
                cur.execute("UPDATE employees SET documents_pending=0, documents_complete=2, onboarding_status=%s WHERE employee_key=%s", ("completed", employee_key))
            conn.commit()

        app.notify_hr_onboarding_completed(employee=employee, account_id="default")
        assert_true(any("complete" in str(item.get("message", "")).lower() for item in captures), "onboarding completed should notify HR")

        captures.clear()
        app.pending_onboarding_reminder_candidates = lambda limit=25, min_hours_since_last=24: [
            {"employee_key": employee_key, "phone": phone, "company_code": company, "name": "Smoke One"},
            {"employee_key": employee_key + "-2", "phone": phone + "1", "company_code": company, "name": "Smoke Two"},
        ]
        app.send_onboarding_reminder = lambda employee, account_id: {"ok": False, "send": {"error": "conversation_closed"}, "employee": employee}
        scan = app.run_onboarding_reminder_scan(account_id="default", dry_run=False, limit=2, min_hours_since_last=1)
        assert_true(len(scan.get("failure_notifications") or []) == 1, "failed reminder scan should create one grouped HR action notification")
        assert_true("2 onboarding reminders failed" in str(scan["failure_notifications"][0].get("message")), "grouped failed reminder copy should include total")

        print("notification policy live scenario checks passed")
        print("action_item_kinds=", sorted(str(kind) for kind in kinds))
        print("delivery_exception_ids_include_closed=", closed_delivery_id in delivery_ids)
        print("normal_reminder_logged_only=", sent_delivery_id not in delivery_ids)
    finally:
        app.notify_hr_admins = original_notify_hr_admins
        app.pending_onboarding_reminder_candidates = original_pending_candidates
        app.send_onboarding_reminder = original_send_onboarding_reminder
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM outbound_delivery_events WHERE delivery_id IN (%s,%s,%s)", (sent_delivery_id, failed_reminder_id, closed_delivery_id))
                cur.execute("DELETE FROM applications WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidates WHERE phone=%s", (phone,))
                cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s", (employee_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (employee_key,))
                for module in ("onboarding", "compliance"):
                    original = next((row for row in original_module_rows if row.get("module_key") == module), None)
                    if original:
                        cur.execute(
                            """
                            UPDATE company_modules
                            SET enabled=%s, settings=%s, updated_at=now()
                            WHERE company_code=%s AND module_key=%s
                            """,
                            (original.get("enabled"), Json(original.get("settings") or {}), company, module),
                        )
                    else:
                        cur.execute("DELETE FROM company_modules WHERE company_code=%s AND module_key=%s", (company, module))
            conn.commit()


if __name__ == "__main__":
    main()
