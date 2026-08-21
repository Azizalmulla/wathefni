"""Workspace Work aggregation — My Work / Company Attention.

Canonical Overview work authority. Does not replace module queues, Action Inbox,
or pre-hire personal work. Those remain systems of action / source payloads.

This layer only:
  - asks each enabled, permitted source for already-authoritative actionable items
  - classifies membership (assigned vs unassigned vs supervisory)
  - normalizes references (destination, due, blocked) from source fields
  - dedupes identical underlying actions

It does not recompute assignment, allowed_actions, or mutations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

CONTRACT = "workspace_work_v1"
CONTRACT_VERSION = "1.1.0"
SCOPES = frozenset({"mine", "attention"})
MEMBERSHIP_ASSIGNED = "assigned"
MEMBERSHIP_UNASSIGNED = "unassigned"
MEMBERSHIP_SUPERVISORY = "supervisory"

# Source keys — one adapter per canonical payload. Do not add a parallel SoT.
SOURCE_PREHIRE = "prehire_personal_work"
SOURCE_INBOX = "action_inbox"
SOURCE_REQUISITIONS = "requisitions"
SOURCE_PREBOARDING = "preboarding"
SOURCE_PROBATION = "probation"

PREHIRE_ACTION_MODULE = {
    "follow_up_failed_delivery": "pre_hiring",
    "ready_for_review": "pre_hiring",
    "interview_feedback": "interviews",
    "interview_scheduling": "interviews",
    "overdue_task": "pre_hiring",
    "approval_needed": "pre_hiring",
    "job_owned_attention": "pre_hiring",
}

PREHIRE_TITLE = {
    "follow_up_failed_delivery": ("Follow up with candidate", "متابعة المرشح"),
    "ready_for_review": ("Review candidate", "مراجعة المرشح"),
    "interview_feedback": ("Submit interview feedback", "إرسال ملاحظات المقابلة"),
    "interview_scheduling": ("Schedule interview", "جدولة مقابلة"),
    "overdue_task": ("Complete overdue task", "إكمال المهمة المتأخرة"),
    "approval_needed": ("Approve or reject", "موافقة أو رفض"),
    "job_owned_attention": ("Review owned role", "مراجعة الدور المملوك"),
}

LoadInboxFn = Callable[[], dict[str, Any] | None]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_work_scope(value: Any) -> str:
    key = _text(value).lower().replace("-", "_")
    if key in {"my", "my_work", "mine", "personal", "assigned"}:
        return "mine"
    if key in {"attention", "company_attention", "company", "company_work", "supervisory"}:
        return "attention"
    return ""


def _actor_match(actor_user_id: str | None, *candidates: Any) -> bool:
    actor = _text(actor_user_id)
    if not actor:
        return False
    for raw in candidates:
        if _text(raw) and _text(raw) == actor:
            return True
    return False


def _has_perm(permissions: set[str], *keys: str) -> bool:
    return any(key in permissions for key in keys)


def _module_on(enabled: set[str], key: str) -> bool:
    return key in enabled


def _work_id(*parts: Any) -> str:
    return ":".join(_text(p) or "_" for p in parts)


def _due_rank(due_state: str | None) -> int:
    key = _text(due_state).lower()
    if key == "overdue":
        return 0
    if key in {"due_soon", "blocked"}:
        return 1
    return 2


def _item(
    *,
    work_id: str,
    scope: str,
    membership: str,
    module: str,
    source_key: str,
    authority_source: str,
    action_type: str,
    title_en: str,
    title_ar: str,
    reason_en: str,
    reason_ar: str,
    destination: dict[str, Any] | None,
    owner_user_id: str | None = None,
    owner_label: str | None = None,
    due_state: str | None = None,
    due_at: Any = None,
    blocked: bool = False,
    priority: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    subject_name: str | None = None,
    next_action_en: str | None = None,
    next_action_ar: str | None = None,
    allowed_actions: list[str] | None = None,
) -> dict[str, Any]:
    dest = destination if isinstance(destination, dict) else {}
    return {
        "work_id": work_id,
        "scope": scope,
        "membership": membership,
        "module": module,
        "source_key": source_key,
        "authority_source": authority_source,
        "action_type": action_type,
        "title_en": title_en,
        "title_ar": title_ar,
        "reason_en": reason_en,
        "reason_ar": reason_ar,
        "next_action_en": next_action_en or title_en,
        "next_action_ar": next_action_ar or title_ar,
        "owner_user_id": owner_user_id,
        "owner": owner_label or ("Unassigned" if not owner_user_id else owner_user_id),
        "due_state": due_state or "open",
        "due_at": due_at,
        "blocked": bool(blocked),
        "priority": int(priority) if priority is not None else None,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "subject_name": subject_name,
        "allowed_actions": list(allowed_actions or []),
        "destination": {
            "page": dest.get("page") or dest.get("web_page"),
            "filters": dest.get("filters") or {},
            "employee": dest.get("employee"),
            "cohort_key": dest.get("cohort_key"),
        },
        "dedupe_key": _work_id(module, entity_type or dest.get("page"), entity_id or work_id, action_type),
    }


def _prehire_module(action_type: str) -> str:
    key = _text(action_type).lower()
    if key in PREHIRE_ACTION_MODULE:
        return PREHIRE_ACTION_MODULE[key]
    if "assessment" in key:
        return "assessments"
    if "interview" in key:
        return "interviews"
    return "pre_hiring"


def _prehire_titles(action_type: str, fallback: str) -> tuple[str, str]:
    key = _text(action_type).lower()
    if key in PREHIRE_TITLE:
        return PREHIRE_TITLE[key]
    if "assessment" in key:
        return ("Act on assessment", "اتخاذ إجراء على التقييم")
    return (fallback or "Open task", fallback or "فتح المهمة")


def collect_prehire(
    *,
    company: str,
    db_connect: Callable[[], Any],
    actor_user_id: str | None,
    actor_role: str | None,
    actor_email: str | None,
    actor_phone: str | None,
    enabled: set[str],
    permissions: set[str],
    settings: dict[str, Any] | None,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": SOURCE_PREHIRE, "used": False, "omitted": None}
    if not _module_on(enabled, "pre_hiring"):
        meta["omitted"] = "module_off"
        return [], meta
    if not _has_perm(permissions, "prehire.read", "candidates.read", "candidate.manage"):
        meta["omitted"] = "permission_denied"
        return [], meta
    import prehire_personal_work as ppw
    import prehire_visibility as pv

    requested = "mine" if scope == "mine" else "company"
    if requested == "company" and not pv.actor_has_prehire_oversight(actor_role):
        meta["omitted"] = "not_oversight"
        return [], meta
    try:
        payload = ppw.build_scoped_work_queue(
            company=company,
            db_connect=db_connect,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            actor_email=actor_email,
            actor_phone=actor_phone,
            scope=requested,
            assessments_enabled=_module_on(enabled, "assessments"),
            interviews_enabled=_module_on(enabled, "interviews"),
            settings=settings,
            limit=100,
            cursor=None,
        )
    except ppw.PersonalWorkScopeError:
        meta["omitted"] = "company_work_forbidden"
        return [], meta
    items: list[dict[str, Any]] = []
    for raw in payload.get("items") or []:
        if not isinstance(raw, dict):
            continue
        action = _text(raw.get("action_type"))
        titles = _prehire_titles(action, _text(raw.get("next_action")) or _text(raw.get("reason")))
        assigned = _text(raw.get("audience")) == "personal" or (
            _actor_match(actor_user_id, raw.get("owner_user_id")) and _text(raw.get("source")) != "company_ops"
        )
        if scope == "mine" and not assigned:
            continue
        membership = MEMBERSHIP_ASSIGNED if assigned else (
            MEMBERSHIP_UNASSIGNED if not raw.get("owner_user_id") else MEMBERSHIP_SUPERVISORY
        )
        if scope == "attention" and membership == MEMBERSHIP_ASSIGNED and _actor_match(actor_user_id, raw.get("owner_user_id")):
            # Assigned-to-me rows stay on My Work; attention is unresolved/unassigned/others.
            continue
        reason = _text(raw.get("reason"))
        items.append(
            _item(
                work_id=_work_id("prehire", raw.get("entity_type"), raw.get("entity_id") or raw.get("person_key"), action),
                scope=scope,
                membership=membership,
                module=_prehire_module(action),
                source_key=SOURCE_PREHIRE,
                authority_source=_text(raw.get("authority_source")) or "prehire_personal_work.work_queue",
                action_type=action,
                title_en=titles[0],
                title_ar=titles[1],
                reason_en=reason,
                reason_ar=reason,
                destination=raw.get("destination") if isinstance(raw.get("destination"), dict) else {},
                owner_user_id=_text(raw.get("owner_user_id")) or None,
                owner_label=_text(raw.get("owner")) or None,
                due_state=_text(raw.get("due_state")) or None,
                priority=raw.get("priority"),
                entity_type=_text(raw.get("entity_type")) or "person",
                entity_id=_text(raw.get("entity_id") or raw.get("person_key")) or None,
                subject_name=_text(raw.get("candidate_name") or raw.get("job_label")) or None,
                next_action_en=_text(raw.get("next_action")) or titles[0],
                next_action_ar=titles[1],
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_action_inbox(
    *,
    scope: str,
    actor_user_id: str | None,
    load_inbox: LoadInboxFn | None,
    modules: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": SOURCE_INBOX, "used": False, "omitted": None}
    if load_inbox is None:
        meta["omitted"] = "loader_missing"
        return [], meta
    try:
        payload = load_inbox()
    except Exception as exc:
        meta["omitted"] = f"load_failed:{exc.__class__.__name__}"
        return [], meta
    if not isinstance(payload, dict) or not payload.get("ok"):
        meta["omitted"] = "unavailable"
        return [], meta
    items: list[dict[str, Any]] = []
    for raw in payload.get("items") or []:
        if not isinstance(raw, dict):
            continue
        assignee = raw.get("assignee_user_id") or raw.get("owner_user_id")
        assigned = _actor_match(actor_user_id, assignee) and _text(assignee)
        # Inbox items are company-HR owned unless a real assignee is present.
        if scope == "mine":
            if not assigned:
                continue
            membership = MEMBERSHIP_ASSIGNED
        else:
            if assigned:
                continue
            membership = MEMBERSHIP_SUPERVISORY if _text(raw.get("owner_role")) else MEMBERSHIP_UNASSIGNED
        dest = raw.get("deep_link") if isinstance(raw.get("deep_link"), dict) else {}
        module = _text(raw.get("source_module") or raw.get("system_of_action") or dest.get("page") or "employees")
        if modules is not None and module not in modules:
            continue
        emp = _text(raw.get("employee_key") or dest.get("employee"))
        action = _text(raw.get("id") or module)
        items.append(
            _item(
                work_id=_work_id("inbox", raw.get("id") or emp or module),
                scope=scope,
                membership=membership,
                module=module,
                source_key=SOURCE_INBOX,
                authority_source="action_inbox_wave1",
                action_type=action,
                title_en=_text(raw.get("what_en")) or "Needs attention",
                title_ar=_text(raw.get("what_ar")) or "يحتاج انتباهاً",
                reason_en=_text(raw.get("why_en")),
                reason_ar=_text(raw.get("why_ar")),
                destination={"page": dest.get("page"), "filters": {}, "employee": dest.get("employee") or emp or None},
                owner_user_id=_text(assignee) or None,
                owner_label=_text(raw.get("owner_label_en") or raw.get("owner_role")) or None,
                due_state="open",
                due_at=raw.get("deadline"),
                entity_type="employee" if emp else "inbox_item",
                entity_id=emp or _text(raw.get("id")) or None,
                subject_name=_text(raw.get("employee_name") or raw.get("what_en")) or None,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_requisitions(
    *,
    company: str,
    cur: Any,
    actor_user_id: str | None,
    enabled: set[str],
    permissions: set[str],
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": SOURCE_REQUISITIONS, "used": False, "omitted": None}
    if not _module_on(enabled, "requisitions"):
        meta["omitted"] = "module_off"
        return [], meta
    can_approve = _has_perm(permissions, "requisitions.approve", "requisitions.manage")
    if scope == "attention" and not can_approve:
        meta["omitted"] = "not_oversight"
        return [], meta
    if scope == "mine" and not _has_perm(permissions, "requisitions.read", "requisitions.manage", "requisitions.approve"):
        meta["omitted"] = "permission_denied"
        return [], meta
    import requisitions_surfaces as surfaces

    payload = surfaces.queue_payload(
        cur,
        company_code=company,
        status="pending_approval",
        actor_user_id=actor_user_id,
        limit=50,
        offset=0,
    )
    if not payload.get("ok"):
        meta["omitted"] = str(payload.get("error") or "unavailable")
        return [], meta
    items: list[dict[str, Any]] = []
    for raw in payload.get("requisitions") or []:
        if not isinstance(raw, dict) or _text(raw.get("status")) != "pending_approval":
            continue
        rid = _text(raw.get("requisition_id"))
        # Wave 1 has no designated approver user; pending approval is supervisory.
        # Creator is explicitly not the assignee (SoD). Never put creator rows in My Work.
        if scope == "mine":
            continue
        title_en = _text(raw.get("title_en")) or "Approve requisition"
        title_ar = _text(raw.get("title_ar")) or title_en
        items.append(
            _item(
                work_id=_work_id("requisitions", rid, "pending_approval"),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="requisitions",
                source_key=SOURCE_REQUISITIONS,
                authority_source="requisitions_surfaces.queue_payload",
                action_type="requisition_approval",
                title_en="Approve requisition",
                title_ar="اعتماد طلب التوظيف",
                reason_en=f"{title_en} is pending approval.",
                reason_ar=f"{title_ar} بانتظار الاعتماد.",
                destination={"page": "requisitions", "filters": {"q": rid, "status": "pending_approval"}},
                owner_user_id=None,
                owner_label="Unassigned",
                due_state="open",
                entity_type="requisition",
                entity_id=rid,
                subject_name=title_en,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_preboarding(
    *,
    company: str,
    cur: Any,
    actor_user_id: str | None,
    enabled: set[str],
    permissions: set[str],
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": SOURCE_PREBOARDING, "used": False, "omitted": None}
    if not _module_on(enabled, "preboarding"):
        meta["omitted"] = "module_off"
        return [], meta
    can_manage = _has_perm(permissions, "preboarding.manage")
    can_read = can_manage or _has_perm(permissions, "preboarding.read")
    if not can_read:
        meta["omitted"] = "permission_denied"
        return [], meta
    if scope == "attention" and not can_manage:
        meta["omitted"] = "not_oversight"
        return [], meta
    import preboarding_surfaces as surfaces

    payload = surfaces.queue_payload(
        cur,
        company_code=company,
        actor_user_id=actor_user_id,
        manager_scope_only=False,
        limit=50,
        offset=0,
    )
    if not payload.get("ok"):
        meta["omitted"] = str(payload.get("error") or "unavailable")
        return [], meta
    items: list[dict[str, Any]] = []
    for raw in payload.get("assignments") or []:
        if not isinstance(raw, dict):
            continue
        summary = raw.get("items_summary") if isinstance(raw.get("items_summary"), dict) else {}
        unresolved = (
            _text(raw.get("status")) == "blocked"
            or int(summary.get("required_open") or 0) > 0
            or int(summary.get("overdue") or 0) > 0
            or int(summary.get("blocked") or 0) > 0
        )
        if not unresolved:
            continue
        assigned = _actor_match(actor_user_id, raw.get("manager_user_id"))
        if scope == "mine" and not assigned:
            continue
        if scope == "attention" and assigned:
            continue
        aid = _text(raw.get("assignment_id"))
        name = _text(raw.get("employee_name") or raw.get("employee_key"))
        blocked = _text(raw.get("status")) == "blocked" or int(summary.get("blocked") or 0) > 0
        due_state = "overdue" if int(summary.get("overdue") or 0) > 0 else ("blocked" if blocked else "open")
        items.append(
            _item(
                work_id=_work_id("preboarding", aid),
                scope=scope,
                membership=MEMBERSHIP_ASSIGNED if assigned else MEMBERSHIP_UNASSIGNED,
                module="preboarding",
                source_key=SOURCE_PREBOARDING,
                authority_source="preboarding_surfaces.queue_payload",
                action_type="preboard_follow_up",
                title_en="Preboarding follow-up",
                title_ar="متابعة التهيئة قبل الالتحاق",
                reason_en=_text(raw.get("next_blocker")) or f"{name} still has open preboarding work.",
                reason_ar=_text(raw.get("next_blocker")) or f"{name} ما زال لديه عمل تهيئة مفتوح.",
                destination={"page": "preboarding", "filters": {"q": aid}, "employee": raw.get("employee_key")},
                owner_user_id=_text(raw.get("manager_user_id")) or None,
                owner_label=None,
                due_state=due_state,
                blocked=blocked,
                entity_type="preboard_assignment",
                entity_id=aid,
                subject_name=name,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_probation(
    *,
    company: str,
    cur: Any,
    actor_user_id: str | None,
    enabled: set[str],
    permissions: set[str],
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": SOURCE_PROBATION, "used": False, "omitted": None}
    if not _module_on(enabled, "probation"):
        meta["omitted"] = "module_off"
        return [], meta
    can_manage = _has_perm(permissions, "probation.manage")
    can_read = can_manage or _has_perm(permissions, "probation.read")
    if not can_read:
        meta["omitted"] = "permission_denied"
        return [], meta
    if scope == "attention" and not can_manage:
        meta["omitted"] = "not_oversight"
        return [], meta
    import probation_surfaces as surfaces

    payload = surfaces.queue_payload(
        cur,
        company_code=company,
        status="attention",
        actor_user_id=actor_user_id,
        manager_scope_only=False,
        limit=50,
        offset=0,
    )
    if not payload.get("ok"):
        meta["omitted"] = str(payload.get("error") or "unavailable")
        return [], meta
    items: list[dict[str, Any]] = []
    for raw in payload.get("cases") or []:
        if not isinstance(raw, dict):
            continue
        if not (raw.get("needs_attention") or raw.get("decision_required")):
            continue
        assigned = _actor_match(actor_user_id, raw.get("manager_user_id"))
        if scope == "mine" and not assigned:
            continue
        if scope == "attention" and assigned:
            continue
        cid = _text(raw.get("case_id"))
        name = _text(raw.get("employee_name") or raw.get("employee_key"))
        decision = bool(raw.get("decision_required"))
        items.append(
            _item(
                work_id=_work_id("probation", cid, "decision" if decision else "attention"),
                scope=scope,
                membership=MEMBERSHIP_ASSIGNED if assigned else MEMBERSHIP_SUPERVISORY,
                module="probation",
                source_key=SOURCE_PROBATION,
                authority_source="probation_surfaces.queue_payload",
                action_type="probation_decision" if decision else "probation_follow_up",
                title_en="Probation decision" if decision else "Probation follow-up",
                title_ar="قرار فترة التجربة" if decision else "متابعة فترة التجربة",
                reason_en=f"{name} needs a probation action.",
                reason_ar=f"{name} يحتاج إجراء فترة التجربة.",
                destination={"page": "probation", "filters": {"q": cid}, "employee": raw.get("employee_key")},
                owner_user_id=_text(raw.get("manager_user_id")) or None,
                due_state="due_soon" if decision else "open",
                entity_type="probation_case",
                entity_id=cid,
                subject_name=name,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_leave_pending(
    *,
    scope: str,
    load_leave: Callable[[], Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "leave_pending", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "no_assignment_field"
        return [], meta
    if load_leave is None:
        meta["omitted"] = "loader_missing"
        return [], meta
    try:
        payload = load_leave()
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    rows = payload.get("leave_requests") or payload.get("requests") or payload.get("pending") or []
    if isinstance(payload, list):
        rows = payload
    items: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        lid = _text(raw.get("leave_id"))
        name = _text(raw.get("employee_name") or raw.get("employee_key"))
        items.append(
            _item(
                work_id=_work_id("leave", lid),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="leave",
                source_key="leave_pending",
                authority_source="list_leave_requests",
                action_type="leave_decide",
                title_en="Decide leave request",
                title_ar="بتّ طلب الإجازة",
                reason_en=f"{name} has a leave request awaiting a decision.",
                reason_ar=f"{name} لديه طلب إجازة بانتظار القرار.",
                destination={"page": "leave", "filters": {}, "employee": raw.get("employee_key")},
                due_state="open",
                entity_type="leave_request",
                entity_id=lid,
                subject_name=name,
                allowed_actions=["decide"],
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_onboarding_actionable(
    *,
    scope: str,
    load_onboarding: Callable[[], Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "onboarding_hr_actionable", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "owner_is_role_not_user"
        return [], meta
    if load_onboarding is None:
        meta["omitted"] = "loader_missing"
        return [], meta
    try:
        payload = load_onboarding()
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    items: list[dict[str, Any]] = []
    for raw in payload.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        key = _text(raw.get("employee_key"))
        name = _text(raw.get("name") or key)
        items.append(
            _item(
                work_id=_work_id("onboarding", key, "hr_review"),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="onboarding",
                source_key="onboarding_hr_actionable",
                authority_source="list_onboarding_hr_actionable_page",
                action_type="onboarding_hr_review",
                title_en="Review onboarding item",
                title_ar="مراجعة بند التهيئة",
                reason_en=f"{name} has onboarding work awaiting HR review.",
                reason_ar=f"{name} لديه عمل تهيئة بانتظار مراجعة الموارد البشرية.",
                destination={"page": "onboarding", "filters": {"q": key}, "employee": key},
                entity_type="employee",
                entity_id=key,
                subject_name=name,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_employment_offers(
    *,
    company: str,
    cur: Any,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "employment_offers", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "no_designated_approver"
        return [], meta
    try:
        cur.execute(
            """
            SELECT offer_id, app_key, candidate_name_snapshot, status
              FROM employment_offers
             WHERE company_code=%s AND status='pending_approval'
             ORDER BY updated_at DESC
             LIMIT 50
            """,
            (company,),
        )
        rows = [dict(r) for r in (cur.fetchall() or [])]
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    items = []
    for raw in rows:
        oid = _text(raw.get("offer_id"))
        name = _text(raw.get("candidate_name_snapshot") or raw.get("app_key"))
        items.append(
            _item(
                work_id=_work_id("employment_offers", oid, "pending_approval"),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="employment_offers",
                source_key="employment_offers",
                authority_source="offer_lifecycle.pending_approval",
                action_type="offer_approval",
                title_en="Approve employment offer",
                title_ar="اعتماد عرض العمل",
                reason_en=f"{name} has an offer pending approval.",
                reason_ar=f"{name} لديه عرض عمل بانتظار الاعتماد.",
                destination={"page": "candidates", "filters": {"q": _text(raw.get("app_key"))}},
                entity_type="employment_offer",
                entity_id=oid,
                subject_name=name,
                allowed_actions=["approve", "return_draft"],
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_attendance_ops(
    *,
    company: str,
    actor_phone: str | None,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "attendance_ops", "used": False, "omitted": None}
    try:
        from attendance_ops_wave3 import get_ops_service

        payload = get_ops_service().list_queue(company_code=company, actor_phone=actor_phone, actor_role="hr")
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    if not payload.get("ok"):
        meta["omitted"] = str(payload.get("error") or "unavailable")
        return [], meta
    items = []
    phone = "".join(ch for ch in str(actor_phone or "") if ch.isdigit())
    for raw in payload.get("exceptions") or []:
        if not isinstance(raw, dict):
            continue
        owner = "".join(ch for ch in str(raw.get("owner_phone") or "") if ch.isdigit())
        assigned = bool(phone and owner and owner == phone)
        if scope == "mine" and not assigned:
            continue
        if scope == "attention" and assigned:
            continue
        eid = _text(raw.get("exception_id") or raw.get("id"))
        items.append(
            _item(
                work_id=_work_id("attendance", eid),
                scope=scope,
                membership=MEMBERSHIP_ASSIGNED if assigned else MEMBERSHIP_UNASSIGNED,
                module="attendance",
                source_key="attendance_ops",
                authority_source="AttendanceOpsService.list_queue",
                action_type=_text(raw.get("kind") or "attendance_exception"),
                title_en="Resolve attendance exception",
                title_ar="حل استثناء الحضور",
                reason_en=_text(raw.get("kind") or "Attendance exception is open."),
                reason_ar="استثناء حضور مفتوح.",
                destination={"page": "attendance", "filters": {}, "employee": raw.get("employee_key")},
                owner_user_id=None,
                owner_label=owner or "Unassigned",
                due_state="open",
                entity_type="attendance_exception",
                entity_id=eid,
                subject_name=_text(raw.get("employee_key")),
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_shift_swaps(
    *,
    scope: str,
    load_swaps: Callable[[], Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "shift_swaps", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "no_designated_approver"
        return [], meta
    if load_swaps is None:
        meta["omitted"] = "loader_missing"
        return [], meta
    try:
        rows = load_swaps() or []
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    items = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        sid = _text(raw.get("swap_id"))
        name = _text(raw.get("requester_employee_key"))
        items.append(
            _item(
                work_id=_work_id("shifts", sid, "swap"),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="shifts",
                source_key="shift_swaps",
                authority_source="resolve_shift_swaps",
                action_type="shift_swap_decide",
                title_en="Decide shift swap",
                title_ar="بتّ تبديل الوردية",
                reason_en=f"{name} requested a shift swap.",
                reason_ar=f"{name} طلب تبديل وردية.",
                destination={"page": "shifts", "filters": {}, "employee": raw.get("requester_employee_key")},
                entity_type="shift_swap",
                entity_id=sid,
                subject_name=name,
                allowed_actions=["approve", "reject"],
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_performance(
    *,
    company: str,
    cur: Any,
    actor_employee_key: str | None,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "performance", "used": False, "omitted": None}
    try:
        import performance_surfaces as surfaces

        payload = surfaces.list_reviews(cur, company_code=company, pending_only=True, actor_role="hr", limit=50)
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    actor = _text(actor_employee_key)
    items = []
    for raw in payload.get("reviews") or []:
        if not isinstance(raw, dict):
            continue
        reviewer = _text(raw.get("reviewer_employee_key"))
        assigned = bool(actor and reviewer and reviewer == actor)
        if scope == "mine":
            if not assigned:
                continue
        else:
            if assigned:
                continue
        rid = _text(raw.get("review_id"))
        name = _text(raw.get("subject_employee_key"))
        items.append(
            _item(
                work_id=_work_id("performance", rid),
                scope=scope,
                membership=MEMBERSHIP_ASSIGNED if assigned else MEMBERSHIP_SUPERVISORY,
                module="performance",
                source_key="performance",
                authority_source="performance_surfaces.list_reviews",
                action_type="performance_review",
                title_en="Complete performance review",
                title_ar="إكمال تقييم الأداء",
                reason_en=f"{name} has a pending performance review.",
                reason_ar=f"{name} لديه تقييم أداء معلّق.",
                destination={"page": "performance", "filters": {}, "employee": raw.get("subject_employee_key")},
                owner_user_id=reviewer or None,
                entity_type="performance_review",
                entity_id=rid,
                subject_name=name,
                allowed_actions=list(raw.get("allowed_actions") or ["read"]),
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_learning_requests(
    *,
    company: str,
    cur: Any,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "learning_requests", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "learner_assignment_is_not_hr_assignment"
        return [], meta
    try:
        import learning_surfaces as surfaces

        payload = surfaces.list_requests(cur, company_code=company, actor_role="hr", limit=50)
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    items = []
    for raw in payload.get("requests") or []:
        if not isinstance(raw, dict) or _text(raw.get("status")).lower() != "requested":
            continue
        rid = _text(raw.get("request_id"))
        name = _text(raw.get("employee_key"))
        title = _text(raw.get("title_en") or "learning request")
        items.append(
            _item(
                work_id=_work_id("learning", rid),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="learning",
                source_key="learning_requests",
                authority_source="learning_surfaces.list_requests",
                action_type="learning_request_decide",
                title_en="Decide learning request",
                title_ar="بتّ طلب التعلّم",
                reason_en=f"{name}: {title}",
                reason_ar=f"{name}: {raw.get('title_ar') or title}",
                destination={"page": "learning", "filters": {}, "employee": raw.get("employee_key")},
                entity_type="learning_request",
                entity_id=rid,
                subject_name=name,
                allowed_actions=["approve", "decline"],
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_benefits_enrollments(
    *,
    company: str,
    cur: Any,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "benefits_enrollments", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "no_designated_approver"
        return [], meta
    try:
        import benefits_surfaces as surfaces

        payload = surfaces.list_enrollments(cur, company_code=company, limit=50)
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    items = []
    pending = {"pending_approval", "pending_evidence"}
    for raw in payload.get("enrollments") or []:
        if not isinstance(raw, dict) or _text(raw.get("status")).lower() not in pending:
            continue
        eid = _text(raw.get("enrollment_id"))
        name = _text(raw.get("employee_key"))
        items.append(
            _item(
                work_id=_work_id("benefits", eid),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="benefits",
                source_key="benefits_enrollments",
                authority_source="benefits_surfaces.list_enrollments",
                action_type="benefits_enrollment",
                title_en="Confirm benefits enrollment",
                title_ar="تأكيد تسجيل المزايا",
                reason_en=f"{name} has a benefits enrollment awaiting confirmation.",
                reason_ar=f"{name} لديه تسجيل مزايا بانتظار التأكيد.",
                destination={"page": "benefits", "filters": {}, "employee": raw.get("employee_key")},
                entity_type="benefits_enrollment",
                entity_id=eid,
                subject_name=name,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_employee_relations(
    *,
    company: str,
    cur: Any,
    actor_key: str | None,
    actor_role: str | None,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "employee_relations", "used": False, "omitted": None}
    try:
        import employee_relations_surfaces as surfaces

        payload = surfaces.list_cases(
            cur,
            company_code=company,
            actor_key=_text(actor_key),
            actor_role=_text(actor_role) or "ordinary_hr",
        )
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    if payload.get("resource_state") == "unavailable":
        meta["omitted"] = "unavailable"
        return [], meta
    actor = _text(actor_key)
    items = []
    for raw in payload.get("cases") or []:
        if not isinstance(raw, dict):
            continue
        status = _text(raw.get("status")).lower()
        if status in {"closed", "cancelled"}:
            continue
        assigned = _actor_match(actor, raw.get("assigned_investigator"))
        if scope == "mine" and not assigned:
            continue
        if scope == "attention" and assigned:
            continue
        cid = _text(raw.get("case_id"))
        items.append(
            _item(
                work_id=_work_id("employee_relations", cid),
                scope=scope,
                membership=MEMBERSHIP_ASSIGNED if assigned else MEMBERSHIP_UNASSIGNED,
                module="employee_relations",
                source_key="employee_relations",
                authority_source="employee_relations_surfaces.list_cases",
                action_type="er_case",
                title_en="Employee relations case",
                title_ar="قضية علاقات الموظفين",
                reason_en=_text(raw.get("case_type_code") or "Open case requires action."),
                reason_ar="قضية مفتوحة تتطلب إجراءً.",
                destination={"page": "employee-relations", "filters": {"q": cid}},
                owner_user_id=_text(raw.get("assigned_investigator")) or None,
                due_at=raw.get("due_date"),
                entity_type="er_case",
                entity_id=cid,
                allowed_actions=["read"],
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_engagement_actions(
    *,
    company: str,
    cur: Any,
    actor_key: str | None,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "engagement_actions", "used": False, "omitted": None}
    try:
        import engagement_surfaces as surfaces

        payload = surfaces.list_action_plans(cur, company_code=company)
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    if payload.get("resource_state") == "unavailable" or payload.get("enabled") is False:
        meta["omitted"] = "unavailable"
        return [], meta
    actor = _text(actor_key)
    items = []
    for plan in payload.get("action_plans") or []:
        if not isinstance(plan, dict):
            continue
        for raw in plan.get("items") or []:
            if not isinstance(raw, dict):
                continue
            status = _text(raw.get("status")).lower()
            if status in {"done", "completed", "cancelled"}:
                continue
            owner = _text(raw.get("owner_key"))
            assigned = bool(actor and owner and owner == actor)
            if scope == "mine" and not assigned:
                continue
            if scope == "attention" and assigned:
                continue
            iid = _text(raw.get("action_item_id"))
            title = _text(raw.get("title_en") or "Engagement action")
            items.append(
                _item(
                    work_id=_work_id("engagement", iid),
                    scope=scope,
                    membership=MEMBERSHIP_ASSIGNED if assigned else MEMBERSHIP_UNASSIGNED,
                    module="engagement",
                    source_key="engagement_actions",
                    authority_source="engagement_surfaces.list_action_plans",
                    action_type="engagement_action",
                    title_en=title,
                    title_ar=_text(raw.get("title_ar") or title),
                    reason_en="Open engagement action item.",
                    reason_ar="بند إجراء مشاركة مفتوح.",
                    destination={"page": "engagement", "filters": {}},
                    owner_user_id=owner or None,
                    due_at=raw.get("due_date"),
                    entity_type="engagement_action_item",
                    entity_id=iid,
                    subject_name=title,
                )
            )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_comp_planning(
    *,
    company: str,
    cur: Any,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "comp_planning", "used": False, "omitted": None}
    if scope != "attention":
        meta["omitted"] = "approver_recorded_at_decision_only"
        return [], meta
    try:
        import compensation_surfaces as surfaces

        summary = surfaces.workspace_summary(cur, company_code=company)
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    if summary.get("resource_state") == "unavailable":
        meta["omitted"] = str(summary.get("reason") or "unavailable")
        return [], meta
    pending = int((summary.get("counts") or {}).get("approvals_needing_attention") or 0)
    items = []
    if pending > 0:
        items.append(
            _item(
                work_id=_work_id("comp_planning", company, "approvals"),
                scope="attention",
                membership=MEMBERSHIP_SUPERVISORY,
                module="comp_planning",
                source_key="comp_planning",
                authority_source="compensation_surfaces.workspace_summary",
                action_type="comp_planning_approve",
                title_en="Approve compensation recommendations",
                title_ar="اعتماد توصيات التعويضات",
                reason_en=f"{pending} compensation recommendations need approval.",
                reason_ar=f"{pending} توصية تعويضات بانتظار الاعتماد.",
                destination={"page": "compensation-planning", "filters": {}},
                entity_type="comp_planning_queue",
                entity_id=company,
            )
        )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def collect_workforce_planning(
    *,
    company: str,
    cur: Any,
    actor_key: str | None,
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source_key": "workforce_planning", "used": False, "omitted": None}
    try:
        import workforce_planning_surfaces as surfaces
    except Exception as exc:
        meta["omitted"] = f"error:{exc.__class__.__name__}"
        return [], meta
    items = []
    actor = _text(actor_key)
    if scope == "mine":
        if not actor:
            meta["omitted"] = "no_actor_key_for_demand_owner"
            return [], meta
        try:
            payload = surfaces.list_demand(cur, company_code=company, owner_keys=[actor])
        except Exception as exc:
            meta["omitted"] = f"error:{exc.__class__.__name__}"
            return [], meta
        for raw in payload.get("demand") or []:
            if not isinstance(raw, dict):
                continue
            did = _text(raw.get("demand_id") or raw.get("item_id"))
            items.append(
                _item(
                    work_id=_work_id("workforce_planning", did, "demand"),
                    scope="mine",
                    membership=MEMBERSHIP_ASSIGNED,
                    module="workforce_planning",
                    source_key="workforce_planning",
                    authority_source="workforce_planning_surfaces.list_demand",
                    action_type="wfp_demand",
                    title_en="Workforce demand item",
                    title_ar="بند طلب القوى العاملة",
                    reason_en="Demand item assigned to you.",
                    reason_ar="بند طلب مسند إليك.",
                    destination={"page": "workforce-planning", "filters": {}},
                    owner_user_id=actor,
                    entity_type="wfp_demand",
                    entity_id=did,
                )
            )
    else:
        try:
            payload = surfaces.list_plans(cur, company_code=company, status="submitted")
        except Exception as exc:
            meta["omitted"] = f"error:{exc.__class__.__name__}"
            return [], meta
        if payload.get("plans") is None and payload.get("resource_state") == "unavailable":
            meta["omitted"] = "unavailable"
            return [], meta
        for raw in payload.get("plans") or []:
            if not isinstance(raw, dict):
                continue
            pid = _text(raw.get("plan_id"))
            title = _text(raw.get("name") or raw.get("title") or pid)
            items.append(
                _item(
                    work_id=_work_id("workforce_planning", pid, "submitted"),
                    scope="attention",
                    membership=MEMBERSHIP_SUPERVISORY,
                    module="workforce_planning",
                    source_key="workforce_planning",
                    authority_source="workforce_planning_surfaces.list_plans",
                    action_type="wfp_plan_approve",
                    title_en="Approve workforce plan",
                    title_ar="اعتماد خطة القوى العاملة",
                    reason_en=f"{title} is submitted for approval.",
                    reason_ar=f"{title} مقدَّمة للاعتماد.",
                    destination={"page": "workforce-planning", "filters": {}},
                    entity_type="wfp_plan",
                    entity_id=pid,
                    subject_name=title,
                    allowed_actions=["approve"],
                )
            )
    meta["used"] = True
    meta["count"] = len(items)
    return items, meta


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        key = _text(item.get("dedupe_key") or item.get("work_id"))
        if not key:
            continue
        prev = best.get(key)
        if prev is None:
            best[key] = item
            order.append(key)
            continue
        prev_rank = (_due_rank(prev.get("due_state")), -(int(prev.get("priority") or 0)))
        next_rank = (_due_rank(item.get("due_state")), -(int(item.get("priority") or 0)))
        if next_rank < prev_rank:
            best[key] = item
    return [best[key] for key in order]


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = list(items)
    ordered.sort(
        key=lambda row: (
            _due_rank(row.get("due_state")),
            0 if row.get("blocked") else 1,
            -(int(row.get("priority") or 0)),
            _text(row.get("work_id")),
        )
    )
    return ordered


def can_view_attention(
    *,
    actor_role: str | None,
    permissions: set[str],
    enabled: set[str],
    inbox_ok: bool = False,
) -> bool:
    from workspace_work_contributions import MODULE_WORK_CONTRIBUTIONS, attention_entitled

    for spec in MODULE_WORK_CONTRIBUTIONS:
        if attention_entitled(spec, enabled=enabled, permissions=permissions, actor_role=actor_role):
            return True
    return False


def compose_workspace_work(
    *,
    company: str,
    db_connect: Callable[[], Any],
    actor_user_id: str | None,
    actor_role: str | None,
    actor_email: str | None,
    actor_phone: str | None,
    enabled_modules: list[str] | set[str],
    permissions: list[str] | set[str],
    settings: dict[str, Any] | None = None,
    scope: str,
    limit: int = 10,
    load_inbox: LoadInboxFn | None = None,
    load_leave: Callable[[], Any] | None = None,
    load_onboarding: Callable[[], Any] | None = None,
    load_swaps: Callable[[], Any] | None = None,
    actor_employee_key: str | None = None,
    actor_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    from workspace_work_contributions import (
        MODULE_WORK_CONTRIBUTIONS,
        attention_entitled,
        contribution_matrix,
        mine_entitled,
    )

    scope_n = normalize_work_scope(scope) or "mine"
    if scope_n not in SCOPES:
        return {"ok": False, "error": "invalid_scope", "message": "scope must be mine or attention"}
    enabled = {str(m) for m in enabled_modules}
    perms = {str(p) for p in permissions}
    limit_n = max(1, min(int(limit or 10), 50))
    actor_ref = _text(actor_key) or _text(actor_user_id) or _text(actor_phone)
    sources: list[dict[str, Any]] = []
    collected: list[dict[str, Any]] = []
    contribution_status: list[dict[str, Any]] = []
    needed: set[str] = set()
    allowed_modules: set[str] = set()

    for spec in MODULE_WORK_CONTRIBUTIONS:
        row: dict[str, Any] = {
            "module": spec.module,
            "mine": spec.mine,
            "attention": spec.attention,
            "omit_reason": spec.omit_reason,
            "loader": spec.loader or None,
            "authority_source": spec.authority_source or None,
            "status": "none",
            "count": 0,
        }
        if spec.module not in enabled:
            row["status"] = "module_off"
            contribution_status.append(row)
            continue
        if not spec.mine and not spec.attention:
            row["status"] = "none"
            contribution_status.append(row)
            continue
        if scope_n == "mine" and not spec.mine:
            row["status"] = "no_mine_contribution"
            contribution_status.append(row)
            continue
        if scope_n == "attention" and not spec.attention:
            row["status"] = "no_attention_contribution"
            contribution_status.append(row)
            continue
        entitled = (
            mine_entitled(spec, enabled=enabled, permissions=perms)
            if scope_n == "mine"
            else attention_entitled(spec, enabled=enabled, permissions=perms, actor_role=actor_role)
        )
        if not entitled:
            row["status"] = "permission_denied"
            contribution_status.append(row)
            continue
        row["status"] = "eligible"
        needed.add(spec.loader)
        allowed_modules.add(spec.module)
        contribution_status.append(row)

    def _safe(label: str, fn: Callable[[], tuple[list[dict[str, Any]], dict[str, Any]]]) -> None:
        if label not in needed:
            return
        try:
            rows, meta = fn()
        except Exception as exc:
            sources.append({"source_key": label, "used": False, "omitted": f"error:{exc.__class__.__name__}"})
            return
        sources.append(meta)
        collected.extend(rows)

    _safe(
        "prehire_personal_work",
        lambda: collect_prehire(
            company=company,
            db_connect=db_connect,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            actor_email=actor_email,
            actor_phone=actor_phone,
            enabled=enabled,
            permissions=perms,
            settings=settings,
            scope=scope_n,
        ),
    )
    _safe(
        "action_inbox",
        lambda: collect_action_inbox(
            scope=scope_n,
            actor_user_id=actor_user_id,
            load_inbox=load_inbox,
            modules=allowed_modules,
        ),
    )
    _safe("leave_pending", lambda: collect_leave_pending(scope=scope_n, load_leave=load_leave))
    _safe(
        "onboarding_hr_actionable",
        lambda: collect_onboarding_actionable(scope=scope_n, load_onboarding=load_onboarding),
    )
    _safe("shift_swaps", lambda: collect_shift_swaps(scope=scope_n, load_swaps=load_swaps))
    _safe(
        "attendance_ops",
        lambda: collect_attendance_ops(company=company, actor_phone=actor_phone, scope=scope_n),
    )

    with db_connect() as conn:
        with conn.cursor() as cur:
            _safe(
                "requisitions",
                lambda: collect_requisitions(
                    company=company,
                    cur=cur,
                    actor_user_id=actor_user_id,
                    enabled=enabled,
                    permissions=perms,
                    scope=scope_n,
                ),
            )
            _safe(
                "preboarding",
                lambda: collect_preboarding(
                    company=company,
                    cur=cur,
                    actor_user_id=actor_user_id,
                    enabled=enabled,
                    permissions=perms,
                    scope=scope_n,
                ),
            )
            _safe(
                "probation",
                lambda: collect_probation(
                    company=company,
                    cur=cur,
                    actor_user_id=actor_user_id,
                    enabled=enabled,
                    permissions=perms,
                    scope=scope_n,
                ),
            )
            _safe(
                "employment_offers",
                lambda: collect_employment_offers(company=company, cur=cur, scope=scope_n),
            )
            _safe(
                "performance",
                lambda: collect_performance(
                    company=company,
                    cur=cur,
                    actor_employee_key=actor_employee_key,
                    scope=scope_n,
                ),
            )
            _safe(
                "learning_requests",
                lambda: collect_learning_requests(company=company, cur=cur, scope=scope_n),
            )
            _safe(
                "benefits_enrollments",
                lambda: collect_benefits_enrollments(company=company, cur=cur, scope=scope_n),
            )
            _safe(
                "employee_relations",
                lambda: collect_employee_relations(
                    company=company,
                    cur=cur,
                    actor_key=actor_ref,
                    actor_role=actor_role,
                    scope=scope_n,
                ),
            )
            _safe(
                "engagement_actions",
                lambda: collect_engagement_actions(
                    company=company, cur=cur, actor_key=actor_ref, scope=scope_n
                ),
            )
            _safe(
                "comp_planning",
                lambda: collect_comp_planning(company=company, cur=cur, scope=scope_n),
            )
            _safe(
                "workforce_planning",
                lambda: collect_workforce_planning(
                    company=company, cur=cur, actor_key=actor_ref, scope=scope_n
                ),
            )
        conn.commit()

    filtered = [row for row in collected if _text(row.get("module")) in allowed_modules]
    ordered = _sort_items(_dedupe(filtered))
    page = ordered[:limit_n]
    by_module: dict[str, int] = {}
    by_membership: dict[str, int] = {}
    for row in ordered:
        mod = _text(row.get("module")) or "unknown"
        mem = _text(row.get("membership")) or MEMBERSHIP_UNASSIGNED
        by_module[mod] = by_module.get(mod, 0) + 1
        by_membership[mem] = by_membership.get(mem, 0) + 1
    for row in contribution_status:
        if row.get("status") == "eligible":
            count = int(by_module.get(row["module"]) or 0)
            row["count"] = count
            row["status"] = "used" if count else "empty"
    attention_ok = can_view_attention(
        actor_role=actor_role,
        permissions=perms,
        enabled=enabled,
    )
    stamp = (now or _now()).astimezone(timezone.utc).isoformat()
    return {
        "ok": True,
        "company_code": company,
        "contract": CONTRACT,
        "contract_version": CONTRACT_VERSION,
        "scope": scope_n,
        "work_scope": scope_n,
        "audience": "personal" if scope_n == "mine" else "attention",
        "can_view_attention": attention_ok,
        "can_view_company_work": attention_ok,
        "as_of": stamp,
        "authority_source": "workspace_work.compose",
        "composes_only": True,
        "mutates_records": False,
        "total": len(ordered),
        "limit": limit_n,
        "has_more": len(ordered) > limit_n,
        "items": page,
        "counts": {
            "total": len(ordered),
            "by_module": by_module,
            "by_membership": by_membership,
        },
        "sources": sources,
        "contributions": contribution_status,
        "contribution_matrix": contribution_matrix(),
        "honesty": {
            "modules_remain_systems_of_action": True,
            "assignment_from_source_only": True,
            "no_frontend_membership": True,
            "action_inbox_unchanged": True,
            "prehire_personal_work_unchanged": True,
            "module_queues_preserved": True,
            "disabled_modules_contribute_nothing": True,
            "unauthorized_modules_contribute_nothing": True,
        },
    }
