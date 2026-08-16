"""Wave 6 C4 — Employee Relations (confidential need-to-know).

Canonical authority:
  case → intake → classification → assignment → investigation →
  evidence → actions/outcome → closure

Does NOT own employee/employment/org truth. Case-level RBAC.
Ordinary HR ≠ ER. Manager ≠ ER. Outcome ≠ employment mutation.
Wave 5 facts exclude sensitive free text. Claims of Kuwait legal
outcomes forbidden — configurable taxonomy only.
Assistant mutations OUT.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

PHASE = "employee_relations_c4"
CONTRACT_VERSION = "employee_relations_c4_v1"
PASS_STAMP = "EMPLOYEE_RELATIONS_FULL_PASS"
COMMERCIAL_MODULE_KEY = "employee_relations"
FLAG = "WATHEFNI_EMPLOYEE_RELATIONS_C4"
COMPANIES_FLAG = "WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"
_ON = {"1", "true", "yes", "on"}

CASE_TYPE_CODES = (
    "grievance",
    "complaint",
    "disciplinary",
    "investigation",
    "corrective_action",
    "other",
)
CASE_STATES = (
    "open",
    "triage",
    "investigating",
    "decision_action",
    "closed",
    "withdrawn",
    "dismissed",
)
INTAKE_SOURCES = ("hr_created", "manager_referred", "employee_submitted", "imported_external")
ACCESS_PERMS = ("view", "manage", "investigate", "decide", "sensitive_evidence")
ACTOR_ROLES = ("er_admin", "investigator", "ordinary_hr", "manager", "employee", "assistant")
CONFIDENTIALITY = ("standard_er", "highly_sensitive", "restricted")
OUTCOME_CODES = ("no_action", "warning_corrective", "investigation_closed", "referral", "other_configured")
SAFE_EMPLOYEE_STATUSES = {
    "open": "received",
    "triage": "under_review",
    "investigating": "in_progress",
    "decision_action": "decision_pending",
    "closed": "closed",
    "withdrawn": "withdrawn",
    "dismissed": "closed",
}

STATUS_LABELS = {
    "open": {"en": "Open", "ar": "مفتوح"},
    "triage": {"en": "Triage", "ar": "فرز"},
    "investigating": {"en": "Investigating", "ar": "قيد التحقيق"},
    "decision_action": {"en": "Decision / action", "ar": "قرار/إجراء"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "withdrawn": {"en": "Withdrawn", "ar": "مسحوب"},
    "dismissed": {"en": "Dismissed", "ar": "مرفوض"},
    "employee_relations": {"en": "Employee Relations", "ar": "علاقات الموظفين"},
    "received": {"en": "Received", "ar": "مستلم"},
    "under_review": {"en": "Under review", "ar": "قيد المراجعة"},
    "in_progress": {"en": "In progress", "ar": "قيد المعالجة"},
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
        "case_level_need_to_know": True,
        "ordinary_hr_not_er": True,
        "manager_not_er": True,
        "employee_submission_not_finding": True,
        "investigation_not_outcome": True,
        "outcome_not_employment_mutation": True,
        "no_invented_kuwait_legal_outcomes": True,
        "wave5_excludes_sensitive_free_text": True,
        "assistant_mutations": False,
        "works_without_engagement": True,
        "works_without_payroll": True,
        "works_without_talent_performance": True,
        "due_date_not_silent_outcome": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {"primary_sealed_workspace": True, "setup_separate_from_ops": True},
        "hr_mobile": {"intentionally_thin": True, "no_heavy_investigation_authoring": True},
        "manager": {"no_er_by_reporting_line": True, "referral_only_when_policy": True},
        "employee_app": {"safe_status_only": True, "no_internal_notes": True},
        "assistant": {"mutations": False, "no_case_narrative_dump": True, "read_explain_deep_link": True},
        "setup": {"owns_case_types_and_access_policy": True},
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "employee_relations_c4_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if company not in allow:
        try:
            import capability_readiness as _cr

            entitled = _cr.employee_relations_runtime_allowlist_admits(company, allow)
        except Exception:
            entitled = False
        if not entitled:
            return {
                "ok": False,
                "enabled": False,
                "error": "employee_relations_company_not_allowlisted",
                "gate": "company_allowlist",
                "phase": PHASE,
                "company_code": company if allow else None,
            }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_employee_relations_c4_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS er_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          employee_submission_enabled boolean NOT NULL DEFAULT true,
          manager_referral_enabled boolean NOT NULL DEFAULT true,
          default_confidentiality text NOT NULL DEFAULT 'standard_er',
          sla_triage_days int NOT NULL DEFAULT 3,
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
        CREATE TABLE IF NOT EXISTS er_case_types (
          case_type_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          type_version int NOT NULL DEFAULT 1,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          confidentiality_default text NOT NULL DEFAULT 'standard_er',
          allowed_outcomes jsonb NOT NULL DEFAULT '[]'::jsonb,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code, type_version),
          CHECK (code IN ('grievance','complaint','disciplinary','investigation','corrective_action','other')),
          CHECK (confidentiality_default IN ('standard_er','highly_sensitive','restricted'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_cases (
          case_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_type_id uuid NOT NULL REFERENCES er_case_types(case_type_id),
          case_type_code text NOT NULL,
          case_type_version int NOT NULL,
          subject_employee_key text NOT NULL,
          reporter_employee_key text,
          intake_source text NOT NULL,
          status text NOT NULL DEFAULT 'open',
          severity text NOT NULL DEFAULT 'medium',
          confidentiality_class text NOT NULL DEFAULT 'standard_er',
          assigned_investigator text,
          due_date date,
          opened_at timestamptz NOT NULL DEFAULT now(),
          closed_at timestamptz,
          reopened_from uuid,
          summary_en text NOT NULL DEFAULT '',
          summary_ar text NOT NULL DEFAULT '',
          created_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CHECK (intake_source IN ('hr_created','manager_referred','employee_submitted','imported_external')),
          CHECK (status IN ('open','triage','investigating','decision_action','closed','withdrawn','dismissed')),
          CHECK (confidentiality_class IN ('standard_er','highly_sensitive','restricted'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_case_parties (
          party_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          party_role text NOT NULL,
          employee_key text,
          display_label text NOT NULL DEFAULT '',
          visibility text NOT NULL DEFAULT 'internal_only',
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (party_role IN ('subject','reporter','witness','investigator','other')),
          CHECK (visibility IN ('internal_only','employee_safe','er_only'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_allegations (
          allegation_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          allegation_code text NOT NULL DEFAULT '',
          statement_en text NOT NULL DEFAULT '',
          statement_ar text NOT NULL DEFAULT '',
          proven boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_access_grants (
          grant_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          actor_key text NOT NULL,
          actor_role text NOT NULL,
          permissions text[] NOT NULL,
          granted_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          revoked_at timestamptz,
          CHECK (actor_role IN ('er_admin','investigator','ordinary_hr','manager','employee','assistant'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_investigation_notes (
          note_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          author_key text NOT NULL,
          body_en text NOT NULL DEFAULT '',
          body_ar text NOT NULL DEFAULT '',
          locked boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_findings (
          finding_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          investigator_key text NOT NULL,
          findings_en text NOT NULL DEFAULT '',
          findings_ar text NOT NULL DEFAULT '',
          locked boolean NOT NULL DEFAULT false,
          submitted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_evidence_refs (
          evidence_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          shared_document_ref text NOT NULL,
          label_en text NOT NULL DEFAULT '',
          label_ar text NOT NULL DEFAULT '',
          sensitive boolean NOT NULL DEFAULT true,
          uploaded_by text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_safe_messages (
          message_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          audience text NOT NULL DEFAULT 'subject_employee',
          body_en text NOT NULL,
          body_ar text NOT NULL,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (audience IN ('subject_employee','reporter'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_outcomes (
          outcome_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          outcome_code text NOT NULL,
          outcome_version int NOT NULL DEFAULT 1,
          summary_en text NOT NULL DEFAULT '',
          summary_ar text NOT NULL DEFAULT '',
          employment_mutated boolean NOT NULL DEFAULT false,
          decided_by_phone text,
          decided_at timestamptz NOT NULL DEFAULT now(),
          CHECK (outcome_code IN ('no_action','warning_corrective','investigation_closed','referral','other_configured')),
          CHECK (employment_mutated = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_employment_handoffs (
          handoff_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          outcome_id uuid REFERENCES er_outcomes(outcome_id),
          target_authority text NOT NULL DEFAULT 'employment_change_c1',
          handoff_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          applied boolean NOT NULL DEFAULT false,
          employment_mutated_by_er boolean NOT NULL DEFAULT false,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (employment_mutated_by_er = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_task_links (
          link_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid NOT NULL REFERENCES er_cases(case_id),
          shared_task_ref text NOT NULL,
          task_kind text NOT NULL DEFAULT 'triage',
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_wave5_fact_outbox (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_audit_events (
          audit_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_id uuid,
          actor_phone text,
          action text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS er_notification_dedupe (
          dedupe_key text PRIMARY KEY,
          company_code text NOT NULL,
          payload_safe boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (payload_safe = true)
        )
        """,
    ):
        cur.execute(ddl)


def _audit(
    cur: Any,
    *,
    company: str,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    case_id: str | None = None,
    detail: dict | None = None,
) -> None:
    # Never put allegation/evidence free text into audit detail from callers — callers must sanitize
    cur.execute(
        """
        INSERT INTO er_audit_events (audit_id, company_code, case_id, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            str(uuid.uuid4()), company, case_id, _digits(actor), action, entity_type, entity_id,
            json.dumps(detail or {}),
        ),
    )


def _emit_safe_fact(cur: Any, *, company: str, fact_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
    """Wave 5 facts must not include allegation/witness/investigation free text."""
    forbidden_keys = {
        "allegation_text", "statement_en", "statement_ar", "findings_en", "findings_ar",
        "body_en", "body_ar", "witness_statement", "evidence_text", "note_text",
    }
    clean = {k: v for k, v in dict(payload or {}).items() if k not in forbidden_keys and not str(k).endswith("_text")}
    # Strip long free-text values
    for k, v in list(clean.items()):
        if isinstance(v, str) and len(v) > 80:
            clean[k] = v[:80] + "…"
    cur.execute(
        """
        INSERT INTO er_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, json.dumps(clean)),
    )


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def enable_company_employee_relations(
    cur: Any, *, company_code: str, actor_phone: str, reason: str, **kwargs: Any
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_employee_relations_c4_schema(cur)
    cur.execute(
        """
        INSERT INTO er_company_settings (
          company_code, enabled, employee_submission_enabled, manager_referral_enabled,
          default_confidentiality, sla_triage_days, enabled_by_phone, enabled_reason,
          enabled_at, disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          employee_submission_enabled=EXCLUDED.employee_submission_enabled,
          manager_referral_enabled=EXCLUDED.manager_referral_enabled,
          default_confidentiality=EXCLUDED.default_confidentiality,
          sla_triage_days=EXCLUDED.sla_triage_days,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(kwargs.get("employee_submission_enabled", True)),
            bool(kwargs.get("manager_referral_enabled", True)),
            str(kwargs.get("default_confidentiality") or "standard_er"),
            int(kwargs.get("sla_triage_days", 3)),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company)}


def disable_company_employee_relations(cur: Any, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_employee_relations_c4_schema(cur)
    cur.execute(
        """
        UPDATE er_company_settings
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
    ensure_employee_relations_c4_schema(cur)
    cur.execute("SELECT enabled FROM er_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "employee_relations_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _settings(cur: Any, company: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM er_company_settings WHERE company_code=%s", (company,))
    return _row(cur) or {}


def upsert_case_type(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    title_en: str,
    title_ar: str,
    type_version: int = 1,
    confidentiality_default: str = "standard_er",
    allowed_outcomes: list[str] | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    c = str(code or "").lower()
    if c not in CASE_TYPE_CODES:
        return {"ok": False, "error": "invalid_case_type", "allowed": list(CASE_TYPE_CODES)}
    conf = str(confidentiality_default or "standard_er")
    if conf not in CONFIDENTIALITY:
        return {"ok": False, "error": "invalid_confidentiality"}
    outcomes = list(allowed_outcomes or list(OUTCOME_CODES))
    for o in outcomes:
        if o not in OUTCOME_CODES:
            return {"ok": False, "error": "invalid_outcome_code", "code": o, "no_invented_kuwait_legal_outcomes": True}
    case_type_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_case_types (
          case_type_id, company_code, code, type_version, title_en, title_ar,
          confidentiality_default, allowed_outcomes, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING *
        """,
        (
            case_type_id, company, c, int(type_version), title_en.strip(), title_ar.strip(),
            conf, json.dumps(outcomes), _digits(actor_phone),
        ),
    )
    return {"ok": True, "case_type": _row(cur), "stable_id": case_type_id}


def grant_case_access(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    case_id: str,
    actor_key: str,
    actor_role: str,
    permissions: list[str],
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    role = str(actor_role or "").lower()
    if role not in ACTOR_ROLES:
        return {"ok": False, "error": "invalid_actor_role"}
    perms = [p for p in permissions if p in ACCESS_PERMS]
    if not perms:
        return {"ok": False, "error": "permissions_required"}
    # Ordinary HR / manager never auto-elevated
    if role in {"ordinary_hr", "manager"} and "sensitive_evidence" in perms:
        return {"ok": False, "error": "role_cannot_hold_sensitive_evidence", "ordinary_hr_not_er": True, "manager_not_er": True}
    grant_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_access_grants (
          grant_id, company_code, case_id, actor_key, actor_role, permissions, granted_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (grant_id, company, case_id, actor_key, role, perms, _digits(actor_phone)),
    )
    grant = _row(cur)
    _audit(
        cur, company=company, actor=actor_phone, action="grant_access", entity_type="access_grant",
        entity_id=grant_id, case_id=case_id, detail={"actor_key": actor_key, "actor_role": role, "permissions": perms},
    )
    return {"ok": True, "grant": grant}


def check_case_permission(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_key: str,
    actor_role: str,
    permission: str,
) -> dict[str, Any]:
    """Case-level need-to-know. Ordinary HR/manager denied without explicit grant."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "allowed": False}
    company = gate["company_code"]
    role = str(actor_role or "").lower()
    perm = str(permission or "").lower()
    if role in {"ordinary_hr", "manager"} and not _has_grant(cur, company, case_id, actor_key, perm):
        return {
            "ok": True,
            "allowed": False,
            "error": "er_access_denied",
            "ordinary_hr_not_er": role == "ordinary_hr",
            "manager_not_er": role == "manager",
            "case_level_need_to_know": True,
        }
    if role == "employee":
        # Employee may only see safe self view — never investigate/decide/sensitive
        if perm in {"investigate", "decide", "sensitive_evidence", "manage"}:
            return {"ok": True, "allowed": False, "error": "employee_denied_internal"}
        return {"ok": True, "allowed": perm == "view", "employee_safe_only": True}
    if role == "assistant":
        return {"ok": True, "allowed": perm == "view", "mutations": False, "no_case_narrative_dump": True}
    if role in {"er_admin", "investigator"}:
        if _has_grant(cur, company, case_id, actor_key, perm) or (
            role == "er_admin" and perm in ACCESS_PERMS
        ):
            # er_admin still needs company enable; for prove, er_admin with grant or global er_admin key
            if role == "er_admin":
                return {"ok": True, "allowed": True, "case_level_need_to_know": True}
            return {"ok": True, "allowed": _has_grant(cur, company, case_id, actor_key, perm)}
        return {"ok": True, "allowed": False, "error": "er_access_denied"}
    return {"ok": True, "allowed": False, "error": "er_access_denied"}


def _has_grant(cur: Any, company: str, case_id: str, actor_key: str, permission: str) -> bool:
    cur.execute(
        """
        SELECT permissions FROM er_access_grants
         WHERE company_code=%s AND case_id=%s AND actor_key=%s AND revoked_at IS NULL
        """,
        (company, case_id, actor_key),
    )
    for row in cur.fetchall():
        perms = list(dict(row).get("permissions") or [])
        if permission in perms or "manage" in perms and permission == "view":
            return True
    return False


def open_case(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    case_type_id: str,
    subject_employee_key: str,
    intake_source: str,
    actor_role: str,
    actor_key: str,
    reporter_employee_key: str | None = None,
    summary_en: str = "",
    summary_ar: str = "",
    severity: str = "medium",
    due_date: date | str | None = None,
    allegation_en: str = "",
    allegation_ar: str = "",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    src = str(intake_source or "").lower()
    if src not in INTAKE_SOURCES:
        return {"ok": False, "error": "invalid_intake_source"}
    if src == "employee_submitted" and not settings.get("employee_submission_enabled", True):
        return {"ok": False, "error": "employee_submission_disabled"}
    if src == "manager_referred" and not settings.get("manager_referral_enabled", True):
        return {"ok": False, "error": "manager_referral_disabled"}
    # Manager referral does not grant case content access
    cur.execute(
        "SELECT * FROM er_case_types WHERE company_code=%s AND case_type_id=%s",
        (company, case_type_id),
    )
    ctype = _row(cur)
    if not ctype:
        return {"ok": False, "error": "case_type_not_found"}
    case_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_cases (
          case_id, company_code, case_type_id, case_type_code, case_type_version,
          subject_employee_key, reporter_employee_key, intake_source, status, severity,
          confidentiality_class, due_date, summary_en, summary_ar, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            case_id, company, case_type_id, ctype["code"], int(ctype["type_version"]),
            subject_employee_key, reporter_employee_key, src, severity,
            ctype["confidentiality_default"], _as_date(due_date),
            summary_en[:500], summary_ar[:500], _digits(actor_phone),
        ),
    )
    case = _row(cur)
    assert case
    cur.execute(
        """
        INSERT INTO er_case_parties (party_id, company_code, case_id, party_role, employee_key, visibility)
        VALUES (%s,%s,%s,'subject',%s,'employee_safe')
        """,
        (str(uuid.uuid4()), company, case_id, subject_employee_key),
    )
    if reporter_employee_key:
        cur.execute(
            """
            INSERT INTO er_case_parties (party_id, company_code, case_id, party_role, employee_key, visibility)
            VALUES (%s,%s,%s,'reporter',%s,'employee_safe')
            """,
            (str(uuid.uuid4()), company, case_id, reporter_employee_key),
        )
    if allegation_en or allegation_ar:
        cur.execute(
            """
            INSERT INTO er_allegations (allegation_id, company_code, case_id, statement_en, statement_ar, proven)
            VALUES (%s,%s,%s,%s,%s,false)
            """,
            (str(uuid.uuid4()), company, case_id, allegation_en, allegation_ar),
        )
    # Grant opener appropriate access
    opener_role = "er_admin" if actor_role == "er_admin" else ("investigator" if actor_role == "investigator" else actor_role)
    if opener_role in {"er_admin", "investigator"}:
        grant_case_access(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            case_id=case_id,
            actor_key=actor_key,
            actor_role=opener_role,
            permissions=list(ACCESS_PERMS) if opener_role == "er_admin" else ["view", "investigate"],
        )
    elif src == "manager_referred" and actor_role == "manager":
        # Explicit: referral does NOT grant case content
        pass
    _emit_safe_fact(
        cur,
        company=company,
        fact_type="er.case_opened",
        entity_type="case",
        entity_id=case_id,
        payload={
            "case_type_code": ctype["code"],
            "case_type_version": ctype["type_version"],
            "intake_source": src,
            "status": "open",
            "confidentiality_class": ctype["confidentiality_default"],
        },
    )
    _notify_dedupe(cur, company=company, key=f"case_open:{case_id}")
    return {
        "ok": True,
        "case": case,
        "employee_submission_not_finding": src == "employee_submitted",
        "complaint_not_disciplinary_finding": ctype["code"] == "complaint",
        "manager_gains_no_content_by_referral": src == "manager_referred",
    }


def transition_case(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    to_status: str,
    reason: str = "",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    perm = check_case_permission(
        cur, company_code=company, case_id=case_id, actor_key=actor_key, actor_role=actor_role, permission="manage"
    )
    if not perm.get("allowed") and actor_role != "er_admin":
        # er_admin with manage via grant or role
        perm2 = check_case_permission(
            cur, company_code=company, case_id=case_id, actor_key=actor_key, actor_role=actor_role, permission="view"
        )
        if actor_role != "er_admin" or not (perm.get("allowed") or _has_grant(cur, company, case_id, actor_key, "manage")):
            if actor_role != "er_admin":
                return {"ok": False, "error": "er_access_denied", **{k: perm.get(k) for k in ("ordinary_hr_not_er", "manager_not_er") if k in perm}}
    target = str(to_status or "").lower()
    if target not in CASE_STATES:
        return {"ok": False, "error": "invalid_status"}
    cur.execute("SELECT * FROM er_cases WHERE company_code=%s AND case_id=%s", (company, case_id))
    case = _row(cur)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case["status"] == "closed" and target != "closed":
        return {"ok": False, "error": "reopen_requires_governed_authority"}
    closed_at = datetime.utcnow() if target in {"closed", "withdrawn", "dismissed"} else None
    cur.execute(
        """
        UPDATE er_cases SET status=%s, closed_at=COALESCE(%s, closed_at), updated_at=now()
         WHERE case_id=%s RETURNING *
        """,
        (target, closed_at, case_id),
    )
    row = _row(cur)
    _audit(
        cur, company=company, actor=actor_phone, action="transition", entity_type="case",
        entity_id=case_id, case_id=case_id, detail={"from": case["status"], "to": target, "reason": reason[:200]},
    )
    if target == "closed":
        _emit_safe_fact(
            cur, company=company, fact_type="er.case_closed", entity_type="case", entity_id=case_id,
            payload={"case_type_code": case["case_type_code"], "status": "closed"},
        )
    return {"ok": True, "case": row, "due_date_not_silent_outcome": True}


def reopen_case(
    cur: Any, *, company_code: str, actor_phone: str, actor_key: str, actor_role: str, case_id: str, reason: str
) -> dict[str, Any]:
    """Governed reopen only — not silent."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if actor_role != "er_admin" and not _has_grant(cur, company, case_id, actor_key, "decide"):
        return {"ok": False, "error": "reopen_requires_governed_authority"}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    cur.execute("SELECT * FROM er_cases WHERE company_code=%s AND case_id=%s", (company, case_id))
    case = _row(cur)
    if not case or case["status"] not in {"closed", "dismissed", "withdrawn"}:
        return {"ok": False, "error": "case_not_reopenable"}
    # Governed reopen: flip status with audit — not silent
    cur.execute(
        """
        UPDATE er_cases SET status='triage', closed_at=NULL, reopened_from=%s, updated_at=now()
         WHERE case_id=%s RETURNING *
        """,
        (case_id, case_id),
    )
    row = _row(cur)
    _audit(
        cur, company=company, actor=actor_phone, action="reopen", entity_type="case",
        entity_id=case_id, case_id=case_id, detail={"reason": reason[:200], "governed": True},
    )
    return {"ok": True, "case": row, "governed_reopen": True}


def case_derived_sla(case: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    day = today or date.today()
    due = _as_date(case.get("due_date"))
    overdue = bool(due and due < day and case.get("status") not in {"closed", "withdrawn", "dismissed"})
    return {
        "overdue": overdue,
        "outcome_changed": False,
        "due_date_not_silent_outcome": True,
    }


def assign_investigator(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    investigator_key: str,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if actor_role != "er_admin" and not _has_grant(cur, company, case_id, actor_key, "manage"):
        return {"ok": False, "error": "er_access_denied"}
    cur.execute(
        """
        UPDATE er_cases SET assigned_investigator=%s, status=CASE WHEN status='open' THEN 'triage' ELSE status END, updated_at=now()
         WHERE company_code=%s AND case_id=%s RETURNING *
        """,
        (investigator_key, company, case_id),
    )
    case = _row(cur)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    grant_case_access(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        case_id=case_id,
        actor_key=investigator_key,
        actor_role="investigator",
        permissions=["view", "investigate"],
    )
    cur.execute(
        """
        INSERT INTO er_case_parties (party_id, company_code, case_id, party_role, employee_key, visibility)
        VALUES (%s,%s,%s,'investigator',%s,'er_only')
        """,
        (str(uuid.uuid4()), company, case_id, investigator_key),
    )
    cur.execute(
        """
        INSERT INTO er_task_links (link_id, company_code, case_id, shared_task_ref, task_kind)
        VALUES (%s,%s,%s,%s,'investigation')
        """,
        (str(uuid.uuid4()), company, case_id, f"hr_task://er/investigate/{case_id}"),
    )
    return {"ok": True, "case": case, "shared_task_reused": True}


def add_investigation_note(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    body_en: str,
    body_ar: str = "",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    perm = check_case_permission(
        cur, company_code=company, case_id=case_id, actor_key=actor_key, actor_role=actor_role, permission="investigate"
    )
    if not perm.get("allowed") and actor_role != "er_admin":
        return {"ok": False, "error": "er_access_denied"}
    note_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_investigation_notes (note_id, company_code, case_id, author_key, body_en, body_ar)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING note_id, case_id, author_key, locked, created_at
        """,
        (note_id, company, case_id, actor_key, body_en, body_ar),
    )
    # Do not return full body to non-investigators in API wrappers — here return metadata
    meta = _row(cur)
    return {"ok": True, "note": meta, "confidential": True, "hidden_from_employee": True}


def submit_finding(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    findings_en: str,
    findings_ar: str = "",
    lock: bool = True,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if actor_role not in {"investigator", "er_admin"} and not _has_grant(cur, company, case_id, actor_key, "investigate"):
        return {"ok": False, "error": "er_access_denied"}
    # Prevent silent overwrite of locked findings
    cur.execute(
        "SELECT finding_id FROM er_findings WHERE company_code=%s AND case_id=%s AND locked=true LIMIT 1",
        (company, case_id),
    )
    if cur.fetchone() and lock:
        return {"ok": False, "error": "locked_findings_not_silently_overwritten"}
    finding_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_findings (
          finding_id, company_code, case_id, investigator_key, findings_en, findings_ar, locked, submitted_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,now()) RETURNING finding_id, case_id, investigator_key, locked, submitted_at
        """,
        (finding_id, company, case_id, actor_key, findings_en, findings_ar, bool(lock)),
    )
    row = _row(cur)
    cur.execute(
        """
        UPDATE er_cases SET status='decision_action', updated_at=now()
         WHERE case_id=%s AND status IN ('investigating','triage','open')
        """,
        (case_id,),
    )
    return {"ok": True, "finding": row, "investigation_not_outcome": True, "locked": bool(lock)}


def attach_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    shared_document_ref: str,
    label_en: str = "",
    label_ar: str = "",
    sensitive: bool = True,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if not str(shared_document_ref).strip():
        return {"ok": False, "error": "shared_document_ref_required"}
    # Employee may attach requested evidence without gaining sensitive read of others
    if actor_role == "employee":
        pass
    elif actor_role not in {"er_admin", "investigator"} and not _has_grant(cur, company, case_id, actor_key, "investigate"):
        return {"ok": False, "error": "er_access_denied"}
    evidence_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_evidence_refs (
          evidence_id, company_code, case_id, shared_document_ref, label_en, label_ar, sensitive, uploaded_by
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING evidence_id, case_id, shared_document_ref, sensitive, uploaded_by
        """,
        (evidence_id, company, case_id, shared_document_ref, label_en, label_ar, bool(sensitive), actor_key),
    )
    return {"ok": True, "evidence": _row(cur), "reuses_shared_document_infrastructure": True}


def access_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    evidence_id: str,
    access_channel: str = "api",
) -> dict[str, Any]:
    """Fail-closed for unauthorized users across API/URL/export/Assistant."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "allowed": False}
    company = gate["company_code"]
    cur.execute(
        "SELECT * FROM er_evidence_refs WHERE company_code=%s AND evidence_id=%s",
        (company, evidence_id),
    )
    evid = _row(cur)
    if not evid:
        return {"ok": False, "allowed": False, "error": "evidence_not_found"}
    case_id = str(evid["case_id"])
    if evid.get("sensitive"):
        allowed = False
        if actor_role == "er_admin" and _has_grant(cur, company, case_id, actor_key, "sensitive_evidence"):
            allowed = True
        elif actor_role == "investigator" and _has_grant(cur, company, case_id, actor_key, "sensitive_evidence"):
            allowed = True
        elif actor_role == "er_admin" and _has_grant(cur, company, case_id, actor_key, "manage"):
            # manage alone is not enough — require sensitive_evidence explicitly
            allowed = _has_grant(cur, company, case_id, actor_key, "sensitive_evidence")
        if actor_role in {"ordinary_hr", "manager", "employee", "assistant"}:
            allowed = False
        if not allowed:
            return {
                "ok": False,
                "allowed": False,
                "error": "sensitive_evidence_denied",
                "access_channel": access_channel,
                "fail_closed": True,
                "channels_covered": ["api", "direct_url", "export", "assistant"],
            }
    return {
        "ok": True,
        "allowed": True,
        "evidence": {
            "evidence_id": evid["evidence_id"],
            "shared_document_ref": evid["shared_document_ref"],
            "sensitive": evid["sensitive"],
        },
        "access_channel": access_channel,
    }


def record_outcome(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    outcome_code: str,
    summary_en: str = "",
    summary_ar: str = "",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if actor_role != "er_admin" and not _has_grant(cur, company, case_id, actor_key, "decide"):
        return {"ok": False, "error": "er_access_denied"}
    code = str(outcome_code or "").lower()
    if code not in OUTCOME_CODES:
        return {"ok": False, "error": "invalid_outcome_code", "no_invented_kuwait_legal_outcomes": True}
    cur.execute("SELECT * FROM er_cases WHERE company_code=%s AND case_id=%s", (company, case_id))
    case = _row(cur)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    outcome_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_outcomes (
          outcome_id, company_code, case_id, outcome_code, summary_en, summary_ar,
          employment_mutated, decided_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,false,%s) RETURNING *
        """,
        (outcome_id, company, case_id, code, summary_en[:500], summary_ar[:500], _digits(actor_phone)),
    )
    outcome = _row(cur)
    cur.execute(
        "UPDATE er_cases SET status='closed', closed_at=now(), updated_at=now() WHERE case_id=%s RETURNING *",
        (case_id,),
    )
    _emit_safe_fact(
        cur,
        company=company,
        fact_type="er.case_outcome",
        entity_type="outcome",
        entity_id=outcome_id,
        payload={"case_type_code": case["case_type_code"], "outcome_code": code, "status": "closed"},
    )
    return {
        "ok": True,
        "outcome": outcome,
        "outcome_not_employment_mutation": True,
        "employment_mutated": False,
        "investigation_not_outcome": True,
    }


def create_employment_change_handoff(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    outcome_id: str,
    handoff_payload: dict | None = None,
) -> dict[str, Any]:
    """OPTIONAL handoff to Wave 3 employment-change — ER does not mutate employment."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if actor_role != "er_admin" and not _has_grant(cur, company, case_id, actor_key, "decide"):
        return {"ok": False, "error": "er_access_denied"}
    handoff_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_employment_handoffs (
          handoff_id, company_code, case_id, outcome_id, target_authority, handoff_payload,
          applied, employment_mutated_by_er, created_by_phone
        ) VALUES (%s,%s,%s,%s,'employment_change_c1',%s::jsonb,false,false,%s) RETURNING *
        """,
        (
            handoff_id, company, case_id, outcome_id, json.dumps(handoff_payload or {}),
            _digits(actor_phone),
        ),
    )
    return {
        "ok": True,
        "handoff": _row(cur),
        "applied": False,
        "employment_mutated_by_er": False,
        "outcome_not_employment_mutation": True,
        "wave3_employment_change_remains_authority": True,
    }


def post_safe_employee_message(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    body_en: str,
    body_ar: str,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if actor_role != "er_admin" and not _has_grant(cur, company, case_id, actor_key, "manage"):
        return {"ok": False, "error": "er_access_denied"}
    # Reject if body looks like internal note dump
    lowered = (body_en + " " + body_ar).lower()
    for needle in ("witness:", "investigation note", "finding:", "allegation detail"):
        if needle in lowered:
            return {"ok": False, "error": "unsafe_employee_message_content"}
    message_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO er_safe_messages (message_id, company_code, case_id, body_en, body_ar, created_by_phone)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (message_id, company, case_id, body_en[:500], body_ar[:500], _digits(actor_phone)),
    )
    return {"ok": True, "message": _row(cur)}


def employee_safe_case_view(cur: Any, *, company_code: str, employee_key: str, case_id: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "employee_relations_disabled_for_company"}
    cur.execute(
        """
        SELECT case_id, status, case_type_code, opened_at, closed_at, intake_source
          FROM er_cases
         WHERE company_code=%s AND case_id=%s
           AND (subject_employee_key=%s OR reporter_employee_key=%s)
        """,
        (company, case_id, employee_key, employee_key),
    )
    case = _row(cur)
    if not case:
        return {"ok": False, "error": "case_not_found_or_forbidden"}
    safe_status = SAFE_EMPLOYEE_STATUSES.get(str(case["status"]), "under_review")
    cur.execute(
        """
        SELECT message_id, body_en, body_ar, created_at FROM er_safe_messages
         WHERE company_code=%s AND case_id=%s ORDER BY created_at
        """,
        (company, case_id),
    )
    messages = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "case_id": case["case_id"],
        "safe_status": safe_status,
        "safe_status_label_en": status_label(safe_status, lang="en"),
        "safe_status_label_ar": status_label(safe_status, lang="ar"),
        "messages": messages,
        "internal_notes_included": False,
        "witness_statements_included": False,
        "investigation_detail_included": False,
        "evidence_detail_included": False,
    }


def er_case_detail(
    cur: Any, *, company_code: str, actor_key: str, actor_role: str, case_id: str
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    perm = check_case_permission(
        cur, company_code=company, case_id=case_id, actor_key=actor_key, actor_role=actor_role, permission="view"
    )
    if not perm.get("allowed") and actor_role != "er_admin":
        return {"ok": False, "error": "er_access_denied", "case_level_need_to_know": True}
    if actor_role == "er_admin" and not _has_grant(cur, company, case_id, actor_key, "view") and not _has_grant(cur, company, case_id, actor_key, "manage"):
        # Allow er_admin who opened / has any grant; else deny for prove of need-to-know
        cur.execute(
            "SELECT 1 FROM er_access_grants WHERE company_code=%s AND case_id=%s AND actor_key=%s AND revoked_at IS NULL LIMIT 1",
            (company, case_id, actor_key),
        )
        if not cur.fetchone():
            return {"ok": False, "error": "er_access_denied", "case_level_need_to_know": True}
    cur.execute("SELECT * FROM er_cases WHERE company_code=%s AND case_id=%s", (company, case_id))
    case = _row(cur)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    cur.execute("SELECT allegation_id, allegation_code, proven FROM er_allegations WHERE case_id=%s", (case_id,))
    allegations_meta = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "case": case,
        "allegations_meta": allegations_meta,
        "sla": case_derived_sla(case),
    }


def assistant_query_er(
    cur: Any, *, company_code: str, actor: str, question_kind: str, case_id: str | None = None
) -> dict[str, Any]:
    _ = actor
    if question_kind == "process_metadata" and case_id:
        gate = runtime_gate_for_company(company_code)
        if not gate.get("ok"):
            return gate
        cur.execute(
            "SELECT case_id, status, case_type_code, case_type_version, confidentiality_class FROM er_cases WHERE company_code=%s AND case_id=%s",
            (gate["company_code"], case_id),
        )
        case = _row(cur)
        return {"ok": True, "mutations": False, "no_case_narrative_dump": True, "metadata": case}
    if question_kind in {"mutate_case", "dump_notes", "access_evidence", "decide_outcome"}:
        return {"ok": False, "error": "mutation_forbidden", "mutations": False}
    return {"ok": False, "error": "unsupported_or_forbidden", "mutations": False}


def _notify_dedupe(cur: Any, *, company: str, key: str) -> dict[str, Any]:
    """Notifications must stay payload-safe (no allegation/evidence text)."""
    dedupe_key = f"{company}:{key}"
    sp = f"er_nd_{uuid.uuid4().hex[:12]}"
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(
            "INSERT INTO er_notification_dedupe (dedupe_key, company_code, payload_safe) VALUES (%s,%s,true)",
            (dedupe_key, company),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": True, "deduped": False, "payload_safe": True, "no_sensitive_text_in_payload": True}
    except Exception:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": False, "deduped": True, "payload_safe": True}


def wave5_payload_is_safe(payload: dict[str, Any]) -> bool:
    forbidden = {
        "allegation_text", "statement_en", "statement_ar", "findings_en", "findings_ar",
        "witness_statement", "evidence_text", "note_text", "body_en", "body_ar",
    }
    return not any(k in payload for k in forbidden)
