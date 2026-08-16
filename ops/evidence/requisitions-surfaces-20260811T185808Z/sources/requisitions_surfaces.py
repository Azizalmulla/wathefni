"""Thin surface helpers for Requisitions — wraps frozen requisitions.py.

list_cases lives here only. Answers: What headcount is requested? Who must approve? What is open to fill?
"""
from __future__ import annotations

from typing import Any

import requisitions as rq


def require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = rq.requisitions_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    return {"ok": True, "company_code": rq.company_code_norm(company_code)}


def list_requisitions(
    cur: Any,
    *,
    company_code: str,
    status: str | None = None,
    search: str | None = None,
    created_by_user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    company = rq.company_code_norm(company_code)
    params: list[Any] = [company]
    where = ["company_code=%s"]
    if status:
        st = str(status).strip().lower()
        if st == "attention":
            where.append("status IN ('pending_approval','rejected')")
        elif st == "open_pipeline":
            where.append("status IN ('approved','open')")
        else:
            where.append("status=%s")
            params.append(st)
    if created_by_user_id:
        where.append("created_by_user_id=%s")
        params.append(str(created_by_user_id))
    if search:
        where.append("(title_en ILIKE %s OR coalesce(title_ar,'') ILIKE %s OR coalesce(department,'') ILIKE %s)")
        q = f"%{search.strip()}%"
        params.extend([q, q, q])
    where_sql = " AND ".join(where)

    cur.execute(
        "SELECT status, count(*) AS c FROM requisitions WHERE company_code=%s GROUP BY status",
        (company,),
    )
    counts = {str(r["status"]): int(r["c"]) for r in (cur.fetchall() or [])}
    cur.execute(
        """
        SELECT count(*) AS c FROM requisitions
         WHERE company_code=%s AND status IN ('pending_approval','rejected')
        """,
        (company,),
    )
    counts["attention"] = int(dict(cur.fetchone() or {"c": 0})["c"])

    cur.execute(f"SELECT count(*) AS c FROM requisitions WHERE {where_sql}", tuple(params))
    total = int(dict(cur.fetchone() or {"c": 0})["c"])
    lim = max(1, min(int(limit or 100), 200))
    off = max(0, int(offset or 0))
    cur.execute(
        f"""
        SELECT * FROM requisitions
         WHERE {where_sql}
         ORDER BY
           CASE status
             WHEN 'pending_approval' THEN 0
             WHEN 'rejected' THEN 1
             WHEN 'draft' THEN 2
             WHEN 'approved' THEN 3
             WHEN 'open' THEN 4
             ELSE 9
           END,
           updated_at DESC
         LIMIT %s OFFSET %s
        """,
        tuple(params + [lim, off]),
    )
    rows = [rq._row(dict(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "company_code": company,
        "requisitions": rows,
        "counts": counts,
        "total_count": total,
        "limit": lim,
        "offset": off,
        "has_more": off + len(rows) < total,
    }


def list_events(cur: Any, *, company_code: str, requisition_id: str, limit: int = 80) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM requisition_events
         WHERE company_code=%s AND requisition_id=%s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (rq.company_code_norm(company_code), str(requisition_id), max(1, min(int(limit), 200))),
    )
    out = []
    for r in cur.fetchall() or []:
        d = dict(r)
        for k in ("event_id", "requisition_id"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        out.append(d)
    return out


def enrich_requisition(req: dict[str, Any]) -> dict[str, Any]:
    out = dict(req)
    st = str(req.get("status") or "")
    out["needs_approval"] = st == "pending_approval"
    out["needs_attention"] = st in {"pending_approval", "rejected"}
    out["fillable"] = st in {"approved", "open"}
    out["decision_required"] = st == "pending_approval"
    return out


def queue_payload(
    cur: Any,
    *,
    company_code: str,
    status: str | None = None,
    search: str | None = None,
    manager_scope_only: bool = False,
    actor_user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    # Managers see pending approval queue company-wide for Wave 1 (approver role via permission).
    # Optional: filter to own drafts when manager_scope_only without approve perm — handled in HTTP.
    listed = list_requisitions(
        cur,
        company_code=company_code,
        status=status,
        search=search,
        created_by_user_id=actor_user_id if manager_scope_only else None,
        limit=limit,
        offset=offset,
    )
    return {
        **listed,
        "requisitions": [enrich_requisition(r) for r in (listed.get("requisitions") or [])],
        "settings": rq.get_settings(cur, company_code),
        "job_publish_gate": rq.job_publish_gate_required(cur, company_code),
    }


def detail_payload(
    cur: Any,
    *,
    company_code: str,
    requisition_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    gate = require_enabled(cur, company_code)
    if not gate.get("ok"):
        return gate
    req = rq.get_requisition(cur, company_code=company_code, requisition_id=requisition_id)
    if not req:
        return {"ok": False, "error": "requisition_not_found"}
    role = (actor_role or "hr").lower()
    events = list_events(cur, company_code=company_code, requisition_id=requisition_id)
    can_manage = role in {"hr", "admin", "owner", "manager"}
    can_approve = role in {"hr", "admin", "owner"}  # SoD still enforced in transition
    return {
        "ok": True,
        "requisition": enrich_requisition(req),
        "events": events,
        "permissions": {
            "manage": can_manage,
            "approve": can_approve,
            "submit": can_manage,
            "configure": role in {"hr", "admin", "owner"},
        },
        "settings": rq.get_settings(cur, company_code),
        "job_publish_gate": rq.job_publish_gate_required(cur, company_code),
        "sod_note": "Creator cannot self-approve; transition_requisition enforces SoD.",
    }


def explain_status(req: dict[str, Any]) -> dict[str, Any]:
    st = req.get("status")
    lines_en = [f"Requisition '{req.get('title_en')}' is {st}."]
    lines_ar = [f"طلب التوظيف «{req.get('title_ar') or req.get('title_en')}» بحالة {st}."]
    if st == "pending_approval":
        lines_en.append("Approval decision required.")
        lines_ar.append("مطلوب قرار موافقة.")
    return {
        "status": st,
        "summary_en": " ".join(lines_en),
        "summary_ar": " ".join(lines_ar),
        "deep_link": {
            "web_page": "requisitions",
            "requisition_id": req.get("requisition_id"),
            "hr_mobile_path": f"/hr/requisitions/{req.get('requisition_id')}",
        },
    }
