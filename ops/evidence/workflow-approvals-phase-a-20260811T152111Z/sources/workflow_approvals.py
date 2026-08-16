"""Phase A — workflow_approvals authority (slice 1).

Canonical multi-step approval engine + delegation grants.
Dark by default: requires env flag + company allowlist + per-company settings.enabled.

Does NOT migrate legacy offer/leave dual-control paths.
Does NOT register product subjects (requisition/probation) — those arrive later.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKFLOW_APPROVALS_SCHEMA_VERSION = "1.0.0"

_ON_VALUES = {"1", "true", "yes", "on"}

INSTANCE_STATUSES = frozenset(
    {"draft", "pending", "approved", "rejected", "cancelled", "expired"}
)
INSTANCE_TERMINAL = frozenset({"approved", "rejected", "cancelled", "expired"})
STEP_STATUSES = frozenset({"pending", "approved", "rejected", "skipped", "delegated"})
DELEGATION_STATUSES = frozenset({"scheduled", "active", "revoked", "expired"})

# Transitions: from -> allowed to
INSTANCE_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pending", "cancelled"}),
    "pending": frozenset({"approved", "rejected", "cancelled", "expired"}),
    "approved": frozenset(),
    "rejected": frozenset(),
    "cancelled": frozenset(),
    "expired": frozenset(),
}

STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"approved", "rejected", "skipped", "delegated"}),
    "approved": frozenset(),
    "rejected": frozenset(),
    "skipped": frozenset(),
    "delegated": frozenset({"approved", "rejected", "skipped"}),
}

DELEGATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "scheduled": frozenset({"active", "revoked", "expired"}),
    "active": frozenset({"revoked", "expired"}),
    "revoked": frozenset(),
    "expired": frozenset(),
}

EVENT_TYPES = frozenset(
    {
        "policy_upserted",
        "instance_created",
        "instance_submitted",
        "step_decided",
        "instance_approved",
        "instance_rejected",
        "instance_cancelled",
        "instance_expired",
        "delegation_created",
        "delegation_activated",
        "delegation_revoked",
        "delegation_expired",
        "gate_denied",
        "sod_denied",
        "concurrency_conflict",
        "idempotent_replay",
    }
)

_SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "workflow_approvals_phase_a_v1.sql"


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def workflow_approvals_runtime_flag_on() -> bool:
    """Global kill-switch. Default off."""
    return _env_on("WATHEFNI_WORKFLOW_APPROVALS", "off")


def workflow_approvals_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_WORKFLOW_APPROVALS_COMPANIES", "") or "")
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def can_transition(machine: dict[str, frozenset[str]], from_status: str, to_status: str) -> bool:
    return to_status in machine.get(from_status, frozenset())


def validate_policy_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]] | dict[str, Any]:
    if not steps:
        return {"ok": False, "error": "policy_steps_required"}
    normalized: list[dict[str, Any]] = []
    seen_orders: set[int] = set()
    for idx, raw in enumerate(steps):
        if not isinstance(raw, dict):
            return {"ok": False, "error": "policy_step_invalid", "index": idx}
        order = int(raw.get("step_order") or (idx + 1))
        if order < 1 or order in seen_orders:
            return {"ok": False, "error": "policy_step_order_invalid", "index": idx}
        role = str(raw.get("assignee_role") or "").strip() or None
        user_id = str(raw.get("assignee_user_id") or "").strip() or None
        if not role and not user_id:
            return {"ok": False, "error": "policy_step_assignee_required", "index": idx}
        seen_orders.add(order)
        normalized.append(
            {
                "step_order": order,
                "assignee_role": role,
                "assignee_user_id": user_id,
            }
        )
    normalized.sort(key=lambda s: int(s["step_order"]))
    return normalized


def sod_self_approval_denied(
    *,
    forbid_self_approval: bool,
    created_by_user_id: str | None,
    created_by_phone: str | None,
    actor_user_id: str | None,
    actor_phone: str | None,
) -> dict[str, Any] | None:
    if not forbid_self_approval:
        return None
    actor_u = str(actor_user_id or "").strip()
    creator_u = str(created_by_user_id or "").strip()
    if actor_u and creator_u and actor_u == creator_u:
        return {"ok": False, "error": "self_approval_forbidden", "reason": "sod_user"}
    actor_p = digits_phone(actor_phone)
    creator_p = digits_phone(created_by_phone)
    if actor_p and creator_p and actor_p == creator_p:
        return {"ok": False, "error": "self_approval_forbidden", "reason": "sod_phone"}
    return None


def delegation_covers(
    *,
    grant: dict[str, Any],
    subject_type: str,
    at: datetime | None = None,
) -> bool:
    status = str(grant.get("status") or "")
    if status not in {"scheduled", "active"}:
        return False
    when = at or utc_now()
    starts = grant.get("starts_at")
    ends = grant.get("ends_at")
    if starts is not None and when < starts:
        return False
    if ends is not None and when > ends:
        return False
    # scheduled becomes effective once starts_at reached
    if status == "scheduled" and starts is not None and when < starts:
        return False
    scope = grant.get("scope_subject_types")
    if scope is None:
        return True
    if isinstance(scope, str):
        return subject_type == scope
    return subject_type in {str(s) for s in scope}


def effective_delegation_status(grant: dict[str, Any], at: datetime | None = None) -> str:
    status = str(grant.get("status") or "")
    if status in {"revoked", "expired"}:
        return status
    when = at or utc_now()
    ends = grant.get("ends_at")
    if ends is not None and when > ends:
        return "expired"
    starts = grant.get("starts_at")
    if status == "scheduled" and starts is not None and when >= starts:
        if ends is None or when <= ends:
            return "active"
    return status


def actor_may_decide_step(
    *,
    step: dict[str, Any],
    actor_user_id: str | None,
    acting_as_user_id: str | None = None,
) -> bool:
    """Direct assignee or acting via delegation (acting_as = original assignee)."""
    actor = str(actor_user_id or "").strip()
    if not actor:
        return False
    assignee = str(step.get("assignee_user_id") or "").strip()
    if assignee and actor == assignee:
        return True
    proxy_for = str(acting_as_user_id or "").strip()
    if assignee and proxy_for and proxy_for == assignee and actor != assignee:
        return True
    # Role-only steps: caller must resolve role→user externally and pass acting match
    if not assignee and step.get("assignee_role") and proxy_for:
        return True
    return False


def next_instance_status_after_step(
    *,
    decision: str,
    has_remaining_pending_steps: bool,
) -> str:
    if decision == "rejected":
        return "rejected"
    if decision == "approved" and not has_remaining_pending_steps:
        return "approved"
    if decision in {"approved", "skipped", "delegated"}:
        return "pending"
    return "pending"


def ensure_workflow_approvals_schema(cur: Any) -> None:
    sql = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    cur.execute(sql)


def seed_company_workflow_approval_settings(cur: Any, company_code: str) -> None:
    company = company_code_norm(company_code)
    if not company:
        return
    cur.execute(
        """
        INSERT INTO workflow_approval_settings (company_code, enabled)
        VALUES (%s, false)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def get_company_workflow_approval_settings(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    seed_company_workflow_approval_settings(cur, company)
    cur.execute(
        "SELECT company_code, enabled, updated_at FROM workflow_approval_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    if not row:
        return {"company_code": company, "enabled": False}
    d = dict(row)
    return {
        "company_code": company,
        "enabled": bool(d.get("enabled")),
        "updated_at": d.get("updated_at"),
    }


def set_company_workflow_approval_enabled(
    cur: Any, company_code: str, *, enabled: bool
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO workflow_approval_settings (company_code, enabled, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (company_code) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now()
        RETURNING company_code, enabled, updated_at
        """,
        (company, bool(enabled)),
    )
    row = dict(cur.fetchone())
    return {"company_code": company, "enabled": bool(row.get("enabled")), "updated_at": row.get("updated_at")}


def workflow_approvals_enabled_for_company(cur: Any, company_code: str) -> dict[str, Any]:
    """Tenant/module gate: env + allowlist + company setting. Fail closed."""
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required"}
    if not workflow_approvals_runtime_flag_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_approvals_disabled",
            "gate": "runtime_flag",
        }
    allow = workflow_approvals_company_allowlist()
    if not allow or company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_approvals_company_not_allowlisted",
            "gate": "company_allowlist",
        }
    settings = get_company_workflow_approval_settings(cur, company)
    if not settings.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_approvals_company_disabled",
            "gate": "company_setting",
        }
    return {"ok": True, "enabled": True, "company_code": company}


def _require_gate(cur: Any, company_code: str) -> dict[str, Any] | None:
    gate = workflow_approvals_enabled_for_company(cur, company_code)
    if gate.get("ok"):
        return None
    return gate


def _insert_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    instance_id: str | None = None,
    grant_id: str | None = None,
    step_id: str | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown_event_type:{event_type}")
    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO workflow_approval_events (
          event_id, company_code, instance_id, grant_id, step_id,
          event_type, actor_user_id, actor_phone, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            event_id,
            company_code_norm(company_code),
            instance_id,
            grant_id,
            step_id,
            event_type,
            actor_user_id,
            digits_phone(actor_phone) or None,
            json.dumps(payload or {}),
        ),
    )
    return event_id


def upsert_policy(
    cur: Any,
    *,
    company_code: str,
    subject_type: str,
    name: str,
    steps: list[dict[str, Any]],
    forbid_self_approval: bool = True,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    denied = _require_gate(cur, company_code)
    if denied:
        _insert_event(
            cur,
            company_code=company_code or "UNKNOWN",
            event_type="gate_denied",
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={"op": "upsert_policy", **{k: denied.get(k) for k in ("error", "gate")}},
        )
        return denied

    company = company_code_norm(company_code)
    subject = str(subject_type or "").strip()
    if not subject:
        return {"ok": False, "error": "subject_type_required"}
    validated = validate_policy_steps(steps)
    if isinstance(validated, dict) and validated.get("ok") is False:
        return validated

    if activate:
        cur.execute(
            """
            UPDATE workflow_approval_policies
               SET active=false, updated_at=now(), version=version
             WHERE company_code=%s AND subject_type=%s AND active=true
            """,
            (company, subject),
        )

    policy_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO workflow_approval_policies (
          policy_id, company_code, subject_type, name, forbid_self_approval,
          steps_json, active, version
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,1)
        RETURNING policy_id, company_code, subject_type, name, forbid_self_approval,
                  steps_json, active, version, created_at, updated_at
        """,
        (
            policy_id,
            company,
            subject,
            str(name or subject).strip(),
            bool(forbid_self_approval),
            json.dumps(validated),
            bool(activate),
        ),
    )
    row = dict(cur.fetchone())
    _insert_event(
        cur,
        company_code=company,
        event_type="policy_upserted",
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"policy_id": policy_id, "subject_type": subject, "active": bool(activate)},
    )
    return {"ok": True, "policy": _policy_row(row)}


def _policy_row(row: dict[str, Any]) -> dict[str, Any]:
    steps = row.get("steps_json")
    if isinstance(steps, str):
        steps = json.loads(steps)
    return {
        "policy_id": str(row["policy_id"]),
        "company_code": row["company_code"],
        "subject_type": row["subject_type"],
        "name": row["name"],
        "forbid_self_approval": bool(row.get("forbid_self_approval", True)),
        "steps": list(steps or []),
        "active": bool(row.get("active")),
        "version": int(row.get("version") or 1),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def get_active_policy(cur: Any, *, company_code: str, subject_type: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM workflow_approval_policies
         WHERE company_code=%s AND subject_type=%s AND active=true
         LIMIT 1
        """,
        (company_code_norm(company_code), str(subject_type or "").strip()),
    )
    row = cur.fetchone()
    return _policy_row(dict(row)) if row else None


def create_instance(
    cur: Any,
    *,
    company_code: str,
    subject_type: str,
    subject_id: str,
    created_by_user_id: str | None = None,
    created_by_phone: str | None = None,
    idempotency_key: str | None = None,
    submit: bool = True,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    denied = _require_gate(cur, company_code)
    if denied:
        return denied

    company = company_code_norm(company_code)
    subject = str(subject_type or "").strip()
    sid = str(subject_id or "").strip()
    if not subject or not sid:
        return {"ok": False, "error": "subject_required"}

    idem = str(idempotency_key or "").strip() or None
    if idem:
        cur.execute(
            """
            SELECT * FROM workflow_approval_instances
             WHERE company_code=%s AND idempotency_key=%s
             LIMIT 1
            """,
            (company, idem),
        )
        existing = cur.fetchone()
        if existing:
            inst = _instance_row(dict(existing))
            _insert_event(
                cur,
                company_code=company,
                event_type="idempotent_replay",
                instance_id=inst["instance_id"],
                actor_user_id=actor_user_id or created_by_user_id,
                actor_phone=actor_phone or created_by_phone,
                payload={"op": "create_instance", "idempotency_key": idem},
            )
            return {"ok": True, "instance": inst, "replayed": True}

    policy = get_active_policy(cur, company_code=company, subject_type=subject)
    if not policy:
        return {"ok": False, "error": "policy_not_found", "subject_type": subject}

    instance_id = str(uuid.uuid4())
    status = "pending" if submit else "draft"
    first_order = int(policy["steps"][0]["step_order"]) if policy["steps"] else None
    cur.execute(
        """
        INSERT INTO workflow_approval_instances (
          instance_id, company_code, policy_id, policy_version, subject_type, subject_id,
          status, current_step_order, created_by_user_id, created_by_phone, idempotency_key
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            instance_id,
            company,
            policy["policy_id"],
            int(policy["version"]),
            subject,
            sid,
            status,
            first_order if submit else None,
            str(created_by_user_id or "").strip() or None,
            digits_phone(created_by_phone) or None,
            idem,
        ),
    )
    inst_row = dict(cur.fetchone())

    for step_def in policy["steps"]:
        cur.execute(
            """
            INSERT INTO workflow_approval_steps (
              step_id, instance_id, company_code, step_order, status,
              assignee_role, assignee_user_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                str(uuid.uuid4()),
                instance_id,
                company,
                int(step_def["step_order"]),
                "pending" if submit else "pending",
                step_def.get("assignee_role"),
                step_def.get("assignee_user_id"),
            ),
        )

    _insert_event(
        cur,
        company_code=company,
        event_type="instance_created",
        instance_id=instance_id,
        actor_user_id=actor_user_id or created_by_user_id,
        actor_phone=actor_phone or created_by_phone,
        payload={"subject_type": subject, "subject_id": sid, "status": status},
    )
    if submit:
        _insert_event(
            cur,
            company_code=company,
            event_type="instance_submitted",
            instance_id=instance_id,
            actor_user_id=actor_user_id or created_by_user_id,
            actor_phone=actor_phone or created_by_phone,
            payload={"current_step_order": first_order},
        )
    return {"ok": True, "instance": _instance_row(inst_row), "replayed": False}


def _instance_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "instance_id": str(row["instance_id"]),
        "company_code": row["company_code"],
        "policy_id": str(row["policy_id"]),
        "policy_version": int(row.get("policy_version") or 1),
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
        "status": row["status"],
        "current_step_order": row.get("current_step_order"),
        "created_by_user_id": row.get("created_by_user_id"),
        "created_by_phone": row.get("created_by_phone"),
        "idempotency_key": row.get("idempotency_key"),
        "row_version": int(row.get("row_version") or 1),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _load_instance(cur: Any, *, company_code: str, instance_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM workflow_approval_instances
         WHERE company_code=%s AND instance_id=%s
         LIMIT 1
        """,
        (company_code_norm(company_code), str(instance_id)),
    )
    row = cur.fetchone()
    return _instance_row(dict(row)) if row else None


def _load_steps(cur: Any, instance_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM workflow_approval_steps
         WHERE instance_id=%s
         ORDER BY step_order ASC
        """,
        (str(instance_id),),
    )
    rows = cur.fetchall() or []
    out = []
    for r in rows:
        d = dict(r)
        out.append(
            {
                "step_id": str(d["step_id"]),
                "instance_id": str(d["instance_id"]),
                "company_code": d["company_code"],
                "step_order": int(d["step_order"]),
                "status": d["status"],
                "assignee_role": d.get("assignee_role"),
                "assignee_user_id": d.get("assignee_user_id"),
                "decided_by_user_id": d.get("decided_by_user_id"),
                "decided_by_phone": d.get("decided_by_phone"),
                "decision_id": d.get("decision_id"),
                "comment": d.get("comment"),
                "decided_at": d.get("decided_at"),
                "row_version": int(d.get("row_version") or 1),
            }
        )
    return out


def find_active_delegation(
    cur: Any,
    *,
    company_code: str,
    delegate_user_id: str,
    delegator_user_id: str,
    subject_type: str,
    at: datetime | None = None,
) -> dict[str, Any] | None:
    when = at or utc_now()
    cur.execute(
        """
        SELECT * FROM workflow_delegation_grants
         WHERE company_code=%s
           AND delegate_user_id=%s
           AND delegator_user_id=%s
           AND status IN ('scheduled', 'active')
         ORDER BY created_at DESC
        """,
        (
            company_code_norm(company_code),
            str(delegate_user_id).strip(),
            str(delegator_user_id).strip(),
        ),
    )
    for row in cur.fetchall() or []:
        grant = dict(row)
        eff = effective_delegation_status(grant, when)
        if eff != "active":
            continue
        grant["status"] = eff
        if delegation_covers(grant=grant, subject_type=subject_type, at=when):
            grant["grant_id"] = str(grant["grant_id"])
            return grant
    return None


def decide_step(
    cur: Any,
    *,
    company_code: str,
    instance_id: str,
    decision: str,
    actor_user_id: str | None,
    actor_phone: str | None = None,
    decision_id: str | None = None,
    expected_row_version: int | None = None,
    expected_step_row_version: int | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    denied = _require_gate(cur, company_code)
    if denied:
        return denied

    company = company_code_norm(company_code)
    decision_n = str(decision or "").strip().lower()
    if decision_n not in {"approved", "rejected"}:
        return {"ok": False, "error": "decision_invalid"}

    inst = _load_instance(cur, company_code=company, instance_id=instance_id)
    if not inst:
        return {"ok": False, "error": "instance_not_found"}

    did = str(decision_id or "").strip() or None
    steps = _load_steps(cur, instance_id)
    # Idempotent replay is keyed by decision_id across the instance (not only
    # the current step), so retries after progression remain safe.
    if did:
        prior = next((s for s in steps if s.get("decision_id") == did), None)
        if prior:
            _insert_event(
                cur,
                company_code=company,
                event_type="idempotent_replay",
                instance_id=instance_id,
                step_id=prior["step_id"],
                actor_user_id=actor_user_id,
                actor_phone=actor_phone,
                payload={"decision_id": did, "decision": prior["status"]},
            )
            return {
                "ok": True,
                "replayed": True,
                "instance": inst,
                "step": prior,
            }

    if inst["status"] != "pending":
        return {"ok": False, "error": "instance_not_pending", "status": inst["status"]}

    if expected_row_version is not None and int(inst["row_version"]) != int(expected_row_version):
        _insert_event(
            cur,
            company_code=company,
            event_type="concurrency_conflict",
            instance_id=instance_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={
                "expected_row_version": expected_row_version,
                "actual_row_version": inst["row_version"],
            },
        )
        return {
            "ok": False,
            "error": "concurrency_conflict",
            "expected_row_version": expected_row_version,
            "actual_row_version": inst["row_version"],
        }

    policy = get_active_policy(cur, company_code=company, subject_type=inst["subject_type"])
    # Prefer policy snapshot fields from instance's policy_id
    cur.execute(
        "SELECT * FROM workflow_approval_policies WHERE policy_id=%s LIMIT 1",
        (inst["policy_id"],),
    )
    prow = cur.fetchone()
    forbid = True
    if prow:
        forbid = bool(dict(prow).get("forbid_self_approval", True))
    elif policy:
        forbid = bool(policy.get("forbid_self_approval", True))

    sod = sod_self_approval_denied(
        forbid_self_approval=forbid,
        created_by_user_id=inst.get("created_by_user_id"),
        created_by_phone=inst.get("created_by_phone"),
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
    )
    if sod:
        _insert_event(
            cur,
            company_code=company,
            event_type="sod_denied",
            instance_id=instance_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload=sod,
        )
        return sod

    current_order = inst.get("current_step_order")
    current = next((s for s in steps if s["step_order"] == current_order), None)
    if not current or current["status"] not in {"pending", "delegated"}:
        return {"ok": False, "error": "step_not_decidable"}

    if did and current.get("decision_id") and current.get("decision_id") != did:
        return {"ok": False, "error": "decision_id_conflict", "existing_decision_id": current["decision_id"]}

    acting_as: str | None = None
    assignee = str(current.get("assignee_user_id") or "").strip()
    actor = str(actor_user_id or "").strip()
    if assignee and actor == assignee:
        acting_as = None
    elif assignee and actor and actor != assignee:
        grant = find_active_delegation(
            cur,
            company_code=company,
            delegate_user_id=actor,
            delegator_user_id=assignee,
            subject_type=inst["subject_type"],
        )
        if not grant:
            return {"ok": False, "error": "actor_not_assignee"}
        acting_as = assignee
    elif not assignee and current.get("assignee_role"):
        # Role-resolved externally: require actor_user_id present (caller authorized)
        if not actor:
            return {"ok": False, "error": "actor_required"}
    else:
        return {"ok": False, "error": "actor_not_assignee"}

    if expected_step_row_version is not None and int(current["row_version"]) != int(
        expected_step_row_version
    ):
        return {
            "ok": False,
            "error": "concurrency_conflict",
            "expected_step_row_version": expected_step_row_version,
            "actual_step_row_version": current["row_version"],
        }

    if not can_transition(STEP_TRANSITIONS, current["status"], decision_n):
        return {
            "ok": False,
            "error": "invalid_step_transition",
            "from": current["status"],
            "to": decision_n,
        }

    cur.execute(
        """
        UPDATE workflow_approval_steps
           SET status=%s,
               decided_by_user_id=%s,
               decided_by_phone=%s,
               decision_id=COALESCE(%s, decision_id),
               comment=%s,
               decided_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE step_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (
            decision_n,
            actor or None,
            digits_phone(actor_phone) or None,
            did,
            str(comment or "").strip() or None,
            current["step_id"],
            company,
            int(current["row_version"]),
        ),
    )
    updated_step = cur.fetchone()
    if not updated_step:
        return {"ok": False, "error": "concurrency_conflict", "entity": "step"}

    remaining = [
        s
        for s in steps
        if s["step_order"] > int(current["step_order"]) and s["status"] == "pending"
    ]
    new_status = next_instance_status_after_step(
        decision=decision_n, has_remaining_pending_steps=bool(remaining)
    )
    if not can_transition(INSTANCE_TRANSITIONS, inst["status"], new_status) and new_status != inst["status"]:
        return {"ok": False, "error": "invalid_instance_transition", "to": new_status}

    next_order = int(remaining[0]["step_order"]) if remaining and new_status == "pending" else None
    cur.execute(
        """
        UPDATE workflow_approval_instances
           SET status=%s,
               current_step_order=%s,
               row_version=row_version+1,
               updated_at=now()
         WHERE instance_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (new_status, next_order, instance_id, company, int(inst["row_version"])),
    )
    updated_inst = cur.fetchone()
    if not updated_inst:
        return {"ok": False, "error": "concurrency_conflict", "entity": "instance"}

    _insert_event(
        cur,
        company_code=company,
        event_type="step_decided",
        instance_id=instance_id,
        step_id=current["step_id"],
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={
            "decision": decision_n,
            "decision_id": did,
            "acting_as_user_id": acting_as,
            "step_order": current["step_order"],
        },
    )
    if new_status == "approved":
        _insert_event(
            cur,
            company_code=company,
            event_type="instance_approved",
            instance_id=instance_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={},
        )
    elif new_status == "rejected":
        _insert_event(
            cur,
            company_code=company,
            event_type="instance_rejected",
            instance_id=instance_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={},
        )

    return {
        "ok": True,
        "replayed": False,
        "instance": _instance_row(dict(updated_inst)),
        "step": dict(updated_step),
        "acting_as_user_id": acting_as,
    }


def cancel_instance(
    cur: Any,
    *,
    company_code: str,
    instance_id: str,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    denied = _require_gate(cur, company_code)
    if denied:
        return denied
    company = company_code_norm(company_code)
    inst = _load_instance(cur, company_code=company, instance_id=instance_id)
    if not inst:
        return {"ok": False, "error": "instance_not_found"}
    if inst["status"] in INSTANCE_TERMINAL:
        return {"ok": False, "error": "instance_terminal", "status": inst["status"]}
    if not can_transition(INSTANCE_TRANSITIONS, inst["status"], "cancelled"):
        return {"ok": False, "error": "invalid_instance_transition"}
    if expected_row_version is not None and int(inst["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}
    cur.execute(
        """
        UPDATE workflow_approval_instances
           SET status='cancelled', current_step_order=NULL,
               row_version=row_version+1, updated_at=now()
         WHERE instance_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (instance_id, company, int(inst["row_version"])),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type="instance_cancelled",
        instance_id=instance_id,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={},
    )
    return {"ok": True, "instance": _instance_row(dict(row))}


def create_delegation_grant(
    cur: Any,
    *,
    company_code: str,
    delegator_user_id: str,
    delegate_user_id: str,
    starts_at: datetime,
    ends_at: datetime | None = None,
    scope_subject_types: list[str] | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    denied = _require_gate(cur, company_code)
    if denied:
        return denied
    company = company_code_norm(company_code)
    delegator = str(delegator_user_id or "").strip()
    delegate = str(delegate_user_id or "").strip()
    if not delegator or not delegate:
        return {"ok": False, "error": "delegation_parties_required"}
    if delegator == delegate:
        return {"ok": False, "error": "delegation_self_forbidden"}
    if ends_at is not None and ends_at <= starts_at:
        return {"ok": False, "error": "delegation_window_invalid"}

    now = utc_now()
    status = "active" if starts_at <= now else "scheduled"
    if ends_at is not None and ends_at < now:
        return {"ok": False, "error": "delegation_already_ended"}

    scope = None
    if scope_subject_types is not None:
        scope = [str(s).strip() for s in scope_subject_types if str(s).strip()]

    grant_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO workflow_delegation_grants (
          grant_id, company_code, delegator_user_id, delegate_user_id,
          scope_subject_types, status, starts_at, ends_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (grant_id, company, delegator, delegate, scope, status, starts_at, ends_at),
    )
    row = dict(cur.fetchone())
    _insert_event(
        cur,
        company_code=company,
        event_type="delegation_created",
        grant_id=grant_id,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"status": status, "delegator_user_id": delegator, "delegate_user_id": delegate},
    )
    if status == "active":
        _insert_event(
            cur,
            company_code=company,
            event_type="delegation_activated",
            grant_id=grant_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={},
        )
    row["grant_id"] = grant_id
    return {"ok": True, "grant": row}


def revoke_delegation_grant(
    cur: Any,
    *,
    company_code: str,
    grant_id: str,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    denied = _require_gate(cur, company_code)
    if denied:
        return denied
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT * FROM workflow_delegation_grants
         WHERE company_code=%s AND grant_id=%s
         LIMIT 1
        """,
        (company, str(grant_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "grant_not_found"}
    grant = dict(row)
    status = str(grant.get("status") or "")
    if not can_transition(DELEGATION_TRANSITIONS, status, "revoked"):
        return {"ok": False, "error": "invalid_delegation_transition", "status": status}
    if expected_row_version is not None and int(grant.get("row_version") or 1) != int(
        expected_row_version
    ):
        return {"ok": False, "error": "concurrency_conflict"}
    cur.execute(
        """
        UPDATE workflow_delegation_grants
           SET status='revoked', revoked_at=now(), revoked_by_user_id=%s,
               row_version=row_version+1
         WHERE grant_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (
            str(actor_user_id or "").strip() or None,
            str(grant_id),
            company,
            int(grant.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type="delegation_revoked",
        grant_id=str(grant_id),
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={},
    )
    return {"ok": True, "grant": dict(updated)}


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Set WATHEFNI_WORKFLOW_APPROVALS=off (global kill-switch)",
            "Clear or remove company from WATHEFNI_WORKFLOW_APPROVALS_COMPANIES",
            "SET workflow_approval_settings.enabled=false for canary companies",
        ],
        "data": [
            "Retain all workflow_approval_* tables; do not DROP",
            "Legacy offer/leave dual-control paths remain authoritative for their subjects",
            "No product subjects bind until Wave 1 modules entitle",
        ],
        "schema_version": WORKFLOW_APPROVALS_SCHEMA_VERSION,
    }
