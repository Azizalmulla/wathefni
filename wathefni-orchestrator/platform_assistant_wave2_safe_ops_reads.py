"""Platform Assistant Wave 2 — Safe Ops Queue Reads (Leave + Attendance).

Grounded, read-only summarize tools for Leave request queues and Attendance
exception queues. HR dashboard · WATHEFNI · mutations off.

Reuses Wave 1 spine: kill switches, citations, freshness, authority, audit, EN/AR.
Attendance answers are ingest-off / existing-record based. Leave/Attendance SoA
remain systems of action — prepare deep links only.

Does NOT: Payroll, Shifts, Onboarding, new Analytics/Compliance surfaces,
WhatsApp/manager/employee/mobile, money, ingest, or mutations.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

import platform_assistant_spine_wave1 as spine

WAVE2_VERSION = "1.0.0"
WAVE2_CONTRACT = "platform_assistant_wave2_safe_ops_reads"

WAVE2_READ_TOOLS = frozenset(
    {
        "summarize_leave_queue",
        "summarize_attendance_exceptions",
    }
)


def _flag_on(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def platform_assistant_wave2_enabled() -> bool:
    return _flag_on("WATHEFNI_PLATFORM_ASSISTANT_WAVE2") and spine.platform_assistant_wave1_enabled()


def wave2_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PLATFORM_ASSISTANT_WAVE2_COMPANIES") or spine.ALLOWED_COMPANY).strip()
    return {part.strip().upper() for part in raw.split(",") if part.strip()} or {spine.ALLOWED_COMPANY}


def wave2_enabled_for_company(company_code: str | None) -> bool:
    if not platform_assistant_wave2_enabled():
        return False
    if not spine.wave1_enabled_for_company(company_code):
        return False
    company = str(company_code or "").strip().upper()
    return company in wave2_companies()


def honesty_payload() -> dict[str, Any]:
    base = spine.honesty_payload()
    return {
        **base,
        "contract": WAVE2_CONTRACT,
        "wave2_version": WAVE2_VERSION,
        "wave2_scope": ["leave_queue_reads", "attendance_exception_reads"],
        "payroll": False,
        "shifts": False,
        "onboarding_assistant_surface": False,
        "analytics_new_surface": False,
        "compliance_new_surface": False,
        "attendance_ingest": False,
        "capture_ingest": "off",
        "attendance_records_basis": "existing_records_only",
        "leave_soa_unchanged": True,
        "attendance_soa_unchanged": True,
        "mutations": False,
    }


def ensure_wave2_module_contracts() -> None:
    spine.ensure_default_module_contracts()
    if spine.get_module_contract("leave_queue"):
        return
    spine.register_module_contract(
        spine._base_contract(
            module_key="leave_queue",
            label_en="Leave request queue",
            label_ar="طابور طلبات الإجازة",
            tools=["summarize_leave_queue"],
            deep_link={"page": "leave", "path": "/dashboard/posthire?tab=leave"},
            kill_class="platform_assistant_wave2",
        )
    )
    spine.register_module_contract(
        spine._base_contract(
            module_key="attendance_exceptions",
            label_en="Attendance exceptions",
            label_ar="استثناءات الحضور",
            tools=["summarize_attendance_exceptions"],
            deep_link={"page": "attendance", "path": "/dashboard/posthire?tab=attendance"},
            kill_class="platform_assistant_wave2",
        )
    )


ensure_wave2_module_contracts()


def is_wave2_read_tool(name: str | None) -> bool:
    return str(name or "") in WAVE2_READ_TOOLS


def is_spine_read_tool(name: str | None) -> bool:
    return spine.is_wave1_read_tool(name) or is_wave2_read_tool(name)


def wave2_preflight(ctx: Any, *, required_permission: str) -> dict[str, Any] | None:
    """Wave 2 gate on top of Wave 1 spine preflight."""
    locale = spine._locale_from_request(ctx.request)
    if spine.assistant_kill_engaged():
        return spine.fallback_envelope("killed", locale=locale)
    company = str((ctx.action or {}).get("company_code") or "").upper()
    if not wave2_enabled_for_company(company):
        if company and company not in wave2_companies():
            return spine.fallback_envelope("tenant_denied", locale=locale)
        return spine.fallback_envelope(
            "blocked",
            locale=locale,
            payload={"reason": "platform_assistant_wave2_disabled"},
        )
    if not spine._is_dashboard_channel(ctx.request):
        return spine.fallback_envelope("whatsapp_denied", locale=locale)
    perms = spine._permissions_from_ctx(ctx)
    if not spine._perm_ok(perms, required_permission):
        return spine.fallback_envelope("blocked", locale=locale, payload={"required_permission": required_permission})
    return None


def _viewer_phone(ctx: Any) -> str | None:
    meta = getattr(ctx.request, "metadata", None) if isinstance(getattr(ctx.request, "metadata", None), dict) else {}
    admin = meta.get("admin_user") if isinstance(meta.get("admin_user"), dict) else {}
    access = meta.get("access") if isinstance(meta.get("access"), dict) else {}
    phone = str(admin.get("phone") or access.get("phone") or "").strip()
    return phone or None


def _group_rows(
    rows: list[dict[str, Any]],
    *,
    employee_key_field: str = "employee_key",
    employee_name_field: str = "employee_name",
    status_field: str = "status",
    team_field: str = "team",
) -> dict[str, Any]:
    by_employee: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    by_team: dict[str, int] = defaultdict(int)
    labels: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ek = str(row.get(employee_key_field) or "unknown")
        by_employee[ek] += 1
        labels[ek] = str(row.get(employee_name_field) or ek)
        st = str(row.get(status_field) or "unknown")
        by_status[st] += 1
        team = str(row.get(team_field) or row.get("department") or row.get("branch_name") or "unassigned")
        by_team[team] += 1
    return {
        "by_employee": [
            {"employee_key": k, "name": labels.get(k, k), "count": v}
            for k, v in sorted(by_employee.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        ],
        "by_status": dict(sorted(by_status.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_team": dict(sorted(by_team.items(), key=lambda kv: (-kv[1], kv[0]))[:20]),
    }


def execute_summarize_leave_queue(ctx: Any) -> dict[str, Any]:
    locale = spine._locale_from_request(ctx.request)
    denied = wave2_preflight(ctx, required_permission="leave.read")
    if denied:
        return spine._tool_result("summarize_leave_queue", denied)

    legacy = ctx.legacy
    company = str((ctx.action or {}).get("company_code") or spine.ALLOWED_COMPANY).upper()
    action = dict(ctx.action or {})
    action.setdefault("company_code", company)
    action.setdefault("status", "requested")  # pending-like queue by default
    if _viewer_phone(ctx):
        action["viewer_phone"] = _viewer_phone(ctx)
    query = str(action.get("query") or "").strip()
    if query:
        action["prompt_text"] = query

    try:
        if not hasattr(legacy, "list_leave_requests"):
            return spine._tool_result("summarize_leave_queue", spine.fallback_envelope("unavailable", locale=locale))
        # Module entitlement
        if hasattr(legacy, "company_has_module") and not legacy.company_has_module(company, "leave"):
            return spine._tool_result(
                "summarize_leave_queue",
                spine.fallback_envelope(
                    "blocked",
                    locale=locale,
                    payload={"reason": "module_disabled", "module": "leave"},
                    deep_links=[{"page": "leave"}],
                ),
            )
        result = legacy.list_leave_requests(action, company_code=company)
    except Exception as exc:
        return spine._tool_result(
            "summarize_leave_queue",
            spine.fallback_envelope("unavailable", locale=locale, payload={"error": str(exc)[:200]}),
        )

    if not isinstance(result, dict) or not result.get("ok"):
        err = str((result or {}).get("error") or "leave_list_failed")
        key = "blocked" if "scope" in err or "denied" in err else "unavailable"
        return spine._tool_result(
            "summarize_leave_queue",
            spine.fallback_envelope(key, locale=locale, payload={"error": err}),
        )

    rows = [r for r in (result.get("leave_requests") or []) if isinstance(r, dict)]
    total = int(result.get("total_count") or result.get("count") or len(rows))
    groups = _group_rows(rows)
    # Urgency: needs_review / needs_info / shift conflicts first
    urgent = []
    citations = []
    proposed = []
    for row in rows[:25]:
        status = str(row.get("status") or "")
        conflicts = int(row.get("shift_conflict_count") or 0)
        urgency = "high" if status in {"needs_review", "needs_info"} or conflicts > 0 else "medium" if status in {"requested", "pending"} else "low"
        item = {
            "leave_id": row.get("leave_id") or row.get("id"),
            "employee_key": row.get("employee_key"),
            "employee_name": row.get("employee_name"),
            "status": status,
            "start_date": row.get("start_date"),
            "end_date": row.get("end_date"),
            "shift_conflict_count": conflicts,
            "urgency": urgency,
            "team": row.get("team") or row.get("department"),
        }
        if urgency == "high":
            urgent.append(item)
        citations.append(
            {
                "kind": "leave_request",
                "module": "leave",
                "id": str(item["leave_id"] or item["employee_key"]),
                "label_en": f"{item['employee_name'] or item['employee_key']} · {status}",
                "label_ar": f"{item['employee_name'] or item['employee_key']} · {status}",
                "as_of": spine.kuwait_now_iso(),
                "authority_state": "live_controlled",
                "deep_link": {"page": "leave", "leave_id": item["leave_id"], "employee_key": item["employee_key"]},
            }
        )
        proposed.append(
            {
                "kind": "deep_link",
                "module": "leave",
                "label_en": f"Open leave for {item['employee_name'] or item['employee_key']}",
                "label_ar": f"افتح إجازة {item['employee_name'] or item['employee_key']}",
                "deep_link": {"page": "leave", "leave_id": item["leave_id"], "employee_key": item["employee_key"]},
                "executes": False,
            }
        )

    if total == 0:
        summary_en = "Leave queue is clear — no pending leave requests in scope."
        summary_ar = "طابور الإجازات فارغ — لا طلبات إجازة معلّقة في النطاق."
        confidence = "grounded"
        authority = "live_controlled"
    else:
        high_n = len(urgent)
        summary_en = (
            f"Leave queue: {total} pending request(s) in scope"
            + (f", {high_n} high-urgency (needs review/info or shift conflict)" if high_n else "")
            + ". Grouped by employee/status/team. Deep links only — Leave remains the system of action; I will not approve or reject."
        )
        summary_ar = (
            f"طابور الإجازات: {total} طلب(ات) معلّقة في النطاق"
            + (f"، منها {high_n} عالية الأولوية (مراجعة/معلومات أو تعارض وردية)" if high_n else "")
            + ". مجمّعة حسب الموظف/الحالة/الفريق. روابط فقط — الإجازات تبقى نظام التنفيذ؛ لن أوافق أو أرفض."
        )
        confidence = "partial" if result.get("has_more") else "grounded"
        authority = "partial" if result.get("has_more") else "live_controlled"

    env = spine.grounded_envelope(
        ok=True,
        summary_en=summary_en,
        summary_ar=summary_ar,
        citations=citations[:15],
        authority_state=authority,
        data_freshness=spine.kuwait_now_iso(),
        confidence=confidence,
        locale=locale,
        deep_links=[{"page": "leave", "path": "/dashboard/posthire?tab=leave", "label_en": "Open Leave", "label_ar": "فتح الإجازات"}],
        proposed_actions=proposed[:8],
        payload={
            "total": total,
            "returned": len(rows),
            "has_more": bool(result.get("has_more")),
            "groups": groups,
            "urgent_count": len(urgent),
            "status_filter": result.get("status_filter") or action.get("status"),
            "window": {"start": result.get("start_date"), "end": result.get("end_date")},
            "mutates_records": False,
            "soa": "leave",
        },
        fallback_key="partial" if result.get("has_more") else None,
    )
    return spine._tool_result("summarize_leave_queue", env)


def execute_summarize_attendance_exceptions(ctx: Any) -> dict[str, Any]:
    locale = spine._locale_from_request(ctx.request)
    denied = wave2_preflight(ctx, required_permission="attendance.read")
    if denied:
        return spine._tool_result("summarize_attendance_exceptions", denied)

    legacy = ctx.legacy
    company = str((ctx.action or {}).get("company_code") or spine.ALLOWED_COMPANY).upper()
    action = dict(ctx.action or {})
    action.setdefault("company_code", company)
    if _viewer_phone(ctx):
        action["viewer_phone"] = _viewer_phone(ctx)
    query = str(action.get("query") or "").strip().lower()
    if query:
        action["prompt_text"] = query
    # Default: surface exception-like statuses when query implies it; else late+absent bias via status
    if not action.get("status"):
        if "absent" in query:
            action["status"] = "absent"
        elif "late" in query:
            action["status"] = "late"
        # else leave unset — we'll filter exception-like locally after fetch

    ingest_off = spine._flag_off("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
    try:
        if hasattr(legacy, "company_has_module") and not legacy.company_has_module(company, "attendance"):
            return spine._tool_result(
                "summarize_attendance_exceptions",
                spine.fallback_envelope(
                    "blocked",
                    locale=locale,
                    payload={"reason": "module_disabled", "module": "attendance"},
                ),
            )
        if not hasattr(legacy, "list_attendance"):
            return spine._tool_result(
                "summarize_attendance_exceptions",
                spine.fallback_envelope("unavailable", locale=locale),
            )
        result = legacy.list_attendance(action, company_code=company)
    except Exception as exc:
        return spine._tool_result(
            "summarize_attendance_exceptions",
            spine.fallback_envelope("unavailable", locale=locale, payload={"error": str(exc)[:200]}),
        )

    if not isinstance(result, dict) or not result.get("ok"):
        err = str((result or {}).get("error") or "attendance_list_failed")
        key = "blocked" if "scope" in err or "denied" in err else "unavailable"
        return spine._tool_result(
            "summarize_attendance_exceptions",
            spine.fallback_envelope(key, locale=locale, payload={"error": err}),
        )

    rows_all = [r for r in (result.get("attendance") or []) if isinstance(r, dict)]
    # Exception queue: late, absent, pending, or explicit exception flags — existing records only
    if action.get("status") in {"late", "absent", "pending"}:
        rows = rows_all
    else:
        rows = []
        for r in rows_all:
            status = str(r.get("status") or "")
            late = int(r.get("late_minutes") or 0)
            if status in {"absent", "pending", "late"} or late > 0:
                rows.append(r)
    total = len(rows)
    groups = _group_rows(rows)

    citations = []
    proposed = []
    for row in rows[:25]:
        status = str(row.get("status") or "")
        late = int(row.get("late_minutes") or 0)
        urgency = "high" if status == "absent" or late >= 30 else "medium"
        citations.append(
            {
                "kind": "attendance_record",
                "module": "attendance",
                "id": f"{row.get('employee_key')}:{row.get('attendance_date') or row.get('work_date')}",
                "label_en": f"{row.get('employee_name') or row.get('employee_key')} · {status}"
                + (f" · late {late}m" if late else ""),
                "label_ar": f"{row.get('employee_name') or row.get('employee_key')} · {status}",
                "as_of": spine.kuwait_now_iso(),
                "authority_state": "synthetic" if ingest_off else "live_controlled",
                "deep_link": {
                    "page": "attendance",
                    "employee_key": row.get("employee_key"),
                    "date": row.get("attendance_date") or row.get("work_date"),
                },
            }
        )
        proposed.append(
            {
                "kind": "deep_link",
                "module": "attendance",
                "label_en": f"Open attendance for {row.get('employee_name') or row.get('employee_key')}",
                "label_ar": f"افتح حضور {row.get('employee_name') or row.get('employee_key')}",
                "deep_link": {
                    "page": "attendance",
                    "employee_key": row.get("employee_key"),
                    "date": row.get("attendance_date") or row.get("work_date"),
                },
                "executes": False,
            }
        )

    ingest_note_en = (
        "Attendance device ingest is OFF — answers are based on existing attendance records only, not live device punches."
    )
    ingest_note_ar = (
        "استقبال أجهزة الحضور مغلق — الإجابات من سجلات الحضور الموجودة فقط، وليست من بصمات أجهزة حية."
    )

    if total == 0:
        summary_en = f"No attendance exceptions in scope for this window. {ingest_note_en}"
        summary_ar = f"لا استثناءات حضور في النطاق لهذه الفترة. {ingest_note_ar}"
        confidence = "grounded"
        authority = "synthetic" if ingest_off else "live_controlled"
    else:
        summary_en = (
            f"Attendance exceptions: {total} record(s) in scope (late/absent/pending). "
            f"Grouped by employee/status/team. Deep links only — Attendance remains the system of action; "
            f"I will not correct or mark absence. {ingest_note_en}"
        )
        summary_ar = (
            f"استثناءات الحضور: {total} سجل(ات) في النطاق (تأخير/غياب/معلّق). "
            f"مجمّعة حسب الموظف/الحالة/الفريق. روابط فقط — الحضور يبقى نظام التنفيذ؛ "
            f"لن أصحّح أو أسجّل غياباً. {ingest_note_ar}"
        )
        confidence = "partial" if result.get("has_more") else "grounded"
        authority = "partial" if result.get("has_more") else ("synthetic" if ingest_off else "live_controlled")

    env = spine.grounded_envelope(
        ok=True,
        summary_en=summary_en,
        summary_ar=summary_ar,
        citations=citations[:15],
        authority_state=authority,
        data_freshness=spine.kuwait_now_iso(),
        confidence=confidence,
        locale=locale,
        deep_links=[
            {
                "page": "attendance",
                "path": "/dashboard/posthire?tab=attendance",
                "label_en": "Open Attendance",
                "label_ar": "فتح الحضور",
            }
        ],
        proposed_actions=proposed[:8],
        payload={
            "total": total,
            "returned": len(rows),
            "scanned": len(rows_all),
            "has_more": bool(result.get("has_more")),
            "groups": groups,
            "window": {"start": result.get("start_date"), "end": result.get("end_date")},
            "capture_ingest": "off" if ingest_off else "on",
            "records_basis": "existing_records_only",
            "authority_version": result.get("authority"),
            "mutates_records": False,
            "soa": "attendance",
        },
        fallback_key="partial" if result.get("has_more") else None,
    )
    return spine._tool_result("summarize_attendance_exceptions", env)
