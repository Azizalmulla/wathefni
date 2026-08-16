"""Wave 6 C5 — Engagement (surveys/pulses, anonymity-first).

Canonical authority:
  survey definition → audience snapshot → launch → response collection →
  anonymity enforcement → governed aggregates → action planning

Does NOT own employee/org/employment. Recognition OUT of MVP.
Anonymous: no respondent↔answer mapping via ordinary app authority.
min_responses default 5, configurable upward only.
eNPS only on explicit enps_scale questions.
Action plans ≠ ER / ≠ performance development.
Assistant mutations OUT. No second analytics engine.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

PHASE = "engagement_c5"
CONTRACT_VERSION = "engagement_c5_v1"
PASS_STAMP = "ENGAGEMENT_FULL_PASS"
COMMERCIAL_MODULE_KEY = "engagement"
FLAG = "WATHEFNI_ENGAGEMENT_C5"
COMPANIES_FLAG = "WATHEFNI_ENGAGEMENT_COMPANIES"
_ON = {"1", "true", "yes", "on"}
DEFAULT_MIN_RESPONSES = 5

PRIVACY_MODES = ("anonymous", "confidential_restricted", "identified")
QUESTION_TYPES = ("rating_scale", "single_choice", "multiple_choice", "free_text", "enps_scale")
CAMPAIGN_STATES = ("draft", "launched", "closed")
INVITE_STATES = ("invited", "started", "submitted")
ACTION_STATES = ("open", "in_progress", "done", "cancelled")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "launched": {"en": "Launched", "ar": "مُطلق"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "invited": {"en": "Invited", "ar": "مدعو"},
    "started": {"en": "Started", "ar": "بدأ"},
    "submitted": {"en": "Submitted", "ar": "مُرسل"},
    "anonymous": {"en": "Anonymous", "ar": "مجهول"},
    "confidential_restricted": {"en": "Confidential / restricted", "ar": "سري/مقيّد"},
    "identified": {"en": "Identified", "ar": "مُعرّف"},
    "suppressed": {"en": "Suppressed", "ar": "محجوب"},
    "engagement": {"en": "Engagement", "ar": "المشاركة والارتباط"},
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


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "does_not_own_employee_employment_org": True,
        "recognition_out_of_mvp": True,
        "works_without_er": True,
        "works_without_performance_talent": True,
        "works_without_learning": True,
        "works_without_payroll": True,
        "min_responses_default_5": True,
        "threshold_upward_only": True,
        "anonymous_no_respondent_answer_map": True,
        "participation_separated_from_answers": True,
        "below_threshold_fail_closed": True,
        "complementary_suppression": True,
        "enps_only_on_explicit_scale": True,
        "action_plan_not_er_or_development": True,
        "feedback_does_not_auto_create_er": True,
        "no_second_analytics_engine": True,
        "assistant_mutations": False,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {"primary_admin": True, "not_generic_bi": True},
        "hr_mobile": {"intentionally_thin": True, "no_heavy_survey_authoring": True},
        "manager": {"aggregates_only_when_threshold_met": True, "no_raw_anonymous_answers": True},
        "employee_app": {"open_surveys": True, "privacy_mode_before_response": True, "no_company_analytics_by_default": True},
        "assistant": {"mutations": False, "respects_anonymity_suppression": True},
        "setup": {"owns_anonymity_and_threshold_policy": True},
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "engagement_c5_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "engagement_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "engagement_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_engagement_c5_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eng_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          min_responses int NOT NULL DEFAULT 5,
          default_privacy_mode text NOT NULL DEFAULT 'anonymous',
          manager_results_enabled boolean NOT NULL DEFAULT true,
          free_text_enabled boolean NOT NULL DEFAULT true,
          free_text_access_role text NOT NULL DEFAULT 'engagement_admin',
          employee_survey_enabled boolean NOT NULL DEFAULT true,
          action_plans_enabled boolean NOT NULL DEFAULT true,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CHECK (min_responses >= 5),
          CHECK (default_privacy_mode IN ('anonymous','confidential_restricted','identified'))
        )
        """
    )
    for ddl in (
        """
        CREATE TABLE IF NOT EXISTS eng_surveys (
          survey_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          status text NOT NULL DEFAULT 'template',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_survey_versions (
          survey_version_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          survey_id uuid NOT NULL REFERENCES eng_surveys(survey_id),
          version_no int NOT NULL,
          privacy_mode text NOT NULL,
          min_responses int NOT NULL DEFAULT 5,
          visibility text NOT NULL DEFAULT 'hr_and_managers_threshold',
          snapshot jsonb NOT NULL,
          frozen_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (survey_id, version_no),
          CHECK (privacy_mode IN ('anonymous','confidential_restricted','identified')),
          CHECK (min_responses >= 5)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_questions (
          question_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          survey_version_id uuid NOT NULL REFERENCES eng_survey_versions(survey_version_id),
          question_type text NOT NULL,
          prompt_en text NOT NULL,
          prompt_ar text NOT NULL,
          scale_min int,
          scale_max int,
          options jsonb NOT NULL DEFAULT '[]'::jsonb,
          is_enps boolean NOT NULL DEFAULT false,
          sort_order int NOT NULL DEFAULT 0,
          CHECK (question_type IN ('rating_scale','single_choice','multiple_choice','free_text','enps_scale'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_campaigns (
          campaign_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          survey_id uuid NOT NULL REFERENCES eng_surveys(survey_id),
          survey_version_id uuid NOT NULL REFERENCES eng_survey_versions(survey_version_id),
          title_en text NOT NULL,
          title_ar text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          privacy_mode text NOT NULL,
          min_responses int NOT NULL,
          opens_at timestamptz,
          closes_at timestamptz,
          audience_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
          audience_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
          audience_frozen boolean NOT NULL DEFAULT false,
          calculation_version text NOT NULL DEFAULT 'engagement_calc_v1',
          launched_at timestamptz,
          closed_at timestamptz,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('draft','launched','closed')),
          CHECK (privacy_mode IN ('anonymous','confidential_restricted','identified')),
          CHECK (min_responses >= 5)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_invitations (
          invitation_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          campaign_id uuid NOT NULL REFERENCES eng_campaigns(campaign_id),
          employee_key text NOT NULL,
          status text NOT NULL DEFAULT 'invited',
          started_at timestamptz,
          submitted_at timestamptz,
          department_snapshot text NOT NULL DEFAULT '',
          location_snapshot text NOT NULL DEFAULT '',
          manager_scope_snapshot text NOT NULL DEFAULT '',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (campaign_id, employee_key),
          CHECK (status IN ('invited','started','submitted'))
        )
        """,
        # Response batches intentionally have NO FK to invitations for anonymous mode.
        # Identified mode may store employee_key; anonymous must keep employee_key NULL.
        """
        CREATE TABLE IF NOT EXISTS eng_response_batches (
          batch_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          campaign_id uuid NOT NULL REFERENCES eng_campaigns(campaign_id),
          privacy_mode text NOT NULL,
          employee_key text,
          submitted_at timestamptz NOT NULL DEFAULT now(),
          CHECK (privacy_mode IN ('anonymous','confidential_restricted','identified')),
          CHECK (
            (privacy_mode = 'anonymous' AND employee_key IS NULL)
            OR (privacy_mode <> 'anonymous')
          )
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_answers (
          answer_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          campaign_id uuid NOT NULL REFERENCES eng_campaigns(campaign_id),
          batch_id uuid NOT NULL REFERENCES eng_response_batches(batch_id),
          question_id uuid NOT NULL REFERENCES eng_questions(question_id),
          value_number numeric,
          value_text text,
          value_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_action_plans (
          action_plan_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          campaign_id uuid NOT NULL REFERENCES eng_campaigns(campaign_id),
          title_en text NOT NULL,
          title_ar text NOT NULL,
          source_result_ref text NOT NULL DEFAULT '',
          owner_key text,
          status text NOT NULL DEFAULT 'open',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('open','in_progress','done','cancelled'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_action_items (
          action_item_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          action_plan_id uuid NOT NULL REFERENCES eng_action_plans(action_plan_id),
          title_en text NOT NULL,
          title_ar text NOT NULL,
          owner_key text,
          due_date date,
          status text NOT NULL DEFAULT 'open',
          shared_task_ref text NOT NULL DEFAULT '',
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('open','in_progress','done','cancelled'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eng_wave5_fact_outbox (
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
        CREATE TABLE IF NOT EXISTS eng_audit_events (
          audit_id uuid PRIMARY KEY,
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
        CREATE TABLE IF NOT EXISTS eng_notification_dedupe (
          dedupe_key text PRIMARY KEY,
          company_code text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ):
        cur.execute(ddl)
    # Explicitly do NOT create recognition tables.


def recognition_absent_check() -> dict[str, Any]:
    src = open(__file__, encoding="utf-8").read().lower()
    needle = "create table if not exists " + "eng_recognition"
    return {
        "ok": True,
        "recognition_out_of_mvp": True,
        "has_recognition_table_ddl": needle in src,
        "recognition_absent": needle not in src,
    }


def _audit(cur: Any, *, company: str, actor: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO eng_audit_events (audit_id, company_code, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, _digits(actor), action, entity_type, entity_id, json.dumps(detail or {})),
    )


def _emit(cur: Any, *, company: str, fact_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
    # Never emit raw answers or free text
    clean = {k: v for k, v in dict(payload or {}).items() if k not in {"answers", "value_text", "free_text", "respondent"}}
    cur.execute(
        """
        INSERT INTO eng_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, json.dumps(clean)),
    )


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def enable_company_engagement(cur: Any, *, company_code: str, actor_phone: str, reason: str, **kwargs: Any) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_engagement_c5_schema(cur)
    min_r = int(kwargs.get("min_responses", DEFAULT_MIN_RESPONSES))
    if min_r < DEFAULT_MIN_RESPONSES:
        return {"ok": False, "error": "threshold_upward_only", "min_allowed": DEFAULT_MIN_RESPONSES}
    privacy = str(kwargs.get("default_privacy_mode") or "anonymous")
    if privacy not in PRIVACY_MODES:
        return {"ok": False, "error": "invalid_privacy_mode"}
    cur.execute(
        """
        INSERT INTO eng_company_settings (
          company_code, enabled, min_responses, default_privacy_mode, manager_results_enabled,
          free_text_enabled, employee_survey_enabled, action_plans_enabled,
          enabled_by_phone, enabled_reason, enabled_at, disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          min_responses=EXCLUDED.min_responses,
          default_privacy_mode=EXCLUDED.default_privacy_mode,
          manager_results_enabled=EXCLUDED.manager_results_enabled,
          free_text_enabled=EXCLUDED.free_text_enabled,
          employee_survey_enabled=EXCLUDED.employee_survey_enabled,
          action_plans_enabled=EXCLUDED.action_plans_enabled,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (
            company, min_r, privacy,
            bool(kwargs.get("manager_results_enabled", True)),
            bool(kwargs.get("free_text_enabled", True)),
            bool(kwargs.get("employee_survey_enabled", True)),
            bool(kwargs.get("action_plans_enabled", True)),
            _digits(actor_phone), str(reason).strip()[:500], _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company)}


def disable_company_engagement(cur: Any, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_engagement_c5_schema(cur)
    cur.execute(
        """
        UPDATE eng_company_settings
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
    ensure_engagement_c5_schema(cur)
    cur.execute("SELECT enabled FROM eng_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "engagement_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _settings(cur: Any, company: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM eng_company_settings WHERE company_code=%s", (company,))
    return _row(cur) or {}


def set_min_responses(cur: Any, *, company_code: str, actor_phone: str, min_responses: int) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    current = int(settings.get("min_responses") or DEFAULT_MIN_RESPONSES)
    target = int(min_responses)
    if target < DEFAULT_MIN_RESPONSES:
        return {"ok": False, "error": "threshold_upward_only", "min_allowed": DEFAULT_MIN_RESPONSES}
    if target < current:
        return {"ok": False, "error": "threshold_upward_only", "current": current, "requested": target}
    cur.execute(
        "UPDATE eng_company_settings SET min_responses=%s, updated_by_phone=%s, updated_at=now() WHERE company_code=%s RETURNING *",
        (target, _digits(actor_phone), company),
    )
    return {"ok": True, "settings": _row(cur), "threshold_upward_only": True}


def create_survey_template(
    cur: Any, *, company_code: str, actor_phone: str, code: str, title_en: str, title_ar: str
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    survey_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO eng_surveys (survey_id, company_code, code, title_en, title_ar, created_by_phone)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (survey_id, company, code.strip(), title_en.strip(), title_ar.strip(), _digits(actor_phone)),
    )
    return {"ok": True, "survey": _row(cur), "stable_id": survey_id, "recognition_absent": True}


def create_survey_version(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    survey_id: str,
    version_no: int,
    privacy_mode: str,
    questions: list[dict[str, Any]],
    min_responses: int | None = None,
    visibility: str = "hr_and_managers_threshold",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    mode = str(privacy_mode or settings.get("default_privacy_mode") or "anonymous")
    if mode not in PRIVACY_MODES:
        return {"ok": False, "error": "invalid_privacy_mode", "allowed": list(PRIVACY_MODES)}
    min_r = int(min_responses if min_responses is not None else settings.get("min_responses") or DEFAULT_MIN_RESPONSES)
    if min_r < DEFAULT_MIN_RESPONSES:
        return {"ok": False, "error": "threshold_upward_only"}
    if not questions:
        return {"ok": False, "error": "questions_required"}
    for q in questions:
        qt = str(q.get("question_type") or "").lower()
        if qt not in QUESTION_TYPES:
            return {"ok": False, "error": "invalid_question_type", "type": qt}
        if qt == "enps_scale":
            if int(q.get("scale_min", 0)) != 0 or int(q.get("scale_max", 10)) != 10:
                return {"ok": False, "error": "enps_requires_0_to_10_scale"}
        if qt == "free_text" and not settings.get("free_text_enabled", True):
            return {"ok": False, "error": "free_text_disabled"}
    survey_version_id = str(uuid.uuid4())
    snapshot = {
        "privacy_mode": mode,
        "min_responses": min_r,
        "visibility": visibility,
        "questions": questions,
        "wording_frozen_marker": True,
    }
    cur.execute(
        """
        INSERT INTO eng_survey_versions (
          survey_version_id, company_code, survey_id, version_no, privacy_mode, min_responses, visibility, snapshot
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING *
        """,
        (survey_version_id, company, survey_id, int(version_no), mode, min_r, visibility, json.dumps(snapshot)),
    )
    version = _row(cur)
    for idx, q in enumerate(questions):
        qt = str(q["question_type"]).lower()
        is_enps = qt == "enps_scale"
        cur.execute(
            """
            INSERT INTO eng_questions (
              question_id, company_code, survey_version_id, question_type, prompt_en, prompt_ar,
              scale_min, scale_max, options, is_enps, sort_order
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            """,
            (
                str(uuid.uuid4()), company, survey_version_id, qt,
                str(q.get("prompt_en") or ""), str(q.get("prompt_ar") or ""),
                q.get("scale_min"), q.get("scale_max"), json.dumps(q.get("options") or []),
                is_enps, int(q.get("sort_order", idx)),
            ),
        )
    return {"ok": True, "survey_version": version, "privacy_mode_label_en": status_label(mode, lang="en"), "privacy_mode_label_ar": status_label(mode, lang="ar")}


def create_campaign(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    survey_id: str,
    survey_version_id: str,
    title_en: str,
    title_ar: str,
    audience_rule: dict[str, Any],
    audience_employee_keys: list[str],
    opens_at: datetime | str | None = None,
    closes_at: datetime | str | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM eng_survey_versions WHERE company_code=%s AND survey_version_id=%s",
        (company, survey_version_id),
    )
    ver = _row(cur)
    if not ver:
        return {"ok": False, "error": "survey_version_not_found"}
    if not audience_employee_keys:
        return {"ok": False, "error": "audience_required"}
    # Snapshot audience with optional department/location attrs from rule metadata
    attrs = dict(audience_rule.get("employee_attrs") or {})
    snapshot = []
    for key in audience_employee_keys:
        meta = dict(attrs.get(key) or {})
        snapshot.append({
            "employee_key": key,
            "department": meta.get("department", ""),
            "location": meta.get("location", ""),
            "manager_scope": meta.get("manager_scope", ""),
        })
    campaign_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO eng_campaigns (
          campaign_id, company_code, survey_id, survey_version_id, title_en, title_ar, status,
          privacy_mode, min_responses, opens_at, closes_at, audience_rule, audience_snapshot,
          audience_frozen, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s::jsonb,%s::jsonb,false,%s) RETURNING *
        """,
        (
            campaign_id, company, survey_id, survey_version_id, title_en, title_ar,
            ver["privacy_mode"], int(ver["min_responses"]), opens_at, closes_at,
            json.dumps(audience_rule or {}), json.dumps(snapshot), _digits(actor_phone),
        ),
    )
    return {"ok": True, "campaign": _row(cur), "audience_count": len(snapshot)}


def launch_campaign(cur: Any, *, company_code: str, actor_phone: str, campaign_id: str) -> dict[str, Any]:
    """Freeze survey version + audience at launch."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT * FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if not camp:
        return {"ok": False, "error": "campaign_not_found"}
    if camp["status"] != "draft":
        return {"ok": False, "error": "campaign_not_draft"}
    audience = camp.get("audience_snapshot") or []
    if isinstance(audience, str):
        audience = json.loads(audience)
    cur.execute(
        """
        UPDATE eng_campaigns
           SET status='launched', audience_frozen=true, launched_at=now(), updated_at=now()
         WHERE campaign_id=%s RETURNING *
        """,
        (campaign_id,),
    )
    launched = _row(cur)
    cur.execute(
        "UPDATE eng_survey_versions SET frozen_at=COALESCE(frozen_at, now()) WHERE survey_version_id=%s",
        (camp["survey_version_id"],),
    )
    for member in audience:
        cur.execute(
            """
            INSERT INTO eng_invitations (
              invitation_id, company_code, campaign_id, employee_key, status,
              department_snapshot, location_snapshot, manager_scope_snapshot
            ) VALUES (%s,%s,%s,%s,'invited',%s,%s,%s)
            ON CONFLICT (campaign_id, employee_key) DO NOTHING
            """,
            (
                str(uuid.uuid4()), company, campaign_id, member["employee_key"],
                member.get("department", ""), member.get("location", ""), member.get("manager_scope", ""),
            ),
        )
    _emit(
        cur, company=company, fact_type="engagement.eligible_audience", entity_type="campaign",
        entity_id=campaign_id, payload={"audience_count": len(audience), "privacy_mode": camp["privacy_mode"]},
    )
    _notify_dedupe(cur, company=company, key=f"launch:{campaign_id}")
    return {
        "ok": True,
        "campaign": launched,
        "survey_version_frozen": True,
        "audience_frozen": True,
        "privacy_mode": camp["privacy_mode"],
        "privacy_mode_label_en": status_label(camp["privacy_mode"], lang="en"),
        "privacy_mode_label_ar": status_label(camp["privacy_mode"], lang="ar"),
    }


def campaign_population(cur: Any, *, company_code: str, campaign_id: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT employee_key FROM eng_invitations WHERE company_code=%s AND campaign_id=%s ORDER BY employee_key",
        (company, campaign_id),
    )
    keys = [dict(r)["employee_key"] for r in cur.fetchall()]
    return {"ok": True, "employee_keys": keys, "frozen": True}


def start_response(cur: Any, *, company_code: str, employee_key: str, campaign_id: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    if not settings.get("employee_survey_enabled", True):
        return {"ok": False, "error": "employee_survey_disabled"}
    cur.execute(
        "SELECT * FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s",
        (company, campaign_id),
    )
    camp = _row(cur)
    if not camp or camp["status"] != "launched":
        return {"ok": False, "error": "campaign_not_open"}
    cur.execute(
        """
        UPDATE eng_invitations SET status='started', started_at=COALESCE(started_at, now())
         WHERE company_code=%s AND campaign_id=%s AND employee_key=%s AND status IN ('invited','started')
        RETURNING invitation_id, status, employee_key
        """,
        (company, campaign_id, employee_key),
    )
    inv = _row(cur)
    if not inv:
        return {"ok": False, "error": "not_in_audience"}
    return {
        "ok": True,
        "invitation": inv,
        "privacy_mode": camp["privacy_mode"],
        "privacy_mode_label_en": status_label(camp["privacy_mode"], lang="en"),
        "privacy_mode_label_ar": status_label(camp["privacy_mode"], lang="ar"),
        "privacy_disclosed_before_response": True,
    }


def submit_response(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    campaign_id: str,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Participation updated separately from answer batch; anonymous batches have no employee_key."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT * FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if not camp or camp["status"] != "launched":
        return {"ok": False, "error": "campaign_not_open"}
    cur.execute(
        """
        SELECT * FROM eng_invitations
         WHERE company_code=%s AND campaign_id=%s AND employee_key=%s
        """,
        (company, campaign_id, employee_key),
    )
    inv = _row(cur)
    if not inv:
        return {"ok": False, "error": "not_in_audience"}
    if inv["status"] == "submitted":
        return {"ok": False, "error": "already_submitted_immutable"}
    privacy = camp["privacy_mode"]
    batch_id = str(uuid.uuid4())
    emp_key_for_batch = None if privacy == "anonymous" else employee_key
    cur.execute(
        """
        INSERT INTO eng_response_batches (batch_id, company_code, campaign_id, privacy_mode, employee_key)
        VALUES (%s,%s,%s,%s,%s) RETURNING batch_id, privacy_mode, employee_key
        """,
        (batch_id, company, campaign_id, privacy, emp_key_for_batch),
    )
    batch = _row(cur)
    for ans in answers:
        cur.execute(
            """
            INSERT INTO eng_answers (
              answer_id, company_code, campaign_id, batch_id, question_id, value_number, value_text, value_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                str(uuid.uuid4()), company, campaign_id, batch_id, ans["question_id"],
                ans.get("value_number"), ans.get("value_text"), json.dumps(ans.get("value_json") or {}),
            ),
        )
    # Mark participation WITHOUT linking to batch_id
    cur.execute(
        """
        UPDATE eng_invitations SET status='submitted', submitted_at=now()
         WHERE invitation_id=%s RETURNING invitation_id, status, employee_key, submitted_at
        """,
        (inv["invitation_id"],),
    )
    participation = _row(cur)
    return {
        "ok": True,
        "participation": participation,
        "batch": batch,
        "participation_separated_from_answers": True,
        "anonymous_batch_has_no_employee_key": privacy == "anonymous" and batch and batch.get("employee_key") is None,
        "auto_created_er_case": False,
        "immutable_after_submit": True,
    }


def assert_no_respondent_answer_map(cur: Any, *, company_code: str, campaign_id: str) -> dict[str, Any]:
    """Ordinary application authority cannot recombine who→what for anonymous campaigns."""
    company = company_code_norm(company_code)
    cur.execute("SELECT privacy_mode FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if not camp:
        return {"ok": False, "error": "campaign_not_found"}
    if camp["privacy_mode"] != "anonymous":
        return {"ok": True, "applicable": False, "privacy_mode": camp["privacy_mode"]}
    # No join table; batches have null employee_key; no column linking invitation to batch
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM eng_response_batches
         WHERE company_code=%s AND campaign_id=%s AND employee_key IS NOT NULL
        """,
        (company, campaign_id),
    )
    leak = int(dict(cur.fetchone())["c"])
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.columns
         WHERE table_name='eng_invitations' AND column_name='batch_id'
        """
    )
    has_join_col = int(dict(cur.fetchone())["c"]) > 0
    return {
        "ok": True,
        "applicable": True,
        "anonymous_batches_with_employee_key": leak,
        "invitation_batch_join_column": has_join_col,
        "respondent_answer_map_unavailable": leak == 0 and not has_join_col,
    }


def try_admin_resolve_respondent_answers(
    cur: Any, *, company_code: str, campaign_id: str, employee_key: str, actor_role: str = "engagement_admin"
) -> dict[str, Any]:
    """Fail closed for anonymous — even admins cannot resolve answers by employee."""
    _ = actor_role
    company = company_code_norm(company_code)
    cur.execute("SELECT privacy_mode FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if not camp:
        return {"ok": False, "error": "campaign_not_found"}
    if camp["privacy_mode"] == "anonymous":
        return {
            "ok": False,
            "allowed": False,
            "error": "anonymous_respondent_answer_map_unavailable",
            "admin_cannot_resolve": True,
        }
    cur.execute(
        """
        SELECT a.question_id, a.value_number, a.value_text
          FROM eng_answers a
          JOIN eng_response_batches b ON b.batch_id=a.batch_id
         WHERE a.company_code=%s AND a.campaign_id=%s AND b.employee_key=%s
        """,
        (company, campaign_id, employee_key),
    )
    return {"ok": True, "allowed": True, "answers": [dict(r) for r in cur.fetchall()]}


def hr_edit_response_forbidden() -> dict[str, Any]:
    return {"ok": False, "error": "hr_cannot_edit_employee_response", "mutations": False}


def compute_aggregates(
    cur: Any,
    *,
    company_code: str,
    campaign_id: str,
    segment: dict[str, str] | None = None,
    actor_role: str = "engagement_admin",
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Threshold + complementary suppression. Never send suppressed raw to frontend."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    cur.execute("SELECT * FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if not camp:
        return {"ok": False, "error": "campaign_not_found"}
    min_r = int(camp["min_responses"])
    seg = dict(segment or {})

    # Count submitted participation in segment
    where = ["company_code=%s", "campaign_id=%s", "status='submitted'"]
    params: list[Any] = [company, campaign_id]
    if seg.get("department"):
        where.append("department_snapshot=%s")
        params.append(seg["department"])
    if seg.get("location"):
        where.append("location_snapshot=%s")
        params.append(seg["location"])
    if actor_role == "manager":
        if not settings.get("manager_results_enabled", True):
            return {"ok": False, "error": "manager_results_disabled", "suppressed": True}
        keys = list(manager_scope_employee_keys or [])
        if not keys:
            return {"ok": True, "suppressed": True, "reason": "manager_scope_empty", "raw_values_sent": False}
        where.append("employee_key = ANY(%s)")
        params.append(keys)
    cur.execute(f"SELECT COUNT(*) AS c FROM eng_invitations WHERE {' AND '.join(where)}", params)
    n = int(dict(cur.fetchone())["c"])

    # Complementary: total and complement
    cur.execute(
        "SELECT COUNT(*) AS c FROM eng_invitations WHERE company_code=%s AND campaign_id=%s AND status='submitted'",
        (company, campaign_id),
    )
    total_n = int(dict(cur.fetchone())["c"])
    complement_n = total_n - n if seg else None

    if n < min_r:
        return {
            "ok": True,
            "suppressed": True,
            "reason": "below_threshold",
            "n": None,  # do not leak exact small n to client when policy requires
            "threshold": min_r,
            "raw_values_sent": False,
            "fail_closed": True,
            "scores": None,
            "enps": None,
        }
    if seg and complement_n is not None and complement_n < min_r and complement_n > 0:
        return {
            "ok": True,
            "suppressed": True,
            "reason": "complementary_suppression",
            "threshold": min_r,
            "raw_values_sent": False,
            "fail_closed": True,
            "scores": None,
            "enps": None,
        }

    # Aggregate numeric answers only (not free text by default)
    cur.execute(
        """
        SELECT q.question_id, q.question_type, q.is_enps, q.scale_min, q.scale_max,
               COUNT(a.answer_id) AS answer_n,
               AVG(a.value_number) AS avg_score
          FROM eng_questions q
          JOIN eng_answers a ON a.question_id=q.question_id AND a.campaign_id=%s
         WHERE q.survey_version_id=%s AND q.question_type <> 'free_text'
         GROUP BY q.question_id, q.question_type, q.is_enps, q.scale_min, q.scale_max
        """,
        (campaign_id, camp["survey_version_id"]),
    )
    scores = []
    enps_result = None
    for row in cur.fetchall():
        r = dict(row)
        entry = {
            "question_id": str(r["question_id"]),
            "question_type": r["question_type"],
            "avg_score": float(r["avg_score"]) if r["avg_score"] is not None else None,
            "answer_n": int(r["answer_n"]),
        }
        if r["is_enps"] and r["question_type"] == "enps_scale":
            enps_result = compute_enps(cur, company_code=company, campaign_id=campaign_id, question_id=str(r["question_id"]))
            entry["enps"] = enps_result
        scores.append(entry)

    _emit(
        cur, company=company, fact_type="engagement.participation", entity_type="campaign",
        entity_id=campaign_id, payload={"submitted_n": n, "eligible_n": total_n, "rate": (n / total_n) if total_n else 0},
    )
    return {
        "ok": True,
        "suppressed": False,
        "n": n,
        "threshold": min_r,
        "raw_values_sent": False,
        "scores": scores,
        "enps": enps_result,
        "calculation_version": camp["calculation_version"],
        "manager_raw_anonymous_answers": False,
    }


def compute_enps(cur: Any, *, company_code: str, campaign_id: str, question_id: str) -> dict[str, Any]:
    """eNPS only for explicit enps_scale (0–10): promoters 9–10, detractors 0–6."""
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT question_type, is_enps, scale_min, scale_max FROM eng_questions
         WHERE company_code=%s AND question_id=%s
        """,
        (company, question_id),
    )
    q = _row(cur)
    if not q or not q.get("is_enps") or q.get("question_type") != "enps_scale":
        return {"ok": False, "error": "not_enps_question", "enps_only_on_explicit_scale": True}
    if int(q.get("scale_min") or -1) != 0 or int(q.get("scale_max") or -1) != 10:
        return {"ok": False, "error": "enps_requires_0_to_10_scale"}
    cur.execute(
        """
        SELECT value_number FROM eng_answers
         WHERE company_code=%s AND campaign_id=%s AND question_id=%s AND value_number IS NOT NULL
        """,
        (company, campaign_id, question_id),
    )
    values = [float(dict(r)["value_number"]) for r in cur.fetchall()]
    if not values:
        return {"ok": True, "enps": None, "n": 0}
    promoters = sum(1 for v in values if v >= 9)
    detractors = sum(1 for v in values if v <= 6)
    n = len(values)
    score = round(100.0 * (promoters - detractors) / n, 2)
    result = {
        "ok": True,
        "enps": score,
        "n": n,
        "promoters": promoters,
        "detractors": detractors,
        "passives": n - promoters - detractors,
        "scale": "0_to_10",
        "calculation_version": "enps_v1",
        "not_arbitrary_1_to_5": True,
    }
    _emit(
        cur, company=company, fact_type="engagement.enps", entity_type="question",
        entity_id=question_id, payload={"campaign_id": campaign_id, "enps": score, "n": n},
    )
    return result


def manager_raw_anonymous_answers(
    cur: Any, *, company_code: str, campaign_id: str, manager_scope_employee_keys: list[str]
) -> dict[str, Any]:
    _ = manager_scope_employee_keys
    company = company_code_norm(company_code)
    cur.execute("SELECT privacy_mode FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if camp and camp["privacy_mode"] == "anonymous":
        return {
            "ok": False,
            "allowed": False,
            "error": "manager_cannot_see_raw_anonymous_answers",
            "answers": None,
        }
    return {"ok": False, "allowed": False, "error": "not_authorized_for_raw"}


def create_action_plan(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    campaign_id: str,
    title_en: str,
    title_ar: str,
    source_result_ref: str,
    owner_key: str,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    if not settings.get("action_plans_enabled", True):
        return {"ok": False, "error": "action_plans_disabled"}
    plan_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO eng_action_plans (
          action_plan_id, company_code, campaign_id, title_en, title_ar, source_result_ref, owner_key, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (plan_id, company, campaign_id, title_en, title_ar, source_result_ref, owner_key, _digits(actor_phone)),
    )
    plan = _row(cur)
    items = []
    for a in actions or []:
        item_id = str(uuid.uuid4())
        task_ref = f"hr_task://engagement/action/{item_id}"
        cur.execute(
            """
            INSERT INTO eng_action_items (
              action_item_id, company_code, action_plan_id, title_en, title_ar, owner_key, due_date, shared_task_ref
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING action_item_id, status, shared_task_ref
            """,
            (
                item_id, company, plan_id, a.get("title_en", ""), a.get("title_ar", ""),
                a.get("owner_key", owner_key), a.get("due_date"), task_ref,
            ),
        )
        items.append(_row(cur))
    _emit(
        cur, company=company, fact_type="engagement.action_open", entity_type="action_plan",
        entity_id=plan_id, payload={"campaign_id": campaign_id, "open_items": len(items)},
    )
    return {
        "ok": True,
        "action_plan": plan,
        "items": items,
        "not_er_corrective_action": True,
        "not_performance_development_plan": True,
        "shared_tasks_reused": True,
        "auto_created_er_case": False,
    }


def free_text_access(
    cur: Any, *, company_code: str, campaign_id: str, actor_role: str
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    settings = _settings(cur, company)
    if not settings.get("free_text_enabled", True):
        return {"ok": False, "error": "free_text_disabled"}
    if actor_role not in {"engagement_admin"}:
        return {"ok": False, "error": "free_text_access_denied", "confidential": True}
    cur.execute("SELECT privacy_mode FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur)
    if not camp:
        return {"ok": False, "error": "campaign_not_found"}
    cur.execute(
        """
        SELECT a.answer_id, a.value_text, b.employee_key
          FROM eng_answers a
          JOIN eng_response_batches b ON b.batch_id=a.batch_id
          JOIN eng_questions q ON q.question_id=a.question_id
         WHERE a.company_code=%s AND a.campaign_id=%s AND q.question_type='free_text'
        """,
        (company, campaign_id),
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        if camp["privacy_mode"] == "anonymous":
            d["employee_key"] = None  # never expose
            # Also ensure no system-added identifier in text
        rows.append({"answer_id": str(d["answer_id"]), "value_text": d["value_text"], "employee_key": d.get("employee_key")})
    return {
        "ok": True,
        "items": rows,
        "anonymous_strips_identity": camp["privacy_mode"] == "anonymous",
        "does_not_auto_create_er": True,
    }


def employee_open_surveys(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "engagement_disabled_for_company"}
    cur.execute(
        """
        SELECT i.campaign_id, i.status, c.title_en, c.title_ar, c.privacy_mode, c.closes_at
          FROM eng_invitations i
          JOIN eng_campaigns c ON c.campaign_id=i.campaign_id
         WHERE i.company_code=%s AND i.employee_key=%s AND c.status='launched'
           AND i.status IN ('invited','started')
        """,
        (company, employee_key),
    )
    items = []
    for r in cur.fetchall():
        d = dict(r)
        items.append({
            **{k: d[k] for k in ("campaign_id", "status", "title_en", "title_ar", "privacy_mode", "closes_at")},
            "privacy_mode_label_en": status_label(d["privacy_mode"], lang="en"),
            "privacy_mode_label_ar": status_label(d["privacy_mode"], lang="ar"),
        })
    return {"ok": True, "surveys": items, "company_analytics_included": False}


def assistant_query_engagement(
    cur: Any, *, company_code: str, actor: str, question_kind: str, campaign_id: str | None = None, employee_key: str | None = None
) -> dict[str, Any]:
    _ = actor
    if question_kind == "open_surveys" and employee_key:
        view = employee_open_surveys(cur, company_code=company_code, employee_key=employee_key)
        return {"ok": True, "mutations": False, "surveys": view.get("surveys")}
    if question_kind == "authorized_aggregates" and campaign_id:
        agg = compute_aggregates(cur, company_code=company_code, campaign_id=campaign_id, actor_role="engagement_admin")
        if agg.get("suppressed"):
            return {"ok": True, "mutations": False, "suppressed": True, "scores": None}
        return {"ok": True, "mutations": False, "suppressed": False, "scores": agg.get("scores"), "enps": agg.get("enps")}
    if question_kind in {"identify_respondent", "expose_suppressed", "submit_response", "mutate_campaign", "fake_score"}:
        return {"ok": False, "error": "mutation_or_privacy_forbidden", "mutations": False}
    return {"ok": False, "error": "unsupported_or_forbidden", "mutations": False}


def _notify_dedupe(cur: Any, *, company: str, key: str) -> dict[str, Any]:
    dedupe_key = f"{company}:{key}"
    sp = f"eng_nd_{uuid.uuid4().hex[:12]}"
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(
            "INSERT INTO eng_notification_dedupe (dedupe_key, company_code) VALUES (%s,%s)",
            (dedupe_key, company),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": True, "deduped": False, "answers_not_in_payload": True}
    except Exception:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": False, "deduped": True, "answers_not_in_payload": True}


def close_campaign(cur: Any, *, company_code: str, actor_phone: str, campaign_id: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        UPDATE eng_campaigns SET status='closed', closed_at=now(), updated_at=now()
         WHERE company_code=%s AND campaign_id=%s RETURNING *
        """,
        (company, campaign_id),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="close", entity_type="campaign", entity_id=campaign_id)
    return {"ok": True, "campaign": row}
