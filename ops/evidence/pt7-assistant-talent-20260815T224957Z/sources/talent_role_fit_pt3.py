#!/usr/bin/env python3
"""PT3 overlay — deterministic role fit + target-specific readiness context.

Role fit ≠ readiness ≠ promotion eligibility.
Human C6 readiness remains authoritative where it exists.
JA may draft requirements; PT never writes scores back to JA.
JA OFF → role fit is honestly unavailable; Talent itself continues.
"""
from __future__ import annotations

import json
from typing import Any

import talent_evidence_index_pt1 as idx
import talent_profile_c5 as c5
import talent_succession_c6 as c6

PHASE = "talent_role_fit_pt3"
CONTRACT_VERSION = "talent_role_fit_pt3_v1"
PASS_STAMP = "PT3_ROLE_FIT_READINESS_FULL_PASS"

REQUIREMENT_KINDS = (
    "competency",
    "skill",
    "certification",
    "experience",
    "assessment",
    "performance_evidence",
    "development",
)
OUTCOMES = ("met", "partial", "gap", "not_assessed", "not_permitted")
FIT_LABELS = ("strong_fit", "partial_fit", "gaps", "not_assessed", "unavailable")
PRIORITIES = ("required", "preferred")
DERIVATIONS = ("none", "rules_v1", "weighted_v1")
MISSING_POLICIES = ("insufficient", "exclude_renormalize")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "published": {"en": "Published", "ar": "منشور"},
    "met": {"en": "Met", "ar": "مستوفى"},
    "partial": {"en": "Partial", "ar": "جزئي"},
    "gap": {"en": "Gap", "ar": "فجوة"},
    "not_assessed": {"en": "Not assessed", "ar": "غير مُقيَّم"},
    "not_permitted": {"en": "Not permitted", "ar": "غير مسموح"},
    "strong_fit": {"en": "Strong fit", "ar": "ملاءمة قوية"},
    "partial_fit": {"en": "Partial fit", "ar": "ملاءمة جزئية"},
    "gaps": {"en": "Gaps", "ar": "فجوات"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "role_fit": {"en": "Role fit", "ar": "ملاءمة الدور"},
    "readiness": {"en": "Readiness", "ar": "الجاهزية"},
    "promotion_eligibility": {"en": "Promotion eligibility", "ar": "أهلية الترقية"},
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
        "role_fit_is_not_readiness": True,
        "role_fit_is_not_promotion_eligibility": True,
        "readiness_is_not_promotion_eligibility": True,
        "human_c6_readiness_authoritative": True,
        "no_write_back_to_ja": True,
        "no_universal_fit_percent": True,
        "missing_is_not_zero": True,
        "missing_is_not_one_hundred": True,
        "ja_off_fit_unavailable": True,
        "talent_works_without_ja": True,
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


def ja_available(company_code: str) -> dict[str, Any]:
    try:
        import job_architecture_c1 as ja

        gate = ja.runtime_gate_for_company(company_code)
        return {"ok": bool(gate.get("ok")), "gate": gate}
    except Exception as exc:
        return {"ok": False, "gate": {"error": "ja_import_failed", "detail": str(exc)}}


def ensure_talent_role_fit_pt3_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c5.ensure_talent_profile_c5_schema(cur)
    c6.ensure_talent_succession_c6_schema(cur)
    idx.ensure_talent_evidence_index_pt1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_role_requirement_sets_pt3 (
          set_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          job_profile_id text,
          critical_role_id text,
          status text NOT NULL DEFAULT 'draft',
          current_version int NOT NULL DEFAULT 0,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT trs_pt3_status_chk CHECK (status IN ('draft','published','deprecated')),
          CONSTRAINT trs_pt3_target_chk CHECK (job_profile_id IS NOT NULL OR critical_role_id IS NOT NULL)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_role_requirement_set_versions_pt3 (
          version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          set_id uuid NOT NULL REFERENCES talent_role_requirement_sets_pt3(set_id),
          version int NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          derivation text NOT NULL DEFAULT 'rules_v1',
          requirements jsonb NOT NULL DEFAULT '[]'::jsonb,
          readiness_rules jsonb NOT NULL DEFAULT '[]'::jsonb,
          weights jsonb NOT NULL DEFAULT '{}'::jsonb,
          missing_data_policy text NOT NULL DEFAULT 'insufficient',
          imported_from_ja boolean NOT NULL DEFAULT false,
          published_at timestamptz,
          published_by_phone text,
          publish_reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (set_id, version),
          CONSTRAINT trsv_pt3_der_chk CHECK (derivation IN ('none','rules_v1','weighted_v1')),
          CONSTRAINT trsv_pt3_miss_chk CHECK (missing_data_policy IN ('insufficient','exclude_renormalize'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_role_fit_evaluations_pt3 (
          evaluation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          set_id uuid NOT NULL,
          version_id uuid NOT NULL,
          version int NOT NULL,
          overall_fit text NOT NULL,
          weighted_pct numeric,
          requirement_results jsonb NOT NULL DEFAULT '[]'::jsonb,
          readiness_suggestion text,
          human_readiness text,
          human_readiness_authoritative boolean NOT NULL DEFAULT true,
          ja_written boolean NOT NULL DEFAULT false,
          c6_readiness_written boolean NOT NULL DEFAULT false,
          why jsonb NOT NULL DEFAULT '{}'::jsonb,
          as_of timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key, version_id),
          CONSTRAINT trfe_pt3_fit_chk CHECK (overall_fit IN ('strong_fit','partial_fit','gaps','not_assessed','unavailable')),
          CONSTRAINT trfe_pt3_no_ja_write_chk CHECK (ja_written = false),
          CONSTRAINT trfe_pt3_no_c6_write_chk CHECK (c6_readiness_written = false)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_role_fit_pt3_audit (
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
        CREATE OR REPLACE FUNCTION talent_role_req_versions_pt3_immutable()
        RETURNS trigger AS $$
        BEGIN
          IF OLD.status = 'published' THEN
            IF NEW.requirements IS DISTINCT FROM OLD.requirements
               OR NEW.derivation IS DISTINCT FROM OLD.derivation
               OR NEW.weights IS DISTINCT FROM OLD.weights
               OR NEW.readiness_rules IS DISTINCT FROM OLD.readiness_rules
               OR NEW.missing_data_policy IS DISTINCT FROM OLD.missing_data_policy
               OR NEW.version IS DISTINCT FROM OLD.version
            THEN
              RAISE EXCEPTION 'published_requirement_set_immutable';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    cur.execute("DROP TRIGGER IF EXISTS trsv_pt3_immutable ON talent_role_requirement_set_versions_pt3")
    cur.execute(
        """
        CREATE TRIGGER trsv_pt3_immutable
        BEFORE UPDATE ON talent_role_requirement_set_versions_pt3
        FOR EACH ROW EXECUTE FUNCTION talent_role_req_versions_pt3_immutable()
        """
    )


def _audit(cur: Any, *, company_code: str, action: str, actor_phone: str | None, reason: str, subject_type: str, subject_id: str, payload: dict[str, Any] | None = None) -> None:
    cur.execute(
        """
        INSERT INTO talent_role_fit_pt3_audit (
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


def _validate_requirements(requirements: list[Any], *, derivation: str, weights: dict[str, Any], missing_data_policy: str) -> dict[str, Any] | None:
    if derivation not in DERIVATIONS:
        return {"ok": False, "error": "invalid_derivation"}
    if missing_data_policy not in MISSING_POLICIES:
        return {"ok": False, "error": "invalid_missing_data_policy"}
    if not requirements:
        return {"ok": False, "error": "requirements_required"}
    ids = []
    for req in requirements:
        if not isinstance(req, dict):
            return {"ok": False, "error": "invalid_requirement"}
        rid = str(req.get("id") or "")
        kind = str(req.get("kind") or "")
        priority = str(req.get("priority") or "required")
        if not rid or kind not in REQUIREMENT_KINDS or priority not in PRIORITIES:
            return {"ok": False, "error": "invalid_requirement", "requirement": req}
        ids.append(rid)
    if len(ids) != len(set(ids)):
        return {"ok": False, "error": "requirement_ids_invalid"}
    if derivation == "weighted_v1":
        if not weights:
            return {"ok": False, "error": "weighted_v1_requires_explicit_weights"}
        total = 0.0
        for rid in ids:
            if rid not in weights:
                return {"ok": False, "error": "weighted_v1_missing_weight", "requirement": rid}
            try:
                total += float(weights[rid])
            except (TypeError, ValueError):
                return {"ok": False, "error": "weighted_v1_invalid_weight", "requirement": rid}
        if abs(total - 1.0) > 0.001:
            return {"ok": False, "error": "weighted_v1_weights_must_sum_to_1", "sum": total}
    return None


def create_requirement_set(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    name_ar: str | None = None,
    job_profile_id: str | None = None,
    critical_role_id: str | None = None,
    reason: str = "create role requirement set",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not str(name_en or "").strip():
        return {"ok": False, "error": "name_required"}
    if not job_profile_id and not critical_role_id:
        return {"ok": False, "error": "target_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_talent_role_fit_pt3_schema(cur)
    cur.execute(
        """
        INSERT INTO talent_role_requirement_sets_pt3 (
          company_code, name_en, name_ar, job_profile_id, critical_role_id, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:300],
            (str(name_ar).strip()[:300] if name_ar else None),
            job_profile_id,
            critical_role_id,
            _digits(actor_phone),
        ),
    )
    row = _row(cur.fetchone())
    _audit(cur, company_code=company, action="set_created", actor_phone=actor_phone, reason=reason, subject_type="requirement_set", subject_id=str(row["set_id"]))
    return {"ok": True, "set": row, **honesty_payload(company_code=company)}


def save_draft_version(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    set_id: str,
    requirements: list[Any],
    derivation: str = "rules_v1",
    readiness_rules: list[Any] | None = None,
    weights: dict[str, Any] | None = None,
    missing_data_policy: str = "insufficient",
    imported_from_ja: bool = False,
    reason: str = "save draft requirement set",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_talent_role_fit_pt3_schema(cur)
    cur.execute("SELECT * FROM talent_role_requirement_sets_pt3 WHERE company_code=%s AND set_id=%s", (company, set_id))
    if not cur.fetchone():
        return {"ok": False, "error": "set_not_found"}
    err = _validate_requirements(list(requirements or []), derivation=derivation, weights=dict(weights or {}), missing_data_policy=missing_data_policy)
    if err:
        return err
    cur.execute("SELECT COALESCE(MAX(version),0) AS v FROM talent_role_requirement_set_versions_pt3 WHERE set_id=%s", (set_id,))
    nxt = int(_row(cur.fetchone()).get("v") or 0) + 1
    cur.execute(
        """
        INSERT INTO talent_role_requirement_set_versions_pt3 (
          company_code, set_id, version, status, derivation, requirements, readiness_rules,
          weights, missing_data_policy, imported_from_ja
        ) VALUES (%s,%s,%s,'draft',%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            set_id,
            nxt,
            derivation,
            json.dumps(requirements, default=str),
            json.dumps(readiness_rules or [], default=str),
            json.dumps(weights or {}, default=str),
            missing_data_policy,
            bool(imported_from_ja),
        ),
    )
    row = _row(cur.fetchone())
    _audit(cur, company_code=company, action="version_drafted", actor_phone=actor_phone, reason=reason, subject_type="requirement_set_version", subject_id=str(row["version_id"]))
    return {"ok": True, "version": row, "immutable": False, **honesty_payload(company_code=company)}


def publish_version(cur: Any, *, company_code: str, actor_phone: str, version_id: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM talent_role_requirement_set_versions_pt3 WHERE company_code=%s AND version_id=%s", (company, version_id))
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "version_not_found"}
    ver = _row(row)
    if str(ver.get("status")) == "published":
        return {"ok": False, "error": "already_published", "immutable": True}
    err = _validate_requirements(
        list(_json(ver.get("requirements")) or []),
        derivation=str(ver.get("derivation")),
        weights=dict(_json(ver.get("weights")) or {}),
        missing_data_policy=str(ver.get("missing_data_policy") or "insufficient"),
    )
    if err:
        return err
    cur.execute(
        """
        UPDATE talent_role_requirement_set_versions_pt3
           SET status='published', published_at=now(), published_by_phone=%s, publish_reason=%s
         WHERE version_id=%s RETURNING *
        """,
        (_digits(actor_phone), str(reason).strip()[:500], version_id),
    )
    published = _row(cur.fetchone())
    cur.execute(
        "UPDATE talent_role_requirement_sets_pt3 SET status='published', current_version=%s, updated_at=now() WHERE set_id=%s",
        (published.get("version"), published.get("set_id")),
    )
    _audit(cur, company_code=company, action="version_published", actor_phone=actor_phone, reason=reason, subject_type="requirement_set_version", subject_id=str(version_id), payload={"immutable": True})
    return {"ok": True, "version": published, "immutable": True, **honesty_payload(company_code=company)}


def list_sets(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_talent_role_fit_pt3_schema(cur)
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM talent_role_requirement_sets_pt3 WHERE company_code=%s ORDER BY created_at", (company,))
    return {"ok": True, "sets": [_row(r) for r in (cur.fetchall() or [])], **honesty_payload(company_code=company)}


def get_published_version(cur: Any, *, company_code: str, set_id: str | None = None, version_id: str | None = None) -> dict[str, Any] | None:
    company = company_code_norm(company_code)
    if version_id:
        cur.execute(
            "SELECT * FROM talent_role_requirement_set_versions_pt3 WHERE company_code=%s AND version_id=%s AND status='published'",
            (company, version_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM talent_role_requirement_set_versions_pt3
             WHERE company_code=%s AND set_id=%s AND status='published'
             ORDER BY version DESC LIMIT 1
            """,
            (company, set_id),
        )
    row = cur.fetchone()
    return _row(row) if row else None


def import_draft_from_ja(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    job_profile_id: str,
    name_en: str | None = None,
    name_ar: str | None = None,
    reason: str = "import JA requirements as draft",
) -> dict[str, Any]:
    """JA may provide/import requirements as a draft. PT never writes scores back."""
    ja_gate = ja_available(company_code)
    if not ja_gate.get("ok"):
        return {"ok": False, "error": "job_architecture_unavailable", "role_fit": "unavailable", **honesty_payload(company_code=company_code)}
    import job_architecture_c1 as ja

    company = company_code_norm(company_code)
    ja.ensure_job_architecture_c1_schema(cur)
    cur.execute("SELECT * FROM ja_job_profile WHERE company_code=%s AND profile_id=%s", (company, job_profile_id))
    profile = cur.fetchone()
    if not profile:
        return {"ok": False, "error": "ja_profile_not_found"}
    profile = _row(profile)
    cur.execute(
        """
        SELECT optional_requirements, edge_type, notes_en, notes_ar
          FROM ja_career_edge
         WHERE company_code=%s AND to_profile_id=%s
        """,
        (company, job_profile_id),
    )
    edges = [_row(r) for r in (cur.fetchall() or [])]
    requirements: list[dict[str, Any]] = []
    for i, edge in enumerate(edges):
        reqs = _json(edge.get("optional_requirements")) or {}
        if isinstance(reqs, dict):
            for kind in REQUIREMENT_KINDS:
                for item in reqs.get(kind) or reqs.get(f"{kind}s") or []:
                    code = item if isinstance(item, str) else str((item or {}).get("code") or (item or {}).get("id") or "")
                    if not code:
                        continue
                    requirements.append(
                        {
                            "id": f"{kind}-{code}-{i}",
                            "kind": kind,
                            "code": code,
                            "priority": str((item or {}).get("priority") or "preferred") if isinstance(item, dict) else "preferred",
                            "level_or_rule": (item or {}).get("level") if isinstance(item, dict) else None,
                        }
                    )
    if not requirements:
        requirements = [
            {
                "id": "skill-placeholder",
                "kind": "skill",
                "code": str(profile.get("code") or "TARGET"),
                "priority": "preferred",
                "level_or_rule": None,
                "imported_empty_honest": True,
            }
        ]
    created = create_requirement_set(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        name_en=name_en or f"{profile.get('name_en') or profile.get('code')} requirements",
        name_ar=name_ar or profile.get("name_ar"),
        job_profile_id=str(job_profile_id),
        reason=reason,
    )
    if not created.get("ok"):
        return created
    draft = save_draft_version(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        set_id=str(created["set"]["set_id"]),
        requirements=requirements,
        imported_from_ja=True,
        reason=reason,
    )
    return {
        "ok": True,
        "set": created["set"],
        "version": draft.get("version"),
        "imported_as_draft": True,
        "ja_written": False,
        **honesty_payload(company_code=company),
    }


def _human_readiness(cur: Any, *, company: str, employee_key: str, critical_role_id: str | None) -> str | None:
    if not critical_role_id:
        return None
    cur.execute(
        """
        SELECT readiness FROM talent_successor_nominations
         WHERE company_code=%s AND employee_key=%s AND critical_role_id=%s AND status='active'
         ORDER BY updated_at DESC LIMIT 1
        """,
        (company, employee_key, critical_role_id),
    )
    row = cur.fetchone()
    return str(_row(row).get("readiness")) if row else None


def _skill_state(cur: Any, *, company: str, employee_key: str, code: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT skill_code, state, proficiency_level, source
          FROM talent_skills
         WHERE company_code=%s AND employee_key=%s AND upper(skill_code)=upper(%s) AND status='active'
         ORDER BY version DESC LIMIT 1
        """,
        (company, employee_key, code),
    )
    row = cur.fetchone()
    return _row(row) if row else None


def _evaluate_requirement(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    req: dict[str, Any],
    contracts: dict[str, bool],
    evidence_items: list[dict[str, Any]],
    ja_on: bool,
) -> dict[str, Any]:
    kind = str(req.get("kind"))
    code = str(req.get("code") or req.get("id") or "")
    level = req.get("level_or_rule")
    allow_claimed = bool(req.get("allow_claimed"))
    result = {
        "id": req.get("id"),
        "kind": kind,
        "code": code,
        "priority": req.get("priority") or "required",
        "outcome": "not_assessed",
        "evidence": None,
        "reason": None,
    }
    if kind == "assessment" and not contracts.get("assessment_as_evidence_v1"):
        result["outcome"] = "not_permitted"
        result["reason"] = "assessment_as_evidence_v1_off"
        return result
    if kind == "performance_evidence" and not contracts.get("performance_outcome_as_evidence_v1"):
        result["outcome"] = "not_permitted"
        result["reason"] = "performance_outcome_as_evidence_v1_off"
        return result
    if kind in {"certification"} and not contracts.get("learning_cert_as_evidence_v1"):
        # certifications may still exist as Talent evidence kinds without Learning consume
        pass
    if kind == "experience":
        if not ja_on:
            result["outcome"] = "not_assessed"
            result["reason"] = "experience_requires_ja_assignment_history"
            return result
        import job_architecture_c1 as ja

        asg = ja.resolve_assignment_as_of(cur, company_code=company, employee_key=employee_key, as_of=__import__("datetime").date.today())
        if asg.get("ok") and asg.get("assignment"):
            result["outcome"] = "met" if not level else "partial"
            result["evidence"] = {"authority": "ja_employment_assignment", "id": str((asg.get("assignment") or {}).get("assignment_id"))}
        else:
            result["outcome"] = "not_assessed"
            result["reason"] = "no_ja_assignment"
        return result
    if kind == "skill":
        skill = _skill_state(cur, company=company, employee_key=employee_key, code=code)
        if not skill:
            result["outcome"] = "not_assessed"
            result["reason"] = "skill_evidence_missing"
            return result
        if skill.get("state") == "claimed" and not allow_claimed:
            result["outcome"] = "not_permitted"
            result["reason"] = "claimed_skill_not_verified"
            result["evidence"] = {"authority": "talent_skills", "state": "claimed"}
            return result
        if level and str(skill.get("proficiency_level") or "").lower() != str(level).lower() and skill.get("state") in {"verified", "assessed"}:
            result["outcome"] = "partial"
        else:
            result["outcome"] = "met" if skill.get("state") in {"verified", "assessed"} or allow_claimed else "partial"
        result["evidence"] = {"authority": "talent_skills", "state": skill.get("state"), "level": skill.get("proficiency_level")}
        return result

    match = None
    for item in evidence_items:
        if item.get("evidence_kind") != kind and not (kind == "competency" and item.get("evidence_kind") == "competency"):
            if item.get("evidence_kind") != kind:
                continue
        if item.get("provenance_class") == "AI-SYNTHESIZED":
            continue
        if code and code.lower() not in {str(item.get("source_id") or "").lower(), str((item.get("metadata") or {}).get("code") or "").lower()}:
            if str(item.get("evidence_kind")) != kind:
                continue
        match = item
        break
    if not match:
        # kind-only match (honest: present vs missing, not a fake percent)
        match = next((e for e in evidence_items if e.get("evidence_kind") == kind and e.get("provenance_class") != "AI-SYNTHESIZED"), None)
    if not match:
        result["outcome"] = "not_assessed"
        result["reason"] = "evidence_missing"
        return result
    result["evidence"] = {
        "authority": match.get("source_authority"),
        "id": match.get("source_id"),
        "provenance_class": match.get("provenance_class"),
    }
    result["outcome"] = "met" if not level else "partial"
    return result


def _overall_fit(results: list[dict[str, Any]], *, ja_required: bool, ja_on: bool) -> str:
    if ja_required and not ja_on:
        return "unavailable"
    required = [r for r in results if r.get("priority") == "required"]
    if not required:
        required = results
    if any(r.get("outcome") == "not_permitted" for r in required) and all(r.get("outcome") in {"not_permitted", "not_assessed"} for r in required):
        return "not_assessed"
    if any(r.get("outcome") == "not_assessed" for r in required):
        return "not_assessed"
    if any(r.get("outcome") == "gap" for r in required):
        return "gaps"
    if any(r.get("outcome") == "partial" for r in required):
        return "partial_fit"
    if required and all(r.get("outcome") == "met" for r in required):
        return "strong_fit"
    if any(r.get("outcome") == "met" for r in results):
        return "partial_fit"
    return "not_assessed"


def _suggest_readiness(overall: str, results: list[dict[str, Any]]) -> str:
    if overall == "unavailable":
        return "unassessed"
    if overall == "not_assessed":
        return "unassessed"
    if overall == "strong_fit":
        return "ready_now"
    if overall == "partial_fit":
        return "ready_lt_1y"
    if any(r.get("outcome") == "gap" and r.get("priority") == "required" for r in results):
        return "longer_term"
    return "ready_1_2y"


def evaluate_role_fit(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    set_id: str | None = None,
    version_id: str | None = None,
    can_see_sensitive: bool = True,
    reason: str = "evaluate role fit",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_talent_role_fit_pt3_schema(cur)
    version = get_published_version(cur, company_code=company, set_id=set_id, version_id=version_id)
    if not version:
        return {"ok": False, "error": "published_version_required"}
    cur.execute("SELECT * FROM talent_role_requirement_sets_pt3 WHERE company_code=%s AND set_id=%s", (company, version.get("set_id")))
    target = _row(cur.fetchone())
    ja_required = bool(target.get("job_profile_id"))
    ja_on = ja_available(company).get("ok") is True
    if ja_required and not ja_on:
        graph = {
            "subject": "role_fit",
            "set_id": str(version.get("set_id")),
            "version_id": str(version.get("version_id")),
            "version": version.get("version"),
            "job_profile_id": target.get("job_profile_id"),
            "overall_fit": "unavailable",
            "reason": "job_architecture_off",
            "requirement_results": [],
            "missing_evidence": [{"reason": "ja_off"}],
            "contradictions_reconciled": False,
            "ja_written": False,
            "weighted_pct": None,
        }
        cur.execute(
            """
            INSERT INTO talent_role_fit_evaluations_pt3 (
              company_code, employee_key, set_id, version_id, version, overall_fit, requirement_results,
              readiness_suggestion, human_readiness, why
            ) VALUES (%s,%s,%s,%s,%s,'unavailable','[]'::jsonb,'unassessed',%s,%s::jsonb)
            ON CONFLICT (company_code, employee_key, version_id) DO UPDATE SET
              overall_fit='unavailable', readiness_suggestion='unassessed', why=EXCLUDED.why, as_of=now()
            RETURNING *
            """,
            (
                company,
                employee_key,
                version.get("set_id"),
                version.get("version_id"),
                version.get("version"),
                _human_readiness(cur, company=company, employee_key=employee_key, critical_role_id=target.get("critical_role_id")),
                json.dumps(graph, default=str),
            ),
        )
        stored = _row(cur.fetchone())
        return {
            "ok": True,
            "evaluation": stored,
            "overall_fit": "unavailable",
            "why": graph,
            "talent_continues": True,
            "ja_written": False,
            "c6_readiness_written": False,
            **honesty_payload(company_code=company),
        }

    contracts = idx.get_consume_contracts(cur, company)
    evidence = idx.list_evidence(
        cur,
        company_code=company,
        employee_key=employee_key,
        actor_role="hr",
        has_talent_read=True,
        can_see_sensitive=can_see_sensitive,
        can_see_performance=True,
    )
    items = [e for e in (evidence.get("evidence") or []) if e.get("visible")]
    results = [
        _evaluate_requirement(cur, company=company, employee_key=employee_key, req=req, contracts=contracts, evidence_items=items, ja_on=ja_on)
        for req in (_json(version.get("requirements")) or [])
        if isinstance(req, dict)
    ]
    overall = _overall_fit(results, ja_required=ja_required, ja_on=ja_on)
    weighted_pct = None
    if str(version.get("derivation")) == "weighted_v1":
        weights = dict(_json(version.get("weights")) or {})
        acc = 0.0
        used = 0.0
        missing_policy = str(version.get("missing_data_policy") or "insufficient")
        for req_result in results:
            rid = str(req_result.get("id"))
            w = float(weights.get(rid) or 0)
            if req_result.get("outcome") in {"not_assessed", "not_permitted"}:
                if missing_policy == "insufficient":
                    overall = "not_assessed"
                    weighted_pct = None
                    break
                continue
            score = {"met": 100.0, "partial": 50.0, "gap": 0.0}.get(str(req_result.get("outcome")), None)
            if score is None:
                if missing_policy == "insufficient":
                    overall = "not_assessed"
                    weighted_pct = None
                    break
                continue
            acc += w * score
            used += w
        else:
            if used <= 0:
                overall = "not_assessed"
                weighted_pct = None
            else:
                weighted_pct = round(acc / used if missing_policy == "exclude_renormalize" else acc, 4)
    suggestion = _suggest_readiness(overall, results)
    human = _human_readiness(cur, company=company, employee_key=employee_key, critical_role_id=target.get("critical_role_id"))
    graph = {
        "subject": "role_fit",
        "set_id": str(version.get("set_id")),
        "version_id": str(version.get("version_id")),
        "version": version.get("version"),
        "model_id": str(version.get("set_id")),
        "job_profile_id": target.get("job_profile_id"),
        "critical_role_id": target.get("critical_role_id"),
        "derivation": version.get("derivation"),
        "evidence_consumed": [r.get("evidence") for r in results if r.get("evidence")],
        "evidence_excluded": [r for r in results if r.get("outcome") == "not_permitted"],
        "missing_evidence": [r for r in results if r.get("outcome") == "not_assessed"],
        "requirement_results": results,
        "overall_fit": overall,
        "weighted_pct": weighted_pct,
        "readiness_suggestion": suggestion,
        "human_readiness": human,
        "human_readiness_authoritative": True,
        "readiness_overwritten": False,
        "ja_written": False,
        "contradictions_reconciled": False,
        "role_fit_is_not_readiness": True,
        "role_fit_is_not_promotion_eligibility": True,
    }
    cur.execute(
        """
        INSERT INTO talent_role_fit_evaluations_pt3 (
          company_code, employee_key, set_id, version_id, version, overall_fit, weighted_pct,
          requirement_results, readiness_suggestion, human_readiness, why
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, employee_key, version_id) DO UPDATE SET
          overall_fit=EXCLUDED.overall_fit,
          weighted_pct=EXCLUDED.weighted_pct,
          requirement_results=EXCLUDED.requirement_results,
          readiness_suggestion=EXCLUDED.readiness_suggestion,
          human_readiness=EXCLUDED.human_readiness,
          why=EXCLUDED.why,
          as_of=now()
        RETURNING *
        """,
        (
            company,
            employee_key,
            version.get("set_id"),
            version.get("version_id"),
            version.get("version"),
            overall,
            weighted_pct,
            json.dumps(results, default=str),
            suggestion,
            human,
            json.dumps(graph, default=str),
        ),
    )
    stored = _row(cur.fetchone())
    _audit(cur, company_code=company, action="role_fit_evaluated", actor_phone=actor_phone, reason=reason, subject_type="evaluation", subject_id=str(stored.get("evaluation_id")), payload={"overall_fit": overall})
    return {
        "ok": True,
        "evaluation": stored,
        "overall_fit": overall,
        "readiness_suggestion": suggestion,
        "human_readiness": human,
        "human_readiness_authoritative": True,
        "c6_readiness_written": False,
        "ja_written": False,
        "why": graph,
        **honesty_payload(company_code=company),
    }


def list_evaluations(cur: Any, *, company_code: str, set_id: str | None = None, overall_fit: str | None = None) -> dict[str, Any]:
    ensure_talent_role_fit_pt3_schema(cur)
    company = company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if set_id:
        where.append("set_id=%s")
        params.append(set_id)
    if overall_fit:
        where.append("overall_fit=%s")
        params.append(overall_fit)
    cur.execute(
        f"SELECT * FROM talent_role_fit_evaluations_pt3 WHERE {' AND '.join(where)} ORDER BY as_of DESC",
        params,
    )
    return {
        "ok": True,
        "evaluations": [_row(r) for r in (cur.fetchall() or [])],
        "master_fit_score": None,
        **honesty_payload(company_code=company),
    }


def list_role_fit_candidates(cur: Any, *, company_code: str, set_id: str) -> dict[str, Any]:
    """Strongest candidates = explainable categories, not an opaque rank score."""
    listed = list_evaluations(cur, company_code=company_code, set_id=set_id)
    order = {"strong_fit": 0, "partial_fit": 1, "gaps": 2, "not_assessed": 3, "unavailable": 4}
    rows = sorted(listed.get("evaluations") or [], key=lambda r: order.get(str(r.get("overall_fit")), 9))
    return {
        "ok": True,
        "candidates": rows,
        "silent_ranking": False,
        "master_fit_score": None,
        **honesty_payload(company_code=company_code),
    }
