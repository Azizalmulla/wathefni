"""Canonical Candidate Profile Facts (candidate-profile-facts-v1).

Normalizes raw application-cv-facts-v1 extraction shapes into a clean HR contract
used by person-profile API and the dashboard. Frontend must never parse
`{ value: "..." }` extraction objects.

Priority for effective values:
  HR-confirmed > extracted > grounded derived

Original extraction snapshots remain immutable; this layer projects them.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

PROFILE_FACTS_SCHEMA = "candidate-profile-facts-v1"
PROFILE_FACTS_SCHEMA_V2 = "candidate-profile-facts-v2"
SOURCE_FACTS_CONTRACT = "application-cv-facts-v1"
ALLOWED_PROFILE_SCHEMAS = frozenset({PROFILE_FACTS_SCHEMA, PROFILE_FACTS_SCHEMA_V2})

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candidate_profile_facts (
  profile_facts_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  facts_id uuid NOT NULL UNIQUE,
  company_code text NOT NULL,
  app_key text NOT NULL,
  profile_hash text NOT NULL,
  profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  schema_version text NOT NULL DEFAULT 'candidate-profile-facts-v1',
  source_facts_hash text,
  is_current boolean NOT NULL DEFAULT true,
  materialized_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_profile_facts_current
  ON candidate_profile_facts(company_code, app_key)
  WHERE is_current=true;

CREATE INDEX IF NOT EXISTS idx_candidate_profile_facts_app
  ON candidate_profile_facts(company_code, app_key, updated_at DESC);
"""

_LOCATION_RE = re.compile(
    r"\b(Kuwait|Kuwait City|Hawalli|Salmiya|Dubai|Abu Dhabi|Riyadh|Jeddah|"
    r"Doha|Manama|Muscat|Amman|Cairo|London|Remote)\b",
    re.I,
)
_DEGREE_RE = re.compile(
    r"(Bachelor|B\.?Sc|B\.?S\.|Master|M\.?Sc|MBA|Ph\.?D|Diploma|Bootcamp)"
    r"[^\n,]{0,80}(Computer Science|Software|Engineering|Information|Business|Finance|Accounting|Data|AI|Cloud)?",
    re.I,
)
_SUMMARY_NOISE = re.compile(
    r"^(skills|experience|education|languages|certifications|projects|contact)\b",
    re.I,
)


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def profile_hash(profile: dict[str, Any]) -> str:
    body = {k: v for k, v in profile.items() if k not in {"field_sources", "materialized_at"}}
    return hashlib.sha256(_stable_json(body).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("value", "label", "name", "title", "role", "degree", "school", "text", "normalized"):
            found = value.get(key)
            if isinstance(found, (str, int, float)) and str(found).strip():
                return str(found).strip()
    return ""


def _string_list(value: Any, *, limit: int = 40) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _employment_lines(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return _string_list(value, limit=limit)
    out: list[str] = []
    for item in value:
        if isinstance(item, dict):
            role = _text(item.get("role") or item.get("title"))
            company = _text(item.get("company") or item.get("employer"))
            when = " – ".join(
                part
                for part in (
                    _text(item.get("start_date") or item.get("from")),
                    _text(item.get("end_date") or item.get("to")),
                )
                if part
            )
            line = " · ".join(part for part in (role, company, when) if part)
            if line and len(line) > 220:
                line = line[:217].rstrip() + "…"
            if line:
                out.append(line)
                continue
        text = _text(item)
        if text:
            out.append(text[:220] + ("…" if len(text) > 220 else ""))
        if len(out) >= limit:
            break
    return out


def _years_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if float(value) >= 0 else None
    if isinstance(value, dict):
        return _years_number(value.get("value"))
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
        return number if number >= 0 else None
    except ValueError:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match:
            return None
        return float(match.group(1))


def normalize_extracted_fields(raw_facts: dict[str, Any] | None) -> dict[str, Any]:
    """Convert raw extraction / effective facts into clean string lists + scalars."""
    facts = raw_facts if isinstance(raw_facts, dict) else {}
    years = _years_number(facts.get("experience_years"))
    return {
        "skills": _string_list(facts.get("skills"), limit=30),
        "education": _string_list(facts.get("education"), limit=16),
        "employment": _employment_lines(facts.get("employment") or facts.get("experience"), limit=12),
        "languages": _string_list(facts.get("languages"), limit=12),
        "certifications": _string_list(facts.get("certifications"), limit=12),
        "location": _text(facts.get("location")) or None,
        "professional_summary": _text(
            facts.get("summary") or facts.get("profile_summary") or facts.get("professional_summary")
        )
        or None,
        "primary_expertise": _text(
            facts.get("primary_expertise") or facts.get("expertise") or facts.get("headline")
        )
        or None,
        "experience_years": years,
    }


def derive_grounded_fields(
    extracted: dict[str, Any],
    *,
    cv_text: str | None = None,
    classification_chip: str | None = None,
) -> dict[str, Any]:
    """Fill gaps only — never invent conflicting values over extracted content."""
    text = str(cv_text or "").strip()
    derived: dict[str, Any] = {
        "skills": [],
        "education": [],
        "employment": [],
        "languages": [],
        "certifications": [],
        "location": None,
        "professional_summary": None,
        "primary_expertise": None,
        "experience_years": None,
        "_derived_keys": [],
    }

    if not extracted.get("location") and text:
        match = _LOCATION_RE.search(text[:1200])
        if match:
            derived["location"] = match.group(1)
            derived["_derived_keys"].append("location")

    if not extracted.get("professional_summary") and text:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        # Also consider single-newline blocks (many CVs lack blank lines).
        if len(paragraphs) <= 2:
            paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        for paragraph in paragraphs[:8]:
            compact = re.sub(r"\s+", " ", paragraph).strip()
            if len(compact) < 60 or len(compact) > 600:
                continue
            if _SUMMARY_NOISE.search(compact):
                continue
            if re.search(r"@|https?://|\+\d{6,}", compact):
                continue
            if re.match(r"^[\w .'-]{2,60}$", compact):
                # Likely a bare name line.
                continue
            if "." in compact or "," in compact:
                derived["professional_summary"] = compact[:480]
                derived["_derived_keys"].append("professional_summary")
                break
        if not derived.get("professional_summary"):
            # Fallback: first long sentence-like span in the opening 1500 chars.
            opening = re.sub(r"\s+", " ", text[:1500]).strip()
            match = re.search(
                r"([A-Z][^.]{50,420}\.)",
                opening,
            )
            if match and not re.search(r"@|https?://", match.group(1)):
                derived["professional_summary"] = match.group(1).strip()
                derived["_derived_keys"].append("professional_summary")

    chip = str(classification_chip or "").strip()
    if chip:
        cleaned = re.sub(
            r"^(Confirmed|Advisory|AI suggested|AI|HR confirmed)\s*:?\s*",
            "",
            chip,
            flags=re.I,
        ).strip()
        if "·" in cleaned:
            cleaned = cleaned.split("·")[-1].strip()
        if cleaned and not re.search(r"unknown|unclassified|n/?a", cleaned, re.I):
            derived["primary_expertise"] = cleaned
            derived["_derived_keys"].append("primary_expertise")

    if not derived.get("primary_expertise"):
        for line in extracted.get("education") or []:
            match = _DEGREE_RE.search(str(line))
            if match:
                label = re.sub(r"\s+", " ", match.group(0)).strip(" ,.-")
                if label:
                    derived["primary_expertise"] = label[:120]
                    derived["_derived_keys"].append("primary_expertise")
                    break
        if not derived.get("primary_expertise"):
            for skill in extracted.get("skills") or []:
                head = str(skill).split(":", 1)[0].strip()
                if 3 <= len(head) <= 40 and not head.endswith("."):
                    derived["primary_expertise"] = head
                    derived["_derived_keys"].append("primary_expertise")
                    break

    if not extracted.get("location"):
        for line in extracted.get("education") or []:
            match = _LOCATION_RE.search(str(line))
            if match:
                derived["location"] = match.group(1)
                if "location" not in derived["_derived_keys"]:
                    derived["_derived_keys"].append("location")
                break

    return derived


def _apply_hr_path_overrides(
    canonical: dict[str, Any],
    reviews_by_path: dict[str, Any] | None,
) -> tuple[dict[str, Any], set[str]]:
    confirmed: set[str] = set()
    if not isinstance(reviews_by_path, dict) or not reviews_by_path:
        return canonical, confirmed

    path_map = {
        "skills": "skills",
        "education": "education",
        "employment": "employment",
        "experience": "employment",
        "languages": "languages",
        "certifications": "certifications",
        "location": "location",
        "summary": "professional_summary",
        "profile_summary": "professional_summary",
        "professional_summary": "professional_summary",
        "expertise": "primary_expertise",
        "primary_expertise": "primary_expertise",
        "experience_years": "experience_years",
        "years_of_experience": "experience_years",
    }
    out = dict(canonical)
    for path, event in reviews_by_path.items():
        if not isinstance(event, dict):
            continue
        if str(event.get("display_state") or "").lower() != "hr_confirmed":
            continue
        root = str(path or "").split(".", 1)[0].strip().lower()
        field = path_map.get(root)
        if not field:
            continue
        new_value = event.get("new_value")
        if field in {"skills", "education", "employment", "languages", "certifications"}:
            if isinstance(new_value, list):
                out[field] = (
                    _string_list(new_value) if field != "employment" else _employment_lines(new_value)
                )
            elif new_value is not None and "." not in str(path):
                out[field] = (
                    _string_list([new_value]) if field != "employment" else _employment_lines([new_value])
                )
        elif field == "experience_years":
            out[field] = _years_number(new_value)
        else:
            text = _text(new_value)
            out[field] = text or None
        confirmed.add(field)
    return out, confirmed


def build_canonical_profile_facts(
    *,
    raw_facts: dict[str, Any] | None,
    reviews_by_path: dict[str, Any] | None = None,
    cv_text: str | None = None,
    classification_chip: str | None = None,
    facts_id: str | None = None,
    source_facts_hash: str | None = None,
) -> dict[str, Any]:
    """Build the clean candidate-profile-facts-v1 contract."""
    extracted = normalize_extracted_fields(raw_facts)
    derived = derive_grounded_fields(
        extracted,
        cv_text=cv_text,
        classification_chip=classification_chip,
    )

    field_sources: dict[str, Any] = {}
    merged: dict[str, Any] = {}
    for key in (
        "skills",
        "education",
        "employment",
        "languages",
        "certifications",
        "location",
        "professional_summary",
        "primary_expertise",
        "experience_years",
    ):
        extracted_value = extracted.get(key)
        derived_value = derived.get(key)
        empty = extracted_value in (None, "", [])
        if not empty:
            merged[key] = extracted_value
            field_sources[key] = {"origin": "extracted"}
        elif derived_value not in (None, "", []):
            merged[key] = derived_value
            field_sources[key] = {"origin": "derived"}
        else:
            merged[key] = (
                [] if key in {"skills", "education", "employment", "languages", "certifications"} else None
            )
            field_sources[key] = {"origin": "missing"}

    merged, hr_fields = _apply_hr_path_overrides(merged, reviews_by_path)
    for key in hr_fields:
        field_sources[key] = {"origin": "hr_confirmed"}

    profile = {
        "schema": PROFILE_FACTS_SCHEMA,
        "skills": merged.get("skills") or [],
        "education": merged.get("education") or [],
        "employment": merged.get("employment") or [],
        "languages": merged.get("languages") or [],
        "certifications": merged.get("certifications") or [],
        "location": merged.get("location"),
        "professional_summary": merged.get("professional_summary"),
        "primary_expertise": merged.get("primary_expertise"),
        "experience_years": merged.get("experience_years"),
        "field_sources": field_sources,
        "source_facts_id": facts_id,
        "source_contract_version": SOURCE_FACTS_CONTRACT,
        "source_facts_hash": source_facts_hash,
    }
    profile["profile_hash"] = profile_hash(profile)
    return profile


def materialize_profile_facts(
    cur: Any,
    *,
    facts_id: str,
    company_code: str,
    app_key: str,
    profile: dict[str, Any],
    source_facts_hash: str | None = None,
) -> dict[str, Any]:
    """Persist one projection per extraction snapshot (idempotent, no new CV facts)."""
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    application = str(app_key or "").strip()
    snapshot_id = str(facts_id or "").strip()
    if not all((company, application, snapshot_id)):
        raise ValueError("candidate_profile_facts_fields_required")
    if str(profile.get("schema") or "") not in ALLOWED_PROFILE_SCHEMAS:
        raise ValueError("candidate_profile_facts_schema_mismatch")

    digest = str(profile.get("profile_hash") or profile_hash(profile))
    payload = dict(profile)
    payload["profile_hash"] = digest
    payload["materialized_at"] = datetime.now(timezone.utc).isoformat()
    schema_version = str(profile.get("schema") or PROFILE_FACTS_SCHEMA)

    cur.execute(
        """
        UPDATE candidate_profile_facts
        SET is_current=false, superseded_at=now(), updated_at=now()
        WHERE company_code=%s AND app_key=%s AND is_current=true
          AND facts_id IS DISTINCT FROM %s::uuid
        """,
        (company, application, snapshot_id),
    )
    cur.execute(
        """
        INSERT INTO candidate_profile_facts(
          facts_id, company_code, app_key, profile_hash, profile,
          schema_version, source_facts_hash, is_current,
          materialized_at, created_at, updated_at
        ) VALUES (
          %s::uuid, %s, %s, %s, %s::jsonb, %s, %s, true, now(), now(), now()
        )
        ON CONFLICT (facts_id) DO UPDATE SET
          company_code=EXCLUDED.company_code,
          app_key=EXCLUDED.app_key,
          profile_hash=EXCLUDED.profile_hash,
          profile=EXCLUDED.profile,
          schema_version=EXCLUDED.schema_version,
          source_facts_hash=EXCLUDED.source_facts_hash,
          is_current=true,
          materialized_at=now(),
          superseded_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            snapshot_id,
            company,
            application,
            digest,
            _stable_json(payload),
            schema_version,
            source_facts_hash,
        ),
    )
    return dict(cur.fetchone() or {})


def materialize_from_cv_snapshot(
    cur: Any,
    snapshot_row: dict[str, Any],
    *,
    cv_text: str | None = None,
    classification_chip: str | None = None,
    reviews_by_path: dict[str, Any] | None = None,
) -> dict[str, Any]:
    facts = snapshot_row.get("facts") if isinstance(snapshot_row.get("facts"), dict) else {}
    profile = build_canonical_profile_facts(
        raw_facts=facts,
        reviews_by_path=reviews_by_path,
        cv_text=cv_text,
        classification_chip=classification_chip,
        facts_id=str(snapshot_row.get("facts_id") or "") or None,
        source_facts_hash=str(snapshot_row.get("facts_hash") or "") or None,
    )
    return materialize_profile_facts(
        cur,
        facts_id=str(snapshot_row.get("facts_id")),
        company_code=str(snapshot_row.get("company_code")),
        app_key=str(snapshot_row.get("app_key")),
        profile=profile,
        source_facts_hash=str(snapshot_row.get("facts_hash") or "") or None,
    )


def backfill_current_snapshots(
    cur: Any,
    *,
    company_code: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Idempotent projection of all current extraction snapshots. No re-extraction."""
    ensure_schema(cur)
    params: list[Any] = []
    where = "WHERE s.is_current=true"
    if company_code:
        where += " AND s.company_code=%s"
        params.append(str(company_code).strip().upper())
    sql = f"""
        SELECT s.facts_id, s.company_code, s.app_key, s.facts, s.facts_hash,
               s.contract_version, s.extractor_version, s.document_id
        FROM application_cv_fact_snapshots s
        {where}
        ORDER BY s.materialized_at ASC NULLS LAST
    """
    if limit and int(limit) > 0:
        sql += " LIMIT %s"
        params.append(int(limit))
    cur.execute(sql, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    written = 0
    unchanged = 0
    for row in rows:
        cv_text = None
        # Prefer semantic text already indexed for the application (no re-extraction).
        try:
            cur.execute("SAVEPOINT cpf_semantic")
            cur.execute(
                """
                SELECT left(coalesce(content, ''), 12000) AS content
                FROM semantic_documents
                WHERE entity_type='application' AND entity_key=%s
                LIMIT 1
                """,
                (row["app_key"],),
            )
            semantic = cur.fetchone()
            if semantic and semantic.get("content"):
                cv_text = str(semantic["content"])
            cur.execute("RELEASE SAVEPOINT cpf_semantic")
        except Exception:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT cpf_semantic")
            except Exception:
                pass
            cv_text = None

        profile = build_canonical_profile_facts(
            raw_facts=row.get("facts") if isinstance(row.get("facts"), dict) else {},
            cv_text=cv_text,
            facts_id=str(row.get("facts_id")),
            source_facts_hash=str(row.get("facts_hash") or "") or None,
        )
        cur.execute(
            "SELECT profile_hash FROM candidate_profile_facts WHERE facts_id=%s::uuid LIMIT 1",
            (row["facts_id"],),
        )
        existing = cur.fetchone()
        if existing and str(existing.get("profile_hash") or "") == str(profile.get("profile_hash") or ""):
            materialize_profile_facts(
                cur,
                facts_id=str(row["facts_id"]),
                company_code=str(row["company_code"]),
                app_key=str(row["app_key"]),
                profile=profile,
                source_facts_hash=str(row.get("facts_hash") or "") or None,
            )
            unchanged += 1
            continue
        materialize_profile_facts(
            cur,
            facts_id=str(row["facts_id"]),
            company_code=str(row["company_code"]),
            app_key=str(row["app_key"]),
            profile=profile,
            source_facts_hash=str(row.get("facts_hash") or "") or None,
        )
        written += 1
    return {
        "ok": True,
        "scanned": len(rows),
        "written": written,
        "unchanged_or_refreshed": unchanged,
        "schema": PROFILE_FACTS_SCHEMA,
    }


def experience_years_label(years: Any, *, locale: str = "en") -> str | None:
    number = _years_number(years)
    if number is None:
        return None
    if float(number).is_integer():
        number_i = int(number)
        if locale == "ar":
            return f"{number_i} سنوات" if number_i != 1 else "سنة واحدة"
        return f"{number_i} years" if number_i != 1 else "1 year"
    if locale == "ar":
        return f"{number} سنوات"
    return f"{number} years"


__all__ = [
    "ALLOWED_PROFILE_SCHEMAS",
    "PROFILE_FACTS_SCHEMA",
    "PROFILE_FACTS_SCHEMA_V2",
    "backfill_current_snapshots",
    "build_canonical_profile_facts",
    "ensure_schema",
    "experience_years_label",
    "materialize_from_cv_snapshot",
    "materialize_profile_facts",
    "normalize_extracted_fields",
    "profile_hash",
]
