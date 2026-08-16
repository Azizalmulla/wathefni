#!/usr/bin/env python3
"""Surgical production patch for complete Talent Pool Classification UI read model.

Same complete-UI anchors as staging, tolerant of
UNIFIED_CANDIDATES_PRODUCTION_DARK_PATCH import markers.
Idempotent. Does not replace whole app.py.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_staging_patch():
    staging_path = (
        pathlib.Path(__file__).resolve().parent
        / "patch-staging-app-talent-pool-classification-complete-ui.py"
    )
    spec = importlib.util.spec_from_file_location("tpc_complete_ui_staging_patch", staging_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def patch(src: str, staging) -> str:
    out = src
    out = staging._ensure_route_mount(out)
    if "classification_filters: dict[str, Any] | None = None," not in out:
        replaced = False
        for marker in (
            "UNIFIED_CANDIDATES_STAGING_PATCH",
            "UNIFIED_CANDIDATES_PRODUCTION_DARK_PATCH",
        ):
            old = (
                "    department_intake_tag: str | None = None,\n"
                "    include_match_reasons: bool = False,\n"
                ") -> dict[str, Any]:\n"
                f"    import unified_candidates as _uc  # {marker}\n"
            )
            new = (
                "    department_intake_tag: str | None = None,\n"
                "    include_match_reasons: bool = False,\n"
                f"    classification_filters: dict[str, Any] | None = None,  # {staging.COMPLETE_MARKER}\n"
                ") -> dict[str, Any]:\n"
                f"    import unified_candidates as _uc  # {marker}\n"
                f"    import talent_pool_classification as _tpc  # {staging.COMPLETE_MARKER}\n"
            )
            if old in out:
                out = out.replace(old, new, 1)
                replaced = True
                break
        if not replaced:
            raise RuntimeError("prehire_applications_query signature anchor missing")
    out = staging._patch_use_unified(out)
    out = staging._patch_filter_sql(out)
    out = staging._patch_row_projection(out)
    out = staging._patch_payload_merge(out)
    out = staging._patch_return_echo(out)
    out = staging._patch_dashboard_endpoint(out)
    if staging.COMPLETE_MARKER not in out:
        raise RuntimeError("complete UI markers missing after patch")
    if "mount_talent_pool_classification_routes" not in out:
        raise RuntimeError("classification routes not mounted")
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: patch-production-app-talent-pool-classification-complete-ui.py <app.py.in> <app.py.out>",
            file=sys.stderr,
        )
        return 2
    staging = _load_staging_patch()
    src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    pathlib.Path(sys.argv[2]).write_text(patch(src, staging), encoding="utf-8")
    print("patched", sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
