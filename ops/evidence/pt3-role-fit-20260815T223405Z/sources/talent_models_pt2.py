#!/usr/bin/env python3
"""PT2 overlay — versioned Talent models + deterministic WHY graph.

Does not replace C5 potential or C6 HiPo. Derived High Potential signal ≠ designated HiPo.
AI may narrate a WHY graph; AI is never a classification input.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import talent_evidence_index_pt1 as idx
import talent_profile_c5 as c5
import talent_succession_c6 as c6

PHASE = "talent_models_pt2"
CONTRACT_VERSION = "talent_models_pt2_v1"
PASS_STAMP = "PT2_TALENT_MODELS_WHY_FULL_PASS"

DERIVATIONS = ("none", "rules_v1", "weighted_v1")
MODEL_STATUSES = ("draft", "published", "deprecated")
MISSING_POLICIES = ("insufficient", "exclude_renormalize")
OPS = ("eq", "neq", "in", "gte", "lte", "exists")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "published": {"en": "Published", "ar": "منشور"},
    "deprecated": {"en": "Deprecated", "ar": "مهجور"},
    "derived_high_potential": {"en": "Derived high-potential signal", "ar": "إشارة إمكانات عالية مشتقة"},
    "none": {"en": "No derived signal", "ar": "لا توجد إشارة مشتقة"},
    "insufficient_evidence": {"en": "Insufficient evidence", "ar": "دليل غير كافٍ"},
    "designated_hipo": {"en": "Designated HiPo (human)", "ar": "إمكانات عالية معيّنة (بشري)"},
    "rules_v1": {"en": "Rules v1", "ar": "قواعد الإصدار 1"},
    "weighted_v1": {"en": "Weighted v1", "ar": "ترجيح الإصدار 1"},
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
        "derived_signal_is_not_designated_hipo": True,
        "no_universal_talent_score": True,
        "no_auto_hipo": True,
        "ai_not_classification_input": True,
        "missing_is_not_zero": True,
        "missing_is_not_one_hundred": True,
        "contradictions_not_reconciled": True,
        "c5_potential_unchanged": True,
        "c6_hipo_unchanged": True,
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


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def ensure_talent_models_pt2_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c5.ensure_talent_profile_c5_schema(cur)
    c6.ensure_talent_succession_c6_schema(cur)
    idx.ensure_talent_evidence_index_pt1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_models_pt2 (
          model_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          status text NOT NULL DEFAULT 'draft',
          current_version int NOT NULL DEFAULT 0,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT tm_pt2_status_chk CHECK (status IN ('draft','published','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_model_versions_pt2 (
          version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          model_id uuid NOT NULL REFERENCES talent_models_pt2(model_id),
          version int NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          derivation text NOT NULL DEFAULT 'rules_v1',
          output_classifications jsonb NOT NULL DEFAULT '[]'::jsonb,
          dimensions jsonb NOT NULL DEFAULT '[]'::jsonb,
          evidence_bindings jsonb NOT NULL DEFAULT '[]'::jsonb,
          thresholds jsonb NOT NULL DEFAULT '[]'::jsonb,
          eligibility jsonb NOT NULL DEFAULT '[]'::jsonb,
          rules jsonb NOT NULL DEFAULT '[]'::jsonb,
          weights jsonb NOT NULL DEFAULT '{}'::jsonb,
          missing_data_policy text NOT NULL DEFAULT 'insufficient',
          ai_narration text NOT NULL DEFAULT 'forbidden',
          published_at timestamptz,
          published_by_phone text,
          publish_reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (model_id, version),
          CONSTRAINT tmv_pt2_der_chk CHECK (derivation IN ('none','rules_v1','weighted_v1')),
          CONSTRAINT tmv_pt2_miss_chk CHECK (missing_data_policy IN ('insufficient','exclude_renormalize')),
          CONSTRAINT tmv_pt2_ai_chk CHECK (ai_narration IN ('allowed','forbidden'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_model_runs_pt2 (
          run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          model_id uuid NOT NULL,
          version_id uuid NOT NULL,
          version int NOT NULL,
          employee_key text NOT NULL,
          as_of timestamptz NOT NULL DEFAULT now(),
          classification text NOT NULL,
          weighted_pct numeric,
          why jsonb NOT NULL DEFAULT '{}'::jsonb,
          hipo_written boolean NOT NULL DEFAULT false,
          potential_written boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT tmr_pt2_no_hipo_write_chk CHECK (hipo_written = false),
          CONSTRAINT tmr_pt2_no_pot_write_chk CHECK (potential_written = false)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_model_classifications_pt2 (
          classification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          model_id uuid NOT NULL,
          version_id uuid NOT NULL,
          version int NOT NULL,
          run_id uuid NOT NULL,
          classification text NOT NULL,
          as_of timestamptz NOT NULL DEFAULT now(),
          why_id uuid,
          UNIQUE (company_code, employee_key, version_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_explanations_pt2 (
          why_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          subject_type text NOT NULL DEFAULT 'classification',
          subject_id text NOT NULL,
          employee_key text NOT NULL,
          model_id uuid,
          version_id uuid,
          version int,
          graph jsonb NOT NULL,
          narrative_en text,
          narrative_ar text,
          narrative_provenance text NOT NULL DEFAULT 'none',
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT te_pt2_narr_chk CHECK (narrative_provenance IN ('none','AI-SYNTHESIZED'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_models_pt2_audit (
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
        CREATE OR REPLACE FUNCTION talent_model_versions_pt2_immutable()
        RETURNS trigger AS $$
        BEGIN
          IF OLD.status = 'published' THEN
            IF NEW.derivation IS DISTINCT FROM OLD.derivation
               OR NEW.dimensions IS DISTINCT FROM OLD.dimensions
               OR NEW.rules IS DISTINCT FROM OLD.rules
               OR NEW.weights IS DISTINCT FROM OLD.weights
               OR NEW.missing_data_policy IS DISTINCT FROM OLD.missing_data_policy
               OR NEW.thresholds IS DISTINCT FROM OLD.thresholds
               OR NEW.eligibility IS DISTINCT FROM OLD.eligibility
               OR NEW.evidence_bindings IS DISTINCT FROM OLD.evidence_bindings
               OR NEW.output_classifications IS DISTINCT FROM OLD.output_classifications
               OR NEW.ai_narration IS DISTINCT FROM OLD.ai_narration
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.model_id IS DISTINCT FROM OLD.model_id
               OR NEW.company_code IS DISTINCT FROM OLD.company_code
            THEN
              RAISE EXCEPTION 'published_version_immutable';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    cur.execute("DROP TRIGGER IF EXISTS tmv_pt2_immutable ON talent_model_versions_pt2")
    cur.execute(
        """
        CREATE TRIGGER tmv_pt2_immutable
        BEFORE UPDATE ON talent_model_versions_pt2
        FOR EACH ROW EXECUTE FUNCTION talent_model_versions_pt2_immutable()
        """
    )


def _audit(cur: Any, *, company_code: str, action: str, actor_phone: str | None, reason: str, subject_type: str, subject_id: str, payload: dict[str, Any] | None = None) -> None:
    cur.execute(
        """
        INSERT INTO talent_models_pt2_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code,
            action,
            _digits(actor_phone) if actor_phone else None,
            str(reason or "")[:500],
            subject_type,
            subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur: Any, company_code: str) -> dict[str, Any]:
    return c5._entitled(cur, company_code)


def create_model(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    name_ar: str | None = None,
    reason: str = "create talent model",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not str(name_en or "").strip():
        return {"ok": False, "error": "name_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_talent_models_pt2_schema(cur)
    cur.execute(
        """
        INSERT INTO talent_models_pt2 (company_code, name_en, name_ar, created_by_phone)
        VALUES (%s,%s,%s,%s) RETURNING *
        """,
        (company, str(name_en).strip()[:300], (str(name_ar).strip()[:300] if name_ar else None), _digits(actor_phone)),
    )
    row = _row(cur.fetchone())
    _audit(cur, company_code=company, action="model_created", actor_phone=actor_phone, reason=reason, subject_type="model", subject_id=str(row["model_id"]))
    return {"ok": True, "model": row, **honesty_payload(company_code=company)}


def _validate_config(*, derivation: str, dimensions: list[Any], rules: list[Any], weights: dict[str, Any], missing_data_policy: str) -> dict[str, Any] | None:
    if derivation not in DERIVATIONS:
        return {"ok": False, "error": "invalid_derivation", "allowed": list(DERIVATIONS)}
    if missing_data_policy not in MISSING_POLICIES:
        return {"ok": False, "error": "invalid_missing_data_policy", "allowed": list(MISSING_POLICIES)}
    if not dimensions:
        return {"ok": False, "error": "dimensions_required"}
    ids = [str(d.get("id") or "") for d in dimensions if isinstance(d, dict)]
    if not all(ids) or len(ids) != len(set(ids)):
        return {"ok": False, "error": "dimension_ids_invalid"}
    if derivation == "weighted_v1":
        if not weights:
            return {"ok": False, "error": "weighted_v1_requires_explicit_weights"}
        total = 0.0
        for dim in ids:
            if dim not in weights:
                return {"ok": False, "error": "weighted_v1_missing_weight", "dimension": dim}
            try:
                total += float(weights[dim])
            except (TypeError, ValueError):
                return {"ok": False, "error": "weighted_v1_invalid_weight", "dimension": dim}
        if abs(total - 1.0) > 0.001:
            return {"ok": False, "error": "weighted_v1_weights_must_sum_to_1", "sum": total}
    if derivation == "rules_v1" and not rules:
        return {"ok": False, "error": "rules_v1_requires_rules"}
    return None


def save_draft_version(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    model_id: str,
    derivation: str = "rules_v1",
    output_classifications: list[Any] | None = None,
    dimensions: list[Any] | None = None,
    evidence_bindings: list[Any] | None = None,
    thresholds: list[Any] | None = None,
    eligibility: list[Any] | None = None,
    rules: list[Any] | None = None,
    weights: dict[str, Any] | None = None,
    missing_data_policy: str = "insufficient",
    ai_narration: str = "forbidden",
    reason: str = "save draft model version",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_talent_models_pt2_schema(cur)
    cur.execute("SELECT * FROM talent_models_pt2 WHERE company_code=%s AND model_id=%s", (company, model_id))
    model = cur.fetchone()
    if not model:
        return {"ok": False, "error": "model_not_found"}
    err = _validate_config(
        derivation=derivation,
        dimensions=list(dimensions or []),
        rules=list(rules or []),
        weights=dict(weights or {}),
        missing_data_policy=missing_data_policy,
    )
    if err:
        return err
    cur.execute(
        "SELECT COALESCE(MAX(version),0) AS v FROM talent_model_versions_pt2 WHERE model_id=%s",
        (model_id,),
    )
    nxt = int(_row(cur.fetchone()).get("v") or 0) + 1
    cur.execute(
        """
        INSERT INTO talent_model_versions_pt2 (
          company_code, model_id, version, status, derivation, output_classifications,
          dimensions, evidence_bindings, thresholds, eligibility, rules, weights,
          missing_data_policy, ai_narration
        ) VALUES (%s,%s,%s,'draft',%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            model_id,
            nxt,
            derivation,
            json.dumps(output_classifications or ["derived_high_potential", "none", "insufficient_evidence"], default=str),
            json.dumps(dimensions or [], default=str),
            json.dumps(evidence_bindings or [], default=str),
            json.dumps(thresholds or [], default=str),
            json.dumps(eligibility or [], default=str),
            json.dumps(rules or [], default=str),
            json.dumps(weights or {}, default=str),
            missing_data_policy,
            "allowed" if ai_narration == "allowed" else "forbidden",
        ),
    )
    row = _row(cur.fetchone())
    _audit(cur, company_code=company, action="version_drafted", actor_phone=actor_phone, reason=reason, subject_type="model_version", subject_id=str(row["version_id"]))
    return {"ok": True, "version": row, "immutable": False, **honesty_payload(company_code=company)}


def publish_version(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    version_id: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM talent_model_versions_pt2 WHERE company_code=%s AND version_id=%s",
        (company, version_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "version_not_found"}
    ver = _row(row)
    if str(ver.get("status")) == "published":
        return {"ok": False, "error": "already_published", "immutable": True}
    err = _validate_config(
        derivation=str(ver.get("derivation")),
        dimensions=list(_json(ver.get("dimensions")) or []),
        rules=list(_json(ver.get("rules")) or []),
        weights=dict(_json(ver.get("weights")) or {}),
        missing_data_policy=str(ver.get("missing_data_policy") or "insufficient"),
    )
    if err:
        return err
    cur.execute(
        """
        UPDATE talent_model_versions_pt2
           SET status='published', published_at=now(), published_by_phone=%s, publish_reason=%s
         WHERE version_id=%s
        RETURNING *
        """,
        (_digits(actor_phone), str(reason).strip()[:500], version_id),
    )
    published = _row(cur.fetchone())
    cur.execute(
        """
        UPDATE talent_models_pt2
           SET status='published', current_version=%s, updated_at=now()
         WHERE model_id=%s
        """,
        (published.get("version"), published.get("model_id")),
    )
    _audit(cur, company_code=company, action="version_published", actor_phone=actor_phone, reason=reason, subject_type="model_version", subject_id=str(version_id), payload={"immutable": True})
    return {"ok": True, "version": published, "immutable": True, **honesty_payload(company_code=company)}


def get_published_version(cur: Any, *, company_code: str, model_id: str | None = None, version_id: str | None = None) -> dict[str, Any] | None:
    company = company_code_norm(company_code)
    if version_id:
        cur.execute(
            "SELECT * FROM talent_model_versions_pt2 WHERE company_code=%s AND version_id=%s AND status='published'",
            (company, version_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM talent_model_versions_pt2
             WHERE company_code=%s AND model_id=%s AND status='published'
             ORDER BY version DESC LIMIT 1
            """,
            (company, model_id),
        )
    row = cur.fetchone()
    return _row(row) if row else None


def list_models(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_talent_models_pt2_schema(cur)
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM talent_models_pt2 WHERE company_code=%s ORDER BY created_at", (company,))
    return {"ok": True, "models": [_row(r) for r in (cur.fetchall() or [])], **honesty_payload(company_code=company)}


def _compare(op: str, actual: Any, expected: Any) -> bool:
    if op == "exists":
        return actual not in (None, "", [], {})
    if actual in (None, ""):
        return False
    if op == "eq":
        return str(actual).lower() == str(expected).lower()
    if op == "neq":
        return str(actual).lower() != str(expected).lower()
    if op == "in":
        allowed = expected if isinstance(expected, (list, tuple, set)) else [expected]
        return str(actual).lower() in {str(x).lower() for x in allowed}
    try:
        left = float(actual)
        right = float(expected)
    except (TypeError, ValueError):
        return False
    if op == "gte":
        return left >= right
    if op == "lte":
        return left <= right
    return False


def _collect_inputs(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    version: dict[str, Any],
    can_see_performance: bool,
    can_see_sensitive: bool,
) -> dict[str, Any]:
    dimensions = list(_json(version.get("dimensions")) or [])
    bindings = {str(b.get("dimension")): b for b in (_json(version.get("evidence_bindings")) or []) if isinstance(b, dict)}
    contracts = idx.get_consume_contracts(cur, company)
    evidence = idx.list_evidence(
        cur,
        company_code=company,
        employee_key=employee_key,
        actor_role="hr",
        has_talent_read=True,
        can_see_sensitive=can_see_sensitive,
        can_see_performance=can_see_performance,
    )
    ev_items = [e for e in (evidence.get("evidence") or []) if e.get("visible")]
    pot = c5.get_potential_for_viewer(
        cur,
        company_code=company,
        employee_key=employee_key,
        viewer_role="hr",
        has_sensitive_permission=can_see_sensitive,
    )
    assessments = pot.get("assessments") if pot.get("ok") else []
    latest_pot = next((a for a in assessments if str(a.get("status")) in {"submitted", "accepted"}), None)
    hipo = c6.get_hipo_for_viewer(
        cur,
        company_code=company,
        employee_key=employee_key,
        viewer_role="hr",
        has_sensitive_permission=can_see_sensitive,
    )
    designations = hipo.get("designations") if hipo.get("ok") else []
    current_hipo = next((d for d in designations if not d.get("superseded_by_designation_id")), None)
    hipo_status = str((current_hipo or {}).get("status") or "")

    collected: dict[str, Any] = {}
    consumed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for dim in dimensions:
        did = str(dim.get("id"))
        kind = str(dim.get("input_kind") or "evidence")
        required = bool(dim.get("required", True))
        binding = bindings.get(did) or {}
        allowed_kinds = {str(x) for x in (binding.get("evidence_kinds") or [])}
        allowed_prov = {str(x) for x in (binding.get("provenance") or [])}
        value = None
        source = None
        if kind == "human_potential":
            if latest_pot:
                value = latest_pot.get("resulting_level")
                source = {
                    "authority": "talent_potential_assessments",
                    "id": str(latest_pot.get("assessment_id")),
                    "provenance_class": "HR-ASSESSED" if str(latest_pot.get("assessor_role")) != "manager" else "MANAGER-ASSESSED",
                }
            else:
                missing.append({"dimension": did, "reason": "human_potential_missing"})
        elif kind == "human_hipo":
            if current_hipo:
                value = hipo_status
                source = {
                    "authority": "talent_hipo_designations",
                    "id": str(current_hipo.get("designation_id")),
                    "provenance_class": "HR-ASSESSED",
                }
            else:
                value = "not_designated"
                source = {"authority": "talent_hipo_designations", "id": None, "provenance_class": "SYSTEM-DERIVED"}
        elif kind == "okr_progress":
            if not contracts.get("okr_as_talent_evidence_v1"):
                excluded.append({"dimension": did, "reason": "okr_as_talent_evidence_v1_off"})
            else:
                okr = next((e for e in ev_items if e.get("evidence_kind") == "okr"), None)
                if okr:
                    value = "present"
                    source = {
                        "authority": okr.get("source_authority"),
                        "id": okr.get("source_id"),
                        "provenance_class": okr.get("provenance_class"),
                    }
                    if okr.get("source_authority") == "perf_objectives":
                        import performance_goals_c1 as c1

                        roll = c1.objective_rollup(cur, company_code=company, objective_id=str(okr.get("source_id")))
                        if roll.get("progress_pct") is not None:
                            value = float(roll["progress_pct"])
                else:
                    missing.append({"dimension": did, "reason": "okr_evidence_missing"})
        elif kind == "performance_outcome":
            if not contracts.get("performance_outcome_as_evidence_v1") and not (c5.get_company_settings(cur, company) or {}).get("performance_evidence_consume"):
                excluded.append({"dimension": did, "reason": "performance_outcome_as_evidence_v1_off"})
            else:
                perf = next((e for e in ev_items if e.get("evidence_kind") in {"review_outcome", "development"} or e.get("source_authority") == "talent_dimension_facts"), None)
                cur.execute(
                    """
                    SELECT * FROM talent_dimension_facts
                     WHERE company_code=%s AND employee_key=%s AND source='performance_outcome' AND status='active'
                     ORDER BY version DESC LIMIT 1
                    """,
                    (company, employee_key),
                )
                fact = cur.fetchone()
                if fact:
                    fact = _row(fact)
                    value = fact.get("detail_en") or fact.get("title_en") or "present"
                    source = {
                        "authority": "talent_dimension_facts",
                        "id": str(fact.get("fact_id")),
                        "provenance_class": "SYSTEM-DERIVED",
                    }
                elif perf:
                    value = "present"
                    source = {
                        "authority": perf.get("source_authority"),
                        "id": perf.get("source_id"),
                        "provenance_class": perf.get("provenance_class"),
                    }
                else:
                    missing.append({"dimension": did, "reason": "performance_evidence_missing"})
        else:
            match = None
            for item in ev_items:
                if allowed_kinds and item.get("evidence_kind") not in allowed_kinds:
                    continue
                if allowed_prov and item.get("provenance_class") not in allowed_prov:
                    continue
                if item.get("provenance_class") == "AI-SYNTHESIZED":
                    excluded.append({"dimension": did, "reason": "ai_synthesized_not_classification_input", "source_id": item.get("source_id")})
                    continue
                if item.get("claimed_not_verified") and not binding.get("allow_claimed"):
                    excluded.append({"dimension": did, "reason": "claimed_skill_not_verified", "source_id": item.get("source_id")})
                    continue
                match = item
                break
            if match:
                value = match.get("evidence_kind")
                source = {
                    "authority": match.get("source_authority"),
                    "id": match.get("source_id"),
                    "provenance_class": match.get("provenance_class"),
                }
            elif required:
                missing.append({"dimension": did, "reason": "evidence_missing"})
        collected[did] = {"value": value, "source": source, "input_kind": kind, "required": required}
        if source and value not in (None, ""):
            consumed.append({"dimension": did, **source, "value": value})
        elif required and value in (None, "") and not any(m.get("dimension") == did for m in missing) and not any(e.get("dimension") == did for e in excluded):
            missing.append({"dimension": did, "reason": "value_missing"})

    return {
        "dimensions": collected,
        "consumed": consumed,
        "excluded": excluded,
        "missing": missing,
        "human_potential": (latest_pot or {}).get("resulting_level"),
        "human_hipo": hipo_status or "not_designated",
        "potential_assessments_ok": pot.get("ok") is True,
        "hipo_ok": hipo.get("ok") is True,
    }


def _apply_rules(rules: list[Any], collected: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    fired: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        clauses = list(rule.get("all") or [])
        ok = True
        for clause in clauses:
            dim = str(clause.get("dimension") or "")
            actual = ((collected.get(dim) or {}).get("value"))
            if not _compare(str(clause.get("op") or "eq"), actual, clause.get("value")):
                ok = False
                break
        if ok and clauses:
            label = str(rule.get("classification") or "none")
            fired.append({"rule": rule.get("id") or label, "classification": label})
            return label, fired
    return "none", fired


_WEIGHTED_BANDS = {
    "low": 0.0,
    "none": 0.0,
    "not_designated": 0.0,
    "moderate": 30.0,
    "high": 100.0,
    "expanding": 100.0,
    "enterprise": 100.0,
    "designated": 100.0,
}


def _eligibility_failed(eligibility: list[Any], collected: dict[str, Any]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for clause in eligibility:
        if not isinstance(clause, dict):
            continue
        dim = str(clause.get("dimension") or "")
        actual = (collected.get(dim) or {}).get("value")
        if not _compare(str(clause.get("op") or "eq"), actual, clause.get("value")):
            failed.append({"dimension": dim, "op": clause.get("op"), "expected": clause.get("value"), "actual": actual})
    return failed


def _apply_weighted(weights: dict[str, Any], collected: dict[str, Any], missing_policy: str, thresholds: list[Any]) -> tuple[str, float | None, list[dict[str, Any]]]:
    terms: list[dict[str, Any]] = []
    used = 0.0
    acc = 0.0
    for dim, weight in weights.items():
        w = float(weight)
        raw = (collected.get(dim) or {}).get("value")
        if raw in (None, ""):
            if missing_policy == "insufficient":
                return "insufficient_evidence", None, [{"dimension": dim, "weight": w, "missing": True, "treated_as": None}]
            terms.append({"dimension": dim, "weight": w, "missing": True, "excluded": True, "treated_as": None})
            continue
        try:
            score = float(raw)
        except (TypeError, ValueError):
            key = str(raw).lower()
            if key not in _WEIGHTED_BANDS:
                if missing_policy == "insufficient":
                    return "insufficient_evidence", None, [{"dimension": dim, "weight": w, "unmapped_value": raw, "treated_as": None}]
                terms.append({"dimension": dim, "weight": w, "unmapped_value": raw, "excluded": True, "treated_as": None})
                continue
            score = _WEIGHTED_BANDS[key]
        acc += w * score
        used += w
        terms.append({"dimension": dim, "weight": w, "value": raw, "contribution": w * score, "missing": False})
    if used <= 0:
        return "insufficient_evidence", None, terms
    pct = acc / used if missing_policy == "exclude_renormalize" else acc
    label = "none"
    for band in thresholds:
        if not isinstance(band, dict):
            continue
        if _compare(str(band.get("op") or "gte"), pct, band.get("value")):
            label = str(band.get("classification") or "none")
            break
    return label, float(round(pct, 4)), terms


def evaluate_employee(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    model_id: str | None = None,
    version_id: str | None = None,
    can_see_performance: bool = True,
    can_see_sensitive: bool = True,
    reason: str = "evaluate talent model",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_talent_models_pt2_schema(cur)
    version = get_published_version(cur, company_code=company, model_id=model_id, version_id=version_id)
    if not version:
        return {"ok": False, "error": "published_version_required"}
    hipo_before = c6.get_hipo_for_viewer(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=True
    )
    pot_before = c5.get_potential_for_viewer(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=True
    )
    inputs = _collect_inputs(
        cur,
        company=company,
        employee_key=employee_key,
        version=version,
        can_see_performance=can_see_performance,
        can_see_sensitive=can_see_sensitive,
    )
    collected = inputs["dimensions"]
    required_missing = [m for m in inputs["missing"] if (collected.get(m["dimension"]) or {}).get("required", True)]
    derivation = str(version.get("derivation"))
    weighted_pct = None
    fired: list[dict[str, Any]] = []
    eligibility_failed = _eligibility_failed(list(_json(version.get("eligibility")) or []), collected)
    if required_missing and str(version.get("missing_data_policy") or "insufficient") == "insufficient":
        classification = "insufficient_evidence"
    elif eligibility_failed:
        classification = "none"
        fired = [{"eligibility_failed": eligibility_failed}]
    elif derivation == "none":
        classification = "none"
    elif derivation == "weighted_v1":
        classification, weighted_pct, fired = _apply_weighted(
            dict(_json(version.get("weights")) or {}),
            collected,
            str(version.get("missing_data_policy") or "insufficient"),
            list(_json(version.get("thresholds")) or []),
        )
    else:
        classification, fired = _apply_rules(list(_json(version.get("rules")) or []), collected)

    overrides = []
    if inputs["human_hipo"] in {"designated", "nominated"} and classification != "derived_high_potential":
        overrides.append({"kind": "human_hipo", "status": inputs["human_hipo"], "note": "human_designation_differs_from_derived"})
    if classification == "derived_high_potential" and inputs["human_hipo"] not in {"designated", "nominated"}:
        overrides.append({"kind": "derived_not_designated", "status": inputs["human_hipo"], "note": "derived_signal_is_not_designated_hipo"})

    graph = {
        "subject": "classification",
        "model_id": str(version.get("model_id")),
        "version_id": str(version.get("version_id")),
        "version": version.get("version"),
        "derivation": derivation,
        "evidence_consumed": inputs["consumed"],
        "evidence_excluded": inputs["excluded"],
        "missing_evidence": inputs["missing"],
        "provenance": [c.get("provenance_class") for c in inputs["consumed"]],
        "rules_or_weights_fired": fired,
        "human_overrides": overrides,
        "human_potential": inputs["human_potential"],
        "human_hipo": inputs["human_hipo"],
        "resulting_derived_classification": classification,
        "weighted_pct": weighted_pct,
        "weighted_methodology_complete": derivation != "weighted_v1" or weighted_pct is not None,
        "eligibility_failed": eligibility_failed,
        "contradictions_reconciled": False,
        "ai_classification_input": False,
        "designated_hipo": inputs["human_hipo"] in {"designated", "nominated"},
    }
    cur.execute(
        """
        INSERT INTO talent_explanations_pt2 (
          company_code, subject_type, subject_id, employee_key, model_id, version_id, version, graph
        ) VALUES (%s,'classification',%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            employee_key,
            employee_key,
            version.get("model_id"),
            version.get("version_id"),
            version.get("version"),
            json.dumps(graph, default=str),
        ),
    )
    why = _row(cur.fetchone())
    cur.execute(
        """
        INSERT INTO talent_model_runs_pt2 (
          company_code, model_id, version_id, version, employee_key, classification, weighted_pct, why
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            version.get("model_id"),
            version.get("version_id"),
            version.get("version"),
            employee_key,
            classification,
            weighted_pct,
            json.dumps(graph, default=str),
        ),
    )
    run = _row(cur.fetchone())
    cur.execute(
        """
        INSERT INTO talent_model_classifications_pt2 (
          company_code, employee_key, model_id, version_id, version, run_id, classification, why_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, employee_key, version_id) DO UPDATE SET
          run_id=EXCLUDED.run_id,
          classification=EXCLUDED.classification,
          why_id=EXCLUDED.why_id,
          as_of=now()
        RETURNING *
        """,
        (
            company,
            employee_key,
            version.get("model_id"),
            version.get("version_id"),
            version.get("version"),
            run.get("run_id"),
            classification,
            why.get("why_id"),
        ),
    )
    stored = _row(cur.fetchone())
    hipo_after = c6.get_hipo_for_viewer(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=True
    )
    pot_after = c5.get_potential_for_viewer(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=True
    )
    _audit(cur, company_code=company, action="model_evaluated", actor_phone=actor_phone, reason=reason, subject_type="classification", subject_id=str(stored.get("classification_id")), payload={"classification": classification})
    return {
        "ok": True,
        "run": run,
        "classification": stored,
        "why": {"why_id": why.get("why_id"), **graph},
        "derived_signal_is_not_designated_hipo": True,
        "designated_hipo": graph["designated_hipo"],
        "human_potential": inputs["human_potential"],
        "human_hipo": inputs["human_hipo"],
        "hipo_mutated": hipo_before.get("designations") != hipo_after.get("designations") if hipo_before.get("ok") and hipo_after.get("ok") else False,
        "potential_mutated": pot_before.get("assessments") != pot_after.get("assessments") if pot_before.get("ok") and pot_after.get("ok") else False,
        "master_talent_score": None,
        **honesty_payload(company_code=company),
    }


def get_why(cur: Any, *, company_code: str, why_id: str | None = None, employee_key: str | None = None, version_id: str | None = None) -> dict[str, Any]:
    ensure_talent_models_pt2_schema(cur)
    company = company_code_norm(company_code)
    if why_id:
        cur.execute("SELECT * FROM talent_explanations_pt2 WHERE company_code=%s AND why_id=%s", (company, why_id))
    else:
        cur.execute(
            """
            SELECT * FROM talent_explanations_pt2
             WHERE company_code=%s AND employee_key=%s
               AND (%s IS NULL OR version_id=%s)
             ORDER BY created_at DESC LIMIT 1
            """,
            (company, employee_key, version_id, version_id),
        )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "why_not_found"}
    item = _row(row)
    graph = _json(item.get("graph")) or {}
    return {"ok": True, "why": {**item, "graph": graph}, **honesty_payload(company_code=company)}


def list_classifications(cur: Any, *, company_code: str, model_id: str | None = None, classification: str | None = None) -> dict[str, Any]:
    ensure_talent_models_pt2_schema(cur)
    company = company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if model_id:
        where.append("model_id=%s")
        params.append(model_id)
    if classification:
        where.append("classification=%s")
        params.append(classification)
    cur.execute(
        f"SELECT * FROM talent_model_classifications_pt2 WHERE {' AND '.join(where)} ORDER BY as_of DESC",
        params,
    )
    return {
        "ok": True,
        "classifications": [_row(r) for r in (cur.fetchall() or [])],
        "master_talent_score": None,
        **honesty_payload(company_code=company),
    }


def attach_ai_narrative(
    cur: Any,
    *,
    company_code: str,
    why_id: str,
    narrative_en: str,
    narrative_ar: str | None = None,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM talent_explanations_pt2 WHERE company_code=%s AND why_id=%s", (company, why_id))
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "why_not_found"}
    item = _row(row)
    cur.execute("SELECT ai_narration FROM talent_model_versions_pt2 WHERE version_id=%s", (item.get("version_id"),))
    ver = _row(cur.fetchone())
    if str(ver.get("ai_narration") or "forbidden") != "allowed":
        return {"ok": False, "error": "ai_narration_forbidden"}
    cur.execute(
        """
        UPDATE talent_explanations_pt2
           SET narrative_en=%s, narrative_ar=%s, narrative_provenance='AI-SYNTHESIZED'
         WHERE why_id=%s
        RETURNING *
        """,
        (narrative_en, narrative_ar, why_id),
    )
    updated = _row(cur.fetchone())
    return {
        "ok": True,
        "why": updated,
        "narrative_is_not_evidence": True,
        "ai_not_classification_input": True,
        **honesty_payload(company_code=company),
    }


def default_high_potential_signal_config() -> dict[str, Any]:
    """Safe default: derived signal requires human potential. OKR/perf cannot mint HiPo."""
    return {
        "derivation": "rules_v1",
        "output_classifications": ["derived_high_potential", "none", "insufficient_evidence"],
        "dimensions": [
            {"id": "potential", "label_en": "Human potential", "label_ar": "الإمكانات البشرية", "input_kind": "human_potential", "required": True},
            {"id": "performance", "label_en": "Performance outcome", "label_ar": "نتيجة الأداء", "input_kind": "performance_outcome", "required": False},
            {"id": "okr", "label_en": "OKR outcome", "label_ar": "نتيجة النتائج الرئيسية", "input_kind": "okr_progress", "required": False},
            {"id": "hipo", "label_en": "Human HiPo designation", "label_ar": "تعيين الإمكانات العالية", "input_kind": "human_hipo", "required": False},
        ],
        "evidence_bindings": [
            {"dimension": "potential", "evidence_kinds": ["potential"], "provenance": ["MANAGER-ASSESSED", "HR-ASSESSED"]},
            {"dimension": "performance", "evidence_kinds": ["review_outcome"], "provenance": ["SYSTEM-DERIVED", "HR-ASSESSED"]},
            {"dimension": "okr", "evidence_kinds": ["okr"], "provenance": ["SYSTEM-DERIVED"]},
        ],
        "rules": [
            {
                "id": "derived_hipo_requires_human_potential",
                "classification": "derived_high_potential",
                "all": [{"dimension": "potential", "op": "in", "value": ["high", "expanding", "enterprise"]}],
            }
        ],
        "weights": {},
        "missing_data_policy": "insufficient",
        "thresholds": [],
        "eligibility": [],
        "ai_narration": "forbidden",
    }
