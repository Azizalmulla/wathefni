#!/usr/bin/env python3
"""Create the narrow production compatibility artifact for OctoHR parity.

The VPS still runs a historically patched app.py. Replacing it wholesale would
discard accepted production fixes. This patcher therefore preserves the
already-deployed review-auth registration and adds only the five frozen
employee feature definitions, the five frozen HTTP router registrations, and
the matching module-catalog rows.

Every durable inbound-intake and app-link marker is required before a patch is
written. The expected source hashes make unexplained drift fail closed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

EXPECTED_APP_SHA256 = "4912189f246eac19fea4b1c5e72ef32d3f90a534f95036fa44a48e6f8eb53b69"
EXPECTED_CATALOG_SHA256 = "d2d5b7f3096f405efb3997777647bb57982fb65b1746a8c508185f7ad59bfabd"

APP_MARKER = "OCTOHR_PRODUCTION_PARITY_COMPAT_V1"
CATALOG_MARKER = "OCTOHR_PRODUCTION_PARITY_CATALOG_V1"

PRESERVED_APP_MARKERS = (
    '"/orchestrator/debug/intake-operations"',
    '"/orchestrator/debug/intake-documents/{document_id}/download"',
    '"/orchestrator/debug/intake-documents/{document_id}/signed-download"',
    '"/orchestrator/debug/intake-quarantine/sweep"',
    '"/orchestrator/debug/intake-worker/run"',
    "import app_links as _app_links",
    "app.include_router(_app_links.router)",
)

STORE_REVIEW_ANCHOR = "_operator_mobile.register_operator_mobile_routes(sys.modules[__name__])\n"
STORE_REVIEW_BLOCK = f"""_operator_mobile.register_operator_mobile_routes(sys.modules[__name__])
import store_review_access as _store_review_access

_store_review_access.register_store_review_routes(sys.modules[__name__])  # {APP_MARKER}
"""

PAYSLIP_FEATURE = """    "payslips": {
        "dependency_mode": "all",
        "module_keys": ("payroll",),
        "actions": ("view", "download"),
        "implemented": True,
    },
"""

POSTHIRE_FEATURES = f"""    "performance": {{
        "dependency_mode": "all",
        "module_keys": ("performance",),
        "actions": ("view", "update", "submit"),
        "implemented": True,
    }},
    "talent": {{
        "dependency_mode": "all",
        "module_keys": ("talent",),
        "actions": ("view", "update"),
        "implemented": True,
    }},
    "learning": {{
        "dependency_mode": "all",
        "module_keys": ("learning",),
        "actions": ("view", "request"),
        "implemented": True,
    }},
    "benefits": {{
        "dependency_mode": "all",
        "module_keys": ("benefits",),
        "actions": ("view", "enroll", "waive"),
        "implemented": True,
    }},
    "engagement": {{
        "dependency_mode": "all",
        "module_keys": ("engagement",),
        "actions": ("view", "submit"),
        "implemented": True,
    }},  # {APP_MARKER}
"""

APP_AUTH_ANCHOR = "# --- /app auth ---------------------------------------------------------------\n"
ROUTER_BLOCK = f"""# Frozen post-hire HTTP adapters. They register only after dashboard_context,
# _posthire_read_context, require_employee_app_feature, and employee_app_context.
import performance_http as _performance_http
import talent_http as _talent_http
import learning_http as _learning_http
import benefits_http as _benefits_http
import engagement_http as _engagement_http

_performance_http.register_performance_http(sys.modules[__name__])
_talent_http.register_talent_http(sys.modules[__name__])
_learning_http.register_learning_http(sys.modules[__name__])
_benefits_http.register_benefits_http(sys.modules[__name__])
_engagement_http.register_engagement_http(sys.modules[__name__])  # {APP_MARKER}


"""

ANALYTICS_MODULE_ANCHOR = """    ModuleDefinition(
        "analytics",
"""

CATALOG_BLOCK = f"""    # {CATALOG_MARKER}
    ModuleDefinition(
        "performance", "Performance", "post_hire", "employee", 155, True, True,
        recommended_with=(),
        recommendation_copy="Works alone. Talent remains a separate unreleased capability.",
        app_surface_key="performance", app_surface_label="Goals, reviews, and development",
    ),
    ModuleDefinition(
        "talent", "Talent", "post_hire", "employee", 156, True, True,
        recommended_with=(),
        recommendation_copy="Works alone. Distinct from Performance and from recruiting talent_pool.",
        app_surface_key="talent", app_surface_label="Career interests and mobility preferences",
    ),
    ModuleDefinition(
        "learning", "Learning & Development", "post_hire", "employee", 157, True, True,
        recommended_with=(),
        recommendation_copy="Works alone. Optional Performance / Talent / Job Architecture enrichment. Does not duplicate Wave 4 development plans.",
        app_surface_key="learning", app_surface_label="My learning, mandatory training, and certificates",
    ),
    ModuleDefinition(
        "benefits", "Benefits", "post_hire", "employee", 158, False, True,
        recommended_with=(),
        recommendation_copy="Works alone. Payroll handoff is optional. Claims remain out of scope.",
        app_surface_key="benefits", app_surface_label="My benefits, enrollment, and coverage",
    ),
    ModuleDefinition(
        "engagement", "Engagement", "post_hire", "employee", 161, False, True,
        recommended_with=(),
        recommendation_copy="Works alone. Anonymous responses stay anonymous. Below the anonymity threshold, results are suppressed — never guessed. Recognition is out of scope.",
        app_surface_key="engagement", app_surface_label="Open surveys and participation",
    ),
"""

ALIAS_ANCHOR = '    "onboarding": "onboarding",\n'
ALIAS_BLOCK = f"""    "performance": "performance",
    "perf": "performance",
    "learning": "learning",
    "learning_development": "learning",
    "l_and_d": "learning",
    "benefits": "benefits",
    "benefits_administration": "benefits",
    "engagement": "engagement",
    "surveys": "engagement",  # {CATALOG_MARKER}
"""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _insert_once(source: str, anchor: str, replacement: str, label: str) -> str:
    count = source.count(anchor)
    if count != 1:
        raise RuntimeError(f"{label}_anchor_count={count}")
    return source.replace(anchor, replacement, 1)


def patch_app(raw: bytes) -> str:
    source = raw.decode("utf-8")
    for marker in PRESERVED_APP_MARKERS:
        if marker not in source:
            raise RuntimeError(f"preserved_hotfix_missing={marker}")
    if APP_MARKER not in source:
        if _digest(raw) != EXPECTED_APP_SHA256:
            raise RuntimeError(f"app_base_sha_mismatch={_digest(raw)}")
        if "register_store_review_routes" not in source:
            source = _insert_once(source, STORE_REVIEW_ANCHOR, STORE_REVIEW_BLOCK, "store_review")
        source = _insert_once(
            source,
            PAYSLIP_FEATURE,
            PAYSLIP_FEATURE + POSTHIRE_FEATURES,
            "employee_features",
        )
        source = _insert_once(
            source,
            APP_AUTH_ANCHOR,
            ROUTER_BLOCK + APP_AUTH_ANCHOR,
            "frozen_routers",
        )
    for required in (
        "register_store_review_routes",
        "register_performance_http",
        "register_talent_http",
        "register_learning_http",
        "register_benefits_http",
        "register_engagement_http",
        '"performance": {',
        '"talent": {',
        '"learning": {',
        '"benefits": {',
        '"engagement": {',
    ):
        if required not in source:
            raise RuntimeError(f"app_required_marker_missing={required}")
    ast.parse(source)
    return source


def patch_catalog(raw: bytes) -> str:
    source = raw.decode("utf-8")
    if CATALOG_MARKER not in source:
        if _digest(raw) != EXPECTED_CATALOG_SHA256:
            raise RuntimeError(f"catalog_base_sha_mismatch={_digest(raw)}")
        source = _insert_once(
            source,
            ANALYTICS_MODULE_ANCHOR,
            CATALOG_BLOCK + ANALYTICS_MODULE_ANCHOR,
            "catalog_modules",
        )
        source = _insert_once(
            source,
            ALIAS_ANCHOR,
            ALIAS_BLOCK + ALIAS_ANCHOR,
            "catalog_aliases",
        )
    for key in ("performance", "talent", "learning", "benefits", "engagement"):
        if f'        "{key}"' not in source and f'        "{key}",' not in source:
            raise RuntimeError(f"catalog_module_missing={key}")
    ast.parse(source)
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-source", type=Path, required=True)
    parser.add_argument("--app-output", type=Path, required=True)
    parser.add_argument("--catalog-source", type=Path, required=True)
    parser.add_argument("--catalog-output", type=Path, required=True)
    args = parser.parse_args()

    app_raw = args.app_source.read_bytes()
    catalog_raw = args.catalog_source.read_bytes()
    args.app_output.write_text(patch_app(app_raw), encoding="utf-8")
    args.catalog_output.write_text(patch_catalog(catalog_raw), encoding="utf-8")
    print(f"app_base_sha256={_digest(app_raw)}")
    print(f"app_patched_sha256={_digest(args.app_output.read_bytes())}")
    print(f"catalog_base_sha256={_digest(catalog_raw)}")
    print(f"catalog_patched_sha256={_digest(args.catalog_output.read_bytes())}")
    print(f"preserved_hotfix_markers={len(PRESERVED_APP_MARKERS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
