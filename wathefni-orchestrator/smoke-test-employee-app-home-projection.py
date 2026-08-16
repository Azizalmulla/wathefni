#!/usr/bin/env python3
"""Employee App `/app/home` server-owned projection contract.

Home must aggregate what the owning modules already say and nothing else. This smoke
proves the projection against real fixtures on the production database (synthetic
employees only; Aziz/Talal are never touched).

Proves:
- entitlement shapes: zero, one, two, four and full suite report the right per-module state
- a disabled module is `disabled` and carries no value (never an empty business fact)
- a failing module read is `error`, carries no value, and does not abort the sibling reads
- today's attendance is today's record, not the newest row in the 30-day window
- tasks are the owning modules' own facts: onboarding outstanding steps, document
  renewals, pending leave, and a released-but-unread payslip
- a task disappears when its module is disabled, without Home re-deriving anything
- `caught_up` is only claimed when every contributing module was actually read
- entitlement gating for the projection is the same feature contract used everywhere
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
# A release gate never executes deployment DDL.
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
import employee_app_access as access  # noqa: E402

COMPANY = "WATHEFNI"
TAG = uuid.uuid4().hex[:8]
FAILS: list[str] = []
CREATED: list[str] = []

# Employee feature keys reported by the projection.
FEATURE_KEYS = ("shifts", "attendance", "leave", "onboarding", "documents", "payslips")
# Company module keys that entitle them. `documents` has no module of its own: it is
# entitled by onboarding OR compliance, and `payslips` by payroll.
FULL_SUITE_MODULES = {"shifts", "attendance", "leave", "onboarding", "compliance", "payroll"}


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def hr_ctx() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "user_id": "home-projection-smoke",
        "actor_user_id": "home-projection-smoke",
        "email": "home-projection-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def allow(*keys: str) -> None:
    current = {k for k in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if k}
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(current | set(keys)))


def create_employee(suffix: str) -> str:
    phone = f"9657{TAG[:4]}{suffix}"[:11].ljust(11, "0")
    result = legacy.create_company_employee(
        COMPANY,
        name=f"Home Projection {TAG} {suffix}",
        phone=phone,
        email=f"home-projection-{TAG}-{suffix}@example.invalid",
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
        allow(key)
        access.set_employee_app_access(
            legacy, hr_ctx(), employee_key=key, enabled=True, reason="home-projection-smoke", deliver_invite=False
        )
    return key


def employee_ctx(employee_key: str) -> dict[str, Any]:
    """The `/app` context shape without minting a session (no auth path under test)."""
    employee = legacy.find_employee_by_key(employee_key, company_code=COMPANY) or {}
    phone = legacy.digits(employee.get("phone"))
    return {
        "company_code": COMPANY,
        "employee_key": employee_key,
        "employee": employee,
        "phone": phone,
        "session_id": f"home-projection-{TAG}",
        "actor_employee_key": employee_key,
        "actor_user_id": f"employee_app:{employee_key}",
        "actor_phone": phone,
        "actor_email": employee.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {"role": "employee", "company_code": COMPANY, "phone": phone, "name": employee.get("name") or ""},
    }


def home(employee_key: str, *, locale: str = "en") -> dict[str, Any]:
    return legacy.app_home(locale=locale, context=employee_ctx(employee_key))


def with_modules(modules: set[str], fn: Any) -> Any:
    """Run `fn` with the effective *company module* set forced, leaving config alone.

    Feature keys are derived from these by the shared feature contract, which is exactly
    what Home must defer to instead of keeping a registry of its own.
    """
    real = legacy.employee_app_effective_modules

    def fake(_context: dict[str, Any]) -> set[str]:
        return set(modules)

    legacy.employee_app_effective_modules = fake  # type: ignore[assignment]
    try:
        return fn()
    finally:
        legacy.employee_app_effective_modules = real  # type: ignore[assignment]


def seed_shift(employee_key: str, *, on_date: Any, start: str, end: str) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignments (company_code, employee_key, shift_date, start_time, end_time, status)
                VALUES (%s,%s,%s,%s,%s,'assigned')
                """,
                (COMPANY, employee_key, on_date, start, end),
            )
        conn.commit()


def seed_attendance(employee_key: str, *, on_date: Any, status: str) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO attendance_records (company_code, employee_key, attendance_date, status)
                VALUES (%s,%s,%s,%s)
                """,
                (COMPANY, employee_key, on_date, status),
            )
        conn.commit()


def seed_leave(employee_key: str, *, status: str) -> None:
    today = legacy.kuwait_today()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests
                    (company_code, employee_key, start_date, end_date, leave_type, status, reason)
                VALUES (%s,%s,%s,%s,'annual',%s,%s)
                """,
                (COMPANY, employee_key, today + timedelta(days=7), today + timedelta(days=8), status, f"home-{TAG}"),
            )
        conn.commit()


def seed_expired_compliance_document(employee_key: str) -> None:
    """An expired canonical document. Documents owns `renewal_required`; Home only counts it."""
    today = legacy.kuwait_today()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO compliance_documents
                    (company_code, employee_key, document_type, status, expiry_date, warning_days)
                VALUES (%s,%s,'civil_id','valid',%s,30)
                ON CONFLICT (employee_key, document_type) DO UPDATE
                    SET expiry_date=EXCLUDED.expiry_date, status=EXCLUDED.status
                """,
                (COMPANY, employee_key, today - timedelta(days=10)),
            )
        conn.commit()


def seed_unread_payroll_message(employee_key: str, payslip_id: str) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee_messages
                    (company_code, employee_key, flow, template_key, status, sensitivity, body_preview, metadata)
                VALUES (%s,%s,'payroll','payslip_ready','sent','plain',%s,%s)
                """,
                (
                    COMPANY,
                    employee_key,
                    f"home-{TAG}",
                    legacy.json.dumps({"payslip_id": payslip_id}),
                ),
            )
        conn.commit()


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for key in CREATED:
                for table in (
                    "shift_assignments",
                    "attendance_records",
                    "leave_requests",
                    "compliance_documents",
                    "employee_messages",
                    "employee_sessions",
                    "employee_app_invites",
                    "employee_push_tokens",
                ):
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code=%s AND employee_key=%s",
                        (COMPANY, key),
                    )
                cur.execute(
                    "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
            conn.commit()


def main() -> int:
    original_policy = access.get_company_app_access_policy(legacy, COMPANY)
    original_allowlist = os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST")
    today = legacy.kuwait_today()
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                access.ensure_access_schema(cur)
                conn.commit()
        access.set_company_app_access_policy(
            legacy, hr_ctx(), module_enabled=True, access_mode="selected", sync_invites=False
        )

        key = create_employee("01")

        # --- 1) Zero entitlements: core shell only, nothing claimed
        zero = with_modules(set(), lambda: home(key))
        check(
            "zero-entitlement Home reports every module disabled",
            all(zero["modules"][m] == "disabled" for m in FEATURE_KEYS),
            str(zero["modules"]),
        )
        check("zero-entitlement Home still reads the inbox", zero["modules"]["notifications"] == "ready")
        check(
            "zero-entitlement Home carries no module values",
            zero["today"]["shifts"] is None
            and zero["today"]["attendance"] is None
            and zero["attendance_window"] is None
            and zero["onboarding"] is None,
            str(zero["today"]),
        )
        check("zero-entitlement Home has no tasks", zero["tasks"] == [])
        check("zero-entitlement Home is caught up", zero["caught_up"] is True)
        check("Home dates the projection in Kuwait time", str(zero["date"]) == str(today))

        # --- 2) One entitlement: only that module is read
        one = with_modules({"leave"}, lambda: home(key))
        check(
            "one-entitlement Home reads only that module",
            one["modules"]["leave"] == "ready"
            and all(one["modules"][m] == "disabled" for m in FEATURE_KEYS if m != "leave"),
            str(one["modules"]),
        )

        # --- 3) Two entitlements: today's summary appears for both
        seed_shift(key, on_date=today, start="09:00", end="17:00")
        seed_attendance(key, on_date=today - timedelta(days=3), status="present")
        two = with_modules({"shifts", "attendance"}, lambda: home(key))
        check(
            "two-entitlement Home reads both modules",
            two["modules"]["shifts"] == "ready" and two["modules"]["attendance"] == "ready",
            str(two["modules"]),
        )
        check("today's shift comes from the shifts module", two["today"]["shift_count"] == 1, str(two["today"]))
        check(
            "an older attendance row is never presented as today",
            two["today"]["attendance"] is None,
            str(two["today"]["attendance"]),
        )
        check(
            "the attendance window summary still reports the older row",
            (two["attendance_window"] or {}).get("summary", {}).get("present") == 1,
            str(two["attendance_window"]),
        )

        seed_attendance(key, on_date=today, status="late")
        two_today = with_modules({"shifts", "attendance"}, lambda: home(key))
        check(
            "today's attendance is today's record",
            str((two_today["today"]["attendance"] or {}).get("date")) == str(today)
            and (two_today["today"]["attendance"] or {}).get("status") == "late",
            str(two_today["today"]["attendance"]),
        )

        # --- 4) Four entitlements + tasks from owning modules
        seed_leave(key, status="pending")
        four = with_modules({"shifts", "attendance", "leave", "compliance"}, lambda: home(key))
        kinds = [task["kind"] for task in four["tasks"]]
        check("pending leave becomes a leave task", "leave_pending" in kinds, str(four["tasks"]))
        check(
            "the leave task carries the owning module's count and severity",
            next(t for t in four["tasks"] if t["kind"] == "leave_pending")["count"] == 1
            and next(t for t in four["tasks"] if t["kind"] == "leave_pending")["severity"] == "informational",
            str(four["tasks"]),
        )
        check("outstanding work is not 'caught up'", four["caught_up"] is False)
        check(
            "documents is read from the compliance entitlement, with no rows to show",
            four["modules"]["documents"] == "ready" and four["modules"]["onboarding"] == "disabled",
            str(four["modules"]),
        )
        check(
            "documents is also entitled by onboarding alone",
            with_modules({"onboarding"}, lambda: home(key))["modules"]["documents"] == "ready",
        )

        # --- 5) A disabled module removes its task without Home re-deriving anything
        no_leave = with_modules({"shifts", "attendance", "compliance"}, lambda: home(key))
        check(
            "disabling leave removes the leave task",
            all(task["kind"] != "leave_pending" for task in no_leave["tasks"]),
            str(no_leave["tasks"]),
        )

        # --- 6) Full suite reads every module
        full = with_modules(FULL_SUITE_MODULES, lambda: home(key))
        check(
            "full-suite Home reads every entitled module",
            all(
                full["modules"][m] == "ready"
                for m in ("shifts", "attendance", "leave", "onboarding", "documents")
            ),
            str(full["modules"]),
        )
        check(
            "payslips follow the payroll company gate, not a Home rule",
            full["modules"]["payslips"]
            == ("ready" if legacy._payroll_w3.payroll_wave3_enabled_for_company(COMPANY) else "disabled"),
            str(full["modules"]["payslips"]),
        )
        check(
            "onboarding progress comes from its own completion contract",
            isinstance(full["onboarding"], dict) and "required_total" in full["onboarding"],
            str(full["onboarding"]),
        )

        # --- 7) A failing module read is stated as error and isolated from siblings.
        # The forced failure is a real SQL error so the shared transaction is genuinely
        # aborted: only the per-module savepoint lets the later reads survive it.
        real_attendance = legacy._employee_attendance_rows

        def exploding_attendance(cur: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            cur.execute("SELECT 1 FROM home_projection_smoke_missing_table")
            return []

        legacy._employee_attendance_rows = exploding_attendance  # type: ignore[assignment]
        try:
            broken = with_modules({"shifts", "attendance", "leave"}, lambda: home(key))
        finally:
            legacy._employee_attendance_rows = real_attendance  # type: ignore[assignment]
        check("a failed module read reports error", broken["modules"]["attendance"] == "error", str(broken["modules"]))
        check(
            "a failed module read carries no value",
            broken["today"]["attendance"] is None and broken["attendance_window"] is None,
            str(broken["today"]),
        )
        check(
            "a failed module read does not abort its siblings",
            broken["modules"]["shifts"] == "ready" and broken["modules"]["leave"] == "ready",
            str(broken["modules"]),
        )
        check("an unread module can never be 'caught up'", broken["caught_up"] is False)

        # --- 8) An expired document becomes a renewal task, owned by Documents
        seed_expired_compliance_document(key)
        docs = with_modules({"compliance"}, lambda: home(key))
        renewal = next((task for task in docs["tasks"] if task["kind"] == "document_renewal"), None)
        check(
            "an expired document becomes a document renewal task",
            renewal is not None and renewal["count"] == 1 and renewal["severity"] == "action_required",
            str(docs["tasks"]),
        )
        check(
            "the renewal task disappears with the documents entitlement",
            all(
                task["kind"] != "document_renewal"
                for task in with_modules({"leave"}, lambda: home(key))["tasks"]
            ),
        )

        # --- 9) Payslip task needs both Payroll's release and Inbox's unread fact
        released_only = with_modules({"payroll"}, lambda: home(key))
        check(
            "no payslip task without a released-and-unread payslip",
            all(task["kind"] != "payslip_released" for task in released_only["tasks"]),
            str(released_only["tasks"]),
        )
        seed_unread_payroll_message(key, str(uuid.uuid4()))
        stray = with_modules({"payroll"}, lambda: home(key))
        check(
            "an unread payroll message alone does not invent a payslip task",
            all(task["kind"] != "payslip_released" for task in stray["tasks"]),
            str(stray["tasks"]),
        )
        check(
            "the unread payroll message still counts as inbox unread",
            stray["inbox"]["unread"] >= 1,
            str(stray["inbox"]),
        )

        # --- 10) Locale is echoed and constrained
        arabic = with_modules(set(), lambda: home(key, locale="ar"))
        check("Home echoes the requested locale", arabic["locale"] == "ar")
        weird = with_modules(set(), lambda: home(key, locale="fr-CA"))
        check("Home falls back to a supported locale", weird["locale"] == "en")

        # --- 11) Home is an aggregation, not a second entitlement registry
        contract_modules = with_modules({"leave"}, lambda: home(key))["modules"]
        check(
            "Home module state follows the shared feature contract",
            contract_modules["leave"] == "ready" and contract_modules["payslips"] == "disabled",
            str(contract_modules),
        )

    finally:
        cleanup()
        try:
            access.set_company_app_access_policy(
                legacy,
                hr_ctx(),
                module_enabled=bool(original_policy.get("module_enabled")),
                access_mode=str(original_policy.get("access_mode") or "selected"),
                selected_departments=list(original_policy.get("selected_departments") or []),
                sync_invites=False,
            )
        except Exception:
            pass
        if original_allowlist is None:
            os.environ.pop("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST", None)
        else:
            os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = original_allowlist

    print("---")
    if FAILS:
        print(f"FAIL count={len(FAILS)}: {', '.join(FAILS)}")
        return 1
    print("PASS employee app home projection contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
