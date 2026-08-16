#!/usr/bin/env python3
"""Surgical staging patch for complete Talent Pool Classification UI read model.

Extends the prior route-mount patch with:
  - taxonomy-driven classification_filters on Candidates list
  - server-side EXISTS filtering before count/pagination
  - bulk sidecar projection (chip/state/node_ids) without N+1

Does not replace whole app.py. Idempotent. Does not touch production.
"""
from __future__ import annotations

import pathlib
import sys

MARKER = "TALENT_POOL_CLASSIFICATION_STAGING_PATCH"
COMPLETE_MARKER = "TALENT_POOL_CLASSIFICATION_COMPLETE_UI_PATCH"
UC_MARKER = "UNIFIED_CANDIDATES_STAGING_PATCH"

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


def _ensure_route_mount(out: str) -> str:
    spa = '@app.get("/dashboard/{asset_path:path}")\ndef dashboard_spa_or_asset(asset_path: str):\n'
    if "mount_talent_pool_classification_routes" in out and MARKER in out:
        return out
    if spa not in out:
        raise RuntimeError("SPA catch-all anchor missing")
    if "mount_unified_candidate_routes_late(sys.modules[__name__])" in out and MARKER not in out:
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
            return out.replace(late_uc, late_uc + cls_only, 1)
    return out.replace(spa, LATE_BLOCK + spa, 1)


def _patch_query_signature(out: str) -> str:
    if "classification_filters: dict[str, Any] | None = None," in out:
        return out
    old = (
        "    department_intake_tag: str | None = None,\n"
        "    include_match_reasons: bool = False,\n"
        ") -> dict[str, Any]:\n"
        "    import unified_candidates as _uc  # UNIFIED_CANDIDATES_STAGING_PATCH\n"
    )
    new = (
        "    department_intake_tag: str | None = None,\n"
        "    include_match_reasons: bool = False,\n"
        f"    classification_filters: dict[str, Any] | None = None,  # {COMPLETE_MARKER}\n"
        ") -> dict[str, Any]:\n"
        "    import unified_candidates as _uc  # UNIFIED_CANDIDATES_STAGING_PATCH\n"
        f"    import talent_pool_classification as _tpc  # {COMPLETE_MARKER}\n"
    )
    if old not in out:
        raise RuntimeError("prehire_applications_query signature anchor missing")
    return out.replace(old, new, 1)


def _patch_use_unified(out: str) -> str:
    if "parsed_classification" in out and COMPLETE_MARKER in out:
        return out
    old = """    unified_on = _uc.feature_enabled_for_company(company_code)
    use_unified = unified_on and (
        bool(view_key)
        or any(
            [
                source_channel,
                recruiter_owner,
                cv_processing_state,
                received_from,
                received_to,
                has_grounded_email,
                has_grounded_phone,
                fact_completeness,
                department_intake_tag,
            ]
        )
    )
"""
    new = f"""    unified_on = _uc.feature_enabled_for_company(company_code)
    classification_ui = False  # {COMPLETE_MARKER}
    parsed_classification = None  # {COMPLETE_MARKER}
    try:
        classification_ui = bool(
            _tpc.feature_enabled_for_company(company_code)
            and (_tpc.feature_ui_enabled() or _tpc.feature_schema_enabled())
        )
        if classification_ui and classification_filters:
            parsed_classification = _tpc.parse_classification_filter_query(classification_filters)
    except Exception:
        classification_ui = False
        parsed_classification = None
    use_unified = unified_on and (
        bool(view_key)
        or any(
            [
                source_channel,
                recruiter_owner,
                cv_processing_state,
                received_from,
                received_to,
                has_grounded_email,
                has_grounded_phone,
                fact_completeness,
                department_intake_tag,
                bool(parsed_classification and parsed_classification.get("active")),
            ]
        )
    )
"""
    if old not in out:
        raise RuntimeError("use_unified anchor missing")
    return out.replace(old, new, 1)


def _patch_filter_sql(out: str) -> str:
    if f"# {COMPLETE_MARKER}: classification EXISTS filter" in out:
        return out
    old = """    count_where_sql = " AND ".join(where)
    count_params = list(params)
"""
    new = f"""    if classification_ui and parsed_classification and parsed_classification.get("active"):  # {COMPLETE_MARKER}: classification EXISTS filter
        try:
            class_sql, class_params = _tpc.classification_filter_sql(
                company_code=company_code,
                filters=parsed_classification,
                applications_alias="a",
            )
            if class_sql and class_sql.strip() != "TRUE":
                where.append(f"({{class_sql}})")
                params.extend(class_params)
        except Exception:
            pass
    count_where_sql = " AND ".join(where)
    count_params = list(params)
"""
    # Fix f-string escaping - we want literal {class_sql} in the output file as f"({class_sql})"
    new = new.replace('f"({{class_sql}})"', 'f"({class_sql})"')
    if old not in out:
        raise RuntimeError("count_where_sql anchor missing")
    return out.replace(old, new, 1)


def _patch_row_projection(out: str) -> str:
    if f"# {COMPLETE_MARKER}: bulk classification projection" in out:
        return out
    old = """            rows = [dict(row) for row in cur.fetchall()]
            cur.execute(
                \"\"\"
                SELECT user_id, name, email, role, status
                FROM dashboard_users
"""
    new = f"""            rows = [dict(row) for row in cur.fetchall()]
            classification_by_app = {{}}  # {COMPLETE_MARKER}: bulk classification projection
            if classification_ui and rows:
                try:
                    app_keys = [str(r.get("app_key") or "") for r in rows if r.get("app_key")]
                    classification_by_app = _tpc.bulk_load_classification_rows(
                        cur,
                        company_code=company_code,
                        app_keys=app_keys,
                    )
                    for row in rows:
                        key = str(row.get("app_key") or "")
                        projection = (classification_by_app.get(key) or {{}}).get("projection") or {{}}
                        row["_classification_projection"] = projection
                except Exception:
                    for row in rows:
                        row["_classification_projection"] = {{}}
            cur.execute(
                \"\"\"
                SELECT user_id, name, email, role, status
                FROM dashboard_users
"""
    if old not in out:
        raise RuntimeError("rows fetch anchor missing")
    return out.replace(old, new, 1)


def _patch_payload_merge(out: str) -> str:
    if f"# {COMPLETE_MARKER}: merge classification projection" in out:
        return out
    old = """        if use_unified:
            gov = row.get("governance_json") if isinstance(row.get("governance_json"), dict) else None
            summary = _uc.enrich_application_summary(summary, row, gov=gov, permissions=permissions)
"""
    new = f"""        if use_unified:
            gov = row.get("governance_json") if isinstance(row.get("governance_json"), dict) else None
            summary = _uc.enrich_application_summary(summary, row, gov=gov, permissions=permissions)
        projection = row.get("_classification_projection") if isinstance(row.get("_classification_projection"), dict) else None  # {COMPLETE_MARKER}: merge classification projection
        if projection:
            summary.update(projection)
"""
    if old not in out:
        raise RuntimeError("unified payload enrich anchor missing")
    return out.replace(old, new, 1)


def _patch_return_echo(out: str) -> str:
    if '"classification_filters": parsed_classification' in out:
        return out
    old = """        "view": view_key or None,
        "unified_candidates": use_unified,
        "applications": _unified_applications_payload(
"""
    new = f"""        "view": view_key or None,
        "unified_candidates": use_unified,
        "classification_filters": parsed_classification if classification_ui else None,  # {COMPLETE_MARKER}
        "applications": _unified_applications_payload(
"""
    if old not in out:
        raise RuntimeError("return echo anchor missing")
    return out.replace(old, new, 1)


def _patch_dashboard_endpoint(out: str) -> str:
    if "classification_career_area: str | None = None," in out and COMPLETE_MARKER in out:
        return out
    old = """    fact_completeness: str | None = None,
    department_intake_tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidates.read")
    company = context["company_code"]
    search = (q or "").strip() or None
    return {
        "company_code": company,
        **prehire_applications_query(
"""
    new = f"""    fact_completeness: str | None = None,
    department_intake_tag: str | None = None,
    classification_career_area: str | None = None,  # {COMPLETE_MARKER}
    classification_likely_role: str | None = None,
    classification_skill: str | None = None,
    classification_industry: str | None = None,
    classification_seniority: str | None = None,
    classification_experience_band: str | None = None,
    classification_node_ids: str | None = None,
    classification_authority: str | None = None,
    classification_confidence: str | None = None,
    classification_include_medium_ai: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidates.read")
    company = context["company_code"]
    search = (q or "").strip() or None
    classification_filters = {{
        "career_area": (classification_career_area or "").strip() or None,
        "likely_role": (classification_likely_role or "").strip() or None,
        "skill": (classification_skill or "").strip() or None,
        "industry": (classification_industry or "").strip() or None,
        "seniority": (classification_seniority or "").strip() or None,
        "experience_band": (classification_experience_band or "").strip() or None,
        "node_ids": (classification_node_ids or "").strip() or None,
        "authority": (classification_authority or "").strip() or None,
        "confidence": (classification_confidence or "").strip() or None,
        "include_medium_ai": (classification_include_medium_ai or "").strip() or None,
    }}
    return {{
        "company_code": company,
        **prehire_applications_query(
"""
    if old not in out:
        raise RuntimeError("dashboard applications endpoint anchor missing")
    out = out.replace(old, new, 1)
    # Inject classification_filters kwarg into the query call if missing
    if "classification_filters=classification_filters," not in out:
        tip = "            include_match_reasons=bool(search),\n        ),\n    }"
        tip_new = (
            "            include_match_reasons=bool(search),\n"
            f"            classification_filters=classification_filters,  # {COMPLETE_MARKER}\n"
            "        ),\n    }"
        )
        # Only replace within dashboard function — first occurrence after dashboard def is fine
        dash = out.find("def dashboard_prehire_applications(")
        region = out[dash : dash + 5000]
        if tip not in region:
            raise RuntimeError("dashboard query call tip missing")
        out = out[:dash] + region.replace(tip, tip_new, 1) + out[dash + 5000 :]
    return out


def patch(src: str) -> str:
    out = src
    out = _ensure_route_mount(out)
    out = _patch_query_signature(out)
    out = _patch_use_unified(out)
    out = _patch_filter_sql(out)
    out = _patch_row_projection(out)
    out = _patch_payload_merge(out)
    out = _patch_return_echo(out)
    out = _patch_dashboard_endpoint(out)
    if COMPLETE_MARKER not in out:
        raise RuntimeError("complete UI markers missing after patch")
    if "mount_talent_pool_classification_routes" not in out:
        raise RuntimeError("classification routes not mounted")
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: patch-staging-app-talent-pool-classification-complete-ui.py <app.py.in> <app.py.out>",
            file=sys.stderr,
        )
        return 2
    src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    pathlib.Path(sys.argv[2]).write_text(patch(src), encoding="utf-8")
    print("patched", sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
