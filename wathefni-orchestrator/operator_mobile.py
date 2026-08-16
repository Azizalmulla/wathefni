"""HR-1 — Wathefni HR operator mobile authentication and capability contract.

Backend-only. Separate from employee `/app/auth/*` and browser dashboard sessions.
All authority is recomputed from backend-current grants on every request.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable

logger = logging.getLogger("wathefni.operator_mobile")

# ---------------------------------------------------------------------------
# Session / auth constants
# ---------------------------------------------------------------------------

SESSION_CHANNEL = "operator_mobile"
# Short access TTL forces authority recompute; refresh is the trusted-device
# continuity secret. Replay-protected rotation + operator/company checks on
# every refresh are the security control — not a short refresh lifetime.
ACCESS_TTL = timedelta(minutes=45)
REFRESH_TTL = timedelta(days=90)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_MAX_FAILURES = 8
LOGIN_LOCK = timedelta(minutes=15)

# MFA extension point — not enforced in HR-1.
MFA_EXTENSION = {
    "required": False,
    "enforced": False,
    "methods_available": [],
    "challenge_ready": False,
    "note": "MFA challenge hook reserved; HR-1 login does not weaken auth to add MFA later.",
}

# Client SecureStore contract (HR operator namespace — never Employee keys).
SECURE_STORE_CONTRACT = {
    "session_blob_key": "wathefni.hr.session.v1",
    "access_token_key": "wathefni.hr.access_token",  # legacy shard; migrated into blob
    "refresh_token_key": "wathefni.hr.refresh_token",  # legacy shard; migrated into blob
    "company_code_key": "wathefni.hr.company_code",
    "expires_at_key": "wathefni.hr.access_expires_at",
    "rules": [
        "Store only opaque tokens issued by /dashboard/mobile/auth/*.",
        "Persist access+refresh atomically in wathefni.hr.session.v1 (single keystore value).",
        "Never persist role, permissions, modules, or manager scope locally as authority.",
        "On every cold start call GET /dashboard/mobile/me and trust only that response.",
        "Access expiry must refresh invisibly; clear SecureStore only on definitive revoke/termination.",
        "If session_revoked arrives after another local rotation, reload SecureStore before clearing.",
        "Do not write tokens into logs, analytics, or crash reports.",
        "HR keys must never collide with Employee wathefni.session.* keys.",
    ],
}


# ---------------------------------------------------------------------------
# Request models (pydantic loaded lazily so unit smokes work without fastapi)
# ---------------------------------------------------------------------------

def _models():
    from pydantic import BaseModel, Field

    class MobileLoginRequest(BaseModel):
        email: str | None = None
        password: str | None = None
        company_code: str | None = None

    class MobileRefreshRequest(BaseModel):
        refresh_token: str | None = None

    class MobileLogoutRequest(BaseModel):
        refresh_token: str | None = None

    return MobileLoginRequest, MobileRefreshRequest, MobileLogoutRequest


# Populated on first route registration for FastAPI type hints.
MobileLoginRequest = None  # type: ignore[assignment]
MobileRefreshRequest = None  # type: ignore[assignment]
MobileLogoutRequest = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

OPERATOR_MOBILE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_operator_mobile_sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES dashboard_users(user_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  access_token_hash text NOT NULL UNIQUE,
  refresh_token_hash text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  refresh_expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  revoked_reason text,
  rotated_from_session_id uuid,
  device_label text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_op_mobile_sessions_user
  ON dashboard_operator_mobile_sessions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_op_mobile_sessions_company
  ON dashboard_operator_mobile_sessions(company_code, status);
CREATE INDEX IF NOT EXISTS idx_op_mobile_sessions_refresh
  ON dashboard_operator_mobile_sessions(refresh_token_hash);

CREATE TABLE IF NOT EXISTS dashboard_operator_mobile_login_attempts (
  attempt_key text PRIMARY KEY,
  fail_count int NOT NULL DEFAULT 0,
  window_started_at timestamptz NOT NULL DEFAULT now(),
  locked_until timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);
"""


def ensure_operator_mobile_schema(app_mod: Any) -> None:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(OPERATOR_MOBILE_SCHEMA_SQL)
        conn.commit()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _token_hash(token: str | None) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _login_attempt_key(company_code: str, email: str) -> str:
    raw = f"{str(company_code or '').strip().upper()}|{str(email or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _auth_failed(app_mod: Any, *, code: str = "invalid_credentials", message: str | None = None, status: int = 401):
    from fastapi import HTTPException

    return HTTPException(
        status_code=status,
        detail={
            "error": code,
            "message": message or "Access needs to be verified.",
            "channel": SESSION_CHANNEL,
        },
    )


def _generic_login_failure() -> HTTPException:
    # Never reveal whether email/company/account exists.
    return _auth_failed(None, code="invalid_credentials")


# ---------------------------------------------------------------------------
# Login rate limiting
# ---------------------------------------------------------------------------

def _login_rate_guard(app_mod: Any, company_code: str, email: str) -> None:
    key = _login_attempt_key(company_code, email)
    now = app_mod.now_utc()
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_operator_mobile_login_attempts WHERE attempt_key=%s LIMIT 1 FOR UPDATE",
                (key,),
            )
            row = cur.fetchone()
            if row:
                locked_until = row.get("locked_until")
                if locked_until and locked_until > now:
                    raise _auth_failed(
                        app_mod,
                        code="rate_limited",
                        message="Too many sign-in attempts. Try again later.",
                        status=429,
                    )
                window_started = row.get("window_started_at") or now
                if window_started + LOGIN_WINDOW < now:
                    cur.execute(
                        """
                        UPDATE dashboard_operator_mobile_login_attempts
                        SET fail_count=0, window_started_at=now(), locked_until=NULL, updated_at=now()
                        WHERE attempt_key=%s
                        """,
                        (key,),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO dashboard_operator_mobile_login_attempts (attempt_key)
                    VALUES (%s) ON CONFLICT (attempt_key) DO NOTHING
                    """,
                    (key,),
                )
        conn.commit()


def _record_login_failure(app_mod: Any, company_code: str, email: str) -> None:
    key = _login_attempt_key(company_code, email)
    now = app_mod.now_utc()
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_operator_mobile_login_attempts WHERE attempt_key=%s LIMIT 1 FOR UPDATE",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    INSERT INTO dashboard_operator_mobile_login_attempts
                      (attempt_key, fail_count, window_started_at, updated_at)
                    VALUES (%s, 1, now(), now())
                    """,
                    (key,),
                )
            else:
                window_started = row.get("window_started_at") or now
                fail_count = int(row.get("fail_count") or 0)
                if window_started + LOGIN_WINDOW < now:
                    fail_count = 0
                    window_started = now
                fail_count += 1
                locked_until = None
                if fail_count >= LOGIN_MAX_FAILURES:
                    locked_until = now + LOGIN_LOCK
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_login_attempts
                    SET fail_count=%s, window_started_at=%s, locked_until=%s, updated_at=now()
                    WHERE attempt_key=%s
                    """,
                    (fail_count, window_started, locked_until, key),
                )
        conn.commit()


def _clear_login_failures(app_mod: Any, company_code: str, email: str) -> None:
    key = _login_attempt_key(company_code, email)
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_login_attempts
                SET fail_count=0, locked_until=NULL, window_started_at=now(), updated_at=now()
                WHERE attempt_key=%s
                """,
                (key,),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def create_operator_mobile_session(
    app_mod: Any,
    user: dict[str, Any],
    *,
    rotated_from_session_id: str | None = None,
    device_label: str | None = None,
) -> dict[str, Any]:
    access = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(48)
    now = app_mod.now_utc()
    expires_at = now + ACCESS_TTL
    refresh_expires_at = now + REFRESH_TTL
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_operator_mobile_sessions
                  (user_id, company_code, access_token_hash, refresh_token_hash,
                   expires_at, refresh_expires_at, rotated_from_session_id, device_label, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING session_id
                """,
                (
                    user["user_id"],
                    str(user["company_code"]).upper(),
                    _token_hash(access),
                    _token_hash(refresh),
                    expires_at,
                    refresh_expires_at,
                    rotated_from_session_id,
                    (device_label or "")[:120] or None,
                    app_mod.Json({"channel": SESSION_CHANNEL}),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return {
        "session_id": str(row["session_id"]),
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": expires_at,
        "refresh_expires_at": refresh_expires_at,
        "token_type": "bearer",
        "channel": SESSION_CHANNEL,
    }


def _load_user_by_id(app_mod: Any, user_id: str, company_code: str) -> dict[str, Any] | None:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_users WHERE user_id=%s AND company_code=%s LIMIT 1",
                (user_id, str(company_code or "").upper()),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def operator_mobile_user_by_access_token(app_mod: Any, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = _token_hash(token)
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.session_id, s.company_code AS session_company, s.expires_at AS session_expires_at,
                       s.refresh_expires_at, s.status AS session_status, s.revoked_reason,
                       u.*
                FROM dashboard_operator_mobile_sessions s
                JOIN dashboard_users u ON u.user_id = s.user_id
                WHERE s.access_token_hash=%s
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            if str(data.get("session_status") or "") != "active":
                data["_session_denial"] = "session_revoked"
                return data
            if data.get("session_expires_at") and data["session_expires_at"] <= app_mod.now_utc():
                data["_session_denial"] = "session_expired"
                return data
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_sessions
                SET last_seen_at=now()
                WHERE session_id=%s
                """,
                (data["session_id"],),
            )
            cur.execute(
                "UPDATE dashboard_users SET last_active_at=now(), updated_at=now() WHERE user_id=%s",
                (data["user_id"],),
            )
        conn.commit()
    data.pop("session_company", None)
    return data


def rotate_operator_mobile_session(app_mod: Any, refresh_token: str | None) -> dict[str, Any]:
    if not refresh_token:
        raise _auth_failed(app_mod, code="session_expired")
    presented = _token_hash(refresh_token)
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_operator_mobile_sessions
                WHERE refresh_token_hash=%s
                LIMIT 1 FOR UPDATE
                """,
                (presented,),
            )
            row = cur.fetchone()
            if not row:
                # Possible replay of an already-rotated refresh token.
                raise _auth_failed(app_mod, code="session_revoked", message="This session is no longer valid.")
            sess = dict(row)
            if str(sess.get("status") or "") != "active":
                raise _auth_failed(app_mod, code="session_revoked", message="This session is no longer valid.")
            if not sess.get("refresh_expires_at") or sess["refresh_expires_at"] <= app_mod.now_utc():
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_sessions
                    SET status='revoked', revoked_at=now(), revoked_reason='refresh_expired'
                    WHERE session_id=%s
                    """,
                    (sess["session_id"],),
                )
                conn.commit()
                raise _auth_failed(app_mod, code="session_expired")

            cur.execute(
                "SELECT * FROM dashboard_users WHERE user_id=%s AND company_code=%s LIMIT 1",
                (sess["user_id"], sess["company_code"]),
            )
            user_row = cur.fetchone()
            if not user_row:
                raise _auth_failed(app_mod, code="operator_disabled")
            user = dict(user_row)
            if app_mod.normalize_dashboard_user_status(user.get("status")) != "active":
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_sessions
                    SET status='revoked', revoked_at=now(), revoked_reason='operator_disabled'
                    WHERE session_id=%s
                    """,
                    (sess["session_id"],),
                )
                conn.commit()
                raise _auth_failed(app_mod, code="operator_disabled", status=403, message="Your account is not active.")

            company = str(sess["company_code"]).upper()
            lifecycle = app_mod.company_lifecycle_status(company)
            if lifecycle != "active":
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_sessions
                    SET status='revoked', revoked_at=now(), revoked_reason=%s
                    WHERE session_id=%s
                    """,
                    (f"company_{lifecycle}", sess["session_id"]),
                )
                conn.commit()
                raise _auth_failed(
                    app_mod,
                    code=f"company_{lifecycle}",
                    status=403,
                    message="This company workspace is not active.",
                )

            # Mark current refresh as rotated (replay of this refresh fails closed).
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_sessions
                SET status='rotated', revoked_at=now(), revoked_reason='rotated'
                WHERE session_id=%s
                """,
                (sess["session_id"],),
            )
        conn.commit()

    tokens = create_operator_mobile_session(
        app_mod,
        user,
        rotated_from_session_id=str(sess["session_id"]),
        device_label=sess.get("device_label"),
    )
    return {"user": user, "tokens": tokens}


def revoke_operator_mobile_access_token(app_mod: Any, access_token: str | None, *, reason: str = "logout") -> bool:
    if not access_token:
        return False
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_sessions
                SET status='revoked', revoked_at=now(), revoked_reason=%s
                WHERE access_token_hash=%s AND status='active'
                """,
                (reason, _token_hash(access_token)),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def revoke_operator_mobile_refresh_token(app_mod: Any, refresh_token: str | None, *, reason: str = "logout") -> bool:
    if not refresh_token:
        return False
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_sessions
                SET status='revoked', revoked_at=now(), revoked_reason=%s
                WHERE refresh_token_hash=%s AND status IN ('active', 'rotated')
                """,
                (reason, _token_hash(refresh_token)),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def revoke_all_operator_mobile_sessions_for_user(app_mod: Any, user_id: str, *, reason: str = "logout_all") -> int:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_sessions
                SET status='revoked', revoked_at=now(), revoked_reason=%s
                WHERE user_id=%s AND status='active'
                """,
                (reason, user_id),
            )
            count = cur.rowcount
        conn.commit()
    return int(count or 0)


def revoke_company_operator_mobile_sessions(cur: Any, company_code: str, *, reason: str) -> int:
    cur.execute(
        """
        UPDATE dashboard_operator_mobile_sessions
        SET status='revoked', revoked_at=now(), revoked_reason=%s
        WHERE company_code=%s AND status='active'
        """,
        (reason, str(company_code or "").upper()),
    )
    return int(cur.rowcount or 0)


def revoke_user_operator_mobile_sessions(cur: Any, user_id: str, *, reason: str = "operator_disabled") -> int:
    cur.execute(
        """
        UPDATE dashboard_operator_mobile_sessions
        SET status='revoked', revoked_at=now(), revoked_reason=%s
        WHERE user_id=%s AND status='active'
        """,
        (reason, user_id),
    )
    return int(cur.rowcount or 0)


# ---------------------------------------------------------------------------
# Context + capability contract
# ---------------------------------------------------------------------------

def dashboard_session_token_exists(app_mod: Any, token: str | None) -> bool:
    """Read-only check — does not bump last_seen_at."""
    if not token:
        return False
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM dashboard_user_sessions
                WHERE token_hash=%s AND status='active' AND expires_at > now()
                LIMIT 1
                """,
                (_token_hash(token),),
            )
            return bool(cur.fetchone())


def build_operator_mobile_context(app_mod: Any, user: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
    public = app_mod.dashboard_user_public(user)
    company = public["company_code"]
    access = app_mod.dashboard_access_payload_for_user(user)
    scope = app_mod.operator_manager_scope(
        company_code=company,
        manager_phone=public.get("phone"),
        dashboard_user_id=public.get("user_id"),
        actor_role=public.get("role"),
    )
    return {
        "company_code": company,
        "hr_phone": public.get("phone") or "",
        "hr_user": public,
        "access": access,
        "permissions": access["permissions"],
        "permission_authority": "backend_current",
        "permission_subject_user_id": access["permission_subject_user_id"],
        "permission_subject_company": access["permission_subject_company"],
        "actor_user_id": public["user_id"],
        "actor_email": public["email"],
        "actor_phone": public.get("phone") or "",
        "actor_role": public["role"],
        "actor": public,
        "scope": scope,
        "session_channel": SESSION_CHANNEL,
        "mobile_session_id": session_id,
    }


def _feature(
    *,
    enabled: bool,
    actions: list[str] | None = None,
    reason: str | None = None,
    confirmation_required: bool = False,
    advisory: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"enabled": bool(enabled), "actions": list(actions or []) if enabled else []}
    if reason and not enabled:
        payload["reason"] = reason
    if confirmation_required:
        payload["confirmation_required"] = True
    if advisory:
        payload["advisory"] = True
    return payload


def _has(perms: set[str], *needed: str) -> bool:
    return any(p in perms for p in needed)


def _module_on(app_mod: Any, company: str, *modules: str) -> bool:
    return any(app_mod.company_has_module(company, m) for m in modules)


def build_hr_workspace_capabilities(app_mod: Any, context: dict[str, Any]) -> dict[str, Any]:
    company = context["company_code"]
    perms = set(context.get("permissions") or [])
    role = str(context.get("actor_role") or "")
    scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    scope_blocked = bool(scope.get("configuration_error") or scope.get("blocked"))
    if role == "manager" and scope_blocked:
        # Fail-closed manager: no HR operational features until scope is healthy.
        disabled = _feature(enabled=False, reason="manager_scope_conflict" if scope.get("configuration_error") == "manager_scope_binding_conflict" else "manager_scope_missing")
        keys = [
            "hr_tasks", "leave_approvals", "onboarding_review", "preboarding_review", "probation_review", "performance_reviews", "employee_relations_actions", "document_review",
            "attendance_exceptions", "today_shifts", "shift_swap_decisions",
            "employee_search", "employee_quick_profile", "delivery_alerts", "assistant",
        ]
        return {k: dict(disabled) for k in keys}

    leave_mod = _module_on(app_mod, company, "leave")
    onboarding_mod = _module_on(app_mod, company, "onboarding")
    preboarding_mod = _module_on(app_mod, company, "preboarding")
    probation_mod = _module_on(app_mod, company, "probation")
    performance_mod = _module_on(app_mod, company, "performance")
    er_mod = _module_on(app_mod, company, "employee_relations")
    compliance_mod = _module_on(app_mod, company, "compliance")
    attendance_mod = _module_on(app_mod, company, "attendance")
    shifts_mod = _module_on(app_mod, company, "shifts")
    any_posthire = leave_mod or onboarding_mod or preboarding_mod or probation_mod or performance_mod or compliance_mod or attendance_mod or shifts_mod or _module_on(
        app_mod, company, "payroll"
    )
    onboarding_mutation_on = bool(
        onboarding_mod
        and callable(getattr(app_mod, "onboarding_hr_mutate_enabled_for_company", None))
        and app_mod.onboarding_hr_mutate_enabled_for_company(company)
    )

    leave_actions = []
    if leave_mod and "leave.read" in perms:
        leave_actions.append("read")
    if leave_mod and "leave.decide" in perms:
        leave_actions.extend(["approve", "reject"])

    onboarding_actions = []
    if onboarding_mod and "onboarding.read" in perms:
        onboarding_actions.append("read")
    if onboarding_mutation_on and "onboarding.manage" in perms:
        onboarding_actions.append("review")

    preboarding_actions = []
    if preboarding_mod and "preboarding.read" in perms:
        preboarding_actions.append("read")
    if preboarding_mod and _has(perms, "preboarding.manage", "preboarding.waive_item"):
        preboarding_actions.extend(["review", "waive"])

    probation_actions = []
    if probation_mod and "probation.read" in perms:
        probation_actions.append("read")
    if probation_mod and "probation.manage" in perms:
        probation_actions.extend(["review", "recommend"])
    if probation_mod and "probation.decide" in perms:
        probation_actions.append("decide")

    performance_actions = []
    if performance_mod and "performance.read" in perms:
        performance_actions.append("read")
    if performance_mod and "performance.manage" in perms:
        performance_actions.append("submit")

    er_actions = []
    if er_mod and role != "manager" and "er.read" in perms:
        er_actions.append("read")
    if er_mod and role != "manager" and ("er.manage" in perms or "er.investigate" in perms):
        er_actions.append("acknowledge")

    doc_actions = []
    if (onboarding_mod or compliance_mod) and _has(perms, "onboarding.read", "compliance.read"):
        doc_actions.append("read")
    if (onboarding_mutation_on and "onboarding.manage" in perms) or (
        compliance_mod and "compliance.manage" in perms
    ):
        doc_actions.append("review")

    attendance_actions = []
    if attendance_mod and "attendance.read" in perms:
        attendance_actions.append("read")
    if attendance_mod and "attendance.manage" in perms:
        attendance_actions.append("resolve")

    shift_actions = []
    if shifts_mod and "shifts.read" in perms:
        shift_actions.append("read")
    swap_actions = []
    if shifts_mod and "shifts.manage" in perms:
        swap_actions.extend(["read", "approve", "reject"])

    emp_read = "employees.read" in perms

    hr_task_read = any_posthire and _has(
        perms,
        "leave.read",
        "attendance.read",
        "onboarding.read",
        "compliance.read",
        "shifts.read",
        "payroll.read",
    )
    hr_task_actions: list[str] = []
    if hr_task_read:
        hr_task_actions.append("read")
    # Align with dashboard _hr_tasks_context(manage=True): users.manage or any posthire .manage.
    if any_posthire and (
        "users.manage" in perms
        or _has(
            perms,
            "leave.manage",
            "attendance.manage",
            "onboarding.manage",
            "compliance.manage",
            "shifts.manage",
            "payroll.manage",
        )
    ):
        hr_task_actions.append("resolve")

    try:
        from operator_mobile_assistant import assistant_mobile_offerable

        assistant_on = bool(assistant_mobile_offerable(app_mod, context))
    except Exception:
        assistant_on = False

    return {
        "hr_tasks": _feature(
            enabled=hr_task_read,
            actions=hr_task_actions,
            reason="module_disabled" if not any_posthire else "action_forbidden",
        ),
        "leave_approvals": _feature(
            enabled=bool(leave_actions),
            actions=leave_actions,
            reason="module_disabled" if not leave_mod else "action_forbidden",
        ),
        "onboarding_review": _feature(
            enabled=bool(onboarding_actions),
            actions=onboarding_actions,
            reason="module_disabled" if not onboarding_mod else "action_forbidden",
        ),
        "preboarding_review": _feature(
            enabled=bool(preboarding_actions),
            actions=preboarding_actions,
            reason="module_disabled" if not preboarding_mod else "action_forbidden",
        ),
        "probation_review": _feature(
            enabled=bool(probation_actions),
            actions=probation_actions,
            reason="module_disabled" if not probation_mod else "action_forbidden",
        ),
        "performance_reviews": _feature(
            enabled=bool(performance_actions),
            actions=performance_actions,
            reason="module_disabled" if not performance_mod else "action_forbidden",
        ),
        "employee_relations_actions": _feature(
            enabled=bool(er_actions),
            actions=er_actions,
            reason="module_disabled" if not er_mod else "action_forbidden",
        ),
        "document_review": _feature(
            enabled=bool(doc_actions),
            actions=doc_actions,
            reason="module_disabled" if not (onboarding_mod or compliance_mod) else "action_forbidden",
        ),
        "attendance_exceptions": _feature(
            enabled=bool(attendance_actions),
            actions=attendance_actions,
            reason="module_disabled" if not attendance_mod else "action_forbidden",
        ),
        "today_shifts": _feature(
            enabled=bool(shift_actions),
            actions=shift_actions,
            reason="module_disabled" if not shifts_mod else "action_forbidden",
        ),
        "shift_swap_decisions": _feature(
            enabled=bool(swap_actions),
            actions=swap_actions,
            reason="module_disabled" if not shifts_mod else "action_forbidden",
        ),
        "employee_search": _feature(
            enabled=emp_read,
            actions=["read"] if emp_read else [],
            reason="action_forbidden",
        ),
        "employee_quick_profile": _feature(
            enabled=emp_read,
            actions=["read"] if emp_read else [],
            reason="action_forbidden",
        ),
        "delivery_alerts": _feature(
            # Same read authority OR as hr_tasks / dashboard outbound (_hr_tasks_context):
            # any post-hire module + matching .read (includes payroll.read). Read-only.
            enabled=hr_task_read,
            actions=["read"] if hr_task_read else [],
            reason="module_disabled" if not any_posthire else "action_forbidden",
        ),
        "assistant": _feature(
            enabled=assistant_on,
            actions=["chat", "read"] if assistant_on else [],
            reason="assistant_unavailable" if not assistant_on else None,
        ),
    }


def _capability_permissions(app_mod: Any, context: dict[str, Any]) -> set[str]:
    """Use the same backend_current authority as require_entitlement when available."""
    if hasattr(app_mod, "context_permissions"):
        return {str(item) for item in app_mod.context_permissions(context) if str(item).strip()}
    return {str(item) for item in (context.get("permissions") or []) if str(item).strip()}


def build_recruiting_workspace_capabilities(app_mod: Any, context: dict[str, Any]) -> dict[str, Any]:
    company = context["company_code"]
    perms = _capability_permissions(app_mod, context)
    prehire = _module_on(app_mod, company, "pre_hiring")
    interviews = _module_on(app_mod, company, "interviews")
    can_read = prehire and "prehire.read" in perms
    can_manage = prehire and "candidate.manage" in perms
    can_decide = prehire and "candidate.decide" in perms
    can_interview = interviews and "interview.manage" in perms
    assessments = _module_on(app_mod, company, "assessments")

    # Unavailable until a safe mobile endpoint exists — explicitly disabled.
    unavailable = _feature(enabled=False, reason="feature_disabled")

    features: dict[str, Any] = {
        "candidate_rankings": _feature(
            enabled=can_read,
            actions=["read"] if can_read else [],
            reason="module_disabled" if not prehire else "action_forbidden",
            advisory=True,
        ),
        "candidate_summary": _feature(enabled=can_read, actions=["read"] if can_read else [], reason="module_disabled" if not prehire else "action_forbidden"),
        "candidate_evidence": _feature(enabled=can_read, actions=["read"] if can_read else [], reason="module_disabled" if not prehire else "action_forbidden"),
        "candidate_cv": _feature(
            enabled=can_read,
            actions=["view", "preview", "download"] if can_read else [],
            reason="module_disabled" if not prehire else "action_forbidden",
        ),
        "candidate_shortlist": _feature(
            enabled=can_manage,
            actions=["shortlist"] if can_manage else [],
            reason="module_disabled" if not prehire else "action_forbidden",
            confirmation_required=True,
        ),
        "candidate_reject": _feature(
            enabled=can_decide,
            actions=["reject"] if can_decide else [],
            reason="module_disabled" if not prehire else "action_forbidden",
            confirmation_required=True,
        ),
        "candidate_hire": _feature(
            enabled=can_decide,
            actions=["hire"] if can_decide else [],
            reason="module_disabled" if not prehire else "action_forbidden",
            confirmation_required=True,
        ),
        "employment_offers": _feature(
            enabled=_module_on(app_mod, company, "employment_offers") and (
                "offer.approve" in perms
                or "offer.record_response" in perms
                or "offer.withdraw" in perms
                or "prehire.read" in perms
            ),
            actions=(
                (["read"] if "prehire.read" in perms else [])
                + (["approve", "return_draft"] if "offer.approve" in perms else [])
                + (["record_accept", "record_decline"] if "offer.record_response" in perms else [])
                + (["withdraw"] if "offer.withdraw" in perms else [])
            ),
            reason="module_disabled" if not _module_on(app_mod, company, "employment_offers") else "action_forbidden",
            confirmation_required=True,
        ),
        "candidate_communication_status": _feature(
            enabled=can_manage or can_read,
            actions=["read"] if (can_manage or can_read) else [],
            reason="module_disabled" if not prehire else "action_forbidden",
        ),
        # Explicitly unavailable mobile surfaces
        "new_candidate_push": unavailable,
        "interview_reschedule": unavailable,
        "kanban_stage_management": unavailable,
        "bulk_import": unavailable,
        "job_pipeline_configuration": unavailable,
        "ai_scoring_configuration": unavailable,
    }
    # Omit Assessments entirely when the module is OFF (do not advertise a disabled key).
    if assessments:
        features["assessments"] = _feature(
            enabled=can_read,
            actions=["read"] if can_read else [],
            reason="action_forbidden",
            advisory=True,
        )
    # Live interview mobile surfaces require the interviews module.
    if interviews:
        features["interview_status"] = _feature(
            enabled=can_read or can_interview,
            actions=["read"] if (can_read or can_interview) else [],
            reason="action_forbidden",
        )
        features["interview_notes"] = _feature(
            enabled=can_interview,
            actions=["read", "write"] if can_interview else [],
            reason="action_forbidden",
        )

    # Requisitions — works alone (no HARD pre_hiring dependency).
    req_mod = _module_on(app_mod, company, "requisitions")
    req_actions: list[str] = []
    if req_mod and "requisitions.read" in perms:
        req_actions.append("read")
    if req_mod and "requisitions.manage" in perms:
        req_actions.append("manage")
    if req_mod and "requisitions.approve" in perms:
        req_actions.append("approve")
    features["requisitions_review"] = _feature(
        enabled=bool(req_actions),
        actions=req_actions,
        reason="module_disabled" if not req_mod else "action_forbidden",
        confirmation_required=True,
    )
    return features


def build_owner_workspace_capabilities(app_mod: Any, context: dict[str, Any]) -> dict[str, Any]:
    # HR-1: no owner-only mobile features yet. Do not invent a dashboard.
    # Owner users still receive HR/recruiting capabilities via those namespaces.
    return {
        "enabled": False,
        "features": {},
        "reason": "feature_disabled",
        "note": "Owner mobile workspace reserved; Setup Console and provisioning stay out of OctoHR.",
    }


def _scope_metadata(scope: dict[str, Any], role: str) -> dict[str, Any]:
    error = str(scope.get("configuration_error") or "").strip()
    restricted = bool(scope.get("restricted"))
    binding = str(scope.get("scope_authority") or "")
    if not binding:
        if scope.get("dashboard_user_id"):
            binding = "dashboard_user_id"
        elif scope.get("manager_phone"):
            binding = "phone_transitional"
        else:
            binding = "none"
    configured = True
    if role == "manager":
        configured = not error and (restricted or scope.get("scopes") is not None)
        if error in {"manager_scope_unconfigured", "manager_scope_binding_missing", "manager_scope_empty"}:
            configured = False
    return {
        "restricted": restricted if role == "manager" or restricted else False,
        "binding": binding if role == "manager" or restricted else "unrestricted",
        "configured": configured if role == "manager" else True,
        "configuration_error": error or None,
    }


def build_mobile_me_payload(app_mod: Any, context: dict[str, Any]) -> dict[str, Any]:
    public = context.get("hr_user") if isinstance(context.get("hr_user"), dict) else app_mod.dashboard_user_public(context.get("actor"))
    company = context["company_code"]
    company_state = app_mod.company_lifecycle_status(company)
    account_state = str(public.get("status") or "active")
    role = str(context.get("actor_role") or public.get("role") or "")
    scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    hr_features = build_hr_workspace_capabilities(app_mod, context)
    recruiting_features = build_recruiting_workspace_capabilities(app_mod, context)
    owner = build_owner_workspace_capabilities(app_mod, context)

    hr_enabled = any(bool((v or {}).get("enabled")) for v in hr_features.values())
    recruiting_enabled = any(
        bool((v or {}).get("enabled"))
        for k, v in recruiting_features.items()
        if k
        not in {
            "new_candidate_push",
            "interview_reschedule",
            "kanban_stage_management",
            "bulk_import",
            "job_pipeline_configuration",
            "ai_scoring_configuration",
        }
    )

    return {
        "ok": True,
        "company_identity": app_mod.mobile_company_identity(company),
        "principal": {
            "user_id": public.get("user_id"),
            "company_code": company,
            "display_name": public.get("name") or public.get("email") or "",
            "email": public.get("email") or "",
            "role": role,
            "role_label": public.get("role_label") or role,
        },
        "permission_authority": "backend_current",
        "account_state": account_state,
        "company_state": company_state,
        "workspaces": {
            "hr": {"enabled": hr_enabled, "features": hr_features},
            "recruiting": {"enabled": recruiting_enabled, "features": recruiting_features},
            "owner": owner,
        },
        "scope": _scope_metadata(scope, role),
        "mfa": MFA_EXTENSION,
        "secure_store": SECURE_STORE_CONTRACT,
        "session": {
            "channel": SESSION_CHANNEL,
            "company_bound": True,
            "mobile_session_id": context.get("mobile_session_id"),
        },
    }


def _auth_tokens_response(app_mod: Any, user: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    context = build_operator_mobile_context(app_mod, user, session_id=tokens.get("session_id"))
    me = build_mobile_me_payload(app_mod, context)
    return {
        "ok": True,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_at": tokens["expires_at"].isoformat() if hasattr(tokens["expires_at"], "isoformat") else tokens["expires_at"],
        "refresh_expires_at": tokens["refresh_expires_at"].isoformat()
        if hasattr(tokens["refresh_expires_at"], "isoformat")
        else tokens["refresh_expires_at"],
        "company_code": str(user.get("company_code") or "").upper(),
        "channel": SESSION_CHANNEL,
        "mfa": MFA_EXTENSION,
        "secure_store": SECURE_STORE_CONTRACT,
        "me": me,
    }


# ---------------------------------------------------------------------------
# Route handlers (registered from app.py)
# ---------------------------------------------------------------------------

def register_operator_mobile_routes(app_mod: Any) -> None:
    """Attach /dashboard/mobile/* routes onto the FastAPI app."""
    from fastapi import Depends, Header

    global MobileLoginRequest, MobileRefreshRequest, MobileLogoutRequest
    MobileLoginRequest, MobileRefreshRequest, MobileLogoutRequest = _models()

    def operator_mobile_context(
        authorization: str | None = Header(default=None),
        x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
        x_company_code: str | None = Header(default=None, alias="X-Company-Code"),
    ) -> dict[str, Any]:
        app_mod.ensure_schema()
        ensure_operator_mobile_schema(app_mod)
        token = app_mod.bearer_token(authorization) or str(x_dashboard_token or "").strip()
        if not token:
            raise _auth_failed(app_mod, code="session_expired")

        # Reject employee / browser tokens explicitly before mobile lookup ambiguity.
        if app_mod.employee_by_session(token):
            raise _auth_failed(app_mod, code="employee_token_rejected")
        # Shared legacy dashboard token must never establish mobile operator context.
        configured = app_mod.dashboard_configured_token()
        if configured and hmac.compare_digest(token, configured):
            raise _auth_failed(app_mod, code="legacy_authority_rejected")

        row = operator_mobile_user_by_access_token(app_mod, token)
        if row and row.get("_session_denial"):
            raise _auth_failed(app_mod, code=str(row["_session_denial"]))
        if not row:
            # If this is a browser dashboard session, reject with a clear code.
            if dashboard_session_token_exists(app_mod, token):
                raise _auth_failed(app_mod, code="browser_session_rejected")
            raise _auth_failed(app_mod, code="session_expired")

        public = app_mod.dashboard_user_public(row)
        company = public["company_code"]
        requested = str(x_company_code or "").strip().upper()
        if requested and requested != company:
            raise _auth_failed(app_mod, code="action_forbidden", status=403, message="Access needs to be verified.")

        lifecycle = app_mod.company_lifecycle_status(company)
        if lifecycle != "active":
            raise _auth_failed(
                app_mod,
                code=f"company_{lifecycle}",
                status=403,
                message="This company workspace is not active.",
            )
        if public.get("status") != "active":
            raise _auth_failed(app_mod, code="operator_disabled", status=403, message="Your account is not active.")

        return build_operator_mobile_context(app_mod, row, session_id=str(row.get("session_id") or ""))

    @app_mod.app.post("/dashboard/mobile/auth/login")
    def mobile_auth_login(request: MobileLoginRequest):  # type: ignore[valid-type]
        app_mod.ensure_schema()
        ensure_operator_mobile_schema(app_mod)
        company = str(request.company_code or "").strip().upper()
        email = app_mod.normalize_email(request.email)
        password = str(request.password or "")
        if not company or not email or not password:
            raise _generic_login_failure()

        _login_rate_guard(app_mod, company, email)

        try:
            app_mod.require_active_company(company)
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            detail = detail if isinstance(detail, dict) else {}
            code = str(detail.get("error") or "")
            if code.startswith("company_"):
                status = app_mod.company_lifecycle_status(company)
                if status in {"disabled", "archived"}:
                    _record_login_failure(app_mod, company, email)
                    raise _auth_failed(app_mod, code=f"company_{status}", status=403, message="This company workspace is not active.")
            _record_login_failure(app_mod, company, email)
            raise _generic_login_failure()

        user = app_mod.dashboard_user_by_email(company, email)
        if not user:
            _record_login_failure(app_mod, company, email)
            raise _generic_login_failure()
        if app_mod.normalize_dashboard_user_status(user.get("status")) != "active":
            _record_login_failure(app_mod, company, email)
            raise _auth_failed(app_mod, code="operator_disabled", status=403, message="Your account is not active.")
        if not app_mod.dashboard_password_ok(password, user.get("password_hash")):
            _record_login_failure(app_mod, company, email)
            raise _generic_login_failure()

        _clear_login_failures(app_mod, company, email)
        tokens = create_operator_mobile_session(app_mod, user)
        return _auth_tokens_response(app_mod, user, tokens)

    @app_mod.app.post("/dashboard/mobile/auth/refresh")
    def mobile_auth_refresh(request: MobileRefreshRequest):  # type: ignore[valid-type]
        app_mod.ensure_schema()
        ensure_operator_mobile_schema(app_mod)
        rotated = rotate_operator_mobile_session(app_mod, request.refresh_token)
        return _auth_tokens_response(app_mod, rotated["user"], rotated["tokens"])

    @app_mod.app.post("/dashboard/mobile/auth/logout")
    def mobile_auth_logout(
        request: MobileLogoutRequest | None = None,  # type: ignore[valid-type]
        authorization: str | None = Header(default=None),
        x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
    ):
        app_mod.ensure_schema()
        ensure_operator_mobile_schema(app_mod)
        access = app_mod.bearer_token(authorization) or str(x_dashboard_token or "").strip()
        refresh = str((request.refresh_token if request else None) or "").strip() or None
        revoke_operator_mobile_access_token(app_mod, access, reason="logout")
        revoke_operator_mobile_refresh_token(app_mod, refresh, reason="logout")
        return {"ok": True}

    @app_mod.app.post("/dashboard/mobile/auth/logout-all")
    def mobile_auth_logout_all(context: dict[str, Any] = Depends(operator_mobile_context)):
        count = revoke_all_operator_mobile_sessions_for_user(
            app_mod,
            str(context.get("actor_user_id") or ""),
            reason="logout_all",
        )
        return {"ok": True, "revoked_sessions": count}

    @app_mod.app.get("/dashboard/mobile/me")
    def mobile_me(context: dict[str, Any] = Depends(operator_mobile_context)):
        # Recompute authority every request (already done in dependency).
        if context.get("permission_authority") != "backend_current":
            raise _auth_failed(app_mod, code="permission_authority_unavailable", status=403)
        return build_mobile_me_payload(app_mod, context)

    from operator_mobile_assistant import register_mobile_assistant_routes

    register_mobile_assistant_routes(app_mod, operator_mobile_context=operator_mobile_context)

    # Expose dependency for tests.
    register_operator_mobile_routes.operator_mobile_context = operator_mobile_context  # type: ignore[attr-defined]
