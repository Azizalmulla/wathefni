#!/usr/bin/env python3
"""Surgically mount Talent Pool Classification routes on staging app.py.

Also repairs latent Unified Candidates mid-file mount (helpers must exist first).
Does not replace whole app.py. Idempotent.
"""
from __future__ import annotations

import pathlib
import sys

MARKER = "TALENT_POOL_CLASSIFICATION_STAGING_PATCH"
UC_MARKER = "UNIFIED_CANDIDATES_STAGING_PATCH"

EARLY_MOUNT_OLD = (
    "import unified_candidates_routes as _unified_candidates_routes  "
    f"# {UC_MARKER}\n\n"
    "_unified_candidates_routes.mount_unified_candidate_routes(sys.modules[__name__])\n"
)

EARLY_MOUNT_NEW = (
    f"# {UC_MARKER}: import retained; late mount before SPA catch-all "
    f"(helpers such as record_admin_audit must exist first)\n"
    "import unified_candidates_routes as _unified_candidates_routes  "
    f"# {UC_MARKER}\n"
)

LATE_BLOCK = f"""
# {UC_MARKER}: late route mount after helpers exist, before SPA catch-all
import unified_candidates_routes as _unified_candidates_routes

_unified_candidates_routes.mount_unified_candidate_routes_late(sys.modules[__name__])

# {MARKER}: classification routes after helpers exist; independent of Unified Candidates flags
try:
    import talent_pool_classification_routes as _tpc_routes  # {MARKER}
except Exception as _tpc_import_err:
    print("talent_pool_classification import skipped:", _tpc_import_err)
    _tpc_routes = None
if _tpc_routes is not None:
    try:
        _tpc_routes.mount_talent_pool_classification_routes(sys.modules[__name__])
    except Exception as _tpc_mount_err:
        print("talent_pool_classification mount skipped:", _tpc_mount_err)


"""


def patch(src: str) -> str:
    out = src

    # Remove prior classification mid-file mounts if re-patching a failed attempt
    if f"# {MARKER}" in out and "mount_talent_pool_classification_routes" in out:
        # Strip previous broken insertion between offer routes and assessment routes
        start = out.find(f"# {MARKER}: schema + route mount")
        if start >= 0:
            # remove from marker through mount try/except block before assessment import
            end = out.find("import assessment_ai_routes", start)
            if end > start:
                # also remove any try/import block immediately before start that we added
                import_start = out.rfind("import unified_candidates_routes", 0, start)
                # keep unified import line if present before our bad block
                out = out[:start] + out[end:]

    # Normalize early mid-file mount → import only
    if "mount_unified_candidate_routes(sys.modules[__name__])" in out:
        out = out.replace(
            "import unified_candidates_routes as _unified_candidates_routes  "
            f"# {UC_MARKER}\n\n"
            "_unified_candidates_routes.mount_unified_candidate_routes(sys.modules[__name__])\n",
            EARLY_MOUNT_NEW,
            1,
        )
        # Also handle variant without blank line / with our prior broken insert remnants
        if "mount_unified_candidate_routes(sys.modules[__name__])" in out:
            out = out.replace(
                "_unified_candidates_routes.mount_unified_candidate_routes(sys.modules[__name__])\n",
                f"# deferred: use mount_unified_candidate_routes_late before SPA ({UC_MARKER})\n",
                1,
            )

    spa = '@app.get("/dashboard/{asset_path:path}")\ndef dashboard_spa_or_asset(asset_path: str):\n'
    if MARKER not in out or "mount_talent_pool_classification_routes" not in out.split(spa)[0][-2000:]:
        if spa not in out:
            raise RuntimeError("SPA catch-all anchor missing")
        if "mount_unified_candidate_routes_late(sys.modules[__name__])" in out and MARKER in out:
            pass  # already late-mounted
        else:
            # Avoid duplicating late UC mount if already present immediately above SPA
            if "mount_unified_candidate_routes_late(sys.modules[__name__])" in out and f"# {MARKER}" not in out:
                # Insert classification only after existing late UC mount
                late_uc = "_unified_candidates_routes.mount_unified_candidate_routes_late(sys.modules[__name__])\n"
                cls_only = f"""
# {MARKER}: classification routes after helpers exist; independent of Unified Candidates flags
try:
    import talent_pool_classification_routes as _tpc_routes  # {MARKER}
except Exception as _tpc_import_err:
    print("talent_pool_classification import skipped:", _tpc_import_err)
    _tpc_routes = None
if _tpc_routes is not None:
    try:
        _tpc_routes.mount_talent_pool_classification_routes(sys.modules[__name__])
    except Exception as _tpc_mount_err:
        print("talent_pool_classification mount skipped:", _tpc_mount_err)

"""
                if late_uc in out:
                    out = out.replace(late_uc, late_uc + cls_only, 1)
                else:
                    out = out.replace(spa, LATE_BLOCK + spa, 1)
            else:
                out = out.replace(spa, LATE_BLOCK + spa, 1)

    if MARKER not in out:
        raise RuntimeError("patch failed to insert classification markers")
    if "mount_unified_candidate_routes(sys.modules[__name__])" in out:
        raise RuntimeError("early unified candidates mount still present")
    if "mount_unified_candidate_routes_late(sys.modules[__name__])" not in out:
        raise RuntimeError("late unified candidates mount missing")
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch-staging-app-talent-pool-classification.py <app.py.in> <app.py.out>", file=sys.stderr)
        return 2
    src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    pathlib.Path(sys.argv[2]).write_text(patch(src), encoding="utf-8")
    print("patched", sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
