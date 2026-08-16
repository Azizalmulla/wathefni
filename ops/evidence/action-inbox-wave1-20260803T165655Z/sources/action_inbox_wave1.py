"""Post-Hire Differentiation Wave 1 — Unified Action Inbox.

Read-only composition of:
  - Analytics attention[]
  - Compliance findings[]
  - Employees 360 next actions

Inbox ranks and displays; frozen modules remain systems of action.
No mutations, no AI, no Hiring Reports, no Payroll money, no Compliance/Analytics Wave 2.
Alerts & Delivery owns notification delivery.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


ACTION_INBOX_WAVE1_VERSION = "1.0.0"
ACTION_INBOX_WAVE1_CONTRACT = "action_inbox_wave1"
ACTION_INBOX_SYNTHETIC_MARKERS_DEFAULT = ("AIW1", "AIW1-SYNTH|")
ACTION_INBOX_SYNTHETIC_PHONE_PREFIX_DEFAULT = ("965542",)

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SOURCE_PRIORITY = {"compliance": 0, "analytics": 1, "employees": 2}

KUWAIT_TZ = ZoneInfo("Asia/Kuwait")

DEFAULT_HR_OWNER = {
    "owner_role": "hr_ops",
    "owner_label_en": "Company HR",
    "owner_label_ar": "الموارد البشرية",
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def action_inbox_wave1_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1")
    if raw is None or str(raw).strip() == "":
        return True
    return _truthy(raw)


def action_inbox_wave1_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY")
    if raw is None or str(raw).strip() == "":
        return True
    return _truthy(raw)


def action_inbox_wave1_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES") or "WATHEFNI").strip()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def action_inbox_wave1_enabled_for_company(company_code: str | None) -> bool:
    if not action_inbox_wave1_enabled():
        return False
    company = (company_code or "WATHEFNI").upper()
    allowed = action_inbox_wave1_companies()
    return not allowed or company in allowed


def honesty_payload() -> dict[str, Any]:
    return {
        "wave": "action_inbox_wave1",
        "version": ACTION_INBOX_WAVE1_VERSION,
        "contract": ACTION_INBOX_WAVE1_CONTRACT,
        "read_only": True,
        "composes_only": True,
        "mutates_records": False,
        "ai": False,
        "hiring_reports_separate": True,
        "alerts_delivery_owns_notifications": True,
        "compliance_wave2": False,
        "analytics_wave2": False,
        "payroll_money": False,
        "attendance_ingest": False,
        "shifts_manager_expansion": False,
        "systems_of_action": [
            "analytics",
            "compliance",
            "employees",
            "onboarding",
            "attendance",
            "leave",
            "shifts",
            "payroll",
        ],
        "synthetic_only": action_inbox_wave1_synthetic_only(),
        "enabled": action_inbox_wave1_enabled(),
        "companies": sorted(action_inbox_wave1_companies()),
    }


def kuwait_window_payload() -> dict[str, Any]:
    now = datetime.now(KUWAIT_TZ)
    today = now.date()
    as_of = now.isoformat()
    return {
        "as_of": as_of,
        "timezone": "Asia/Kuwait",
        "kuwait_date": today.isoformat(),
        "window": {
            "kind": "kuwait_calendar_day",
            "label_en": "Kuwait calendar day (Asia/Kuwait)",
            "label_ar": "اليوم حسب تقويم الكويت (آسيا/الكويت)",
            "as_of_date": today.isoformat(),
        },
        "freshness": {
            "as_of": as_of,
            "max_age_seconds": 300,
            "stale_after_seconds": 300,
        },
    }


def _map_severity(raw: str | None) -> str:
    s = str(raw or "medium").strip().lower()
    if s in SEVERITY_RANK:
        return s
    if s == "critical":
        return "critical"
    return "medium"


def normalize_analytics_item(item: dict[str, Any]) -> dict[str, Any]:
    severity = _map_severity(item.get("severity"))
    # Analytics uses high/medium/low — promote high→high, keep
    deep = item.get("deep_link") if isinstance(item.get("deep_link"), dict) else {}
    page = str(deep.get("page") or item.get("source_module") or "analytics")
    soa = str(item.get("source_module") or page)
    return {
        "id": f"analytics:{item.get('id') or page}",
        "severity": severity if severity != "critical" else "high",
        "what_en": str(item.get("reason_en") or item.get("reason") or item.get("subject") or "Needs attention"),
        "what_ar": str(item.get("reason_ar") or item.get("reason_en") or item.get("reason") or "يحتاج انتباهاً"),
        "why_en": str(
            item.get("reason_en")
            or "Ranked workforce attention from Analytics (read-only)."
        ),
        "why_ar": str(
            item.get("reason_ar")
            or "انتباه مرتّب من التحليلات (قراءة فقط)."
        ),
        "employee_key": item.get("subject_key") or deep.get("employee"),
        "employee_name": item.get("subject"),
        "team": item.get("team"),
        "location": item.get("location"),
        "owner_role": DEFAULT_HR_OWNER["owner_role"],
        "owner_label_en": DEFAULT_HR_OWNER["owner_label_en"],
        "owner_label_ar": DEFAULT_HR_OWNER["owner_label_ar"],
        "deadline": None,
        "deadline_label_en": "Act from the system of action",
        "deadline_label_ar": "اتخذ إجراءً من نظام التنفيذ",
        "escalation_step": "open_system_of_action",
        "escalation_label_en": "Open the producing module — Analytics does not mutate records",
        "escalation_label_ar": "افتح الوحدة المنتجة — التحليلات لا تعدّل السجلات",
        "source_stream": "analytics",
        "source_module": soa,
        "system_of_action": soa,
        "evidence_status": "operational_signal",
        "evidence_status_label_en": "Operational attention signal (not money authority)",
        "evidence_status_label_ar": "إشارة تشغيلية (ليست سلطة دفع)",
        "authority_status": "read_projection",
        "authority_status_label_en": "Analytics read projection — frozen module remains authority",
        "authority_status_label_ar": "إسقاط قراءة من التحليلات — الوحدة المجمّدة تبقى السلطة",
        "government_verified": False,
        "deep_link": {
            "page": page,
            **({"employee": deep["employee"]} if deep.get("employee") else {}),
        },
        "clears_when": "source_attention_resolved",
        "alerts_delivery_owns_notifications": True,
    }


def normalize_compliance_finding(item: dict[str, Any]) -> dict[str, Any]:
    severity = _map_severity(item.get("severity"))
    deep = item.get("deep_link") if isinstance(item.get("deep_link"), dict) else {}
    page = str(deep.get("page") or item.get("system_of_action") or "compliance")
    doc_type = str(item.get("document_type_canonical") or item.get("document_type") or "")
    emp = str(item.get("employee_key") or item.get("subject_key") or "")
    return {
        "id": f"compliance:{item.get('id') or f'{emp}:{doc_type}'}",
        "severity": severity,
        "what_en": str(item.get("reason_en") or item.get("reason") or "Document finding"),
        "what_ar": str(item.get("reason_ar") or item.get("reason_en") or "نتيجة مستند"),
        "why_en": str(item.get("why_it_matters_en") or item.get("rule_label_en") or "Document compliance finding (guidance only)."),
        "why_ar": str(item.get("why_it_matters_ar") or item.get("rule_label_ar") or "نتيجة امتثال مستندي (إرشاد فقط)."),
        "employee_key": emp or None,
        "employee_name": item.get("employee_name") or item.get("subject"),
        "team": item.get("team"),
        "location": item.get("location"),
        "owner_role": item.get("owner_role") or "hr_compliance",
        "owner_label_en": item.get("owner_label_en") or "Company HR / Compliance",
        "owner_label_ar": item.get("owner_label_ar") or "الموارد البشرية / الامتثال",
        "deadline": item.get("deadline"),
        "deadline_label_en": item.get("deadline_label_en"),
        "deadline_label_ar": item.get("deadline_label_ar"),
        "escalation_step": item.get("escalation_step"),
        "escalation_label_en": item.get("escalation_label_en"),
        "escalation_label_ar": item.get("escalation_label_ar"),
        "source_stream": "compliance",
        "source_module": "compliance",
        "system_of_action": item.get("system_of_action") or page,
        "document_type": item.get("document_type"),
        "document_type_canonical": doc_type or None,
        "evidence_status": item.get("evidence_status"),
        "evidence_status_label_en": item.get("evidence_status_label_en"),
        "evidence_status_label_ar": item.get("evidence_status_label_ar"),
        "authority_status": "document_findings",
        "authority_status_label_en": "Document findings — never government verified",
        "authority_status_label_ar": "نتائج مستندات — ليست تحققاً حكومياً",
        "government_verified": False,
        "guidance_only": True,
        "deep_link": {
            "page": page,
            **({"employee": deep["employee"]} if deep.get("employee") else {}),
            **({"document_type": deep["document_type"]} if deep.get("document_type") else {}),
        },
        "secondary_links": item.get("secondary_links") or [],
        "clears_when": "compliance_finding_resolved",
        "alerts_delivery_owns_notifications": True,
    }


def normalize_e360_next_action(
    item: dict[str, Any],
    *,
    employee_key: str | None,
    employee_name: str | None,
    team: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    severity_raw = str(item.get("severity") or "medium").lower()
    # E360 uses critical/high/medium/low
    severity = _map_severity("high" if severity_raw == "critical" else severity_raw)
    if severity_raw == "critical":
        severity = "critical"
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    page = str(target.get("page") or item.get("page") or item.get("module") or "employees")
    module = str(item.get("module") or page)
    title = str(item.get("title") or item.get("label") or "Next action")
    reason = str(item.get("reason") or title)
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    doc_type = meta.get("document_type")
    return {
        "id": f"employees:{employee_key or 'unknown'}:{item.get('id') or title}",
        "severity": severity,
        "what_en": title,
        "what_ar": title,  # E360 next actions are EN today; UI can fall back
        "why_en": reason,
        "why_ar": reason,
        "employee_key": employee_key,
        "employee_name": employee_name,
        "team": team,
        "location": location,
        "owner_role": DEFAULT_HR_OWNER["owner_role"],
        "owner_label_en": DEFAULT_HR_OWNER["owner_label_en"],
        "owner_label_ar": DEFAULT_HR_OWNER["owner_label_ar"],
        "deadline": str(item.get("source_at"))[:10] if item.get("source_at") else None,
        "deadline_label_en": "See person profile / module",
        "deadline_label_ar": "راجع ملف الشخص / الوحدة",
        "escalation_step": "open_employees_or_module",
        "escalation_label_en": "Open Employees or the source module — inbox does not mutate",
        "escalation_label_ar": "افتح الموظفين أو وحدة المصدر — الصندوق لا يعدّل",
        "source_stream": "employees",
        "source_module": module,
        "system_of_action": page if page != "employees" else module,
        "document_type": doc_type,
        "evidence_status": "person_next_action",
        "evidence_status_label_en": "Employees 360 next action (composed from module reads)",
        "evidence_status_label_ar": "إجراء تالي من ملف 360 (مركّب من قراءات الوحدات)",
        "authority_status": "person_projection",
        "authority_status_label_en": "Person projection — frozen module remains authority",
        "authority_status_label_ar": "إسقاط شخص — الوحدة المجمّدة تبقى السلطة",
        "government_verified": False,
        "deep_link": {
            "page": "employees" if page in {"employees", "workforce"} else page,
            **({"employee": employee_key} if employee_key else {}),
        },
        "clears_when": "e360_next_action_cleared",
        "alerts_delivery_owns_notifications": True,
        "executable_in_source": bool(item.get("executable")),
    }


def compliance_dedupe_key(item: dict[str, Any]) -> tuple[str, str] | None:
    emp = str(item.get("employee_key") or "").strip()
    doc = str(
        item.get("document_type_canonical")
        or item.get("document_type")
        or ""
    ).strip().lower()
    if not emp or not doc:
        return None
    if doc in {"residency", "residency_iqama"}:
        doc = "residence"
    return (emp, doc)


def rank_inbox_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(row: dict[str, Any]) -> tuple:
        sev = SEVERITY_RANK.get(str(row.get("severity") or "low"), 9)
        src = SOURCE_PRIORITY.get(str(row.get("source_stream") or ""), 9)
        deadline = str(row.get("deadline") or "9999-99-99")
        return (sev, src, deadline, str(row.get("what_en") or ""))

    return sorted(items, key=sort_key)


def build_action_inbox(
    *,
    analytics_attention: list[dict[str, Any]] | None = None,
    compliance_findings: list[dict[str, Any]] | None = None,
    e360_next_actions: list[dict[str, Any]] | None = None,
    sources_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose and rank inbox items. Dedupes E360 compliance rows covered by findings."""
    normalized: list[dict[str, Any]] = []
    for item in analytics_attention or []:
        if isinstance(item, dict):
            normalized.append(normalize_analytics_item(item))

    finding_keys: set[tuple[str, str]] = set()
    for item in compliance_findings or []:
        if not isinstance(item, dict):
            continue
        row = normalize_compliance_finding(item)
        normalized.append(row)
        key = compliance_dedupe_key(row)
        if key:
            finding_keys.add(key)

    skipped_e360_dupes = 0
    for item in e360_next_actions or []:
        if not isinstance(item, dict):
            continue
        # Pre-normalized E360 rows already have source_stream=employees
        if item.get("source_stream") == "employees":
            row = item
        else:
            row = normalize_e360_next_action(
                item,
                employee_key=item.get("employee_key"),
                employee_name=item.get("employee_name"),
                team=item.get("team"),
                location=item.get("location"),
            )
        if str(row.get("source_module") or "") == "compliance":
            key = compliance_dedupe_key(row)
            if key and key in finding_keys:
                skipped_e360_dupes += 1
                continue
        normalized.append(row)

    ranked = rank_inbox_items(normalized)
    window = kuwait_window_payload()
    by_stream = {"analytics": 0, "compliance": 0, "employees": 0}
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for row in ranked:
        stream = str(row.get("source_stream") or "")
        if stream in by_stream:
            by_stream[stream] += 1
        sev = str(row.get("severity") or "low")
        if sev in by_severity:
            by_severity[sev] += 1

    meta = sources_meta if isinstance(sources_meta, dict) else {}
    return {
        **window,
        "contract": ACTION_INBOX_WAVE1_CONTRACT,
        "contract_version": ACTION_INBOX_WAVE1_VERSION,
        "items": ranked,
        "summary": {
            "total": len(ranked),
            "by_stream": by_stream,
            "by_severity": by_severity,
            "deduped_e360_compliance": skipped_e360_dupes,
        },
        "sources": meta,
        "honesty": honesty_payload(),
        "authority": {
            "read_only": True,
            "composes_only": True,
            "mutates_records": False,
            "alerts_delivery_owns_notifications": True,
            "hiring_reports_separate": True,
            "ai": False,
            "payroll_money": False,
            "systems_of_action_frozen": True,
            "wave1_enabled": action_inbox_wave1_enabled(),
            "synthetic_only": action_inbox_wave1_synthetic_only(),
        },
        "definitions": [
            {
                "key": "authority",
                "label_en": "Authority",
                "label_ar": "السلطة",
                "definition_en": (
                    "Action Inbox only composes and ranks. Analytics, Compliance, Employees, "
                    "Onboarding, Attendance, Leave, Shifts, and Payroll remain systems of action. "
                    "Alerts & Delivery owns notifications. Hiring Reports stay separate."
                ),
                "definition_ar": (
                    "صندوق الإجراءات يركّب ويرتّب فقط. التحليلات والامتثال والموظفون والتهيئة "
                    "والحضور والإجازات والورديات والرواتب تبقى أنظمة التنفيذ. التنبيهات تملك الإشعارات."
                ),
            },
            {
                "key": "clears",
                "label_en": "Clearing",
                "label_ar": "الإزالة",
                "definition_en": "Items disappear when the source module no longer reports them — complete the action in the system of action.",
                "definition_ar": "تختفي العناصر عندما تتوقف وحدة المصدر عن الإبلاغ عنها — أكمل الإجراء في نظام التنفيذ.",
            },
        ],
    }


def prove_item_clears_when_source_resolves() -> dict[str, Any]:
    """Offline proof: inbox shrinks when source lists shrink."""
    attention = [
        {
            "id": "pending_leave",
            "severity": "high",
            "reason_en": "1 leave request awaits a decision",
            "reason_ar": "طلب إجازة بانتظار القرار",
            "subject": "Leave queue",
            "source_module": "leave",
            "deep_link": {"page": "leave"},
        }
    ]
    findings = [
        {
            "id": "expired:E1:residence",
            "severity": "high",
            "reason_en": "Alice residence expired",
            "reason_ar": "إقامة Alice منتهية",
            "employee_key": "E1",
            "employee_name": "Alice",
            "document_type": "residence",
            "document_type_canonical": "residence",
            "system_of_action": "compliance",
            "deep_link": {"page": "compliance", "employee": "E1"},
            "evidence_status": "expired",
            "owner_role": "hr_compliance",
            "government_verified": False,
            "guidance_only": True,
        }
    ]
    e360 = [
        normalize_e360_next_action(
            {
                "id": "compliance:expired:residence",
                "severity": "critical",
                "module": "compliance",
                "title": "Residence expired",
                "reason": "Document has expired",
                "target": {"page": "compliance", "section": "compliance"},
                "meta": {"document_type": "residence"},
            },
            employee_key="E1",
            employee_name="Alice",
        ),
        normalize_e360_next_action(
            {
                "id": "onboarding:incomplete",
                "severity": "medium",
                "module": "onboarding",
                "title": "Onboarding incomplete",
                "reason": "2 required items still open",
                "target": {"page": "onboarding", "section": "onboarding"},
            },
            employee_key="E1",
            employee_name="Alice",
        ),
    ]
    before = build_action_inbox(
        analytics_attention=attention,
        compliance_findings=findings,
        e360_next_actions=e360,
    )
    # Resolve sources: leave decided, residence renewed, onboarding still open
    after = build_action_inbox(
        analytics_attention=[],
        compliance_findings=[],
        e360_next_actions=[e360[1]],
    )
    return {
        "before_total": before["summary"]["total"],
        "after_total": after["summary"]["total"],
        "deduped": before["summary"]["deduped_e360_compliance"],
        "cleared": before["summary"]["total"] > after["summary"]["total"],
        "remaining_ids": [i["id"] for i in after["items"]],
    }
