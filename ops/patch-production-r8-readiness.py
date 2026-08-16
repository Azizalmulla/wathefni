#!/usr/bin/env python3
"""Create a narrowly scoped R2-link/R8-readiness production app candidate.

This is for the older production listener only. It refuses unknown/already
diverged input, never edits in place, and leaves deployment/backups to the
operator. The current repository app remains the source authority.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_span(source: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = source.find(start_marker)
    end = source.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise RuntimeError(f"patch_marker_missing:{start_marker!r}:{end_marker!r}")
    return source[:start] + replacement.rstrip() + "\n\n\n" + source[end:]


LINK_HELPERS = '''def assessment_link_secret() -> bytes:
    """R2 dedicated assessment signing key; no credential/dev fallback."""
    return _link_secrets.signing_secret("assessment")


def video_interview_link_secret() -> bytes:
    """R2 dedicated video-interview signing key; fail closed."""
    return _link_secrets.signing_secret("video_interview")


def link_signing_available(purpose: str) -> bool:
    return _link_secrets.available(purpose)


def link_signing_unavailable_error(purpose: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "link_signing_unavailable",
            "message": "This link capability is temporarily unavailable.",
            "purpose": purpose,
        },
    )'''


ASSESSMENT_VERIFY = '''def _verify_link_signature(purpose: str, subject_id: str, token: str | None) -> bool:
    """Constant-time verification against active and retired R2 keys."""
    if not token:
        return False
    try:
        decoded = b64url_decode(str(token))
        prefix, signature = decoded[:-32], decoded[-32:]
        payload = prefix.decode("utf-8").rstrip(":")
        token_subject, expires_text = payload.rsplit(":", 1)
        expires_at = int(expires_text)
    except Exception:
        return False
    if not _link_secrets.compare_text(str(subject_id), str(token_subject)):
        return False
    if expires_at < int(time_module.time()):
        return False
    try:
        candidates = _link_secrets.verification_secrets(purpose)
    except _link_secrets.LinkSecretUnavailable:
        return False
    matched = False
    for secret in candidates:
        expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest()
        matched = _link_secrets.compare(expected, signature) or matched
    return matched


def verify_assessment_token(attempt_id: str, token: str | None) -> bool:
    return _verify_link_signature("assessment", attempt_id, token)'''


VIDEO_VERIFY = '''def verify_video_interview_token(interview_id: str, token: str | None) -> bool:
    return _verify_link_signature("video_interview", interview_id, token)'''


HEALTH_READY = '''@app.get("/health")
def health():
    """Liveness only. Auth flags and schema apply stay off this public probe."""
    return {
        "status": "ok",
        "runtime": "toolcall_fastapi",
        "liveness": True,
        "environment_binding": runtime_environment_readiness(),
        "permission_authority": "backend_current_required",
    }


@app.get("/ready")
def ready():
    """Frozen R8 readiness: authority, link signing, delivery, migrations."""
    ensure_schema()
    legacy_on = legacy_dashboard_token_auth_enabled()
    link_signing = _link_secrets.status()
    delivery = _observability.delivery_snapshot(sys.modules[__name__])
    migrations = delivery.get("migrations") or {}
    ready_ok = bool(migrations.get("ok", True))
    payload = {
        "status": "ready" if ready_ok else "not_ready",
        "environment_binding": runtime_environment_readiness(),
        "permission_authority": "backend_current_required",
        "legacy_dashboard_token_auth": legacy_on,
        "trusted_authority_enforced": not legacy_on,
        "link_signing": link_signing,
        "public_link_capabilities_available": bool(link_signing.get("ok")),
        "delivery": delivery,
    }
    if ready_ok:
        return payload
    return JSONResponse(status_code=503, content=payload)'''


def patch(source: str) -> str:
    banned = ("wathefni-assessment-dev-secret", "wathefni-video-interview-dev-secret")
    if not all(value in source for value in banned):
        raise RuntimeError("unexpected_input:legacy_link_fallbacks_not_both_present")
    if "import observability as _observability" in source:
        raise RuntimeError("unexpected_input:r8_already_present")

    import_anchor = "import operator_mobile_data as _operator_mobile_data  # noqa: E402\n"
    imports = (
        import_anchor
        + "import security_link_secrets as _link_secrets  # R2/R8 production parity\n"
        + "import observability as _observability  # R8 production parity\n"
        + "import observability_http as _observability_http  # R8 production parity\n"
    )
    if source.count(import_anchor) != 1:
        raise RuntimeError("unexpected_input:operator_mobile_import_anchor")
    source = source.replace(import_anchor, imports, 1)

    source = replace_span(source, "def assessment_link_secret() -> bytes:", "def b64url_encode(value: bytes) -> str:", LINK_HELPERS)
    source = replace_span(source, "def verify_assessment_token(attempt_id: str, token: str | None) -> bool:", "def assessment_public_link(attempt_id: str, raw_token: str) -> str:", ASSESSMENT_VERIFY)
    source = replace_span(source, "def verify_video_interview_token(interview_id: str, token: str | None) -> bool:", "def video_interview_public_link(interview_id: str, *, ttl_days: int = 14) -> tuple[str, datetime]:", VIDEO_VERIFY)

    video_anchor = "def video_interview_public_link(interview_id: str, *, ttl_days: int = 14) -> tuple[str, datetime]:\n    ttl_seconds ="
    video_secure = "def video_interview_public_link(interview_id: str, *, ttl_days: int = 14) -> tuple[str, datetime]:\n    if not link_signing_available(\"video_interview\"):\n        raise link_signing_unavailable_error(\"video_interview\")\n    ttl_seconds ="
    if source.count(video_anchor) != 1:
        raise RuntimeError("unexpected_input:video_public_link_anchor")
    source = source.replace(video_anchor, video_secure, 1)

    fetch_anchor = "def fetch_public_async_video_interview(interview_id: str, token: str | None, *, start: bool = False) -> dict[str, Any]:\n    if not verify_video_interview_token"
    fetch_secure = "def fetch_public_async_video_interview(interview_id: str, token: str | None, *, start: bool = False) -> dict[str, Any]:\n    if not link_signing_available(\"video_interview\"):\n        raise link_signing_unavailable_error(\"video_interview\")\n    if not verify_video_interview_token"
    if source.count(fetch_anchor) != 1:
        raise RuntimeError("unexpected_input:video_fetch_anchor")
    source = source.replace(fetch_anchor, fetch_secure, 1)

    source = replace_span(source, '@app.get("/health")\ndef health():', '@app.get("/orchestrator/debug/prompt-context")', HEALTH_READY)

    register_anchor = "_operator_mobile_data.register_operator_mobile_data_routes(sys.modules[__name__])\n"
    register = register_anchor + "_observability_http.register_observability_http(sys.modules[__name__])\n"
    if source.count(register_anchor) != 1:
        raise RuntimeError("unexpected_input:operator_mobile_register_anchor")
    source = source.replace(register_anchor, register, 1)

    # The production checkout already mounts the canonical Unified Candidates
    # router. These historical local helpers duplicated eight method/path pairs
    # with weaker, older wrappers. Keep the callables for compatibility, but do
    # not mount them a second time.
    duplicate_decorators = (
        '@app.post("/dashboard/prehire/applications/{app_key}/facts/review")\n',
        '@app.get("/dashboard/prehire/applications/{app_key}/facts")\n',
        '@app.get("/dashboard/prehire/applications/{app_key}/profile")\n',
        '@app.delete("/dashboard/prehire/candidates/saved-views/{view_id}")\n',
        '@app.get("/dashboard/prehire/intake-operations/attention")\n',
        '@app.get("/dashboard/prehire/intake-operations")\n',
        '@app.post("/dashboard/prehire/candidates/saved-views")\n',
        '@app.get("/dashboard/prehire/candidates/saved-views")\n',
    )
    for decorator in duplicate_decorators:
        if source.count(decorator) != 1:
            raise RuntimeError(f"unexpected_input:duplicate_decorator:{decorator.strip()}")
        source = source.replace(decorator, "", 1)

    local_anchor = "# local-only: dashboard_prehire_application_fact_review"
    local_note = (
        "# Legacy local-only compatibility helpers below are intentionally not mounted.\n"
        "# The canonical Unified Candidates router owns these eight method/path pairs.\n\n"
    )
    if source.count(local_anchor) != 1:
        raise RuntimeError("unexpected_input:local_unified_candidates_anchor")
    source = source.replace(local_anchor, local_note + local_anchor, 1)

    if any(value in source for value in banned):
        raise RuntimeError("postcondition:legacy_link_fallback_remains")
    required = (
        "_link_secrets.verification_secrets",
        '"link_signing": link_signing',
        '"delivery": delivery',
        "_observability_http.register_observability_http",
        "status_code=503",
        "Legacy local-only compatibility helpers below are intentionally not mounted.",
    )
    if not all(value in source for value in required):
        raise RuntimeError("postcondition:r8_contract_incomplete")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise SystemExit("refusing in-place patch")
    result = patch(args.source.read_text(encoding="utf-8"))
    args.output.write_text(result, encoding="utf-8")
    print(f"PATCHED_R2_R8_CANDIDATE={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
