"""Wave 1 — Requisitions authority + optional job publish gate.

Dark by default:
  WATHEFNI_REQUISITIONS=on
  ∧ company in WATHEFNI_REQUISITIONS_COMPANIES
  ∧ requisition_settings.enabled (or company_modules.requisitions)

Job publish gate is OPTIONAL_INTEGRATION:
  both requisitions + pre_hiring entitled
  ∧ jobs_require_approved_requisition (default true when both on)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REQUISITIONS_SCHEMA_VERSION = "1.0.0"
_ON_VALUES = {"1", "true", "yes", "on"}
_SCHEMA = Path(__file__).resolve().parent / "ops" / "sql" / "requisitions_wave1_v1.sql"

REQUISITION_STATUSES = frozenset(
    {"draft", "pending_approval", "approved", "rejected", "open", "filled", "cancelled"}
)
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pending_approval", "cancelled"}),
    "pending_approval": frozenset({"approved", "rejected", "cancelled"}),
    "rejected": frozenset({"draft", "cancelled"}),
    "approved": frozenset({"open", "cancelled"}),
    "open": frozenset({"filled", "cancelled"}),
    "filled": frozenset(),
    "cancelled": frozenset(),
}

EVENT_TYPES = frozenset(
    {
        "created",
        "submitted",
        "approved",
        "rejected",
        "opened",
        "filled",
        "cancelled",
        "revised",
        "job_linked",
        "gate_denied",
        "gate_checked",
        "idempotent_replay",
        "concurrency_conflict",
    }
)


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def requisitions_runtime_flag_on() -> bool:
    return _env_on("WATHEFNI_REQUISITIONS", "off")


def requisitions_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_REQUISITIONS_COMPANIES", "") or "")
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, frozenset())


def ensure_requisitions_schema(cur: Any) -> None:
    cur.execute(_SCHEMA.read_text(encoding="utf-8"))


def seed_settings(cur: Any, company_code: str) -> None:
    company = company_code_norm(company_code)
    if not company:
        return
    cur.execute(
        """
        INSERT INTO requisition_settings (company_code, enabled, jobs_require_approved_requisition)
        VALUES (%s, false, true)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def get_settings(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    seed_settings(cur, company)
    cur.execute("SELECT * FROM requisition_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    d = dict(row) if row else {}
    return {
        "company_code": company,
        "enabled": bool(d.get("enabled")),
        "jobs_require_approved_requisition": bool(d.get("jobs_require_approved_requisition", True)),
    }


def set_settings(
    cur: Any,
    company_code: str,
    *,
    enabled: bool | None = None,
    jobs_require_approved_requisition: bool | None = None,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    seed_settings(cur, company)
    current = get_settings(cur, company)
    en = bool(current["enabled"] if enabled is None else enabled)
    gate = bool(
        current["jobs_require_approved_requisition"]
        if jobs_require_approved_requisition is None
        else jobs_require_approved_requisition
    )
    cur.execute(
        """
        UPDATE requisition_settings
           SET enabled=%s, jobs_require_approved_requisition=%s, updated_at=now()
         WHERE company_code=%s
        RETURNING *
        """,
        (en, gate, company),
    )
    return get_settings(cur, company)


def _module_enabled(cur: Any, company_code: str) -> bool:
    company = company_code_norm(company_code)
    try:
        cur.execute(
            """
            SELECT enabled FROM company_modules
             WHERE company_code=%s AND module_key='requisitions'
             LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        if row and bool(dict(row).get("enabled")):
            return True
    except Exception:
        pass
    return bool(get_settings(cur, company).get("enabled"))


def _pre_hiring_enabled(cur: Any, company_code: str) -> bool:
    company = company_code_norm(company_code)
    try:
        cur.execute(
            """
            SELECT enabled FROM company_modules
             WHERE company_code=%s AND module_key='pre_hiring'
             LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        return bool(row and dict(row).get("enabled"))
    except Exception:
        return False


def requisitions_enabled_for_company(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required"}
    if not requisitions_runtime_flag_on():
        return {"ok": False, "enabled": False, "error": "requisitions_disabled", "gate": "runtime_flag"}
    allow = requisitions_company_allowlist()
    if not allow or company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "requisitions_company_not_allowlisted",
            "gate": "company_allowlist",
        }
    if not _module_enabled(cur, company):
        return {
            "ok": False,
            "enabled": False,
            "error": "requisitions_company_disabled",
            "gate": "company_setting",
        }
    return {"ok": True, "enabled": True, "company_code": company}


def job_publish_gate_required(cur: Any, company_code: str) -> dict[str, Any]:
    """OPTIONAL_INTEGRATION: gate active only when both modules + setting on."""
    company = company_code_norm(company_code)
    req = requisitions_enabled_for_company(cur, company)
    if not req.get("ok"):
        return {"required": False, "reason": "requisitions_off", "gate": req}
    if not _pre_hiring_enabled(cur, company):
        return {"required": False, "reason": "pre_hiring_off"}
    settings = get_settings(cur, company)
    if not settings.get("jobs_require_approved_requisition"):
        return {"required": False, "reason": "company_setting_off"}
    return {"required": True, "reason": "optional_integration_active", "company_code": company}


def _insert_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    requisition_id: str | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown_event_type:{event_type}")
    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO requisition_events (
          event_id, company_code, requisition_id, event_type,
          actor_user_id, actor_phone, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            event_id,
            company_code_norm(company_code),
            requisition_id,
            event_type,
            actor_user_id,
            digits_phone(actor_phone) or None,
            json.dumps(payload or {}),
        ),
    )
    return event_id


def _row(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata")
    if isinstance(meta, str):
        meta = json.loads(meta)
    return {
        "requisition_id": str(row["requisition_id"]),
        "company_code": row["company_code"],
        "title_en": row.get("title_en"),
        "title_ar": row.get("title_ar"),
        "department": row.get("department"),
        "org_unit_id": row.get("org_unit_id"),
        "headcount": int(row.get("headcount") or 1),
        "target_hire_date": row.get("target_hire_date"),
        "budget_ref": row.get("budget_ref"),
        "position_id": row.get("position_id"),
        "status": row.get("status"),
        "approval_instance_id": str(row["approval_instance_id"]) if row.get("approval_instance_id") else None,
        "created_by_user_id": row.get("created_by_user_id"),
        "created_by_phone": row.get("created_by_phone"),
        "row_version": int(row.get("row_version") or 1),
        "idempotency_key": row.get("idempotency_key"),
        "metadata": meta or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def get_requisition(cur: Any, *, company_code: str, requisition_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM requisitions
         WHERE company_code=%s AND requisition_id=%s
         LIMIT 1
        """,
        (company_code_norm(company_code), str(requisition_id)),
    )
    row = cur.fetchone()
    return _row(dict(row)) if row else None


def create_requisition(
    cur: Any,
    *,
    company_code: str,
    title_en: str,
    title_ar: str | None = None,
    department: str | None = None,
    org_unit_id: str | None = None,
    headcount: int = 1,
    target_hire_date: date | None = None,
    budget_ref: str | None = None,
    position_id: str | None = None,
    created_by_user_id: str | None = None,
    created_by_phone: str | None = None,
    idempotency_key: str | None = None,
    submit: bool = False,
) -> dict[str, Any]:
    gate = requisitions_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    title = str(title_en or "").strip()
    if not title:
        return {"ok": False, "error": "title_required"}
    try:
        hc = int(headcount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "headcount_invalid"}
    if hc < 1:
        return {"ok": False, "error": "headcount_invalid"}

    idem = str(idempotency_key or "").strip() or None
    if idem:
        cur.execute(
            "SELECT * FROM requisitions WHERE company_code=%s AND idempotency_key=%s LIMIT 1",
            (company, idem),
        )
        existing = cur.fetchone()
        if existing:
            _insert_event(
                cur,
                company_code=company,
                event_type="idempotent_replay",
                requisition_id=str(dict(existing)["requisition_id"]),
                actor_user_id=created_by_user_id,
                actor_phone=created_by_phone,
                payload={"op": "create_requisition"},
            )
            return {"ok": True, "replayed": True, "requisition": _row(dict(existing))}

    rid = str(uuid.uuid4())
    status = "pending_approval" if submit else "draft"
    cur.execute(
        """
        INSERT INTO requisitions (
          requisition_id, company_code, title_en, title_ar, department, org_unit_id,
          headcount, target_hire_date, budget_ref, position_id, status,
          created_by_user_id, created_by_phone, idempotency_key
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            rid,
            company,
            title,
            str(title_ar or "").strip() or None,
            str(department or "").strip() or None,
            str(org_unit_id or "").strip() or None,
            hc,
            target_hire_date,
            str(budget_ref or "").strip() or None,
            str(position_id or "").strip() or None,
            status,
            str(created_by_user_id or "").strip() or None,
            digits_phone(created_by_phone) or None,
            idem,
        ),
    )
    row = dict(cur.fetchone())
    _insert_event(
        cur,
        company_code=company,
        event_type="created",
        requisition_id=rid,
        actor_user_id=created_by_user_id,
        actor_phone=created_by_phone,
        payload={"status": status},
    )
    if submit:
        _insert_event(
            cur,
            company_code=company,
            event_type="submitted",
            requisition_id=rid,
            actor_user_id=created_by_user_id,
            actor_phone=created_by_phone,
            payload={},
        )
    return {"ok": True, "replayed": False, "requisition": _row(row)}


def transition_requisition(
    cur: Any,
    *,
    company_code: str,
    requisition_id: str,
    to_status: str,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
    approval_instance_id: str | None = None,
) -> dict[str, Any]:
    gate = requisitions_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    req = get_requisition(cur, company_code=company, requisition_id=requisition_id)
    if not req:
        return {"ok": False, "error": "requisition_not_found"}
    dst = str(to_status or "").strip().lower()
    if dst not in REQUISITION_STATUSES:
        return {"ok": False, "error": "status_invalid"}
    if not can_transition(req["status"], dst):
        return {
            "ok": False,
            "error": "invalid_transition",
            "from": req["status"],
            "to": dst,
        }
    if expected_row_version is not None and int(req["row_version"]) != int(expected_row_version):
        _insert_event(
            cur,
            company_code=company,
            event_type="concurrency_conflict",
            requisition_id=requisition_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={"expected": expected_row_version, "actual": req["row_version"]},
        )
        return {"ok": False, "error": "concurrency_conflict"}

    # SoD: creator cannot self-approve
    if dst == "approved":
        actor = str(actor_user_id or "").strip()
        creator = str(req.get("created_by_user_id") or "").strip()
        if actor and creator and actor == creator:
            return {"ok": False, "error": "self_approval_forbidden"}
        actor_p = digits_phone(actor_phone)
        creator_p = digits_phone(req.get("created_by_phone"))
        if actor_p and creator_p and actor_p == creator_p:
            return {"ok": False, "error": "self_approval_forbidden"}

    cur.execute(
        """
        UPDATE requisitions
           SET status=%s,
               approval_instance_id=COALESCE(%s, approval_instance_id),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND requisition_id=%s AND row_version=%s
        RETURNING *
        """,
        (
            dst,
            str(approval_instance_id).strip() if approval_instance_id else None,
            company,
            str(requisition_id),
            int(req["row_version"]),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    event_map = {
        "pending_approval": "submitted",
        "approved": "approved",
        "rejected": "rejected",
        "open": "opened",
        "filled": "filled",
        "cancelled": "cancelled",
        "draft": "revised",
    }
    _insert_event(
        cur,
        company_code=company,
        event_type=event_map.get(dst, "revised"),
        requisition_id=str(requisition_id),
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"from": req["status"], "to": dst},
    )
    return {"ok": True, "requisition": _row(dict(updated))}


def link_job_to_requisition(
    cur: Any,
    *,
    company_code: str,
    requisition_id: str,
    position_code: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    gate = requisitions_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    req = get_requisition(cur, company_code=company, requisition_id=requisition_id)
    if not req:
        return {"ok": False, "error": "requisition_not_found"}
    if req["status"] not in {"approved", "open"}:
        return {"ok": False, "error": "requisition_not_linkable", "status": req["status"]}
    code = str(position_code or "").strip()
    if not code:
        return {"ok": False, "error": "position_code_required"}
    link_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO requisition_job_links (
          link_id, company_code, requisition_id, position_code, linked_by_user_id
        ) VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, position_code) DO UPDATE
          SET requisition_id=EXCLUDED.requisition_id,
              linked_at=now(),
              linked_by_user_id=EXCLUDED.linked_by_user_id
        RETURNING *
        """,
        (link_id, company, str(requisition_id), code, actor_user_id),
    )
    link = dict(cur.fetchone())
    try:
        cur.execute(
            """
            UPDATE positions
               SET requisition_id=%s, updated_at=now()
             WHERE company_code=%s AND position_code=%s
            """,
            (str(requisition_id), company, code),
        )
    except Exception:
        pass
    _insert_event(
        cur,
        company_code=company,
        event_type="job_linked",
        requisition_id=str(requisition_id),
        actor_user_id=actor_user_id,
        payload={"position_code": code},
    )
    return {"ok": True, "link": link, "requisition": req}


def assert_job_publish_allowed(
    cur: Any,
    *,
    company_code: str,
    position_code: str | None = None,
    requisition_id: str | None = None,
) -> dict[str, Any]:
    """Fail-closed job publish gate when OPTIONAL_INTEGRATION is active."""
    company = company_code_norm(company_code)
    need = job_publish_gate_required(cur, company)
    if not need.get("required"):
        _insert_event(
            cur,
            company_code=company or "UNKNOWN",
            event_type="gate_checked",
            payload={"allowed": True, "reason": need.get("reason"), "position_code": position_code},
        )
        return {"ok": True, "allowed": True, "gate_required": False, "reason": need.get("reason")}

    rid = str(requisition_id or "").strip() or None
    code = str(position_code or "").strip() or None
    if not rid and code:
        cur.execute(
            """
            SELECT requisition_id FROM requisition_job_links
             WHERE company_code=%s AND position_code=%s
             LIMIT 1
            """,
            (company, code),
        )
        link = cur.fetchone()
        if link:
            rid = str(dict(link)["requisition_id"])
        else:
            try:
                cur.execute(
                    """
                    SELECT requisition_id FROM positions
                     WHERE company_code=%s AND position_code=%s
                     LIMIT 1
                    """,
                    (company, code),
                )
                prow = cur.fetchone()
                if prow and dict(prow).get("requisition_id"):
                    rid = str(dict(prow)["requisition_id"])
            except Exception:
                pass

    if not rid:
        _insert_event(
            cur,
            company_code=company,
            event_type="gate_denied",
            payload={"reason": "requisition_required", "position_code": code},
        )
        return {
            "ok": False,
            "allowed": False,
            "gate_required": True,
            "error": "requisition_required",
            "message": "An approved requisition is required before publishing this job.",
        }

    req = get_requisition(cur, company_code=company, requisition_id=rid)
    if not req or req["status"] not in {"approved", "open"}:
        _insert_event(
            cur,
            company_code=company,
            event_type="gate_denied",
            requisition_id=rid,
            payload={"reason": "requisition_not_approved", "status": (req or {}).get("status")},
        )
        return {
            "ok": False,
            "allowed": False,
            "gate_required": True,
            "error": "requisition_not_approved",
            "requisition_id": rid,
            "status": (req or {}).get("status"),
            "message": "Link an approved requisition before publishing this job.",
        }

    _insert_event(
        cur,
        company_code=company,
        event_type="gate_checked",
        requisition_id=rid,
        payload={"allowed": True, "position_code": code},
    )
    return {
        "ok": True,
        "allowed": True,
        "gate_required": True,
        "requisition_id": rid,
        "requisition_status": req["status"],
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Set WATHEFNI_REQUISITIONS=off",
            "Remove company from WATHEFNI_REQUISITIONS_COMPANIES",
            "SET requisition_settings.enabled=false; optionally jobs_require_approved_requisition=false",
            "Disable company_modules.requisitions",
        ],
        "data": ["Retain requisitions tables; do not DROP", "Job publish resumes without gate when module off"],
        "schema_version": REQUISITIONS_SCHEMA_VERSION,
    }
