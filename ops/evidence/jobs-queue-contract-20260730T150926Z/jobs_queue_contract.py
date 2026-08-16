"""Jobs applicant-count and status-alias contract — single source of truth.

Approved product contract:

* jobs.applications_total — every historical application (all statuses), under
  the existing production + CV-exists gate.
* jobs.active_pipeline — same gate, excluding hired / rejected / withdrawn /
  archived.
* jobs.role_active_candidates — exact same predicate as active_pipeline, plus
  the selected position_code (Candidates list filter).
* Clickable Applications number, View candidates open total, and close-job
  confirmation all use active_pipeline.
* Historical funnel / stage_counts may retain all statuses and must not be
  presented as the clickable active-applicant count.

Job status authority:

* Canonical: draft | open | paused | closed
* Aliases: active, published → open; inactive → closed
* Lifecycle transitions unchanged; reopen is closed → open.
"""

from __future__ import annotations

from typing import Any

CANONICAL_JOB_STATUSES = ("draft", "open", "paused", "closed")
CANONICAL_JOB_STATUS_SET = frozenset(CANONICAL_JOB_STATUSES)

JOB_STATUS_ALIASES = {
    "active": "open",
    "published": "open",
    "inactive": "closed",
}

# Terminal / out-of-pipeline application statuses for active_pipeline.
PIPELINE_EXCLUDED_STATUSES = ("hired", "rejected", "withdrawn", "archived")

# Production + CV gate shared by Jobs inventory aggregates (and funnel).
APPLICATIONS_PRODUCTION_CV_SQL = (
    "COALESCE(data_source, raw_json->>'data_source', 'production')='production'"
    " AND (cv_received IS TRUE OR jsonb_typeof(raw_json->'cv') = 'object')"
)


def normalize_job_status(value: Any, *, blank_as: str = "open") -> str:
    """Normalize legacy aliases to a canonical job status.

    Blank maps to ``blank_as`` (default ``open``) to preserve existing serialize
    / eligibility behavior. Unknown non-blank values map to ``closed``.
    """
    status = str(value or "").strip().lower()
    if not status:
        return blank_as if blank_as in CANONICAL_JOB_STATUS_SET else "closed"
    status = JOB_STATUS_ALIASES.get(status, status)
    if status not in CANONICAL_JOB_STATUS_SET:
        return "closed"
    return status


def coerce_job_status_filter(value: Any) -> str:
    """Accept UI/API status filters including aliases; empty means no filter."""
    raw = str(value or "").strip().lower()
    if raw in {"", "all", "*"}:
        return ""
    normalized = JOB_STATUS_ALIASES.get(raw, raw)
    return normalized if normalized in CANONICAL_JOB_STATUS_SET else ""


def active_pipeline_predicate(alias: str = "a") -> str:
    """SQL predicate for jobs.active_pipeline / jobs.role_active_candidates."""
    excluded = ", ".join(f"'{status}'" for status in PIPELINE_EXCLUDED_STATUSES)
    return f"{alias}.status NOT IN ({excluded})"


def active_pipeline_status_filter_sql(status_expr: str = "status") -> str:
    """FILTER / WHERE fragment for a bare status column expression."""
    excluded = ", ".join(f"'{status}'" for status in PIPELINE_EXCLUDED_STATUSES)
    return f"{status_expr} NOT IN ({excluded})"


def effective_job_status_sql(column: str = "p.status") -> str:
    """SQL expression that normalizes legacy job status aliases to canonical."""
    return (
        "CASE"
        f" WHEN lower(COALESCE(NULLIF(TRIM({column}), ''), ''))"
        " IN ('', 'active', 'published') THEN 'open'"
        f" WHEN lower(COALESCE(NULLIF(TRIM({column}), ''), '')) = 'inactive' THEN 'closed'"
        f" WHEN lower(COALESCE(NULLIF(TRIM({column}), ''), 'closed'))"
        " IN ('draft', 'open', 'paused', 'closed')"
        f" THEN lower(COALESCE(NULLIF(TRIM({column}), ''), 'closed'))"
        " ELSE 'closed'"
        " END"
    )


def is_active_pipeline_status(status: Any) -> bool:
    raw = str(status or "").strip().lower()
    return bool(raw) and raw not in PIPELINE_EXCLUDED_STATUSES
