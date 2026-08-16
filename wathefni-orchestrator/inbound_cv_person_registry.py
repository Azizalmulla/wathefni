"""Wave 4: link intake subjects through Person Registry (additive).

Creates/links persons + memberships for envelope subjects without unsafe merges.
Does not own CV processing, Ranking, or Job lifecycle.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

try:
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover
    Json = dict  # type: ignore[misc, assignment]

import candidate_identity as identity

FEATURE = "WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE"
AUTHORITY_VERSION = "unified-inbound-cv-person-registry-v1"
_ID_NAMESPACE = uuid.UUID("b82e4f1a-9c0d-4e5f-a1b2-c3d4e5f60718")


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE))


def _safe_company(value: str | None) -> str:
    company = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())
    if not company:
        raise ValueError("company_scope_missing")
    return company


def _json(value: Any) -> Any:
    if Json is dict:
        return value
    return Json(value)


def stable_person_id_for_exact_contact(*, company_code: str, contact_type: str, normalized: str) -> str:
    key = f"{company_code}|{contact_type}|{normalized}"
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:person-seed:{key}"))


def ensure_or_link_person_for_subject(
    cur: Any,
    *,
    company_code: str,
    subject_id: str,
    phone: str | None = None,
    email: str | None = None,
    display_name: str | None = None,
    source: str = "intake_subject",
    force_identity_review: bool = False,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Link an intake subject to a person/membership.

    Exact phone/email reuse is allowed. Ambiguous multi-match or weak evidence
    leaves the subject in identity_review without merging.
    """

    if not enabled(environ):
        return {"ok": True, "skipped": True, "reason": "person_registry_dual_write_disabled"}

    company = _safe_company(company_code)
    identity.ensure_schema(cur)
    subject = str(subject_id or "").strip()
    if not subject:
        raise ValueError("subject_id_required")

    cur.execute(
        """
        SELECT subject_id::text, person_id::text, membership_id::text, status,
               legacy_candidate_phone
        FROM intake_subjects
        WHERE company_code=%s AND subject_id=%s
        LIMIT 1
        """,
        (company, subject),
    )
    row = cur.fetchone() or {}
    if row.get("person_id") and row.get("membership_id") and not force_identity_review:
        return {
            "ok": True,
            "skipped": False,
            "already_linked": True,
            "person_id": row.get("person_id"),
            "membership_id": row.get("membership_id"),
            "status": row.get("status"),
        }

    phone_norm = None
    email_norm = None
    try:
        if phone:
            phone_norm = identity.normalize_phone(str(phone))
    except Exception:
        phone_norm = None
    try:
        if email:
            email_norm = identity.normalize_email(str(email))
    except Exception:
        email_norm = None

    matches: list[dict[str, Any]] = []
    if phone_norm:
        cur.execute(
            """
            SELECT DISTINCT p.person_id::text, m.membership_id::text
            FROM person_contact_points c
            JOIN persons p ON p.person_id=c.person_id
            JOIN person_company_memberships m
              ON m.person_id=p.person_id AND m.company_code=c.company_code
            WHERE c.company_code=%s AND c.contact_type='phone' AND c.normalized_value=%s
              AND COALESCE(p.status,'active')='active'
            """,
            (company, phone_norm),
        )
        matches.extend([dict(r) for r in (cur.fetchall() or [])])
    if email_norm:
        cur.execute(
            """
            SELECT DISTINCT p.person_id::text, m.membership_id::text
            FROM person_contact_points c
            JOIN persons p ON p.person_id=c.person_id
            JOIN person_company_memberships m
              ON m.person_id=p.person_id AND m.company_code=c.company_code
            WHERE c.company_code=%s AND c.contact_type='email' AND c.normalized_value=%s
              AND COALESCE(p.status,'active')='active'
            """,
            (company, email_norm),
        )
        matches.extend([dict(r) for r in (cur.fetchall() or [])])

    unique: dict[str, dict[str, Any]] = {}
    for item in matches:
        key = str(item.get("person_id") or "")
        if key and key not in unique:
            unique[key] = item
    distinct = list(unique.values())

    if force_identity_review or (not phone_norm and not email_norm) or len(distinct) > 1:
        cur.execute(
            """
            UPDATE intake_subjects
            SET status='identity_review', updated_at=now()
            WHERE company_code=%s AND subject_id=%s
            """,
            (company, subject),
        )
        return {
            "ok": True,
            "skipped": False,
            "status": "identity_review",
            "reason": "ambiguous_or_insufficient_identity",
            "match_count": len(distinct),
            "person_id": None,
            "membership_id": None,
            "merged": False,
        }

    if len(distinct) == 1:
        person_id = distinct[0]["person_id"]
        membership_id = distinct[0]["membership_id"]
        outcome = "safe_exact_reuse"
    else:
        seed = phone_norm or email_norm or subject
        contact_type = "phone" if phone_norm else "email"
        person_id = stable_person_id_for_exact_contact(
            company_code=company, contact_type=contact_type, normalized=str(seed)
        )
        membership_id = str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:membership:{company}:{person_id}"))
        cur.execute(
            """
            INSERT INTO persons(person_id, display_name, preferred_locale, metadata)
            VALUES (%s,%s,'ar',%s)
            ON CONFLICT (person_id) DO NOTHING
            """,
            (person_id, display_name, _json({"authority_version": AUTHORITY_VERSION, "source": source})),
        )
        cur.execute(
            """
            INSERT INTO person_company_memberships(membership_id, person_id, company_code, source)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (membership_id) DO NOTHING
            """,
            (membership_id, person_id, company, source),
        )
        if phone_norm:
            cur.execute(
                """
                INSERT INTO person_contact_points(person_id, company_code, contact_type, raw_value, normalized_value, is_preferred)
                VALUES (%s,%s,'phone',%s,%s,true)
                ON CONFLICT DO NOTHING
                """,
                (person_id, company, phone, phone_norm),
            )
        if email_norm:
            cur.execute(
                """
                INSERT INTO person_contact_points(person_id, company_code, contact_type, raw_value, normalized_value)
                VALUES (%s,%s,'email',%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (person_id, company, email, email_norm),
            )
        outcome = "new_person"

    cur.execute(
        """
        UPDATE intake_subjects
        SET person_id=%s, membership_id=%s, status='linked',
            legacy_candidate_phone=COALESCE(legacy_candidate_phone, %s),
            updated_at=now()
        WHERE company_code=%s AND subject_id=%s
        """,
        (person_id, membership_id, phone_norm, company, subject),
    )
    return {
        "ok": True,
        "skipped": False,
        "status": "linked",
        "outcome": outcome,
        "person_id": person_id,
        "membership_id": membership_id,
        "merged": False,
        "authority_version": AUTHORITY_VERSION,
    }


__all__ = [
    "FEATURE",
    "AUTHORITY_VERSION",
    "enabled",
    "stable_person_id_for_exact_contact",
    "ensure_or_link_person_for_subject",
]
