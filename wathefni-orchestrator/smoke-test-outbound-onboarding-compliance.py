"""Phase D: onboarding + compliance -> shared outbound delivery layer (staging).

Proves that the onboarding kickoff, onboarding reminder, and compliance reminder
route through deliver_to_employee when their flow is enabled
(WATHEFNI_OUTBOUND_FLOWS includes onboarding / compliance) — recording an
employee_messages row with the right template, honoring the compliance
metadata-only body policy, and (under dry-run) marking delivered — while with the
flows OFF the legacy direct-send path is used and no employee_messages row is
created.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_DELIVERY_MODE=dry_run \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-outbound-onboarding-compliance.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY = "OUTBOUNDOBCOMPCO"
MARKER = "temporary_outbound_ob_comp_harness"

EMP = "outbound-obcomp-emp"
PHONE = "96550000000601"
EMAIL = "outbound-obcomp-emp@example.com"


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
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _flows(value: str | None) -> None:
    if value:
        app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
        app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = value
    else:
        app.os.environ.pop("WATHEFNI_OUTBOUND_LAYER", None)
        app.os.environ.pop("WATHEFNI_OUTBOUND_FLOWS", None)


def _employee() -> dict[str, Any]:
    return {"employee_key": EMP, "company_code": COMPANY, "phone": PHONE, "email": EMAIL, "name": "Omar Onboard"}


def _messages(template_key: str) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM employee_messages WHERE company_code=%s AND template_key=%s ORDER BY created_at",
                (COMPANY, template_key),
            )
            return [dict(r) for r in cur.fetchall()]


def _clear_messages() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employee_messages WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM hr_tasks WHERE company_code=%s", (COMPANY,))
        conn.commit()


def _insert_columns(cur: Any, table: str, desired: dict[str, Any]) -> None:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    columns = {row["column_name"] for row in cur.fetchall()}
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})", [desired[c] for c in cols])


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in ("employee_messages", "hr_tasks", "compliance_documents", "employees"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM outbound_delivery_events WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def setup() -> None:
    app.os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                (COMPANY, "Outbound OB/Compliance Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            _insert_columns(cur, "employees", {
                "company_code": COMPANY, "phone": PHONE, "name": "Omar Onboard", "email": EMAIL,
                "employee_key": EMP, "status": "active", "onboarding_status": "in_progress",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            })
            # An outstanding compliance doc: no expiry + status 'missing' classifies
            # into the "missing" bucket, so the reminder has something to send.
            _insert_columns(cur, "compliance_documents", {
                "company_code": COMPANY, "employee_key": EMP, "document_type": "civil_id",
                "label": "Civil ID", "status": "missing", "metadata": Json({"smoke": MARKER}),
            })
        conn.commit()


def teardown() -> None:
    _purge()
    _flows(None)


def run_checks(checks: Checks) -> None:
    token = app.set_active_company_code(COMPANY)
    try:
        emp = _employee()

        # --- Flows ON --------------------------------------------------------
        _flows("onboarding,compliance")

        kickoff = app.notify_employee_onboarding_started(emp, None)
        checks.check("onboarding kickoff via layer", lambda: kickoff.get("via") == "outbound_layer")
        checks.check("kickoff delivered under dry-run", lambda: kickoff.get("delivery_status") == "delivered_whatsapp")
        welcome = _messages("employee_onboarding_welcome")
        checks.check("kickoff created one welcome message", lambda: len(welcome) == 1)
        checks.check("kickoff message flow is onboarding", lambda: welcome and welcome[0]["flow"] == "onboarding")

        reminder = app.send_onboarding_reminder(emp, None)
        checks.check("onboarding reminder via layer", lambda: reminder.get("via") == "outbound_layer")
        checks.check("reminder keeps missing_documents field", lambda: "missing_documents" in reminder)
        rem_rows = _messages("onboarding_reminder")
        checks.check("reminder created one onboarding_reminder message", lambda: len(rem_rows) == 1)

        comp = app.send_compliance_reminder(emp, None, None)
        checks.check("compliance reminder via layer", lambda: comp.get("via") == "outbound_layer")
        checks.check("compliance delivered under dry-run", lambda: comp.get("delivery_status") == "delivered_whatsapp")
        checks.check("compliance keeps documents field", lambda: bool(comp.get("documents")))
        checks.check("compliance bumps reminder bookkeeping when reached", lambda: (comp.get("reminder_update") or {}).get("updated", 0) >= 1)
        comp_rows = _messages("compliance_document_required")
        checks.check("compliance created one message", lambda: len(comp_rows) == 1)
        checks.check("compliance message flow is compliance", lambda: comp_rows and comp_rows[0]["flow"] == "compliance")
        # metadata-only: the stored preview is a generic label, never the body text.
        checks.check("compliance stored body is metadata-only generic", lambda: comp_rows and comp_rows[0]["body_preview"] == "Document required")
        checks.check("compliance stored no raw body / ciphertext", lambda: comp_rows and comp_rows[0]["body_encrypted"] is None and not (comp_rows[0]["body_preview"] or "").lower().startswith("hi "))

        # --- Flows OFF: legacy direct send, no employee_messages rows --------
        _clear_messages()
        _flows(None)
        kickoff_off = app.notify_employee_onboarding_started(emp, None)
        comp_off = app.send_compliance_reminder(emp, None, None)
        checks.check("flag OFF: kickoff not via layer", lambda: kickoff_off.get("via") != "outbound_layer")
        checks.check("flag OFF: compliance not via layer", lambda: comp_off.get("via") != "outbound_layer")
        checks.check("flag OFF: no employee_message rows created", lambda: len(_messages("employee_onboarding_welcome")) + len(_messages("compliance_document_required")) == 0)
        checks.check("flag OFF: compliance still succeeds (legacy)", lambda: comp_off.get("ok") is True)
    finally:
        app.reset_active_company_code(token)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"outbound onboarding/compliance harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nOUTBOUND ONBOARDING/COMPLIANCE HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nOUTBOUND ONBOARDING/COMPLIANCE HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
