"""Compliance Wave 1 — Document Findings Contract.

Ranked document findings for HR: what is wrong, why it matters (guidance-only),
who owns the next action, deadline, escalation step, and which frozen module is
the system of action.

Document compliance only. Never government verification, filing, fine authority,
or automatic legal-compliance claims. Alerts & Delivery owns reminder delivery.
Analytics must not absorb Compliance metrics.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


COMPLIANCE_WAVE1_VERSION = "1.0.0"
COMPLIANCE_WAVE1_CONTRACT = "compliance_findings_wave1"
COMPLIANCE_WAVE1_SYNTHETIC_MARKERS_DEFAULT = ("CFW1", "CFW1-SYNTH|")
COMPLIANCE_WAVE1_SYNTHETIC_PHONE_PREFIX_DEFAULT = ("965541",)

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

KUWAIT_TZ = ZoneInfo("Asia/Kuwait")

# Canonical vocabulary (Kuwait). Legacy aliases stay readable; new writes use these.
CANONICAL_RESIDENCE = "residence"
LEGACY_RESIDENCE_ALIASES = frozenset({"residency", "residency_iqama"})
RESIDENCE_FAMILY = frozenset({CANONICAL_RESIDENCE}) | LEGACY_RESIDENCE_ALIASES

DEFAULT_HR_OWNER = {
    "owner_role": "hr_compliance",
    "owner_label_en": "Company HR / Compliance",
    "owner_label_ar": "الموارد البشرية / الامتثال",
}

# Configurable per document type; defaults to company HR/compliance role.
# Override via WATHEFNI_COMPLIANCE_OWNER_BY_TYPE JSON: {"civil_id":{"owner_role":"...","owner_label_en":"...","owner_label_ar":"..."}}
DOCUMENT_OWNER_DEFAULTS: dict[str, dict[str, str]] = {
    "civil_id": dict(DEFAULT_HR_OWNER),
    "passport": dict(DEFAULT_HR_OWNER),
    "residence": dict(DEFAULT_HR_OWNER),
    "residency": dict(DEFAULT_HR_OWNER),
    "residency_iqama": dict(DEFAULT_HR_OWNER),
    "work_permit": dict(DEFAULT_HR_OWNER),
    "medical": dict(DEFAULT_HR_OWNER),
    "education_cert": dict(DEFAULT_HR_OWNER),
    "employment_contract": dict(DEFAULT_HR_OWNER),
}

# Guidance-only rule labels (not legal enforcement, not government verification).
RULE_GUIDANCE: dict[str, dict[str, str]] = {
    "civil_id": {
        "rule_id": "kw.paci.civil_id.track",
        "authority": "PACI",
        "label_en": "Civil ID tracking (PACI) — guidance only",
        "label_ar": "تتبع البطاقة المدنية (الهيئة العامة للمعلومات المدنية) — إرشاد فقط",
    },
    "passport": {
        "rule_id": "kw.passport.track",
        "authority": "Embassy / Home Country",
        "label_en": "Passport validity tracking — guidance only",
        "label_ar": "تتبع صلاحية جواز السفر — إرشاد فقط",
    },
    "residence": {
        "rule_id": "kw.moi.residence.track",
        "authority": "MOI",
        "label_en": "Residence permit tracking (MOI) — guidance only",
        "label_ar": "تتبع الإقامة (وزارة الداخلية) — إرشاد فقط",
    },
    "work_permit": {
        "rule_id": "kw.pam.work_permit.track",
        "authority": "PAM",
        "label_en": "Work permit tracking (PAM) — guidance only",
        "label_ar": "تتبع إذن العمل (هيئة القوى العاملة) — إرشاد فقط",
    },
    "medical": {
        "rule_id": "kw.moh.medical.track",
        "authority": "MOH",
        "label_en": "Medical fitness certificate tracking — guidance only",
        "label_ar": "تتبع شهادة اللياقة الطبية — إرشاد فقط",
    },
    "education_cert": {
        "rule_id": "employer.education_cert.track",
        "authority": "Employer policy",
        "label_en": "Education certificate tracking — employer policy guidance",
        "label_ar": "تتبع الشهادة التعليمية — إرشاد سياسة صاحب العمل",
    },
    "employment_contract": {
        "rule_id": "employer.contract.track",
        "authority": "Employer policy",
        "label_en": "Employment contract tracking — employer policy guidance",
        "label_ar": "تتبع عقد العمل — إرشاد سياسة صاحب العمل",
    },
}

DOC_LABELS_EN = {
    "civil_id": "Civil ID",
    "passport": "Passport",
    "residence": "Residence",
    "residency": "Residence",
    "residency_iqama": "Residence (legacy id)",
    "work_permit": "Work permit",
    "medical": "Medical certificate",
    "education_cert": "Education certificate",
    "employment_contract": "Employment contract",
}

DOC_LABELS_AR = {
    "civil_id": "البطاقة المدنية",
    "passport": "جواز السفر",
    "residence": "الإقامة",
    "residency": "الإقامة",
    "residency_iqama": "الإقامة (معرّف قديم)",
    "work_permit": "إذن العمل",
    "medical": "الشهادة الطبية",
    "education_cert": "الشهادة التعليمية",
    "employment_contract": "عقد العمل",
}

EVIDENCE_STATUS_LABELS = {
    "missing": {"en": "Missing", "ar": "ناقص"},
    "uploaded": {"en": "Uploaded — pending HR review", "ar": "مرفوع — بانتظار مراجعة الموارد البشرية"},
    "hr_reviewed": {"en": "HR reviewed (not government verified)", "ar": "مراجعة موارد بشرية (ليست تحققاً حكومياً)"},
    "expired": {"en": "Expired", "ar": "منتهي"},
    "expiring": {"en": "Expiring soon", "ar": "ينتهي قريباً"},
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def compliance_wave1_enabled() -> bool:
    # Staging/default: on when unset so Findings Contract ships with the code path.
    # Production synthetic posture should set the flag explicitly.
    raw = os.environ.get("WATHEFNI_COMPLIANCE_WAVE1")
    if raw is None or str(raw).strip() == "":
        return True
    return _truthy(raw)


def compliance_wave1_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_ONLY")
    if raw is None or str(raw).strip() == "":
        return True
    return _truthy(raw)


def compliance_wave1_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_COMPLIANCE_WAVE1_COMPANIES") or "WATHEFNI").strip()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def compliance_wave1_enabled_for_company(company_code: str | None) -> bool:
    if not compliance_wave1_enabled():
        return False
    company = (company_code or "WATHEFNI").upper()
    allowed = compliance_wave1_companies()
    return not allowed or company in allowed


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(
        os.environ.get("WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_KEY_MARKERS")
        or ",".join(COMPLIANCE_WAVE1_SYNTHETIC_MARKERS_DEFAULT)
    )
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    return parts or COMPLIANCE_WAVE1_SYNTHETIC_MARKERS_DEFAULT


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(
        os.environ.get("WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_PHONE_PREFIXES")
        or ",".join(COMPLIANCE_WAVE1_SYNTHETIC_PHONE_PREFIX_DEFAULT)
    )
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    return parts or COMPLIANCE_WAVE1_SYNTHETIC_PHONE_PREFIX_DEFAULT


def is_synthetic_subject(*, employee_key: str | None = None, phone: str | None = None) -> bool:
    key = str(employee_key or "")
    if any(marker in key for marker in synthetic_key_markers()):
        return True
    phone_s = str(phone or "")
    return any(phone_s.startswith(prefix) for prefix in synthetic_phone_prefixes())


def honesty_payload() -> dict[str, Any]:
    return {
        "wave": "compliance_wave1",
        "version": COMPLIANCE_WAVE1_VERSION,
        "contract": COMPLIANCE_WAVE1_CONTRACT,
        "document_compliance_only": True,
        "government_verified": False,
        "government_apis": False,
        "filing": False,
        "fine_calculations": False,
        "legal_compliance_claims": False,
        "ai": False,
        "analytics_excludes_compliance": True,
        "alerts_delivery_owns_reminders": True,
        "systems_of_action": ["compliance", "onboarding", "employees"],
        "synthetic_only": compliance_wave1_synthetic_only(),
        "enabled": compliance_wave1_enabled(),
        "companies": sorted(compliance_wave1_companies()),
        "evidence_classes": ["missing", "uploaded", "hr_reviewed", "expired", "expiring"],
        "never_government_verified": True,
    }


def ensure_compliance_wave1_schema(cur: Any, *, force: bool = False) -> None:
    """Additive ACK table only. No frozen-module schema changes."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_wave_acks (
          ack_id bigserial PRIMARY KEY,
          company_code text NOT NULL,
          wave text NOT NULL,
          contract text NOT NULL,
          environment text NOT NULL,
          synthetic_only boolean NOT NULL DEFAULT true,
          details jsonb NOT NULL DEFAULT '{}'::jsonb,
          canary_tag text,
          acknowledged_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS compliance_wave_acks_company_wave_idx
          ON compliance_wave_acks (company_code, wave, acknowledged_at DESC)
        """
    )
    if force:
        cur.execute("SELECT to_regclass('public.compliance_wave_acks') AS reg")
        row = dict(cur.fetchone() or {})
        if not row.get("reg"):
            raise RuntimeError("compliance_wave_acks missing after ensure")


def record_compliance_wave_ack(
    cur: Any,
    *,
    company_code: str,
    environment: str,
    details: dict[str, Any] | None = None,
    canary_tag: str | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO compliance_wave_acks (
          company_code, wave, contract, environment, synthetic_only, details, canary_tag
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
        RETURNING ack_id, company_code, wave, contract, environment, synthetic_only, canary_tag, acknowledged_at
        """,
        (
            (company_code or "WATHEFNI").upper(),
            "compliance_wave1",
            COMPLIANCE_WAVE1_CONTRACT,
            environment,
            compliance_wave1_synthetic_only(),
            json.dumps(details or honesty_payload()),
            canary_tag,
        ),
    )
    return dict(cur.fetchone() or {})


def residual_synthetic_acks(cur: Any, *, company_code: str, tag: str) -> int:
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM compliance_wave_acks
        WHERE company_code=%s
          AND canary_tag=%s
          AND wave='compliance_wave1'
        """,
        ((company_code or "WATHEFNI").upper(), tag),
    )
    return int(dict(cur.fetchone() or {}).get("n") or 0)


def cleanup_canary_acks(cur: Any, *, company_code: str, tag: str) -> int:
    cur.execute(
        """
        DELETE FROM compliance_wave_acks
        WHERE company_code=%s
          AND canary_tag=%s
          AND wave='compliance_wave1'
        """,
        ((company_code or "WATHEFNI").upper(), tag),
    )
    return int(cur.rowcount or 0)


def canonicalize_document_type(document_type: str | None) -> str:
    raw = str(document_type or "").strip().lower()
    if raw in LEGACY_RESIDENCE_ALIASES or raw == CANONICAL_RESIDENCE:
        return CANONICAL_RESIDENCE
    return raw


def document_label(document_type: str | None, *, locale: str = "en") -> str:
    raw = str(document_type or "").strip().lower()
    canon = canonicalize_document_type(raw)
    table = DOC_LABELS_AR if str(locale).lower().startswith("ar") else DOC_LABELS_EN
    return table.get(raw) or table.get(canon) or (document_type or "Document")


def owner_for_document_type(document_type: str | None) -> dict[str, str]:
    overrides: dict[str, Any] = {}
    raw = str(os.environ.get("WATHEFNI_COMPLIANCE_OWNER_BY_TYPE") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                overrides = parsed
        except Exception:
            overrides = {}
    canon = canonicalize_document_type(document_type)
    raw_type = str(document_type or "").strip().lower()
    chosen = overrides.get(raw_type) or overrides.get(canon) or DOCUMENT_OWNER_DEFAULTS.get(raw_type) or DOCUMENT_OWNER_DEFAULTS.get(canon)
    if isinstance(chosen, dict) and chosen.get("owner_role"):
        return {
            "owner_role": str(chosen.get("owner_role") or DEFAULT_HR_OWNER["owner_role"]),
            "owner_label_en": str(chosen.get("owner_label_en") or DEFAULT_HR_OWNER["owner_label_en"]),
            "owner_label_ar": str(chosen.get("owner_label_ar") or DEFAULT_HR_OWNER["owner_label_ar"]),
        }
    return dict(DEFAULT_HR_OWNER)


def rule_guidance_for(document_type: str | None) -> dict[str, Any]:
    canon = canonicalize_document_type(document_type)
    base = RULE_GUIDANCE.get(canon) or {
        "rule_id": f"employer.{canon or 'document'}.track",
        "authority": "Employer policy",
        "label_en": f"{document_label(document_type)} tracking — guidance only",
        "label_ar": f"تتبع {document_label(document_type, locale='ar')} — إرشاد فقط",
    }
    return {
        **base,
        "guidance_only": True,
        "legal_compliance_claim": False,
        "government_verified": False,
    }


def kuwait_now() -> datetime:
    return datetime.now(KUWAIT_TZ)


def kuwait_today() -> date:
    return kuwait_now().date()


def kuwait_window_payload() -> dict[str, Any]:
    today = kuwait_today()
    month_start = today.replace(day=1)
    as_of = kuwait_now().isoformat()
    return {
        "as_of": as_of,
        "timezone": "Asia/Kuwait",
        "kuwait_date": today.isoformat(),
        "window": {
            "kind": "kuwait_calendar_day",
            "label_en": "Kuwait calendar day (Asia/Kuwait)",
            "label_ar": "اليوم حسب تقويم الكويت (آسيا/الكويت)",
            "start_date": month_start.isoformat(),
            "end_date": today.isoformat(),
            "as_of_date": today.isoformat(),
        },
        "freshness": {
            "as_of": as_of,
            "max_age_seconds": 300,
            "stale_after_seconds": 300,
        },
    }


def evidence_status_for(
    *,
    bucket: str,
    has_file: bool,
) -> str:
    """Honest evidence class — never government_verified."""
    if bucket == "expired":
        return "expired"
    if bucket == "expiring_soon":
        return "expiring"
    if bucket == "missing":
        return "missing"
    if bucket == "needs_review":
        return "uploaded" if has_file else "uploaded"
    if bucket == "valid":
        return "hr_reviewed"
    return "missing"


def escalation_for(*, bucket: str, days_until_expiry: int | None) -> dict[str, str]:
    """Product escalation ladder (guidance). Delivery remains Alerts & Delivery."""
    if bucket == "expired":
        return {
            "step": "overdue_daily",
            "label_en": "Overdue — daily HR follow-up until resolved (alerts deliver reminders)",
            "label_ar": "متأخر — متابعة يومية من الموارد البشرية حتى الحل (التنبيهات توصل التذكيرات)",
        }
    if bucket == "needs_review":
        return {
            "step": "hr_review",
            "label_en": "HR must review uploaded evidence (not government verification)",
            "label_ar": "يجب على الموارد البشرية مراجعة الدليل المرفوع (ليست تحققاً حكومياً)",
        }
    if bucket == "missing":
        return {
            "step": "request_document",
            "label_en": "Request document via Onboarding / Compliance; Alerts deliver the reminder",
            "label_ar": "اطلب المستند عبر التهيئة / الامتثال؛ التنبيهات توصل التذكير",
        }
    days = days_until_expiry
    if days is not None and days <= 7:
        return {
            "step": "critical_hr",
            "label_en": "Critical — escalate to HR owner; daily follow-up",
            "label_ar": "حرج — صعّد إلى مالك الموارد البشرية؛ متابعة يومية",
        }
    if days is not None and days <= 15:
        return {
            "step": "urgent_hr",
            "label_en": "Urgent — HR follow-up if no employee response",
            "label_ar": "عاجل — متابعة الموارد البشرية إن لم يستجب الموظف",
        }
    return {
        "step": "notify_hr_and_employee",
        "label_en": "Notify HR and employee; Alerts & Delivery owns reminder delivery",
        "label_ar": "أبلغ الموارد البشرية والموظف؛ التنبيهات والتسليم تملك توصيل التذكير",
    }


def system_of_action_for(bucket: str) -> dict[str, str]:
    """Read-only deep-link target. Mutations stay in the destination module."""
    if bucket == "missing":
        return {
            "module": "onboarding",
            "page": "onboarding",
            "why_en": "Collect the missing document in Onboarding",
            "why_ar": "اجمع المستند الناقص من التهيئة",
        }
    if bucket == "needs_review":
        return {
            "module": "compliance",
            "page": "compliance",
            "why_en": "Review uploaded evidence in Compliance",
            "why_ar": "راجع الدليل المرفوع في الامتثال",
        }
    # expired / expiring — Compliance owns expiry authority; Employees for person context
    return {
        "module": "compliance",
        "page": "compliance",
        "why_en": "Track renewal in Compliance; open Employees for person context",
        "why_ar": "تابع التجديد في الامتثال؛ افتح الموظفين لسياق الشخص",
    }


def compliance_metric_definitions() -> list[dict[str, str]]:
    return [
        {
            "key": "authority",
            "label_en": "Authority",
            "label_ar": "السلطة",
            "definition_en": (
                "Compliance Findings are a document-tracking projection. "
                "HR-reviewed means uploaded evidence was reviewed by HR — never government verified. "
                "No filing, fines, or legal-compliance claims. Alerts & Delivery owns reminder delivery. "
                "Onboarding collects; Compliance owns expiry; Employees holds person context. Analytics excludes Compliance."
            ),
            "definition_ar": (
                "نتائج الامتثال إسقاط لتتبع المستندات. "
                "مراجعة الموارد البشرية تعني مراجعة دليل مرفوع — وليست تحققاً حكومياً. "
                "لا تقديم ولا غرامات ولا ادعاءات امتثال قانوني. التنبيهات تملك توصيل التذكيرات. "
                "التهيئة تجمع؛ الامتثال يملك الانتهاء؛ الموظفون يحتفظون بسياق الشخص. التحليلات تستثني الامتثال."
            ),
        },
        {
            "key": "evidence",
            "label_en": "Evidence status",
            "label_ar": "حالة الدليل",
            "definition_en": "missing · uploaded · HR reviewed · expired/expiring. Never government verified.",
            "definition_ar": "ناقص · مرفوع · مراجعة موارد بشرية · منتهي/ينتهي. ليست تحققاً حكومياً أبداً.",
        },
        {
            "key": "owner",
            "label_en": "Owner",
            "label_ar": "المالك",
            "definition_en": "Default owner is the company HR / Compliance role; configurable per document type.",
            "definition_ar": "المالك الافتراضي هو دور الموارد البشرية / الامتثال؛ قابل للضبط حسب نوع المستند.",
        },
        {
            "key": "escalation",
            "label_en": "Escalation",
            "label_ar": "التصعيد",
            "definition_en": "Product escalation ladder (guidance). Reminder delivery remains Alerts & Delivery.",
            "definition_ar": "سلم تصعيد المنتج (إرشاد). توصيل التذكير يبقى لدى التنبيهات والتسليم.",
        },
    ]


def source_availability(enabled_modules: set[str] | list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    enabled = {str(m).strip().lower() for m in (enabled_modules or []) if str(m).strip()}

    def _src(module: str, *, note_en: str, note_ar: str) -> dict[str, Any]:
        available = module in enabled
        return {
            "module": module,
            "available": available,
            "status": "live" if available else "unavailable",
            "note_en": note_en if available else f"{module} is not enabled for this company.",
            "note_ar": note_ar if available else f"وحدة {module} غير مفعّلة لهذه الشركة.",
        }

    sources = {
        "compliance": _src(
            "compliance",
            note_en="Document expiry and HR review from compliance_documents.",
            note_ar="انتهاء المستندات ومراجعة الموارد البشرية من compliance_documents.",
        ),
        "onboarding": _src(
            "onboarding",
            note_en="Document collection checklist (system of action for missing docs).",
            note_ar="قائمة جمع المستندات (نظام التنفيذ للمستندات الناقصة).",
        ),
        "employees": _src(
            "employees",
            note_en="Person context drill-through.",
            note_ar="الانتقال لسياق الشخص.",
        ),
        "alerts": {
            "module": "alerts",
            "available": True,
            "status": "delivery_only",
            "note_en": "Alerts & Delivery owns reminder delivery — not findings ranking.",
            "note_ar": "التنبيهات والتسليم تملك توصيل التذكير — وليست ترتيب النتائج.",
        },
    }
    # Employees directory is usable whenever people modules are on.
    if not sources["employees"]["available"] and enabled & {"compliance", "onboarding", "attendance", "leave", "shifts", "payroll"}:
        sources["employees"] = {
            **sources["employees"],
            "available": True,
            "status": "live",
            "note_en": "Person drill-through uses the Employees directory (people surface).",
            "note_ar": "الانتقال للشخص يستخدم دليل الموظفين.",
        }
    unavailable = [key for key, row in sources.items() if not row.get("available") and key != "alerts"]
    return {
        "sources": sources,
        "unavailable_source_keys": unavailable,
        "partial": bool(unavailable),
    }


def location_team_from_employee(employee_row: dict[str, Any] | None, card: dict[str, Any] | None) -> tuple[str | None, str | None]:
    data = employee_row if isinstance(employee_row, dict) else {}
    card_d = card if isinstance(card, dict) else {}
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    raw = data.get("raw_json") if isinstance(data.get("raw_json"), dict) else {}
    location = (
        data.get("branch_name")
        or profile.get("branch_name")
        or profile.get("branch")
        or raw.get("branch_name")
        or raw.get("branch")
        or None
    )
    team = (
        data.get("team_name")
        or profile.get("team_name")
        or profile.get("team")
        or card_d.get("department")
        or profile.get("department")
        or raw.get("team")
        or raw.get("department")
        or None
    )
    loc_s = str(location).strip() if location else None
    team_s = str(team).strip() if team else None
    return (loc_s or None, team_s or None)


def build_finding_from_document(
    *,
    document: dict[str, Any],
    employee_row: dict[str, Any] | None = None,
    sources: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build one ranked finding. Valid/HR-reviewed docs are omitted from attention."""
    bucket = str(document.get("status") or "").strip().lower()
    if bucket == "valid":
        return None
    if bucket not in {"expired", "expiring_soon", "missing", "needs_review"}:
        return None

    doc_type = str(document.get("document_type") or "")
    canon = canonicalize_document_type(doc_type)
    name = str(document.get("employee_name") or "Employee")
    employee_key = str(document.get("employee_key") or "") or None
    label_en = document_label(doc_type, locale="en")
    label_ar = document_label(doc_type, locale="ar")
    days = document.get("days_until_expiry")
    days_i = int(days) if days is not None else None
    expiry = document.get("expiry_date")
    expiry_s = str(expiry)[:10] if expiry else None
    has_file = bool(document.get("file_id"))
    evidence = evidence_status_for(bucket=bucket, has_file=has_file)
    owner = owner_for_document_type(doc_type)
    rule = rule_guidance_for(doc_type)
    escalation = escalation_for(bucket=bucket, days_until_expiry=days_i)
    soa = system_of_action_for(bucket)
    location, team = location_team_from_employee(employee_row, document)

    src_map = {}
    if isinstance(sources, dict):
        src_map = sources.get("sources") if isinstance(sources.get("sources"), dict) else sources

    # Severity
    if bucket == "expired":
        severity = "high"
        reason_en = f"{name}'s {label_en} is expired"
        reason_ar = f"{label_ar} لـ {name} منتهية"
        if days_i is not None:
            reason_en += f" by {abs(days_i)} day{'s' if abs(days_i) != 1 else ''}"
            reason_ar += f" منذ {abs(days_i)} يوم"
        deadline = kuwait_today().isoformat()
        deadline_label_en = "Overdue — act today"
        deadline_label_ar = "متأخر — اتخذ إجراءً اليوم"
    elif bucket == "expiring_soon":
        severity = "high" if days_i is not None and days_i <= 7 else "medium"
        reason_en = f"{name}'s {label_en} expires soon"
        reason_ar = f"{label_ar} لـ {name} تنتهي قريباً"
        if days_i is not None:
            reason_en += f" ({days_i} day{'s' if days_i != 1 else ''} left)"
            reason_ar += f" (متبقي {days_i} يوم)"
        deadline = expiry_s
        deadline_label_en = f"Renew before {expiry_s}" if expiry_s else "Renew before expiry"
        deadline_label_ar = f"جدّد قبل {expiry_s}" if expiry_s else "جدّد قبل الانتهاء"
    elif bucket == "needs_review":
        severity = "medium"
        reason_en = f"{name}'s {label_en} needs HR review (expiry could not be confirmed)"
        reason_ar = f"{label_ar} لـ {name} تحتاج مراجعة الموارد البشرية (تعذر تأكيد الانتهاء)"
        deadline = (kuwait_today() + timedelta(days=3)).isoformat()
        deadline_label_en = "Review within 3 days"
        deadline_label_ar = "راجع خلال 3 أيام"
    else:  # missing
        severity = "medium"
        reason_en = f"{name}'s {label_en} is missing"
        reason_ar = f"{label_ar} لـ {name} ناقصة"
        deadline = (kuwait_today() + timedelta(days=7)).isoformat()
        deadline_label_en = "Request within 7 days"
        deadline_label_ar = "اطلب خلال 7 أيام"

    why_en = (
        f"Tracked under {rule.get('authority')} guidance. "
        f"Evidence status: {EVIDENCE_STATUS_LABELS[evidence]['en']}. "
        "Not government verified."
    )
    why_ar = (
        f"يُتتبع وفق إرشاد {rule.get('authority')}. "
        f"حالة الدليل: {EVIDENCE_STATUS_LABELS[evidence]['ar']}. "
        "ليست تحققاً حكومياً."
    )

    # Deep links: primary SoA + Employees person context when available
    page = soa["page"]
    if page == "onboarding" and src_map and not src_map.get("onboarding", {}).get("available"):
        page = "compliance"
    deep_link = {
        "page": page,
        "module": soa["module"] if page == soa["page"] else "compliance",
    }
    if employee_key:
        deep_link["employee"] = employee_key
    if doc_type:
        deep_link["document_type"] = canon or doc_type

    secondary_links: list[dict[str, str]] = []
    if employee_key and (not src_map or src_map.get("employees", {}).get("available", True)):
        secondary_links.append({"page": "employees", "employee": employee_key, "label_en": "Open employee", "label_ar": "افتح الموظف"})
    if page != "compliance":
        secondary_links.append(
            {
                "page": "compliance",
                "employee": employee_key or "",
                "document_type": canon or doc_type,
                "label_en": "Open Compliance",
                "label_ar": "افتح الامتثال",
            }
        )

    finding_id = f"{bucket}:{employee_key or 'unknown'}:{canon or doc_type or 'doc'}"
    return {
        "id": finding_id,
        "severity": severity,
        "reason": reason_en,
        "reason_en": reason_en,
        "reason_ar": reason_ar,
        "why_it_matters_en": why_en,
        "why_it_matters_ar": why_ar,
        "subject": name,
        "subject_key": employee_key,
        "employee_key": employee_key,
        "employee_name": name,
        "location": location,
        "team": team,
        "document_type": doc_type,
        "document_type_canonical": canon,
        "document_label": label_en,
        "document_label_en": label_en,
        "document_label_ar": label_ar,
        "bucket": bucket,
        "evidence_status": evidence,
        "evidence_status_label_en": EVIDENCE_STATUS_LABELS[evidence]["en"],
        "evidence_status_label_ar": EVIDENCE_STATUS_LABELS[evidence]["ar"],
        "government_verified": False,
        "rule": rule,
        "rule_label_en": rule.get("label_en"),
        "rule_label_ar": rule.get("label_ar"),
        "guidance_only": True,
        "owner_role": owner["owner_role"],
        "owner_label_en": owner["owner_label_en"],
        "owner_label_ar": owner["owner_label_ar"],
        "deadline": deadline,
        "deadline_label_en": deadline_label_en,
        "deadline_label_ar": deadline_label_ar,
        "days_until_expiry": days_i,
        "expiry_date": expiry_s,
        "escalation_step": escalation["step"],
        "escalation_label_en": escalation["label_en"],
        "escalation_label_ar": escalation["label_ar"],
        "system_of_action": soa["module"],
        "system_of_action_why_en": soa["why_en"],
        "system_of_action_why_ar": soa["why_ar"],
        "source_module": "compliance",
        "deep_link": deep_link,
        "secondary_links": [link for link in secondary_links if link.get("page")],
        "next_action_en": document.get("next_action") or reason_en,
        "alerts_delivery_owns_reminders": True,
    }


def rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> tuple:
        sev = SEVERITY_RANK.get(str(item.get("severity") or "low"), 9)
        days = item.get("days_until_expiry")
        # Expired (negative days) first within same severity, then soonest expiry
        day_rank = 10_000
        if days is not None:
            try:
                day_rank = int(days)
            except Exception:
                day_rank = 10_000
        return (sev, day_rank, str(item.get("employee_name") or ""), str(item.get("document_type") or ""))

    return sorted(findings, key=sort_key)


def build_compliance_findings(
    *,
    documents: list[dict[str, Any]],
    employee_rows_by_key: dict[str, dict[str, Any]] | None = None,
    enabled_modules: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build ranked findings + honesty envelope from classified compliance documents."""
    sources = source_availability(enabled_modules)
    rows_by_key = employee_rows_by_key or {}
    findings: list[dict[str, Any]] = []
    for doc in documents:
        key = str(doc.get("employee_key") or "")
        finding = build_finding_from_document(
            document=doc,
            employee_row=rows_by_key.get(key),
            sources=sources,
        )
        if finding:
            findings.append(finding)
    ranked = rank_findings(findings)
    window = kuwait_window_payload()
    high = sum(1 for f in ranked if f.get("severity") == "high")
    medium = sum(1 for f in ranked if f.get("severity") == "medium")
    return {
        **window,
        "contract": COMPLIANCE_WAVE1_CONTRACT,
        "contract_version": COMPLIANCE_WAVE1_VERSION,
        "findings": ranked,
        "findings_summary": {
            "total": len(ranked),
            "high": high,
            "medium": medium,
            "low": sum(1 for f in ranked if f.get("severity") == "low"),
        },
        "definitions": compliance_metric_definitions(),
        "sources": sources,
        "honesty": honesty_payload(),
        "authority": {
            "document_compliance_only": True,
            "government_verified": False,
            "legal_compliance_claims": False,
            "fine_calculations": False,
            "filing": False,
            "ai": False,
            "alerts_delivery_owns_reminders": True,
            "analytics_excludes_compliance": True,
            "systems_of_action": ["compliance", "onboarding", "employees"],
            "default_owner": dict(DEFAULT_HR_OWNER),
            "wave1_enabled": compliance_wave1_enabled(),
            "synthetic_only": compliance_wave1_synthetic_only(),
        },
    }


def enrich_document_row(document: dict[str, Any]) -> dict[str, Any]:
    """Additive fields on each document row for EN/AR + evidence honesty."""
    doc_type = str(document.get("document_type") or "")
    canon = canonicalize_document_type(doc_type)
    bucket = str(document.get("status") or "")
    evidence = evidence_status_for(bucket=bucket, has_file=bool(document.get("file_id")))
    owner = owner_for_document_type(doc_type)
    rule = rule_guidance_for(doc_type)
    return {
        **document,
        "document_type_canonical": canon,
        "document_label_en": document_label(doc_type, locale="en"),
        "document_label_ar": document_label(doc_type, locale="ar"),
        "evidence_status": evidence,
        "evidence_status_label_en": EVIDENCE_STATUS_LABELS.get(evidence, {}).get("en"),
        "evidence_status_label_ar": EVIDENCE_STATUS_LABELS.get(evidence, {}).get("ar"),
        "government_verified": False,
        "guidance_only": True,
        "rule_label_en": rule.get("label_en"),
        "rule_label_ar": rule.get("label_ar"),
        "owner_role": owner["owner_role"],
        "owner_label_en": owner["owner_label_en"],
        "owner_label_ar": owner["owner_label_ar"],
    }


def assert_residence_work_permit_integrity() -> dict[str, Any]:
    """Offline integrity checks for Wave 1 vocabulary + seed dual-write contract."""
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("canon_residency_iqama", canonicalize_document_type("residency_iqama") == "residence")
    check("canon_residency", canonicalize_document_type("residency") == "residence")
    check("canon_residence", canonicalize_document_type("residence") == "residence")
    check("canon_work_permit", canonicalize_document_type("work_permit") == "work_permit")

    try:
        import kuwait_pilot_document_journey as journey

        check("dual_write_residence", journey.should_dual_write_compliance("residence") is True)
        check("dual_write_work_permit", journey.should_dual_write_compliance("work_permit") is True)
        check("dual_write_residency_iqama", journey.should_dual_write_compliance("residency_iqama") is True)
        check("journey_canon_iqama", journey.canonical_compliance_type("residency_iqama") == "residence")
    except Exception as exc:
        check("dual_write_import", False, str(exc))

    try:
        import kuwait_first_client_foundation as foundation

        expat = foundation.compliance_seed_types_for_category("article_18_expatriate", country_code="KW")
        national = foundation.compliance_seed_types_for_category("kuwaiti_national", country_code="KW")
        check("expat_seed_has_residence", "residence" in expat, expat)
        check("expat_seed_has_work_permit", "work_permit" in expat, expat)
        check("national_seed_no_residence", "residence" not in national, national)
        check("national_seed_no_work_permit", "work_permit" not in national, national)
    except Exception as exc:
        check("seed_types", False, str(exc))

    owner = owner_for_document_type("residence")
    check("default_owner_hr", owner.get("owner_role") == "hr_compliance", owner)

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks}
