"""Wave 6 C1 — Job Architecture / Grades foundation (platform capability).

Shared versioned authority:
  job family → job function → job profile → grade → level → career relationships

References (does not duplicate) canonical org/position/employment truth.
Not a separate customer SKU. Comp Planning + Workforce Planning HARD-depend later.
Salary bands OUT (Comp Planning). Assistant mutations OUT.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

PHASE = "job_architecture_c1"
CONTRACT_VERSION = "job_architecture_c1_v1"
PASS_STAMP = "JOB_ARCHITECTURE_FULL_PASS"
PLATFORM_CAPABILITY_KEY = "job_architecture"
COMMERCIAL_SKU = False  # shared internal/platform capability
FLAG = "WATHEFNI_JOB_ARCHITECTURE_C1"
COMPANIES_FLAG = "WATHEFNI_JOB_ARCHITECTURE_COMPANIES"
_ON = {"1", "true", "yes", "on"}

CATALOG_STATUSES = ("draft", "published", "retired")
CAREER_EDGE_TYPES = ("promotion", "lateral", "specialist", "manager")
LEGACY_MATCH_KINDS = ("deterministic_unique", "unmapped_ambiguous", "unmapped_none", "manual")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "published": {"en": "Published", "ar": "منشور"},
    "retired": {"en": "Retired", "ar": "متقاعد"},
    "promotion": {"en": "Promotion", "ar": "ترقية"},
    "lateral": {"en": "Lateral", "ar": "أفقي"},
    "specialist": {"en": "Specialist", "ar": "تخصصي"},
    "manager": {"en": "Manager track", "ar": "مسار إداري"},
    "mapped": {"en": "Mapped", "ar": "مربوط"},
    "unmapped": {"en": "Unmapped", "ar": "غير مربوط"},
    "job_architecture": {"en": "Job Architecture", "ar": "هيكل الوظائف"},
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


def _norm_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "platform_capability_key": PLATFORM_CAPABILITY_KEY,
        "commercial_sku": COMMERCIAL_SKU,
        "not_separate_customer_sku": True,
        "runs_independently": True,
        "comp_planning_hard_depends": True,
        "workforce_planning_hard_depends": True,
        "other_integrations_optional": True,
        "recruiting_job_is_not_ja_profile": True,
        "talent_critical_role_is_not_ja_catalog": True,
        "org_position_is_not_reusable_job_profile": True,
        "salary_bands_out_of_c1": True,
        "no_fuzzy_ai_migration": True,
        "career_edges_are_not_eligibility": True,
        "no_employee_eligibility_scoring": True,
        "assistant_mutations": False,
        "emits_typed_facts_not_analytics_engine": True,
        "legacy_raw_preserved": True,
        "ja_off_preserves_legacy_text": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def future_hard_contracts() -> dict[str, Any]:
    """Document HARD contracts Comp Planning / Workforce Planning will require."""
    return {
        "compensation_planning": {
            "hard": True,
            "requires": ["published_grades", "published_levels_optional", "job_profile_refs_optional"],
            "owns_salary_bands": True,
            "ja_does_not_own_bands": True,
            "apply_path": "explicit_handoff_not_silent_mutation",
        },
        "workforce_planning": {
            "hard": True,
            "requires": ["published_job_profiles", "published_grades_optional"],
            "planned_seats_ref_ja_profile": True,
            "truth_planes": ["actual", "plan", "scenario", "approved_execution"],
            "draft_requisition_handoff_only": True,
        },
        "talent_optional_ref": {
            "hard": False,
            "critical_role_may_ref_job_profile_id": True,
            "does_not_create_second_catalog": True,
        },
        "recruiting_optional_ref": {
            "hard": False,
            "opening_may_ref_job_profile_id": True,
            "opening_is_not_ja_profile": True,
        },
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "job_architecture_c1_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "job_architecture_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Job Architecture allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "job_architecture_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_job_architecture_c1_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ja_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          migration_mode text NOT NULL DEFAULT 'non_destructive',
          allow_optional_talent_ref boolean NOT NULL DEFAULT true,
          allow_optional_recruiting_ref boolean NOT NULL DEFAULT true,
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
        CREATE TABLE IF NOT EXISTS ja_job_family (
          family_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          description_en text NOT NULL DEFAULT '',
          description_ar text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          retired_at timestamptz,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_job_function (
          function_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          family_id uuid NOT NULL REFERENCES ja_job_family(family_id),
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          description_en text NOT NULL DEFAULT '',
          description_ar text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          retired_at timestamptz,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_job_profile (
          profile_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          function_id uuid NOT NULL REFERENCES ja_job_function(function_id),
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          description_en text NOT NULL DEFAULT '',
          description_ar text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          default_grade_id uuid,
          default_level_id uuid,
          retired_at timestamptz,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_grade (
          grade_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          rank_order int NOT NULL DEFAULT 0,
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          retired_at timestamptz,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_level (
          level_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          grade_id uuid REFERENCES ja_grade(grade_id),
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          rank_order int NOT NULL DEFAULT 0,
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          retired_at timestamptz,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_career_edge (
          edge_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          edge_type text NOT NULL,
          from_profile_id uuid REFERENCES ja_job_profile(profile_id),
          to_profile_id uuid REFERENCES ja_job_profile(profile_id),
          from_grade_id uuid REFERENCES ja_grade(grade_id),
          to_grade_id uuid REFERENCES ja_grade(grade_id),
          optional_requirements jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          notes_en text NOT NULL DEFAULT '',
          notes_ar text NOT NULL DEFAULT '',
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (edge_type IN ('promotion','lateral','specialist','manager')),
          CHECK (from_profile_id IS NOT NULL OR from_grade_id IS NOT NULL),
          CHECK (to_profile_id IS NOT NULL OR to_grade_id IS NOT NULL)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_employment_assignment (
          assignment_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          employment_period_key text,
          profile_id uuid REFERENCES ja_job_profile(profile_id),
          grade_id uuid REFERENCES ja_grade(grade_id),
          level_id uuid REFERENCES ja_level(level_id),
          effective_start date NOT NULL,
          effective_end date,
          superseded_by uuid,
          source_authority text NOT NULL DEFAULT 'job_architecture_c1',
          reason text NOT NULL DEFAULT '',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_org_position_link (
          link_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          org_position_ref text NOT NULL,
          profile_id uuid NOT NULL REFERENCES ja_job_profile(profile_id),
          effective_start date NOT NULL,
          effective_end date,
          superseded_by uuid,
          reason text NOT NULL DEFAULT '',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, org_position_ref, effective_start)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_optional_external_ref (
          ref_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          domain text NOT NULL,
          external_key text NOT NULL,
          profile_id uuid REFERENCES ja_job_profile(profile_id),
          grade_id uuid REFERENCES ja_grade(grade_id),
          note text NOT NULL DEFAULT '',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, domain, external_key),
          CHECK (domain IN ('talent_critical_role','recruiting_opening'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_legacy_mapping (
          mapping_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          raw_field text NOT NULL,
          raw_value text NOT NULL,
          raw_normalized text NOT NULL,
          match_kind text NOT NULL,
          mapped_entity_type text,
          mapped_entity_id uuid,
          provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, raw_field, raw_normalized),
          CHECK (match_kind IN ('deterministic_unique','unmapped_ambiguous','unmapped_none','manual'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_wave5_fact_outbox (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          truth_plane text NOT NULL DEFAULT 'actual',
          emitted_at timestamptz NOT NULL DEFAULT now(),
          source_authority text NOT NULL DEFAULT 'job_architecture_c1'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ja_audit_events (
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
    ):
        cur.execute(ddl)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ja_employment_assignment_emp ON ja_employment_assignment (company_code, employee_key, effective_start)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ja_legacy_mapping_company ON ja_legacy_mapping (company_code, match_kind)"
    )


def _audit(cur: Any, *, company: str, actor: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO ja_audit_events (event_id, company_code, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, _digits(actor), action, entity_type, entity_id, json.dumps(detail or {})),
    )


def enable_company_job_architecture(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        INSERT INTO ja_company_settings (
          company_code, enabled, migration_mode, enabled_by_phone, enabled_reason, enabled_at, disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,'non_destructive',%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true, enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (company, _digits(actor_phone), str(reason).strip()[:500], _digits(actor_phone)),
    )
    row = dict(cur.fetchone())
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company)}


def disable_company_job_architecture(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        UPDATE ja_company_settings
           SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now(),
               metadata = metadata || jsonb_build_object('last_disable_reason', %s::text)
         WHERE company_code=%s
        RETURNING *
        """,
        (_digits(actor_phone), str(reason or "")[:500], company),
    )
    row = cur.fetchone()
    _audit(cur, company=company, actor=actor_phone, action="disable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": dict(row) if row else None, "history_retained": True}


def module_enabled_for_company(cur: Any, company_code: str) -> bool:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return False
    ensure_job_architecture_c1_schema(cur)
    cur.execute("SELECT enabled FROM ja_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "job_architecture_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def _emit_fact(
    cur: Any,
    *,
    company: str,
    fact_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO ja_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, payload, truth_plane)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb,'actual')
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, json.dumps(payload)),
    )


# ---------- catalog upserts ----------

def upsert_job_family(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    name_en: str,
    name_ar: str,
    status: str = "draft",
    description_en: str = "",
    description_ar: str = "",
    reason: str = "upsert family",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    st = str(status or "draft").lower()
    if st not in CATALOG_STATUSES:
        return {"ok": False, "error": "invalid_status"}
    code_n = str(code or "").strip()
    if not code_n or not name_en.strip() or not name_ar.strip():
        return {"ok": False, "error": "code_and_bilingual_names_required"}
    cur.execute("SELECT * FROM ja_job_family WHERE company_code=%s AND code=%s", (company, code_n))
    existing = _row(cur)
    if existing:
        new_version = int(existing["effective_version"]) + (
            1 if (existing["name_en"] != name_en or existing["name_ar"] != name_ar or existing["status"] != st) else 0
        )
        cur.execute(
            """
            UPDATE ja_job_family SET name_en=%s, name_ar=%s, description_en=%s, description_ar=%s,
              status=%s, effective_version=%s, updated_by_phone=%s, updated_at=now(),
              retired_at=CASE WHEN %s='retired' THEN COALESCE(retired_at, now()) ELSE NULL END
             WHERE family_id=%s RETURNING *
            """,
            (
                name_en.strip(), name_ar.strip(), description_en, description_ar, st, new_version,
                _digits(actor_phone), st, str(existing["family_id"]),
            ),
        )
        row = _row(cur)
    else:
        family_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ja_job_family (
              family_id, company_code, code, name_en, name_ar, description_en, description_ar,
              status, effective_version, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s) RETURNING *
            """,
            (
                family_id, company, code_n, name_en.strip(), name_ar.strip(), description_en, description_ar,
                st, _digits(actor_phone), _digits(actor_phone),
            ),
        )
        row = _row(cur)
    assert row
    _audit(cur, company=company, actor=actor_phone, action="upsert_family", entity_type="job_family", entity_id=str(row["family_id"]), detail={"reason": reason, "code": code_n})
    _emit_fact(cur, company=company, fact_type="job_architecture.family", entity_type="job_family", entity_id=str(row["family_id"]), payload={"code": code_n, "status": st, "version": row["effective_version"]})
    return {"ok": True, "family": row, "stable_id": str(row["family_id"])}


def upsert_job_function(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    family_id: str,
    code: str,
    name_en: str,
    name_ar: str,
    status: str = "draft",
    reason: str = "upsert function",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT family_id FROM ja_job_family WHERE company_code=%s AND family_id=%s", (company, family_id))
    if not cur.fetchone():
        return {"ok": False, "error": "family_not_found"}
    code_n = str(code or "").strip()
    st = str(status or "draft").lower()
    if st not in CATALOG_STATUSES or not code_n or not name_en.strip() or not name_ar.strip():
        return {"ok": False, "error": "invalid_function_payload"}
    cur.execute("SELECT * FROM ja_job_function WHERE company_code=%s AND code=%s", (company, code_n))
    existing = _row(cur)
    if existing:
        ver = int(existing["effective_version"]) + 1
        cur.execute(
            """
            UPDATE ja_job_function SET family_id=%s, name_en=%s, name_ar=%s, status=%s, effective_version=%s,
              updated_by_phone=%s, updated_at=now()
             WHERE function_id=%s RETURNING *
            """,
            (family_id, name_en.strip(), name_ar.strip(), st, ver, _digits(actor_phone), str(existing["function_id"])),
        )
        row = _row(cur)
    else:
        function_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ja_job_function (
              function_id, company_code, family_id, code, name_en, name_ar, status, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (function_id, company, family_id, code_n, name_en.strip(), name_ar.strip(), st, _digits(actor_phone), _digits(actor_phone)),
        )
        row = _row(cur)
    assert row
    _audit(cur, company=company, actor=actor_phone, action="upsert_function", entity_type="job_function", entity_id=str(row["function_id"]), detail={"reason": reason})
    return {"ok": True, "function": row, "stable_id": str(row["function_id"])}


def upsert_grade(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    name_en: str,
    name_ar: str,
    rank_order: int = 0,
    status: str = "draft",
    reason: str = "upsert grade",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    code_n = str(code or "").strip()
    st = str(status or "draft").lower()
    if st not in CATALOG_STATUSES or not code_n or not name_en.strip() or not name_ar.strip():
        return {"ok": False, "error": "invalid_grade_payload"}
    cur.execute("SELECT * FROM ja_grade WHERE company_code=%s AND code=%s", (company, code_n))
    existing = _row(cur)
    if existing:
        ver = int(existing["effective_version"]) + 1
        cur.execute(
            """
            UPDATE ja_grade SET name_en=%s, name_ar=%s, rank_order=%s, status=%s, effective_version=%s,
              updated_by_phone=%s, updated_at=now()
             WHERE grade_id=%s RETURNING *
            """,
            (name_en.strip(), name_ar.strip(), int(rank_order), st, ver, _digits(actor_phone), str(existing["grade_id"])),
        )
        row = _row(cur)
    else:
        grade_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ja_grade (
              grade_id, company_code, code, name_en, name_ar, rank_order, status, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (grade_id, company, code_n, name_en.strip(), name_ar.strip(), int(rank_order), st, _digits(actor_phone), _digits(actor_phone)),
        )
        row = _row(cur)
    assert row
    _audit(cur, company=company, actor=actor_phone, action="upsert_grade", entity_type="grade", entity_id=str(row["grade_id"]), detail={"reason": reason})
    _emit_fact(cur, company=company, fact_type="job_architecture.grade", entity_type="grade", entity_id=str(row["grade_id"]), payload={"code": code_n, "status": st, "version": row["effective_version"]})
    return {"ok": True, "grade": row, "stable_id": str(row["grade_id"]), "salary_bands_not_in_c1": True}


def upsert_level(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    name_en: str,
    name_ar: str,
    grade_id: str | None = None,
    rank_order: int = 0,
    status: str = "draft",
    reason: str = "upsert level",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    code_n = str(code or "").strip()
    st = str(status or "draft").lower()
    if st not in CATALOG_STATUSES or not code_n or not name_en.strip() or not name_ar.strip():
        return {"ok": False, "error": "invalid_level_payload"}
    if grade_id:
        cur.execute("SELECT grade_id FROM ja_grade WHERE company_code=%s AND grade_id=%s", (company, grade_id))
        if not cur.fetchone():
            return {"ok": False, "error": "grade_not_found"}
    cur.execute("SELECT * FROM ja_level WHERE company_code=%s AND code=%s", (company, code_n))
    existing = _row(cur)
    if existing:
        ver = int(existing["effective_version"]) + 1
        cur.execute(
            """
            UPDATE ja_level SET grade_id=%s, name_en=%s, name_ar=%s, rank_order=%s, status=%s, effective_version=%s,
              updated_by_phone=%s, updated_at=now()
             WHERE level_id=%s RETURNING *
            """,
            (grade_id, name_en.strip(), name_ar.strip(), int(rank_order), st, ver, _digits(actor_phone), str(existing["level_id"])),
        )
        row = _row(cur)
    else:
        level_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ja_level (
              level_id, company_code, grade_id, code, name_en, name_ar, rank_order, status, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (level_id, company, grade_id, code_n, name_en.strip(), name_ar.strip(), int(rank_order), st, _digits(actor_phone), _digits(actor_phone)),
        )
        row = _row(cur)
    assert row
    _audit(cur, company=company, actor=actor_phone, action="upsert_level", entity_type="level", entity_id=str(row["level_id"]), detail={"reason": reason})
    return {"ok": True, "level": row, "stable_id": str(row["level_id"])}


def upsert_job_profile(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    function_id: str,
    code: str,
    name_en: str,
    name_ar: str,
    status: str = "draft",
    default_grade_id: str | None = None,
    default_level_id: str | None = None,
    description_en: str = "",
    description_ar: str = "",
    reason: str = "upsert profile",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT function_id FROM ja_job_function WHERE company_code=%s AND function_id=%s", (company, function_id))
    if not cur.fetchone():
        return {"ok": False, "error": "function_not_found"}
    code_n = str(code or "").strip()
    st = str(status or "draft").lower()
    if st not in CATALOG_STATUSES or not code_n or not name_en.strip() or not name_ar.strip():
        return {"ok": False, "error": "invalid_profile_payload"}
    cur.execute("SELECT * FROM ja_job_profile WHERE company_code=%s AND code=%s", (company, code_n))
    existing = _row(cur)
    if existing:
        ver = int(existing["effective_version"]) + 1
        profile_id = str(existing["profile_id"])
        cur.execute(
            """
            UPDATE ja_job_profile SET function_id=%s, name_en=%s, name_ar=%s, description_en=%s, description_ar=%s,
              status=%s, effective_version=%s, default_grade_id=%s, default_level_id=%s,
              updated_by_phone=%s, updated_at=now()
             WHERE profile_id=%s RETURNING *
            """,
            (
                function_id, name_en.strip(), name_ar.strip(), description_en, description_ar, st, ver,
                default_grade_id, default_level_id, _digits(actor_phone), profile_id,
            ),
        )
        row = _row(cur)
    else:
        profile_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ja_job_profile (
              profile_id, company_code, function_id, code, name_en, name_ar, description_en, description_ar,
              status, default_grade_id, default_level_id, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                profile_id, company, function_id, code_n, name_en.strip(), name_ar.strip(), description_en, description_ar,
                st, default_grade_id, default_level_id, _digits(actor_phone), _digits(actor_phone),
            ),
        )
        row = _row(cur)
    assert row
    _audit(cur, company=company, actor=actor_phone, action="upsert_profile", entity_type="job_profile", entity_id=str(row["profile_id"]), detail={"reason": reason})
    _emit_fact(
        cur,
        company=company,
        fact_type="job_architecture.job_profile",
        entity_type="job_profile",
        entity_id=str(row["profile_id"]),
        payload={"code": code_n, "status": st, "version": row["effective_version"], "not_recruiting_job": True, "not_org_position": True},
    )
    return {
        "ok": True,
        "profile": row,
        "stable_id": str(row["profile_id"]),
        "boundaries": {
            "recruiting_job_is_not_ja_profile": True,
            "org_position_is_not_reusable_job_profile": True,
            "talent_critical_role_is_not_ja_catalog": True,
        },
    }


def create_career_edge(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    edge_type: str,
    from_profile_id: str | None = None,
    to_profile_id: str | None = None,
    from_grade_id: str | None = None,
    to_grade_id: str | None = None,
    optional_requirements: dict | None = None,
    status: str = "published",
    notes_en: str = "",
    notes_ar: str = "",
    reason: str = "create career edge",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    et = str(edge_type or "").lower()
    if et not in CAREER_EDGE_TYPES:
        return {"ok": False, "error": "invalid_edge_type", "allowed": list(CAREER_EDGE_TYPES)}
    if not (from_profile_id or from_grade_id) or not (to_profile_id or to_grade_id):
        return {"ok": False, "error": "edge_endpoints_required"}
    reqs = dict(optional_requirements or {})
    # Allow skill/competency requirement keys only as declarative lists — never eligibility scores
    if "eligibility_score" in reqs or "ai_recommendation" in reqs:
        return {"ok": False, "error": "eligibility_scoring_forbidden"}
    edge_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ja_career_edge (
          edge_id, company_code, edge_type, from_profile_id, to_profile_id, from_grade_id, to_grade_id,
          optional_requirements, status, notes_en, notes_ar, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            edge_id, company, et, from_profile_id, to_profile_id, from_grade_id, to_grade_id,
            json.dumps(reqs), str(status or "published").lower(), notes_en, notes_ar,
            _digits(actor_phone), _digits(actor_phone),
        ),
    )
    row = _row(cur)
    assert row
    _audit(cur, company=company, actor=actor_phone, action="create_career_edge", entity_type="career_edge", entity_id=edge_id, detail={"reason": reason, "edge_type": et})
    return {
        "ok": True,
        "edge": row,
        "is_eligibility": False,
        "employee_auto_eligible": False,
        "ai_recommendations": False,
    }


def assign_employment_architecture(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    effective_start: date | str,
    profile_id: str | None = None,
    grade_id: str | None = None,
    level_id: str | None = None,
    employment_period_key: str | None = None,
    reason: str = "assign architecture",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if not profile_id and not grade_id and not level_id:
        return {"ok": False, "error": "assignment_target_required"}
    start = date.fromisoformat(str(effective_start)) if not isinstance(effective_start, date) else effective_start
    # Supersede open assignments
    cur.execute(
        """
        UPDATE ja_employment_assignment
           SET effective_end=%s, updated_at=now()
         WHERE company_code=%s AND employee_key=%s AND superseded_by IS NULL AND effective_end IS NULL
           AND effective_start <= %s
        RETURNING assignment_id
        """,
        (start, company, employee_key, start),
    )
    prior = [str(dict(r)["assignment_id"]) for r in cur.fetchall()]
    assignment_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ja_employment_assignment (
          assignment_id, company_code, employee_key, employment_period_key, profile_id, grade_id, level_id,
          effective_start, reason, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            assignment_id, company, employee_key, employment_period_key, profile_id, grade_id, level_id,
            start, str(reason)[:500], _digits(actor_phone),
        ),
    )
    row = _row(cur)
    assert row
    if prior:
        cur.execute(
            "UPDATE ja_employment_assignment SET superseded_by=%s WHERE assignment_id = ANY(%s::uuid[])",
            (assignment_id, prior),
        )
    _emit_fact(
        cur,
        company=company,
        fact_type="job_architecture.employment_assignment",
        entity_type="employee",
        entity_id=employee_key,
        payload={
            "assignment_id": assignment_id,
            "profile_id": profile_id,
            "grade_id": grade_id,
            "level_id": level_id,
            "effective_start": str(start),
        },
    )
    return {"ok": True, "assignment": row, "superseded": prior}


def resolve_assignment_as_of(
    cur: Any, *, company_code: str, employee_key: str, as_of: date | str
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    day = date.fromisoformat(str(as_of)) if not isinstance(as_of, date) else as_of
    ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        SELECT * FROM ja_employment_assignment
         WHERE company_code=%s AND employee_key=%s
           AND effective_start <= %s
           AND (effective_end IS NULL OR effective_end >= %s)
         ORDER BY effective_start DESC
         LIMIT 1
        """,
        (company, employee_key, day, day),
    )
    row = _row(cur)
    return {"ok": True, "as_of": str(day), "assignment": row, "reconstructable": True}


def link_org_position(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    org_position_ref: str,
    profile_id: str,
    effective_start: date | str,
    reason: str = "link org position",
) -> dict[str, Any]:
    """Org position references a JA profile — position itself is not the reusable profile."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    start = date.fromisoformat(str(effective_start)) if not isinstance(effective_start, date) else effective_start
    link_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ja_org_position_link (
          link_id, company_code, org_position_ref, profile_id, effective_start, reason, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (link_id, company, str(org_position_ref), profile_id, start, str(reason)[:500], _digits(actor_phone)),
    )
    row = _row(cur)
    return {
        "ok": True,
        "link": row,
        "org_position_is_not_reusable_job_profile": True,
    }


def optional_external_ref(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    domain: str,
    external_key: str,
    profile_id: str | None = None,
    grade_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """OPTIONAL Talent/Recruiting refs — never create dependency or second catalog."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    dom = str(domain or "").strip().lower()
    if dom not in {"talent_critical_role", "recruiting_opening"}:
        return {"ok": False, "error": "invalid_external_domain"}
    ref_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ja_optional_external_ref (
          ref_id, company_code, domain, external_key, profile_id, grade_id, note, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, domain, external_key) DO UPDATE SET
          profile_id=EXCLUDED.profile_id, grade_id=EXCLUDED.grade_id, note=EXCLUDED.note
        RETURNING *
        """,
        (ref_id, company, dom, str(external_key), profile_id, grade_id, note, _digits(actor_phone)),
    )
    row = _row(cur)
    return {
        "ok": True,
        "ref": row,
        "optional": True,
        "hard_dependency": False,
        "boundaries": honesty_payload(company_code=company),
    }


def migrate_legacy_values(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    raw_field: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Non-destructive migration. Auto-map only deterministic unique matches. No fuzzy/AI."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    field = str(raw_field or "").strip()
    if field not in {"grade", "job_title", "job_role"}:
        return {"ok": False, "error": "unsupported_raw_field"}

    # Build deterministic lookup from published grades (for grade field) or profiles (for titles)
    if field == "grade":
        cur.execute(
            "SELECT grade_id, code, name_en, name_ar FROM ja_grade WHERE company_code=%s AND status='published'",
            (company,),
        )
        catalog = [dict(r) for r in cur.fetchall()]
        index: dict[str, list[str]] = {}
        for item in catalog:
            for key in (item["code"], item["name_en"], item["name_ar"]):
                tok = _norm_token(key)
                if tok:
                    index.setdefault(tok, []).append(str(item["grade_id"]))
        entity_type = "grade"
    else:
        cur.execute(
            "SELECT profile_id, code, name_en, name_ar FROM ja_job_profile WHERE company_code=%s AND status='published'",
            (company,),
        )
        catalog = [dict(r) for r in cur.fetchall()]
        index = {}
        for item in catalog:
            for key in (item["code"], item["name_en"], item["name_ar"]):
                tok = _norm_token(key)
                if tok:
                    index.setdefault(tok, []).append(str(item["profile_id"]))
        entity_type = "job_profile"

    results = []
    for cand in candidates:
        raw_value = str(cand.get("raw_value") or "")
        provenance = dict(cand.get("provenance") or {})
        provenance.setdefault("source", cand.get("source") or "legacy")
        provenance["raw_value_preserved"] = raw_value
        tok = _norm_token(raw_value)
        matches = list(dict.fromkeys(index.get(tok) or []))
        if len(matches) == 1:
            kind = "deterministic_unique"
            mapped_id = matches[0]
            mapped_type = entity_type
        elif len(matches) > 1:
            kind = "unmapped_ambiguous"
            mapped_id = None
            mapped_type = None
        else:
            kind = "unmapped_none"
            mapped_id = None
            mapped_type = None
        mapping_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ja_legacy_mapping (
              mapping_id, company_code, raw_field, raw_value, raw_normalized, match_kind,
              mapped_entity_type, mapped_entity_id, provenance, created_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (company_code, raw_field, raw_normalized) DO UPDATE SET
              raw_value=EXCLUDED.raw_value,
              match_kind=EXCLUDED.match_kind,
              mapped_entity_type=EXCLUDED.mapped_entity_type,
              mapped_entity_id=EXCLUDED.mapped_entity_id,
              provenance=EXCLUDED.provenance,
              updated_at=now()
            RETURNING *
            """,
            (
                mapping_id, company, field, raw_value, tok or raw_value, kind,
                mapped_type, mapped_id, json.dumps(provenance), _digits(actor_phone),
            ),
        )
        results.append(dict(cur.fetchone()))
    return {
        "ok": True,
        "mapped": sum(1 for r in results if r["match_kind"] == "deterministic_unique"),
        "unmapped_ambiguous": sum(1 for r in results if r["match_kind"] == "unmapped_ambiguous"),
        "unmapped_none": sum(1 for r in results if r["match_kind"] == "unmapped_none"),
        "results": results,
        "fuzzy_ai_used": False,
        "raw_preserved": True,
    }


def list_catalog(cur: Any, *, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_job_architecture_c1_schema(cur)
    enabled = module_enabled_for_company(cur, company)
    out: dict[str, Any] = {
        "ok": True,
        "company_code": company,
        "enabled": enabled,
        "honesty": honesty_payload(company_code=company),
        "future_hard_contracts": future_hard_contracts(),
    }
    if not enabled:
        out["legacy_text_still_works"] = True
        out["families"] = []
        out["functions"] = []
        out["profiles"] = []
        out["grades"] = []
        out["levels"] = []
        out["career_edges"] = []
        return out
    for key, table in (
        ("families", "ja_job_family"),
        ("functions", "ja_job_function"),
        ("profiles", "ja_job_profile"),
        ("grades", "ja_grade"),
        ("levels", "ja_level"),
        ("career_edges", "ja_career_edge"),
    ):
        cur.execute(f"SELECT * FROM {table} WHERE company_code=%s ORDER BY created_at", (company,))
        out[key] = [dict(r) for r in cur.fetchall()]
    return out


def assistant_explain_profile(cur: Any, *, company_code: str, profile_id: str) -> dict[str, Any]:
    """Read/explain only — no mutations."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "mutations": False}
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "job_architecture_disabled_for_company", "mutations": False}
    cur.execute(
        """
        SELECT p.*, f.code AS function_code, fam.code AS family_code
          FROM ja_job_profile p
          JOIN ja_job_function f ON f.function_id=p.function_id
          JOIN ja_job_family fam ON fam.family_id=f.family_id
         WHERE p.company_code=%s AND p.profile_id=%s
        """,
        (company, profile_id),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "profile_not_found", "mutations": False}
    return {
        "ok": True,
        "mutations": False,
        "explain": {
            "profile_id": str(row["profile_id"]),
            "code": row["code"],
            "name_en": row["name_en"],
            "name_ar": row["name_ar"],
            "family_code": row["family_code"],
            "function_code": row["function_code"],
            "version": row["effective_version"],
            "status": row["status"],
        },
        "deep_link": f"/setup/job-architecture?profile={row['profile_id']}",
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "setup_web": {"primary_authoring": True, "owns_architecture": True},
        "hr_web": {"catalog_read": True, "authoring_via_setup": True},
        "hr_mobile": {"intentionally_thin": True, "no_heavyweight_authoring": True},
        "employee_app": {"no_company_architecture_admin": True},
        "assistant": {"mutations": False, "read_explain_deep_link": True},
    }
