"""Wave 4 Talent Pool authority (additive, governed entries).

Owns talent_pool_entries for person/subject membership. Does not create Job
applications or rewrite Ranking evidence.
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

FEATURE = "WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES"
AUTHORITY_VERSION = "unified-talent-pool-authority-v1"
_ID_NAMESPACE = uuid.UUID("c93f5a2b-0d1e-4f60-b2c3-d4e5f6071829")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS talent_pool_entries (
  entry_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  person_id uuid,
  membership_id uuid,
  subject_id uuid,
  status text NOT NULL DEFAULT 'active',
  actionable boolean NOT NULL DEFAULT false,
  current_cv_version_id uuid,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, subject_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_talent_pool_entries_membership
  ON talent_pool_entries(company_code, membership_id)
  WHERE membership_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_talent_pool_entries_company_status
  ON talent_pool_entries(company_code, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_talent_pool_entries_person
  ON talent_pool_entries(company_code, person_id)
  WHERE person_id IS NOT NULL;
"""


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


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def stable_entry_id(*, company_code: str, subject_id: str | None, membership_id: str | None) -> str:
    key = f"{company_code}|{subject_id or ''}|{membership_id or ''}"
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:talent-pool-entry:{key}"))


def upsert_talent_pool_entry(
    cur: Any,
    *,
    company_code: str,
    subject_id: str | None = None,
    person_id: str | None = None,
    membership_id: str | None = None,
    current_cv_version_id: str | None = None,
    actionable: bool = False,
    status: str = "active",
    provenance: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not enabled(environ):
        return {"ok": True, "skipped": True, "reason": "talent_pool_entries_disabled"}
    company = _safe_company(company_code)
    if not subject_id and not membership_id:
        raise ValueError("subject_or_membership_required")
    ensure_schema(cur)
    # Provisional / identity-review subjects are never actionable.
    actionable = bool(actionable) and bool(person_id and membership_id)
    prov = _json(
        {
            **(provenance or {}),
            "authority_version": AUTHORITY_VERSION,
            "creates_job_application": False,
        }
    )

    # One membership → one Talent Pool entry. Prefer reuse when membership already pinned.
    if membership_id:
        cur.execute(
            """
            SELECT entry_id::text AS entry_id, actionable, status, subject_id::text AS subject_id
            FROM talent_pool_entries
            WHERE company_code=%s AND membership_id=%s
            LIMIT 1
            """,
            (company, membership_id),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE talent_pool_entries
                SET person_id=COALESCE(%s, person_id),
                    subject_id=COALESCE(%s, subject_id),
                    status=%s,
                    actionable=%s,
                    current_cv_version_id=COALESCE(%s, current_cv_version_id),
                    provenance=%s,
                    updated_at=now()
                WHERE company_code=%s AND entry_id=%s
                RETURNING entry_id::text AS entry_id, actionable, status
                """,
                (
                    person_id,
                    subject_id,
                    status,
                    actionable,
                    current_cv_version_id,
                    prov,
                    company,
                    existing.get("entry_id"),
                ),
            )
            row = cur.fetchone() or existing
            return {
                "ok": True,
                "skipped": False,
                "entry_id": row.get("entry_id"),
                "actionable": bool(row.get("actionable")),
                "status": row.get("status"),
                "reused_membership": True,
                "authority_version": AUTHORITY_VERSION,
            }

    entry_id = stable_entry_id(
        company_code=company, subject_id=subject_id, membership_id=membership_id
    )
    cur.execute(
        """
        INSERT INTO talent_pool_entries
          (entry_id, company_code, person_id, membership_id, subject_id, status,
           actionable, current_cv_version_id, provenance)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, subject_id)
        DO UPDATE SET
          person_id=COALESCE(EXCLUDED.person_id, talent_pool_entries.person_id),
          membership_id=COALESCE(EXCLUDED.membership_id, talent_pool_entries.membership_id),
          status=EXCLUDED.status,
          actionable=EXCLUDED.actionable,
          current_cv_version_id=COALESCE(EXCLUDED.current_cv_version_id, talent_pool_entries.current_cv_version_id),
          provenance=EXCLUDED.provenance,
          updated_at=now()
        RETURNING entry_id::text AS entry_id, actionable, status
        """,
        (
            entry_id,
            company,
            person_id,
            membership_id,
            subject_id,
            status,
            actionable,
            current_cv_version_id,
            prov,
        ),
    )
    row = cur.fetchone() or {"entry_id": entry_id, "actionable": actionable, "status": status}
    return {
        "ok": True,
        "skipped": False,
        "entry_id": row.get("entry_id"),
        "actionable": bool(row.get("actionable")),
        "status": row.get("status"),
        "authority_version": AUTHORITY_VERSION,
    }


def pin_current_cv_version(
    cur: Any,
    *,
    company_code: str,
    entry_id: str,
    cv_version_id: str,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not enabled(environ):
        return {"ok": True, "skipped": True, "reason": "talent_pool_entries_disabled"}
    company = _safe_company(company_code)
    cur.execute(
        """
        UPDATE talent_pool_entries
        SET current_cv_version_id=%s, updated_at=now()
        WHERE company_code=%s AND entry_id=%s
        RETURNING entry_id::text AS entry_id, current_cv_version_id::text AS current_cv_version_id
        """,
        (cv_version_id, company, entry_id),
    )
    row = cur.fetchone()
    return {"ok": bool(row), "entry": dict(row) if row else None}


__all__ = [
    "FEATURE",
    "AUTHORITY_VERSION",
    "enabled",
    "ensure_schema",
    "stable_entry_id",
    "upsert_talent_pool_entry",
    "pin_current_cv_version",
]
