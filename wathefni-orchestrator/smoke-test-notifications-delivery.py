"""Notifications / Delivery Center smoke test (staging).

Covers two fixes made together, both in the delivery-monitoring surfaces shown
on the Notifications page ("Needs your follow-up" / "Delivery issues" /
"Reminder activity" cards, plus the compact banner on every post-hire module
page):

1. Eligibility-aware failure messages (`_humanize_delivery_failure`).
   Before: any WhatsApp-side reason code other than "no_phone" was described
   as "WhatsApp chat isn't open" with a suggestion to "ask them to message you
   on WhatsApp first" -- including `preset_no_whatsapp`, which means the
   company's OWN notification preset (or the template's channel policy) chose
   never to attempt WhatsApp for this message. That advice can never help: the
   system will never try WhatsApp for that message regardless of what the
   employee does. Same idea for email (`email:disabled` / `email:preset_blocked`
   is a config choice, not a broken send). This test proves a channel that was
   never eligible for a given message is never blamed and never produces an
   actionable suggestion referencing it -- only channels that were actually
   eligible and still failed (or are missing data) are surfaced as something
   to fix.

2. True counts + pagination for HR tasks and delivery follow-up messages.
   Before: `/dashboard/hr-tasks` capped its list at 200 with no offset (the
   "Needs your follow-up" badge showed `len(tasks)` -- a truncated page length
   -- even though the endpoint already computed a true `open_count` separately
   and just didn't return/use it consistently), and
   `/dashboard/outbound/needs-follow-up` had no true count at all, capped at
   200 with zero disclosure of whether more existed. Unlike HR tasks (which
   get resolved and cleared), that list also accumulates throttled/
   dashboard-only rows that never get "resolved," making it the most likely of
   the two to be silently truncated at real scale. This test proves both now
   report a true, page-independent total and page through the complete set
   with no duplicates or gaps.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-notifications-delivery.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY_A = "NOTIFDELIVA"  # scale subject
COMPANY_B = "NOTIFDELIVB"  # isolation control
MARKER = "temporary_notifications_delivery_smoke"

TASK_COUNT_A = 45
MESSAGE_COUNT_A = 45  # spread across needs-follow-up statuses


def _ctx(company: str) -> dict[str, Any]:
    return {
        "company_code": company,
        "permissions": ["compliance.read"],
        "access": {"role": "owner", "permissions": ["compliance.read"]},
        "actor_user_id": f"smoke-notif-{company}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"smoke-notif-{company}",
        "permission_subject_company": company,
        "actor_role": "owner",
        "hr_user": {"role": "owner", "status": "active", "company_code": company},
        "scope": None,
    }

class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"      PASS  {label}")
        for label in self.failed:
            print(f"      FAIL  {label}")
        print(f"\n    {len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute("DELETE FROM hr_tasks WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM employee_messages WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Clean any stale rows from a prior interrupted run FIRST -- `_purge`
            # also clears `company_modules`, so it must run before (not after)
            # the module-enable inserts below, or the module gate this test
            # depends on (`_hr_tasks_context`) would immediately fail.
            _purge(cur)
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Notifications Delivery {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                    "VALUES (%s,'compliance',TRUE,'smoke',now()) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                    (company,),
                )

            for i in range(TASK_COUNT_A):
                cur.execute(
                    """
                    INSERT INTO hr_tasks (company_code, employee_key, task_type, source, title, detail, status, priority)
                    VALUES (%s,%s,'delivery_failed','smoke',%s,%s,'open','normal')
                    """,
                    (COMPANY_A, f"{COMPANY_A}-emp{i}", f"Follow up {i}", MARKER),
                )
            # One resolved task -- must NOT count towards open_count/total(open).
            cur.execute(
                """
                INSERT INTO hr_tasks (company_code, employee_key, task_type, source, title, detail, status, priority)
                VALUES (%s,%s,'delivery_failed','smoke','Already done',%s,'done','normal')
                """,
                (COMPANY_A, f"{COMPANY_A}-empdone", MARKER),
            )
            # Company B: one open task, proves isolation.
            cur.execute(
                """
                INSERT INTO hr_tasks (company_code, employee_key, task_type, source, title, detail, status, priority)
                VALUES (%s,%s,'delivery_failed','smoke','B task',%s,'open','normal')
                """,
                (COMPANY_B, f"{COMPANY_B}-emp0", MARKER),
            )

            for i in range(MESSAGE_COUNT_A):
                status = od.STATUS_FAILED if i % 2 == 0 else od.STATUS_THROTTLED
                cur.execute(
                    """
                    INSERT INTO employee_messages
                        (company_code, employee_key, flow, criticality, status, last_error, attempts, created_at, updated_at)
                    VALUES (%s,%s,'shift','standard',%s,'session:no_usable_conversation_id;email:no_employee_email',1,now(),now())
                    """,
                    (COMPANY_A, f"{COMPANY_A}-msgemp{i}", status),
                )
            # A delivered (non-issue) message -- must be EXCLUDED from the needs-follow-up count.
            cur.execute(
                """
                INSERT INTO employee_messages (company_code, employee_key, flow, criticality, status, created_at, updated_at)
                VALUES (%s,%s,'shift','standard','sent_email_fallback',now(),now())
                """,
                (COMPANY_A, f"{COMPANY_A}-msgemp-ok"),
            )
            # Company B: one needs-follow-up message, proves isolation.
            cur.execute(
                """
                INSERT INTO employee_messages
                    (company_code, employee_key, flow, criticality, status, last_error, attempts, created_at, updated_at)
                VALUES (%s,%s,'shift','standard','failed','session:no_usable_conversation_id',1,now(),now())
                """,
                (COMPANY_B, f"{COMPANY_B}-msgemp0"),
            )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def _page_task_ids(company: str, *, limit: int) -> tuple[list[str], int]:
    seen: list[str] = []
    offset = 0
    total = 0
    for _ in range(1000):
        page = app.dashboard_hr_tasks(status="open", limit=limit, offset=offset, context=_ctx(company))
        total = page["total"]
        rows = page["tasks"]
        seen.extend(str(t["task_id"]) for t in rows)
        if not rows or (offset + len(rows)) >= total:
            break
        offset += len(rows)
    return seen, total


def _page_message_ids(company: str, *, limit: int) -> tuple[list[str], int]:
    seen: list[str] = []
    offset = 0
    total = 0
    for _ in range(1000):
        page = app.dashboard_outbound_needs_follow_up(limit=limit, offset=offset, context=_ctx(company))
        total = page["total"]
        rows = page["messages"]
        seen.extend(str(m["message_id"]) for m in rows)
        if not rows or (offset + len(rows)) >= total:
            break
        offset += len(rows)
    return seen, total


def run_humanize_checks(checks: Checks) -> None:
    # A channel that was NEVER eligible for this message (company preset / template
    # policy chose no WhatsApp) must never be described as "not open", and must
    # never be the subject of a suggested action -- even when nothing else worked.
    reason, action = app._humanize_delivery_failure(
        last_error="session:preset_no_whatsapp;template:preset_no_whatsapp;email:no_employee_email",
        employee_name="Sara",
        has_email=False,
    )
    checks.check("preset_no_whatsapp + no email: never claims the WhatsApp chat isn't open", lambda: "chat isn't open" not in reason.lower())
    checks.check("preset_no_whatsapp + no email: never suggests messaging on WhatsApp", lambda: "ask them to message" not in action.lower())
    checks.check("preset_no_whatsapp + no email: still tells HR to add an email", lambda: "email" in action.lower())

    # Same combination but email is globally disabled too -- nothing eligible
    # ever failed; must say so plainly instead of blaming either channel.
    reason2, action2 = app._humanize_delivery_failure(
        last_error="session:preset_no_whatsapp;template:preset_no_whatsapp;email:disabled",
        employee_name="Omar",
        has_email=True,
    )
    checks.check("no eligible channel at all: plain 'no channel enabled' message", lambda: "no channel enabled" in reason2.lower())
    checks.check("no eligible channel at all: never mentions WhatsApp in the suggestion", lambda: "whatsapp" not in action2.lower())

    # A genuine WhatsApp technical failure (eligible, attempted, failed) must
    # still read as an actionable WhatsApp problem -- the fix must not have
    # over-corrected into hiding real issues.
    reason3, action3 = app._humanize_delivery_failure(
        last_error="session:no_usable_conversation_id;template:whatsapp_failed;email:no_employee_email",
        employee_name="Fatima",
        has_email=False,
    )
    checks.check("real WhatsApp failure still described as a WhatsApp problem", lambda: "whatsapp" in reason3.lower())
    checks.check("real WhatsApp failure still suggests messaging on WhatsApp", lambda: "whatsapp" in action3.lower() and "message" in action3.lower())

    # No phone at all is a real, actionable data gap regardless of preset.
    reason4, action4 = app._humanize_delivery_failure(
        last_error="session:no_phone;email:no_employee_email",
        employee_name="Yousef",
        has_email=False,
    )
    checks.check("no phone + no email: asks to add contact details", lambda: "number" in reason4.lower() and "email" in reason4.lower())

    # Employee opt-out stays a calm, non-error message regardless of preset codes.
    reason5, _ = app._humanize_delivery_failure(
        last_error="session:suppressed_opt_out;template:suppressed_opt_out",
        employee_name="Noor",
        has_email=True,
    )
    checks.check("employee opt-out framed as their choice, not a failure", lambda: "opted out" in reason5.lower())


def run_pagination_checks(checks: Checks) -> None:
    ctx_a = _ctx(COMPANY_A)
    ctx_b = _ctx(COMPANY_B)

    # 1) HR tasks: badge-facing total is the true open count, not a page length.
    page1 = app.dashboard_hr_tasks(status="open", limit=20, offset=0, context=ctx_a)
    checks.check("hr-tasks page caps at limit=20", lambda: len(page1["tasks"]) == 20)
    checks.check("hr-tasks open_count == true open total (not page size)", lambda: page1["open_count"] == TASK_COUNT_A)
    checks.check("hr-tasks total == true open total", lambda: page1["total"] == TASK_COUNT_A)
    checks.check("hr-tasks total != len(page) (proves old truncation bug is gone)", lambda: page1["total"] != len(page1["tasks"]))

    seen, total = _page_task_ids(COMPANY_A, limit=13)
    checks.check("hr-tasks paging total == true open total", lambda: total == TASK_COUNT_A)
    checks.check("hr-tasks paging visits every open task once, no dup/gaps", lambda: len(seen) == TASK_COUNT_A and len(set(seen)) == TASK_COUNT_A)

    # 2) needs-follow-up: true total independent of page size.
    total_messages_a = MESSAGE_COUNT_A  # excludes the one delivered/'sent_email_fallback' row
    msg_page1 = app.dashboard_outbound_needs_follow_up(limit=15, offset=0, context=ctx_a)
    checks.check("needs-follow-up page caps at limit=15", lambda: len(msg_page1["messages"]) == 15)
    checks.check("needs-follow-up total == true count (not page size)", lambda: msg_page1["total"] == total_messages_a)
    checks.check("needs-follow-up total != len(page) (proves old truncation bug is gone)", lambda: msg_page1["total"] != len(msg_page1["messages"]))

    seen_msgs, total_msgs = _page_message_ids(COMPANY_A, limit=11)
    checks.check("needs-follow-up paging total == true count", lambda: total_msgs == total_messages_a)
    checks.check("needs-follow-up paging visits every message once, no dup/gaps", lambda: len(seen_msgs) == total_messages_a and len(set(seen_msgs)) == total_messages_a)

    # 3) Tenant isolation.
    page_b = app.dashboard_hr_tasks(status="open", limit=50, offset=0, context=ctx_b)
    checks.check("company B sees only its own open task", lambda: page_b["total"] == 1 and page_b["open_count"] == 1)
    msg_b = app.dashboard_outbound_needs_follow_up(limit=50, offset=0, context=ctx_b)
    checks.check("company B sees only its own needs-follow-up message", lambda: msg_b["total"] == 1)
    a_ids = {t["task_id"] for t in app.dashboard_hr_tasks(status="open", limit=200, offset=0, context=ctx_a)["tasks"]}
    b_ids = {t["task_id"] for t in page_b["tasks"]}
    checks.check("A and B hr-tasks never overlap", lambda: a_ids.isdisjoint(b_ids))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"notifications delivery smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_humanize_checks(checks)
        run_pagination_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    NOTIFICATIONS DELIVERY: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
