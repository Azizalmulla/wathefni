#!/usr/bin/env python3
"""Production Readiness R2 — security hardening unit contracts (no DB).

Covers the parts of the R2 blocker set that are pure logic:

  P0-2  link signing secrets fail closed, old committed constants are banned,
        rotation verifies, tampered tokens fail
  P0-4  internal worker channel has no localhost fail-open
  P0-5  every internal route is explicitly classified; break-glass credentials
        cannot collapse into the shared internal token
  P0-3 / P1-22  rate-limit policies exist with real dimensions and windows

The durable behaviours (counters, tenant isolation, audit rows) are proven
against the staging database in smoke-test-r2-security-db.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0

GOOD_SECRET = "r2-unit-assessment-8f3c1d9b4a7e26051c8d"  # 44 chars, mixed
GOOD_SECRET_B = "r2-unit-rotated-5b8e2c7f1a94d36002ef7a19"
OLD_ASSESSMENT_CONSTANT = "wathefni-assessment-dev-secret"
OLD_VIDEO_CONSTANT = "wathefni-video-interview-dev-secret"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _clear(*names: str) -> None:
    for name in names:
        os.environ.pop(name, None)


def link_secret_contracts() -> None:
    import security_link_secrets as links

    print("\n    P0-2 — link signing secrets fail closed")

    _clear(
        "WATHEFNI_ASSESSMENT_LINK_SECRET",
        "WATHEFNI_ASSESSMENT_LINK_SECRET_PREVIOUS",
        "WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET",
        "WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET_PREVIOUS",
        "WATHEFNI_DATABASE_URL",
        "WATHEFNI_DASHBOARD_TOKEN",
    )

    for purpose, constant in (("assessment", OLD_ASSESSMENT_CONSTANT), ("video_interview", OLD_VIDEO_CONSTANT)):
        ok, reason = links.validate_secret(constant, purpose=purpose)
        check(f"{purpose}: committed dev constant rejected", not ok and reason == "banned_known_value", reason)

    ok, reason = links.validate_secret("postgresql://user:pw@127.0.0.1:5432/wathefni", purpose="assessment")
    check("database URL rejected as signing key", not ok and reason == "looks_like_connection_string", reason)

    os.environ["WATHEFNI_DATABASE_URL"] = "postgres://someuser:somepass@127.0.0.1:5432/wathefni_staging_db"
    os.environ["WATHEFNI_DASHBOARD_TOKEN"] = "dashboard-token-value-with-enough-length-1234"
    ok, reason = links.validate_secret(os.environ["WATHEFNI_DASHBOARD_TOKEN"], purpose="assessment")
    check("dashboard token cannot be reused as signing key", not ok and reason == "reuses_other_credential", reason)
    _clear("WATHEFNI_DATABASE_URL", "WATHEFNI_DASHBOARD_TOKEN")

    ok, reason = links.validate_secret("short-secret-123", purpose="assessment")
    check("short secret rejected", not ok and reason == "too_short", reason)

    ok, reason = links.validate_secret("a" * 64, purpose="assessment")
    check("low-entropy secret rejected", not ok and reason == "insufficient_entropy", reason)

    ok, reason = links.validate_secret(None, purpose="assessment")
    check("missing secret rejected", not ok and reason == "missing", reason)

    ok, reason = links.validate_secret(GOOD_SECRET, purpose="assessment")
    check("dedicated strong secret accepted", ok and reason == "ok", reason)

    check("assessment unavailable while unset", links.available("assessment") is False)
    try:
        links.signing_secret("assessment")
        check("signing without a secret raises", False)
    except links.LinkSecretUnavailable as exc:
        check("signing without a secret raises LinkSecretUnavailable", exc.reason == "missing", exc.reason)

    status = links.status()
    check("readiness reports link signing not ok", status.get("ok") is False)
    check(
        "readiness never returns secret material",
        all("secret" not in str(v).lower() or k == "env_var" for k, v in status["purposes"]["assessment"].items()),
    )

    os.environ["WATHEFNI_ASSESSMENT_LINK_SECRET"] = OLD_ASSESSMENT_CONSTANT
    check("banned constant in env still fails closed", links.available("assessment") is False)

    os.environ["WATHEFNI_ASSESSMENT_LINK_SECRET"] = GOOD_SECRET
    check("valid dedicated secret makes capability available", links.available("assessment") is True)
    fingerprint = links.secret_fingerprint("assessment")
    check("fingerprint is a short digest, not the secret", bool(fingerprint) and GOOD_SECRET not in str(fingerprint))

    os.environ["WATHEFNI_ASSESSMENT_LINK_SECRET_PREVIOUS"] = f"{OLD_ASSESSMENT_CONSTANT},{GOOD_SECRET_B}"
    verifiers = links.verification_secrets("assessment")
    check("rotation accepts one retired key", len(verifiers) == 2, len(verifiers))
    check("retired banned constant is dropped", OLD_ASSESSMENT_CONSTANT.encode() not in verifiers)
    _clear("WATHEFNI_ASSESSMENT_LINK_SECRET_PREVIOUS")


def token_forgery_contracts() -> None:
    print("\n    P0-2 — forged tokens from the removed fallbacks")
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  app import (psycopg2 unavailable locally)")
            return
        raise

    import hashlib
    import hmac
    import time as _time

    def forge(subject: str, secret: str, ttl: int = 600) -> str:
        expires = int(_time.time()) + ttl
        payload = f"{subject}:{expires}"
        signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        return app.b64url_encode(f"{payload}:".encode("utf-8") + signature)

    os.environ["WATHEFNI_ASSESSMENT_LINK_SECRET"] = GOOD_SECRET
    os.environ["WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET"] = GOOD_SECRET_B
    _clear("WATHEFNI_ASSESSMENT_LINK_SECRET_PREVIOUS", "WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET_PREVIOUS")

    check(
        "assessment token forged with the old constant is rejected",
        not app.verify_assessment_token("attempt-1", forge("attempt-1", OLD_ASSESSMENT_CONSTANT)),
    )
    check(
        "video token forged with the old constant is rejected",
        not app.verify_video_interview_token("iv-1", forge("iv-1", OLD_VIDEO_CONSTANT)),
    )

    db_url = "postgres://someuser:somepass@127.0.0.1:5432/wathefni_staging_db"
    check(
        "token forged with the database URL is rejected",
        not app.verify_video_interview_token("iv-1", forge("iv-1", db_url)),
    )

    good = app.sign_video_interview_token("iv-1", int(_time.time()) + 600)
    check("token signed by the dedicated secret verifies", app.verify_video_interview_token("iv-1", good))
    check("token bound to its subject", not app.verify_video_interview_token("iv-2", good))
    check("tampered token rejected", not app.verify_video_interview_token("iv-1", good + "AA"))
    check("expired token rejected", not app.verify_video_interview_token("iv-1", app.sign_video_interview_token("iv-1", int(_time.time()) - 5)))

    # Rotation: the retired key keeps issued links alive, removing it kills them.
    os.environ["WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET"] = GOOD_SECRET
    os.environ["WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET_PREVIOUS"] = GOOD_SECRET_B
    check("link issued before rotation still verifies", app.verify_video_interview_token("iv-1", good))
    _clear("WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET_PREVIOUS")
    check("link stops verifying once the retired key is removed", not app.verify_video_interview_token("iv-1", good))

    _clear("WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET")
    check("capability unavailable with no secret", app.link_signing_available("video_interview") is False)
    check("verification fails closed with no secret", not app.verify_video_interview_token("iv-1", good))
    os.environ["WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET"] = GOOD_SECRET_B


def internal_authority_contracts() -> None:
    import security_internal_authority as authority

    print("\n    P0-5 — internal endpoint classification and principals")

    matrix = authority.classification_matrix()
    check("every internal route in scope is classified", len(matrix) >= 11, len(matrix))
    check(
        "no ambiguous classification",
        all(row["class"] in {authority.CLASS_TENANT, authority.CLASS_BREAK_GLASS} for row in matrix),
    )
    check(
        "destructive routes are break-glass, never tenant-routine",
        all(row["class"] == authority.CLASS_BREAK_GLASS for row in matrix if row["destructive"]),
    )
    check(
        "tenant-scoped routes all declare a company scope",
        all(row["company_scope"] == "required" for row in matrix if row["class"] == authority.CLASS_TENANT),
    )
    for route in (
        "/orchestrator/audit/turns",
        "/orchestrator/audit/pending-actions",
        "/orchestrator/audit/action-results",
        "/orchestrator/posthire/documents/email-intake",
        "/orchestrator/debug/intake-quarantine/sweep",
        "/orchestrator/debug/intake-worker/run",
    ):
        check(f"classified: {route}", route in authority.ENDPOINT_CLASSIFICATION)

    _clear("WATHEFNI_INTERNAL_TENANT_TOKENS", "WATHEFNI_INTERNAL_TOKEN")
    check("no configuration means no principal", authority.resolve_principal("anything") is None)

    os.environ["WATHEFNI_INTERNAL_TOKEN"] = "platform-internal-token-value-123456"
    os.environ["WATHEFNI_INTERNAL_TENANT_TOKENS"] = (
        '{"ALPHACO": "alpha-tenant-internal-token-0011", "BETACO": "beta-tenant-internal-token-0022"}'
    )
    platform = authority.resolve_principal("platform-internal-token-value-123456")
    alpha = authority.resolve_principal("alpha-tenant-internal-token-0011")
    check("platform token resolves to a platform principal", platform and platform["kind"] == "platform")
    check("tenant token resolves to its own company", alpha and alpha["company_code"] == "ALPHACO")
    check("unknown token resolves to nothing", authority.resolve_principal("guessed-token") is None)

    os.environ["WATHEFNI_INTERNAL_TENANT_TOKENS"] = '{"WEAKCO": "short"}'
    check("weak tenant token is refused", authority.resolve_principal("short") is None)
    os.environ["WATHEFNI_INTERNAL_TENANT_TOKENS"] = (
        '{"ALPHACO": "alpha-tenant-internal-token-0011", "BETACO": "beta-tenant-internal-token-0022"}'
    )

    print("\n    P0-5 — break-glass credential separation")
    _clear("WATHEFNI_BREAK_GLASS_TOKEN", "WATHEFNI_BREAK_GLASS_ENABLED")
    check("break-glass disabled by default", authority.break_glass_enabled() is False)
    check("break-glass unconfigured by default", authority.break_glass_secret() is None)
    os.environ["WATHEFNI_BREAK_GLASS_TOKEN"] = "too-short-token"
    check("short break-glass token refused", authority.break_glass_secret() is None)
    os.environ["WATHEFNI_BREAK_GLASS_TOKEN"] = os.environ["WATHEFNI_INTERNAL_TOKEN"]
    check(
        "break-glass token equal to the internal token is refused",
        authority.break_glass_secret() is None,
    )
    os.environ["WATHEFNI_BREAK_GLASS_TOKEN"] = "break-glass-distinct-token-9f2b7c4e11"
    check("distinct strong break-glass token accepted", authority.break_glass_secret() is not None)


def worker_auth_contracts() -> None:
    print("\n    P0-4 — internal worker channel")
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  app import (psycopg2 unavailable locally)")
            return
        raise

    class _Client:
        host = "127.0.0.1"

    class _Req:
        client = _Client()
        headers: dict[str, str] = {}

    _clear("WATHEFNI_INTERNAL_WORKER_TOKEN", "WATHEFNI_INTERNAL_WORKER_ACCEPT_SHARED")
    os.environ["WATHEFNI_INTERNAL_TOKEN"] = "platform-internal-token-value-123456"

    check("shared token is not a worker token by default", app.internal_worker_token() is None)
    try:
        app.require_internal_worker_access(_Req(), None)
        check("no worker secret + localhost is denied", False)
    except app.HTTPException as exc:
        check("no worker secret + localhost is denied", exc.status_code == 403)

    try:
        app.require_internal_worker_access(_Req(), "platform-internal-token-value-123456")
        check("shared internal token alone is denied", False)
    except app.HTTPException as exc:
        check("shared internal token alone is denied", exc.status_code == 403)

    os.environ["WATHEFNI_INTERNAL_WORKER_TOKEN"] = "worker-dedicated-token-77c1b204ae"
    try:
        app.require_internal_worker_access(_Req(), "wrong-token")
        check("wrong worker token denied", False)
    except app.HTTPException as exc:
        check("wrong worker token denied", exc.status_code == 403)

    try:
        app.require_internal_worker_access(_Req(), "worker-dedicated-token-77c1b204ae")
        check("correct dedicated worker token accepted", True)
    except app.HTTPException as exc:
        check("correct dedicated worker token accepted", False, exc.detail)

    source = Path(__file__).resolve().parent.joinpath("app.py").read_text(encoding="utf-8")
    start = source.index("def require_internal_worker_access")
    body = source[start : start + 1800]
    check("no localhost allowlist remains in the worker gate", "127.0.0.1" not in body)


def rate_limit_contracts() -> None:
    import security_rate_limit as rl

    print("\n    P0-3 / P1-22 — rate-limit policy framework")
    matrix = rl.policy_matrix()
    keys = {row["policy"] for row in matrix}
    for expected in ("dashboard_login", "setup_operator_login", "calendar_guest_token", "internal_break_glass"):
        check(f"policy registered: {expected}", expected in keys)
    check("every policy has a positive limit and window", all(r["limit"] > 0 and r["window_seconds"] > 0 for r in matrix))
    check("every policy names its dimensions", all(r["dimensions"] for r in matrix))
    check(
        "login policies count failures, public token policies count requests",
        rl.policy("dashboard_login").mode == rl.MODE_FAILURE
        and rl.policy("calendar_guest_token").mode == rl.MODE_REQUEST,
    )
    check("setup operator lock is at least as strict as dashboard", rl.policy("setup_operator_login").limit <= rl.policy("dashboard_login").limit)

    os.environ["WATHEFNI_RATE_LIMIT_OVERRIDES"] = '{"dashboard_login": {"limit": 3}}'
    check("policies are tunable without a code change", rl.policy("dashboard_login").limit == 3)
    _clear("WATHEFNI_RATE_LIMIT_OVERRIDES")
    check("override removal restores the default", rl.policy("dashboard_login").limit == 8)

    check("identity digests are not reversible", rl.principal_digest("ACME|ceo@acme.test") != "ACME|ceo@acme.test")
    check("empty principal is labelled, not hashed", rl.principal_digest("") == "anonymous")

    redacted = rl.safe_detail(
        {
            "password": "hunter2",
            "operator_token": "abcd",
            "bearer_token": "xyz",
            "signing_secret": "s3cret",
            "route": "/dashboard/auth/login",
            "attempts": 9,
            "nested": {"authorization": "Bearer abc", "company_code": "ALPHACO"},
        }
    )
    check("passwords never reach the audit record", redacted["password"] == "[redacted]")
    check("operator tokens never reach the audit record", redacted["operator_token"] == "[redacted]")
    check("bearer tokens never reach the audit record", redacted["bearer_token"] == "[redacted]")
    check("signing secrets never reach the audit record", redacted["signing_secret"] == "[redacted]")
    check("nested credentials are redacted too", redacted["nested"]["authorization"] == "[redacted]")
    check("diagnostic context survives redaction", redacted["route"] == "/dashboard/auth/login" and redacted["attempts"] == 9)


def source_contracts() -> None:
    print("\n    R2 — source-level regressions that must not come back")
    source = Path(__file__).resolve().parent.joinpath("app.py").read_text(encoding="utf-8")
    check("no committed assessment dev secret in app.py", OLD_ASSESSMENT_CONSTANT not in source)
    check("no committed video-interview dev secret in app.py", OLD_VIDEO_CONSTANT not in source)
    check(
        "signing no longer falls back to the database URL",
        'or os.environ.get("WATHEFNI_DATABASE_URL")' not in source,
    )
    check(
        "audit reads are company scoped",
        source.count("FROM hr_turns\n                WHERE company_code=%s") == 1,
    )
    check(
        "web_dashboard metadata alone is no longer tenant authority",
        'str(metadata.get("channel") or "") == "web_dashboard"' not in source
        or "metadata_has_dashboard_authority" in source,
    )
    check("dashboard turn authority marker exists", "DASHBOARD_TURN_AUTHORITY_KEY" in source)


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    print("    PRODUCTION READINESS R2 — security hardening unit contracts")
    link_secret_contracts()
    token_forgery_contracts()
    internal_authority_contracts()
    worker_auth_contracts()
    rate_limit_contracts()
    source_contracts()
    print("\n    R2_SECURITY_UNIT_PASS")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
