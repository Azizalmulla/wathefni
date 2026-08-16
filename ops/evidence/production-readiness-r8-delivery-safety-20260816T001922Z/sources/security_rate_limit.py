"""R2 — shared server-side abuse control primitive.

One durable rate-limit authority so public and authentication endpoints stop
inventing their own throttling. Backed by Postgres (not a per-process dict) so
every uvicorn worker shares the same counters.

Design rules:

* Route-specific policies. There is no single global number applied to every
  endpoint; application APIs are never throttled by this module unless a policy
  is explicitly registered and called.
* Two dimensions per call site where useful (network source and normalized
  account/tenant identity). Either dimension can trip independently.
* Denials are auditable without leaking secrets: identities are stored as
  salted-free SHA-256 digests, never raw passwords/tokens/emails.
* Fail closed. If the rate-limit store is unavailable the call is denied, since
  every protected endpoint already requires the same database to do its work.
  `WATHEFNI_RATE_LIMIT_FAIL_OPEN=1` inverts this for emergency operations.

Usage (failure-counting, e.g. login):

    security_rate_limit.guard(app_mod, "dashboard_login", route="/dashboard/auth/login",
                              dimensions={"source": ip, "identity": f"{company}|{email}"})
    ... attempt ...
    on failure: security_rate_limit.record_failure(app_mod, "dashboard_login", ...)
    on success: security_rate_limit.reset(app_mod, "dashboard_login", ...)

Usage (request-counting, e.g. public token endpoint):

    security_rate_limit.consume(app_mod, "calendar_guest_token", route=..., dimensions={...})
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable

logger = logging.getLogger("wathefni.security.rate_limit")

_ON = {"1", "true", "yes", "on", "enabled"}

CONTRACT_VERSION = "r2-security-rate-limit-v1"

# Mode semantics.
MODE_FAILURE = "failure"  # only failed attempts increment the counter
MODE_REQUEST = "request"  # every call increments the counter


@dataclass(frozen=True)
class RateLimitPolicy:
    key: str
    limit: int
    window_seconds: int
    lock_seconds: int
    mode: str
    dimensions: tuple[str, ...]
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.key,
            "limit": self.limit,
            "window_seconds": self.window_seconds,
            "lock_seconds": self.lock_seconds,
            "mode": self.mode,
            "dimensions": list(self.dimensions),
            "description": self.description,
        }


_BASE_POLICIES: dict[str, RateLimitPolicy] = {
    "dashboard_login": RateLimitPolicy(
        key="dashboard_login",
        limit=8,
        window_seconds=15 * 60,
        lock_seconds=15 * 60,
        mode=MODE_FAILURE,
        dimensions=("source", "identity"),
        description="HR web dashboard password login (brute force / spray / enumeration).",
    ),
    "setup_operator_login": RateLimitPolicy(
        key="setup_operator_login",
        limit=5,
        window_seconds=15 * 60,
        lock_seconds=30 * 60,
        mode=MODE_FAILURE,
        dimensions=("source", "identity"),
        description="Setup Console platform operator login.",
    ),
    "calendar_guest_token": RateLimitPolicy(
        key="calendar_guest_token",
        limit=40,
        window_seconds=5 * 60,
        lock_seconds=10 * 60,
        mode=MODE_REQUEST,
        dimensions=("source", "identity"),
        description="Public calendar guest bearer-token endpoints.",
    ),
    "internal_break_glass": RateLimitPolicy(
        key="internal_break_glass",
        limit=10,
        window_seconds=10 * 60,
        lock_seconds=10 * 60,
        mode=MODE_REQUEST,
        dimensions=("source", "identity"),
        description="Platform break-glass administration calls.",
    ),
    "client_error_report": RateLimitPolicy(
        key="client_error_report",
        limit=30,
        window_seconds=60,
        lock_seconds=60,
        mode=MODE_REQUEST,
        dimensions=("source",),
        description="First-party client crash ingest (R8).",
    ),
}

# Per-dimension limit multipliers: a shared office NAT should not lock out on the
# same count as a single account. Network sources get a wider allowance.
_SOURCE_MULTIPLIER = 4


def _overrides() -> dict[str, dict[str, Any]]:
    raw = (os.environ.get("WATHEFNI_RATE_LIMIT_OVERRIDES") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("rate limit overrides ignored: invalid json")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def policy(policy_key: str) -> RateLimitPolicy:
    base = _BASE_POLICIES.get(policy_key)
    if base is None:
        raise KeyError(f"unknown_rate_limit_policy:{policy_key}")
    override = _overrides().get(policy_key)
    if not isinstance(override, dict):
        return base
    fields: dict[str, Any] = {}
    for name in ("limit", "window_seconds", "lock_seconds"):
        if name in override:
            try:
                fields[name] = max(1, int(override[name]))
            except Exception:
                continue
    return replace(base, **fields) if fields else base


def policy_matrix() -> list[dict[str, Any]]:
    return [policy(key).as_dict() for key in sorted(_BASE_POLICIES)]


def disabled() -> bool:
    """Emergency kill switch. Off by default; documented as an incident control."""
    return (os.environ.get("WATHEFNI_RATE_LIMIT_DISABLED") or "").strip().lower() in _ON


def _fail_open() -> bool:
    return (os.environ.get("WATHEFNI_RATE_LIMIT_FAIL_OPEN") or "").strip().lower() in _ON


def principal_digest(value: str | None) -> str:
    """Stable, non-reversible identifier for logs and buckets."""
    raw = str(value or "").strip().lower()
    if not raw:
        return "anonymous"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _bucket_key(policy_key: str, dimension: str, value: str | None) -> str:
    raw = f"{policy_key}|{dimension}|{str(value or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _limit_for(pol: RateLimitPolicy, dimension: str) -> int:
    if dimension == "source":
        return max(pol.limit, pol.limit * _SOURCE_MULTIPLIER)
    return pol.limit


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def ensure_security_rate_limit_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS security_rate_limit_buckets (
          bucket_key text PRIMARY KEY,
          policy_key text NOT NULL,
          dimension text NOT NULL,
          hit_count int NOT NULL DEFAULT 0,
          window_started_at timestamptz NOT NULL DEFAULT now(),
          locked_until timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_security_rate_limit_policy
          ON security_rate_limit_buckets(policy_key, updated_at DESC);

        CREATE TABLE IF NOT EXISTS security_denial_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          policy_key text,
          route text NOT NULL,
          denial_class text NOT NULL,
          dimension text,
          principal_digest text,
          company_code text,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_security_denial_events_recent
          ON security_denial_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_security_denial_events_route
          ON security_denial_events(route, created_at DESC);
        """
    )


# --------------------------------------------------------------------------
# Telemetry hooks
# --------------------------------------------------------------------------

_TELEMETRY_HOOKS: list[Callable[[dict[str, Any]], None]] = []


def register_telemetry_hook(hook: Callable[[dict[str, Any]], None]) -> None:
    """Attach an observer for denial events (R8 will wire real error reporting)."""
    if hook not in _TELEMETRY_HOOKS:
        _TELEMETRY_HOOKS.append(hook)


def _emit(event: dict[str, Any]) -> None:
    for hook in list(_TELEMETRY_HOOKS):
        try:
            hook(dict(event))
        except Exception:
            logger.warning("rate limit telemetry hook failed", exc_info=False)


# --------------------------------------------------------------------------
# Denial audit
# --------------------------------------------------------------------------

_SENSITIVE_DETAIL_KEYS = {
    "password",
    "token",
    "secret",
    "authorization",
    "operator_token",
    "signature",
    "raw_text",
    "content_base64",
}


def _safe_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Strip anything that could carry a credential or candidate/employee content."""
    if not isinstance(detail, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in detail.items():
        name = str(key).lower()
        if any(marker in name for marker in _SENSITIVE_DETAIL_KEYS):
            clean[key] = "[redacted]"
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        elif isinstance(value, (list, tuple)):
            clean[key] = [v for v in value if isinstance(v, (str, int, float, bool))][:20]
        elif isinstance(value, dict):
            clean[key] = _safe_detail(value)
    return clean


def safe_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Public alias: redact credential-shaped keys before anything is persisted."""
    return _safe_detail(detail)


def record_denial(
    app_mod: Any,
    *,
    route: str,
    denial_class: str,
    policy_key: str | None = None,
    dimension: str | None = None,
    principal: str | None = None,
    company_code: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Persist a denied attempt. Never records credentials or message content."""
    digest = principal if (principal or "") in {None, "", "anonymous"} else principal_digest(principal)
    safe = _safe_detail(detail)
    event = {
        "route": route,
        "denial_class": denial_class,
        "policy": policy_key,
        "dimension": dimension,
        "principal_digest": digest,
        "company_code": (str(company_code).upper() if company_code else None),
        "detail": safe,
    }
    logger.warning(
        "security denial route=%s class=%s policy=%s dimension=%s principal=%s company=%s",
        route,
        denial_class,
        policy_key or "-",
        dimension or "-",
        digest or "-",
        event["company_code"] or "-",
    )
    _emit(event)
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_security_rate_limit_schema(cur)
                cur.execute(
                    """
                    INSERT INTO security_denial_events
                      (policy_key, route, denial_class, dimension, principal_digest, company_code, detail)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        policy_key,
                        route,
                        denial_class,
                        dimension,
                        digest,
                        event["company_code"],
                        app_mod.Json(safe),
                    ),
                )
            conn.commit()
    except Exception:
        # Audit must never break the denial itself.
        logger.warning("security denial not persisted route=%s class=%s", route, denial_class)


# --------------------------------------------------------------------------
# Core limiter
# --------------------------------------------------------------------------

def _too_many(app_mod: Any, pol: RateLimitPolicy, dimension: str, retry_after: int) -> Exception:
    return app_mod.HTTPException(
        status_code=429,
        detail={
            "error": "rate_limited",
            "message": "Too many attempts. Try again later.",
            "policy": pol.key,
            "retry_after_seconds": int(retry_after),
        },
        headers={"Retry-After": str(int(max(1, retry_after)))},
    )


def _unavailable(app_mod: Any, pol: RateLimitPolicy) -> Exception:
    return app_mod.HTTPException(
        status_code=503,
        detail={
            "error": "rate_limit_unavailable",
            "message": "Service temporarily unavailable. Try again later.",
            "policy": pol.key,
        },
        headers={"Retry-After": "30"},
    )


def _dimension_values(pol: RateLimitPolicy, dimensions: dict[str, str | None]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name in pol.dimensions:
        value = dimensions.get(name)
        text = str(value or "").strip()
        if not text:
            continue
        out.append((name, text))
    return out


def _evaluate(
    app_mod: Any,
    pol: RateLimitPolicy,
    pairs: Iterable[tuple[str, str]],
    *,
    increment: bool,
) -> tuple[bool, str | None, int]:
    """Returns (allowed, tripped_dimension, retry_after_seconds)."""
    now = app_mod.now_utc()
    tripped: str | None = None
    retry_after = 0
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_security_rate_limit_schema(cur)
            for dimension, value in pairs:
                key = _bucket_key(pol.key, dimension, value)
                cur.execute(
                    "SELECT * FROM security_rate_limit_buckets WHERE bucket_key=%s LIMIT 1 FOR UPDATE",
                    (key,),
                )
                row = cur.fetchone()
                limit = _limit_for(pol, dimension)
                if row is None:
                    cur.execute(
                        """
                        INSERT INTO security_rate_limit_buckets
                          (bucket_key, policy_key, dimension, hit_count, window_started_at)
                        VALUES (%s,%s,%s,%s, now())
                        ON CONFLICT (bucket_key) DO NOTHING
                        """,
                        (key, pol.key, dimension, 1 if increment else 0),
                    )
                    continue

                locked_until = row.get("locked_until")
                if locked_until and locked_until > now:
                    tripped = tripped or dimension
                    retry_after = max(retry_after, int((locked_until - now).total_seconds()) + 1)
                    continue

                window_started = row.get("window_started_at") or now
                hit_count = int(row.get("hit_count") or 0)
                expired = (window_started + app_mod.timedelta(seconds=pol.window_seconds)) < now
                if expired:
                    hit_count = 0
                    window_started = now
                if increment:
                    hit_count += 1
                new_lock = None
                if hit_count >= limit:
                    new_lock = now + app_mod.timedelta(seconds=pol.lock_seconds)
                    tripped = tripped or dimension
                    retry_after = max(retry_after, pol.lock_seconds)
                cur.execute(
                    """
                    UPDATE security_rate_limit_buckets
                    SET hit_count=%s, window_started_at=%s, locked_until=%s, updated_at=now()
                    WHERE bucket_key=%s
                    """,
                    (hit_count, window_started, new_lock, key),
                )
        conn.commit()
    return (tripped is None), tripped, retry_after


def guard(
    app_mod: Any,
    policy_key: str,
    *,
    route: str,
    dimensions: dict[str, str | None],
    company_code: str | None = None,
) -> None:
    """Deny if this caller is currently locked out. Does not increment counters."""
    if disabled():
        return
    pol = policy(policy_key)
    pairs = _dimension_values(pol, dimensions)
    if not pairs:
        return
    try:
        allowed, tripped, retry_after = _evaluate(app_mod, pol, pairs, increment=False)
    except Exception as exc:
        logger.error("rate limit store unavailable policy=%s: %s", pol.key, type(exc).__name__)
        if _fail_open():
            return
        raise _unavailable(app_mod, pol) from exc
    if allowed:
        return
    record_denial(
        app_mod,
        route=route,
        denial_class="rate_limited",
        policy_key=pol.key,
        dimension=tripped,
        principal=dimensions.get("identity") or dimensions.get("source"),
        company_code=company_code,
        detail={"retry_after_seconds": retry_after},
    )
    raise _too_many(app_mod, pol, tripped or "identity", retry_after)


def consume(
    app_mod: Any,
    policy_key: str,
    *,
    route: str,
    dimensions: dict[str, str | None],
    company_code: str | None = None,
) -> None:
    """Count this request and deny once the policy limit is exceeded."""
    if disabled():
        return
    pol = policy(policy_key)
    pairs = _dimension_values(pol, dimensions)
    if not pairs:
        return
    try:
        allowed, tripped, retry_after = _evaluate(app_mod, pol, pairs, increment=True)
    except Exception as exc:
        logger.error("rate limit store unavailable policy=%s: %s", pol.key, type(exc).__name__)
        if _fail_open():
            return
        raise _unavailable(app_mod, pol) from exc
    if allowed:
        return
    record_denial(
        app_mod,
        route=route,
        denial_class="rate_limited",
        policy_key=pol.key,
        dimension=tripped,
        principal=dimensions.get("identity") or dimensions.get("source"),
        company_code=company_code,
        detail={"retry_after_seconds": retry_after},
    )
    raise _too_many(app_mod, pol, tripped or "identity", retry_after)


def record_failure(
    app_mod: Any,
    policy_key: str,
    *,
    route: str,
    dimensions: dict[str, str | None],
    company_code: str | None = None,
    denial_class: str = "auth_failed",
) -> None:
    """Count a failed attempt. Never raises; the caller returns its own error."""
    if disabled():
        return
    pol = policy(policy_key)
    pairs = _dimension_values(pol, dimensions)
    if not pairs:
        return
    try:
        _evaluate(app_mod, pol, pairs, increment=True)
    except Exception:
        logger.error("rate limit failure not recorded policy=%s", pol.key)
    record_denial(
        app_mod,
        route=route,
        denial_class=denial_class,
        policy_key=pol.key,
        principal=dimensions.get("identity") or dimensions.get("source"),
        company_code=company_code,
    )


def reset(
    app_mod: Any,
    policy_key: str,
    *,
    dimensions: dict[str, str | None],
) -> None:
    """Clear counters after a legitimate success so real users are not punished."""
    if disabled():
        return
    pol = policy(policy_key)
    pairs = _dimension_values(pol, dimensions)
    if not pairs:
        return
    keys = [_bucket_key(pol.key, dimension, value) for dimension, value in pairs]
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_security_rate_limit_schema(cur)
                cur.execute(
                    "DELETE FROM security_rate_limit_buckets WHERE bucket_key = ANY(%s)",
                    (keys,),
                )
            conn.commit()
    except Exception:
        logger.warning("rate limit reset failed policy=%s", pol.key)


_LOOPBACK_PROXIES = ("127.0.0.1", "::1", "localhost")


def trusted_proxy_hosts() -> frozenset[str]:
    """Peers whose X-Forwarded-For may be believed.

    Defaults to loopback because the edge proxy runs on the same host as the
    application. Anything else reaches us directly and cannot be trusted to
    describe its own address.
    """
    raw = (os.environ.get("WATHEFNI_TRUSTED_PROXY_HOSTS") or "").strip()
    if not raw:
        return frozenset(_LOOPBACK_PROXIES)
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def client_source(request: Any) -> str:
    """Network source for rate-limit dimensions.

    The edge proxy *appends* the real peer to any X-Forwarded-For the caller
    sent, so the trustworthy hop is the last one, not the first. Reading the
    first element let a caller spoof its own source and spray passwords past
    the per-source budget, so we only consult the header when the direct peer
    is a trusted proxy, and then only its final entry.
    """
    try:
        client = getattr(request, "client", None)
        peer = str(getattr(client, "host", "") or "").strip()
        if peer and peer in trusted_proxy_hosts():
            headers = getattr(request, "headers", None)
            forwarded = str(headers.get("x-forwarded-for") or "") if headers is not None else ""
            hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
            if hops:
                return hops[-1]
        return peer or "unknown"
    except Exception:
        return "unknown"
