"""Leave Wave 4 — controlled real-operation readiness (WATHEFNI).

- Real HR/manager leave decisions only via named phone allowlist when gate is on.
- Dual-control for resolving stale real pending leave (audited).
- Honesty: enforced=false / legal_reviewed=false remain.
- Kill switch: WATHEFNI_LEAVE_WAVE4_KILL=on disables Wave 4 UX enrich + real allowlist gate
  (falls back to Wave 3B synthetic-only posture without expanding real decisions).

Does NOT enable balance enforcement or Payroll money.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

LEAVE_WAVE4_VERSION = "4.0.0"
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
_ON = {"1", "true", "yes", "on"}

# Named WATHEFNI HR/manager phones for controlled real leave decisions (digits).
# Empty allowlist + gate on ⇒ no real decisions (fail closed).
DEFAULT_REAL_DECISION_ALLOWLIST = (
    "96599338566",  # historical leave decider in prod evidence
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leave_dual_control_actions (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  leave_id uuid NOT NULL,
  action_kind text NOT NULL,
  status text NOT NULL DEFAULT 'pending_second',
  initiated_by_phone text NOT NULL,
  confirmed_by_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  confirmed_at timestamptz,
  CONSTRAINT leave_dual_status_chk CHECK (status IN ('pending_second','confirmed','cancelled','expired')),
  CONSTRAINT leave_dual_kind_chk CHECK (action_kind IN ('expire_stale','reject_stale','cancel_stale'))
);
CREATE INDEX IF NOT EXISTS idx_leave_dual_leave
  ON leave_dual_control_actions(company_code, leave_id, status);
"""


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def leave_wave4_enabled() -> bool:
    if str(os.environ.get("WATHEFNI_LEAVE_WAVE4_KILL") or "").strip().lower() in _ON:
        return False
    raw = os.environ.get("WATHEFNI_LEAVE_WAVE4")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON


def leave_real_decision_gate_enabled() -> bool:
    """When on, non-synthetic leave decisions require allowlisted actor phone."""
    if not leave_wave4_enabled():
        return False
    raw = os.environ.get("WATHEFNI_LEAVE_REAL_DECISION_GATE")
    if raw is None or str(raw).strip() == "":
        # Production defaults ON for Wave 4 controlled readiness; non-prod off unless set.
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"
    return str(raw).strip().lower() in _ON


def real_decision_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST") or "").strip()
    if not raw:
        return {_digits(p) for p in DEFAULT_REAL_DECISION_ALLOWLIST if _digits(p)}
    return {_digits(p) for p in raw.split(",") if _digits(p)}


def ensure_leave_wave4_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def actor_allowlisted_for_real_decision(actor_phone: str | None) -> bool:
    d = _digits(actor_phone)
    if not d:
        return False
    return d in real_decision_allowlist()


def real_decision_denied(
    *,
    leave: dict[str, Any] | None,
    actor_phone: str | None,
    is_synthetic_subject: bool,
) -> dict[str, Any] | None:
    """Deny real (non-synthetic) leave decisions when gate on and actor not allowlisted."""
    if not leave_real_decision_gate_enabled():
        return None
    if is_synthetic_subject:
        return None
    if actor_allowlisted_for_real_decision(actor_phone):
        return None
    return {
        "ok": False,
        "error": "leave_real_decision_not_allowlisted",
        "message": (
            "Real leave decisions are limited to the named WATHEFNI allowlist "
            "while Leave is in controlled readiness (enforced=false)."
        ),
        "balances_enforced": False,
        "legal_reviewed": False,
    }


def enrich_leave_row_for_ui(row: dict[str, Any], *, as_of: date | None = None) -> dict[str, Any]:
    """Add presentation helpers without mutating balance enforcement."""
    import leave_workflow_wave3 as w3

    out = dict(row)
    unit = str(out.get("duration_unit") or w3.DURATION_FULL_DAY)
    out["duration_unit"] = unit
    out["duration_label"] = {
        w3.DURATION_FULL_DAY: "full_day",
        w3.DURATION_HALF_DAY: "half_day",
        w3.DURATION_HOURLY: "hourly",
    }.get(unit, unit)
    out["is_partial_day"] = unit in {w3.DURATION_HALF_DAY, w3.DURATION_HOURLY}
    out["is_unpaid"] = str(out.get("leave_type") or "").lower() == "unpaid"
    out["balance_binding"] = False
    out["balances_enforced"] = False
    out["legal_reviewed"] = False
    out["payroll_owns_unpaid_money"] = out["is_unpaid"]
    if as_of is None:
        as_of = datetime.now(tz=KUWAIT_TZ).date()
    try:
        out["temporal_state"] = w3.classify_leave_temporal_state(out, as_of=as_of)
    except Exception:
        out["temporal_state"] = "unknown"
    # Next action hint for queue UX
    status = str(out.get("status") or "")
    if status in {"requested", "needs_review"}:
        out["next_action"] = "decide"
    elif status == "needs_info":
        out["next_action"] = "await_resubmit"
    elif status == "approved" and out.get("temporal_state") == "future":
        out["next_action"] = "may_cancel"
    else:
        out["next_action"] = None
    return out


def holiday_year_status_payload(cur: Any, *, year: int | None = None) -> dict[str, Any]:
    """Surface holiday-year review state for UX (fail-closed reason when enforced)."""
    y = year or datetime.now(tz=KUWAIT_TZ).year
    try:
        cur.execute(
            """
            SELECT status, version, updated_at
            FROM leave_holiday_year_versions
            WHERE calendar_code='kw_public_v2' AND year=%s
            ORDER BY version DESC LIMIT 1
            """,
            (y,),
        )
        row = cur.fetchone()
    except Exception:
        return {
            "year": y,
            "status": "unknown",
            "fail_closed_if_enforced": True,
            "reason": "holiday_year_status_unavailable",
            "enforced": False,
        }
    if not row:
        return {
            "year": y,
            "status": "missing",
            "fail_closed_if_enforced": True,
            "reason": "holiday_year_not_approved",
            "enforced": False,
        }
    d = dict(row)
    status = str(d.get("status") or "pending_review")
    return {
        "year": y,
        "status": status,
        "version": d.get("version"),
        "fail_closed_if_enforced": status != "approved",
        "reason": None if status == "approved" else "holiday_year_not_approved",
        "enforced": False,
        "message_en": (
            "Holiday calendar year is approved."
            if status == "approved"
            else "Holiday year is pending review — enforced chargeable-day gates would fail closed. Observe mode still uses seeded/approved holidays only."
        ),
        "message_ar": (
            "تم اعتماد تقويم العطل للسنة."
            if status == "approved"
            else "سنة العطل قيد المراجعة — بوابات الأيام المحتسبة المفروضة ستُغلق. وضع المراقبة يستخدم العطل المعتمدة/المزروعة فقط."
        ),
    }


def initiate_stale_dual_control(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    actor_phone: str | None,
    action_kind: str = "expire_stale",
    note: str | None = None,
) -> dict[str, Any]:
    """First leg of dual control for stale real pending leave."""
    ensure_leave_wave4_schema(cur)
    company = (company_code or "").upper()
    leave_id = leave.get("leave_id")
    actor = _digits(actor_phone)
    if not leave_id or not actor:
        return {"ok": False, "error": "invalid_dual_control_request"}
    if action_kind not in {"expire_stale", "reject_stale", "cancel_stale"}:
        return {"ok": False, "error": "invalid_dual_control_kind"}
    # Cancel any open pending dual for same leave
    cur.execute(
        """
        UPDATE leave_dual_control_actions
        SET status='cancelled'
        WHERE company_code=%s AND leave_id=%s AND status='pending_second'
        """,
        (company, leave_id),
    )
    cur.execute(
        """
        INSERT INTO leave_dual_control_actions (
          company_code, leave_id, action_kind, status, initiated_by_phone, payload
        ) VALUES (%s,%s,%s,'pending_second',%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            leave_id,
            action_kind,
            actor,
            __import__("json").dumps({"note": note, "leave_status": leave.get("status"), "start_date": str(leave.get("start_date") or "")}),
        ),
    )
    row = dict(cur.fetchone())
    return {"ok": True, "dual_control": row, "awaiting_second_approver": True}


def confirm_stale_dual_control(
    cur: Any,
    *,
    company_code: str,
    leave_id: str,
    actor_phone: str | None,
    dual_action_id: str | None = None,
) -> dict[str, Any]:
    """Second leg — different phone from initiator required."""
    ensure_leave_wave4_schema(cur)
    company = (company_code or "").upper()
    actor = _digits(actor_phone)
    if not actor:
        return {"ok": False, "error": "actor_phone_required"}
    if dual_action_id:
        cur.execute(
            """
            SELECT * FROM leave_dual_control_actions
            WHERE action_id=%s AND company_code=%s AND leave_id=%s AND status='pending_second'
            LIMIT 1
            """,
            (dual_action_id, company, leave_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM leave_dual_control_actions
            WHERE company_code=%s AND leave_id=%s AND status='pending_second'
            ORDER BY created_at DESC LIMIT 1
            """,
            (company, leave_id),
        )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "dual_control_not_found"}
    d = dict(row)
    if _digits(d.get("initiated_by_phone")) == actor:
        return {
            "ok": False,
            "error": "dual_control_same_actor",
            "message": "Second confirmation must come from a different allowlisted actor.",
        }
    if not actor_allowlisted_for_real_decision(actor):
        return {"ok": False, "error": "leave_real_decision_not_allowlisted"}
    cur.execute(
        """
        UPDATE leave_dual_control_actions
        SET status='confirmed', confirmed_by_phone=%s, confirmed_at=now()
        WHERE action_id=%s
        RETURNING *
        """,
        (actor, d["action_id"]),
    )
    confirmed = dict(cur.fetchone())
    return {"ok": True, "dual_control": confirmed, "action_kind": confirmed.get("action_kind")}


def policy_eligibility_snapshot(
    cur: Any,
    *,
    company_code: str,
    employee_keys: list[str],
) -> list[dict[str, Any]]:
    """Confirm policy-pack binding + lifecycle label for named employees (read-only)."""
    import leave_authority_wave1 as w1

    company = (company_code or "").upper()
    out: list[dict[str, Any]] = []
    for key in employee_keys:
        cur.execute(
            "SELECT employee_key, name, phone, employment_status FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
            (company, key),
        )
        emp = cur.fetchone()
        if not emp:
            out.append({"employee_key": key, "ok": False, "error": "employee_not_found"})
            continue
        e = dict(emp)
        life = w1.resolve_employee_lifecycle_label(cur, company_code=company, employee=e)
        cur.execute(
            "SELECT leave_type, days_per_year, eligibility_months, enforced, legal_reviewed FROM leave_policies WHERE company_code=%s ORDER BY leave_type",
            (company,),
        )
        pols = [dict(r) for r in cur.fetchall()]
        out.append(
            {
                "employee_key": key,
                "name": e.get("name"),
                "phone": e.get("phone"),
                "lifecycle": life,
                "ok": True,
                "policies": pols,
                "enforced": False,
                "legal_reviewed": False,
            }
        )
    return out
