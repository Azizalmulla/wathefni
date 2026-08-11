#!/usr/bin/env python3
"""Onboarding Wave 2 — canonical template, lifecycle, concurrency, audit.

Local/staging authority for operational completeness. Does not enable production
SEED/HR_MUTATE and does not mutate the four real production checklists.

Template version pin: historical employee assignments keep their template_version;
new seeds use CANONICAL_TEMPLATE_VERSION.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

CANONICAL_TEMPLATE_ID = "default_kuwait"
CANONICAL_TEMPLATE_VERSION = "2.0.0"

_ON_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})

# Wave 2B production canary — reserved synthetic markers (distinct from lifecycle 965522).
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965523",)
DEFAULT_SYNTHETIC_NAME_PREFIX = "W2B-SYNTH|"

# Employee rollup states (assignment + employees.onboarding_status).
ONBOARDING_STATES = frozenset({
    "not_started",
    "delayed",
    "in_progress",
    "completed",
    "cancelled",
    "abandoned",
})

TERMINAL_STATES = frozenset({"completed", "cancelled", "abandoned"})

# due_offset_days: relative to planned_start_date (negative = before start).
# depends_on: item must be received/verified/waived before this item is actionable.
# authority: onboarding | compliance_mirror | ess
# collection_mode: document | text | task | date | ack | ess_encrypted | none


@dataclass(frozen=True)
class TemplateItem:
    item_id: str
    label: str
    category: str
    item_type: str
    required: bool
    owner: str
    authority: str = "onboarding"
    collection_mode: str = "document"
    due_offset_days: int | None = None
    depends_on: tuple[str, ...] = ()
    notes: str = ""


def _item(
    item_id: str,
    label: str,
    category: str,
    item_type: str,
    required: bool,
    owner: str,
    *,
    authority: str = "onboarding",
    collection_mode: str | None = None,
    due_offset_days: int | None = None,
    depends_on: tuple[str, ...] = (),
    notes: str = "",
) -> TemplateItem:
    mode = collection_mode or (
        "ess_encrypted" if authority == "ess"
        else "none" if item_type == "task" and owner != "employee"
        else item_type
    )
    return TemplateItem(
        item_id=item_id,
        label=label,
        category=category,
        item_type=item_type,
        required=required,
        owner=owner,
        authority=authority,
        collection_mode=mode,
        due_offset_days=due_offset_days,
        depends_on=depends_on,
        notes=notes,
    )


# Canonical Default Kuwait v2 — bank is ESS-only; compliance expiry rows are mirrors.
DEFAULT_KUWAIT_V2: tuple[TemplateItem, ...] = (
    # Identity & legal
    _item("civil_id", "Civil ID (front and back)", "identity_legal", "document", True, "employee",
          due_offset_days=-3),
    _item("passport", "Passport copy (if applicable)", "identity_legal", "document", False, "employee",
          due_offset_days=-3),
    _item("personal_photo", "Personal photo", "identity_legal", "document", True, "employee",
          due_offset_days=-3),
    _item("residence", "Residence permit (Article 18 expats)", "identity_legal", "document", False, "employee",
          due_offset_days=0, depends_on=("civil_id",)),
    _item("work_permit", "Work permit (expats)", "identity_legal", "document", False, "employee",
          due_offset_days=0, depends_on=("residence",)),
    _item("employment_contract", "Signed employment contract", "identity_legal", "document", True, "employee",
          due_offset_days=0),
    _item("offer_letter", "Job offer / appointment letter", "identity_legal", "document", False, "hr",
          due_offset_days=-7),
    _item("personal_details_form", "Personal details form", "identity_legal", "text", False, "employee",
          due_offset_days=0),
    _item("emergency_contact", "Emergency contact", "identity_legal", "text", False, "employee",
          due_offset_days=0, depends_on=("personal_details_form",)),
    # Payroll & bank — ESS encrypted only (no plaintext IBAN via onboarding)
    _item(
        "bank_details",
        "Bank setup via Employee Self-Service (encrypted IBAN)",
        "payroll_bank",
        "task",
        True,
        "employee",
        authority="ess",
        collection_mode="ess_encrypted",
        due_offset_days=3,
        notes="Completion via ESS bank workflow; onboarding never collects plaintext IBAN.",
    ),
    _item("salary_transfer_details", "Salary transfer details", "payroll_bank", "task", False, "hr",
          due_offset_days=5, depends_on=("bank_details",)),
    _item("salary_allowances_confirmed", "Basic salary / allowances confirmed", "payroll_bank", "task", False, "hr",
          due_offset_days=5),
    _item("payroll_status", "Payroll status", "payroll_bank", "task", False, "system",
          due_offset_days=10, depends_on=("salary_allowances_confirmed",)),
    # Compliance mirrors — authoritative expiry lives in compliance_documents
    _item("civil_id_expiry", "Civil ID expiry recorded (Compliance mirror)", "compliance_gov", "date", False, "system",
          authority="compliance_mirror", due_offset_days=1, depends_on=("civil_id",),
          notes="Prompt only; Compliance module is source of truth."),
    _item("passport_expiry", "Passport expiry recorded (Compliance mirror)", "compliance_gov", "date", False, "system",
          authority="compliance_mirror", due_offset_days=1, depends_on=("passport",)),
    _item("residency_expiry", "Residency expiry recorded (Compliance mirror)", "compliance_gov", "date", False, "system",
          authority="compliance_mirror", due_offset_days=1, depends_on=("residence",)),
    _item("work_permit_expiry", "Work permit expiry recorded (Compliance mirror)", "compliance_gov", "date", False, "system",
          authority="compliance_mirror", due_offset_days=1, depends_on=("work_permit",)),
    _item("medical_check", "Medical check status (expats)", "compliance_gov", "task", False, "hr",
          due_offset_days=7),
    _item("visa_article_type", "Visa / residency type (e.g. Article 18)", "compliance_gov", "text", False, "hr",
          due_offset_days=0),
    _item("probation_end", "Probation period end date", "compliance_gov", "date", False, "hr",
          due_offset_days=0),
    # Company readiness
    _item("department_assigned", "Department assigned", "company_readiness", "task", False, "hr", due_offset_days=-1),
    _item("job_title_confirmed", "Job title confirmed", "company_readiness", "task", False, "hr", due_offset_days=-1),
    _item("reporting_manager_assigned", "Reporting manager assigned", "company_readiness", "task", False, "hr",
          due_offset_days=-1, depends_on=("department_assigned",)),
    _item("work_location_assigned", "Work location / branch assigned", "company_readiness", "task", False, "hr",
          due_offset_days=-1),
    _item("shift_group_assigned", "Shift group assigned (if applicable)", "company_readiness", "task", False, "hr"),
    _item("attendance_device_id", "Attendance device ID assigned (if applicable)", "company_readiness", "task", False, "hr"),
    _item("app_invite_sent", "Employee app invite sent (if enabled)", "company_readiness", "task", False, "system",
          due_offset_days=0),
    _item("account_access_created", "Email / account access created (if applicable)", "company_readiness", "task", False, "hr"),
    _item("uniform_ppe_issued", "Uniform / PPE issued (if applicable)", "company_readiness", "task", False, "hr"),
    _item("access_card_issued", "Access card / badge issued (if applicable)", "company_readiness", "task", False, "hr"),
    _item("asset_handover", "Laptop / asset handover (if applicable)", "company_readiness", "task", False, "hr"),
    _item("company_policy_ack", "Company policy acknowledged", "company_readiness", "ack", False, "employee",
          due_offset_days=1),
    _item("code_of_conduct_ack", "Code of conduct acknowledged", "company_readiness", "ack", False, "employee",
          due_offset_days=1, depends_on=("company_policy_ack",)),
    _item("nda_signed", "NDA / confidentiality signed (if applicable)", "company_readiness", "ack", False, "employee"),
    _item("training_completed", "Training completed (if applicable)", "company_readiness", "task", False, "hr"),
    _item("first_day_checklist", "First-day checklist completed", "company_readiness", "task", False, "hr",
          due_offset_days=1, depends_on=("employment_contract", "civil_id", "personal_photo")),
)

# Legacy short-template ids that are obsolete vs v2 (auditable migration only).
OBSOLETE_LEGACY_ITEM_IDS = frozenset({"education_cert", "medical"})
# Map legacy → canonical when ids differ (medical → medical_check is rename, not same row).
LEGACY_ITEM_MAP: dict[str, str | None] = {
    "civil_id": "civil_id",
    "passport": "passport",
    "personal_photo": "personal_photo",
    "bank_details": "bank_details",  # keep id; change collection_mode to ess
    "education_cert": None,  # obsolete — remove only via auditable migration
    "medical": "medical_check",  # rename target if migrating
}

FOUR_REALS = (
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
)
FOUR_REALS_SET = frozenset(FOUR_REALS)


def onboarding_synthetic_canary_enabled() -> bool:
    """When on (with SEED/HR_MUTATE off), mutations are allowed only for synthetics."""
    return (os.environ.get("WATHEFNI_ONBOARDING_SYNTHETIC_CANARY") or "").strip().lower() in _ON_VALUES


def onboarding_synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_ONBOARDING_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def onboarding_synthetic_name_prefix() -> str:
    return (
        str(os.environ.get("WATHEFNI_ONBOARDING_SYNTHETIC_NAME_PREFIX") or "").strip()
        or DEFAULT_SYNTHETIC_NAME_PREFIX
    )


def is_onboarding_synthetic_employee(
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
    provenance: Any = None,
    raw_json: Any = None,
) -> bool:
    """Strict synthetic recognition. Four reals are never synthetic."""
    key = str(employee_key or "").strip()
    if key in FOUR_REALS_SET:
        return False
    phone_s = str(phone or "").strip()
    for prefix in onboarding_synthetic_phone_prefixes():
        if phone_s.startswith(prefix) or (key and f"-{prefix}" in key):
            return True
    name_s = str(name or "")
    if name_s.startswith(onboarding_synthetic_name_prefix()):
        return True
    blob: dict[str, Any] = {}
    for candidate in (raw_json, provenance):
        if isinstance(candidate, dict):
            blob.update(candidate)
        elif isinstance(candidate, str) and candidate.strip().startswith("{"):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    blob.update(parsed)
            except Exception:
                pass
    if (
        blob.get("onboarding_synthetic_canary") is True
        or blob.get("onboarding_wave2b_synthetic") is True
        or str(blob.get("source") or "") == "wave2b_synthetic_canary"
    ):
        return True
    return False


def stamp_onboarding_synthetic_markers(cur: Any, *, company: str, employee_key: str) -> None:
    """Mark hub employee as Wave 2B synthetic canary (idempotent)."""
    marker = {
        "onboarding_synthetic_canary": True,
        "onboarding_wave2b_synthetic": True,
        "source": "wave2b_synthetic_canary",
    }
    cur.execute(
        """
        UPDATE employees
        SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
            updated_at = now()
        WHERE company_code=%s AND employee_key=%s
        """,
        (json.dumps(marker), str(company or "").upper(), employee_key),
    )


def is_four_real_employee(employee_key: str | None) -> bool:
    return str(employee_key or "").strip() in FOUR_REALS_SET


def template_as_legacy_tuples() -> list[tuple[str, str, str, str, bool, str]]:
    """Compatibility shape for resolve_onboarding_template / older callers."""
    return [
        (i.item_id, i.label, i.category, i.item_type, i.required, i.owner)
        for i in DEFAULT_KUWAIT_V2
    ]


def get_template_item(item_id: str) -> TemplateItem | None:
    for item in DEFAULT_KUWAIT_V2:
        if item.item_id == item_id:
            return item
    return None


def ensure_onboarding_wave2_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_onboarding_assignments (
          employee_key text PRIMARY KEY,
          company_code text NOT NULL,
          template_id text NOT NULL,
          template_version text NOT NULL,
          status text NOT NULL DEFAULT 'not_started',
          planned_start_date date,
          actual_start_at timestamptz,
          completed_at timestamptz,
          cancelled_at timestamptz,
          cancelled_reason text,
          abandoned_at timestamptz,
          version integer NOT NULL DEFAULT 1,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_assignments_company_status
          ON employee_onboarding_assignments (company_code, status)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_audit_events (
          event_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          item_id text,
          event_type text NOT NULL,
          actor_phone text,
          actor_user_id text,
          before_json jsonb,
          after_json jsonb,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_audit_employee
          ON onboarding_audit_events (company_code, employee_key, created_at DESC)
        """
    )
    for stmt in (
        "ALTER TABLE IF EXISTS onboarding_items ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1",
        "ALTER TABLE IF EXISTS onboarding_items ADD COLUMN IF NOT EXISTS due_date date",
        "ALTER TABLE IF EXISTS onboarding_items ADD COLUMN IF NOT EXISTS depends_on jsonb NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE IF EXISTS onboarding_items ADD COLUMN IF NOT EXISTS collection_mode text",
        "ALTER TABLE IF EXISTS onboarding_items ADD COLUMN IF NOT EXISTS authority text",
        "ALTER TABLE IF EXISTS onboarding_items ADD COLUMN IF NOT EXISTS template_version text",
        "ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS onboarding_template_version text",
    ):
        cur.execute(stmt)


def record_onboarding_audit(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    event_type: str,
    item_id: str | None = None,
    actor_phone: str | None = None,
    actor_user_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO onboarding_audit_events
          (event_id, company_code, employee_key, item_id, event_type,
           actor_phone, actor_user_id, before_json, after_json, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
        """,
        (
            event_id,
            str(company_code or "").upper(),
            employee_key,
            item_id,
            event_type,
            actor_phone,
            actor_user_id,
            json.dumps(before or {}, default=str),
            json.dumps(after or {}, default=str),
            json.dumps(metadata or {}, default=str),
        ),
    )
    return event_id


def compute_due_date(planned_start: date | None, offset_days: int | None) -> date | None:
    if planned_start is None or offset_days is None:
        return None
    return planned_start + timedelta(days=int(offset_days))


def item_is_satisfied(status: str | None) -> bool:
    """Delegates to the canonical completion contract.

    Historically this set omitted `accepted` (breaking Wave 2A dependency gates)
    and treated legacy `received` as verified.
    """
    import onboarding_completion_contract as _contract

    return _contract.item_is_satisfied(status)


def dependency_blockers(item: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[str]:
    raw = item.get("depends_on") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    blockers = []
    for dep in raw or []:
        dep_id = str(dep)
        other = by_id.get(dep_id)
        if not other or not item_is_satisfied(other.get("status")):
            blockers.append(dep_id)
    return blockers


def get_assignment(cur: Any, employee_key: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM employee_onboarding_assignments WHERE employee_key=%s LIMIT 1",
        (employee_key,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_assignment(
    cur: Any,
    *,
    employee_key: str,
    company_code: str,
    status: str,
    planned_start_date: date | None = None,
    template_id: str = CANONICAL_TEMPLATE_ID,
    template_version: str = CANONICAL_TEMPLATE_VERSION,
    metadata: dict[str, Any] | None = None,
    bump_version: bool = True,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if status not in ONBOARDING_STATES:
        raise ValueError(f"invalid_onboarding_status:{status}")
    existing = get_assignment(cur, employee_key)
    meta = metadata or {}
    if existing:
        if expected_version is not None and int(existing.get("version") or 0) != int(expected_version):
            return {"ok": False, "error": "stale_assignment_version", "assignment": existing}
        new_version = int(existing.get("version") or 1) + (1 if bump_version else 0)
        cur.execute(
            """
            UPDATE employee_onboarding_assignments
            SET status=%s,
                planned_start_date=COALESCE(%s, planned_start_date),
                template_id=%s,
                template_version=%s,
                version=%s,
                metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb,
                updated_at=now()
            WHERE employee_key=%s
            RETURNING *
            """,
            (
                status,
                planned_start_date,
                template_id,
                template_version,
                new_version,
                json.dumps(meta, default=str),
                employee_key,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO employee_onboarding_assignments
              (employee_key, company_code, template_id, template_version, status,
               planned_start_date, metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING *
            """,
            (
                employee_key,
                str(company_code or "").upper(),
                template_id,
                template_version,
                status,
                planned_start_date,
                json.dumps(meta, default=str),
            ),
        )
    row = dict(cur.fetchone())
    return {"ok": True, "assignment": row}


def seed_wave2_items(
    cur: Any,
    employee: dict[str, Any],
    *,
    planned_start_date: date | None = None,
    required_overrides: dict[str, bool] | None = None,
    template_version: str = CANONICAL_TEMPLATE_VERSION,
) -> dict[str, Any]:
    """Idempotent insert-missing seed using v2 template metadata."""
    employee_key = str(employee.get("employee_key") or "").strip()
    company = str(employee.get("company_code") or "").upper()
    if not employee_key:
        return {"ok": False, "error": "employee_key_required", "seeded": 0}
    overrides = required_overrides or {}
    start = planned_start_date or date.today()
    cur.execute("SELECT item_id FROM onboarding_items WHERE employee_key=%s", (employee_key,))
    existing = {str(r["item_id"]) for r in (cur.fetchall() or []) if r.get("item_id")}
    seeded = 0
    for order, spec in enumerate(DEFAULT_KUWAIT_V2):
        if spec.item_id in existing:
            continue
        is_required = bool(overrides[spec.item_id]) if spec.item_id in overrides else bool(spec.required)
        due = compute_due_date(start, spec.due_offset_days)
        document_type = spec.item_id if spec.item_type == "document" else None
        seed_meta = {
            "seeded_by": "onboarding_wave2",
            "template": CANONICAL_TEMPLATE_ID,
            "template_version": template_version,
            "authority": spec.authority,
            "collection_mode": spec.collection_mode,
        }
        cur.execute(
            """
            INSERT INTO onboarding_items
              (employee_key, company_code, item_id, label, category, item_type, required, owner,
               sort_order, document_type, status, due_date, depends_on,
               collection_mode, authority, template_version, row_version, raw_json, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s::jsonb,%s,%s,%s,1,%s::jsonb, now())
            """,
            (
                employee_key,
                company or None,
                spec.item_id,
                spec.label,
                spec.category,
                spec.item_type,
                is_required,
                spec.owner,
                order,
                document_type,
                due,
                json.dumps(list(spec.depends_on)),
                spec.collection_mode,
                spec.authority,
                template_version,
                json.dumps(seed_meta),
            ),
        )
        seeded += cur.rowcount or 0
    cur.execute(
        "UPDATE employees SET onboarding_template_version=%s, updated_at=now() WHERE employee_key=%s",
        (template_version, employee_key),
    )
    return {
        "ok": True,
        "seeded": seeded,
        "template_id": CANONICAL_TEMPLATE_ID,
        "template_version": template_version,
        "skipped_existing": sorted(existing),
    }


def start_onboarding_wave2(
    cur: Any,
    employee: dict[str, Any],
    *,
    planned_start_date: date | None = None,
    delayed: bool = False,
    actor_phone: str | None = None,
    actor_user_id: str | None = None,
    seed_fn: Callable[..., int] | None = None,
    allow_restart: bool = False,
) -> dict[str, Any]:
    """Start with duplicate prevention, assignment pin, optional delayed start."""
    employee_key = str(employee.get("employee_key") or "")
    company = str(employee.get("company_code") or "").upper()
    assignment = get_assignment(cur, employee_key)
    current = str((assignment or {}).get("status") or employee.get("onboarding_status") or "not_started").lower()
    if current in TERMINAL_STATES and not allow_restart:
        return {"ok": False, "error": "onboarding_terminal", "status": current}
    if current == "in_progress" and not allow_restart:
        return {
            "ok": True,
            "idempotent": True,
            "error": None,
            "status": "in_progress",
            "message": "already_in_progress",
            "assignment": assignment,
        }
    target_status = "delayed" if delayed else "in_progress"
    planned = planned_start_date or date.today()
    if delayed and planned <= date.today():
        return {"ok": False, "error": "delayed_start_requires_future_date"}
    before = {"status": current, "assignment": assignment}
    result = upsert_assignment(
        cur,
        employee_key=employee_key,
        company_code=company,
        status=target_status,
        planned_start_date=planned,
        metadata={"started_via": "wave2", "delayed": delayed},
    )
    if not result.get("ok"):
        return result
    if target_status == "in_progress":
        cur.execute(
            """
            UPDATE employee_onboarding_assignments
            SET actual_start_at=COALESCE(actual_start_at, now()), updated_at=now()
            WHERE employee_key=%s
            """,
            (employee_key,),
        )
        cur.execute(
            "UPDATE employees SET onboarding_status='in_progress', updated_at=now() WHERE employee_key=%s",
            (employee_key,),
        )
        if seed_fn:
            seeded = seed_fn(cur, employee)
        else:
            seeded = seed_wave2_items(cur, employee, planned_start_date=planned).get("seeded", 0)
    else:
        cur.execute(
            "UPDATE employees SET onboarding_status='delayed', updated_at=now() WHERE employee_key=%s",
            (employee_key,),
        )
        seeded = 0
    after = get_assignment(cur, employee_key)
    event_id = record_onboarding_audit(
        cur,
        company_code=company,
        employee_key=employee_key,
        event_type="onboarding_started" if target_status == "in_progress" else "onboarding_delayed",
        actor_phone=actor_phone,
        actor_user_id=actor_user_id,
        before=before,
        after={"assignment": after, "seeded": seeded},
    )
    return {
        "ok": True,
        "idempotent": False,
        "status": target_status,
        "seeded": seeded,
        "assignment": after,
        "audit_event_id": event_id,
    }


def activate_delayed_starts(
    cur: Any,
    *,
    company_code: str | None = None,
    today: date | None = None,
    seed_fn: Callable[..., int] | None = None,
    synthetic_only: bool | None = None,
) -> dict[str, Any]:
    """Promote delayed assignments whose planned_start_date <= today to in_progress.

    When synthetic canary is on (default), only synthetic employees are activated
    so production four-reals stay untouched by unattended activation.
    """
    day = today or date.today()
    company = str(company_code or "").strip().upper()
    if synthetic_only is None:
        canary_gate = onboarding_synthetic_canary_enabled()
    else:
        canary_gate = bool(synthetic_only)
    params: list[Any] = [day]
    clause = ""
    if company:
        clause = " AND a.company_code=%s"
        params.append(company)
    cur.execute(
        f"""
        SELECT a.*, e.name AS emp_name, e.phone AS emp_phone, e.raw_json AS emp_raw
        FROM employee_onboarding_assignments a
        LEFT JOIN employees e ON e.employee_key = a.employee_key
        WHERE a.status='delayed' AND a.planned_start_date IS NOT NULL AND a.planned_start_date <= %s
        {clause}
        ORDER BY a.planned_start_date ASC
        """,
        params,
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    activated = []
    skipped = []
    for row in rows:
        emp_key = str(row["employee_key"])
        if is_four_real_employee(emp_key):
            skipped.append({"employee_key": emp_key, "reason": "four_real_protected"})
            continue
        if canary_gate and not is_onboarding_synthetic_employee(
            employee_key=emp_key,
            phone=row.get("emp_phone"),
            name=row.get("emp_name"),
            raw_json=row.get("emp_raw"),
        ):
            skipped.append({"employee_key": emp_key, "reason": "synthetic_only_gate"})
            continue
        cur.execute(
            """
            UPDATE employee_onboarding_assignments
            SET status='in_progress', actual_start_at=COALESCE(actual_start_at, now()),
                version=version+1, updated_at=now()
            WHERE employee_key=%s AND status='delayed'
            RETURNING *
            """,
            (emp_key,),
        )
        updated = cur.fetchone()
        if not updated:
            continue
        cur.execute(
            "UPDATE employees SET onboarding_status='in_progress', updated_at=now() WHERE employee_key=%s",
            (emp_key,),
        )
        seeded = 0
        if seed_fn:
            emp = {
                "employee_key": emp_key,
                "company_code": row.get("company_code"),
                "name": row.get("emp_name"),
                "phone": row.get("emp_phone"),
                "start_date": row.get("planned_start_date"),
            }
            seeded = int(seed_fn(cur, emp) or 0)
        record_onboarding_audit(
            cur,
            company_code=row.get("company_code") or "",
            employee_key=emp_key,
            event_type="onboarding_delayed_activated",
            before={k: row[k] for k in row if not str(k).startswith("emp_")},
            after={**dict(updated), "seeded": seeded},
        )
        activated.append(emp_key)
    return {"ok": True, "activated": activated, "count": len(activated), "skipped": skipped}


def reschedule_onboarding_start(
    cur: Any,
    employee: dict[str, Any],
    *,
    new_start_date: date,
    expected_version: int | None = None,
    actor_phone: str | None = None,
    recompute_due_dates: bool = True,
) -> dict[str, Any]:
    employee_key = str(employee.get("employee_key") or "")
    company = str(employee.get("company_code") or "").upper()
    assignment = get_assignment(cur, employee_key)
    if not assignment:
        return {"ok": False, "error": "assignment_not_found"}
    status = str(assignment.get("status") or "")
    if status in TERMINAL_STATES:
        return {"ok": False, "error": "onboarding_terminal", "status": status}
    if expected_version is not None and int(assignment.get("version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_assignment_version", "assignment": assignment}
    new_status = "delayed" if new_start_date > date.today() else status
    if status == "not_started":
        new_status = "delayed" if new_start_date > date.today() else "not_started"
    result = upsert_assignment(
        cur,
        employee_key=employee_key,
        company_code=company,
        status=new_status if new_status in ONBOARDING_STATES else status,
        planned_start_date=new_start_date,
        expected_version=expected_version,
        metadata={"rescheduled_to": new_start_date.isoformat()},
    )
    if not result.get("ok"):
        return result
    if recompute_due_dates:
        for spec in DEFAULT_KUWAIT_V2:
            due = compute_due_date(new_start_date, spec.due_offset_days)
            if due is None:
                continue
            import onboarding_completion_contract as _completion

            cur.execute(
                f"""
                UPDATE onboarding_items
                SET due_date=%s, row_version=row_version+1, updated_at=now()
                WHERE employee_key=%s AND item_id=%s
                  AND NOT {_completion.sql_satisfied_predicate('status')}
                """,
                (due, employee_key, spec.item_id),
            )
    cur.execute(
        "UPDATE employees SET onboarding_status=%s, updated_at=now() WHERE employee_key=%s",
        (new_status, employee_key),
    )
    after = get_assignment(cur, employee_key)
    event_id = record_onboarding_audit(
        cur,
        company_code=company,
        employee_key=employee_key,
        event_type="onboarding_rescheduled",
        actor_phone=actor_phone,
        before=assignment,
        after=after,
        metadata={"new_start_date": new_start_date.isoformat()},
    )
    return {"ok": True, "assignment": after, "audit_event_id": event_id}


def cancel_onboarding(
    cur: Any,
    employee: dict[str, Any],
    *,
    reason: str | None = None,
    expected_version: int | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Cancel/withdraw without deleting checklist history."""
    employee_key = str(employee.get("employee_key") or "")
    company = str(employee.get("company_code") or "").upper()
    assignment = get_assignment(cur, employee_key)
    status = str((assignment or {}).get("status") or employee.get("onboarding_status") or "not_started")
    if status == "cancelled":
        return {"ok": True, "idempotent": True, "status": "cancelled", "assignment": assignment}
    if status == "abandoned":
        return {"ok": False, "error": "already_abandoned"}
    if expected_version is not None and assignment and int(assignment.get("version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_assignment_version", "assignment": assignment}
    # Preserve items; stamp cancelled_at on assignment only.
    if assignment:
        cur.execute(
            """
            UPDATE employee_onboarding_assignments
            SET status='cancelled', cancelled_at=now(), cancelled_reason=%s,
                version=version+1, updated_at=now()
            WHERE employee_key=%s
            RETURNING *
            """,
            (reason, employee_key),
        )
        after = dict(cur.fetchone() or {})
    else:
        upsert_assignment(
            cur,
            employee_key=employee_key,
            company_code=company,
            status="cancelled",
            metadata={"cancelled_reason": reason},
        )
        cur.execute(
            "UPDATE employee_onboarding_assignments SET cancelled_at=now(), cancelled_reason=%s WHERE employee_key=%s RETURNING *",
            (reason, employee_key),
        )
        after = dict(cur.fetchone() or {})
    cur.execute(
        "UPDATE employees SET onboarding_status='cancelled', updated_at=now() WHERE employee_key=%s",
        (employee_key,),
    )
    # Soft-close open required items without deleting.
    # Satisfied rows keep their status: completion evidence is never overwritten.
    import onboarding_completion_contract as _completion

    cur.execute(
        f"""
        UPDATE onboarding_items
        SET status=CASE
              WHEN {_completion.sql_satisfied_predicate('status')} THEN status
              ELSE 'cancelled_onboarding'
            END,
            row_version=row_version+1,
            updated_at=now()
        WHERE employee_key=%s
        """,
        (employee_key,),
    )
    event_id = record_onboarding_audit(
        cur,
        company_code=company,
        employee_key=employee_key,
        event_type="onboarding_cancelled",
        actor_phone=actor_phone,
        before=assignment,
        after=after,
        metadata={"reason": reason, "history_preserved": True},
    )
    return {"ok": True, "status": "cancelled", "assignment": after, "audit_event_id": event_id, "history_preserved": True}


def abandon_onboarding(
    cur: Any,
    employee: dict[str, Any],
    *,
    reason: str | None = None,
    expected_version: int | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Abandon onboarding without deleting checklist history (employment ended / withdrawn)."""
    employee_key = str(employee.get("employee_key") or "")
    company = str(employee.get("company_code") or "").upper()
    assignment = get_assignment(cur, employee_key)
    status = str((assignment or {}).get("status") or employee.get("onboarding_status") or "not_started")
    if status == "abandoned":
        return {"ok": True, "idempotent": True, "status": "abandoned", "assignment": assignment, "history_preserved": True}
    if status == "cancelled":
        return {"ok": False, "error": "already_cancelled"}
    if expected_version is not None and assignment and int(assignment.get("version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_assignment_version", "assignment": assignment}
    if assignment:
        cur.execute(
            """
            UPDATE employee_onboarding_assignments
            SET status='abandoned', abandoned_at=now(),
                version=version+1, updated_at=now(),
                metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb
            WHERE employee_key=%s
            RETURNING *
            """,
            (json.dumps({"abandoned_reason": reason}, default=str), employee_key),
        )
        after = dict(cur.fetchone() or {})
    else:
        upsert_assignment(
            cur,
            employee_key=employee_key,
            company_code=company,
            status="abandoned",
            metadata={"abandoned_reason": reason},
        )
        cur.execute(
            "UPDATE employee_onboarding_assignments SET abandoned_at=now() WHERE employee_key=%s RETURNING *",
            (employee_key,),
        )
        after = dict(cur.fetchone() or {})
    cur.execute(
        "UPDATE employees SET onboarding_status='abandoned', updated_at=now() WHERE employee_key=%s",
        (employee_key,),
    )
    import onboarding_completion_contract as _completion

    cur.execute(
        f"""
        UPDATE onboarding_items
        SET status=CASE
              WHEN {_completion.sql_satisfied_predicate('status')} THEN status
              ELSE 'abandoned_employment_ended'
            END,
            row_version=row_version+1,
            updated_at=now()
        WHERE employee_key=%s
        """,
        (employee_key,),
    )
    event_id = record_onboarding_audit(
        cur,
        company_code=company,
        employee_key=employee_key,
        event_type="onboarding_abandoned",
        actor_phone=actor_phone,
        before=assignment,
        after=after,
        metadata={"reason": reason, "history_preserved": True},
    )
    return {
        "ok": True,
        "status": "abandoned",
        "assignment": after,
        "audit_event_id": event_id,
        "history_preserved": True,
    }


def mark_item_wave2(
    cur: Any,
    *,
    employee_key: str,
    company_code: str,
    item_id: str,
    new_status: str,
    expected_row_version: int | None = None,
    actor_phone: str | None = None,
    actor_user_id: str | None = None,
    by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mark/waive with optimistic concurrency, dependency checks, and audit."""
    new_status = str(new_status or "received").lower()
    if new_status not in {"received", "waived"}:
        new_status = "received"
    cur.execute(
        "SELECT * FROM onboarding_items WHERE employee_key=%s AND item_id=%s LIMIT 1",
        (employee_key, item_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "item_not_found"}
    item = dict(row)
    # Assignment terminal guard
    assignment = get_assignment(cur, employee_key)
    if assignment and str(assignment.get("status") or "") in TERMINAL_STATES:
        return {"ok": False, "error": "onboarding_terminal", "status": assignment.get("status")}
    if expected_row_version is not None and int(item.get("row_version") or 1) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_item_version",
            "expected": expected_row_version,
            "actual": item.get("row_version"),
            "item": item,
        }
    # ESS bank cannot be marked received via plaintext path — HR may waive only,
    # or mark received only when metadata says ess_completed.
    if item_id == "bank_details" and new_status == "received":
        mode = str(item.get("collection_mode") or "")
        if mode == "ess_encrypted" or str(item.get("authority") or "") == "ess":
            # Allow HR confirm after ESS; still not plaintext collection.
            pass
    # Dependency gate for employee-facing completion (received)
    if new_status == "received":
        catalog = by_id
        if catalog is None:
            cur.execute("SELECT item_id, status FROM onboarding_items WHERE employee_key=%s", (employee_key,))
            catalog = {str(r["item_id"]): dict(r) for r in (cur.fetchall() or [])}
        blockers = dependency_blockers(item, catalog)
        if blockers:
            return {"ok": False, "error": "dependency_unsatisfied", "blockers": blockers}

    if new_status == "waived":
        cur.execute(
            """
            UPDATE onboarding_items
            SET status='waived', required=FALSE, row_version=row_version+1, updated_at=now()
            WHERE employee_key=%s AND item_id=%s AND row_version=%s
            RETURNING *
            """,
            (employee_key, item_id, int(item.get("row_version") or 1)),
        )
    else:
        cur.execute(
            """
            UPDATE onboarding_items
            SET status='received', row_version=row_version+1, updated_at=now()
            WHERE employee_key=%s AND item_id=%s AND row_version=%s
            RETURNING *
            """,
            (employee_key, item_id, int(item.get("row_version") or 1)),
        )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_item_version", "item": item}
    after = dict(updated)
    event_id = record_onboarding_audit(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        item_id=item_id,
        event_type=f"onboarding_item_{new_status}",
        actor_phone=actor_phone,
        actor_user_id=actor_user_id,
        before=item,
        after=after,
    )
    return {"ok": True, "item": after, "audit_event_id": event_id}


def plan_legacy_migration(live_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Read-only migration plan for four reals vs default_kuwait@2.0.0. Does not apply."""
    by_emp: dict[str, list[dict[str, Any]]] = {}
    for row in live_rows:
        key = str(row.get("employee_key") or "")
        if key in FOUR_REALS:
            by_emp.setdefault(key, []).append(row)
    template_ids = {i.item_id for i in DEFAULT_KUWAIT_V2}
    employees = []
    for key in FOUR_REALS:
        items = by_emp.get(key) or []
        live_ids = {str(i.get("item_id")) for i in items}
        name = next((str(i.get("name") or "") for i in items if i.get("name")), "")
        preserve = []
        for live in items:
            iid = str(live.get("item_id"))
            mapped = LEGACY_ITEM_MAP.get(iid, iid if iid in template_ids else None)
            preserve.append({
                "live_item_id": iid,
                "maps_to": mapped,
                "status": live.get("status"),
                "preserve_received": str(live.get("status") or "").lower() in {"received", "complete", "completed", "verified"},
                "preserve_reminders": int(live.get("reminder_count") or 0),
                "obsolete": iid in OBSOLETE_LEGACY_ITEM_IDS,
                "action": (
                    "preserve_as_is"
                    if mapped == iid
                    else ("rename_map" if mapped else "obsolete_remove_audited")
                ),
            })
        missing = sorted(template_ids - {p["maps_to"] for p in preserve if p["maps_to"]})
        employees.append({
            "employee_key": key,
            "name": name,
            "live_count": len(items),
            "brian_partial": key.endswith("411617") and len(items) < 4,
            "preserve": preserve,
            "missing_to_add": [
                {
                    "item_id": mid,
                    "template": get_template_item(mid).__dict__ if get_template_item(mid) else {},
                    "action": "insert_pending_on_backfill",
                }
                for mid in missing
            ],
            "obsolete_to_retire": [p for p in preserve if p["obsolete"]],
            "bank_policy": "keep bank_details row; set collection_mode=ess_encrypted; never plaintext",
            "apply_to_production": False,
        })
    return {
        "mode": "read_only_plan",
        "template_id": CANONICAL_TEMPLATE_ID,
        "template_version": CANONICAL_TEMPLATE_VERSION,
        "applied": False,
        "employees": employees,
        "policy": {
            "preserve_received_and_reminders": True,
            "obsolete_only_via_audit": True,
            "brian_explicit": True,
            "production_apply": False,
            "wave2b_synthetic_canary_only": True,
            "four_reals_protected": True,
        },
    }


def transition_model() -> dict[str, Any]:
    return {
        "states": sorted(ONBOARDING_STATES),
        "terminal": sorted(TERMINAL_STATES),
        "transitions": [
            {"from": "not_started", "to": "in_progress", "action": "start_onboarding"},
            {"from": "not_started", "to": "delayed", "action": "start_delayed / reschedule future"},
            {"from": "delayed", "to": "in_progress", "action": "activate_delayed_starts / start date reached"},
            {"from": "in_progress", "to": "completed", "action": "recompute all required satisfied"},
            {"from": "in_progress", "to": "cancelled", "action": "cancel_onboarding (history kept)"},
            {"from": "delayed", "to": "cancelled", "action": "cancel_onboarding"},
            {"from": "in_progress", "to": "abandoned", "action": "abandon_onboarding / lifecycle employment end"},
            {"from": "delayed", "to": "abandoned", "action": "abandon_onboarding"},
            {"from": "not_started|delayed|in_progress", "to": "reschedule", "action": "reschedule_onboarding_start"},
        ],
        "item_concurrency": "row_version optimistic lock on mark/waive/upload",
        "assignment_concurrency": "version optimistic lock on reschedule/cancel",
        "audit": "onboarding_audit_events for start/mark/waive/upload/complete/cancel/reschedule",
    }
