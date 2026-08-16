"""Wave 4 exact Job binding authority (additive).

Creates application_job_bindings and application_cv_bindings only after exact
Job selection + confirmation. Does not cut over Stage B live create path;
offers a shared promote helper for dual-write / future callers.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover
    Json = dict  # type: ignore[misc, assignment]

FEATURE = "WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY"
AUTHORITY_VERSION = "unified-job-binding-authority-v1"
UTC = timezone.utc
_ID_NAMESPACE = uuid.UUID("d04a6b3c-1e2f-5071-c3d4-e5f60718293a")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intake_consent_events (
  consent_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  subject_id uuid,
  person_id uuid,
  actor_type text NOT NULL,
  actor_id text,
  consent_kind text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_intake_consent_events_company
  ON intake_consent_events(company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS application_job_bindings (
  binding_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  position_code text NOT NULL,
  apply_code text,
  job_id text,
  verified boolean NOT NULL DEFAULT false,
  verification_mode text NOT NULL DEFAULT 'exact_confirm',
  consent_id uuid,
  person_id uuid,
  membership_id uuid,
  subject_id uuid,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, app_key)
);
CREATE INDEX IF NOT EXISTS idx_application_job_bindings_verified
  ON application_job_bindings(company_code, verified, position_code);

CREATE TABLE IF NOT EXISTS application_cv_bindings (
  binding_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  cv_version_id uuid NOT NULL,
  pinned boolean NOT NULL DEFAULT true,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, app_key, cv_version_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_application_cv_bindings_pinned
  ON application_cv_bindings(company_code, app_key)
  WHERE pinned=true;
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


def record_consent(
    cur: Any,
    *,
    company_code: str,
    consent_kind: str,
    actor_type: str,
    actor_id: str | None = None,
    subject_id: str | None = None,
    person_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> str:
    consent_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO intake_consent_events
          (consent_id, company_code, subject_id, person_id, actor_type, actor_id, consent_kind, evidence)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            consent_id,
            _safe_company(company_code),
            subject_id,
            person_id,
            actor_type,
            actor_id,
            consent_kind,
            _json(evidence or {}),
        ),
    )
    return consent_id


def preflight_duplicate_application(
    cur: Any,
    *,
    company_code: str,
    person_id: str | None,
    phone: str | None,
    position_code: str,
) -> dict[str, Any]:
    """Fail closed on an existing active (non-held) application for same person/Job."""

    company = _safe_company(company_code)
    position = str(position_code or "").strip()
    if not position:
        return {"ok": False, "error": "position_required"}
    held = ("needs_role", "import_review", "import_archived")
    if person_id:
        cur.execute(
            """
            SELECT app_key, status FROM applications
            WHERE company_code=%s AND person_id=%s AND position_code=%s
              AND status NOT IN %s
            LIMIT 1
            """,
            (company, person_id, position, held),
        )
    elif phone:
        cur.execute(
            """
            SELECT app_key, status FROM applications
            WHERE company_code=%s AND phone=%s AND position_code=%s
              AND status NOT IN %s
            LIMIT 1
            """,
            (company, phone, position, held),
        )
    else:
        return {"ok": True, "duplicate": False}
    row = cur.fetchone()
    if row:
        return {
            "ok": False,
            "duplicate": True,
            "error": "duplicate_active_application",
            "app_key": row.get("app_key"),
            "status": row.get("status"),
        }
    return {"ok": True, "duplicate": False}


def bind_application_to_job(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    position_code: str,
    apply_code: str | None = None,
    job_id: str | None = None,
    human_confirmed: bool = False,
    consent_id: str | None = None,
    person_id: str | None = None,
    membership_id: str | None = None,
    subject_id: str | None = None,
    cv_version_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record verified Job + optional CV bindings. Does not invent applications."""

    if not enabled(environ):
        return {"ok": True, "skipped": True, "reason": "job_binding_authority_disabled"}
    if not human_confirmed:
        return {"ok": False, "error": "exact_job_confirmation_required"}
    company = _safe_company(company_code)
    app = str(app_key or "").strip()
    position = str(position_code or "").strip()
    if not app or not position:
        return {"ok": False, "error": "app_and_position_required"}
    ensure_schema(cur)

    dup = preflight_duplicate_application(
        cur,
        company_code=company,
        person_id=person_id,
        phone=None,
        position_code=position,
    )
    # Allow binding the same app_key (reuse path).
    if dup.get("duplicate") and str(dup.get("app_key") or "") != app:
        return dup

    binding_id = str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:job-binding:{company}:{app}"))
    cur.execute(
        """
        INSERT INTO application_job_bindings
          (binding_id, company_code, app_key, position_code, apply_code, job_id,
           verified, verification_mode, consent_id, person_id, membership_id,
           subject_id, provenance)
        VALUES (%s,%s,%s,%s,%s,%s,true,'exact_confirm',%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, app_key)
        DO UPDATE SET
          position_code=EXCLUDED.position_code,
          apply_code=COALESCE(EXCLUDED.apply_code, application_job_bindings.apply_code),
          job_id=COALESCE(EXCLUDED.job_id, application_job_bindings.job_id),
          verified=true,
          consent_id=COALESCE(EXCLUDED.consent_id, application_job_bindings.consent_id),
          person_id=COALESCE(EXCLUDED.person_id, application_job_bindings.person_id),
          membership_id=COALESCE(EXCLUDED.membership_id, application_job_bindings.membership_id),
          subject_id=COALESCE(EXCLUDED.subject_id, application_job_bindings.subject_id),
          provenance=EXCLUDED.provenance,
          updated_at=now()
        RETURNING binding_id::text AS binding_id, verified
        """,
        (
            binding_id,
            company,
            app,
            position,
            apply_code,
            job_id,
            consent_id,
            person_id,
            membership_id,
            subject_id,
            _json(
                {
                    **(provenance or {}),
                    "authority_version": AUTHORITY_VERSION,
                    "bound_at": datetime.now(UTC).isoformat(),
                }
            ),
        ),
    )
    job_row = cur.fetchone() or {"binding_id": binding_id, "verified": True}

    cv_binding = None
    if cv_version_id:
        cv_binding_id = str(
            uuid.uuid5(_ID_NAMESPACE, f"wathefni:cv-binding:{company}:{app}:{cv_version_id}")
        )
        cur.execute(
            """
            UPDATE application_cv_bindings
            SET pinned=false
            WHERE company_code=%s AND app_key=%s AND pinned=true
            """,
            (company, app),
        )
        cur.execute(
            """
            INSERT INTO application_cv_bindings
              (binding_id, company_code, app_key, cv_version_id, pinned, provenance)
            VALUES (%s,%s,%s,%s,true,%s)
            ON CONFLICT (company_code, app_key, cv_version_id)
            DO UPDATE SET pinned=true, provenance=EXCLUDED.provenance
            RETURNING binding_id::text AS binding_id, cv_version_id::text AS cv_version_id
            """,
            (
                cv_binding_id,
                company,
                app,
                cv_version_id,
                _json({"authority_version": AUTHORITY_VERSION}),
            ),
        )
        cv_binding = cur.fetchone()

    return {
        "ok": True,
        "skipped": False,
        "job_binding": dict(job_row),
        "cv_binding": dict(cv_binding) if cv_binding else None,
        "verified": True,
        "authority_version": AUTHORITY_VERSION,
    }


def get_verified_job_binding(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
) -> dict[str, Any] | None:
    company = _safe_company(company_code)
    cur.execute(
        """
        SELECT binding_id::text, app_key, position_code, apply_code, verified,
               person_id::text, membership_id::text, subject_id::text
        FROM application_job_bindings
        WHERE company_code=%s AND app_key=%s AND verified=true
        LIMIT 1
        """,
        (company, app_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


__all__ = [
    "FEATURE",
    "AUTHORITY_VERSION",
    "enabled",
    "ensure_schema",
    "record_consent",
    "preflight_duplicate_application",
    "bind_application_to_job",
    "get_verified_job_binding",
]
