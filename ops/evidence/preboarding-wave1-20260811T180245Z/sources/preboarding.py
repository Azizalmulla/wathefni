"""Wave 1 — Preboarding authority (assignment SM + readiness + Kuwait defaults).

Dark by default:
  WATHEFNI_PREBOARDING=on
  ∧ company in WATHEFNI_PREBOARDING_COMPANIES
  ∧ preboarding_settings.enabled (or company_modules.preboarding)

HARD: attaches to canonical employee_key / employment (pending_start OK).
OPTIONAL: offer auto-create + onboarding handoff (contract-gated; not cosmetic).
ENHANCEMENT: application_id traceability when pre_hiring on.

ready is always derived from required items/gates — never a manual cosmetic mark.
pending_start must remain non-active for payroll/attendance/leave/shifts/ESS.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PREBOARDING_SCHEMA_VERSION = "1.0.0"
DEFAULT_TEMPLATE_ID = "default_kuwait_preboard"
DEFAULT_TEMPLATE_VERSION = "1.0.0"
_ON_VALUES = {"1", "true", "yes", "on"}
_SCHEMA = Path(__file__).resolve().parent / "ops" / "sql" / "preboarding_wave1_v1.sql"

ASSIGNMENT_STATUSES = frozenset(
    {"not_started", "in_progress", "ready", "blocked", "converted", "cancelled"}
)
ITEM_STATUSES = frozenset({"pending", "in_progress", "done", "waived", "blocked"})
OWNER_ROLES = frozenset({"employee", "hr", "manager", "it", "other", "system"})
CANCEL_REASONS = frozenset({"cancelled", "no_show", "withdrawn", "other"})

ASSIGNMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_started": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"ready", "blocked", "cancelled"}),
    "blocked": frozenset({"in_progress", "ready", "cancelled"}),
    "ready": frozenset({"converted", "cancelled", "blocked", "in_progress"}),
    "converted": frozenset(),
    "cancelled": frozenset(),
}
ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "done", "waived", "blocked"}),
    "in_progress": frozenset({"done", "waived", "blocked", "pending"}),
    "blocked": frozenset({"in_progress", "done", "waived", "pending"}),
    "done": frozenset(),
    "waived": frozenset(),
}

EVENT_TYPES = frozenset(
    {
        "created",
        "started",
        "item_updated",
        "item_waived",
        "readiness_recomputed",
        "ready",
        "blocked",
        "converted",
        "cancelled",
        "joining_date_set",
        "handoff_dedupe",
        "task_synced",
        "offer_auto_create",
        "idempotent_replay",
        "concurrency_conflict",
        "gate_denied",
        "scope_denied",
    }
)

# Overlap keys with onboarding DEFAULT_KUWAIT_V2 for OPTIONAL handoff dedupe.
ONBOARDING_OVERLAP_KEYS = frozenset(
    {
        "civil_id",
        "passport",
        "residence",
        "work_permit",
        "employment_contract",
        "company_policy_ack",
        "bank_details",
    }
)


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def preboarding_runtime_flag_on() -> bool:
    return _env_on("WATHEFNI_PREBOARDING", "off")


def preboarding_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PREBOARDING_COMPANIES", "") or "")
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def can_transition_assignment(from_status: str, to_status: str) -> bool:
    return to_status in ASSIGNMENT_TRANSITIONS.get(from_status, frozenset())


def can_transition_item(from_status: str, to_status: str) -> bool:
    return to_status in ITEM_TRANSITIONS.get(from_status, frozenset())


def ensure_preboarding_schema(cur: Any) -> None:
    cur.execute(_SCHEMA.read_text(encoding="utf-8"))


# --- Kuwait-first default template -------------------------------------------------

def default_kuwait_preboard_items() -> list[dict[str, Any]]:
    """Kuwait-first preboard capabilities (bilingual labels; shared item keys)."""
    items: list[dict[str, Any]] = [
        {
            "item_key": "civil_id",
            "title_en": "Civil ID (front and back)",
            "title_ar": "البطاقة المدنية (الوجهان)",
            "category": "identity_legal",
            "item_type": "document",
            "owner_role": "employee",
            "required": True,
            "due_offset_days": -5,
            "depends_on": [],
            "document_type": "civil_id",
            "sort_order": 10,
        },
        {
            "item_key": "passport",
            "title_en": "Passport copy (if applicable)",
            "title_ar": "جواز السفر (إن وجد)",
            "category": "identity_legal",
            "item_type": "document",
            "owner_role": "employee",
            "required": False,
            "due_offset_days": -5,
            "depends_on": [],
            "document_type": "passport",
            "sort_order": 20,
        },
        {
            "item_key": "residence",
            "title_en": "Residency / residence permit readiness",
            "title_ar": "جاهزية الإقامة",
            "category": "identity_legal",
            "item_type": "document",
            "owner_role": "employee",
            "required": False,
            "due_offset_days": -3,
            "depends_on": ["civil_id"],
            "document_type": "residence",
            "sort_order": 30,
        },
        {
            "item_key": "work_permit",
            "title_en": "Work permit readiness",
            "title_ar": "جاهزية إذن العمل",
            "category": "identity_legal",
            "item_type": "document",
            "owner_role": "hr",
            "required": False,
            "due_offset_days": -3,
            "depends_on": ["residence"],
            "document_type": "work_permit",
            "sort_order": 40,
        },
        {
            "item_key": "employment_contract",
            "title_en": "Signed employment contract / forms",
            "title_ar": "عقد العمل / النماذج الموقعة",
            "category": "contracts_forms",
            "item_type": "document",
            "owner_role": "employee",
            "required": True,
            "due_offset_days": -2,
            "depends_on": [],
            "document_type": "employment_contract",
            "sort_order": 50,
        },
        {
            "item_key": "company_policy_ack",
            "title_en": "Policies & acknowledgements",
            "title_ar": "الإقرارات والسياسات",
            "category": "contracts_forms",
            "item_type": "ack",
            "owner_role": "employee",
            "required": True,
            "due_offset_days": -1,
            "depends_on": [],
            "document_type": None,
            "sort_order": 60,
        },
        {
            "item_key": "bank_details",
            "title_en": "Bank / payroll readiness (via ESS — no plaintext IBAN)",
            "title_ar": "جاهزية البنك/الرواتب عبر الخدمة الذاتية",
            "category": "payroll_bank",
            "item_type": "task",
            "owner_role": "employee",
            "required": True,
            "due_offset_days": -2,
            "depends_on": [],
            "document_type": None,
            "sort_order": 70,
            "metadata": {"collection_mode": "ess_encrypted", "no_plaintext_iban": True},
        },
        {
            "item_key": "equipment",
            "title_en": "Equipment readiness",
            "title_ar": "جاهزية المعدات",
            "category": "equipment",
            "item_type": "task",
            "owner_role": "hr",
            "required": False,
            "due_offset_days": -1,
            "depends_on": [],
            "document_type": None,
            "sort_order": 80,
        },
        {
            "item_key": "it_system_access",
            "title_en": "IT / system access readiness",
            "title_ar": "جاهزية أنظمة وتقنية المعلومات",
            "category": "it_access",
            "item_type": "task",
            "owner_role": "it",
            "required": True,
            "due_offset_days": -3,
            "depends_on": [],
            "document_type": None,
            "sort_order": 90,
        },
        {
            "item_key": "workspace_site_ready",
            "title_en": "Workspace / site readiness",
            "title_ar": "جاهزية موقع العمل",
            "category": "site",
            "item_type": "task",
            "owner_role": "hr",
            "required": True,
            "due_offset_days": -2,
            "depends_on": [],
            "document_type": None,
            "sort_order": 100,
        },
        {
            "item_key": "manager_preparation",
            "title_en": "Manager preparation",
            "title_ar": "تجهيز المدير المباشر",
            "category": "manager",
            "item_type": "task",
            "owner_role": "manager",
            "required": True,
            "due_offset_days": -3,
            "depends_on": [],
            "document_type": None,
            "sort_order": 110,
        },
        {
            "item_key": "employee_prejoin_actions",
            "title_en": "Employee pre-join actions",
            "title_ar": "إجراءات الموظف قبل الالتحاق",
            "category": "employee_prejoin",
            "item_type": "task",
            "owner_role": "employee",
            "required": True,
            "due_offset_days": -1,
            "depends_on": ["civil_id", "employment_contract"],
            "document_type": None,
            "sort_order": 120,
        },
        {
            "item_key": "welcome_reminder_comms",
            "title_en": "Welcome / reminder communications",
            "title_ar": "رسائل الترحيب والتذكير",
            "category": "comms",
            "item_type": "comms",
            "owner_role": "hr",
            "required": False,
            "due_offset_days": -7,
            "depends_on": [],
            "document_type": None,
            "sort_order": 130,
        },
    ]
    return items


def seed_settings(cur: Any, company_code: str) -> None:
    company = company_code_norm(company_code)
    if not company:
        return
    cur.execute(
        """
        INSERT INTO preboarding_settings (
          company_code, enabled, auto_create_on_offer_accept,
          required_for_ready_mark, handoff_onboarding_enabled
        ) VALUES (%s, false, true, true, false)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def get_settings(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    seed_settings(cur, company)
    cur.execute("SELECT * FROM preboarding_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    d = dict(row) if row else {}
    return {
        "company_code": company,
        "enabled": bool(d.get("enabled")),
        "auto_create_on_offer_accept": bool(d.get("auto_create_on_offer_accept", True)),
        "required_for_ready_mark": bool(d.get("required_for_ready_mark", True)),
        "handoff_onboarding_enabled": bool(d.get("handoff_onboarding_enabled")),
    }


def set_settings(
    cur: Any,
    company_code: str,
    *,
    enabled: bool | None = None,
    auto_create_on_offer_accept: bool | None = None,
    required_for_ready_mark: bool | None = None,
    handoff_onboarding_enabled: bool | None = None,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    seed_settings(cur, company)
    current = get_settings(cur, company)
    cur.execute(
        """
        UPDATE preboarding_settings
           SET enabled=%s,
               auto_create_on_offer_accept=%s,
               required_for_ready_mark=%s,
               handoff_onboarding_enabled=%s,
               updated_at=now()
         WHERE company_code=%s
        """,
        (
            bool(current["enabled"] if enabled is None else enabled),
            bool(
                current["auto_create_on_offer_accept"]
                if auto_create_on_offer_accept is None
                else auto_create_on_offer_accept
            ),
            bool(
                current["required_for_ready_mark"]
                if required_for_ready_mark is None
                else required_for_ready_mark
            ),
            bool(
                current["handoff_onboarding_enabled"]
                if handoff_onboarding_enabled is None
                else handoff_onboarding_enabled
            ),
            company,
        ),
    )
    return get_settings(cur, company)


def ensure_default_template(cur: Any, company_code: str) -> None:
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO preboarding_templates (
          template_id, company_code, version, title_en, title_ar, active
        ) VALUES (%s,%s,%s,%s,%s,true)
        ON CONFLICT (company_code, template_id) DO NOTHING
        """,
        (
            DEFAULT_TEMPLATE_ID,
            company,
            DEFAULT_TEMPLATE_VERSION,
            "Kuwait preboarding default",
            "تهيئة الالتحاق الافتراضية — الكويت",
        ),
    )
    for spec in default_kuwait_preboard_items():
        cur.execute(
            """
            INSERT INTO preboarding_template_items (
              company_code, template_id, item_key, title_en, title_ar, category,
              item_type, owner_role, required, due_offset_days, depends_on,
              document_type, sort_order, metadata
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)
            ON CONFLICT (company_code, template_id, item_key) DO NOTHING
            """,
            (
                company,
                DEFAULT_TEMPLATE_ID,
                spec["item_key"],
                spec["title_en"],
                spec.get("title_ar"),
                spec["category"],
                spec["item_type"],
                spec["owner_role"],
                bool(spec["required"]),
                spec.get("due_offset_days"),
                json.dumps(spec.get("depends_on") or []),
                spec.get("document_type"),
                int(spec.get("sort_order") or 0),
                json.dumps(spec.get("metadata") or {}),
            ),
        )


def _module_enabled(cur: Any, company_code: str) -> bool:
    company = company_code_norm(company_code)
    try:
        cur.execute(
            """
            SELECT enabled FROM company_modules
             WHERE company_code=%s AND module_key='preboarding'
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


def preboarding_enabled_for_company(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required"}
    if not preboarding_runtime_flag_on():
        return {"ok": False, "enabled": False, "error": "preboarding_disabled", "gate": "runtime_flag"}
    allow = preboarding_company_allowlist()
    if not allow or company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "preboarding_company_not_allowlisted",
            "gate": "company_allowlist",
        }
    if not _module_enabled(cur, company):
        return {
            "ok": False,
            "enabled": False,
            "error": "preboarding_company_disabled",
            "gate": "company_setting",
        }
    return {"ok": True, "enabled": True, "company_code": company}


def _insert_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    assignment_id: str | None = None,
    item_id: str | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown_event_type:{event_type}")
    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO preboard_events (
          event_id, company_code, assignment_id, item_id, event_type,
          actor_user_id, actor_phone, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            event_id,
            company_code_norm(company_code),
            assignment_id,
            item_id,
            event_type,
            actor_user_id,
            digits_phone(actor_phone) or None,
            json.dumps(payload or {}),
        ),
    )
    return event_id


def _parse_deps(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
        except Exception:
            return []
    return []


def _assignment_row(row: dict[str, Any]) -> dict[str, Any]:
    readiness = row.get("readiness")
    if isinstance(readiness, str):
        readiness = json.loads(readiness)
    blockers = row.get("blocker_reasons")
    if isinstance(blockers, str):
        blockers = json.loads(blockers)
    meta = row.get("metadata")
    if isinstance(meta, str):
        meta = json.loads(meta)
    return {
        "assignment_id": str(row["assignment_id"]),
        "company_code": row["company_code"],
        "employee_key": row["employee_key"],
        "employment_id": row.get("employment_id"),
        "status": row.get("status"),
        "joining_date": row.get("joining_date"),
        "template_id": row.get("template_id"),
        "template_version": row.get("template_version"),
        "application_id": row.get("application_id"),
        "offer_id": row.get("offer_id"),
        "manager_user_id": row.get("manager_user_id"),
        "blocker_reasons": blockers or [],
        "readiness": readiness or {},
        "cancel_reason": row.get("cancel_reason"),
        "created_by_user_id": row.get("created_by_user_id"),
        "created_by_phone": row.get("created_by_phone"),
        "row_version": int(row.get("row_version") or 1),
        "idempotency_key": row.get("idempotency_key"),
        "metadata": meta or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _item_row(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata")
    if isinstance(meta, str):
        meta = json.loads(meta)
    return {
        "item_id": str(row["item_id"]),
        "assignment_id": str(row["assignment_id"]),
        "company_code": row["company_code"],
        "employee_key": row["employee_key"],
        "item_key": row["item_key"],
        "title_en": row.get("title_en"),
        "title_ar": row.get("title_ar"),
        "category": row.get("category"),
        "item_type": row.get("item_type"),
        "owner_role": row.get("owner_role"),
        "required": bool(row.get("required")),
        "depends_on": _parse_deps(row.get("depends_on")),
        "due_at": row.get("due_at"),
        "status": row.get("status"),
        "blocker_reason": row.get("blocker_reason"),
        "evidence_document_id": row.get("evidence_document_id"),
        "document_type": row.get("document_type"),
        "waived_by_user_id": row.get("waived_by_user_id"),
        "waive_reason": row.get("waive_reason"),
        "completed_at": row.get("completed_at"),
        "row_version": int(row.get("row_version") or 1),
        "metadata": meta or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def get_assignment(
    cur: Any, *, company_code: str, assignment_id: str
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM preboard_assignments
         WHERE company_code=%s AND assignment_id=%s
         LIMIT 1
        """,
        (company_code_norm(company_code), str(assignment_id)),
    )
    row = cur.fetchone()
    return _assignment_row(dict(row)) if row else None


def list_items(cur: Any, *, company_code: str, assignment_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM preboard_items
         WHERE company_code=%s AND assignment_id=%s
         ORDER BY created_at ASC
        """,
        (company_code_norm(company_code), str(assignment_id)),
    )
    return [_item_row(dict(r)) for r in (cur.fetchall() or [])]


# --- Canonical employment attach / pending_start ---------------------------------

def resolve_canonical_employment(
    cur: Any, *, company_code: str, employee_key: str
) -> dict[str, Any]:
    """Resolve hub employee + employment; fail closed if missing or wrong tenant."""
    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    if not company or not key:
        return {"ok": False, "error": "employee_required"}
    cur.execute(
        """
        SELECT employee_key, company_code, employment_status, start_date, name, phone
          FROM employees
         WHERE company_code=%s AND employee_key=%s
         LIMIT 1
        """,
        (company, key),
    )
    hub = cur.fetchone()
    if not hub:
        return {"ok": False, "error": "employee_not_found"}
    hub_d = dict(hub)
    hub_status = str(hub_d.get("employment_status") or "").strip().lower()
    employment_id = None
    lifecycle = None
    joining = hub_d.get("start_date")
    try:
        cur.execute(
            """
            SELECT employment_id, employment_status, lifecycle_state, start_date
              FROM employee_employments
             WHERE company_code=%s AND legacy_employee_key=%s
             ORDER BY updated_at DESC NULLS LAST
             LIMIT 1
            """,
            (company, key),
        )
        emp = cur.fetchone()
        if emp:
            ed = dict(emp)
            employment_id = str(ed.get("employment_id") or "") or None
            lifecycle = str(ed.get("lifecycle_state") or "").strip().lower() or None
            if ed.get("start_date"):
                joining = ed.get("start_date")
            if str(ed.get("employment_status") or "").strip().lower() == "pending_start":
                hub_status = "pending_start"
    except Exception:
        pass

    # P2/P4/P5: pending_start is attachable; left/terminated is not for new open preboard.
    if hub_status in {"left", "terminated"} or lifecycle == "terminated":
        return {"ok": False, "error": "employee_not_joinable", "hub_status": hub_status}

    is_pending = hub_status == "pending_start" or lifecycle == "pending_start"
    is_active = hub_status == "active" and not is_pending
    return {
        "ok": True,
        "employee_key": key,
        "company_code": company,
        "employment_id": employment_id,
        "hub_status": hub_status or ("pending_start" if is_pending else "active"),
        "lifecycle_state": lifecycle,
        "joining_date": joining,
        "is_pending_start": is_pending,
        "is_active": is_active,
        "name": hub_d.get("name"),
        "phone": hub_d.get("phone"),
    }


def ensure_provisional_pending_start(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    name: str,
    joining_date: date,
    phone: str | None = None,
) -> dict[str, Any]:
    """Create or repair canonical pending_start employment (no parallel person table)."""
    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    if not company or not key:
        return {"ok": False, "error": "employee_required"}
    if not isinstance(joining_date, date):
        return {"ok": False, "error": "joining_date_required"}

    phone_n = digits_phone(phone) or f"9650{uuid.uuid4().hex[:8]}"
    cur.execute(
        """
        INSERT INTO employees (
          employee_key, company_code, name, phone, employment_status, start_date, updated_at
        ) VALUES (%s,%s,%s,%s,'pending_start',%s,now())
        ON CONFLICT (employee_key) DO UPDATE SET
          company_code=EXCLUDED.company_code,
          name=COALESCE(EXCLUDED.name, employees.name),
          phone=COALESCE(EXCLUDED.phone, employees.phone),
          employment_status='pending_start',
          start_date=COALESCE(EXCLUDED.start_date, employees.start_date),
          updated_at=now()
        """,
        (key, company, str(name or "").strip() or key, phone_n, joining_date),
    )

    employment_id = None
    try:
        import employee_lifecycle_wave3 as _life

        _life.ensure_lifecycle_schema(cur)
        employment_id = str(uuid.uuid4())
        # person_id may be required — try minimal authority row; fall back hub-only.
        cur.execute(
            """
            SELECT employment_id FROM employee_employments
             WHERE company_code=%s AND legacy_employee_key=%s
             LIMIT 1
            """,
            (company, key),
        )
        existing = cur.fetchone()
        if existing:
            employment_id = str(dict(existing)["employment_id"])
            cur.execute(
                """
                UPDATE employee_employments
                   SET employment_status='pending_start',
                       lifecycle_state='pending_start',
                       start_date=COALESCE(%s, start_date),
                       updated_at=now()
                 WHERE employment_id=%s AND company_code=%s
                """,
                (joining_date, employment_id, company),
            )
        else:
            # Need person_id — create lightweight person if table exists.
            person_id = str(uuid.uuid4())
            try:
                cur.execute(
                    """
                    INSERT INTO employee_persons (person_id, company_code, display_name, provenance)
                    VALUES (%s,%s,%s,%s::jsonb)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        person_id,
                        company,
                        str(name or key),
                        json.dumps({"source": "preboarding_provisional"}),
                    ),
                )
            except Exception:
                # Schema variants — skip person if unavailable; employment may still work.
                pass
            try:
                cur.execute(
                    """
                    INSERT INTO employee_employments (
                      employment_id, company_code, person_id, employment_status,
                      lifecycle_state, start_date, hire_source, legacy_employee_key, provenance
                    ) VALUES (%s,%s,%s,'pending_start','pending_start',%s,'preboarding',%s,%s::jsonb)
                    ON CONFLICT (employment_id) DO NOTHING
                    """,
                    (
                        employment_id,
                        company,
                        person_id,
                        joining_date,
                        key,
                        json.dumps({"source": "preboarding_provisional"}),
                    ),
                )
            except Exception:
                employment_id = None
        try:
            _life.repair_pending_start_hub_projection(cur, company_code=company)
        except Exception:
            pass
    except Exception:
        employment_id = None

    resolved = resolve_canonical_employment(cur, company_code=company, employee_key=key)
    if not resolved.get("ok"):
        return resolved
    if not resolved.get("is_pending_start") and resolved.get("hub_status") != "pending_start":
        # Force hub projection for canary / provisional create.
        cur.execute(
            """
            UPDATE employees
               SET employment_status='pending_start', start_date=%s, updated_at=now()
             WHERE company_code=%s AND employee_key=%s
            """,
            (joining_date, company, key),
        )
        resolved = resolve_canonical_employment(cur, company_code=company, employee_key=key)
    return {
        "ok": True,
        "employee_key": key,
        "employment_id": employment_id or resolved.get("employment_id"),
        "joining_date": joining_date,
        "hub_status": "pending_start",
        "is_pending_start": True,
    }


def assert_non_active_eligibility(employee_row: dict[str, Any]) -> dict[str, Any]:
    """Invariant helper: preboarding attach must not imply active ESS/pay/time."""
    try:
        import employee_app_access as _eaa

        ess_ok = bool(_eaa.employment_eligible(employee_row))
    except Exception:
        status = str(employee_row.get("employment_status") or "").strip().lower()
        ess_ok = status == "active"
    return {
        "ok": True,
        "employment_eligible_ess": ess_ok,
        "must_be_false_for_pending_start": ess_ok is False
        or str(employee_row.get("employment_status") or "").lower() != "pending_start",
    }


# --- Readiness authority ----------------------------------------------------------

def compute_readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive readiness from required items + blockers. Never cosmetic."""
    by_key = {str(i["item_key"]): i for i in items}
    required = [i for i in items if i.get("required")]
    blockers: list[dict[str, Any]] = []
    incomplete: list[str] = []
    satisfied = 0
    for item in required:
        key = str(item["item_key"])
        status = str(item.get("status") or "pending")
        if status == "blocked":
            blockers.append(
                {
                    "code": "item_blocked",
                    "item_key": key,
                    "reason": item.get("blocker_reason"),
                }
            )
            incomplete.append(key)
            continue
        if status in {"done", "waived"}:
            satisfied += 1
            continue
        incomplete.append(key)
        blockers.append({"code": "required_incomplete", "item_key": key, "status": status})
        for dep in item.get("depends_on") or []:
            dep_item = by_key.get(str(dep))
            if not dep_item or dep_item.get("status") not in {"done", "waived"}:
                blockers.append(
                    {
                        "code": "dependency_unmet",
                        "item_key": key,
                        "depends_on": str(dep),
                    }
                )

    total_req = len(required)
    pct = int(round((satisfied / total_req) * 100)) if total_req else 100
    is_ready = satisfied == total_req and not any(b["code"] == "item_blocked" for b in blockers)
    if is_ready:
        blockers = []
    is_blocked = any(b["code"] == "item_blocked" for b in blockers)
    return {
        "ready": is_ready,
        "blocked": is_blocked and not is_ready,
        "required_total": total_req,
        "required_satisfied": satisfied,
        "required_incomplete": incomplete,
        "percent": pct,
        "blockers": blockers,
    }


def recompute_assignment_status(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    actor_user_id: str | None = None,
    prefer_in_progress: bool = False,
) -> dict[str, Any]:
    gate = preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    asn = get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    if asn["status"] in {"converted", "cancelled"}:
        return {"ok": True, "assignment": asn, "unchanged": True, "reason": "terminal"}

    items = list_items(cur, company_code=company, assignment_id=assignment_id)
    readiness = compute_readiness(items)
    new_status = asn["status"]
    if readiness["ready"]:
        new_status = "ready"
    elif readiness["blocked"]:
        new_status = "blocked"
    elif asn["status"] == "not_started" and prefer_in_progress:
        new_status = "in_progress"
    elif asn["status"] in {"ready", "blocked"} and not readiness["ready"] and not readiness["blocked"]:
        new_status = "in_progress"
    elif asn["status"] == "not_started" and any(
        i.get("status") != "pending" for i in items
    ):
        new_status = "in_progress"
    elif asn["status"] in {"in_progress", "ready", "blocked"} and not readiness["ready"]:
        if readiness["blocked"]:
            new_status = "blocked"
        else:
            new_status = "in_progress"

    cur.execute(
        """
        UPDATE preboard_assignments
           SET status=%s,
               blocker_reasons=%s::jsonb,
               readiness=%s::jsonb,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND assignment_id=%s AND row_version=%s
        RETURNING *
        """,
        (
            new_status,
            json.dumps(readiness.get("blockers") or []),
            json.dumps(readiness),
            company,
            str(assignment_id),
            int(asn["row_version"]),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    event = "readiness_recomputed"
    if new_status == "ready" and asn["status"] != "ready":
        event = "ready"
    elif new_status == "blocked" and asn["status"] != "blocked":
        event = "blocked"
    _insert_event(
        cur,
        company_code=company,
        event_type=event,
        assignment_id=str(assignment_id),
        actor_user_id=actor_user_id,
        payload={"from": asn["status"], "to": new_status, "readiness": readiness},
    )
    if new_status == "ready":
        _sync_readiness_task(cur, company_code=company, assignment=_assignment_row(dict(updated)))
    return {
        "ok": True,
        "assignment": _assignment_row(dict(updated)),
        "readiness": readiness,
        "items": items,
    }


# --- Tasks / SLA (Phase A spine; soft when tasks module off) ----------------------

def _sync_item_task(
    cur: Any,
    *,
    company_code: str,
    item: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    try:
        import workflow_task_sla as wts

        if item.get("status") in {"done", "waived"}:
            open_task = wts.find_open_workflow_task(
                cur,
                company_code=company_code,
                task_type="preboard_item",
                subject_type="preboard_item",
                subject_id=str(item["item_id"]),
            )
            if open_task:
                return wts.resolve_workflow_task(
                    cur,
                    company_code=company_code,
                    task_id=str(open_task["task_id"]),
                    status="done",
                    actor_user_id=actor_user_id,
                )
            return {"ok": True, "skipped": True, "reason": "no_open_task"}

        due = item.get("due_at")
        if isinstance(due, str):
            due = None
        created = wts.create_workflow_task(
            cur,
            company_code=company_code,
            task_type="preboard_item",
            title=str(item.get("title_en") or item.get("item_key")),
            subject_type="preboard_item",
            subject_id=str(item["item_id"]),
            detail=str(item.get("title_ar") or ""),
            employee_key=str(item.get("employee_key") or ""),
            due_at=due if isinstance(due, datetime) else None,
            source="preboarding",
            metadata={
                "item_key": item.get("item_key"),
                "owner_role": item.get("owner_role"),
                "assignment_id": item.get("assignment_id"),
            },
            actor_user_id=actor_user_id,
            idempotency_key=f"preboard_item:{item['item_id']}",
        )
        if created.get("ok") and due and isinstance(due, datetime):
            try:
                wts.start_sla_clock(
                    cur,
                    company_code=company_code,
                    subject_type="preboard_item",
                    subject_id=str(item["item_id"]),
                    idempotency_key=f"preboard_sla:{item['item_id']}",
                    metadata={"item_key": item.get("item_key")},
                )
            except Exception:
                pass
        if created.get("ok"):
            _insert_event(
                cur,
                company_code=company_code,
                event_type="task_synced",
                assignment_id=str(item.get("assignment_id")),
                item_id=str(item.get("item_id")),
                actor_user_id=actor_user_id,
                payload={"task": created.get("task", {}).get("task_id") or created.get("error")},
            )
        return created
    except Exception as exc:
        return {"ok": False, "soft_fail": True, "error": str(exc)}


def _sync_readiness_task(
    cur: Any, *, company_code: str, assignment: dict[str, Any]
) -> dict[str, Any]:
    try:
        import workflow_task_sla as wts

        return wts.create_workflow_task(
            cur,
            company_code=company_code,
            task_type="preboard_readiness",
            title=f"Preboard ready: {assignment.get('employee_key')}",
            subject_type="preboard_assignment",
            subject_id=str(assignment["assignment_id"]),
            employee_key=str(assignment.get("employee_key") or ""),
            source="preboarding",
            metadata={"status": assignment.get("status")},
            idempotency_key=f"preboard_ready:{assignment['assignment_id']}",
        )
    except Exception as exc:
        return {"ok": False, "soft_fail": True, "error": str(exc)}


# --- RBAC / manager scope ---------------------------------------------------------

def assert_actor_scope(
    *,
    assignment: dict[str, Any],
    actor_user_id: str | None,
    actor_role: str | None = None,
    permission: str = "preboarding.read",
) -> dict[str, Any]:
    """Tenant already enforced by company_code queries. Manager scope for manage/waive."""
    role = str(actor_role or "").strip().lower() or "hr"
    if permission in {"preboarding.manage", "preboarding.waive_item"} and role == "manager":
        mgr = str(assignment.get("manager_user_id") or "").strip()
        actor = str(actor_user_id or "").strip()
        if mgr and actor and mgr != actor:
            return {"ok": False, "error": "manager_scope_denied", "gate": "manager_scope"}
    if permission == "preboarding.waive_item" and role not in {"hr", "admin", "owner"}:
        return {"ok": False, "error": "waive_forbidden", "gate": "rbac"}
    return {"ok": True, "actor_role": role, "permission": permission}


# --- Create / mutate --------------------------------------------------------------

def create_assignment(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    joining_date: date | None = None,
    employment_id: str | None = None,
    application_id: str | None = None,
    offer_id: str | None = None,
    manager_user_id: str | None = None,
    created_by_user_id: str | None = None,
    created_by_phone: str | None = None,
    idempotency_key: str | None = None,
    seed_tasks: bool = True,
    apply_handoff: bool = True,
) -> dict[str, Any]:
    gate = preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        _insert_event(
            cur,
            company_code=company_code_norm(company_code) or "UNKNOWN",
            event_type="gate_denied",
            actor_user_id=created_by_user_id,
            payload=gate,
        )
        return gate
    company = company_code_norm(company_code)
    ensure_default_template(cur, company)

    resolved = resolve_canonical_employment(cur, company_code=company, employee_key=employee_key)
    if not resolved.get("ok"):
        return resolved

    idem = str(idempotency_key or "").strip() or None
    if idem:
        cur.execute(
            """
            SELECT * FROM preboard_assignments
             WHERE company_code=%s AND idempotency_key=%s
             LIMIT 1
            """,
            (company, idem),
        )
        existing = cur.fetchone()
        if existing:
            row = _assignment_row(dict(existing))
            _insert_event(
                cur,
                company_code=company,
                event_type="idempotent_replay",
                assignment_id=row["assignment_id"],
                actor_user_id=created_by_user_id,
                payload={"op": "create_assignment"},
            )
            return {
                "ok": True,
                "replayed": True,
                "assignment": row,
                "items": list_items(cur, company_code=company, assignment_id=row["assignment_id"]),
            }

    # One open assignment per employee
    cur.execute(
        """
        SELECT assignment_id, status FROM preboard_assignments
         WHERE company_code=%s AND employee_key=%s
           AND status NOT IN ('converted','cancelled')
         LIMIT 1
        """,
        (company, str(employee_key)),
    )
    open_row = cur.fetchone()
    if open_row:
        return {
            "ok": False,
            "error": "open_assignment_exists",
            "assignment_id": str(dict(open_row)["assignment_id"]),
        }

    jd = joining_date or resolved.get("joining_date")
    if isinstance(jd, datetime):
        jd = jd.date()
    if jd is not None and not isinstance(jd, date):
        try:
            jd = date.fromisoformat(str(jd)[:10])
        except Exception:
            return {"ok": False, "error": "joining_date_invalid"}

    aid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO preboard_assignments (
          assignment_id, company_code, employee_key, employment_id, status,
          joining_date, template_id, template_version, application_id, offer_id,
          manager_user_id, created_by_user_id, created_by_phone, idempotency_key
        ) VALUES (%s,%s,%s,%s,'not_started',%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            aid,
            company,
            str(employee_key),
            employment_id or resolved.get("employment_id"),
            jd,
            DEFAULT_TEMPLATE_ID,
            DEFAULT_TEMPLATE_VERSION,
            str(application_id or "").strip() or None,
            str(offer_id or "").strip() or None,
            str(manager_user_id or "").strip() or None,
            str(created_by_user_id or "").strip() or None,
            digits_phone(created_by_phone) or None,
            idem,
        ),
    )
    asn = _assignment_row(dict(cur.fetchone()))
    _insert_event(
        cur,
        company_code=company,
        event_type="created",
        assignment_id=aid,
        actor_user_id=created_by_user_id,
        actor_phone=created_by_phone,
        payload={
            "employee_key": employee_key,
            "joining_date": str(jd) if jd else None,
            "is_pending_start": resolved.get("is_pending_start"),
        },
    )
    if jd:
        _insert_event(
            cur,
            company_code=company,
            event_type="joining_date_set",
            assignment_id=aid,
            actor_user_id=created_by_user_id,
            payload={"joining_date": str(jd), "source": "create_assignment"},
        )

    items = _seed_items_from_template(cur, company=company, assignment=asn, joining_date=jd)
    if apply_handoff:
        handoff = apply_onboarding_handoff_dedupe(
            cur, company_code=company, assignment_id=aid, actor_user_id=created_by_user_id
        )
    else:
        handoff = {"ok": True, "skipped": True, "reason": "disabled_by_caller"}

    if seed_tasks:
        for it in items:
            _sync_item_task(cur, company_code=company, item=it, actor_user_id=created_by_user_id)

    recomputed = recompute_assignment_status(
        cur, company_code=company, assignment_id=aid, actor_user_id=created_by_user_id
    )
    return {
        "ok": True,
        "replayed": False,
        "assignment": recomputed.get("assignment") or asn,
        "items": recomputed.get("items") or list_items(cur, company_code=company, assignment_id=aid),
        "readiness": recomputed.get("readiness"),
        "handoff": handoff,
        "employment": {
            "hub_status": resolved.get("hub_status"),
            "is_pending_start": resolved.get("is_pending_start"),
            "employment_id": resolved.get("employment_id"),
        },
    }


def _seed_items_from_template(
    cur: Any,
    *,
    company: str,
    assignment: dict[str, Any],
    joining_date: date | None,
) -> list[dict[str, Any]]:
    ensure_default_template(cur, company)
    cur.execute(
        """
        SELECT * FROM preboarding_template_items
         WHERE company_code=%s AND template_id=%s
         ORDER BY sort_order ASC, item_key ASC
        """,
        (company, assignment.get("template_id") or DEFAULT_TEMPLATE_ID),
    )
    specs = [dict(r) for r in (cur.fetchall() or [])]
    if not specs:
        specs = default_kuwait_preboard_items()
    out: list[dict[str, Any]] = []
    for spec in specs:
        item_id = str(uuid.uuid4())
        due_at = None
        offset = spec.get("due_offset_days")
        if joining_date is not None and offset is not None:
            due_at = datetime.combine(
                joining_date + timedelta(days=int(offset)),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
        meta = spec.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        cur.execute(
            """
            INSERT INTO preboard_items (
              item_id, assignment_id, company_code, employee_key, item_key,
              title_en, title_ar, category, item_type, owner_role, required,
              depends_on, due_at, status, document_type, metadata
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'pending',%s,%s::jsonb)
            RETURNING *
            """,
            (
                item_id,
                assignment["assignment_id"],
                company,
                assignment["employee_key"],
                spec["item_key"],
                spec["title_en"],
                spec.get("title_ar"),
                spec["category"],
                spec.get("item_type") or "task",
                spec["owner_role"],
                bool(spec.get("required")),
                json.dumps(_parse_deps(spec.get("depends_on"))),
                due_at,
                spec.get("document_type"),
                json.dumps(meta if isinstance(meta, dict) else {}),
            ),
        )
        out.append(_item_row(dict(cur.fetchone())))
    return out


def update_item_status(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    item_key: str,
    to_status: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    blocker_reason: str | None = None,
    evidence_document_id: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    asn = get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    if asn["status"] in {"converted", "cancelled"}:
        return {"ok": False, "error": "assignment_terminal", "status": asn["status"]}
    scope = assert_actor_scope(
        assignment=asn,
        actor_user_id=actor_user_id,
        actor_role=actor_role or "hr",
        permission="preboarding.manage",
    )
    if not scope.get("ok"):
        _insert_event(
            cur,
            company_code=company,
            event_type="scope_denied",
            assignment_id=assignment_id,
            actor_user_id=actor_user_id,
            payload=scope,
        )
        return scope

    cur.execute(
        """
        SELECT * FROM preboard_items
         WHERE company_code=%s AND assignment_id=%s AND item_key=%s
         LIMIT 1
        """,
        (company, str(assignment_id), str(item_key)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "item_not_found"}
    item = _item_row(dict(row))
    dst = str(to_status or "").strip().lower()
    if dst not in ITEM_STATUSES:
        return {"ok": False, "error": "status_invalid"}
    if dst == "waived":
        return {"ok": False, "error": "use_waive_item"}
    if not can_transition_item(item["status"], dst):
        return {
            "ok": False,
            "error": "invalid_transition",
            "from": item["status"],
            "to": dst,
        }
    if expected_row_version is not None and int(item["row_version"]) != int(expected_row_version):
        _insert_event(
            cur,
            company_code=company,
            event_type="concurrency_conflict",
            assignment_id=assignment_id,
            item_id=item["item_id"],
            actor_user_id=actor_user_id,
            payload={"expected": expected_row_version, "actual": item["row_version"]},
        )
        return {"ok": False, "error": "concurrency_conflict"}

    completed_at = datetime.now(timezone.utc) if dst == "done" else None
    cur.execute(
        """
        UPDATE preboard_items
           SET status=%s,
               blocker_reason=%s,
               evidence_document_id=COALESCE(%s, evidence_document_id),
               completed_at=COALESCE(%s, completed_at),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND item_id=%s AND row_version=%s
        RETURNING *
        """,
        (
            dst,
            str(blocker_reason or "").strip() or None if dst == "blocked" else None,
            str(evidence_document_id or "").strip() or None,
            completed_at,
            company,
            item["item_id"],
            int(item["row_version"]),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    item_out = _item_row(dict(updated))
    _insert_event(
        cur,
        company_code=company,
        event_type="item_updated",
        assignment_id=assignment_id,
        item_id=item_out["item_id"],
        actor_user_id=actor_user_id,
        payload={"from": item["status"], "to": dst, "item_key": item_key},
    )
    _sync_item_task(cur, company_code=company, item=item_out, actor_user_id=actor_user_id)
    recomputed = recompute_assignment_status(
        cur,
        company_code=company,
        assignment_id=assignment_id,
        actor_user_id=actor_user_id,
        prefer_in_progress=True,
    )
    return {"ok": True, "item": item_out, "assignment": recomputed.get("assignment"), "readiness": recomputed.get("readiness")}


def waive_item(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    item_key: str,
    actor_user_id: str,
    actor_role: str = "hr",
    waive_reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    asn = get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    scope = assert_actor_scope(
        assignment=asn,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        permission="preboarding.waive_item",
    )
    if not scope.get("ok"):
        return scope
    reason = str(waive_reason or "").strip()
    if not reason:
        return {"ok": False, "error": "waive_reason_required"}

    cur.execute(
        """
        SELECT * FROM preboard_items
         WHERE company_code=%s AND assignment_id=%s AND item_key=%s
         LIMIT 1
        """,
        (company, str(assignment_id), str(item_key)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "item_not_found"}
    item = _item_row(dict(row))
    if not can_transition_item(item["status"], "waived"):
        return {"ok": False, "error": "invalid_transition", "from": item["status"], "to": "waived"}
    if expected_row_version is not None and int(item["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}

    cur.execute(
        """
        UPDATE preboard_items
           SET status='waived',
               waived_by_user_id=%s,
               waive_reason=%s,
               completed_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND item_id=%s AND row_version=%s
        RETURNING *
        """,
        (actor_user_id, reason, company, item["item_id"], int(item["row_version"])),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    item_out = _item_row(dict(updated))
    _insert_event(
        cur,
        company_code=company,
        event_type="item_waived",
        assignment_id=assignment_id,
        item_id=item_out["item_id"],
        actor_user_id=actor_user_id,
        payload={"item_key": item_key, "reason": reason},
    )
    _sync_item_task(cur, company_code=company, item=item_out, actor_user_id=actor_user_id)
    recomputed = recompute_assignment_status(
        cur, company_code=company, assignment_id=assignment_id, actor_user_id=actor_user_id
    )
    return {"ok": True, "item": item_out, "assignment": recomputed.get("assignment"), "readiness": recomputed.get("readiness")}


def transition_assignment(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    to_status: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    cancel_reason: str | None = None,
    expected_row_version: int | None = None,
    force_cosmetic_ready: bool = False,
) -> dict[str, Any]:
    """Transition assignment. ready is rejected unless compute_readiness.ready (unless force — always denied)."""
    gate = preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    asn = get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    scope = assert_actor_scope(
        assignment=asn,
        actor_user_id=actor_user_id,
        actor_role=actor_role or "hr",
        permission="preboarding.manage",
    )
    if not scope.get("ok"):
        return scope

    dst = str(to_status or "").strip().lower()
    if dst not in ASSIGNMENT_STATUSES:
        return {"ok": False, "error": "status_invalid"}
    if force_cosmetic_ready:
        return {"ok": False, "error": "cosmetic_ready_forbidden"}
    if not can_transition_assignment(asn["status"], dst):
        return {"ok": False, "error": "invalid_transition", "from": asn["status"], "to": dst}
    if expected_row_version is not None and int(asn["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}

    items = list_items(cur, company_code=company, assignment_id=assignment_id)
    readiness = compute_readiness(items)
    settings = get_settings(cur, company)

    if dst == "ready":
        if settings.get("required_for_ready_mark", True) and not readiness["ready"]:
            return {
                "ok": False,
                "error": "readiness_not_met",
                "readiness": readiness,
            }
        # Prefer derived recompute path
        return recompute_assignment_status(
            cur, company_code=company, assignment_id=assignment_id, actor_user_id=actor_user_id
        )

    if dst == "cancelled":
        reason = str(cancel_reason or "cancelled").strip().lower()
        if reason not in CANCEL_REASONS:
            return {"ok": False, "error": "cancel_reason_invalid"}
        cur.execute(
            """
            UPDATE preboard_assignments
               SET status='cancelled',
                   cancel_reason=%s,
                   row_version=row_version+1,
                   updated_at=now()
             WHERE company_code=%s AND assignment_id=%s AND row_version=%s
            RETURNING *
            """,
            (reason, company, str(assignment_id), int(asn["row_version"])),
        )
        updated = cur.fetchone()
        if not updated:
            return {"ok": False, "error": "concurrency_conflict"}
        _insert_event(
            cur,
            company_code=company,
            event_type="cancelled",
            assignment_id=assignment_id,
            actor_user_id=actor_user_id,
            payload={"from": asn["status"], "cancel_reason": reason},
        )
        return {"ok": True, "assignment": _assignment_row(dict(updated))}

    if dst == "converted":
        if asn["status"] != "ready" and not readiness["ready"]:
            return {"ok": False, "error": "convert_requires_ready", "readiness": readiness}
        cur.execute(
            """
            UPDATE preboard_assignments
               SET status='converted',
                   readiness=%s::jsonb,
                   row_version=row_version+1,
                   updated_at=now()
             WHERE company_code=%s AND assignment_id=%s AND row_version=%s
            RETURNING *
            """,
            (json.dumps(readiness), company, str(assignment_id), int(asn["row_version"])),
        )
        updated = cur.fetchone()
        if not updated:
            return {"ok": False, "error": "concurrency_conflict"}
        _insert_event(
            cur,
            company_code=company,
            event_type="converted",
            assignment_id=assignment_id,
            actor_user_id=actor_user_id,
            payload={"from": asn["status"]},
        )
        return {"ok": True, "assignment": _assignment_row(dict(updated))}

    if dst == "in_progress":
        cur.execute(
            """
            UPDATE preboard_assignments
               SET status='in_progress',
                   row_version=row_version+1,
                   updated_at=now()
             WHERE company_code=%s AND assignment_id=%s AND row_version=%s
            RETURNING *
            """,
            (company, str(assignment_id), int(asn["row_version"])),
        )
        updated = cur.fetchone()
        if not updated:
            return {"ok": False, "error": "concurrency_conflict"}
        _insert_event(
            cur,
            company_code=company,
            event_type="started",
            assignment_id=assignment_id,
            actor_user_id=actor_user_id,
            payload={"from": asn["status"]},
        )
        return {"ok": True, "assignment": _assignment_row(dict(updated))}

    # blocked — only via recompute from item blockers
    return recompute_assignment_status(
        cur, company_code=company, assignment_id=assignment_id, actor_user_id=actor_user_id
    )


def set_joining_date(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    joining_date: date,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Write joining_date on assignment + hub employment start_date (canonical)."""
    gate = preboarding_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    asn = get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    if not isinstance(joining_date, date):
        return {"ok": False, "error": "joining_date_invalid"}

    cur.execute(
        """
        UPDATE preboard_assignments
           SET joining_date=%s, row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND assignment_id=%s
        RETURNING *
        """,
        (joining_date, company, str(assignment_id)),
    )
    updated = cur.fetchone()
    # Propagate to hub employees.start_date (single field authority for readers).
    cur.execute(
        """
        UPDATE employees
           SET start_date=%s, updated_at=now()
         WHERE company_code=%s AND employee_key=%s
        """,
        (joining_date, company, asn["employee_key"]),
    )
    try:
        cur.execute(
            """
            UPDATE employee_employments
               SET start_date=%s, updated_at=now()
             WHERE company_code=%s AND legacy_employee_key=%s
            """,
            (joining_date, company, asn["employee_key"]),
        )
    except Exception:
        pass
    _insert_event(
        cur,
        company_code=company,
        event_type="joining_date_set",
        assignment_id=assignment_id,
        actor_user_id=actor_user_id,
        payload={"joining_date": str(joining_date), "source": "set_joining_date"},
    )
    # Refresh due dates from offsets
    ensure_default_template(cur, company)
    cur.execute(
        """
        SELECT item_key, due_offset_days FROM preboarding_template_items
         WHERE company_code=%s AND template_id=%s
        """,
        (company, asn.get("template_id") or DEFAULT_TEMPLATE_ID),
    )
    offsets = {str(r["item_key"]): r.get("due_offset_days") for r in (cur.fetchall() or [])}
    for item in list_items(cur, company_code=company, assignment_id=assignment_id):
        off = offsets.get(item["item_key"])
        if off is None:
            continue
        due_at = datetime.combine(
            joining_date + timedelta(days=int(off)),
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        cur.execute(
            "UPDATE preboard_items SET due_at=%s, updated_at=now() WHERE item_id=%s",
            (due_at, item["item_id"]),
        )
    return {"ok": True, "assignment": _assignment_row(dict(updated)) if updated else asn}


# --- OPTIONAL integrations (gated; safe when modules off) -------------------------

def offer_auto_create_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    """OPTIONAL_INTEGRATION: preboarding ∧ employment_offers ∧ setting."""
    company = company_code_norm(company_code)
    gate = preboarding_enabled_for_company(cur, company)
    if not gate.get("ok"):
        return {"enabled": False, "reason": "preboarding_off", "gate": gate}
    settings = get_settings(cur, company)
    if not settings.get("auto_create_on_offer_accept"):
        return {"enabled": False, "reason": "company_setting_off"}
    offers_on = False
    try:
        cur.execute(
            """
            SELECT enabled FROM company_modules
             WHERE company_code=%s AND module_key='employment_offers'
             LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        offers_on = bool(row and dict(row).get("enabled"))
    except Exception:
        offers_on = False
    if not offers_on:
        return {"enabled": False, "reason": "employment_offers_off"}
    try:
        import capability_contracts as cc

        ev = cc.evaluate_contract(
            "preboarding.auto_create_on_offer_accept",
            enabled_modules={"preboarding", "employment_offers"},
            company_settings={
                "preboarding.auto_create_on_offer_accept": settings.get("auto_create_on_offer_accept")
            },
        )
        if not ev.get("active"):
            return {"enabled": False, "reason": "contract_inactive", "eval": ev}
    except Exception:
        pass
    return {"enabled": True, "reason": "optional_integration_active", "company_code": company}


def maybe_create_assignment_from_offer(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    offer_id: str,
    joining_date: date | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Call-site helper for offer accept. No-op unless OPTIONAL contract active."""
    gate = offer_auto_create_enabled(cur, company_code)
    if not gate.get("enabled"):
        return {"ok": True, "skipped": True, "reason": gate.get("reason")}
    result = create_assignment(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        joining_date=joining_date,
        offer_id=offer_id,
        created_by_user_id=actor_user_id,
        idempotency_key=f"offer:{offer_id}",
    )
    if result.get("ok"):
        _insert_event(
            cur,
            company_code=company_code_norm(company_code),
            event_type="offer_auto_create",
            assignment_id=result.get("assignment", {}).get("assignment_id"),
            actor_user_id=actor_user_id,
            payload={"offer_id": offer_id, "replayed": result.get("replayed")},
        )
    return result


def plan_onboarding_handoff_dedupe(
    cur: Any, *, company_code: str, employee_key: str
) -> dict[str, Any]:
    """Find onboarding_items already complete for overlapping keys (read-only)."""
    company = company_code_norm(company_code)
    satisfied: dict[str, Any] = {}
    try:
        cur.execute(
            """
            SELECT item_id, status, document_type
              FROM onboarding_items
             WHERE company_code=%s AND employee_key=%s
            """,
            (company, str(employee_key)),
        )
        for row in cur.fetchall() or []:
            d = dict(row)
            iid = str(d.get("item_id") or "")
            if iid not in ONBOARDING_OVERLAP_KEYS:
                continue
            st = str(d.get("status") or "").strip().lower()
            if st in {"received", "verified", "completed", "done", "waived", "approved"}:
                satisfied[iid] = {"status": st, "document_type": d.get("document_type")}
    except Exception as exc:
        return {"ok": True, "satisfied": {}, "error_soft": str(exc)}
    return {"ok": True, "satisfied": satisfied}


def apply_onboarding_handoff_dedupe(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """OPTIONAL: mark overlapping preboard items done from onboarding evidence (no dupes)."""
    company = company_code_norm(company_code)
    settings = get_settings(cur, company)
    if not settings.get("handoff_onboarding_enabled"):
        return {"ok": True, "skipped": True, "reason": "handoff_setting_off"}
    # Also require onboarding module
    try:
        cur.execute(
            """
            SELECT enabled FROM company_modules
             WHERE company_code=%s AND module_key='onboarding' LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        if not (row and dict(row).get("enabled")):
            return {"ok": True, "skipped": True, "reason": "onboarding_module_off"}
    except Exception:
        return {"ok": True, "skipped": True, "reason": "onboarding_module_unavailable"}

    asn = get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    plan = plan_onboarding_handoff_dedupe(
        cur, company_code=company, employee_key=asn["employee_key"]
    )
    applied: list[str] = []
    for item in list_items(cur, company_code=company, assignment_id=assignment_id):
        key = item["item_key"]
        if key not in plan.get("satisfied", {}):
            continue
        if item["status"] in {"done", "waived"}:
            continue
        cur.execute(
            """
            UPDATE preboard_items
               SET status='done',
                   completed_at=now(),
                   metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb,
                   row_version=row_version+1,
                   updated_at=now()
             WHERE item_id=%s
            """,
            (
                json.dumps(
                    {
                        "handoff_from": "onboarding",
                        "onboarding_status": plan["satisfied"][key].get("status"),
                    }
                ),
                item["item_id"],
            ),
        )
        applied.append(key)
    if applied:
        _insert_event(
            cur,
            company_code=company,
            event_type="handoff_dedupe",
            assignment_id=assignment_id,
            actor_user_id=actor_user_id,
            payload={"applied": applied},
        )
        recompute_assignment_status(
            cur, company_code=company, assignment_id=assignment_id, actor_user_id=actor_user_id
        )
    return {"ok": True, "applied": applied, "plan": plan}


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Set WATHEFNI_PREBOARDING=off",
            "Remove company from WATHEFNI_PREBOARDING_COMPANIES",
            "SET preboarding_settings.enabled=false",
            "Disable company_modules.preboarding",
        ],
        "data": [
            "Retain preboard_* tables; do not DROP",
            "pending_start employment remains canonical — close via cancel/converted paths",
            "Do not invent active eligibility from retained preboard rows",
        ],
        "schema_version": PREBOARDING_SCHEMA_VERSION,
        "invariants": [
            "ready is derived from required items",
            "pending_start never implies payroll/attendance/leave/shifts/ESS",
            "no duplicate employee/employment on convert",
        ],
    }
