"""Wave 6 C2 — Learning & Development.

Canonical L&D authority:
  catalog → programs/courses → assignments/enrollment → sessions →
  completion evidence → certification/renewal

Does NOT own employee/employment/org/development plans/competencies/skills/
Talent/JA. Optional bridges only. Wave 4 C3 remains sole development SoT.
Works standalone for mandatory/compliance when Performance/Talent OFF.
Assistant mutations OUT. No second analytics engine.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

PHASE = "learning_development_c2"
CONTRACT_VERSION = "learning_development_c2_v1"
PASS_STAMP = "LEARNING_DEVELOPMENT_FULL_PASS"
COMMERCIAL_MODULE_KEY = "learning"
FLAG = "WATHEFNI_LEARNING_C2"
COMPANIES_FLAG = "WATHEFNI_LEARNING_COMPANIES"
_ON = {"1", "true", "yes", "on"}

ITEM_TYPES = (
    "self_paced",
    "instructor_led",
    "external",
    "program",
    "certification",
    "mandatory_compliance",
)
CATALOG_STATUSES = ("draft", "published", "retired")
ASSIGN_SOURCES = (
    "hr_assigned",
    "manager_assigned",
    "mandatory_policy",
    "employee_requested",
    "development_linked",
    "imported_external",
)
ASSIGN_STATES = ("assigned", "in_progress", "completed", "cancelled", "waived")
REQUEST_STATES = ("requested", "approved", "rejected", "cancelled")
CERT_STATUSES = ("valid", "expired", "revoked")
EVIDENCE_SOURCES = (
    "internal_session",
    "external_provider",
    "uploaded_certificate",
    "integration_callback",
    "manual_authorized",
)

STATUS_LABELS = {
    "assigned": {"en": "Assigned", "ar": "مُسند"},
    "in_progress": {"en": "In progress", "ar": "قيد التنفيذ"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "waived": {"en": "Waived", "ar": "مُستثنى"},
    "overdue": {"en": "Overdue", "ar": "متأخر"},
    "requested": {"en": "Requested", "ar": "مطلوب"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "valid": {"en": "Valid", "ar": "ساري"},
    "expired": {"en": "Expired", "ar": "منتهي"},
    "revoked": {"en": "Revoked", "ar": "ملغى"},
    "expiring": {"en": "Expiring soon", "ar": "ينتهي قريباً"},
    "learning": {"en": "Learning & Development", "ar": "التعلم والتطوير"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def _as_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "does_not_own_employee_employment_org": True,
        "does_not_duplicate_c3_development": True,
        "c3_sole_development_authority": True,
        "completion_does_not_silently_close_development_action": True,
        "completion_does_not_auto_verify_skill_or_competency": True,
        "ja_optional": True,
        "talent_optional": True,
        "works_performance_talent_off": True,
        "works_without_ja": True,
        "no_full_lms_player_in_c2": True,
        "external_provider_supported": True,
        "costs_informational_only": True,
        "no_payroll_side_effects": True,
        "assistant_mutations": False,
        "emits_typed_facts_not_analytics_engine": True,
        "request_not_approval_not_enrollment_not_completion": True,
        "due_date_passed_not_automatic_failure": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {
            "primary_admin": True,
            "separates_catalog_from_operations": True,
        },
        "manager": {
            "scoped_reports_learning": True,
            "assign_or_approve_when_policy_allows": True,
        },
        "employee_app": {
            "my_learning": True,
            "no_hr_admin": True,
        },
        "hr_mobile": {
            "intentionally_operational": True,
            "no_full_catalog_authoring": True,
        },
        "assistant": {"mutations": False, "read_explain_deep_link": True},
        "setup": {"owns_company_policy": True},
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "learning_c2_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if company not in allow:
        try:
            import capability_readiness as _cr

            entitled = _cr.learning_runtime_allowlist_admits(company, allow)
        except Exception:
            entitled = False
        if not entitled:
            return {
                "ok": False,
                "enabled": False,
                "error": "learning_company_not_allowlisted",
                "gate": "company_allowlist",
                "phase": PHASE,
                "company_code": company if allow else None,
            }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_learning_development_c2_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ld_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          employee_requests_enabled boolean NOT NULL DEFAULT true,
          manager_assign_enabled boolean NOT NULL DEFAULT true,
          expiry_warning_days int NOT NULL DEFAULT 30,
          evidence_required_for_completion boolean NOT NULL DEFAULT true,
          ja_applicability_enabled boolean NOT NULL DEFAULT false,
          development_fulfillment_enabled boolean NOT NULL DEFAULT true,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    for ddl in (
        """
        CREATE TABLE IF NOT EXISTS ld_providers (
          provider_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          status text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_learning_items (
          item_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          item_type text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          description_en text NOT NULL DEFAULT '',
          description_ar text NOT NULL DEFAULT '',
          category text NOT NULL DEFAULT '',
          provider_id uuid REFERENCES ld_providers(provider_id),
          status text NOT NULL DEFAULT 'draft',
          delivery_mode text NOT NULL DEFAULT 'self_paced',
          duration_minutes int,
          completion_requirements jsonb NOT NULL DEFAULT '{}'::jsonb,
          optional_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
          effective_version int NOT NULL DEFAULT 1,
          retired_at timestamptz,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code),
          CHECK (item_type IN ('self_paced','instructor_led','external','program','certification','mandatory_compliance')),
          CHECK (status IN ('draft','published','retired'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_item_versions (
          version_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          item_id uuid NOT NULL REFERENCES ld_learning_items(item_id),
          effective_version int NOT NULL,
          snapshot jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (item_id, effective_version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_program_items (
          program_item_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          program_item_id_parent uuid NOT NULL REFERENCES ld_learning_items(item_id),
          child_item_id uuid NOT NULL REFERENCES ld_learning_items(item_id),
          program_version int NOT NULL DEFAULT 1,
          sequence_no int,
          required boolean NOT NULL DEFAULT true,
          UNIQUE (program_item_id_parent, child_item_id, program_version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_offerings (
          offering_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          item_id uuid NOT NULL REFERENCES ld_learning_items(item_id),
          starts_at timestamptz,
          ends_at timestamptz,
          location_or_virtual text NOT NULL DEFAULT '',
          instructor text NOT NULL DEFAULT '',
          capacity int,
          status text NOT NULL DEFAULT 'scheduled',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_assignments (
          assignment_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          item_id uuid NOT NULL REFERENCES ld_learning_items(item_id),
          item_version int NOT NULL,
          program_item_id uuid REFERENCES ld_learning_items(item_id),
          program_version int,
          offering_id uuid REFERENCES ld_offerings(offering_id),
          source text NOT NULL,
          required boolean NOT NULL DEFAULT true,
          status text NOT NULL DEFAULT 'assigned',
          assigned_at date NOT NULL,
          due_date date,
          reason text NOT NULL DEFAULT '',
          actor_phone text,
          policy_id uuid,
          policy_version int,
          obligation_key text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (source IN ('hr_assigned','manager_assigned','mandatory_policy','employee_requested','development_linked','imported_external')),
          CHECK (status IN ('assigned','in_progress','completed','cancelled','waived'))
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ld_assignments_mandatory_idempotent
          ON ld_assignments (company_code, employee_key, obligation_key)
          WHERE obligation_key IS NOT NULL AND status NOT IN ('cancelled')
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_learning_requests (
          request_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          item_id uuid NOT NULL REFERENCES ld_learning_items(item_id),
          status text NOT NULL DEFAULT 'requested',
          requested_at timestamptz NOT NULL DEFAULT now(),
          decided_by_phone text,
          decided_at timestamptz,
          assignment_id uuid REFERENCES ld_assignments(assignment_id),
          reason text NOT NULL DEFAULT '',
          CHECK (status IN ('requested','approved','rejected','cancelled'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_completions (
          completion_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          assignment_id uuid NOT NULL REFERENCES ld_assignments(assignment_id),
          employee_key text NOT NULL,
          item_id uuid NOT NULL,
          item_version int NOT NULL,
          evidence_source text NOT NULL,
          evidence_ref text NOT NULL DEFAULT '',
          evidence_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          completed_at timestamptz NOT NULL DEFAULT now(),
          verified_by_phone text,
          provider_id uuid,
          CHECK (evidence_source IN ('internal_session','external_provider','uploaded_certificate','integration_callback','manual_authorized'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_certifications (
          certification_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          cert_type text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          issuer text NOT NULL DEFAULT '',
          issued_on date NOT NULL,
          expires_on date,
          status text NOT NULL DEFAULT 'valid',
          evidence_ref text NOT NULL DEFAULT '',
          linked_completion_id uuid REFERENCES ld_completions(completion_id),
          renewal_of uuid,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('valid','expired','revoked'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_mandatory_policies (
          policy_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          item_id uuid NOT NULL REFERENCES ld_learning_items(item_id),
          item_version int NOT NULL,
          population_rule jsonb NOT NULL,
          policy_version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          due_offset_days int NOT NULL DEFAULT 30,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code, policy_version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_development_fulfillment_links (
          link_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          development_action_id uuid NOT NULL,
          assignment_id uuid REFERENCES ld_assignments(assignment_id),
          completion_id uuid REFERENCES ld_completions(completion_id),
          item_id uuid,
          link_kind text NOT NULL DEFAULT 'fulfillment_evidence',
          silently_closed_c3 boolean NOT NULL DEFAULT false,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (silently_closed_c3 = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_wave5_fact_outbox (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          emitted_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_audit_events (
          event_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          actor_phone text,
          action text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ld_notification_dedupe (
          dedupe_key text PRIMARY KEY,
          company_code text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ):
        cur.execute(ddl)


def _audit(cur: Any, *, company: str, actor: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO ld_audit_events (event_id, company_code, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, _digits(actor), action, entity_type, entity_id, json.dumps(detail or {})),
    )


def _emit(cur: Any, *, company: str, fact_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
    cur.execute(
        """
        INSERT INTO ld_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, json.dumps(payload)),
    )


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def enable_company_learning(
    cur: Any, *, company_code: str, actor_phone: str, reason: str, **kwargs: Any
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_learning_development_c2_schema(cur)
    cur.execute(
        """
        INSERT INTO ld_company_settings (
          company_code, enabled, employee_requests_enabled, manager_assign_enabled,
          expiry_warning_days, evidence_required_for_completion, ja_applicability_enabled,
          development_fulfillment_enabled, enabled_by_phone, enabled_reason, enabled_at,
          disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          employee_requests_enabled=EXCLUDED.employee_requests_enabled,
          manager_assign_enabled=EXCLUDED.manager_assign_enabled,
          expiry_warning_days=EXCLUDED.expiry_warning_days,
          evidence_required_for_completion=EXCLUDED.evidence_required_for_completion,
          ja_applicability_enabled=EXCLUDED.ja_applicability_enabled,
          development_fulfillment_enabled=EXCLUDED.development_fulfillment_enabled,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(kwargs.get("employee_requests_enabled", True)),
            bool(kwargs.get("manager_assign_enabled", True)),
            int(kwargs.get("expiry_warning_days", 30)),
            bool(kwargs.get("evidence_required_for_completion", True)),
            bool(kwargs.get("ja_applicability_enabled", False)),
            bool(kwargs.get("development_fulfillment_enabled", True)),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company)}


def disable_company_learning(cur: Any, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_learning_development_c2_schema(cur)
    cur.execute(
        """
        UPDATE ld_company_settings
           SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="disable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "history_retained": True}


def module_enabled_for_company(cur: Any, company_code: str) -> bool:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return False
    ensure_learning_development_c2_schema(cur)
    cur.execute("SELECT enabled FROM ld_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "learning_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _settings(cur: Any, company: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM ld_company_settings WHERE company_code=%s", (company,))
    row = _row(cur)
    return row or {}


def upsert_provider(cur: Any, *, company_code: str, actor_phone: str, code: str, name_en: str, name_ar: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    provider_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_providers (provider_id, company_code, code, name_en, name_ar)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, code) DO UPDATE SET name_en=EXCLUDED.name_en, name_ar=EXCLUDED.name_ar
        RETURNING *
        """,
        (provider_id, company, str(code).strip(), name_en.strip(), name_ar.strip()),
    )
    return {"ok": True, "provider": _row(cur)}


def upsert_learning_item(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    item_type: str,
    title_en: str,
    title_ar: str,
    status: str = "draft",
    category: str = "",
    provider_id: str | None = None,
    delivery_mode: str = "self_paced",
    duration_minutes: int | None = None,
    completion_requirements: dict | None = None,
    optional_refs: dict | None = None,
    description_en: str = "",
    description_ar: str = "",
    reason: str = "upsert learning item",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    itype = str(item_type or "").lower()
    st = str(status or "draft").lower()
    if itype not in ITEM_TYPES:
        return {"ok": False, "error": "invalid_item_type", "allowed": list(ITEM_TYPES)}
    if st not in CATALOG_STATUSES:
        return {"ok": False, "error": "invalid_status"}
    if not str(code).strip() or not title_en.strip() or not title_ar.strip():
        return {"ok": False, "error": "code_and_bilingual_titles_required"}
    refs = dict(optional_refs or {})
    # Optional JA / competency / skill refs only — never invent ownership
    for forbidden in ("employee_key", "employment_period_key", "development_plan_id"):
        if forbidden in refs:
            return {"ok": False, "error": "must_not_own_external_truth", "field": forbidden}
    cur.execute("SELECT * FROM ld_learning_items WHERE company_code=%s AND code=%s", (company, str(code).strip()))
    existing = _row(cur)
    snapshot = {
        "title_en": title_en.strip(),
        "title_ar": title_ar.strip(),
        "item_type": itype,
        "completion_requirements": completion_requirements or {},
        "optional_refs": refs,
        "delivery_mode": delivery_mode,
        "duration_minutes": duration_minutes,
    }
    if existing:
        ver = int(existing["effective_version"]) + 1
        cur.execute(
            """
            UPDATE ld_learning_items SET item_type=%s, title_en=%s, title_ar=%s, description_en=%s, description_ar=%s,
              category=%s, provider_id=%s, status=%s, delivery_mode=%s, duration_minutes=%s,
              completion_requirements=%s::jsonb, optional_refs=%s::jsonb, effective_version=%s,
              updated_by_phone=%s, updated_at=now()
             WHERE item_id=%s RETURNING *
            """,
            (
                itype, title_en.strip(), title_ar.strip(), description_en, description_ar, category, provider_id,
                st, delivery_mode, duration_minutes, json.dumps(completion_requirements or {}), json.dumps(refs),
                ver, _digits(actor_phone), str(existing["item_id"]),
            ),
        )
        row = _row(cur)
    else:
        item_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ld_learning_items (
              item_id, company_code, code, item_type, title_en, title_ar, description_en, description_ar,
              category, provider_id, status, delivery_mode, duration_minutes, completion_requirements,
              optional_refs, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s) RETURNING *
            """,
            (
                item_id, company, str(code).strip(), itype, title_en.strip(), title_ar.strip(), description_en,
                description_ar, category, provider_id, st, delivery_mode, duration_minutes,
                json.dumps(completion_requirements or {}), json.dumps(refs), _digits(actor_phone), _digits(actor_phone),
            ),
        )
        row = _row(cur)
    assert row
    cur.execute(
        """
        INSERT INTO ld_item_versions (version_id, company_code, item_id, effective_version, snapshot)
        VALUES (%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (item_id, effective_version) DO NOTHING
        """,
        (str(uuid.uuid4()), company, str(row["item_id"]), int(row["effective_version"]), json.dumps(snapshot)),
    )
    _audit(cur, company=company, actor=actor_phone, action="upsert_item", entity_type="learning_item", entity_id=str(row["item_id"]), detail={"reason": reason})
    return {"ok": True, "item": row, "stable_id": str(row["item_id"])}


def add_program_child(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    program_item_id: str,
    child_item_id: str,
    program_version: int,
    sequence_no: int | None = None,
    required: bool = True,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT item_type FROM ld_learning_items WHERE company_code=%s AND item_id=%s",
        (company, program_item_id),
    )
    prog = _row(cur)
    if not prog or prog["item_type"] != "program":
        return {"ok": False, "error": "program_item_required"}
    pid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_program_items (
          program_item_id, company_code, program_item_id_parent, child_item_id, program_version, sequence_no, required
        ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (pid, company, program_item_id, child_item_id, int(program_version), sequence_no, bool(required)),
    )
    return {"ok": True, "program_item": _row(cur), "pinned_program_version": int(program_version)}


def create_offering(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    item_id: str,
    starts_at: datetime | str | None = None,
    ends_at: datetime | str | None = None,
    location_or_virtual: str = "",
    instructor: str = "",
    capacity: int | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    offering_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_offerings (
          offering_id, company_code, item_id, starts_at, ends_at, location_or_virtual, instructor, capacity, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            offering_id, company, item_id, starts_at, ends_at, location_or_virtual, instructor, capacity, _digits(actor_phone),
        ),
    )
    row = _row(cur)
    return {"ok": True, "offering": row, "catalog_item_not_duplicated": True}


def create_assignment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    item_id: str,
    source: str,
    required: bool = True,
    due_date: date | str | None = None,
    reason: str = "",
    offering_id: str | None = None,
    program_item_id: str | None = None,
    program_version: int | None = None,
    policy_id: str | None = None,
    policy_version: int | None = None,
    obligation_key: str | None = None,
    item_version: int | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    src = str(source or "").lower()
    if src not in ASSIGN_SOURCES:
        return {"ok": False, "error": "invalid_assignment_source", "allowed": list(ASSIGN_SOURCES)}
    cur.execute("SELECT * FROM ld_learning_items WHERE company_code=%s AND item_id=%s", (company, item_id))
    item = _row(cur)
    if not item:
        return {"ok": False, "error": "learning_item_not_found"}
    ver = int(item_version if item_version is not None else item["effective_version"])
    assignment_id = str(uuid.uuid4())
    sp = f"ld_asn_{uuid.uuid4().hex[:12]}"
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(
            """
            INSERT INTO ld_assignments (
              assignment_id, company_code, employee_key, item_id, item_version, program_item_id, program_version,
              offering_id, source, required, status, assigned_at, due_date, reason, actor_phone,
              policy_id, policy_version, obligation_key
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'assigned',%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                assignment_id, company, employee_key, item_id, ver, program_item_id, program_version,
                offering_id, src, bool(required), date.today(), _as_date(due_date), str(reason)[:500],
                _digits(actor_phone), policy_id, policy_version, obligation_key,
            ),
        )
        row = _row(cur)
        cur.execute(f"RELEASE SAVEPOINT {sp}")
    except Exception as exc:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        if obligation_key and (
            "ld_assignments_mandatory_idempotent" in str(exc) or "unique" in str(exc).lower()
        ):
            cur.execute(
                """
                SELECT * FROM ld_assignments
                 WHERE company_code=%s AND employee_key=%s AND obligation_key=%s
                   AND status NOT IN ('cancelled')
                 LIMIT 1
                """,
                (company, employee_key, obligation_key),
            )
            existing = _row(cur)
            return {"ok": True, "assignment": existing, "idempotent_replay": True, "created": False}
        raise
    assert row
    _emit(
        cur,
        company=company,
        fact_type="learning.assignment",
        entity_type="assignment",
        entity_id=assignment_id,
        payload={"employee_key": employee_key, "item_id": item_id, "item_version": ver, "source": src, "required": required},
    )
    _notify_dedupe(cur, company=company, key=f"assign:{assignment_id}")
    return {"ok": True, "assignment": row, "created": True, "idempotent_replay": False}


def assignment_derived_state(assignment: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """Due date passed is derived overdue — not automatic failure."""
    day = today or date.today()
    status = str(assignment.get("status") or "")
    due = _as_date(assignment.get("due_date"))
    overdue = bool(due and due < day and status in {"assigned", "in_progress"})
    return {
        "status": status,
        "overdue": overdue,
        "failed": False,
        "due_date_passed_is_not_failure": True,
    }


def advance_assignment(
    cur: Any, *, company_code: str, actor_phone: str, assignment_id: str, to_status: str, reason: str = ""
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    target = str(to_status or "").lower()
    if target not in ASSIGN_STATES:
        return {"ok": False, "error": "invalid_status"}
    if target == "completed":
        return {"ok": False, "error": "use_record_completion_for_completed"}
    cur.execute(
        "SELECT * FROM ld_assignments WHERE company_code=%s AND assignment_id=%s",
        (company, assignment_id),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "assignment_not_found"}
    cur.execute(
        """
        UPDATE ld_assignments SET status=%s, updated_at=now(), reason=CASE WHEN %s='' THEN reason ELSE %s END
         WHERE assignment_id=%s RETURNING *
        """,
        (target, str(reason), str(reason)[:500], assignment_id),
    )
    return {"ok": True, "assignment": _row(cur)}


def create_learning_request(
    cur: Any, *, company_code: str, employee_key: str, item_id: str, reason: str = ""
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    if not settings.get("employee_requests_enabled", True):
        return {"ok": False, "error": "employee_requests_disabled"}
    request_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_learning_requests (request_id, company_code, employee_key, item_id, reason)
        VALUES (%s,%s,%s,%s,%s) RETURNING *
        """,
        (request_id, company, employee_key, item_id, str(reason)[:500]),
    )
    row = _row(cur)
    return {
        "ok": True,
        "request": row,
        "is_approval": False,
        "is_enrollment": False,
        "is_completion": False,
    }


def decide_learning_request(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    request_id: str,
    approve: bool,
    reason: str = "",
) -> dict[str, Any]:
    """Uses shared request spine semantics — approval ≠ enrollment ≠ completion."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM ld_learning_requests WHERE company_code=%s AND request_id=%s",
        (company, request_id),
    )
    req = _row(cur)
    if not req:
        return {"ok": False, "error": "request_not_found"}
    if req["status"] != "requested":
        return {"ok": False, "error": "request_not_pending", "status": req["status"]}
    if not approve:
        cur.execute(
            """
            UPDATE ld_learning_requests SET status='rejected', decided_by_phone=%s, decided_at=now(), reason=%s
             WHERE request_id=%s RETURNING *
            """,
            (_digits(actor_phone), str(reason)[:500], request_id),
        )
        return {"ok": True, "request": _row(cur), "approved": False, "enrollment_created": False, "completion_created": False}
    # Approval may create assignment (enrollment) — still not completion
    assigned = create_assignment(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        employee_key=str(req["employee_key"]),
        item_id=str(req["item_id"]),
        source="employee_requested",
        reason=f"approved request {request_id}",
    )
    if not assigned.get("ok"):
        return assigned
    cur.execute(
        """
        UPDATE ld_learning_requests
           SET status='approved', decided_by_phone=%s, decided_at=now(), assignment_id=%s, reason=%s
         WHERE request_id=%s RETURNING *
        """,
        (_digits(actor_phone), assigned["assignment"]["assignment_id"], str(reason)[:500], request_id),
    )
    return {
        "ok": True,
        "request": _row(cur),
        "approved": True,
        "enrollment_created": True,
        "completion_created": False,
        "request_not_approval_not_enrollment_not_completion": True,
    }


def record_completion(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    assignment_id: str,
    evidence_source: str,
    evidence_ref: str = "",
    evidence_payload: dict | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    src = str(evidence_source or "").lower()
    if src not in EVIDENCE_SOURCES:
        return {"ok": False, "error": "invalid_evidence_source", "allowed": list(EVIDENCE_SOURCES)}
    settings = _settings(cur, company)
    if settings.get("evidence_required_for_completion", True) and not str(evidence_ref).strip() and not evidence_payload:
        return {"ok": False, "error": "evidence_required"}
    cur.execute(
        "SELECT * FROM ld_assignments WHERE company_code=%s AND assignment_id=%s",
        (company, assignment_id),
    )
    asn = _row(cur)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    completion_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_completions (
          completion_id, company_code, assignment_id, employee_key, item_id, item_version,
          evidence_source, evidence_ref, evidence_payload, verified_by_phone, provider_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING *
        """,
        (
            completion_id, company, assignment_id, asn["employee_key"], asn["item_id"], asn["item_version"],
            src, evidence_ref, json.dumps(evidence_payload or {}), _digits(actor_phone), provider_id,
        ),
    )
    completion = _row(cur)
    cur.execute(
        "UPDATE ld_assignments SET status='completed', updated_at=now() WHERE assignment_id=%s RETURNING *",
        (assignment_id,),
    )
    _emit(
        cur,
        company=company,
        fact_type="learning.completion",
        entity_type="completion",
        entity_id=completion_id,
        payload={"assignment_id": assignment_id, "evidence_source": src, "item_version": asn["item_version"]},
    )
    return {
        "ok": True,
        "completion": completion,
        "frontend_checkbox_not_authority": True,
        "skill_auto_verified": False,
        "competency_auto_verified": False,
    }


def issue_certification(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    cert_type: str,
    title_en: str,
    title_ar: str,
    issued_on: date | str,
    expires_on: date | str | None = None,
    issuer: str = "",
    evidence_ref: str = "",
    linked_completion_id: str | None = None,
    renewal_of: str | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    certification_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_certifications (
          certification_id, company_code, employee_key, cert_type, title_en, title_ar, issuer,
          issued_on, expires_on, evidence_ref, linked_completion_id, renewal_of, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            certification_id, company, employee_key, cert_type, title_en, title_ar, issuer,
            _as_date(issued_on), _as_date(expires_on), evidence_ref, linked_completion_id, renewal_of,
            _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _emit(
        cur,
        company=company,
        fact_type="learning.certification",
        entity_type="certification",
        entity_id=certification_id,
        payload={"cert_type": cert_type, "expires_on": str(expires_on) if expires_on else None},
    )
    return {
        "ok": True,
        "certification": row,
        "course_completion_does_not_imply_certification": linked_completion_id is None,
    }


def certification_derived_status(
    certification: dict[str, Any], *, today: date | None = None, warning_days: int = 30
) -> dict[str, Any]:
    day = today or date.today()
    stored = str(certification.get("status") or "valid")
    if stored == "revoked":
        return {"status": "revoked", "expiring": False, "derived": False}
    expires = _as_date(certification.get("expires_on"))
    if expires and expires < day:
        return {"status": "expired", "expiring": False, "derived": True}
    if expires and expires <= day + timedelta(days=int(warning_days)):
        return {"status": "valid", "expiring": True, "derived": True, "expiring_soon_not_stored_truth": True}
    return {"status": "valid", "expiring": False, "derived": False}


def link_development_fulfillment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    development_action_id: str,
    assignment_id: str | None = None,
    completion_id: str | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    """Attach L&D evidence to C3 action — never silently close/rewrite C3."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    if not settings.get("development_fulfillment_enabled", True):
        return {"ok": False, "error": "development_fulfillment_disabled"}
    # Read C3 action if table exists — do not mutate status
    c3_status = None
    cur.execute("SELECT to_regclass('perf_development_actions') AS t")
    if dict(cur.fetchone()).get("t"):
        cur.execute(
            "SELECT action_id, status FROM perf_development_actions WHERE company_code=%s AND action_id=%s",
            (company, development_action_id),
        )
        action = cur.fetchone()
        if action:
            c3_status = dict(action).get("status")
    link_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_development_fulfillment_links (
          link_id, company_code, development_action_id, assignment_id, completion_id, item_id,
          silently_closed_c3, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,false,%s) RETURNING *
        """,
        (link_id, company, development_action_id, assignment_id, completion_id, item_id, _digits(actor_phone)),
    )
    row = _row(cur)
    return {
        "ok": True,
        "link": row,
        "c3_action_status_unchanged": c3_status,
        "silently_closed_c3": False,
        "c3_remains_sole_development_authority": True,
    }


def create_mandatory_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    title_en: str,
    title_ar: str,
    item_id: str,
    population_rule: dict[str, Any],
    due_offset_days: int = 30,
    policy_version: int = 1,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT effective_version FROM ld_learning_items WHERE company_code=%s AND item_id=%s", (company, item_id))
    item = _row(cur)
    if not item:
        return {"ok": False, "error": "learning_item_not_found"}
    policy_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ld_mandatory_policies (
          policy_id, company_code, code, title_en, title_ar, item_id, item_version,
          population_rule, policy_version, due_offset_days, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING *
        """,
        (
            policy_id, company, code, title_en, title_ar, item_id, int(item["effective_version"]),
            json.dumps(population_rule), int(policy_version), int(due_offset_days), _digits(actor_phone),
        ),
    )
    return {"ok": True, "policy": _row(cur)}


def generate_mandatory_assignments(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    policy_id: str,
    employee_keys: list[str],
) -> dict[str, Any]:
    """Idempotent generation for a pinned policy version + population snapshot."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM ld_mandatory_policies WHERE company_code=%s AND policy_id=%s",
        (company, policy_id),
    )
    policy = _row(cur)
    if not policy:
        return {"ok": False, "error": "policy_not_found"}
    created = []
    replayed = []
    for employee_key in employee_keys:
        obligation = f"{policy['code']}:v{policy['policy_version']}:{policy['item_id']}"
        result = create_assignment(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            employee_key=employee_key,
            item_id=str(policy["item_id"]),
            item_version=int(policy["item_version"]),
            source="mandatory_policy",
            required=True,
            due_date=date.today() + timedelta(days=int(policy["due_offset_days"])),
            reason=f"mandatory {policy['code']} v{policy['policy_version']}",
            policy_id=str(policy["policy_id"]),
            policy_version=int(policy["policy_version"]),
            obligation_key=obligation,
        )
        if result.get("idempotent_replay"):
            replayed.append(employee_key)
        elif result.get("ok"):
            created.append(employee_key)
            _emit(
                cur,
                company=company,
                fact_type="learning.mandatory_compliance",
                entity_type="assignment",
                entity_id=str(result["assignment"]["assignment_id"]),
                payload={"policy_id": policy_id, "policy_version": policy["policy_version"], "employee_key": employee_key},
            )
    return {
        "ok": True,
        "created": created,
        "replayed": replayed,
        "policy_version_pinned": int(policy["policy_version"]),
        "item_version_pinned": int(policy["item_version"]),
    }


def _notify_dedupe(cur: Any, *, company: str, key: str) -> dict[str, Any]:
    dedupe_key = f"{company}:{key}"
    sp = f"ld_nd_{uuid.uuid4().hex[:12]}"
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(
            "INSERT INTO ld_notification_dedupe (dedupe_key, company_code) VALUES (%s,%s)",
            (dedupe_key, company),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": True, "deduped": False}
    except Exception:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": False, "deduped": True}


def employee_learning_view(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "learning_disabled_for_company"}
    cur.execute(
        "SELECT * FROM ld_assignments WHERE company_code=%s AND employee_key=%s ORDER BY assigned_at DESC",
        (company, employee_key),
    )
    assignments = [dict(r) for r in cur.fetchall()]
    for asn in assignments:
        asn["derived"] = assignment_derived_state(asn)
    cur.execute(
        "SELECT * FROM ld_certifications WHERE company_code=%s AND employee_key=%s ORDER BY issued_on DESC",
        (company, employee_key),
    )
    settings = _settings(cur, company)
    certs = []
    for row in cur.fetchall():
        cert = dict(row)
        cert["derived"] = certification_derived_status(cert, warning_days=int(settings.get("expiry_warning_days") or 30))
        certs.append(cert)
    return {
        "ok": True,
        "employee_key": employee_key,
        "assignments": assignments,
        "certifications": certs,
        "hr_admin_exposed": False,
    }


def manager_learning_view(
    cur: Any, *, company_code: str, manager_scope_employee_keys: list[str]
) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "learning_disabled_for_company"}
    if not manager_scope_employee_keys:
        return {"ok": True, "assignments": [], "scope_empty": True}
    cur.execute(
        """
        SELECT * FROM ld_assignments
         WHERE company_code=%s AND employee_key = ANY(%s)
         ORDER BY assigned_at DESC
        """,
        (company, list(manager_scope_employee_keys)),
    )
    rows = [dict(r) for r in cur.fetchall()]
    for asn in rows:
        asn["derived"] = assignment_derived_state(asn)
    return {"ok": True, "assignments": rows, "uses_canonical_manager_scope": True}


def assistant_query_learning(
    cur: Any, *, company_code: str, actor: str, question_kind: str, employee_key: str | None = None
) -> dict[str, Any]:
    """Read/explain only."""
    _ = actor
    if question_kind == "mandatory_remaining" and employee_key:
        view = employee_learning_view(cur, company_code=company_code, employee_key=employee_key)
        remaining = [
            a for a in view.get("assignments") or []
            if a.get("required") and a.get("status") in {"assigned", "in_progress"}
        ]
        return {"ok": True, "mutations": False, "remaining": remaining}
    if question_kind == "invent_completion":
        return {"ok": False, "error": "mutation_forbidden", "mutations": False}
    return {"ok": False, "error": "unsupported_or_forbidden", "mutations": False}
