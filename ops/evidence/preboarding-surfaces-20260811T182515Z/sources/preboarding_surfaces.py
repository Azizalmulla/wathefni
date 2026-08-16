"""Thin surface helpers for Preboarding Wave — wraps frozen preboarding.py authority.

No business-logic rewrite: queue/detail projections, overdue flags, manager filter,
assistant explain/remind payloads. HTTP routes in app.py call these helpers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import preboarding as pb


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def item_overdue(item: dict[str, Any], *, now: datetime | None = None) -> bool:
    due = item.get("due_at")
    if not due or item.get("status") in {"done", "waived"}:
        return False
    if isinstance(due, str):
        try:
            due = datetime.fromisoformat(due.replace("Z", "+00:00"))
        except Exception:
            return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due < (now or _utcnow())


def enrich_item(item: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    out = dict(item)
    overdue = item_overdue(item, now=now)
    out["overdue"] = overdue
    out["sla_state"] = "overdue" if overdue else ("done" if item.get("status") in {"done", "waived"} else "open")
    return out


def enrich_assignment(
    assignment: dict[str, Any],
    items: list[dict[str, Any]] | None = None,
    *,
    hub_status: str | None = None,
    employee_name: str | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    live_items = [enrich_item(i, now=now) for i in (items or [])]
    readiness = assignment.get("readiness") or pb.compute_readiness(live_items)
    overdue_items = [i for i in live_items if i.get("overdue")]
    required_open = [
        i
        for i in live_items
        if i.get("required") and i.get("status") not in {"done", "waived"}
    ]
    out = dict(assignment)
    out["readiness"] = readiness
    out["items_summary"] = {
        "total": len(live_items),
        "required_open": len(required_open),
        "overdue": len(overdue_items),
        "blocked": sum(1 for i in live_items if i.get("status") == "blocked"),
    }
    out["employment_lifecycle"] = hub_status or "pending_start"
    out["is_joining"] = str(hub_status or "pending_start").lower() in {
        "pending_start",
        "joining",
        "future_start",
    }
    out["is_active_employee"] = str(hub_status or "").lower() == "active" and not out["is_joining"]
    if employee_name:
        out["employee_name"] = employee_name
    out["next_blocker"] = (readiness.get("blockers") or [None])[0]
    return out


def require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = pb.preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    return {"ok": True, "company_code": pb.company_code_norm(company_code)}


def queue_payload(
    cur: Any,
    *,
    company_code: str,
    status: str | None = None,
    search: str | None = None,
    manager_user_id: str | None = None,
    manager_scope_only: bool = False,
    actor_user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    hub_lookup: Any | None = None,
) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    mgr = None
    if manager_scope_only:
        mgr = manager_user_id or actor_user_id
    listed = pb.list_assignments(
        cur,
        company_code=company_code,
        status=status,
        search=search,
        manager_user_id=mgr,
        limit=limit,
        offset=offset,
    )
    enriched = []
    for asn in listed.get("assignments") or []:
        hub_status = None
        name = None
        if hub_lookup:
            try:
                emp = hub_lookup(asn["employee_key"], company_code)
                if emp:
                    hub_status = str(emp.get("employment_status") or "")
                    name = emp.get("name")
            except Exception:
                pass
        items = pb.list_items(cur, company_code=company_code, assignment_id=asn["assignment_id"])
        enriched.append(enrich_assignment(asn, items, hub_status=hub_status, employee_name=name))
    return {
        "ok": True,
        "company_code": listed["company_code"],
        "assignments": enriched,
        "counts": listed.get("counts") or {},
        "total_count": listed.get("total_count"),
        "limit": listed.get("limit"),
        "offset": listed.get("offset"),
        "has_more": listed.get("has_more"),
        "settings": pb.get_settings(cur, company_code),
    }


def detail_payload(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    hub_employee: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    asn = pb.get_assignment(cur, company_code=company_code, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    scope = pb.assert_actor_scope(
        assignment=asn,
        actor_user_id=actor_user_id,
        actor_role=actor_role or "hr",
        permission="preboarding.read",
    )
    if not scope.get("ok") and (actor_role or "").lower() == "manager":
        return scope
    items = [enrich_item(i) for i in pb.list_items(cur, company_code=company_code, assignment_id=assignment_id)]
    events = pb.list_events(cur, company_code=company_code, assignment_id=assignment_id, limit=80)
    hub_status = str((hub_employee or {}).get("employment_status") or "")
    name = (hub_employee or {}).get("name")
    assignment = enrich_assignment(asn, items, hub_status=hub_status, employee_name=name)
    # Owner buckets for UI
    by_owner: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_owner.setdefault(str(item.get("owner_role") or "other"), []).append(item)
    can_manage = (actor_role or "hr").lower() in {"hr", "admin", "owner", "manager"}
    can_waive = (actor_role or "hr").lower() in {"hr", "admin", "owner"}
    return {
        "ok": True,
        "assignment": assignment,
        "items": items,
        "items_by_owner": by_owner,
        "events": events,
        "readiness": assignment.get("readiness") or pb.compute_readiness(items),
        "permissions": {
            "manage": can_manage,
            "waive_item": can_waive,
            "set_joining_date": can_manage and (actor_role or "").lower() != "manager",
            "configure_template": (actor_role or "").lower() in {"hr", "admin", "owner"},
        },
        "settings": pb.get_settings(cur, company_code),
    }


def employee_self_payload(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    hub_employee: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    asn = pb.get_open_assignment_for_employee(
        cur, company_code=company_code, employee_key=employee_key
    )
    if not asn:
        return {"ok": True, "assignment": None, "items": [], "empty": True}
    items = [
        enrich_item(i)
        for i in pb.list_items(cur, company_code=company_code, assignment_id=asn["assignment_id"])
        if str(i.get("owner_role") or "") == "employee"
    ]
    hub_status = str((hub_employee or {}).get("employment_status") or "pending_start")
    assignment = enrich_assignment(
        asn,
        pb.list_items(cur, company_code=company_code, assignment_id=asn["assignment_id"]),
        hub_status=hub_status,
        employee_name=(hub_employee or {}).get("name"),
    )
    return {
        "ok": True,
        "assignment": assignment,
        "items": items,
        "joining_date": asn.get("joining_date"),
        "progress": assignment.get("readiness"),
        "empty": False,
        "preboarding_only": hub_status in {"pending_start", "joining", "future_start"},
    }


def explain_blockers(assignment: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    readiness = assignment.get("readiness") or pb.compute_readiness(items)
    blockers = readiness.get("blockers") or []
    lines_en = []
    lines_ar = []
    for b in blockers[:8]:
        key = b.get("item_key") or b.get("code")
        lines_en.append(f"{key}: {b.get('code')}" + (f" ({b.get('reason')})" if b.get("reason") else ""))
        lines_ar.append(f"{key}: {b.get('code')}")
    if readiness.get("ready"):
        lines_en = ["All required preboarding items are complete."]
        lines_ar = ["اكتملت جميع عناصر التهيئة المطلوبة."]
    return {
        "ready": bool(readiness.get("ready")),
        "blocked": bool(readiness.get("blocked")),
        "blockers": blockers,
        "summary_en": "; ".join(lines_en) if lines_en else "No blockers.",
        "summary_ar": "؛ ".join(lines_ar) if lines_ar else "لا عوائق.",
        "deep_link": {
            "web_page": "preboarding",
            "assignment_id": assignment.get("assignment_id"),
            "employee_key": assignment.get("employee_key"),
            "hr_mobile_path": f"/hr/preboarding/{assignment.get('assignment_id')}",
            "employee_path": "/preboarding",
        },
    }


def remind_payload(
    *,
    assignment: dict[str, Any],
    item: dict[str, Any] | None,
    locale: str = "en",
) -> dict[str, Any]:
    is_ar = str(locale or "").lower().startswith("ar")
    owner = (item or {}).get("owner_role") or "hr"
    title = (item or {}).get("title_ar" if is_ar else "title_en") or (item or {}).get("item_key") or "preboarding"
    msg_en = f"Reminder: complete '{title}' before joining ({assignment.get('joining_date')})."
    msg_ar = f"تذكير: أكمل «{title}» قبل تاريخ الالتحاق ({assignment.get('joining_date')})."
    return {
        "ok": True,
        "channel_message": msg_ar if is_ar else msg_en,
        "owner_role": owner,
        "deep_link": explain_blockers(assignment, [item] if item else []).get("deep_link"),
        "assignment_id": assignment.get("assignment_id"),
        "item_key": (item or {}).get("item_key"),
    }


def template_config_payload(cur: Any, *, company_code: str) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    pb.ensure_default_template(cur, company_code)
    return {
        "ok": True,
        "template_id": pb.DEFAULT_TEMPLATE_ID,
        "template_version": pb.DEFAULT_TEMPLATE_VERSION,
        "items": pb.list_template_items(cur, company_code=company_code),
        "settings": pb.get_settings(cur, company_code),
    }
