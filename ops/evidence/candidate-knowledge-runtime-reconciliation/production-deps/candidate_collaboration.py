"""Candidate collaboration authority (C2).

This module is deliberately independent of FastAPI and the canonical recruiting
lifecycle.  Callers pass the legacy app module (for ``db_connect`` and ``Json``)
so the service uses the application's validated pooled Postgres connections and
dict-row cursors.

Collaboration state is tenant/application scoped.  Nothing here changes
``applications.status``, ``applications.current_step`` or lifecycle versions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CANDIDATES_READ = "candidates.read"
CANDIDATES_ASSIGN = "candidates.assign"
CANDIDATES_NOTES_MANAGE = "candidates.notes.manage"
CANDIDATES_TASKS_MANAGE = "candidates.tasks.manage"
CANDIDATES_TAGS_MANAGE = "candidates.tags.manage"
CANDIDATE_COLLABORATION_PERMISSIONS = frozenset(
    {
        CANDIDATES_READ,
        CANDIDATES_ASSIGN,
        CANDIDATES_NOTES_MANAGE,
        CANDIDATES_TASKS_MANAGE,
        CANDIDATES_TAGS_MANAGE,
    }
)

RECRUITING_ROLES = frozenset({"owner", "hr_manager", "recruiter", "hiring_manager"})
TERMINAL_APPLICATION_STAGES = frozenset({"hired", "rejected", "withdrawn"})
TASK_STATUSES = frozenset({"open", "completed", "cancelled"})
TASK_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
CONFIRMATION_TTL_SECONDS = 600
MAX_BULK_ITEMS = 500
INTERNAL_APPLICATION_FIELDS = frozenset(
    {
        "owner_user_id",
        "ownership_version",
        "owner_assigned_at",
        "owner_assigned_by_user_id",
        "owner",
        "ownership",
        "notes",
        "tasks",
        "tags",
        "available_tags",
        "open_task_count",
        "overdue_task_count",
    }
)


class CollaborationError(Exception):
    """Stable service error suitable for an API error envelope."""

    def __init__(self, code: str, *, message: str | None = None, details: Mapping[str, Any] | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.details = dict(details or {})

    def envelope(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": False, "error": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


def ensure_schema(cur: Any) -> None:
    """Install additive C2 schema and rollback-safe ownership guards."""

    cur.execute(
        """
        ALTER TABLE IF EXISTS applications
          ADD COLUMN IF NOT EXISTS owner_user_id uuid,
          ADD COLUMN IF NOT EXISTS ownership_version bigint NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS owner_assigned_at timestamptz,
          ADD COLUMN IF NOT EXISTS owner_assigned_by_user_id uuid;

        DO $c2$
        BEGIN
          IF to_regclass('public.applications') IS NOT NULL
             AND to_regclass('public.dashboard_users') IS NOT NULL
             AND NOT EXISTS (
               SELECT 1 FROM pg_constraint
               WHERE conname='applications_owner_user_fk'
                 AND conrelid='applications'::regclass
             )
          THEN
            ALTER TABLE applications
              ADD CONSTRAINT applications_owner_user_fk
              FOREIGN KEY (owner_user_id) REFERENCES dashboard_users(user_id)
              ON DELETE RESTRICT NOT VALID;
          END IF;
          IF to_regclass('public.applications') IS NOT NULL
             AND to_regclass('public.dashboard_users') IS NOT NULL
             AND NOT EXISTS (
               SELECT 1 FROM pg_constraint
               WHERE conname='applications_owner_assigner_fk'
                 AND conrelid='applications'::regclass
             )
          THEN
            ALTER TABLE applications
              ADD CONSTRAINT applications_owner_assigner_fk
              FOREIGN KEY (owner_assigned_by_user_id) REFERENCES dashboard_users(user_id)
              ON DELETE SET NULL NOT VALID;
          END IF;
        END
        $c2$;

        CREATE TABLE IF NOT EXISTS application_ownership_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          event_type text NOT NULL,
          from_owner_user_id uuid,
          to_owner_user_id uuid,
          ownership_version bigint NOT NULL,
          actor_user_id uuid NOT NULL,
          reason text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (event_type IN ('assigned','claimed','reassigned','unassigned'))
        );

        CREATE TABLE IF NOT EXISTS application_notes (
          note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          body text NOT NULL,
          version bigint NOT NULL DEFAULT 1,
          created_by_user_id uuid NOT NULL,
          updated_by_user_id uuid NOT NULL,
          deleted_at timestamptz,
          deleted_by_user_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (version > 0),
          CHECK (deleted_at IS NULL OR deleted_by_user_id IS NOT NULL)
        );

        CREATE TABLE IF NOT EXISTS application_note_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          note_id uuid NOT NULL REFERENCES application_notes(note_id) ON DELETE RESTRICT,
          company_code text NOT NULL,
          app_key text NOT NULL,
          event_type text NOT NULL,
          note_version bigint NOT NULL,
          actor_user_id uuid NOT NULL,
          body_snapshot text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (event_type IN ('created','edited','deleted'))
        );

        CREATE TABLE IF NOT EXISTS application_recruiter_tasks (
          task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          title text NOT NULL,
          description text,
          status text NOT NULL DEFAULT 'open',
          priority text NOT NULL DEFAULT 'normal',
          assigned_to_user_id uuid NOT NULL,
          due_at timestamptz,
          version bigint NOT NULL DEFAULT 1,
          idempotency_key text,
          created_by_user_id uuid NOT NULL,
          updated_by_user_id uuid NOT NULL,
          completed_at timestamptz,
          cancelled_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('open','completed','cancelled')),
          CHECK (priority IN ('low','normal','high','urgent')),
          CHECK (version > 0)
        );

        CREATE TABLE IF NOT EXISTS application_recruiter_task_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          task_id uuid NOT NULL REFERENCES application_recruiter_tasks(task_id) ON DELETE RESTRICT,
          company_code text NOT NULL,
          app_key text NOT NULL,
          event_type text NOT NULL,
          task_version bigint NOT NULL,
          actor_user_id uuid NOT NULL,
          idempotency_key text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (event_type IN ('created','edited','reassigned','completed','cancelled'))
        );

        CREATE TABLE IF NOT EXISTS candidate_tag_dictionary (
          tag_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name text NOT NULL,
          label_ar text,
          canonical_name text NOT NULL,
          color text,
          is_active boolean NOT NULL DEFAULT true,
          created_by_user_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (canonical_name = lower(btrim(canonical_name))),
          UNIQUE (company_code, canonical_name)
        );
        ALTER TABLE IF EXISTS candidate_tag_dictionary
          ADD COLUMN IF NOT EXISTS label_ar text;

        CREATE TABLE IF NOT EXISTS application_tags (
          company_code text NOT NULL,
          app_key text NOT NULL,
          tag_id uuid NOT NULL REFERENCES candidate_tag_dictionary(tag_id) ON DELETE RESTRICT,
          added_by_user_id uuid NOT NULL,
          added_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (company_code, app_key, tag_id)
        );

        CREATE TABLE IF NOT EXISTS application_tag_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          tag_id uuid NOT NULL REFERENCES candidate_tag_dictionary(tag_id) ON DELETE RESTRICT,
          event_type text NOT NULL,
          actor_user_id uuid NOT NULL,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (event_type IN ('added','removed'))
        );

        CREATE TABLE IF NOT EXISTS candidate_c2_confirmations (
          confirmation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          actor_user_id uuid NOT NULL,
          action text NOT NULL,
          payload_hash text NOT NULL,
          token_hash text NOT NULL,
          payload jsonb NOT NULL,
          status text NOT NULL DEFAULT 'pending',
          expires_at timestamptz NOT NULL,
          consumed_at timestamptz,
          result jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('pending','consumed','expired','cancelled'))
        );

        CREATE TABLE IF NOT EXISTS candidate_bulk_operations (
          operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          actor_user_id uuid NOT NULL,
          operation_type text NOT NULL,
          request_hash text NOT NULL,
          request_payload jsonb NOT NULL,
          status text NOT NULL DEFAULT 'previewed',
          confirmation_id uuid REFERENCES candidate_c2_confirmations(confirmation_id) ON DELETE RESTRICT,
          result jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          executed_at timestamptz,
          CHECK (operation_type IN ('assign','tag_add','tag_remove')),
          CHECK (status IN ('previewed','processing','completed','cancelled'))
        );

        CREATE TABLE IF NOT EXISTS candidate_bulk_operation_items (
          item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          operation_id uuid NOT NULL REFERENCES candidate_bulk_operations(operation_id) ON DELETE RESTRICT,
          company_code text NOT NULL,
          app_key text NOT NULL,
          observed_ownership_version bigint NOT NULL,
          observed_lifecycle_version bigint NOT NULL,
          result_status text,
          error_code text,
          result jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          processed_at timestamptz,
          UNIQUE (operation_id, app_key),
          CHECK (result_status IS NULL OR result_status IN ('success','skipped','stale','denied'))
        );

        CREATE INDEX IF NOT EXISTS applications_owner_idx
          ON applications(company_code, owner_user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS application_ownership_events_app_idx
          ON application_ownership_events(company_code, app_key, created_at DESC);
        CREATE INDEX IF NOT EXISTS application_notes_app_idx
          ON application_notes(company_code, app_key, created_at DESC);
        CREATE INDEX IF NOT EXISTS application_note_events_app_idx
          ON application_note_events(company_code, app_key, created_at DESC);
        CREATE INDEX IF NOT EXISTS application_recruiter_tasks_app_idx
          ON application_recruiter_tasks(company_code, app_key, status, due_at);
        CREATE INDEX IF NOT EXISTS application_recruiter_tasks_assignee_idx
          ON application_recruiter_tasks(company_code, assigned_to_user_id, status, due_at);
        CREATE UNIQUE INDEX IF NOT EXISTS application_recruiter_tasks_idem_uq
          ON application_recruiter_tasks(company_code, app_key, idempotency_key)
          WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';
        CREATE UNIQUE INDEX IF NOT EXISTS application_recruiter_task_events_idem_uq
          ON application_recruiter_task_events(company_code, app_key, idempotency_key)
          WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';
        CREATE INDEX IF NOT EXISTS application_tags_app_idx
          ON application_tags(company_code, app_key, added_at DESC);
        CREATE INDEX IF NOT EXISTS candidate_c2_confirmations_lookup_idx
          ON candidate_c2_confirmations(company_code, actor_user_id, action, status, expires_at);
        CREATE UNIQUE INDEX IF NOT EXISTS candidate_bulk_operations_hash_uq
          ON candidate_bulk_operations(company_code, actor_user_id, request_hash);
        CREATE INDEX IF NOT EXISTS candidate_bulk_items_operation_idx
          ON candidate_bulk_operation_items(operation_id, app_key);

        CREATE OR REPLACE FUNCTION prevent_active_candidate_owner_orphan()
        RETURNS trigger AS $guard$
        BEGIN
          IF TG_OP='DELETE' AND EXISTS (
            SELECT 1 FROM applications a
            WHERE a.owner_user_id=OLD.user_id
              AND a.company_code=OLD.company_code
              AND lower(COALESCE(a.status,'')) NOT IN ('hired','rejected','withdrawn')
          )
          THEN
            RAISE EXCEPTION 'active_candidate_ownership_requires_reassignment'
              USING ERRCODE='23503';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          IF (
            COALESCE(NEW.status,'disabled') <> 'active'
            OR COALESCE(NEW.role,'viewer') NOT IN ('owner','hr_manager','recruiter','hiring_manager')
          ) AND EXISTS (
            SELECT 1 FROM applications a
            WHERE a.owner_user_id=OLD.user_id
              AND a.company_code=OLD.company_code
              AND lower(COALESCE(a.status,'')) NOT IN ('hired','rejected','withdrawn')
          )
          THEN
            RAISE EXCEPTION 'active_candidate_ownership_requires_reassignment'
              USING ERRCODE='23503';
          END IF;
          RETURN NEW;
        END
        $guard$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS dashboard_users_candidate_owner_guard ON dashboard_users;
        CREATE TRIGGER dashboard_users_candidate_owner_guard
          BEFORE UPDATE OF status, role OR DELETE ON dashboard_users
          FOR EACH ROW EXECUTE FUNCTION prevent_active_candidate_owner_orphan();
        """
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_company_code(value: Any) -> str:
    company = _text(value).upper()
    if not company:
        raise CollaborationError("tenant_scope_required")
    if len(company) > 128:
        raise CollaborationError("tenant_scope_invalid")
    return company


def validate_app_key(value: Any) -> str:
    app_key = _text(value)
    if not app_key:
        raise CollaborationError("app_key_required")
    if len(app_key) > 512 or any(ord(char) < 32 for char in app_key):
        raise CollaborationError("app_key_invalid")
    return app_key


def validate_user_id(value: Any, *, field: str = "actor_user_id") -> str:
    raw = _text(value)
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError, AttributeError):
        raise CollaborationError(f"{field}_invalid") from None


def normalize_permissions(values: Iterable[Any] | None) -> frozenset[str]:
    return frozenset(_text(value) for value in (values or ()) if _text(value))


def require_permission(permissions: Iterable[Any] | None, permission: str) -> None:
    if permission not in normalize_permissions(permissions):
        raise CollaborationError("permission_denied", details={"permission": permission})


def resolve_user_permissions(
    user: Mapping[str, Any],
    *,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
    cur: Any | None = None,
) -> frozenset[str]:
    if permission_resolver is None:
        return normalize_permissions(user.get("permissions") or ())
    try:
        resolved = permission_resolver(dict(user), cur=cur)
    except TypeError:
        resolved = permission_resolver(dict(user))
    return normalize_permissions(resolved)


def validate_actor(
    cur: Any,
    *,
    company_code: Any,
    actor_user_id: Any,
    permissions: Iterable[Any] | None = None,
    required_permission: str | None = None,
) -> dict[str, Any]:
    company = validate_company_code(company_code)
    actor_id = validate_user_id(actor_user_id)
    cur.execute(
        """
        SELECT user_id, company_code, role, status, name, email
        FROM dashboard_users
        WHERE company_code=%s AND user_id=%s
        """,
        (company, actor_id),
    )
    actor = cur.fetchone()
    if not actor or _text(actor.get("status")).lower() != "active":
        raise CollaborationError("actor_not_active")
    if required_permission:
        require_permission(permissions, required_permission)
    return dict(actor)


def validate_eligible_recruiter(
    cur: Any,
    *,
    company_code: Any,
    user_id: Any,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
) -> dict[str, Any]:
    company = validate_company_code(company_code)
    target_id = validate_user_id(user_id, field="owner_user_id")
    cur.execute(
        """
        SELECT user_id, company_code, role, status, name, email
        FROM dashboard_users
        WHERE company_code=%s AND user_id=%s
        """,
        (company, target_id),
    )
    user = cur.fetchone()
    if not user:
        raise CollaborationError("owner_not_found")
    role = _text(user.get("role")).lower().replace("-", "_").replace(" ", "_")
    if _text(user.get("status")).lower() != "active" or role not in RECRUITING_ROLES:
        raise CollaborationError("owner_not_eligible")
    effective = resolve_user_permissions(user, permission_resolver=permission_resolver, cur=cur)
    if CANDIDATES_READ not in effective:
        raise CollaborationError("owner_not_eligible", details={"permission": CANDIDATES_READ})
    result = dict(user)
    result["permissions"] = sorted(effective)
    return result


def _application_for_update(cur: Any, company: str, app_key: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT app_key, company_code, status, lifecycle_version,
               owner_user_id, ownership_version, owner_assigned_at,
               owner_assigned_by_user_id
        FROM applications
        WHERE company_code=%s AND app_key=%s
        FOR UPDATE
        """,
        (company, app_key),
    )
    row = cur.fetchone()
    if not row:
        raise CollaborationError("application_not_found")
    return dict(row)


def _json_value(legacy: Any, value: Any) -> Any:
    factory = getattr(legacy, "Json", None)
    return factory(value) if callable(factory) else value


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(item) for item in value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def stable_payload_hash(value: Any) -> str:
    encoded = json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utcnow(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_c2_confirmation(
    legacy: Any,
    *,
    company_code: Any,
    actor_user_id: Any,
    action: Any,
    payload: Mapping[str, Any],
    permissions: Iterable[Any] | None,
    required_permission: str,
    ttl_seconds: int = CONFIRMATION_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    company = validate_company_code(company_code)
    actor_id = validate_user_id(actor_user_id)
    action_name = _text(action).lower()
    if not action_name:
        raise CollaborationError("confirmation_action_required")
    require_permission(permissions, required_permission)
    if ttl_seconds < 1 or ttl_seconds > 3600:
        raise CollaborationError("confirmation_ttl_invalid")
    bound_payload = _canonical(dict(payload))
    payload_hash = stable_payload_hash(bound_payload)
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow(now) + timedelta(seconds=ttl_seconds)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(
                cur,
                company_code=company,
                actor_user_id=actor_id,
                permissions=permissions,
                required_permission=required_permission,
            )
            cur.execute(
                """
                INSERT INTO candidate_c2_confirmations
                  (company_code, actor_user_id, action, payload_hash, token_hash, payload, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING confirmation_id, company_code, actor_user_id, action,
                          payload_hash, status, expires_at, created_at
                """,
                (
                    company,
                    actor_id,
                    action_name,
                    payload_hash,
                    _token_hash(token),
                    _json_value(legacy, bound_payload),
                    expires_at,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    row["confirmation_token"] = token
    return {"ok": True, "confirmation": row}


def consume_c2_confirmation(
    cur: Any,
    legacy: Any,
    *,
    confirmation_id: Any,
    confirmation_token: Any,
    company_code: Any,
    actor_user_id: Any,
    action: Any,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    confirmation_uuid = validate_user_id(confirmation_id, field="confirmation_id")
    company = validate_company_code(company_code)
    actor_id = validate_user_id(actor_user_id)
    token = _text(confirmation_token)
    if not token:
        raise CollaborationError("confirmation_required")
    cur.execute(
        """
        SELECT *
        FROM candidate_c2_confirmations
        WHERE confirmation_id=%s
        FOR UPDATE
        """,
        (confirmation_uuid,),
    )
    row = cur.fetchone()
    if not row:
        raise CollaborationError("confirmation_invalid")
    if row.get("status") != "pending":
        raise CollaborationError("confirmation_already_used")
    current = _utcnow(now)
    expires_at = row.get("expires_at")
    if expires_at and expires_at <= current:
        cur.execute(
            "UPDATE candidate_c2_confirmations SET status='expired' WHERE confirmation_id=%s",
            (confirmation_uuid,),
        )
        raise CollaborationError("confirmation_expired")
    expected_hash = stable_payload_hash(dict(payload))
    state_matches = (
        _text(row.get("company_code")).upper() == company
        and _text(row.get("actor_user_id")) == actor_id
        and _text(row.get("action")).lower() == _text(action).lower()
        and hmac.compare_digest(_text(row.get("payload_hash")), expected_hash)
        and hmac.compare_digest(_text(row.get("token_hash")), _token_hash(token))
    )
    if not state_matches:
        raise CollaborationError("confirmation_state_changed")
    cur.execute(
        """
        UPDATE candidate_c2_confirmations
        SET status='consumed', consumed_at=%s
        WHERE confirmation_id=%s AND status='pending'
        RETURNING *
        """,
        (current, confirmation_uuid),
    )
    consumed = cur.fetchone()
    if not consumed:
        raise CollaborationError("confirmation_already_used")
    return dict(consumed)


def _require_assistant_confirmation(
    cur: Any,
    legacy: Any,
    *,
    actor_type: str,
    confirmation_id: Any,
    confirmation_token: Any,
    company_code: str,
    actor_user_id: str,
    action: str,
    payload: Mapping[str, Any],
) -> None:
    if _text(actor_type).lower() not in {"assistant", "ai"}:
        return
    if not confirmation_id or not confirmation_token:
        raise CollaborationError("confirmation_required")
    consume_c2_confirmation(
        cur,
        legacy,
        confirmation_id=confirmation_id,
        confirmation_token=confirmation_token,
        company_code=company_code,
        actor_user_id=actor_user_id,
        action=action,
        payload=payload,
    )


def _assign_owner(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    actor_user_id: Any,
    owner_user_id: Any | None,
    expected_ownership_version: int,
    expected_lifecycle_version: int | None = None,
    permissions: Iterable[Any] | None,
    event_type: str,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
    reason: str | None = None,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
) -> dict[str, Any]:
    company = validate_company_code(company_code)
    key = validate_app_key(app_key)
    actor_id = validate_user_id(actor_user_id)
    try:
        expected = int(expected_ownership_version)
    except (TypeError, ValueError):
        raise CollaborationError("ownership_version_invalid") from None
    if expected < 0:
        raise CollaborationError("ownership_version_invalid")
    lifecycle_expected = None
    if expected_lifecycle_version is not None:
        try:
            lifecycle_expected = int(expected_lifecycle_version)
        except (TypeError, ValueError):
            raise CollaborationError("lifecycle_version_invalid") from None
        if lifecycle_expected < 0:
            raise CollaborationError("lifecycle_version_invalid")
    target_id = validate_user_id(owner_user_id, field="owner_user_id") if owner_user_id else None
    payload = {
        "app_key": key,
        "owner_user_id": target_id,
        "expected_ownership_version": expected,
        "expected_lifecycle_version": lifecycle_expected,
        "event_type": event_type,
        "reason": _text(reason) or None,
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(
                cur,
                company_code=company,
                actor_user_id=actor_id,
                permissions=permissions,
                required_permission=CANDIDATES_ASSIGN,
            )
            if target_id:
                validate_eligible_recruiter(
                    cur,
                    company_code=company,
                    user_id=target_id,
                    permission_resolver=permission_resolver,
                )
            app = _application_for_update(cur, company, key)
            current_version = int(app.get("ownership_version") or 0)
            if current_version != expected:
                raise CollaborationError(
                    "stale_ownership_version",
                    details={"expected": expected, "actual": current_version},
                )
            if lifecycle_expected is not None and int(app.get("lifecycle_version") or 0) != lifecycle_expected:
                raise CollaborationError(
                    "stale_lifecycle_version",
                    details={"expected": lifecycle_expected, "actual": int(app.get("lifecycle_version") or 0)},
                )
            previous = _text(app.get("owner_user_id")) or None
            if event_type == "claimed" and previous and previous != actor_id:
                raise CollaborationError("application_already_owned")
            if previous == target_id:
                return {"ok": True, "application": app, "skipped": True}
            _require_assistant_confirmation(
                cur,
                legacy,
                actor_type=actor_type,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action=f"ownership.{event_type}",
                payload=payload,
            )
            cur.execute(
                """
                UPDATE applications
                SET owner_user_id=%s,
                    ownership_version=ownership_version+1,
                    owner_assigned_at=CASE WHEN %s IS NULL THEN NULL ELSE now() END,
                    owner_assigned_by_user_id=%s,
                    updated_at=now()
                WHERE company_code=%s AND app_key=%s AND ownership_version=%s
                RETURNING app_key, company_code, status, lifecycle_version,
                          owner_user_id, ownership_version, owner_assigned_at,
                          owner_assigned_by_user_id
                """,
                (target_id, target_id, actor_id, company, key, expected),
            )
            updated = cur.fetchone()
            if not updated:
                raise CollaborationError("stale_ownership_version")
            cur.execute(
                """
                INSERT INTO application_ownership_events
                  (company_code, app_key, event_type, from_owner_user_id,
                   to_owner_user_id, ownership_version, actor_user_id, reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    company,
                    key,
                    event_type,
                    previous,
                    target_id,
                    updated["ownership_version"],
                    actor_id,
                    _text(reason) or None,
                ),
            )
            event = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "application": dict(updated), "event": event}


def assign_application_owner(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return _assign_owner(legacy, event_type="assigned", **kwargs)


def claim_application(
    legacy: Any,
    *,
    actor_user_id: Any,
    owner_user_id: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    actor_id = validate_user_id(actor_user_id)
    if owner_user_id and validate_user_id(owner_user_id, field="owner_user_id") != actor_id:
        raise CollaborationError("claim_must_target_actor")
    return _assign_owner(
        legacy,
        actor_user_id=actor_id,
        owner_user_id=actor_id,
        event_type="claimed",
        **kwargs,
    )


def reassign_application_owner(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return _assign_owner(legacy, event_type="reassigned", **kwargs)


def unassign_application_owner(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    kwargs.pop("owner_user_id", None)
    return _assign_owner(legacy, owner_user_id=None, event_type="unassigned", **kwargs)


def _validated_body(body: Any) -> str:
    text = _text(body)
    if not text:
        raise CollaborationError("note_body_required")
    if len(text) > 20_000:
        raise CollaborationError("note_body_too_long")
    return text


def serialize_note(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if result.get("deleted_at") is not None:
        result["body"] = None
        result["is_deleted"] = True
    else:
        result["is_deleted"] = False
    return result


def create_application_note(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    actor_user_id: Any,
    body: Any,
    permissions: Iterable[Any] | None,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
) -> dict[str, Any]:
    company, key, actor_id = (
        validate_company_code(company_code),
        validate_app_key(app_key),
        validate_user_id(actor_user_id),
    )
    note_body = _validated_body(body)
    payload = {"app_key": key, "body": note_body}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=CANDIDATES_NOTES_MANAGE)
            _application_for_update(cur, company, key)
            _require_assistant_confirmation(cur, legacy, actor_type=actor_type, confirmation_id=confirmation_id, confirmation_token=confirmation_token, company_code=company, actor_user_id=actor_id, action="notes.create", payload=payload)
            cur.execute(
                """
                INSERT INTO application_notes
                  (company_code, app_key, body, created_by_user_id, updated_by_user_id)
                VALUES (%s,%s,%s,%s,%s) RETURNING *
                """,
                (company, key, note_body, actor_id, actor_id),
            )
            note = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO application_note_events
                  (note_id, company_code, app_key, event_type, note_version,
                   actor_user_id, body_snapshot)
                VALUES (%s,%s,%s,'created',%s,%s,%s)
                RETURNING *
                """,
                (note["note_id"], company, key, note["version"], actor_id, note_body),
            )
            event = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "note": serialize_note(note), "event": event}


def list_application_notes(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    permissions: Iterable[Any] | None,
    include_deleted: bool = True,
) -> list[dict[str, Any]]:
    company, key = validate_company_code(company_code), validate_app_key(app_key)
    require_permission(permissions, CANDIDATES_READ)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM application_notes
                WHERE company_code=%s AND app_key=%s
                  AND (%s OR deleted_at IS NULL)
                ORDER BY created_at DESC, note_id DESC
                """,
                (company, key, bool(include_deleted)),
            )
            rows = cur.fetchall()
    return [serialize_note(row) for row in rows]


def _mutate_note(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    note_id: Any,
    actor_user_id: Any,
    expected_version: int,
    permissions: Iterable[Any] | None,
    body: Any = None,
    delete: bool = False,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
) -> dict[str, Any]:
    company, key, actor_id = validate_company_code(company_code), validate_app_key(app_key), validate_user_id(actor_user_id)
    note_uuid = validate_user_id(note_id, field="note_id")
    try:
        version = int(expected_version)
    except (TypeError, ValueError):
        raise CollaborationError("note_version_invalid") from None
    new_body = None if delete else _validated_body(body)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=CANDIDATES_NOTES_MANAGE)
            cur.execute(
                "SELECT * FROM application_notes WHERE company_code=%s AND app_key=%s AND note_id=%s FOR UPDATE",
                (company, key, note_uuid),
            )
            note = cur.fetchone()
            if not note:
                raise CollaborationError("note_not_found")
            if note.get("deleted_at") is not None:
                raise CollaborationError("note_deleted")
            if int(note.get("version") or 0) != version:
                raise CollaborationError("stale_note_version")
            confirmation_payload = {
                "app_key": key,
                "note_id": note_uuid,
                "expected_version": version,
                "body": new_body,
            }
            _require_assistant_confirmation(
                cur,
                legacy,
                actor_type=actor_type,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action="notes.delete" if delete else "notes.edit",
                payload=confirmation_payload,
            )
            if delete:
                cur.execute(
                    """
                    UPDATE application_notes
                    SET body='', version=version+1, deleted_at=now(),
                        deleted_by_user_id=%s, updated_by_user_id=%s, updated_at=now()
                    WHERE company_code=%s AND app_key=%s AND note_id=%s AND version=%s
                    RETURNING *
                    """,
                    (actor_id, actor_id, company, key, note_uuid, version),
                )
                event_type, snapshot = "deleted", None
            else:
                cur.execute(
                    """
                    UPDATE application_notes
                    SET body=%s, version=version+1, updated_by_user_id=%s, updated_at=now()
                    WHERE company_code=%s AND app_key=%s AND note_id=%s AND version=%s
                    RETURNING *
                    """,
                    (new_body, actor_id, company, key, note_uuid, version),
                )
                event_type, snapshot = "edited", new_body
            updated = cur.fetchone()
            if not updated:
                raise CollaborationError("stale_note_version")
            cur.execute(
                """
                INSERT INTO application_note_events
                  (note_id, company_code, app_key, event_type, note_version,
                   actor_user_id, body_snapshot)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (note_uuid, company, key, event_type, updated["version"], actor_id, snapshot),
            )
            event = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "note": serialize_note(updated), "event": event}


def edit_application_note(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return _mutate_note(legacy, delete=False, **kwargs)


def soft_delete_application_note(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    kwargs.pop("body", None)
    return _mutate_note(legacy, delete=True, **kwargs)


def tenant_zone(timezone_name: Any) -> ZoneInfo:
    name = _text(timezone_name) or "Asia/Kuwait"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise CollaborationError("timezone_invalid") from None


def tenant_now(timezone_name: Any, *, now: datetime | None = None) -> datetime:
    return _utcnow(now).astimezone(tenant_zone(timezone_name))


def normalize_due_at(value: Any, *, timezone_name: Any) -> datetime | None:
    if value in (None, ""):
        return None
    due = value
    if isinstance(due, str):
        try:
            due = datetime.fromisoformat(due.replace("Z", "+00:00"))
        except ValueError:
            raise CollaborationError("task_due_at_invalid") from None
    if not isinstance(due, datetime):
        raise CollaborationError("task_due_at_invalid")
    if due.tzinfo is None:
        due = due.replace(tzinfo=tenant_zone(timezone_name))
    return due.astimezone(timezone.utc)


def task_is_overdue(
    task: Mapping[str, Any],
    *,
    timezone_name: Any,
    now: datetime | None = None,
) -> bool:
    if _text(task.get("status")).lower() != "open" or not task.get("due_at"):
        return False
    due = task["due_at"]
    if isinstance(due, str):
        due = datetime.fromisoformat(due.replace("Z", "+00:00"))
    if due.tzinfo is None:
        due = due.replace(tzinfo=tenant_zone(timezone_name))
    return due.astimezone(tenant_zone(timezone_name)) < tenant_now(timezone_name, now=now)


def serialize_task(row: Mapping[str, Any], *, timezone_name: Any = "Asia/Kuwait", now: datetime | None = None) -> dict[str, Any]:
    result = dict(row)
    result["is_overdue"] = task_is_overdue(result, timezone_name=timezone_name, now=now)
    return result


def _validate_task_values(title: Any, priority: Any) -> tuple[str, str]:
    clean_title = _text(title)
    clean_priority = _text(priority).lower() or "normal"
    if not clean_title or len(clean_title) > 500:
        raise CollaborationError("task_title_invalid")
    if clean_priority not in TASK_PRIORITIES:
        raise CollaborationError("task_priority_invalid")
    return clean_title, clean_priority


def create_application_task(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    actor_user_id: Any,
    title: Any,
    permissions: Iterable[Any] | None,
    description: Any = None,
    priority: Any = "normal",
    assigned_to_user_id: Any = None,
    due_at: datetime | None = None,
    idempotency_key: Any = None,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
    timezone_name: Any = "Asia/Kuwait",
) -> dict[str, Any]:
    company, key, actor_id = validate_company_code(company_code), validate_app_key(app_key), validate_user_id(actor_user_id)
    task_title, task_priority = _validate_task_values(title, priority)
    if not assigned_to_user_id:
        raise CollaborationError("task_owner_required")
    assignee = validate_user_id(assigned_to_user_id, field="assigned_to_user_id")
    idem = _text(idempotency_key) or None
    normalized_due_at = normalize_due_at(due_at, timezone_name=timezone_name)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=CANDIDATES_TASKS_MANAGE)
            _application_for_update(cur, company, key)
            if assignee:
                validate_eligible_recruiter(cur, company_code=company, user_id=assignee, permission_resolver=permission_resolver)
            if idem:
                cur.execute(
                    "SELECT * FROM application_recruiter_tasks WHERE company_code=%s AND app_key=%s AND idempotency_key=%s",
                    (company, key, idem),
                )
                existing = cur.fetchone()
                if existing:
                    conn.commit()
                    return {"ok": True, "task": serialize_task(existing, timezone_name=timezone_name), "idempotent": True}
            confirmation_payload = {
                "app_key": key,
                "title": task_title,
                "description": _text(description) or None,
                "priority": task_priority,
                "assigned_to_user_id": assignee,
                "due_at": normalized_due_at,
                "idempotency_key": idem,
            }
            _require_assistant_confirmation(
                cur,
                legacy,
                actor_type=actor_type,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action="tasks.create",
                payload=confirmation_payload,
            )
            cur.execute(
                """
                INSERT INTO application_recruiter_tasks
                  (company_code, app_key, title, description, priority,
                   assigned_to_user_id, due_at, idempotency_key,
                   created_by_user_id, updated_by_user_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, app_key, idempotency_key)
                  WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
                DO NOTHING
                RETURNING *
                """,
                (company, key, task_title, _text(description) or None, task_priority, assignee, normalized_due_at, idem, actor_id, actor_id),
            )
            inserted = cur.fetchone()
            if not inserted and idem:
                cur.execute(
                    "SELECT * FROM application_recruiter_tasks WHERE company_code=%s AND app_key=%s AND idempotency_key=%s",
                    (company, key, idem),
                )
                existing = cur.fetchone()
                if existing:
                    conn.commit()
                    return {"ok": True, "task": serialize_task(existing, timezone_name=timezone_name), "idempotent": True}
            if not inserted:
                raise CollaborationError("task_create_conflict")
            task = dict(inserted)
            cur.execute(
                """
                INSERT INTO application_recruiter_task_events
                  (task_id, company_code, app_key, event_type, task_version,
                   actor_user_id, idempotency_key, payload)
                VALUES (%s,%s,%s,'created',%s,%s,%s,%s) RETURNING *
                """,
                (task["task_id"], company, key, task["version"], actor_id, f"create:{idem}" if idem else None, _json_value(legacy, {"title": task_title, "assigned_to_user_id": assignee})),
            )
            event = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "task": serialize_task(task, timezone_name=timezone_name), "event": event}


def list_application_tasks(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    permissions: Iterable[Any] | None,
    timezone_name: Any = "Asia/Kuwait",
    include_closed: bool = True,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    company, key = validate_company_code(company_code), validate_app_key(app_key)
    require_permission(permissions, CANDIDATES_READ)
    tenant_zone(timezone_name)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM application_recruiter_tasks
                WHERE company_code=%s AND app_key=%s
                  AND (%s OR status='open')
                ORDER BY CASE WHEN status='open' THEN 0 ELSE 1 END,
                         due_at ASC NULLS LAST, created_at DESC, task_id DESC
                """,
                (company, key, bool(include_closed)),
            )
            rows = cur.fetchall()
    return [serialize_task(row, timezone_name=timezone_name, now=now) for row in rows]


def mutate_application_task(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    task_id: Any,
    actor_user_id: Any,
    expected_version: int,
    permissions: Iterable[Any] | None,
    action: str = "edit",
    title: Any = None,
    description: Any = None,
    priority: Any = None,
    due_at: datetime | None = None,
    assigned_to_user_id: Any = None,
    idempotency_key: Any = None,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
    timezone_name: Any = "Asia/Kuwait",
) -> dict[str, Any]:
    company, key, actor_id = validate_company_code(company_code), validate_app_key(app_key), validate_user_id(actor_user_id)
    task_uuid = validate_user_id(task_id, field="task_id")
    operation = _text(action).lower()
    if operation not in {"edit", "reassign", "complete", "cancel"}:
        raise CollaborationError("task_action_invalid")
    try:
        version = int(expected_version)
    except (TypeError, ValueError):
        raise CollaborationError("task_version_invalid") from None
    idem = _text(idempotency_key) or None
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=CANDIDATES_TASKS_MANAGE)
            if idem:
                cur.execute(
                    "SELECT task_id FROM application_recruiter_task_events WHERE company_code=%s AND app_key=%s AND idempotency_key=%s",
                    (company, key, idem),
                )
                prior = cur.fetchone()
                if prior:
                    cur.execute("SELECT * FROM application_recruiter_tasks WHERE company_code=%s AND app_key=%s AND task_id=%s", (company, key, prior["task_id"]))
                    return {"ok": True, "task": serialize_task(cur.fetchone(), timezone_name=timezone_name), "idempotent": True}
            cur.execute("SELECT * FROM application_recruiter_tasks WHERE company_code=%s AND app_key=%s AND task_id=%s FOR UPDATE", (company, key, task_uuid))
            task = cur.fetchone()
            if not task:
                raise CollaborationError("task_not_found")
            if int(task.get("version") or 0) != version:
                raise CollaborationError("stale_task_version")
            if operation in {"complete", "cancel"} and task.get("status") != "open":
                raise CollaborationError("task_not_open")
            assignee = task.get("assigned_to_user_id")
            if operation == "reassign":
                if not assigned_to_user_id:
                    raise CollaborationError("task_owner_required")
                assignee = validate_user_id(assigned_to_user_id, field="assigned_to_user_id")
                validate_eligible_recruiter(cur, company_code=company, user_id=assignee, permission_resolver=permission_resolver)
            new_title = task.get("title") if title is None else title
            new_priority = task.get("priority") if priority is None else priority
            clean_title, clean_priority = _validate_task_values(new_title, new_priority)
            new_description = task.get("description") if description is None else (_text(description) or None)
            new_due = task.get("due_at") if due_at is None else normalize_due_at(due_at, timezone_name=timezone_name)
            status = {"complete": "completed", "cancel": "cancelled"}.get(operation, task.get("status"))
            confirmation_payload = {
                "app_key": key,
                "task_id": task_uuid,
                "expected_version": version,
                "action": operation,
                "title": clean_title,
                "description": new_description,
                "priority": clean_priority,
                "due_at": new_due,
                "assigned_to_user_id": _text(assignee) or None,
                "idempotency_key": idem,
            }
            _require_assistant_confirmation(
                cur,
                legacy,
                actor_type=actor_type,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action=f"tasks.{operation}",
                payload=confirmation_payload,
            )
            cur.execute(
                """
                UPDATE application_recruiter_tasks
                SET title=%s, description=%s, priority=%s, due_at=%s,
                    assigned_to_user_id=%s, status=%s, version=version+1,
                    completed_at=CASE WHEN %s='completed' THEN now() ELSE completed_at END,
                    cancelled_at=CASE WHEN %s='cancelled' THEN now() ELSE cancelled_at END,
                    updated_by_user_id=%s, updated_at=now()
                WHERE company_code=%s AND app_key=%s AND task_id=%s AND version=%s
                RETURNING *
                """,
                (clean_title, new_description, clean_priority, new_due, assignee, status, status, status, actor_id, company, key, task_uuid, version),
            )
            updated = cur.fetchone()
            if not updated:
                raise CollaborationError("stale_task_version")
            event_type = {"edit": "edited", "reassign": "reassigned", "complete": "completed", "cancel": "cancelled"}[operation]
            payload = {"status": status, "assigned_to_user_id": _text(assignee) or None}
            cur.execute(
                """
                INSERT INTO application_recruiter_task_events
                  (task_id, company_code, app_key, event_type, task_version,
                   actor_user_id, idempotency_key, payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (task_uuid, company, key, event_type, updated["version"], actor_id, idem, _json_value(legacy, payload)),
            )
            event = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "task": serialize_task(updated, timezone_name=timezone_name), "event": event}


def edit_application_task(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return mutate_application_task(legacy, action="edit", **kwargs)


def reassign_application_task(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return mutate_application_task(legacy, action="reassign", **kwargs)


def complete_application_task(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return mutate_application_task(legacy, action="complete", **kwargs)


def cancel_application_task(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return mutate_application_task(legacy, action="cancel", **kwargs)


def canonical_tag_name(value: Any) -> str:
    canonical = " ".join(_text(value).split()).casefold()
    if not canonical or len(canonical) > 100:
        raise CollaborationError("tag_name_invalid")
    return canonical


def create_candidate_tag(
    legacy: Any,
    *,
    company_code: Any,
    actor_user_id: Any,
    name: Any,
    permissions: Iterable[Any] | None,
    label_ar: Any = None,
    color: Any = None,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
) -> dict[str, Any]:
    company, actor_id = validate_company_code(company_code), validate_user_id(actor_user_id)
    display = " ".join(_text(name).split())
    canonical = canonical_tag_name(display)
    clean_color = _text(color) or None
    clean_label_ar = " ".join(_text(label_ar).split()) or None
    if clean_label_ar and len(clean_label_ar) > 100:
        raise CollaborationError("tag_label_ar_invalid")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=CANDIDATES_TAGS_MANAGE)
            _require_assistant_confirmation(
                cur,
                legacy,
                actor_type=actor_type,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action="tags.create",
                payload={"name": display, "label_ar": clean_label_ar, "canonical_name": canonical, "color": clean_color},
            )
            cur.execute(
                """
                INSERT INTO candidate_tag_dictionary
                  (company_code, name, label_ar, canonical_name, color, created_by_user_id)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, canonical_name)
                DO UPDATE SET name=candidate_tag_dictionary.name
                RETURNING *
                """,
                (company, display, clean_label_ar, canonical, clean_color, actor_id),
            )
            tag = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "tag": tag}


def list_candidate_tags(legacy: Any, *, company_code: Any, permissions: Iterable[Any] | None, active_only: bool = True) -> list[dict[str, Any]]:
    company = validate_company_code(company_code)
    require_permission(permissions, CANDIDATES_READ)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM candidate_tag_dictionary WHERE company_code=%s AND (%s=false OR is_active=true) ORDER BY canonical_name, tag_id",
                (company, bool(active_only)),
            )
            return [dict(row) for row in cur.fetchall()]


def list_application_tags(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    permissions: Iterable[Any] | None,
) -> list[dict[str, Any]]:
    company, key = validate_company_code(company_code), validate_app_key(app_key)
    require_permission(permissions, CANDIDATES_READ)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.*, at.added_by_user_id, at.added_at
                FROM application_tags at
                JOIN candidate_tag_dictionary d
                  ON d.company_code=at.company_code AND d.tag_id=at.tag_id
                WHERE at.company_code=%s AND at.app_key=%s
                ORDER BY d.canonical_name, d.tag_id
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]


def _mutate_application_tag(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    tag_id: Any,
    actor_user_id: Any,
    permissions: Iterable[Any] | None,
    add: bool,
    actor_type: str = "human",
    confirmation_id: Any = None,
    confirmation_token: Any = None,
) -> dict[str, Any]:
    company, key, actor_id = validate_company_code(company_code), validate_app_key(app_key), validate_user_id(actor_user_id)
    tag_uuid = validate_user_id(tag_id, field="tag_id")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=CANDIDATES_TAGS_MANAGE)
            _application_for_update(cur, company, key)
            cur.execute("SELECT * FROM candidate_tag_dictionary WHERE company_code=%s AND tag_id=%s AND is_active=true", (company, tag_uuid))
            tag = cur.fetchone()
            if not tag:
                raise CollaborationError("tag_not_found")
            _require_assistant_confirmation(
                cur,
                legacy,
                actor_type=actor_type,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action="tags.add" if add else "tags.remove",
                payload={"app_key": key, "tag_id": tag_uuid},
            )
            if add:
                cur.execute(
                    """
                    INSERT INTO application_tags(company_code, app_key, tag_id, added_by_user_id)
                    VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
                    RETURNING *
                    """,
                    (company, key, tag_uuid, actor_id),
                )
            else:
                cur.execute(
                    "DELETE FROM application_tags WHERE company_code=%s AND app_key=%s AND tag_id=%s RETURNING *",
                    (company, key, tag_uuid),
                )
            changed = cur.fetchone()
            if not changed:
                return {"ok": True, "tag": dict(tag), "skipped": True}
            event_type = "added" if add else "removed"
            cur.execute(
                """
                INSERT INTO application_tag_events
                  (company_code, app_key, tag_id, event_type, actor_user_id)
                VALUES (%s,%s,%s,%s,%s) RETURNING *
                """,
                (company, key, tag_uuid, event_type, actor_id),
            )
            event = dict(cur.fetchone())
        conn.commit()
    return {"ok": True, "tag": dict(tag), "event": event}


def add_application_tag(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return _mutate_application_tag(legacy, add=True, **kwargs)


def remove_application_tag(legacy: Any, **kwargs: Any) -> dict[str, Any]:
    return _mutate_application_tag(legacy, add=False, **kwargs)


def ownership_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"unassigned": 0, "total": 0}
    for row in rows:
        counts["total"] += 1
        owner = _text(row.get("owner_user_id"))
        key = owner or "unassigned"
        counts[key] = counts.get(key, 0) + 1
    return counts


def filter_application_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    owner_user_id: Any = None,
    unassigned: bool = False,
    tag_ids: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    owner = _text(owner_user_id)
    required_tags = {_text(tag) for tag in (tag_ids or ()) if _text(tag)}
    result: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        row_owner = _text(row.get("owner_user_id"))
        row_tags = {_text(tag) for tag in row.get("tag_ids") or ()}
        if unassigned and row_owner:
            continue
        if owner and row_owner != owner:
            continue
        if required_tags and not required_tags.issubset(row_tags):
            continue
        result.append(row)
    return result


def strip_collaboration_fields_from_candidate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-safe serializer for candidate-facing responses."""

    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in INTERNAL_APPLICATION_FIELDS:
            continue
        if isinstance(value, Mapping):
            result[key] = strip_collaboration_fields_from_candidate_payload(value)
        elif isinstance(value, list):
            result[key] = [
                strip_collaboration_fields_from_candidate_payload(item)
                if isinstance(item, Mapping)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def encode_timeline_cursor(occurred_at: datetime, event_id: Any) -> str:
    stamp = _utcnow(occurred_at).isoformat()
    raw = json.dumps({"occurred_at": stamp, "event_id": _text(event_id)}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_timeline_cursor(value: Any) -> tuple[datetime, str]:
    token = _text(value)
    if not token:
        raise CollaborationError("cursor_invalid")
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        stamp = datetime.fromisoformat(_text(data["occurred_at"]).replace("Z", "+00:00"))
        event_id = _text(data["event_id"])
        if not event_id or stamp.tzinfo is None:
            raise ValueError
        return stamp.astimezone(timezone.utc), event_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise CollaborationError("cursor_invalid") from None


TIMELINE_UNION_SQL = """
WITH source_events AS (
  SELECT 'application:' || a.app_key AS source_key,
         'application:' || a.app_key AS event_id,
         'application.created' AS event_type,
         COALESCE(a.ingested_at, a.updated_at) AS occurred_at,
         NULL::text AS actor_user_id, NULL::text AS actor_phone,
         'Application created' AS summary,
         jsonb_build_object('type','application','id',a.app_key) AS entity_ref
  FROM applications a
  WHERE a.company_code=%s AND a.app_key=%s

  UNION ALL
  SELECT 'lifecycle:' || e.event_id::text, e.event_id::text,
         'lifecycle.' || e.to_stage, e.created_at,
         e.actor_user_id::text, e.actor_phone,
         'Stage changed to ' || replace(e.to_stage,'_',' '),
         jsonb_build_object('type','lifecycle_event','id',e.event_id)
  FROM application_lifecycle_events e
  WHERE e.company_code=%s AND e.app_key=%s

  UNION ALL
  SELECT 'ownership:' || e.event_id::text, e.event_id::text,
         'ownership.' || e.event_type, e.created_at,
         e.actor_user_id::text, NULL::text,
         CASE WHEN e.to_owner_user_id IS NULL THEN 'Owner removed' ELSE 'Owner ' || e.event_type END,
         jsonb_build_object('type','ownership_event','id',e.event_id)
  FROM application_ownership_events e
  WHERE e.company_code=%s AND e.app_key=%s

  UNION ALL
  SELECT 'note:' || e.event_id::text, e.event_id::text,
         'note.' || e.event_type, e.created_at,
         e.actor_user_id::text, NULL::text,
         'Note ' || e.event_type,
         jsonb_build_object('type','note','id',e.note_id,'version',e.note_version)
  FROM application_note_events e
  WHERE e.company_code=%s AND e.app_key=%s

  UNION ALL
  SELECT 'document:' || f.file_id::text, f.file_id::text,
         'document.' || COALESCE(NULLIF(f.storage_status,''),'created'), f.created_at,
         NULL::text, NULL::text,
         'Document ' || COALESCE(NULLIF(f.document_type,''),NULLIF(f.file_kind,''),'updated'),
         jsonb_build_object('type','document','id',f.file_id)
  FROM file_registry f
  WHERE f.company_code=%s AND f.subject_type='application' AND f.subject_key=%s

  UNION ALL
  SELECT 'assessment:' || a.attempt_id::text || ':' || COALESCE(a.status,'unknown'),
         'assessment:' || a.attempt_id::text || ':' || COALESCE(a.status,'unknown'),
         'assessment.' || COALESCE(a.status,'updated'), COALESCE(a.completed_at,a.started_at,a.created_at),
         NULL::text, NULL::text,
         'Assessment ' || COALESCE(a.status,'updated'),
         jsonb_build_object('type','assessment_attempt','id',a.attempt_id)
  FROM assessment_attempts a
  WHERE a.company_code=%s AND a.app_key=%s

  UNION ALL
  SELECT 'interview:' || e.event_id::text, e.event_id::text,
         'interview.' || e.event_type, e.created_at,
         e.actor_user_id, e.actor_phone,
         'Interview ' || replace(e.event_type,'_',' '),
         jsonb_build_object('type','interview','id',e.interview_id)
  FROM candidate_interview_events e
  WHERE e.company_code=%s AND e.app_key=%s

  UNION ALL
  SELECT 'delivery:' || d.delivery_id, d.delivery_id,
         'delivery.' || d.status, COALESCE(d.sent_at,d.failed_at,d.recovered_at,d.created_at),
         NULL::text, d.admin_phone,
         'Candidate delivery ' || d.status,
         jsonb_build_object('type','delivery','id',d.delivery_id)
  FROM outbound_delivery_events d
  JOIN applications delivery_app
    ON delivery_app.company_code=d.company_code
   AND delivery_app.app_key=d.subject_key
  WHERE d.company_code=%s AND d.subject_key=%s
    AND d.subject_type IN ('candidate','application')

  UNION ALL
  SELECT 'offer:' || e.event_id::text, e.event_id::text,
         CASE WHEN e.to_status='accepted' THEN 'hiring.offer_accepted' ELSE 'offer.' || e.event_type END,
         e.created_at, e.actor_user_id, e.actor_phone,
         'Offer ' || replace(e.event_type,'_',' '),
         jsonb_build_object('type','offer','id',e.offer_id,'version',e.version)
  FROM employment_offer_events e
  JOIN employment_offers o ON o.offer_id=e.offer_id AND o.company_code=e.company_code
  WHERE e.company_code=%s AND o.app_key=%s

  UNION ALL
  SELECT 'task:' || e.event_id::text, e.event_id::text,
         'task.' || e.event_type, e.created_at,
         e.actor_user_id::text, NULL::text,
         'Task ' || e.event_type,
         jsonb_build_object('type','task','id',e.task_id,'version',e.task_version)
  FROM application_recruiter_task_events e
  WHERE e.company_code=%s AND e.app_key=%s
), deduped AS (
  SELECT *, row_number() OVER (
    PARTITION BY event_type, occurred_at, summary,
                 COALESCE(entity_ref->>'type',''),
                 COALESCE(entity_ref->>'id','')
    ORDER BY source_key, event_id DESC
  ) AS mirror_rank
  FROM source_events
  WHERE occurred_at IS NOT NULL
)
SELECT event_id, event_type, occurred_at,
       jsonb_strip_nulls(jsonb_build_object(
         'user_id',actor_user_id,'phone',actor_phone
       )) AS actor,
       summary, entity_ref
FROM deduped
WHERE mirror_rank=1
  AND (%s::timestamptz IS NULL OR (occurred_at, event_id) < (%s::timestamptz, %s))
ORDER BY occurred_at DESC, event_id DESC
LIMIT %s
"""


def get_application_timeline(
    legacy: Any,
    *,
    company_code: Any,
    app_key: Any,
    permissions: Iterable[Any] | None,
    cursor: Any = None,
    limit: int = 50,
) -> dict[str, Any]:
    company, key = validate_company_code(company_code), validate_app_key(app_key)
    require_permission(permissions, CANDIDATES_READ)
    if limit < 1 or limit > 200:
        raise CollaborationError("limit_invalid")
    cursor_at: datetime | None = None
    cursor_id: str | None = None
    if cursor:
        cursor_at, cursor_id = decode_timeline_cursor(cursor)
    scoped = (company, key)
    params: tuple[Any, ...] = scoped * 10 + (cursor_at, cursor_at, cursor_id, limit + 1)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(TIMELINE_UNION_SQL, params)
            rows = [dict(row) for row in cur.fetchall()]
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        next_cursor = encode_timeline_cursor(page[-1]["occurred_at"], page[-1]["event_id"])
    return {"ok": True, "events": page, "next_cursor": next_cursor}


def normalize_bulk_app_keys(app_keys: Sequence[Any]) -> list[str]:
    if not app_keys:
        raise CollaborationError("bulk_items_required")
    if len(app_keys) > MAX_BULK_ITEMS:
        raise CollaborationError("bulk_too_large")
    keys = [validate_app_key(value) for value in app_keys]
    if len(set(keys)) != len(keys):
        raise CollaborationError("bulk_duplicate_app_key")
    return keys


def build_bulk_binding(
    *,
    company_code: Any,
    actor_user_id: Any,
    operation_type: Any,
    items: Sequence[Mapping[str, Any]],
    target_payload: Mapping[str, Any],
) -> dict[str, Any]:
    company, actor_id = validate_company_code(company_code), validate_user_id(actor_user_id)
    operation = _text(operation_type).lower()
    if operation not in {"assign", "tag_add", "tag_remove"}:
        raise CollaborationError("bulk_operation_invalid")
    bound_items = sorted(
        (
            {
                "app_key": validate_app_key(item.get("app_key")),
                "ownership_version": int(item.get("ownership_version") or 0),
                "lifecycle_version": int(item.get("lifecycle_version") or 0),
                "status": _text(item.get("status")).lower(),
            }
            for item in items
        ),
        key=lambda item: item["app_key"],
    )
    if len({item["app_key"] for item in bound_items}) != len(bound_items):
        raise CollaborationError("bulk_duplicate_app_key")
    payload = {
        "company_code": company,
        "actor_user_id": actor_id,
        "operation_type": operation,
        "items": bound_items,
        "target": _canonical(dict(target_payload)),
    }
    return {"payload": payload, "request_hash": stable_payload_hash(payload)}


def preview_bulk_operation(
    legacy: Any,
    *,
    company_code: Any,
    actor_user_id: Any,
    operation_type: Any,
    app_keys: Sequence[Any],
    target_payload: Mapping[str, Any],
    permissions: Iterable[Any] | None,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
) -> dict[str, Any]:
    company, actor_id = validate_company_code(company_code), validate_user_id(actor_user_id)
    keys = normalize_bulk_app_keys(app_keys)
    operation = _text(operation_type).lower()
    permission = CANDIDATES_ASSIGN if operation == "assign" else CANDIDATES_TAGS_MANAGE
    require_permission(permissions, permission)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=permission)
            if operation == "assign":
                validate_eligible_recruiter(
                    cur,
                    company_code=company,
                    user_id=target_payload.get("owner_user_id"),
                    permission_resolver=permission_resolver,
                )
            else:
                target_tag = validate_user_id(target_payload.get("tag_id"), field="tag_id")
                cur.execute(
                    "SELECT tag_id FROM candidate_tag_dictionary WHERE company_code=%s AND tag_id=%s AND is_active=true",
                    (company, target_tag),
                )
                if not cur.fetchone():
                    raise CollaborationError("tag_not_found")
            cur.execute(
                """
                SELECT app_key, status, lifecycle_version, ownership_version, owner_user_id
                FROM applications
                WHERE company_code=%s AND app_key=ANY(%s)
                ORDER BY app_key
                """,
                (company, keys),
            )
            rows = [dict(row) for row in cur.fetchall()]
            found = {row["app_key"] for row in rows}
            if found != set(keys):
                raise CollaborationError("bulk_application_not_found", details={"app_keys": sorted(set(keys) - found)})
            if operation == "assign":
                target_owner = validate_user_id(target_payload.get("owner_user_id"), field="owner_user_id")
                for row in rows:
                    unchanged = _text(row.get("owner_user_id")) == target_owner
                    row["preview_result"] = "skipped" if unchanged else "eligible"
                    row["preview_reason"] = "already_assigned" if unchanged else None
            else:
                cur.execute(
                    """
                    SELECT app_key
                    FROM application_tags
                    WHERE company_code=%s AND app_key=ANY(%s) AND tag_id=%s
                    """,
                    (company, keys, target_tag),
                )
                tagged = {str(row["app_key"]) for row in cur.fetchall()}
                for row in rows:
                    unchanged = (
                        row["app_key"] in tagged
                        if operation == "tag_add"
                        else row["app_key"] not in tagged
                    )
                    row["preview_result"] = "skipped" if unchanged else "eligible"
                    row["preview_reason"] = "tag_state_unchanged" if unchanged else None
            binding = build_bulk_binding(company_code=company, actor_user_id=actor_id, operation_type=operation, items=rows, target_payload=target_payload)
            cur.execute(
                """
                INSERT INTO candidate_bulk_operations
                  (company_code, actor_user_id, operation_type, request_hash, request_payload)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, actor_user_id, request_hash)
                DO UPDATE SET request_hash=EXCLUDED.request_hash
                RETURNING *
                """,
                (company, actor_id, operation, binding["request_hash"], _json_value(legacy, binding["payload"])),
            )
            operation_row = dict(cur.fetchone())
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO candidate_bulk_operation_items
                      (operation_id, company_code, app_key,
                       observed_ownership_version, observed_lifecycle_version)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (operation_id, app_key) DO NOTHING
                    """,
                    (operation_row["operation_id"], company, row["app_key"], int(row.get("ownership_version") or 0), int(row.get("lifecycle_version") or 0)),
                )
        conn.commit()
    return {"ok": True, "operation": operation_row, "items": rows, "request_hash": binding["request_hash"], "confirmation_payload": binding["payload"]}


def execute_bulk_operation(
    legacy: Any,
    *,
    company_code: Any,
    operation_id: Any,
    actor_user_id: Any,
    confirmation_id: Any,
    confirmation_token: Any,
    permissions: Iterable[Any] | None,
    permission_resolver: Callable[..., Iterable[str]] | None = None,
) -> dict[str, Any]:
    company, actor_id = validate_company_code(company_code), validate_user_id(actor_user_id)
    operation_uuid = validate_user_id(operation_id, field="operation_id")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM candidate_bulk_operations WHERE company_code=%s AND operation_id=%s FOR UPDATE",
                (company, operation_uuid),
            )
            operation = cur.fetchone()
            if not operation:
                raise CollaborationError("bulk_operation_not_found")
            if _text(operation.get("actor_user_id")) != actor_id:
                raise CollaborationError("bulk_operation_actor_mismatch")
            if operation.get("status") == "completed":
                return {"ok": True, "operation": dict(operation), "result": operation.get("result"), "idempotent": True}
            if operation.get("status") != "previewed":
                raise CollaborationError("bulk_operation_not_executable")
            operation_type = operation["operation_type"]
            permission = CANDIDATES_ASSIGN if operation_type == "assign" else CANDIDATES_TAGS_MANAGE
            validate_actor(cur, company_code=company, actor_user_id=actor_id, permissions=permissions, required_permission=permission)
            payload = operation.get("request_payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            if stable_payload_hash(payload) != operation.get("request_hash"):
                raise CollaborationError("bulk_operation_tampered")
            consume_c2_confirmation(
                cur,
                legacy,
                confirmation_id=confirmation_id,
                confirmation_token=confirmation_token,
                company_code=company,
                actor_user_id=actor_id,
                action=f"bulk.{operation_type}",
                payload=payload,
            )
            cur.execute("UPDATE candidate_bulk_operations SET status='processing', confirmation_id=%s WHERE operation_id=%s", (confirmation_id, operation_uuid))
            target = payload.get("target") or {}
            if operation_type == "assign":
                target_owner = validate_user_id(target.get("owner_user_id"), field="owner_user_id")
                validate_eligible_recruiter(cur, company_code=company, user_id=target_owner, permission_resolver=permission_resolver)
            else:
                target_tag = validate_user_id(target.get("tag_id"), field="tag_id")
                cur.execute("SELECT tag_id FROM candidate_tag_dictionary WHERE company_code=%s AND tag_id=%s AND is_active=true", (company, target_tag))
                if not cur.fetchone():
                    raise CollaborationError("tag_not_found")
            results: list[dict[str, Any]] = []
            counts = {"success": 0, "skipped": 0, "stale": 0, "denied": 0}
            for observed in payload.get("items") or []:
                key = validate_app_key(observed.get("app_key"))
                cur.execute(
                    """
                    SELECT app_key, status, lifecycle_version, ownership_version, owner_user_id
                    FROM applications WHERE company_code=%s AND app_key=%s FOR UPDATE
                    """,
                    (company, key),
                )
                current = cur.fetchone()
                status, error = "success", None
                if not current:
                    status, error = "denied", "application_not_found"
                elif int(current.get("ownership_version") or 0) != int(observed.get("ownership_version") or 0) or int(current.get("lifecycle_version") or 0) != int(observed.get("lifecycle_version") or 0) or _text(current.get("status")).lower() != _text(observed.get("status")).lower():
                    status, error = "stale", "observed_state_changed"
                elif operation_type == "assign" and _text(current.get("owner_user_id")) == target_owner:
                    status, error = "skipped", "already_assigned"
                else:
                    if operation_type == "assign":
                        cur.execute(
                            """
                            UPDATE applications
                            SET owner_user_id=%s, ownership_version=ownership_version+1,
                                owner_assigned_at=now(), owner_assigned_by_user_id=%s,
                                updated_at=now()
                            WHERE company_code=%s AND app_key=%s AND ownership_version=%s
                            RETURNING ownership_version
                            """,
                            (target_owner, actor_id, company, key, observed["ownership_version"]),
                        )
                        changed = cur.fetchone()
                        if not changed:
                            status, error = "stale", "ownership_version_changed"
                        else:
                            event_type = "assigned" if not current.get("owner_user_id") else "reassigned"
                            cur.execute(
                                """
                                INSERT INTO application_ownership_events
                                  (company_code, app_key, event_type, from_owner_user_id,
                                   to_owner_user_id, ownership_version, actor_user_id, metadata)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                                """,
                                (company, key, event_type, current.get("owner_user_id"), target_owner, changed["ownership_version"], actor_id, _json_value(legacy, {"bulk_operation_id": operation_uuid})),
                            )
                    else:
                        if operation_type == "tag_add":
                            cur.execute("INSERT INTO application_tags(company_code,app_key,tag_id,added_by_user_id) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING tag_id", (company, key, target_tag, actor_id))
                        else:
                            cur.execute("DELETE FROM application_tags WHERE company_code=%s AND app_key=%s AND tag_id=%s RETURNING tag_id", (company, key, target_tag))
                        changed = cur.fetchone()
                        if not changed:
                            status, error = "skipped", "tag_state_unchanged"
                        else:
                            cur.execute("INSERT INTO application_tag_events(company_code,app_key,tag_id,event_type,actor_user_id,metadata) VALUES (%s,%s,%s,%s,%s,%s)", (company, key, target_tag, "added" if operation_type == "tag_add" else "removed", actor_id, _json_value(legacy, {"bulk_operation_id": operation_uuid})))
                counts[status] += 1
                envelope = {"app_key": key, "status": status, "error": error}
                results.append(envelope)
                cur.execute(
                    """
                    UPDATE candidate_bulk_operation_items
                    SET result_status=%s, error_code=%s, result=%s,
                        processed_at=now()
                    WHERE operation_id=%s AND company_code=%s AND app_key=%s
                    """,
                    (status, error, _json_value(legacy, envelope), operation_uuid, company, key),
                )
            result = {"counts": counts, "items": results}
            cur.execute(
                """
                UPDATE candidate_bulk_operations
                SET status='completed', result=%s, executed_at=now()
                WHERE operation_id=%s RETURNING *
                """,
                (_json_value(legacy, result), operation_uuid),
            )
            completed = dict(cur.fetchone())
            cur.execute("UPDATE candidate_c2_confirmations SET result=%s WHERE confirmation_id=%s", (_json_value(legacy, result), confirmation_id))
        conn.commit()
    return {"ok": True, "operation": completed, "result": result}


__all__ = [
    "CANDIDATES_READ",
    "CANDIDATES_ASSIGN",
    "CANDIDATES_NOTES_MANAGE",
    "CANDIDATES_TASKS_MANAGE",
    "CANDIDATES_TAGS_MANAGE",
    "CANDIDATE_COLLABORATION_PERMISSIONS",
    "CollaborationError",
    "ensure_schema",
    "validate_company_code",
    "validate_app_key",
    "validate_actor",
    "validate_eligible_recruiter",
    "assign_application_owner",
    "claim_application",
    "reassign_application_owner",
    "unassign_application_owner",
    "create_application_note",
    "list_application_notes",
    "edit_application_note",
    "soft_delete_application_note",
    "create_application_task",
    "list_application_tasks",
    "edit_application_task",
    "reassign_application_task",
    "complete_application_task",
    "cancel_application_task",
    "create_candidate_tag",
    "list_candidate_tags",
    "list_application_tags",
    "add_application_tag",
    "remove_application_tag",
    "get_application_timeline",
    "ownership_counts",
    "filter_application_rows",
    "preview_bulk_operation",
    "execute_bulk_operation",
    "mint_c2_confirmation",
    "consume_c2_confirmation",
    "normalize_due_at",
    "strip_collaboration_fields_from_candidate_payload",
]
