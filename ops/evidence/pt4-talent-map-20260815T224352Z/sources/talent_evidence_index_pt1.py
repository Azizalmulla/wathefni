#!/usr/bin/env python3
"""PT1 overlay — Talent Evidence Index (pointers, not a second SoT).

Indexes canonical evidence by reference with provenance and consume contracts.
Does not classify Talent. Does not write potential, HiPo, or readiness.
AI-SYNTHESIZED is explanatory metadata only and cannot be a classification input.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import performance_goals_c1 as c1
import talent_profile_c5 as c5

PHASE = "talent_evidence_index_pt1"
CONTRACT_VERSION = "talent_evidence_index_pt1_v1"
PASS_STAMP = "PT1_OKR_EVIDENCE_FULL_PASS"

PROVENANCE = (
    "SYSTEM-DERIVED",
    "MANAGER-ASSESSED",
    "HR-ASSESSED",
    "EMPLOYEE-DECLARED",
    "AI-SYNTHESIZED",
)
EVIDENCE_KINDS = (
    "okr",
    "review_outcome",
    "skill",
    "competency",
    "potential",
    "certification",
    "assignment",
    "assessment",
    "development",
    "aspiration",
    "nomination",
    "explanation",
)
CONSUME_CONTRACTS = (
    "okr_as_talent_evidence_v1",
    "performance_outcome_as_evidence_v1",
    "learning_cert_as_evidence_v1",
    "learning_completion_as_evidence_v1",
    "ja_assignment_as_evidence_v1",
    "recruiting_import_at_hire_v1",
    "assessment_as_evidence_v1",
    "claimed_skill_display_v1",
)
CROSS_MODULE_CONTRACTS = (
    "okr_as_talent_evidence_v1",
    "performance_outcome_as_evidence_v1",
    "learning_cert_as_evidence_v1",
    "learning_completion_as_evidence_v1",
    "ja_assignment_as_evidence_v1",
    "recruiting_import_at_hire_v1",
    "assessment_as_evidence_v1",
)

STATUS_LABELS = {
    "okr_as_talent_evidence_v1": {
        "en": "OKRs as Talent evidence",
        "ar": "النتائج الرئيسية كدليل مواهب",
    },
    "SYSTEM-DERIVED": {"en": "System-derived", "ar": "مشتق من النظام"},
    "MANAGER-ASSESSED": {"en": "Manager-assessed", "ar": "تقييم المدير"},
    "HR-ASSESSED": {"en": "HR-assessed", "ar": "تقييم الموارد البشرية"},
    "EMPLOYEE-DECLARED": {"en": "Employee-declared", "ar": "تصريح الموظف"},
    "AI-SYNTHESIZED": {"en": "AI-synthesized (explanation only)", "ar": "توليد الذكاء (شرح فقط)"},
    "claimed": {"en": "Claimed (not verified)", "ar": "مُدّعى (غير موثّق)"},
    "insufficient_permission": {"en": "Evidence exists but is not visible", "ar": "الدليل موجود وغير ظاهر"},
}


def company_code_norm(company_code: str | None) -> str:
    return c5.company_code_norm(company_code)


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "pointer_not_second_sot": True,
        "no_universal_talent_score": True,
        "no_talent_classification_in_pt1": True,
        "ai_synthesized_not_classification_input": True,
        "contradictions_coexist": True,
        "consume_contracts_default_off": True,
        "okr_completion_is_not_quality": True,
        "okr_is_not_potential": True,
        "okr_is_not_hipo": True,
        "okr_is_not_readiness": True,
        "claimed_skill_is_not_verified": True,
        "no_second_analytics_engine": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def _row(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        return {}


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payload_hash(*, source_authority: str, source_id: str, source_version: Any, marker: Any) -> str:
    raw = json.dumps(
        {
            "authority": source_authority,
            "id": str(source_id),
            "version": source_version,
            "marker": marker,
        },
        default=str,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def default_consume_contracts() -> dict[str, bool]:
    return {key: False for key in CROSS_MODULE_CONTRACTS} | {"claimed_skill_display_v1": True}


def ensure_talent_evidence_index_pt1_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c5.ensure_talent_profile_c5_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_evidence_index_pt1_company_settings (
          company_code text PRIMARY KEY,
          consume_contracts jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_evidence_refs (
          evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          source_module text NOT NULL,
          source_authority text NOT NULL,
          source_id text NOT NULL,
          source_version text NOT NULL DEFAULT '1',
          as_of timestamptz NOT NULL DEFAULT now(),
          evidence_kind text NOT NULL,
          provenance_class text NOT NULL,
          consume_contract text NOT NULL,
          payload_hash text NOT NULL,
          permission_class text NOT NULL DEFAULT 'talent.read',
          claimed_not_verified boolean NOT NULL DEFAULT false,
          classification_input_eligible boolean NOT NULL DEFAULT false,
          retired_at timestamptz,
          inaccessible boolean NOT NULL DEFAULT false,
          source_module_disabled boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE (company_code, source_authority, source_id, source_version, employee_key),
          CONSTRAINT ter_kind_chk CHECK (evidence_kind IN (
            'okr','review_outcome','skill','competency','potential','certification',
            'assignment','assessment','development','aspiration','nomination','explanation'
          )),
          CONSTRAINT ter_prov_chk CHECK (provenance_class IN (
            'SYSTEM-DERIVED','MANAGER-ASSESSED','HR-ASSESSED','EMPLOYEE-DECLARED','AI-SYNTHESIZED'
          )),
          CONSTRAINT ter_ai_not_input_chk CHECK (
            provenance_class <> 'AI-SYNTHESIZED' OR classification_input_eligible = false
          ),
          CONSTRAINT ter_no_copied_rating_chk CHECK (
            (metadata->>'copied_canonical_rating') IS NULL
          )
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_evidence_index_pt1_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          action text NOT NULL,
          actor_phone text,
          reason text,
          subject_type text,
          subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS ter_emp_idx
          ON talent_evidence_refs(company_code, employee_key, consume_contract)
        """
    )


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str | None,
    reason: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO talent_evidence_index_pt1_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code,
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            str(subject_id) if subject_id else None,
            json.dumps(payload or {}, default=str),
        ),
    )


def get_consume_contracts(cur: Any, company_code: str | None) -> dict[str, bool]:
    ensure_talent_evidence_index_pt1_schema(cur)
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT consume_contracts FROM talent_evidence_index_pt1_company_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    stored = {}
    if row:
        raw = _row(row).get("consume_contracts") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if isinstance(raw, dict):
            stored = raw
    out = default_consume_contracts()
    for key, value in stored.items():
        if key in out:
            out[key] = bool(value)
    # Existing frozen Performance evidence opt-in (C5 setting) is the PT0 exception.
    settings = c5.get_company_settings(cur, company) or {}
    if settings.get("performance_evidence_consume"):
        out["performance_outcome_as_evidence_v1"] = True
    return out


def contract_enabled(cur: Any, company_code: str, contract: str) -> bool:
    return bool(get_consume_contracts(cur, company_code).get(contract))


def set_consume_contracts(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    contracts: dict[str, Any],
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    entitled = c5.runtime_gate_for_company(company_code)
    if not entitled.get("ok"):
        return entitled
    company = company_code_norm(company_code)
    current = get_consume_contracts(cur, company)
    for key, value in (contracts or {}).items():
        if key not in CONSUME_CONTRACTS:
            return {"ok": False, "error": "unknown_consume_contract", "allowed": list(CONSUME_CONTRACTS)}
        current[key] = bool(value)
    current["claimed_skill_display_v1"] = True
    ensure_talent_evidence_index_pt1_schema(cur)
    cur.execute(
        """
        INSERT INTO talent_evidence_index_pt1_company_settings (
          company_code, consume_contracts, updated_by_phone, updated_at
        ) VALUES (%s,%s::jsonb,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          consume_contracts=EXCLUDED.consume_contracts,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (company, json.dumps(current), _digits(actor_phone)),
    )
    row = _row(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="consume_contracts_set",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload=current,
    )
    return {
        "ok": True,
        "settings": row,
        "consume_contracts": current,
        "potential_mutated": False,
        "hipo_mutated": False,
        "readiness_mutated": False,
        **honesty_payload(company_code=company),
    }


def sync_from_setup(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    overlay: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    if "okr_as_talent_evidence" in overlay:
        contracts["okr_as_talent_evidence_v1"] = bool(overlay.get("okr_as_talent_evidence"))
    if "performance_evidence_consume" in overlay:
        contracts["performance_outcome_as_evidence_v1"] = bool(overlay.get("performance_evidence_consume"))
    if not contracts:
        return {"ok": True, "synced": False, **honesty_payload(company_code=company_code)}
    return set_consume_contracts(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason, contracts=contracts
    )


def index_ref(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    source_module: str,
    source_authority: str,
    source_id: str,
    source_version: Any,
    evidence_kind: str,
    provenance_class: str,
    consume_contract: str,
    actor_phone: str | None = None,
    reason: str = "index evidence",
    as_of: datetime | None = None,
    permission_class: str = "talent.read",
    claimed_not_verified: bool = False,
    marker: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if evidence_kind not in EVIDENCE_KINDS:
        return {"ok": False, "error": "invalid_evidence_kind", "allowed": list(EVIDENCE_KINDS)}
    if provenance_class not in PROVENANCE:
        return {"ok": False, "error": "invalid_provenance", "allowed": list(PROVENANCE)}
    if consume_contract not in CONSUME_CONTRACTS and consume_contract != "talent_native_v1":
        return {"ok": False, "error": "unknown_consume_contract"}
    if provenance_class == "AI-SYNTHESIZED" and evidence_kind != "explanation":
        return {"ok": False, "error": "ai_synthesized_explanation_only"}
    company = company_code_norm(company_code)
    ensure_talent_evidence_index_pt1_schema(cur)
    version = str(source_version or "1")
    digest = payload_hash(
        source_authority=source_authority,
        source_id=str(source_id),
        source_version=version,
        marker=marker,
    )
    classification_eligible = provenance_class != "AI-SYNTHESIZED" and not claimed_not_verified
    meta = dict(metadata or {})
    meta.pop("copied_canonical_rating", None)
    cur.execute(
        """
        INSERT INTO talent_evidence_refs (
          company_code, employee_key, source_module, source_authority, source_id,
          source_version, as_of, evidence_kind, provenance_class, consume_contract,
          payload_hash, permission_class, claimed_not_verified, classification_input_eligible,
          metadata
        ) VALUES (
          %s,%s,%s,%s,%s,%s,COALESCE(%s, now()),%s,%s,%s,%s,%s,%s,%s,%s::jsonb
        )
        ON CONFLICT (company_code, source_authority, source_id, source_version, employee_key)
        DO UPDATE SET
          payload_hash=EXCLUDED.payload_hash,
          as_of=EXCLUDED.as_of,
          inaccessible=false
        RETURNING *, (xmax = 0) AS inserted
        """,
        (
            company,
            str(employee_key),
            source_module,
            source_authority,
            str(source_id),
            version,
            as_of,
            evidence_kind,
            provenance_class,
            consume_contract,
            digest,
            permission_class,
            bool(claimed_not_verified),
            bool(classification_eligible),
            json.dumps(meta, default=str),
        ),
    )
    row = _row(cur.fetchone())
    inserted = bool(row.pop("inserted", False)) if "inserted" in row else True
    _audit(
        cur,
        company_code=company,
        action="evidence_indexed" if inserted else "evidence_index_idempotent",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="evidence_ref",
        subject_id=str(row.get("evidence_id")),
        payload={"source_id": str(source_id), "idempotent": not inserted},
    )
    return {
        "ok": True,
        "evidence": row,
        "idempotent": not inserted,
        "copied_canonical_rating": False,
        "potential_mutated": False,
        "hipo_mutated": False,
        "readiness_mutated": False,
        **honesty_payload(company_code=company),
    }


def index_okr_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    objective_id: str | None = None,
    key_result_id: str | None = None,
    reason: str = "index okr evidence",
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not contract_enabled(cur, company, "okr_as_talent_evidence_v1"):
        return {
            "ok": False,
            "error": "okr_as_talent_evidence_v1_off",
            "consumed": False,
            **honesty_payload(company_code=company),
        }
    if key_result_id:
        cur.execute(
            """
            SELECT kr.*, o.owner_employee_key, o.period_start, o.period_end, o.objective_id,
                   kr.row_version
              FROM perf_key_results kr
              JOIN perf_objectives o ON o.objective_id=kr.objective_id
             WHERE kr.company_code=%s AND kr.key_result_id=%s
            """,
            (company, key_result_id),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "key_result_not_found"}
        item = _row(row)
        employee = str(item.get("owner_employee_key") or "")
        if not employee:
            return {"ok": False, "error": "okr_owner_required"}
        marker = {
            "current_value": item.get("current_value"),
            "status": item.get("status"),
            "period_start": str(item.get("period_start") or ""),
            "period_end": str(item.get("period_end") or ""),
        }
        return index_ref(
            cur,
            company_code=company,
            employee_key=employee,
            source_module="performance",
            source_authority="perf_key_results",
            source_id=str(key_result_id),
            source_version=item.get("row_version") or 1,
            evidence_kind="okr",
            provenance_class="SYSTEM-DERIVED",
            consume_contract="okr_as_talent_evidence_v1",
            actor_phone=actor_phone,
            reason=reason,
            permission_class="performance.read",
            marker=marker,
            metadata={"period_start": marker["period_start"], "period_end": marker["period_end"]},
        )
    if not objective_id:
        return {"ok": False, "error": "objective_or_key_result_required"}
    cur.execute(
        "SELECT * FROM perf_objectives WHERE company_code=%s AND objective_id=%s",
        (company, objective_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "objective_not_found"}
    item = _row(row)
    employee = str(item.get("owner_employee_key") or "")
    if not employee:
        return {"ok": False, "error": "okr_owner_required"}
    rollup = c1.objective_rollup(cur, company_code=company, objective_id=str(objective_id))
    marker = {
        "status": item.get("status"),
        "progress_pct": rollup.get("progress_pct"),
        "formula_version": rollup.get("formula_version"),
    }
    return index_ref(
        cur,
        company_code=company,
        employee_key=employee,
        source_module="performance",
        source_authority="perf_objectives",
        source_id=str(objective_id),
        source_version=item.get("row_version") or 1,
        evidence_kind="okr",
        provenance_class="SYSTEM-DERIVED",
        consume_contract="okr_as_talent_evidence_v1",
        actor_phone=actor_phone,
        reason=reason,
        permission_class="performance.read",
        marker=marker,
        metadata={"period_start": str(item.get("period_start") or ""), "period_end": str(item.get("period_end") or "")},
    )


def index_claimed_skill(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    skill_id: str,
    actor_phone: str,
    reason: str = "index claimed skill",
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT * FROM talent_skills
         WHERE company_code=%s AND employee_key=%s AND skill_id=%s
        """,
        (company, employee_key, skill_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "skill_not_found"}
    skill = _row(row)
    claimed = str(skill.get("state") or "") == "claimed"
    return index_ref(
        cur,
        company_code=company,
        employee_key=employee_key,
        source_module="talent",
        source_authority="talent_skills",
        source_id=str(skill_id),
        source_version=skill.get("version") or 1,
        evidence_kind="skill",
        provenance_class="EMPLOYEE-DECLARED" if claimed else "HR-ASSESSED",
        consume_contract="claimed_skill_display_v1" if claimed else "talent_native_v1",
        actor_phone=actor_phone,
        reason=reason,
        claimed_not_verified=claimed,
        marker={"state": skill.get("state"), "skill_code": skill.get("skill_code")},
        metadata={"skill_code": skill.get("skill_code"), "claimed_not_verified": claimed},
    )


def index_potential_assessment(
    cur: Any,
    *,
    company_code: str,
    assessment_id: str,
    actor_phone: str,
    reason: str = "index potential",
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM talent_potential_assessments WHERE company_code=%s AND assessment_id=%s",
        (company, assessment_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "potential_assessment_not_found"}
    item = _row(row)
    role = str(item.get("assessor_role") or "hr")
    provenance = "MANAGER-ASSESSED" if role == "manager" else "HR-ASSESSED"
    return index_ref(
        cur,
        company_code=company,
        employee_key=str(item.get("employee_key")),
        source_module="talent",
        source_authority="talent_potential_assessments",
        source_id=str(assessment_id),
        source_version=item.get("version") or 1,
        evidence_kind="potential",
        provenance_class=provenance,
        consume_contract="talent_native_v1",
        actor_phone=actor_phone,
        reason=reason,
        permission_class="talent.sensitive",
        marker={"resulting_level": item.get("resulting_level"), "status": item.get("status")},
    )


def mark_source_module_disabled(cur: Any, *, company_code: str, source_module: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_talent_evidence_index_pt1_schema(cur)
    cur.execute(
        """
        UPDATE talent_evidence_refs
           SET source_module_disabled=true
         WHERE company_code=%s AND source_module=%s
        """,
        (company, source_module),
    )
    return {"ok": True, "history_preserved": True, "hard_deleted": False, **honesty_payload(company_code=company)}


def _source_still_readable(
    cur: Any,
    *,
    company: str,
    ref: dict[str, Any],
    can_see_performance: bool,
    can_see_sensitive: bool,
) -> tuple[bool, str]:
    if ref.get("inaccessible") or ref.get("source_module_disabled"):
        return False, "source_inaccessible"
    perm = str(ref.get("permission_class") or "talent.read")
    if perm == "talent.sensitive" and not can_see_sensitive:
        return False, "sensitive_hidden"
    if perm == "performance.read" and not can_see_performance:
        return False, "source_permission_denied"
    authority = str(ref.get("source_authority") or "")
    source_id = str(ref.get("source_id") or "")
    if authority == "perf_objectives":
        cur.execute(
            "SELECT 1 FROM perf_objectives WHERE company_code=%s AND objective_id=%s",
            (company, source_id),
        )
        return (cur.fetchone() is not None, "source_missing")
    if authority == "perf_key_results":
        cur.execute(
            "SELECT 1 FROM perf_key_results WHERE company_code=%s AND key_result_id=%s",
            (company, source_id),
        )
        return (cur.fetchone() is not None, "source_missing")
    return True, "ok"


def list_evidence(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_role: str,
    has_talent_read: bool,
    can_see_sensitive: bool = False,
    can_see_performance: bool = False,
    consume_only: bool = True,
) -> dict[str, Any]:
    if not has_talent_read:
        return {"ok": False, "error": "talent_read_required"}
    company = company_code_norm(company_code)
    ensure_talent_evidence_index_pt1_schema(cur)
    contracts = get_consume_contracts(cur, company)
    cur.execute(
        """
        SELECT * FROM talent_evidence_refs
         WHERE company_code=%s AND employee_key=%s
         ORDER BY created_at
        """,
        (company, employee_key),
    )
    items: list[dict[str, Any]] = []
    hidden = 0
    for raw in cur.fetchall() or []:
        ref = _row(raw)
        contract = str(ref.get("consume_contract") or "")
        if consume_only and contract in CROSS_MODULE_CONTRACTS and not contracts.get(contract):
            continue
        if ref.get("provenance_class") == "AI-SYNTHESIZED":
            ref["classification_input_eligible"] = False
        readable, reason = _source_still_readable(
            cur,
            company=company,
            ref=ref,
            can_see_performance=can_see_performance,
            can_see_sensitive=can_see_sensitive,
        )
        if not readable:
            hidden += 1
            if reason == "sensitive_hidden":
                items.append(
                    {
                        "evidence_id": ref.get("evidence_id"),
                        "exists": True,
                        "visible": False,
                        "safe_summary": status_label("insufficient_permission", lang="en"),
                        "provenance_class": ref.get("provenance_class"),
                        "evidence_kind": ref.get("evidence_kind"),
                        "copied_canonical_rating": False,
                    }
                )
            continue
        items.append(
            {
                "evidence_id": ref.get("evidence_id"),
                "employee_key": ref.get("employee_key"),
                "source_module": ref.get("source_module"),
                "source_authority": ref.get("source_authority"),
                "source_id": ref.get("source_id"),
                "source_version": ref.get("source_version"),
                "as_of": ref.get("as_of"),
                "evidence_kind": ref.get("evidence_kind"),
                "provenance_class": ref.get("provenance_class"),
                "consume_contract": contract,
                "payload_hash": ref.get("payload_hash"),
                "claimed_not_verified": bool(ref.get("claimed_not_verified")),
                "classification_input_eligible": bool(ref.get("classification_input_eligible")),
                "copied_canonical_rating": False,
                "visible": True,
            }
        )
    provenances = {str(i.get("provenance_class")) for i in items if i.get("visible")}
    return {
        "ok": True,
        "employee_key": employee_key,
        "evidence": items,
        "hidden_count": hidden,
        "contradictions_resolved": False,
        "provenances_present": sorted(provenances),
        "consume_contracts": contracts,
        "potential_mutated": False,
        "hipo_mutated": False,
        "readiness_mutated": False,
        "master_talent_score": None,
        **honesty_payload(company_code=company),
    }


def assert_no_classification_writes() -> dict[str, Any]:
    return {
        "ok": True,
        "potential_writes": False,
        "hipo_writes": False,
        "readiness_writes": False,
        "talent_model_writes": False,
        "ai_classification_input": False,
        "master_talent_score": False,
    }
