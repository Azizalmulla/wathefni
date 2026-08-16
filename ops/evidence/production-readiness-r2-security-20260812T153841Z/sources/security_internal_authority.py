"""R2 — internal endpoint classification, principals, tenant scope, break-glass.

Before R2 every `/orchestrator/audit/*` and `/orchestrator/debug/*` route shared a
single platform token, and several of them took `company_code` from a query string
or request body. One stolen internal token therefore reached every tenant, and
three audit reads returned conversation content across all tenants at once.

R2 replaces that with an explicit two-class model. Every internal endpoint is
declared here; there is no ambiguous middle ground.

Class A — tenant-scoped routine operation
    Runs against exactly one company. The tenant comes from the authenticated
    principal, not from caller-supplied input. A tenant principal cannot widen its
    scope; a platform principal must name the target company explicitly and the
    call is audited.

Class B — platform / break-glass administration
    Genuinely global or destructive. Disabled by default, requires a dedicated
    break-glass secret in addition to the internal token, requires operator
    attribution, is rate limited, and writes an audit row before it runs.

Principals:

    tenant   — `WATHEFNI_INTERNAL_TENANT_TOKENS` = {"COMPANYCODE": "<token>"}
               Scope is fixed to that company and cannot be overridden.
    platform — `WATHEFNI_INTERNAL_TOKEN` (the existing shared internal secret).
               Still required for every internal route, but no longer sufficient
               for global reads or destructive operations.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import security_rate_limit as _rl

logger = logging.getLogger("wathefni.security.internal_authority")

CONTRACT_VERSION = "r2-internal-authority-v1"

_ON = {"1", "true", "yes", "on", "enabled"}

CLASS_TENANT = "A_tenant_scoped"
CLASS_BREAK_GLASS = "B_platform_break_glass"

MIN_TOKEN_LENGTH = 24
MIN_BREAK_GLASS_LENGTH = 32

PRINCIPAL_TENANT = "tenant"
PRINCIPAL_PLATFORM = "platform"


@dataclass(frozen=True)
class EndpointClass:
    route: str
    classification: str
    company_scope: str  # "required" | "principal" | "global"
    destructive: bool
    rationale: str


# Every internal route identified by the R1 P0-5 finding, plus the neighbouring
# internal routes that share the same token, classified explicitly.
ENDPOINT_CLASSIFICATION: dict[str, EndpointClass] = {
    "/orchestrator/audit/turns": EndpointClass(
        route="/orchestrator/audit/turns",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Reads hr_turns.raw_text (conversation content). Must never span tenants.",
    ),
    "/orchestrator/audit/pending-actions": EndpointClass(
        route="/orchestrator/audit/pending-actions",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Reads pending actions for one company's operators.",
    ),
    "/orchestrator/audit/action-results": EndpointClass(
        route="/orchestrator/audit/action-results",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Reads executed action results for one company.",
    ),
    "/orchestrator/debug/intake-jobs/{job_id}/replay": EndpointClass(
        route="/orchestrator/debug/intake-jobs/{job_id}/replay",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Replays one dead-letter job belonging to one company.",
    ),
    "/orchestrator/debug/intake-operations": EndpointClass(
        route="/orchestrator/debug/intake-operations",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Intake operations summary; per-company view is the routine use.",
    ),
    "/orchestrator/debug/intake-documents/{document_id}/download": EndpointClass(
        route="/orchestrator/debug/intake-documents/{document_id}/download",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Returns quarantined document bytes (candidate PII) for one company.",
    ),
    "/orchestrator/debug/intake-documents/{document_id}/signed-download": EndpointClass(
        route="/orchestrator/debug/intake-documents/{document_id}/signed-download",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Mints a short-lived download capability for one company's document.",
    ),
    "/orchestrator/posthire/documents/email-intake": EndpointClass(
        route="/orchestrator/posthire/documents/email-intake",
        classification=CLASS_TENANT,
        company_scope="required",
        destructive=False,
        rationale="Writes employee documents. Tenant is derived from the destination mailbox.",
    ),
    "/orchestrator/debug/intake-outage-replay": EndpointClass(
        route="/orchestrator/debug/intake-outage-replay",
        classification=CLASS_BREAK_GLASS,
        company_scope="global",
        destructive=False,
        rationale="Platform-wide requeue across every tenant during an outage.",
    ),
    "/orchestrator/debug/intake-quarantine/sweep": EndpointClass(
        route="/orchestrator/debug/intake-quarantine/sweep",
        classification=CLASS_BREAK_GLASS,
        company_scope="global",
        destructive=True,
        rationale="apply=true deletes orphaned quarantine storage across tenants.",
    ),
    "/orchestrator/debug/intake-worker/run": EndpointClass(
        route="/orchestrator/debug/intake-worker/run",
        classification=CLASS_BREAK_GLASS,
        company_scope="global",
        destructive=False,
        rationale="Runs the shared ingress worker for all tenants.",
    ),
}


def classification_matrix() -> list[dict[str, Any]]:
    return [
        {
            "route": spec.route,
            "class": spec.classification,
            "company_scope": spec.company_scope,
            "destructive": spec.destructive,
            "rationale": spec.rationale,
        }
        for spec in sorted(ENDPOINT_CLASSIFICATION.values(), key=lambda s: (s.classification, s.route))
    ]


def classify(route: str) -> EndpointClass:
    spec = ENDPOINT_CLASSIFICATION.get(route)
    if spec is None:
        raise KeyError(f"unclassified_internal_route:{route}")
    return spec


# --------------------------------------------------------------------------
# Principals
# --------------------------------------------------------------------------

def tenant_tokens() -> dict[str, str]:
    """Company-scoped internal tokens: {"COMPANYCODE": "<token>"}."""
    raw = (os.environ.get("WATHEFNI_INTERNAL_TENANT_TOKENS") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.error("internal tenant tokens ignored: invalid json")
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, str] = {}
    for company, token in parsed.items():
        code = str(company or "").strip().upper()
        value = str(token or "").strip()
        if not code or len(value) < MIN_TOKEN_LENGTH:
            logger.error("internal tenant token rejected company=%s reason=weak_or_missing", code or "-")
            continue
        out[code] = value
    return out


def platform_token() -> str | None:
    value = str(os.environ.get("WATHEFNI_INTERNAL_TOKEN") or "").strip()
    return value or None


def resolve_principal(provided: str | None) -> dict[str, Any] | None:
    """Match a presented internal secret to a principal. Constant-time compares."""
    token = str(provided or "").strip()
    if not token:
        return None
    for company, secret in tenant_tokens().items():
        if hmac.compare_digest(token, secret):
            return {
                "kind": PRINCIPAL_TENANT,
                "company_code": company,
                "is_internal": True,
                "principal_digest": _rl.principal_digest(f"tenant:{company}"),
            }
    configured = platform_token()
    if configured and hmac.compare_digest(token, configured):
        return {
            "kind": PRINCIPAL_PLATFORM,
            "company_code": None,
            "is_internal": True,
            "principal_digest": _rl.principal_digest("platform"),
        }
    return None


def is_tenant_principal(principal: dict[str, Any] | None) -> bool:
    return bool(principal) and principal.get("kind") == PRINCIPAL_TENANT


# --------------------------------------------------------------------------
# Tenant scope enforcement
# --------------------------------------------------------------------------

def authorize_company(
    app_mod: Any,
    principal: dict[str, Any],
    requested: str | None,
    *,
    route: str,
    required: bool = True,
) -> str | None:
    """Resolve the authorized company for a Class A call.

    A tenant principal is pinned to its own company; asking for another one is a
    scope violation, not a filter. A platform principal must name the company.
    """
    asked = str(requested or "").strip().upper() or None
    if is_tenant_principal(principal):
        owned = str(principal.get("company_code") or "").upper()
        if asked and asked != owned:
            _rl.record_denial(
                app_mod,
                route=route,
                denial_class="tenant_scope_violation",
                principal=f"tenant:{owned}",
                company_code=owned,
                detail={"requested_company": asked},
            )
            raise app_mod.HTTPException(
                status_code=403,
                detail={
                    "error": "tenant_scope_violation",
                    "message": "This principal is not authorized for the requested company.",
                },
            )
        return owned
    if not asked:
        if not required:
            return None
        _rl.record_denial(
            app_mod,
            route=route,
            denial_class="company_scope_required",
            principal="platform",
        )
        raise app_mod.HTTPException(
            status_code=400,
            detail={
                "error": "company_scope_required",
                "message": "An explicit company_code is required for this operation.",
            },
        )
    return asked


# --------------------------------------------------------------------------
# Break-glass
# --------------------------------------------------------------------------

def break_glass_enabled() -> bool:
    return (os.environ.get("WATHEFNI_BREAK_GLASS_ENABLED") or "").strip().lower() in _ON


def break_glass_secret() -> str | None:
    value = str(os.environ.get("WATHEFNI_BREAK_GLASS_TOKEN") or "").strip()
    if not value:
        return None
    if len(value) < MIN_BREAK_GLASS_LENGTH:
        logger.error("break-glass token rejected reason=too_short")
        return None
    if platform_token() and hmac.compare_digest(value, str(platform_token())):
        logger.error("break-glass token rejected reason=same_as_internal_token")
        return None
    return value


def ensure_break_glass_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS security_break_glass_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          route text NOT NULL,
          operation text NOT NULL,
          operator_id text NOT NULL,
          target_company text,
          destructive boolean NOT NULL DEFAULT false,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_security_break_glass_recent
          ON security_break_glass_events(created_at DESC);
        """
    )


def _deny(app_mod: Any, route: str, code: str, message: str, *, status: int = 403, detail: dict | None = None):
    _rl.record_denial(
        app_mod,
        route=route,
        denial_class=code,
        principal="platform",
        detail=detail,
    )
    return app_mod.HTTPException(status_code=status, detail={"error": code, "message": message})


def require_break_glass(
    app_mod: Any,
    principal: dict[str, Any],
    *,
    route: str,
    operation: str,
    operator_id: str | None,
    break_glass_token: str | None,
    source: str | None = None,
    target_company: str | None = None,
    destructive: bool = False,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate a Class B operation. Returns the attribution record it audited."""
    if is_tenant_principal(principal):
        raise _deny(
            app_mod,
            route,
            "break_glass_requires_platform_principal",
            "A tenant principal cannot perform platform administration.",
        )
    if not break_glass_enabled():
        raise _deny(
            app_mod,
            route,
            "break_glass_disabled",
            "Break-glass administration is disabled.",
            detail={"operation": operation},
        )
    configured = break_glass_secret()
    if not configured:
        raise _deny(
            app_mod,
            route,
            "break_glass_unconfigured",
            "Break-glass administration is not configured.",
            detail={"operation": operation},
        )
    presented = str(break_glass_token or "").strip()
    if not presented or not hmac.compare_digest(presented, configured):
        raise _deny(
            app_mod,
            route,
            "break_glass_forbidden",
            "Break-glass authority was rejected.",
            status=401,
            detail={"operation": operation},
        )
    actor = str(operator_id or "").strip()
    if not actor:
        raise _deny(
            app_mod,
            route,
            "break_glass_operator_required",
            "Break-glass operations require operator attribution.",
            status=400,
            detail={"operation": operation},
        )

    _rl.consume(
        app_mod,
        "internal_break_glass",
        route=route,
        dimensions={"source": source, "identity": f"operator:{actor}"},
        company_code=target_company,
    )

    attribution = {
        "route": route,
        "operation": operation,
        "operator_id": actor,
        "target_company": (str(target_company).upper() if target_company else None),
        "destructive": bool(destructive),
        "detail": _rl.safe_detail(detail),
    }
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_break_glass_schema(cur)
                cur.execute(
                    """
                    INSERT INTO security_break_glass_events
                      (route, operation, operator_id, target_company, destructive, detail)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        route,
                        operation,
                        actor,
                        attribution["target_company"],
                        bool(destructive),
                        app_mod.Json(attribution["detail"]),
                    ),
                )
            conn.commit()
    except Exception:
        # An unauditable break-glass action must not proceed.
        logger.error("break-glass audit write failed route=%s operation=%s", route, operation)
        raise _deny(
            app_mod,
            route,
            "break_glass_audit_unavailable",
            "Break-glass administration is unavailable.",
            status=503,
            detail={"operation": operation},
        )
    logger.warning(
        "break-glass executed route=%s operation=%s operator=%s company=%s destructive=%s",
        route,
        operation,
        actor,
        attribution["target_company"] or "-",
        bool(destructive),
    )
    return attribution


# --------------------------------------------------------------------------
# Email intake routing authority
# --------------------------------------------------------------------------

def resolve_intake_company(
    app_mod: Any,
    cur: Any,
    principal: dict[str, Any],
    *,
    route: str,
    recipient: str | None,
    claimed: str | None,
) -> str:
    """Derive the tenant for an inbound email from an authenticated routing source.

    Order of authority:
      1. Tenant principal — pinned, cannot be widened.
      2. Destination mailbox identity — the address the mail was delivered to.
      3. Nothing. A request-body company alone is never sufficient.
    """
    if is_tenant_principal(principal):
        owned = str(principal.get("company_code") or "").upper()
        asked = str(claimed or "").strip().upper()
        if asked and asked != owned:
            _rl.record_denial(
                app_mod,
                route=route,
                denial_class="tenant_scope_violation",
                principal=f"tenant:{owned}",
                company_code=owned,
                detail={"requested_company": asked},
            )
            raise app_mod.HTTPException(
                status_code=403,
                detail={"error": "tenant_scope_violation", "message": "Not authorized for that company."},
            )
        return owned

    derived = company_for_mailbox(cur, recipient)
    if derived:
        asked = str(claimed or "").strip().upper()
        if asked and asked != derived:
            _rl.record_denial(
                app_mod,
                route=route,
                denial_class="intake_routing_conflict",
                principal="platform",
                company_code=derived,
                detail={"requested_company": asked},
            )
            raise app_mod.HTTPException(
                status_code=403,
                detail={
                    "error": "intake_routing_conflict",
                    "message": "Declared company does not match the destination mailbox.",
                },
            )
        return derived

    _rl.record_denial(
        app_mod,
        route=route,
        denial_class="intake_routing_unresolved",
        principal="platform",
        detail={"has_recipient": bool(str(recipient or "").strip())},
    )
    raise app_mod.HTTPException(
        status_code=403,
        detail={
            "error": "intake_routing_unresolved",
            "message": "Tenant could not be derived from the destination mailbox.",
        },
    )


def company_for_mailbox(cur: Any, address: str | None) -> str | None:
    """Map a destination address to its owning company via mailbox authority."""
    email = str(address or "").strip().lower()
    if not email or "@" not in email:
        return None
    try:
        cur.execute(
            """
            SELECT company_code
            FROM company_operational_mailboxes
            WHERE lower(address)=%s AND status <> 'disabled'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (email,),
        )
        row = cur.fetchone()
        if row and row.get("company_code"):
            return str(row["company_code"]).upper()
    except Exception:
        logger.warning("operational mailbox lookup failed")
    try:
        cur.execute(
            """
            SELECT company_code
            FROM mailbox_connections
            WHERE lower(email_address)=%s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (email,),
        )
        row = cur.fetchone()
        if row and row.get("company_code"):
            return str(row["company_code"]).upper()
    except Exception:
        logger.warning("mailbox connection lookup failed")
    return None
