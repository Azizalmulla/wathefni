"""Versioned, application-scoped facts extracted from one canonical CV.

This layer is intentionally separate from job matching.  It answers only
"what does this CV say?" and preserves source excerpts.  Ranking may map these
facts to job criteria, but must never use candidate-global profile state as the
authority for an application.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any


CV_FACTS_CONTRACT_VERSION = "application-cv-facts-v1"
CV_FACTS_EXTRACTOR_VERSION = "cv-facts-deterministic-v1"
READY_STATUS = "ready"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_cv_fact_snapshots (
  facts_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id uuid NOT NULL,
  company_code text NOT NULL,
  app_key text NOT NULL,
  document_id text NOT NULL,
  source_content_sha256 text NOT NULL,
  extracted_text_hash text NOT NULL,
  facts_hash text NOT NULL,
  facts jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  confidence numeric(5,4),
  failure_reason text,
  contract_version text NOT NULL DEFAULT 'application-cv-facts-v1',
  extractor_version text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_current boolean NOT NULL DEFAULT true,
  materialized_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (
    company_code, app_key, document_id, source_content_sha256,
    contract_version, extractor_version
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_application_cv_facts_current
  ON application_cv_fact_snapshots(company_code, app_key)
  WHERE is_current=true;
CREATE INDEX IF NOT EXISTS idx_application_cv_facts_status
  ON application_cv_fact_snapshots(company_code, status, updated_at DESC);

ALTER TABLE application_cv_evidence_materializations
  ADD COLUMN IF NOT EXISTS facts_id uuid;
ALTER TABLE application_cv_evidence_materializations
  ADD COLUMN IF NOT EXISTS facts_status text;
ALTER TABLE application_cv_evidence_materializations
  ADD COLUMN IF NOT EXISTS facts_contract_version text;
ALTER TABLE application_cv_evidence_materializations
  ADD COLUMN IF NOT EXISTS facts_hash text;
"""

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_HEADINGS = {
    "skills": ("skills", "key skills", "technical skills", "competencies", "المهارات", "مهارات"),
    "experience": ("experience", "work experience", "employment", "professional experience", "الخبرة", "الخبرات"),
    "education": ("education", "academic background", "qualifications", "التعليم", "المؤهلات"),
    "certifications": ("certifications", "certificates", "licenses", "الشهادات"),
    "languages": ("languages", "language", "اللغات"),
    "projects": ("projects", "selected projects", "المشاريع"),
}


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def facts_hash(facts: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(facts).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _normalized_lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [re.sub(r"[ \t]+", " ", line).strip() for line in raw.split("\n")]


def _heading_key(line: str) -> str | None:
    normalized = re.sub(r"[:：\s]+$", "", str(line or "").strip()).lower()
    for key, aliases in _HEADINGS.items():
        if normalized in aliases:
            return key
    return None


def _sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in _normalized_lines(text):
        if not line:
            continue
        heading = _heading_key(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _split_items(lines: list[str], *, max_items: int = 30) -> list[str]:
    items: list[str] = []
    for line in lines:
        # DOCX extraction can concatenate bullet runs as "...Acquisition- Employee".
        parts = re.split(
            r"\s*[•▪◦●]\s*|"
            r"(?<!\w)[\-*]\s+|"
            r"(?<=[A-Za-z0-9\)])-\s+(?=[A-Z\u0600-\u06FF])",
            line,
        )
        for part in parts:
            value = re.sub(r"\s+", " ", part).strip(" \t,;:-")
            if 2 <= len(value) <= 320 and value not in items:
                items.append(value)
            if len(items) >= max_items:
                return items
    return items


def _source_fact(value: str, *, section: str, normalized: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "value": value,
        "source": {"section": section, "quote": value[:320]},
        "confidence": 0.9,
    }
    if normalized:
        result["normalized"] = normalized
    return result


def _experience_years(text: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("experience_years", "years_experience"):
        value = profile.get(key)
        try:
            if value not in (None, "") and float(value) >= 0:
                return {
                    "value": float(value),
                    "method": "structured_profile",
                    "confidence": float(profile.get("confidence") or 0.8),
                    "source": {"section": "experience", "quote": str(value)},
                }
        except (TypeError, ValueError):
            pass
    normalized = str(text or "").translate(_ARABIC_DIGITS)
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*\+?\s*(years?|yrs?|سنوات|سنة|عام|أعوام)\b",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "value": float(match.group(1)),
        "method": "explicit_text",
        "confidence": 0.95,
        "source": {"section": "experience", "quote": match.group(0)},
    }


def _profile_list(profile: dict[str, Any], key: str) -> list[str]:
    value = profile.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def extract_application_cv_facts(
    text: str,
    *,
    structured_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract job-independent facts from one CV without inferring absence."""
    content = str(text or "").strip()
    profile = structured_profile if isinstance(structured_profile, dict) else {}
    sections = _sections(content)

    skills = _split_items(sections.get("skills") or [], max_items=30)
    for value in [*_profile_list(profile, "skills"), *_profile_list(profile, "tools")]:
        if value not in skills:
            skills.append(value)
    skill_facts = [
        _source_fact(value, section="skills", normalized=re.sub(r"\s+", " ", value).strip().lower())
        for value in skills[:30]
    ]

    experience_items = _split_items(sections.get("experience") or [], max_items=30)
    role_hint = str(profile.get("role_relevant_experience") or "").strip()
    if role_hint and role_hint not in experience_items:
        experience_items.append(role_hint)
    employment: list[dict[str, Any]] = []
    if experience_items:
        first = experience_items[0]
        combined = " ".join(experience_items)
        kind = (
            "academic_or_simulated"
            if re.search(r"\b(simulated|academic|university project|coursework)\b", combined, re.I)
            else "professional_or_unspecified"
        )
        employment.append(
            {
                "role": first[:180],
                "responsibilities": experience_items[1:15],
                "experience_type": kind,
                "source": {"section": "experience", "quote": combined[:1000]},
                "confidence": 0.85 if len(experience_items) > 1 else 0.7,
            }
        )

    education_items = _split_items(sections.get("education") or [], max_items=12)
    profile_education = str(profile.get("education") or "").strip()
    if profile_education and profile_education not in education_items:
        education_items.append(profile_education)
    education = [_source_fact(value, section="education") for value in education_items]

    certifications = [
        _source_fact(value, section="certifications")
        for value in _split_items(sections.get("certifications") or [], max_items=12)
    ]
    language_values = _split_items(sections.get("languages") or [], max_items=12)
    for value in _profile_list(profile, "languages"):
        if value not in language_values:
            language_values.append(value)
    languages = [_source_fact(value, section="languages") for value in language_values]
    projects = [
        _source_fact(value, section="projects")
        for value in _split_items(sections.get("projects") or [], max_items=20)
    ]

    years = _experience_years(content, profile)
    meaningful = bool(skill_facts or employment or years or education or certifications or languages or projects)
    confidence_values = [
        float(item.get("confidence") or 0)
        for item in [*skill_facts, *employment, *education, *certifications, *languages, *projects]
    ]
    if years:
        confidence_values.append(float(years.get("confidence") or 0))
    confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.0
    return {
        "contract_version": CV_FACTS_CONTRACT_VERSION,
        "extractor_version": CV_FACTS_EXTRACTOR_VERSION,
        "status": READY_STATUS if meaningful else "review",
        "confidence": confidence,
        "skills": skill_facts,
        "employment": employment,
        "experience_years": years,
        "education": education,
        "certifications": certifications,
        "languages": languages,
        "projects": projects,
        "not_found": [
            key
            for key, value in (
                ("skills", skill_facts),
                ("employment", employment),
                ("education", education),
            )
            if not value
        ],
    }


def materialize_facts(
    cur: Any,
    *,
    evidence_id: str,
    company_code: str,
    app_key: str,
    document_id: str,
    source_content_sha256: str,
    extracted_text_hash: str,
    facts: dict[str, Any],
    actor: str,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    application = str(app_key or "").strip()
    document = str(document_id or "").strip()
    source_hash = str(source_content_sha256 or "").strip().lower()
    extracted_hash = str(extracted_text_hash or "").strip().lower()
    if not all((evidence_id, company, application, document, source_hash, extracted_hash)):
        raise ValueError("canonical_cv_facts_fields_required")
    if str(facts.get("contract_version") or "") != CV_FACTS_CONTRACT_VERSION:
        raise ValueError("canonical_cv_facts_contract_mismatch")
    digest = facts_hash(facts)
    status = str(facts.get("status") or "review")
    confidence = float(facts.get("confidence") or 0)

    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{company}:{application}:{CV_FACTS_CONTRACT_VERSION}",),
    )
    cur.execute(
        """
        UPDATE application_cv_fact_snapshots
        SET is_current=false, status='superseded', superseded_at=now(), updated_at=now()
        WHERE company_code=%s AND app_key=%s AND is_current=true
          AND NOT (
            document_id=%s AND source_content_sha256=%s
            AND contract_version=%s AND extractor_version=%s
          )
        """,
        (
            company,
            application,
            document,
            source_hash,
            CV_FACTS_CONTRACT_VERSION,
            CV_FACTS_EXTRACTOR_VERSION,
        ),
    )
    facts_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO application_cv_fact_snapshots(
          facts_id, evidence_id, company_code, app_key, document_id,
          source_content_sha256, extracted_text_hash, facts_hash, facts,
          status, confidence, failure_reason, contract_version,
          extractor_version, provenance, is_current, materialized_at,
          created_at, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,NULL,%s,%s,%s::jsonb,
          true,now(),now(),now()
        )
        ON CONFLICT (
          company_code, app_key, document_id, source_content_sha256,
          contract_version, extractor_version
        ) DO UPDATE SET
          evidence_id=EXCLUDED.evidence_id,
          extracted_text_hash=EXCLUDED.extracted_text_hash,
          facts_hash=EXCLUDED.facts_hash,
          facts=EXCLUDED.facts,
          status=EXCLUDED.status,
          confidence=EXCLUDED.confidence,
          failure_reason=NULL,
          provenance=EXCLUDED.provenance,
          is_current=true,
          materialized_at=now(),
          superseded_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            facts_id,
            evidence_id,
            company,
            application,
            document,
            source_hash,
            extracted_hash,
            digest,
            _stable_json(facts),
            status,
            confidence,
            CV_FACTS_CONTRACT_VERSION,
            CV_FACTS_EXTRACTOR_VERSION,
            _stable_json({"actor": actor, **(provenance or {})}),
        ),
    )
    row = dict(cur.fetchone() or {})
    current_id = str(row.get("facts_id") or facts_id)
    cur.execute(
        """
        UPDATE application_cv_evidence_materializations
        SET facts_id=%s, facts_status=%s, facts_contract_version=%s,
            facts_hash=%s, updated_at=now()
        WHERE evidence_id=%s AND company_code=%s AND app_key=%s
        """,
        (
            current_id,
            status,
            CV_FACTS_CONTRACT_VERSION,
            digest,
            evidence_id,
            company,
            application,
        ),
    )
    # Project clean candidate-profile-facts-v1 without re-extracting or duplicating facts.
    try:
        import candidate_profile_facts as _cpf

        snapshot = dict(row or {})
        snapshot.setdefault("facts_id", current_id)
        snapshot.setdefault("company_code", company)
        snapshot.setdefault("app_key", application)
        snapshot.setdefault("facts", facts)
        snapshot.setdefault("facts_hash", digest)
        _cpf.materialize_from_cv_snapshot(cur, snapshot)
    except Exception:
        # Profile projection must not block canonical CV fact materialization.
        pass
    return row or {
        "facts_id": current_id,
        "status": status,
        "facts_hash": digest,
        "facts": facts,
    }


def readiness_from_row(row: dict[str, Any] | None) -> dict[str, Any]:
    item = row if isinstance(row, dict) else {}
    status = str(item.get("cv_facts_status") or item.get("facts_status") or "").strip().lower()
    contract = str(
        item.get("cv_facts_contract_version") or item.get("facts_contract_version") or ""
    ).strip()
    facts_id = str(item.get("cv_facts_id") or item.get("facts_id") or "").strip()
    facts_value = item.get("application_cv_facts") or item.get("facts")
    reason = None
    if not facts_id:
        reason = "cv_facts_missing"
    elif contract != CV_FACTS_CONTRACT_VERSION:
        reason = "cv_facts_contract_stale"
    elif status != READY_STATUS:
        reason = "cv_facts_review_required" if status == "review" else "cv_facts_unavailable"
    elif not isinstance(facts_value, dict):
        reason = "cv_facts_missing"
    return {
        "ready": reason is None,
        "reason": reason,
        "status": status or "missing",
        "facts_id": facts_id or None,
        "contract_version": contract or CV_FACTS_CONTRACT_VERSION,
    }


def ranking_fields(facts: dict[str, Any] | None) -> dict[str, Any]:
    value = facts if isinstance(facts, dict) else {}
    skills = [
        str(item.get("value") or "").strip()
        for item in (value.get("skills") or [])
        if isinstance(item, dict) and str(item.get("value") or "").strip()
    ]
    employment = [item for item in (value.get("employment") or []) if isinstance(item, dict)]
    education = [
        str(item.get("value") or "").strip()
        for item in (value.get("education") or [])
        if isinstance(item, dict) and str(item.get("value") or "").strip()
    ]
    years = value.get("experience_years") if isinstance(value.get("experience_years"), dict) else {}
    return {
        "skills": skills,
        "experience_years": years.get("value"),
        "employment": employment,
        "education": education,
        "certifications": [
            str(item.get("value") or "").strip()
            for item in (value.get("certifications") or [])
            if isinstance(item, dict) and str(item.get("value") or "").strip()
        ],
        "languages": [
            str(item.get("value") or "").strip()
            for item in (value.get("languages") or [])
            if isinstance(item, dict) and str(item.get("value") or "").strip()
        ],
        "cv_facts_status": value.get("status"),
        "cv_facts_contract_version": value.get("contract_version"),
    }
