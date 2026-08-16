"""Wave 1 — emit canonical workflow tasks for Hire→Ready events.

Best-effort, fail-closed on workflow_tasks gate. Does not invent a second inbox.
Reminders still use surface remind + SLA audit; this creates actionable hr_tasks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _safe_create(
    cur: Any,
    *,
    company_code: str,
    task_type: str,
    title: str,
    subject_type: str,
    subject_id: str,
    employee_key: str | None = None,
    due_at: datetime | None = None,
    actor_user_id: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        import workflow_task_sla as wts

        wts.ensure_workflow_task_sla_schema(cur)
        return wts.create_workflow_task(
            cur,
            company_code=company_code,
            task_type=task_type,
            title=title,
            subject_type=subject_type,
            subject_id=subject_id,
            employee_key=employee_key,
            due_at=due_at,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
            metadata=metadata or {"source": "wave1_task_sync"},
        )
    except Exception as exc:
        return {"ok": False, "skipped": True, "reason": f"task_sync_unavailable:{exc.__class__.__name__}"}


def on_requisition_pending_approval(
    cur: Any,
    *,
    company_code: str,
    requisition: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    rid = str(requisition.get("requisition_id") or "")
    title = f"Approve requisition: {requisition.get('title_en') or rid}"
    return _safe_create(
        cur,
        company_code=company_code,
        task_type="requisition_approval",
        title=title,
        subject_type="requisition",
        subject_id=rid,
        due_at=datetime.now(timezone.utc) + timedelta(days=2),
        actor_user_id=actor_user_id,
        idempotency_key=f"req-approve:{rid}",
        metadata={"status": requisition.get("status"), "source": "wave1_task_sync"},
    )


def on_probation_decision_required(
    cur: Any,
    *,
    company_code: str,
    case: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    cid = str(case.get("case_id") or "")
    emp = str(case.get("employee_key") or "")
    return _safe_create(
        cur,
        company_code=company_code,
        task_type="probation_decision",
        title=f"Probation decision: {emp or cid}",
        subject_type="probation_case",
        subject_id=cid,
        employee_key=emp or None,
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
        actor_user_id=actor_user_id,
        idempotency_key=f"prob-decide:{cid}",
        metadata={"status": case.get("status"), "source": "wave1_task_sync"},
    )


def on_probation_milestone_due(
    cur: Any,
    *,
    company_code: str,
    case: dict[str, Any],
    milestone: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    cid = str(case.get("case_id") or "")
    mk = str(milestone.get("milestone_key") or "")
    return _safe_create(
        cur,
        company_code=company_code,
        task_type="probation_milestone",
        title=f"Probation milestone: {milestone.get('title_en') or mk}",
        subject_type="probation_milestone",
        subject_id=f"{cid}:{mk}",
        employee_key=str(case.get("employee_key") or "") or None,
        actor_user_id=actor_user_id,
        idempotency_key=f"prob-ms:{cid}:{mk}",
        metadata={"milestone_key": mk, "source": "wave1_task_sync"},
    )


def on_preboard_remind(
    cur: Any,
    *,
    company_code: str,
    assignment: dict[str, Any],
    item_key: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    aid = str(assignment.get("assignment_id") or "")
    key = item_key or "readiness"
    return _safe_create(
        cur,
        company_code=company_code,
        task_type="preboard_item" if item_key else "preboard_readiness",
        title=f"Preboarding follow-up: {key}",
        subject_type="preboard_assignment",
        subject_id=f"{aid}:{key}",
        employee_key=str(assignment.get("employee_key") or "") or None,
        actor_user_id=actor_user_id,
        idempotency_key=f"pb-remind:{aid}:{key}",
        metadata={"item_key": item_key, "source": "wave1_task_sync", "channel": "canonical_task"},
    )
