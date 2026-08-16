"""Leave Wave 1 — authority & safety hardening (local/staging).

Does NOT enable legal balance enforcement (enforced remains false).
Does NOT redesign UI or change frozen E360/Onboarding/Attendance modules beyond
leave-side status compatibility for decline_open_leave reverse → requested.

Wave 1B production: LEAVE_AUTHORITY=on + SYNTHETIC_ONLY=on so lifecycle/stale
gates apply only to synthetic markers; self-approval ban remains global.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

LEAVE_AUTHORITY_SCHEMA_VERSION = "1.0.0"

_ON_VALUES = {"1", "true", "yes", "on"}

# Distinct from Attendance (965524), Onboarding (965523), Lifecycle (965522).
DEFAULT_LEAVE_SYNTHETIC_KEY_MARKERS = ("LVW1B", "LVW1B-SYNTH|")
DEFAULT_LEAVE_SYNTHETIC_PHONE_PREFIXES = ("965525",)
FOUR_REAL_LEAVE_KEYS = frozenset(
    {
        "WATHEFNI-96550252254",
        "WATHEFNI-96566363363",
        "WATHEFNI-96597727743",
        "WATHEFNI-96599411617",
    }
)

# --- Canonical catalogue -------------------------------------------------------

CANONICAL_LEAVE_TYPES: tuple[str, ...] = (
    "annual",
    "sick",
    "unpaid",  # catalogue only in Wave 1 — no unpaid workflow
    "other",
)

# Legacy / free-text → canonical. History rows keep stored leave_type; runtime
# uses canonicalize_leave_type() for ledger + new writes.
LEAVE_TYPE_ALIASES: dict[str, str] = {
    "annual": "annual",
    "annual_leave": "annual",
    "vacation": "annual",
    "holiday": "annual",
    "time_off": "annual",
    "timeoff": "annual",
    "personal": "annual",
    "pto": "annual",
    "sick": "sick",
    "sick_leave": "sick",
    "medical": "sick",
    "ill": "sick",
    "unpaid": "unpaid",
    "unpaid_leave": "unpaid",
    "other": "other",
}

# Primary request state machine (Wave 1)
LEAVE_PRIMARY_STATUSES: frozenset[str] = frozenset(
    {
        "requested",
        "approved",
        "rejected",
        "cancelled",
        "expired_stale",
        "needs_review",
        "declined_lifecycle",
    }
)

LEAVE_DECIDABLE_STATUSES: frozenset[str] = frozenset({"requested", "needs_review"})
LEAVE_CANCELABLE_STATUSES: frozenset[str] = frozenset({"requested", "approved", "needs_review"})
LEAVE_HISTORY_STATUSES_W1: frozenset[str] = frozenset(
    {
        "requested",
        "approved",
        "rejected",
        "cancelled",
        "expired_stale",
        "needs_review",
        "declined_lifecycle",
    }
)

# Lifecycle eligibility labels (resolved, not necessarily hub employment_status)
LIFECYCLE_ELIGIBILITY_LABELS: frozenset[str] = frozenset(
    {
        "active",
        "future_start",
        "notice_period",
        "suspended",
        "terminated",
        "left",
        "unknown",
    }
)

DEFAULT_LIFECYCLE_POLICY: dict[str, Any] = {
    "block_terminated": True,
    "block_suspended": True,
    "block_future_start": True,
    "block_notice_period": True,
    "stale_pending_action": "expire",  # expire | needs_review
}

SCHEMA_SQL = """
ALTER TABLE leave_requests
  ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS leave_authority_settings (
  company_code text PRIMARY KEY,
  block_terminated boolean NOT NULL DEFAULT true,
  block_suspended boolean NOT NULL DEFAULT true,
  block_future_start boolean NOT NULL DEFAULT true,
  block_notice_period boolean NOT NULL DEFAULT true,
  stale_pending_action text NOT NULL DEFAULT 'expire',
  balances_enforced boolean NOT NULL DEFAULT false,
  legal_reviewed boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT leave_authority_stale_action_chk
    CHECK (stale_pending_action IN ('expire', 'needs_review'))
);

CREATE TABLE IF NOT EXISTS leave_type_catalogue (
  leave_type text PRIMARY KEY,
  display_en text NOT NULL,
  display_ar text,
  maps_from text[] NOT NULL DEFAULT '{}'::text[],
  ledger_eligible boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO leave_type_catalogue (leave_type, display_en, display_ar, maps_from, ledger_eligible)
VALUES
  ('annual', 'Annual leave', 'إجازة سنوية',
   ARRAY['vacation','holiday','time_off','timeoff','personal','pto','annual_leave'], true),
  ('sick', 'Sick leave', 'إجازة مرضية',
   ARRAY['medical','ill','sick_leave'], true),
  ('unpaid', 'Unpaid leave', 'إجازة بدون راتب',
   ARRAY['unpaid_leave'], false),
  ('other', 'Other leave', 'إجازة أخرى',
   ARRAY[]::text[], false)
ON CONFLICT (leave_type) DO NOTHING;
"""

# P1 ledger types (unchanged observe-only set, now aligned to canonical)
LEAVE_LEDGER_TYPES: frozenset[str] = frozenset({"annual", "sick"})


def leave_authority_enabled() -> bool:
    """Wave 1 authority features. Production requires explicit ON; non-prod defaults ON."""
    raw = os.environ.get("WATHEFNI_LEAVE_AUTHORITY")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON_VALUES


def leave_authority_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_LEAVE_AUTHORITY_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def leave_authority_enabled_for_company(company_code: str | None) -> bool:
    if not leave_authority_enabled():
        return False
    allowed = leave_authority_companies()
    if not allowed:
        return True
    return str(company_code or "").strip().upper() in allowed


def leave_authority_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True  # fail closed in production
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON_VALUES


def leave_authority_synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_LEAVE_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_LEAVE_SYNTHETIC_KEY_MARKERS


def leave_authority_synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_LEAVE_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_LEAVE_SYNTHETIC_PHONE_PREFIXES


def is_leave_synthetic_employee(
    employee: dict[str, Any] | None = None,
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> bool:
    key = str((employee or {}).get("employee_key") or employee_key or "").strip()
    phone_d = digits_phone((employee or {}).get("phone") or (employee or {}).get("employee_phone") or phone)
    nm = str((employee or {}).get("name") or name or "")
    if key in FOUR_REAL_LEAVE_KEYS:
        return False
    if phone_d in {digits_phone(k.split("-")[-1]) for k in FOUR_REAL_LEAVE_KEYS}:
        return False
    for marker in leave_authority_synthetic_key_markers():
        if marker and (marker in key or marker in nm):
            return True
    for prefix in leave_authority_synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def leave_authority_applies_to(
    company_code: str | None,
    employee: dict[str, Any] | None = None,
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> bool:
    """True when lifecycle/stale Wave 1 gates should run for this subject."""
    if not leave_authority_enabled_for_company(company_code):
        return False
    if not leave_authority_synthetic_only():
        return True
    return is_leave_synthetic_employee(
        employee, employee_key=employee_key, phone=phone, name=name
    )


def canonicalize_leave_type(raw: str | None) -> str:
    key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return "annual"
    if key in LEAVE_TYPE_ALIASES:
        return LEAVE_TYPE_ALIASES[key]
    if key in CANONICAL_LEAVE_TYPES:
        return key
    return "other"


def ensure_leave_authority_wave1_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def seed_company_leave_authority_settings(cur: Any, company_code: str) -> None:
    company = (company_code or "").upper()
    if not company:
        return
    cur.execute(
        """
        INSERT INTO leave_authority_settings (company_code)
        VALUES (%s)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def get_leave_authority_settings(cur: Any, company_code: str) -> dict[str, Any]:
    company = (company_code or "").upper()
    seed_company_leave_authority_settings(cur, company)
    cur.execute("SELECT * FROM leave_authority_settings WHERE company_code=%s LIMIT 1", (company,))
    row = cur.fetchone()
    if not row:
        return {"company_code": company, **DEFAULT_LIFECYCLE_POLICY, "balances_enforced": False, "legal_reviewed": False}
    d = dict(row)
    return {
        "company_code": company,
        "block_terminated": bool(d.get("block_terminated", True)),
        "block_suspended": bool(d.get("block_suspended", True)),
        "block_future_start": bool(d.get("block_future_start", True)),
        "block_notice_period": bool(d.get("block_notice_period", True)),
        "stale_pending_action": str(d.get("stale_pending_action") or "expire"),
        # Wave 1 hard rule: never binding
        "balances_enforced": False,
        "legal_reviewed": False,
    }


def honesty_balance_flags(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "balances_enforced": False,
        "legal_reviewed": False,
        "balances_binding": False,
        "observe_only": True,
    }


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def actor_is_leave_subject(leave: dict[str, Any] | None, actor_phone: str | None) -> bool:
    if not leave:
        return False
    actor = digits_phone(actor_phone)
    if not actor:
        return False
    subject = digits_phone(leave.get("employee_phone"))
    return bool(subject) and actor == subject


def self_decision_denied(
    *,
    leave: dict[str, Any] | None,
    actor_phone: str | None,
    action: str,
    allow_self_cancel: bool = False,
) -> dict[str, Any] | None:
    """Hard-ban self approve/reject. Self-cancel of own leave is allowed when allow_self_cancel."""
    act = str(action or "").strip().lower()
    if not actor_is_leave_subject(leave, actor_phone):
        return None
    if act == "cancel" and allow_self_cancel:
        return None
    return {
        "ok": False,
        "error": "self_approval_forbidden",
        "message": "You cannot approve, reject, or decide your own leave request.",
        "action": act,
    }


def resolve_employee_lifecycle_label(
    cur: Any,
    *,
    company_code: str,
    employee: dict[str, Any] | None,
    as_of: date | None = None,
) -> str:
    """Map hub + employment lifecycle into an eligibility label."""
    today = as_of or date.today()
    if not employee:
        return "unknown"
    company = (company_code or employee.get("company_code") or "").upper()
    key = str(employee.get("employee_key") or "")
    hub = str(employee.get("employment_status") or "").strip().lower()
    if hub in {"left", "terminated"}:
        return "terminated"

    life = ""
    if key and company:
        try:
            cur.execute(
                """
                SELECT e.lifecycle_state, e.start_date
                FROM employee_employments e
                LEFT JOIN employee_key_authority_map m
                  ON m.company_code=e.company_code AND m.employment_id=e.employment_id AND m.mapping_status='active'
                WHERE e.company_code=%s
                  AND (e.legacy_employee_key=%s OR m.employee_key=%s)
                ORDER BY e.updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (company, key, key),
            )
            row = cur.fetchone()
            if row:
                life = str(dict(row).get("lifecycle_state") or "").strip().lower()
                start = dict(row).get("start_date")
                if life in {"terminated"}:
                    return "terminated"
                if life in {"suspended"}:
                    return "suspended"
                if life in {"notice_period", "notice"}:
                    return "notice_period"
                if life in {"pending_start"}:
                    return "future_start"
                if start:
                    sd = start if isinstance(start, date) else date.fromisoformat(str(start)[:10])
                    if sd > today:
                        return "future_start"
        except Exception:
            # Table/map may not exist in minimal local DBs
            pass

    # Hub hire_date / start_date fallback
    for field in ("start_date", "hire_date", "hired_at"):
        raw = employee.get(field)
        if not raw:
            continue
        try:
            sd = raw.date() if hasattr(raw, "date") and not isinstance(raw, date) else raw
            if isinstance(sd, str):
                sd = date.fromisoformat(sd[:10])
            if isinstance(sd, date) and sd > today:
                return "future_start"
        except Exception:
            continue

    if life in {"active"} or hub in {"active", ""}:
        return "active"
    return "active" if hub != "left" else "terminated"


def lifecycle_gate(
    *,
    label: str,
    settings: dict[str, Any],
    operation: str,
) -> dict[str, Any] | None:
    """Return error dict if blocked; None if allowed."""
    lab = str(label or "unknown")
    op = str(operation or "request")
    if lab in {"terminated", "left"} and settings.get("block_terminated", True):
        return {
            "ok": False,
            "error": "leave_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Leave is not allowed for terminated employees.",
        }
    if lab == "suspended" and settings.get("block_suspended", True):
        return {
            "ok": False,
            "error": "leave_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Leave is not allowed while the employee is suspended.",
        }
    if lab == "future_start" and settings.get("block_future_start", True):
        return {
            "ok": False,
            "error": "leave_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Leave is not allowed before the employee start date.",
        }
    if lab == "notice_period" and settings.get("block_notice_period", True):
        return {
            "ok": False,
            "error": "leave_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Leave is not allowed during notice period under current policy.",
        }
    return None


def parse_expected_row_version(action: dict[str, Any] | None) -> int | None:
    if not action:
        return None
    for key in ("expected_row_version", "row_version", "expected_version"):
        if key in action and action.get(key) is not None and str(action.get(key)).strip() != "":
            try:
                return int(action.get(key))
            except (TypeError, ValueError):
                return -1  # invalid → fail closed
    return None


def concurrency_clause(expected_version: int | None) -> tuple[str, list[Any]]:
    if expected_version is None:
        return "", []
    return " AND row_version=%s", [expected_version]


def bump_row_version_sql() -> str:
    return "row_version = COALESCE(row_version, 1) + 1"


def stale_target_status(settings: dict[str, Any]) -> str:
    action = str(settings.get("stale_pending_action") or "expire").strip().lower()
    return "needs_review" if action == "needs_review" else "expired_stale"


def apply_stale_pending(
    cur: Any,
    *,
    company_code: str,
    settings: dict[str, Any],
    as_of: date,
    record_event,
    actor_phone: str | None = None,
    leave_id: str | None = None,
) -> list[dict[str, Any]]:
    """Deterministically move past-start requested → expired_stale|needs_review."""
    company = (company_code or "").upper()
    target = stale_target_status(settings)
    params: list[Any] = [target, company, as_of]
    where_id = ""
    if leave_id:
        where_id = " AND leave_id=%s"
        params.append(leave_id)
    cur.execute(
        f"""
        UPDATE leave_requests
        SET status=%s,
            decision_note=COALESCE(decision_note, 'stale pending — start date passed'),
            decided_at=COALESCE(decided_at, now()),
            updated_at=now(),
            {bump_row_version_sql()}
        WHERE company_code=%s
          AND status='requested'
          AND start_date < %s
          {where_id}
        RETURNING *
        """,
        params,
    )
    rows = [dict(r) for r in cur.fetchall()]
    for leave in rows:
        record_event(
            cur,
            leave=leave,
            company_code=company,
            event_type="stale_pending_resolved",
            payload={"leave": leave, "to_status": target, "as_of": as_of.isoformat()},
            created_by_phone=actor_phone,
        )
    return rows


def holiday_calendar_chargeable_smoke(
    *,
    start: date,
    end: date,
    weekend_days: list[str] | None = None,
    holidays: set[date] | None = None,
) -> Decimal:
    """Pure path used by tests when public_holidays table is empty in prod."""
    from datetime import timedelta

    weekend = {str(w).lower() for w in (weekend_days or ["fri", "sat"])}
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    hol = holidays or set()
    total = Decimal("0")
    cur_d = start
    while cur_d <= end:
        if names[cur_d.weekday()] not in weekend and cur_d not in hol:
            total += Decimal("1")
        cur_d = cur_d + timedelta(days=1)
    return total
