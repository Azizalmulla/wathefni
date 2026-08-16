"""Thin surface helpers for Probation Wave — wraps frozen probation.py authority.

Read helpers (list_cases / events / open case) live here only — not in frozen SM.
Answers: Who is on probation? What is due? How are they doing? What decision is required?
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import probation as pr


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_date(value: Any) -> date | None:
    return pr.as_date(value)


def milestone_overdue(ms: dict[str, Any], *, today: date | None = None) -> bool:
    if ms.get("status") in {"completed", "skipped"}:
        return False
    if ms.get("status") == "overdue":
        return True
    due = _as_date(ms.get("due_on"))
    if not due:
        return False
    return due < (today or date.today())


def enrich_milestone(ms: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    out = dict(ms)
    overdue = milestone_overdue(ms, today=today)
    out["overdue"] = overdue
    out["sla_state"] = (
        "done"
        if ms.get("status") in {"completed", "skipped"}
        else ("overdue" if overdue else "open")
    )
    return out


def enrich_case(
    case: dict[str, Any],
    milestones: list[dict[str, Any]] | None = None,
    *,
    employee_name: str | None = None,
    hub_status: str | None = None,
) -> dict[str, Any]:
    today = date.today()
    live = [enrich_milestone(m, today=today) for m in (milestones or [])]
    overdue = [m for m in live if m.get("overdue") or m.get("status") == "overdue"]
    open_ms = [m for m in live if m.get("status") in {"pending", "overdue"}]
    completed = [m for m in live if m.get("status") in {"completed", "skipped"}]
    end = _as_date(case.get("probation_end"))
    days_to_end = (end - today).days if end else None
    review_due = bool(
        case.get("status") in {"under_review", "extended"}
        or (days_to_end is not None and days_to_end <= 14 and case.get("status") in pr.OPEN_CASE)
        or overdue
    )
    decision_required = case.get("status") in {"under_review", "extended"} or (
        days_to_end is not None and days_to_end <= 7 and case.get("status") == "active"
    )
    next_ms = None
    for m in sorted(open_ms, key=lambda x: str(x.get("due_on") or "9999")):
        next_ms = m
        break
    out = dict(case)
    out["milestones_summary"] = {
        "total": len(live),
        "open": len(open_ms),
        "overdue": len(overdue),
        "completed": len(completed),
    }
    out["days_to_end"] = days_to_end
    out["review_due"] = review_due
    out["decision_required"] = bool(decision_required)
    out["needs_attention"] = bool(review_due or overdue or case.get("status") == "under_review")
    out["next_milestone"] = next_ms
    out["employee_name"] = employee_name
    out["employment_lifecycle"] = hub_status
    out["progress_percent"] = int(round(100 * len(completed) / len(live))) if live else 0
    return out


def require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = pr.probation_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    return {"ok": True, "company_code": pr.company_code_norm(company_code), "settings": gate.get("settings")}


def list_cases(
    cur: Any,
    *,
    company_code: str,
    status: str | None = None,
    search: str | None = None,
    manager_user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Surface-only queue read — does not alter frozen probation.py."""
    company = pr.company_code_norm(company_code)
    params: list[Any] = [company]
    where = ["company_code=%s"]
    if status:
        st = str(status).strip().lower()
        if st == "open":
            where.append("status = ANY(%s)")
            params.append(list(pr.OPEN_CASE))
        elif st == "attention":
            where.append(
                """(
                  status IN ('under_review','extended')
                  OR (status IN ('active','scheduled','extended','under_review')
                      AND probation_end <= CURRENT_DATE + INTERVAL '14 days')
                )"""
            )
        else:
            where.append("status=%s")
            params.append(st)
    if manager_user_id:
        where.append("manager_user_id=%s")
        params.append(str(manager_user_id))
    if search:
        where.append("(employee_key ILIKE %s OR cast(case_id as text) ILIKE %s)")
        q = f"%{search.strip()}%"
        params.extend([q, q])

    where_sql = " AND ".join(where)
    cur.execute(
        f"""
        SELECT status, count(*) AS c
          FROM probation_cases
         WHERE company_code=%s
         GROUP BY status
        """,
        (company,),
    )
    counts = {str(r["status"]): int(r["c"]) for r in (cur.fetchall() or [])}
    # Attention count (derived)
    cur.execute(
        """
        SELECT count(*) AS c FROM probation_cases
         WHERE company_code=%s
           AND (
             status IN ('under_review','extended')
             OR (status IN ('active','scheduled') AND probation_end <= CURRENT_DATE + INTERVAL '14 days')
           )
        """,
        (company,),
    )
    counts["attention"] = int(dict(cur.fetchone() or {"c": 0})["c"])
    counts["open"] = sum(counts.get(s, 0) for s in pr.OPEN_CASE)

    cur.execute(
        f"""
        SELECT count(*) AS c FROM probation_cases WHERE {where_sql}
        """,
        tuple(params),
    )
    total = int(dict(cur.fetchone() or {"c": 0})["c"])
    lim = max(1, min(int(limit or 100), 200))
    off = max(0, int(offset or 0))
    cur.execute(
        f"""
        SELECT * FROM probation_cases
         WHERE {where_sql}
         ORDER BY
           CASE status
             WHEN 'under_review' THEN 0
             WHEN 'extended' THEN 1
             WHEN 'active' THEN 2
             WHEN 'scheduled' THEN 3
             ELSE 9
           END,
           probation_end ASC NULLS LAST,
           updated_at DESC
         LIMIT %s OFFSET %s
        """,
        tuple(params + [lim, off]),
    )
    cases = [pr._case_row(dict(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "company_code": company,
        "cases": cases,
        "counts": counts,
        "total_count": total,
        "limit": lim,
        "offset": off,
        "has_more": off + len(cases) < total,
    }


def list_events(
    cur: Any, *, company_code: str, case_id: str, limit: int = 80
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM probation_events
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (pr.company_code_norm(company_code), str(case_id), max(1, min(int(limit), 200))),
    )
    out = []
    for r in cur.fetchall() or []:
        d = dict(r)
        d["event_id"] = str(d.get("event_id") or "")
        d["case_id"] = str(d.get("case_id") or "") if d.get("case_id") else None
        d["milestone_id"] = str(d.get("milestone_id") or "") if d.get("milestone_id") else None
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        out.append(d)
    return out


def get_open_case_for_employee(
    cur: Any, *, company_code: str, employee_key: str
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM probation_cases
         WHERE company_code=%s AND employee_key=%s
           AND status = ANY(%s)
         ORDER BY updated_at DESC
         LIMIT 1
        """,
        (pr.company_code_norm(company_code), str(employee_key), list(pr.OPEN_CASE)),
    )
    row = cur.fetchone()
    if row:
        return pr._case_row(dict(row))
    # Also surface recently terminal for outcome visibility
    cur.execute(
        """
        SELECT * FROM probation_cases
         WHERE company_code=%s AND employee_key=%s
           AND status = ANY(%s)
         ORDER BY decided_at DESC NULLS LAST, updated_at DESC
         LIMIT 1
        """,
        (
            pr.company_code_norm(company_code),
            str(employee_key),
            list(pr.TERMINAL_CASE | {"extended"}),
        ),
    )
    row = cur.fetchone()
    return pr._case_row(dict(row)) if row else None


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
    # Soft overdue flip before queue (idempotent)
    try:
        pr.mark_overdue_milestones(cur, company_code=company_code)
    except Exception:
        pass
    listed = list_cases(
        cur,
        company_code=company_code,
        status=status,
        search=search,
        manager_user_id=mgr,
        limit=limit,
        offset=offset,
    )
    enriched = []
    for case in listed.get("cases") or []:
        hub_status = None
        name = None
        if hub_lookup:
            try:
                emp = hub_lookup(case["employee_key"], company_code)
                if emp:
                    hub_status = str(emp.get("employment_status") or "")
                    name = emp.get("name")
            except Exception:
                pass
        ms = pr.list_milestones(cur, company_code=company_code, case_id=case["case_id"])
        enriched.append(enrich_case(case, ms, employee_name=name, hub_status=hub_status))
    return {
        "ok": True,
        "company_code": listed["company_code"],
        "cases": enriched,
        "counts": listed.get("counts") or {},
        "total_count": listed.get("total_count"),
        "limit": listed.get("limit"),
        "offset": listed.get("offset"),
        "has_more": listed.get("has_more"),
        "settings": pr.get_settings(cur, company_code),
    }


def detail_payload(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    hub_employee: dict[str, Any] | None = None,
    include_confidential: bool = True,
) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    case = pr.get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    role = (actor_role or "hr").lower()
    if role == "manager":
        mgr = str(case.get("manager_user_id") or "").strip()
        actor = str(actor_user_id or "").strip()
        if mgr and actor and mgr != actor:
            return {"ok": False, "error": "manager_scope_denied", "gate": "manager_scope"}

    milestones = [
        enrich_milestone(m)
        for m in pr.list_milestones(cur, company_code=company_code, case_id=case_id)
    ]
    events = list_events(cur, company_code=company_code, case_id=case_id)
    hub_status = str((hub_employee or {}).get("employment_status") or "")
    name = (hub_employee or {}).get("name")
    enriched = enrich_case(case, milestones, employee_name=name, hub_status=hub_status)

    # Confidential: strip decision internals for non-HR when requested
    if not include_confidential or role in {"employee"}:
        enriched = {
            k: v
            for k, v in enriched.items()
            if k
            not in {
                "decision_reason",
                "decided_by_user_id",
                "metadata",
            }
        }
        events = [
            e
            for e in events
            if str(e.get("event_type") or "")
            not in {"case_confirmed", "case_failed", "case_extended"}
            or role != "employee"
        ]
        # Employee may see final outcome status only
        if role == "employee":
            events = [
                {
                    "event_type": e.get("event_type"),
                    "created_at": e.get("created_at"),
                    "payload": {},
                }
                for e in events
                if str(e.get("event_type") or "").startswith("milestone_")
                or str(e.get("event_type") or "")
                in {"case_created", "case_confirmed", "case_failed", "case_extended", "case_cancelled"}
            ]

    can_manage = role in {"hr", "admin", "owner", "manager"}
    can_decide = role in {"hr", "admin", "owner"}  # manager recommends; HR decides by default
    can_recommend = role in {"hr", "admin", "owner", "manager"}
    return {
        "ok": True,
        "case": enriched,
        "milestones": milestones,
        "events": events,
        "permissions": {
            "manage": can_manage,
            "decide": can_decide,
            "recommend": can_recommend,
            "complete_milestone": can_manage,
            "configure": role in {"hr", "admin", "owner"},
        },
        "settings": pr.get_settings(cur, company_code),
        "policy": {
            "manager_recommendation_is_final": False,
            "note": "Manager recommendation is not final HR authority unless company approval policy says so.",
        },
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
    case = get_open_case_for_employee(cur, company_code=company_code, employee_key=employee_key)
    if not case:
        return {"ok": True, "case": None, "milestones": [], "empty": True}
    milestones = [
        enrich_milestone(m)
        for m in pr.list_milestones(cur, company_code=company_code, case_id=case["case_id"])
    ]
    # Employee-safe: no confidential decision material
    safe_case = {
        "case_id": case.get("case_id"),
        "status": case.get("status"),
        "probation_start": case.get("probation_start"),
        "probation_end": case.get("probation_end"),
        "employee_key": case.get("employee_key"),
        "extension_count": case.get("extension_count"),
    }
    # Employee-owned actions: self-reflection milestones tagged in metadata or all open for ack
    employee_actions = [
        m
        for m in milestones
        if str((m.get("metadata") or {}).get("owner_role") or "") == "employee"
        or str(m.get("milestone_key") or "").endswith("_reflection")
    ]
    enriched = enrich_case(
        safe_case,
        milestones,
        employee_name=(hub_employee or {}).get("name"),
        hub_status=str((hub_employee or {}).get("employment_status") or ""),
    )
    outcome = None
    if case.get("status") in pr.TERMINAL_CASE:
        outcome = {"status": case.get("status"), "decided_at": case.get("decided_at")}
    return {
        "ok": True,
        "case": enriched,
        "milestones": milestones,
        "employee_actions": employee_actions,
        "outcome": outcome,
        "empty": False,
        # Never expose decision_reason / internal notes
        "confidential_stripped": True,
    }


def explain_status(case: dict[str, Any], milestones: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = enrich_case(case, milestones)
    lines_en: list[str] = []
    lines_ar: list[str] = []
    status = case.get("status")
    lines_en.append(f"Probation status: {status}. End date: {case.get('probation_end')}.")
    lines_ar.append(f"حالة التجربة: {status}. تاريخ الانتهاء: {case.get('probation_end')}.")
    summary = enriched.get("milestones_summary") or {}
    lines_en.append(
        f"Milestones: {summary.get('completed', 0)}/{summary.get('total', 0)} done; {summary.get('overdue', 0)} overdue."
    )
    lines_ar.append(
        f"المعالم: {summary.get('completed', 0)}/{summary.get('total', 0)} مكتمل؛ {summary.get('overdue', 0)} متأخر."
    )
    if enriched.get("decision_required"):
        lines_en.append("A confirm / extend / fail decision is required.")
        lines_ar.append("مطلوب قرار: تثبيت / تمديد / إنهاء.")
    nxt = enriched.get("next_milestone")
    if nxt:
        title = nxt.get("title_en") or nxt.get("milestone_key")
        lines_en.append(f"Next: {title} due {nxt.get('due_on')}.")
        lines_ar.append(f"التالي: {nxt.get('title_ar') or title} بتاريخ {nxt.get('due_on')}.")
    return {
        "status": status,
        "decision_required": enriched.get("decision_required"),
        "review_due": enriched.get("review_due"),
        "summary_en": " ".join(lines_en),
        "summary_ar": " ".join(lines_ar),
        "deep_link": {
            "web_page": "probation",
            "case_id": case.get("case_id"),
            "employee_key": case.get("employee_key"),
            "hr_mobile_path": f"/hr/probation/{case.get('case_id')}",
            "employee_path": "/probation",
        },
    }


def remind_payload(
    *,
    case: dict[str, Any],
    milestone: dict[str, Any] | None,
    locale: str = "en",
) -> dict[str, Any]:
    is_ar = str(locale or "").lower().startswith("ar")
    title = (milestone or {}).get("title_ar" if is_ar else "title_en") or (
        (milestone or {}).get("milestone_key") or "probation review"
    )
    msg_en = f"Reminder: probation '{title}' due {((milestone or {}).get('due_on') or case.get('probation_end'))}."
    msg_ar = f"تذكير: «{title}» في فترة التجربة مستحق بتاريخ {((milestone or {}).get('due_on') or case.get('probation_end'))}."
    return {
        "ok": True,
        "channel_message": msg_ar if is_ar else msg_en,
        "deep_link": explain_status(case, [milestone] if milestone else []).get("deep_link"),
        "case_id": case.get("case_id"),
        "milestone_key": (milestone or {}).get("milestone_key"),
    }


def assert_manager_scope(
    *,
    case: dict[str, Any],
    actor_user_id: str | None,
    actor_role: str | None,
) -> dict[str, Any]:
    role = str(actor_role or "").strip().lower() or "hr"
    if role != "manager":
        return {"ok": True, "actor_role": role}
    mgr = str(case.get("manager_user_id") or "").strip()
    actor = str(actor_user_id or "").strip()
    if mgr and actor and mgr != actor:
        return {"ok": False, "error": "manager_scope_denied", "gate": "manager_scope"}
    return {"ok": True, "actor_role": role}
