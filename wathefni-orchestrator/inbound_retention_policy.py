"""Versioned, tenant-scoped retention authority for inbound CV source objects.

Policy values are operational defaults supplied through configuration and
materialized as immutable, versioned tenant policy rows.  Cleanup is never
scheduled by this module: callers must explicitly request a dry-run or execute
an owner-authorized pass.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover - local source-contract tests
    def Json(value: Any) -> Any:
        return value

from intake_quarantine_storage import QuarantineStorage


UTC = timezone.utc
POLICY_ENV = {
    "policy_version": "WATHEFNI_INTAKE_RETENTION_POLICY_VERSION",
    "clean_quarantine_days": "WATHEFNI_INTAKE_RETENTION_CLEAN_DAYS",
    "nonclean_quarantine_days": "WATHEFNI_INTAKE_RETENTION_NONCLEAN_DAYS",
    "resolved_review_days": "WATHEFNI_INTAKE_RETENTION_RESOLVED_REVIEW_DAYS",
    "withdrawn_held_days": "WATHEFNI_INTAKE_RETENTION_WITHDRAWN_HELD_DAYS",
    "audit_years": "WATHEFNI_INTAKE_RETENTION_AUDIT_YEARS",
    "correction_audit_years": "WATHEFNI_INTAKE_RETENTION_CORRECTION_AUDIT_YEARS",
}
TERMINAL_NONCLEAN_STATES = frozenset(
    {"infected", "scan_failed", "quarantined", "malware"}
)
HELD_APPLICATION_STATUSES = frozenset(
    {"needs_role", "import_review", "import_archived", "review_pending"}
)


class RetentionPolicyError(RuntimeError):
    """Fail-closed retention configuration or execution error."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


@dataclass(frozen=True)
class RetentionPolicy:
    company_code: str
    policy_version: str
    clean_quarantine_days: int
    nonclean_quarantine_days: int
    resolved_review_days: int
    withdrawn_held_days: int
    audit_years: int
    correction_audit_years: int
    clean_scan_reuse_hours: int
    orphan_grace_seconds: int

    def public_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "open_identity_review": "retain_while_open",
            "legal_hold": "retention_suspended",
            "audit_ledgers_survive_source_deletion": True,
        }


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS inbound_retention_policies (
  company_code text NOT NULL,
  policy_version text NOT NULL,
  clean_quarantine_days integer NOT NULL CHECK (clean_quarantine_days > 0),
  nonclean_quarantine_days integer NOT NULL CHECK (nonclean_quarantine_days > 0),
  resolved_review_days integer NOT NULL CHECK (resolved_review_days > 0),
  withdrawn_held_days integer NOT NULL CHECK (withdrawn_held_days > 0),
  audit_years integer NOT NULL CHECK (audit_years > 0),
  correction_audit_years integer NOT NULL CHECK (correction_audit_years > 0),
  clean_scan_reuse_hours integer NOT NULL CHECK (clean_scan_reuse_hours > 0),
  orphan_grace_seconds integer NOT NULL CHECK (orphan_grace_seconds > 0),
  definition jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, policy_version)
);

CREATE TABLE IF NOT EXISTS inbound_retention_policy_assignments (
  company_code text PRIMARY KEY,
  policy_version text NOT NULL,
  assigned_by text NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (company_code, policy_version)
    REFERENCES inbound_retention_policies(company_code, policy_version)
);

CREATE TABLE IF NOT EXISTS inbound_retention_legal_holds (
  hold_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  intake_document_id uuid,
  content_sha256 text,
  reason text NOT NULL,
  placed_by text NOT NULL,
  placed_at timestamptz NOT NULL DEFAULT now(),
  released_by text,
  released_at timestamptz,
  release_reason text,
  CHECK (intake_document_id IS NOT NULL OR content_sha256 IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_inbound_retention_hold_document
  ON inbound_retention_legal_holds(company_code, intake_document_id)
  WHERE released_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_inbound_retention_hold_hash
  ON inbound_retention_legal_holds(company_code, content_sha256)
  WHERE released_at IS NULL;

CREATE TABLE IF NOT EXISTS inbound_retention_deletions (
  deletion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  intake_document_id uuid NOT NULL,
  content_sha256 text NOT NULL,
  quarantine_object_ref text NOT NULL,
  deletion_reason text NOT NULL,
  actor_service_identity text NOT NULL,
  policy_version text NOT NULL,
  object_deleted boolean NOT NULL,
  deleted_at timestamptz NOT NULL DEFAULT now(),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (company_code, intake_document_id, policy_version)
);

CREATE OR REPLACE FUNCTION prevent_retention_audit_rewrite()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF current_setting('wathefni.authority_cleanup', true) = 'synthetic' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'retention audit records are append-only';
END;
$$;
DROP TRIGGER IF EXISTS trg_retention_deletion_append_only
  ON inbound_retention_deletions;
CREATE TRIGGER trg_retention_deletion_append_only
BEFORE UPDATE OR DELETE ON inbound_retention_deletions
FOR EACH ROW EXECUTE FUNCTION prevent_retention_audit_rewrite();
"""


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _company(value: Any) -> str:
    company = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())
    if not company:
        raise RetentionPolicyError("retention_company_scope_required")
    return company


def _required_int(environ: dict[str, str], name: str) -> int:
    raw = str(environ.get(name) or "").strip()
    if not raw:
        raise RetentionPolicyError("retention_policy_config_unset", name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RetentionPolicyError("retention_policy_config_invalid", name) from exc
    if value <= 0:
        raise RetentionPolicyError("retention_policy_config_invalid", name)
    return value


def policy_from_env(
    company_code: str, environ: dict[str, str] | None = None
) -> RetentionPolicy:
    """Parse all required values; missing/invalid values never fall back."""
    env = environ if environ is not None else os.environ
    version = str(env.get(POLICY_ENV["policy_version"]) or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", version):
        raise RetentionPolicyError(
            "retention_policy_version_invalid", POLICY_ENV["policy_version"]
        )
    return RetentionPolicy(
        company_code=_company(company_code),
        policy_version=version,
        clean_quarantine_days=_required_int(
            env, POLICY_ENV["clean_quarantine_days"]
        ),
        nonclean_quarantine_days=_required_int(
            env, POLICY_ENV["nonclean_quarantine_days"]
        ),
        resolved_review_days=_required_int(env, POLICY_ENV["resolved_review_days"]),
        withdrawn_held_days=_required_int(env, POLICY_ENV["withdrawn_held_days"]),
        audit_years=_required_int(env, POLICY_ENV["audit_years"]),
        correction_audit_years=_required_int(
            env, POLICY_ENV["correction_audit_years"]
        ),
        clean_scan_reuse_hours=_required_int(
            env, "WATHEFNI_INTAKE_SCAN_REUSE_HOURS"
        ),
        orphan_grace_seconds=_required_int(
            env, "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS"
        ),
    )


def activate_policy(cur: Any, policy: RetentionPolicy, *, actor: str) -> None:
    """Materialize an immutable definition and point the tenant assignment to it."""
    ensure_schema(cur)
    actor_name = str(actor or "").strip()
    if not actor_name:
        raise RetentionPolicyError("retention_policy_actor_required")
    values = asdict(policy)
    cur.execute(
        """
        INSERT INTO inbound_retention_policies(
          company_code, policy_version, clean_quarantine_days,
          nonclean_quarantine_days, resolved_review_days, withdrawn_held_days,
          audit_years, correction_audit_years, clean_scan_reuse_hours,
          orphan_grace_seconds, definition, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, policy_version) DO NOTHING
        """,
        (
            policy.company_code,
            policy.policy_version,
            policy.clean_quarantine_days,
            policy.nonclean_quarantine_days,
            policy.resolved_review_days,
            policy.withdrawn_held_days,
            policy.audit_years,
            policy.correction_audit_years,
            policy.clean_scan_reuse_hours,
            policy.orphan_grace_seconds,
            Json(policy.public_dict()),
            actor_name,
        ),
    )
    cur.execute(
        """
        SELECT clean_quarantine_days, nonclean_quarantine_days,
               resolved_review_days, withdrawn_held_days, audit_years,
               correction_audit_years, clean_scan_reuse_hours,
               orphan_grace_seconds
        FROM inbound_retention_policies
        WHERE company_code=%s AND policy_version=%s
        """,
        (policy.company_code, policy.policy_version),
    )
    existing = dict(cur.fetchone() or {})
    expected = {
        key: values[key]
        for key in (
            "clean_quarantine_days",
            "nonclean_quarantine_days",
            "resolved_review_days",
            "withdrawn_held_days",
            "audit_years",
            "correction_audit_years",
            "clean_scan_reuse_hours",
            "orphan_grace_seconds",
        )
    }
    if existing != expected:
        raise RetentionPolicyError("retention_policy_version_definition_conflict")
    cur.execute(
        """
        INSERT INTO inbound_retention_policy_assignments(
          company_code, policy_version, assigned_by)
        VALUES (%s,%s,%s)
        ON CONFLICT (company_code) DO UPDATE
          SET policy_version=EXCLUDED.policy_version,
              assigned_by=EXCLUDED.assigned_by,
              assigned_at=now()
        """,
        (policy.company_code, policy.policy_version, actor_name),
    )


def active_policy(cur: Any, company_code: str) -> RetentionPolicy:
    """Return the exact active tenant policy or fail closed."""
    ensure_schema(cur)
    company = _company(company_code)
    cur.execute(
        """
        SELECT p.*
        FROM inbound_retention_policy_assignments a
        JOIN inbound_retention_policies p
          ON p.company_code=a.company_code
         AND p.policy_version=a.policy_version
        WHERE a.company_code=%s
        """,
        (company,),
    )
    row = cur.fetchone()
    if not row:
        raise RetentionPolicyError("retention_policy_not_configured", company)
    data = dict(row)
    return RetentionPolicy(
        company_code=company,
        policy_version=str(data["policy_version"]),
        clean_quarantine_days=int(data["clean_quarantine_days"]),
        nonclean_quarantine_days=int(data["nonclean_quarantine_days"]),
        resolved_review_days=int(data["resolved_review_days"]),
        withdrawn_held_days=int(data["withdrawn_held_days"]),
        audit_years=int(data["audit_years"]),
        correction_audit_years=int(data["correction_audit_years"]),
        clean_scan_reuse_hours=int(data["clean_scan_reuse_hours"]),
        orphan_grace_seconds=int(data["orphan_grace_seconds"]),
    )


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _eligibility(
    row: dict[str, Any], policy: RetentionPolicy, now: datetime
) -> tuple[bool, str, datetime | None]:
    if row.get("legal_hold"):
        return False, "legal_hold", None
    if str(row.get("review_status") or "").lower() == "open":
        return False, "identity_review_open", None

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    withdrawn_at = _as_datetime(metadata.get("withdrawn_at") or metadata.get("deleted_at"))
    if withdrawn_at:
        if (
            str(row.get("app_status") or "").lower()
            not in HELD_APPLICATION_STATUSES
            or str(row.get("position_code") or "").strip()
        ):
            return False, "withdrawn_source_not_held", None
        eligible_at = withdrawn_at + timedelta(days=policy.withdrawn_held_days)
        return now >= eligible_at, "withdrawn_or_deleted_held_source", eligible_at

    resolved_at = _as_datetime(row.get("review_resolved_at"))
    if resolved_at:
        eligible_at = resolved_at + timedelta(days=policy.resolved_review_days)
        return now >= eligible_at, "resolved_identity_review", eligible_at

    scan_state = str(row.get("scan_state") or "").lower()
    scanned_at = _as_datetime(row.get("scan_completed_at"))
    if not scanned_at:
        return False, "durable_terminal_scan_timestamp_missing", None
    if scan_state == "clean":
        eligible_at = scanned_at + timedelta(days=policy.clean_quarantine_days)
        return now >= eligible_at, "clean_quarantine_expired", eligible_at
    if scan_state in TERMINAL_NONCLEAN_STATES:
        eligible_at = scanned_at + timedelta(days=policy.nonclean_quarantine_days)
        return now >= eligible_at, "nonclean_quarantine_expired", eligible_at
    return False, "durable_terminal_scan_missing", None


def plan_cleanup(
    cur: Any,
    *,
    company_code: str,
    now: datetime | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Return eligible source objects only; never deletes."""
    policy = active_policy(cur, company_code)
    checked_at = now or datetime.now(UTC)
    cur.execute(
        """
        SELECT d.document_id::text, d.company_code, d.content_sha256,
               d.quarantine_key, d.storage_status, d.metadata, d.size_bytes,
               app.status AS app_status, app.position_code,
               scan.state AS scan_state,
               scan.scan_completed_at,
               review.status AS review_status,
               review.resolved_at AS review_resolved_at,
               EXISTS (
                 SELECT 1 FROM inbound_retention_legal_holds h
                 WHERE h.company_code=d.company_code
                   AND h.released_at IS NULL
                   AND (
                     h.intake_document_id=d.document_id
                     OR (
                       h.intake_document_id IS NULL
                       AND h.content_sha256=d.content_sha256
                     )
                   )
               ) AS legal_hold
        FROM intake_documents d
        LEFT JOIN applications app
          ON app.company_code=d.company_code AND app.app_key=d.app_key
        LEFT JOIN LATERAL (
          SELECT s.state, s.scan_completed_at
          FROM inbound_attachment_scan_decisions s
          WHERE s.company_code=d.company_code
            AND s.intake_document_id=d.document_id
          ORDER BY s.attempt_no DESC, s.created_at DESC
          LIMIT 1
        ) scan ON true
        LEFT JOIN LATERAL (
          SELECT r.status, r.resolved_at
          FROM inbound_cv_identity_reviews r
          WHERE r.company_code=d.company_code
            AND r.intake_document_id=d.document_id
          ORDER BY r.created_at DESC
          LIMIT 1
        ) review ON true
        WHERE d.company_code=%s
          AND d.storage_status='stored'
          AND d.quarantine_key IS NOT NULL
          AND d.content_sha256 IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM inbound_retention_deletions x
            WHERE x.company_code=d.company_code
              AND x.intake_document_id=d.document_id
          )
        ORDER BY d.created_at, d.document_id
        LIMIT %s
        """,
        (policy.company_code, max(1, min(int(limit), 5000))),
    )
    eligible: list[dict[str, Any]] = []
    blocked: dict[str, int] = {}
    considered = 0
    for value in cur.fetchall():
        considered += 1
        row = dict(value)
        allowed, reason, eligible_at = _eligibility(row, policy, checked_at)
        if not allowed:
            blocked[reason] = blocked.get(reason, 0) + 1
            continue
        eligible.append(
            {
                "company_code": policy.company_code,
                "intake_document_id": row["document_id"],
                "content_sha256": row["content_sha256"],
                "quarantine_object_ref": row["quarantine_key"],
                "size_bytes": row.get("size_bytes"),
                "reason": reason,
                "eligible_at": eligible_at.isoformat() if eligible_at else None,
                "policy_version": policy.policy_version,
            }
        )
    return {
        "dry_run": True,
        "company_code": policy.company_code,
        "policy": policy.public_dict(),
        "checked_at": checked_at.isoformat(),
        "considered": considered,
        "eligible_count": len(eligible),
        "eligible": eligible,
        "blocked_counts": blocked,
    }


def execute_cleanup(
    cur: Any,
    *,
    company_code: str,
    storage: QuarantineStorage,
    actor: str,
    dry_run: bool = True,
    now: datetime | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Explicit cleanup entry point.  The default is non-destructive dry-run."""
    plan = plan_cleanup(
        cur, company_code=company_code, now=now, limit=limit
    )
    if dry_run:
        return plan
    actor_name = str(actor or "").strip()
    if not actor_name:
        raise RetentionPolicyError("retention_cleanup_actor_required")
    deleted: list[dict[str, Any]] = []
    for item in plan["eligible"]:
        cur.execute(
            """
            SELECT 1 FROM inbound_retention_deletions
            WHERE company_code=%s AND intake_document_id=%s
            """,
            (item["company_code"], item["intake_document_id"]),
        )
        if cur.fetchone():
            continue
        object_deleted = storage.delete(item["quarantine_object_ref"])
        cur.execute(
            """
            INSERT INTO inbound_retention_deletions(
              company_code, intake_document_id, content_sha256,
              quarantine_object_ref, deletion_reason, actor_service_identity,
              policy_version, object_deleted, evidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_code, intake_document_id, policy_version)
              DO NOTHING
            """,
            (
                item["company_code"],
                item["intake_document_id"],
                item["content_sha256"],
                item["quarantine_object_ref"],
                item["reason"],
                actor_name,
                item["policy_version"],
                object_deleted,
                Json(
                    {
                        "eligible_at": item["eligible_at"],
                        "size_bytes": item.get("size_bytes"),
                    }
                ),
            ),
        )
        cur.execute(
            """
            UPDATE intake_documents
            SET storage_status='retention_deleted',
                metadata=COALESCE(metadata,'{}'::jsonb) || %s,
                updated_at=now()
            WHERE company_code=%s AND document_id=%s
            """,
            (
                Json(
                    {
                        "retention_deleted_at": datetime.now(UTC).isoformat(),
                        "retention_deletion_reason": item["reason"],
                        "retention_policy_version": item["policy_version"],
                        "retention_deletion_actor": actor_name,
                    }
                ),
                item["company_code"],
                item["intake_document_id"],
            ),
        )
        deleted.append({**item, "object_deleted": object_deleted})
    return {
        **plan,
        "dry_run": False,
        "deleted_count": len(deleted),
        "deleted": deleted,
    }
