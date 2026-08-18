#!/usr/bin/env python3
"""Build the narrow public account-deletion production compatibility artifact.

Production runs a historically composed ``app.py``.  Replacing that file with
the repository copy would discard accepted production-only composition layers.
This patcher therefore requires the exact qualified production hash, verifies
the durable intake/app-link/parity/Leave markers, and copies only the new
deletion request authority slices from the tracked repository source.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path


EXPECTED_PRODUCTION_APP_SHA256 = "3a144ca1fbfdcd0d1a26344e992c578aae376834c3c51fa043cdc282bac5327d"
EXPECTED_PRODUCTION_RATE_LIMIT_SHA256 = "2ef46cdd44011934c4c20207596a266282c8958588e2ac4e84837922acefab50"
EXPECTED_AUTHORITY_APP_SHA256 = "aed17be195c15e767f62c32ef610882ee5601eab8b0ad15e52912d206e6cfc4f"
MARKER = "OCTOHR_PUBLIC_ACCOUNT_DELETION_COMPAT_V1"

PRESERVED_APP_MARKERS = (
    '"/orchestrator/debug/intake-operations"',
    '"/orchestrator/debug/intake-documents/{document_id}/download"',
    '"/orchestrator/debug/intake-documents/{document_id}/signed-download"',
    '"/orchestrator/debug/intake-quarantine/sweep"',
    '"/orchestrator/debug/intake-worker/run"',
    "import app_links as _app_links",
    "app.include_router(_app_links.router)",
    "OCTOHR_PRODUCTION_PARITY_COMPAT_V1",
    "register_store_review_routes",
    "performance.calibrate",
    "cancel_policy_projection",
    "leave_already_started",
)

EMPLOYEE_BODY_ANCHOR = """class EmployeeDeletionRequestBody(BaseModel):
    reason: str | None = None
"""
OLD_ROUTE_START = '@app.post("/app/account/request-deletion")\n'
ROUTE_END = "\n\n# --- Dashboard side: HR provisions an app invite"

RATE_LIMIT_BLOCK = """    \"public_account_deletion\": RateLimitPolicy(
        key=\"public_account_deletion\",
        limit=5,
        window_seconds=15 * 60,
        lock_seconds=30 * 60,
        mode=MODE_REQUEST,
        dimensions=(\"source\", \"identity\"),
        description=\"Public employee account/data deletion request initiation.\",
    ),
"""
RATE_LIMIT_END = "}\n\n# Per-dimension limit multipliers"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def one_slice(source: str, start: str, end: str, label: str) -> str:
    if source.count(start) != 1 or source.count(end) != 1:
        raise RuntimeError(f"{label}_authority_anchor_mismatch")
    start_at = source.index(start)
    end_at = source.index(end, start_at)
    return source[start_at:end_at]


def patch_app(production_raw: bytes, authority_raw: bytes) -> str:
    production_hash = digest(production_raw)
    authority_hash = digest(authority_raw)
    if production_hash != EXPECTED_PRODUCTION_APP_SHA256:
        raise RuntimeError(f"production_app_sha_mismatch={production_hash}")
    if authority_hash != EXPECTED_AUTHORITY_APP_SHA256:
        raise RuntimeError(f"authority_app_sha_mismatch={authority_hash}")

    source = production_raw.decode("utf-8")
    authority = authority_raw.decode("utf-8")
    for preserved in PRESERVED_APP_MARKERS:
        if preserved not in source:
            raise RuntimeError(f"preserved_production_marker_missing={preserved}")
    if MARKER in source or "/public/account-deletion/request" in source:
        raise RuntimeError("public_account_deletion_already_present")

    public_body = one_slice(
        authority,
        "class PublicEmployeeDeletionRequestBody(BaseModel):",
        "\n\ndef _app_code_generate",
        "public_body",
    )
    if source.count(EMPLOYEE_BODY_ANCHOR) != 1:
        raise RuntimeError("employee_body_anchor_mismatch")
    source = source.replace(
        EMPLOYEE_BODY_ANCHOR,
        f"{EMPLOYEE_BODY_ANCHOR}\n\n# {MARKER}\n{public_body}",
        1,
    )

    authority_route = one_slice(
        authority,
        "def create_employee_account_deletion_request(",
        ROUTE_END,
        "deletion_route",
    )
    if "INSERT INTO employee_sessions" in authority_route or "/app/auth/activate" in authority_route:
        raise RuntimeError("authority_route_must_not_create_session_or_activate")
    if source.count(OLD_ROUTE_START) != 1 or source.count(ROUTE_END) != 1:
        raise RuntimeError("production_deletion_route_anchor_mismatch")
    old_start = source.index(OLD_ROUTE_START)
    old_end = source.index(ROUTE_END, old_start)
    source = (
        source[:old_start]
        + f"# {MARKER}\n"
        + authority_route
        + source[old_end:]
    )

    for required in (
        "class PublicEmployeeDeletionRequestBody",
        "def create_employee_account_deletion_request",
        '@app.options("/public/account-deletion/request")',
        '@app.post("/public/account-deletion/request")',
        'channel="public_web"',
        "public_account_deletion",
    ):
        if required not in source:
            raise RuntimeError(f"patched_app_marker_missing={required}")
    for preserved in PRESERVED_APP_MARKERS:
        if preserved not in source:
            raise RuntimeError(f"preserved_marker_lost={preserved}")
    ast.parse(source)
    return source


def patch_rate_limit(production_raw: bytes) -> str:
    production_hash = digest(production_raw)
    if production_hash != EXPECTED_PRODUCTION_RATE_LIMIT_SHA256:
        raise RuntimeError(f"production_rate_limit_sha_mismatch={production_hash}")
    source = production_raw.decode("utf-8")
    if "public_account_deletion" in source:
        raise RuntimeError("public_account_deletion_rate_limit_already_present")
    if source.count(RATE_LIMIT_END) != 1:
        raise RuntimeError("rate_limit_anchor_mismatch")
    source = source.replace(RATE_LIMIT_END, RATE_LIMIT_BLOCK + RATE_LIMIT_END, 1)
    ast.parse(source)
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-app", type=Path, required=True)
    parser.add_argument("--authority-app", type=Path, required=True)
    parser.add_argument("--production-rate-limit", type=Path, required=True)
    parser.add_argument("--app-output", type=Path, required=True)
    parser.add_argument("--rate-limit-output", type=Path, required=True)
    args = parser.parse_args()

    app_source = args.production_app.read_bytes()
    authority_source = args.authority_app.read_bytes()
    rate_source = args.production_rate_limit.read_bytes()
    args.app_output.write_text(patch_app(app_source, authority_source), encoding="utf-8")
    args.rate_limit_output.write_text(patch_rate_limit(rate_source), encoding="utf-8")
    print(f"production_app_sha256={digest(app_source)}")
    print(f"patched_app_sha256={digest(args.app_output.read_bytes())}")
    print(f"production_rate_limit_sha256={digest(rate_source)}")
    print(f"patched_rate_limit_sha256={digest(args.rate_limit_output.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
