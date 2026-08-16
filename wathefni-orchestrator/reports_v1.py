"""Reports V1 — read-only hiring performance metrics (reports-metrics-v1).

Answers: "How is hiring performing, and where is it getting stuck?"

Consumes applications, lifecycle events, offers, interviews, Ranking runs,
and trusted intake-source buckets. Never mutates lifecycle/Ranking/offers.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable

METRIC_VERSION = "reports-metrics-v1"
REPORTS_MODULE = "pre_hiring"

# Trusted intake source buckets only (mirrors app._application_intake_source).
TRUSTED_SOURCE_BUCKETS = ("whatsapp", "bulk_import", "email", "manual", "unknown")

SENSITIVE_DENYLIST = frozenset(
    {
        "civil_id",
        "civilid",
        "national_id",
        "nationality",
        "gender",
        "sex",
        "religion",
        "date_of_birth",
        "dob",
        "marital_status",
        "family_status",
        "health",
        "disability",
        "address",
        "home_address",
        "personal_photo",
        "passport",
        "bank_account",
        "iban",
    }
)

FUNNEL_STEPS = (
    ("cv_received", "CV received"),
    ("ready_for_review", "Ready for review"),
    ("shortlisted", "Shortlisted"),
    ("interview", "Interview"),
    ("offer_sent", "Offer sent"),
    ("offer_accepted", "Offer accepted"),
    ("hired", "Hired"),
)

# Funnel steps that only exist while their optional module is enabled. A disabled
# module contributes no step, no label, and no conversion percentage.
FUNNEL_STEP_MODULES = {
    "interview": "interviews",
    "offer_sent": "employment_offers",
    "offer_accepted": "employment_offers",
}

FUNNEL_LABELS_AR = {
    "cv_received": "السيرة مستلمة",
    "ready_for_review": "جاهز للمراجعة",
    "shortlisted": "القائمة المختصرة",
    "interview": "مقابلة",
    "offer_sent": "عرض مرسل",
    "offer_accepted": "عرض مقبول",
    "hired": "تم التوظيف",
}

SOURCE_LABELS_EN = {
    "whatsapp": "WhatsApp",
    "bulk_import": "Bulk import",
    "email": "Email",
    "manual": "Manual",
    "unknown": "Unknown",
}

SOURCE_LABELS_AR = {
    "whatsapp": "واتساب",
    "bulk_import": "استيراد جماعي",
    "email": "بريد إلكتروني",
    "manual": "يدوي",
    "unknown": "غير معروف",
}

EXPORT_COLUMNS: dict[str, list[str]] = {
    "candidates": [
        "candidate",
        "phone",
        "email",
        "job",
        "status",
        "screening",
        "assessment",
        "interview",
        "cv_received",
        "updated_at",
    ],
    "roles": [
        "job",
        "position_code",
        "apply_code",
        "status",
        "applications",
        "active_applications",
        "ready_for_review",
        "latest_application_at",
    ],
    "assessments": [
        "candidate",
        "phone",
        "job",
        "status",
        "percent",
        "band",
        "completed_at",
        "updated_at",
    ],
    "interviews": [
        "candidate",
        "phone",
        "candidate_email",
        "job",
        "status",
        "feedback_status",
        "scheduled_start",
        "scheduled_end",
        "invite_sent",
        "updated_at",
    ],
    "followups": [
        "candidate",
        "target_phone",
        "job",
        "followup_type",
        "recommended_action",
        "created_at",
    ],
    "followup_delivery_history": [
        "candidate",
        "target_phone",
        "job",
        "channel",
        "status",
        "error",
        "created_at",
    ],
}

# Export types owned by an optional module, and per-column module ownership inside
# the shared candidates export.
EXPORT_TYPE_MODULES = {
    "assessments": "assessments",
    "interviews": "interviews",
}
CANDIDATE_EXPORT_COLUMN_MODULES = {
    "assessment": "assessments",
    "interview": "interviews",
}

# Canonical human-readable export labels (never raw internal keys).
STAGE_LABELS = {
    "awaiting_cv": "Waiting for CV",
    "cv_processing": "Processing CV",
    "screening": "Screening",
    "screening_complete": "Ready for review",
    "review_pending": "Ready for review",
    "ready_for_review": "Ready for review",
    "shortlisted": "Shortlisted",
    "interview": "Interview",
    "offer_sent": "Offer sent",
    "offer_accepted": "Offer accepted",
    "hired": "Hired",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
    "needs_role": "Needs role",
}

ASSESSMENT_STATE_LABELS = {
    "pending": "Sent",
    "in_progress": "In progress",
    "expired": "Expired",
    "completed": "Completed",
    "cancelled": "Cancelled",
}

REVIEW_LABELS = {"reviewed": "Reviewed", "unreviewed": "Review pending", "notes_pending": "Review pending", "feedback_complete": "Reviewed"}

INTERVIEW_STATE_LABELS = {
    "scheduled": "Scheduled",
    "rescheduled": "Rescheduled",
    "completed": "Completed",
    "no_show": "No-show",
    "cancelled": "Cancelled",
}

DELIVERY_ISSUE_LABELS = {
    "no_usable_conversation_id": "WhatsApp conversation unavailable",
    "missing_candidate_conversation_id": "WhatsApp conversation unavailable",
    "conversation_closed": "WhatsApp conversation inactive",
    "conversation_inactive": "WhatsApp conversation inactive",
    "invalid_grant": "Email account needs reconnecting",
    "gmail_auth": "Email account needs reconnecting",
    "token_expired": "Email account needs reconnecting",
}


def safe_delivery_issue(value):
    text = str(value or "").strip().lower()
    if not text:
        return "Delivery failed"
    for key, label in DELIVERY_ISSUE_LABELS.items():
        if key in text:
            return label
    return "Delivery failed"


BAND_LABELS = {
    "strong": "Strong",
    "qualified": "Qualified",
    "needs_review": "Needs review",
    "low": "Needs review",
    "high": "Strong match",
    "medium": "Moderate match",
    "mixed": "Mixed evidence",
    "development": "Development area",
}

EXPORT_UNITS = {
    "candidates": ("application", "current"),
    "roles": ("role", "current"),
    "assessments": ("attempt", "current"),
    "interviews": ("interview", "current"),
    "followups": ("application", "current"),
    "followup_delivery_history": ("event", "history"),
}


def _label(mapping: dict[str, str], value):
    if value is None or value == "":
        return ""
    return mapping.get(str(value).lower(), str(value).replace("_", " "))


EXPORT_HEADERS_EN: dict[str, list[str]] = {
    "candidates": ["Candidate", "Phone", "Email", "Job", "Stage", "Screening", "Assessment", "Interview", "CV received", "Updated"],
    "roles": ["Job", "Job code", "Apply code", "Status", "Applications", "Active applications", "Ready for review", "Latest application"],
    "assessments": ["Candidate", "Phone", "Job", "Status", "Score percent", "Band", "Completed at", "Updated"],
    "interviews": ["Candidate", "Phone", "Email", "Job", "Status", "Feedback", "Scheduled start", "Scheduled end", "Invite sent", "Updated"],
    "followups": ["Candidate", "Phone", "Job", "Follow-up type", "Recommended action", "Created"],
    "followup_delivery_history": ["Candidate", "Phone", "Job", "Channel", "Status", "Issue", "Created"],
}

EXPORT_HEADERS_AR: dict[str, list[str]] = {
    "candidates": ["المرشح", "الهاتف", "البريد", "الوظيفة", "المرحلة", "الفرز", "التقييم", "المقابلة", "السيرة مستلمة", "آخر تحديث"],
    "roles": ["الوظيفة", "رمز الوظيفة", "رمز التقديم", "الحالة", "الطلبات", "الطلبات النشطة", "جاهز للمراجعة", "آخر طلب"],
    "assessments": ["المرشح", "الهاتف", "الوظيفة", "الحالة", "النسبة", "الشريحة", "اكتمل في", "آخر تحديث"],
    "interviews": ["المرشح", "الهاتف", "البريد", "الوظيفة", "الحالة", "التغذية الراجعة", "بداية الجدولة", "نهاية الجدولة", "دعوة مرسلة", "آخر تحديث"],
    "followups": ["المرشح", "الهاتف", "الوظيفة", "نوع المتابعة", "الإجراء الموصى به", "تاريخ الإنشاء"],
    "followup_delivery_history": ["المرشح", "الهاتف", "الوظيفة", "القناة", "الحالة", "المشكلة", "تاريخ الإنشاء"],
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS report_export_audits (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  actor_user_id text,
  report_type text NOT NULL,
  metric_version text NOT NULL,
  report_stamp text NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  row_count integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_report_export_audits_company
  ON report_export_audits(company_code, created_at DESC);
"""

METRIC_CATALOG: dict[str, dict[str, str]] = {
    "applications": {
        "definition": "Count of production applications with ingested_at in the filter window (optional job filter).",
        "authority": "applications + production_application_predicate",
    },
    "cvs_received": {
        "definition": "Production applications with CV present; clock = COALESCE(cv_received_at::timestamptz, ingested_at) in window.",
        "authority": "applications.cv_received / raw_json->cv",
    },
    "ready_for_review": {
        "definition": "Reviewable applications in READY_FOR_REVIEW_STATUSES (same predicate as Overview action_counts).",
        "authority": "prehire_overview.compute_action_counts / ready_for_review_predicate",
    },
    "shortlisted": {
        "definition": "Reviewable applications currently in status shortlisted (optional job + ingested_at window).",
        "authority": "applications.status",
    },
    "interviews": {
        "definition": "Distinct reviewable applications with at least one candidate_interviews row (optional filters).",
        "authority": "candidate_interviews ⋈ applications",
    },
    "offers": {
        "definition": "Distinct reviewable applications with an employment_offers row in status sent|accepted|approved|pending_approval (open+accepted).",
        "authority": "employment_offers",
    },
    "hires": {
        "definition": "Reviewable applications currently in status hired (optional filters).",
        "authority": "applications.status",
    },
    "followups_needed": {
        "definition": "Distinct reviewable applications with unrecovered failed outbound_delivery_events (same as Overview follow_up_needed).",
        "authority": "prehire_overview.follow_up_needed_exists",
    },
    "followup_delivery_events": {
        "definition": "Count of unrecovered failed outbound_delivery_events for reviewable applications (events, not apps).",
        "authority": "outbound_delivery_events",
    },
    "funnel": {
        "definition": "First-entry counts from application_lifecycle_events / offers; conversion % vs previous step.",
        "authority": "application_lifecycle_events + employment_offers",
    },
    "hiring_speed": {
        "definition": "Mean calendar days between authoritative clocks among apps completing the end event in-window.",
        "authority": "lifecycle events + applications timestamps",
    },
    "ranking_summary": {
        "definition": "Current persisted Ranking run for the selected job only; no rescoring.",
        "authority": "ranking_runs / ranking_run_items",
    },
    "source_summary": {
        "definition": "Application and hire counts by trusted intake buckets only; unknown remains visible.",
        "authority": "applications data_source/intake metadata via trusted bucketizer",
    },
}


class ReportsError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: str | None) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ReportsError("invalid_date", f"invalid date: {raw}") from exc


def normalize_filters(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    position_code: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start and end and end < start:
        raise ReportsError("invalid_date_range", "date_to must be on or after date_from")
    job = str(position_code or "").strip().upper() or None
    return {
        "date_from": start.isoformat() if start else None,
        "date_to": end.isoformat() if end else None,
        "position_code": job,
    }


def trusted_source_bucket(row: dict[str, Any], raw_json: dict[str, Any] | None = None) -> str:
    """Trusted buckets only — never invent campaign labels from free text."""
    blob = raw_json if isinstance(raw_json, dict) else {}
    intake = blob.get("intake") if isinstance(blob.get("intake"), dict) else {}
    import_meta = blob.get("import") if isinstance(blob.get("import"), dict) else {}
    source = str(
        intake.get("source")
        or import_meta.get("source")
        or blob.get("intake_source")
        or blob.get("source")
        or row.get("data_source")
        or ""
    ).strip().lower()
    if any(token in source for token in ("whatsapp", "apply_code", "qr")):
        return "whatsapp"
    if any(token in source for token in ("bulk", "spreadsheet", "csv", "import")):
        return "bulk_import"
    if any(token in source for token in ("email", "mailbox")):
        return "email"
    if any(token in source for token in ("manual", "dashboard", "operator")):
        return "manual"
    return "unknown"


def assert_no_sensitive_columns(columns: Iterable[str]) -> None:
    for col in columns:
        key = re.sub(r"[^a-z0-9_]", "", str(col).strip().lower().replace(" ", "_"))
        if key in SENSITIVE_DENYLIST or any(token in key for token in SENSITIVE_DENYLIST):
            raise ReportsError("sensitive_column_blocked", f"column denied: {col}")


def _production_sql(orch: Any, alias: str = "a") -> str:
    fn = getattr(orch, "production_application_predicate", None)
    if callable(fn):
        return fn(alias)
    return (
        f"COALESCE({alias}.data_source, {alias}.raw_json->>'data_source', 'production') = 'production' "
        f"AND COALESCE({alias}.status, '') NOT IN ('needs_role','import_review','import_archived')"
    )


def _reviewable_sql(orch: Any, alias: str = "a") -> str:
    fn = getattr(orch, "reviewable_application_predicate", None)
    if callable(fn):
        return fn(alias)
    return (
        f"{_production_sql(orch, alias)} "
        f"AND ({alias}.cv_received IS TRUE OR jsonb_typeof({alias}.raw_json->'cv') = 'object')"
    )


def _filter_sql(
    alias: str,
    filters: dict[str, Any],
    *,
    clock_expr: str,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("position_code"):
        clauses.append(f"upper({alias}.position_code)=%s")
        params.append(filters["position_code"])
    if filters.get("date_from"):
        clauses.append(f"({clock_expr})::date >= %s::date")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append(f"({clock_expr})::date <= %s::date")
        params.append(filters["date_to"])
    if not clauses:
        return "TRUE", []
    return " AND ".join(clauses), params


def _avg_days(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


OPTIONAL_REPORT_MODULES = ("assessments", "interviews", "employment_offers")


def resolve_report_modules(
    orch: Any,
    company: str,
    *,
    assessments_enabled: bool | None = None,
    interviews_enabled: bool | None = None,
    offers_enabled: bool | None = None,
) -> dict[str, bool]:
    """Optional-module state that decides what Reports may mention at all."""
    requested = {
        "assessments": assessments_enabled,
        "interviews": interviews_enabled,
        "employment_offers": offers_enabled,
    }
    checker = getattr(orch, "company_has_module", None)
    resolved: dict[str, bool] = {}
    for key in OPTIONAL_REPORT_MODULES:
        value = requested[key]
        if value is None:
            resolved[key] = bool(checker(company, key)) if callable(checker) else True
        else:
            resolved[key] = bool(value)
    return resolved


def build_reports_v1_payload(
    orch: Any,
    *,
    company_code: str,
    date_from: str | None = None,
    date_to: str | None = None,
    position_code: str | None = None,
    locale: str = "en",
    assessments_enabled: bool | None = None,
    interviews_enabled: bool | None = None,
    offers_enabled: bool | None = None,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    if not company:
        raise ReportsError("tenant_scope_required")
    modules = resolve_report_modules(
        orch,
        company,
        assessments_enabled=assessments_enabled,
        interviews_enabled=interviews_enabled,
        offers_enabled=offers_enabled,
    )
    assessments_enabled = modules["assessments"]
    interviews_enabled = modules["interviews"]
    offers_enabled = modules["employment_offers"]
    filters = normalize_filters(date_from=date_from, date_to=date_to, position_code=position_code)
    stamp = f"rpt_{_now().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    production = _production_sql(orch, "a")
    reviewable = _reviewable_sql(orch, "a")
    ingest_filter, ingest_params = _filter_sql("a", filters, clock_expr="a.ingested_at")
    cv_clock = "COALESCE(a.cv_received_at::timestamptz, a.ingested_at)"
    cv_filter, cv_params = _filter_sql("a", filters, clock_expr=cv_clock)

    overview = __import__("prehire_overview")
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)

            # --- summary cards ---
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {production} AND {ingest_filter}
                """,
                (company, *ingest_params),
            )
            applications = int((cur.fetchone() or {}).get("n") or 0)

            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {production}
                  AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object')
                  AND {cv_filter}
                """,
                (company, *cv_params),
            )
            cvs_received = int((cur.fetchone() or {}).get("n") or 0)

            # Overview parity path when unfiltered; same predicates + filters otherwise.
            if not filters.get("date_from") and not filters.get("date_to") and not filters.get("position_code"):
                action_counts = overview.compute_action_counts(
                    company=company,
                    db_connect=orch.db_connect,
                    assessments_enabled=assessments_enabled,
                )
                ready_for_review = int(action_counts.get("ready_for_review") or 0)
                followups_needed = int(action_counts.get("follow_up_needed") or 0)
                overview_parity = True
            else:
                cur.execute(
                    f"""
                    SELECT
                      COUNT(*) FILTER (WHERE {overview.ready_for_review_predicate("a")}) AS ready_for_review,
                      COUNT(*) FILTER (WHERE {overview.follow_up_needed_exists("a")}) AS follow_up_needed
                    FROM applications a
                    WHERE a.company_code=%s AND {reviewable} AND {ingest_filter}
                    """,
                    (company, *ingest_params),
                )
                row = cur.fetchone() or {}
                ready_for_review = int(row.get("ready_for_review") or 0)
                followups_needed = int(row.get("follow_up_needed") or 0)
                overview_parity = False

            assessment_rows = 0
            assessment_status: list[dict[str, Any]] = []
            if assessments_enabled:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM assessment_attempts aa
                    JOIN applications a ON a.company_code=aa.company_code AND a.app_key=aa.app_key
                    WHERE aa.company_code=%s AND {reviewable} AND {ingest_filter}
                    """,
                    (company, *ingest_params),
                )
                assessment_rows = int((cur.fetchone() or {}).get("n") or 0)
                cur.execute(
                    f"""
                    SELECT aa.status, COUNT(*) AS count
                    FROM assessment_attempts aa
                    JOIN applications a ON a.company_code=aa.company_code AND a.app_key=aa.app_key
                    WHERE aa.company_code=%s AND {reviewable} AND {ingest_filter}
                    GROUP BY aa.status
                    ORDER BY count DESC, aa.status
                    """,
                    (company, *ingest_params),
                )
                assessment_status = [
                    {"label": str(row.get("status") or ""), "status": str(row.get("status") or ""), "count": int(row.get("count") or 0)}
                    for row in cur.fetchall()
                ]

            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {reviewable} AND upper(COALESCE(a.status,''))='SHORTLISTED'
                  AND {ingest_filter}
                """,
                (company, *ingest_params),
            )
            shortlisted = int((cur.fetchone() or {}).get("n") or 0)

            interviews = 0
            if interviews_enabled:
                cur.execute(
                    f"""
                    SELECT COUNT(DISTINCT a.app_key) AS n
                    FROM applications a
                    JOIN candidate_interviews ci ON ci.company_code=a.company_code AND ci.app_key=a.app_key
                    WHERE a.company_code=%s AND {reviewable} AND {ingest_filter}
                    """,
                    (company, *ingest_params),
                )
                interviews = int((cur.fetchone() or {}).get("n") or 0)

            offers = 0
            if offers_enabled:
                cur.execute(
                    f"""
                    SELECT COUNT(DISTINCT a.app_key) AS n
                    FROM applications a
                    JOIN employment_offers eo ON eo.company_code=a.company_code AND eo.app_key=a.app_key
                    WHERE a.company_code=%s AND {reviewable}
                      AND eo.status IN ('sent','accepted','approved','pending_approval')
                      AND {ingest_filter}
                    """,
                    (company, *ingest_params),
                )
                offers = int((cur.fetchone() or {}).get("n") or 0)

            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {reviewable} AND upper(COALESCE(a.status,''))='HIRED'
                  AND {ingest_filter}
                """,
                (company, *ingest_params),
            )
            hires = int((cur.fetchone() or {}).get("n") or 0)

            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM outbound_delivery_events ode
                JOIN applications a ON a.app_key=ode.subject_key
                WHERE a.company_code=%s AND {reviewable}
                  AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
                  AND ode.recovered_at IS NULL
                  AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                  AND {ingest_filter}
                """,
                (company, *ingest_params),
            )
            followup_events = int((cur.fetchone() or {}).get("n") or 0)

            # --- funnel first-entry ---
            funnel_rows = _compute_funnel(
                cur, company=company, reviewable=reviewable, filters=filters, modules=modules
            )

            # --- hiring speed ---
            speed = _compute_hiring_speed(
                cur, company=company, reviewable=reviewable, filters=filters, modules=modules
            )

            # --- source summary ---
            source_summary = _compute_source_summary(cur, company=company, production=production, filters=filters)

    ranking_summary = None
    if filters.get("position_code"):
        ranking_summary = _ranking_summary(orch, company_code=company, position_code=filters["position_code"])

    locale_key = "ar" if str(locale).lower().startswith("ar") else "en"
    if locale_key == "ar":
        for row in funnel_rows:
            row["label"] = FUNNEL_LABELS_AR.get(str(row.get("key") or ""), row.get("label") or "")
        for row in source_summary:
            src = str(row.get("source") or "unknown")
            row["label"] = SOURCE_LABELS_AR.get(src, SOURCE_LABELS_EN.get(src, src))
    else:
        for row in source_summary:
            src = str(row.get("source") or "unknown")
            row["label"] = SOURCE_LABELS_EN.get(src, src)

    return {
        "ok": True,
        "company_code": company,
        "metric_version": METRIC_VERSION,
        "report_stamp": stamp,
        "generated_at": _now().isoformat(),
        "locale": locale_key,
        "filters": filters,
        "overview_parity_unfiltered": overview_parity,
        "clock_label": "calendar_elapsed_days",
        "advisory": True,
        "hr_decides": True,
        "summary": {
            "applications": applications,
            "cvs_received": cvs_received,
            "ready_for_review": ready_for_review,
            "shortlisted": shortlisted,
            **({"interviews": interviews} if interviews_enabled else {}),
            **({"offers": offers} if offers_enabled else {}),
            "hires": hires,
            "followups_needed": followups_needed,
            "followup_delivery_events": followup_events,
            # Legacy aliases for older clients / smoke tests
            "cv_received": cvs_received,
            "followups": followups_needed,
        },
        "funnel": funnel_rows,
        "hiring_speed": speed,
        "ranking_summary": ranking_summary,
        "source_summary": source_summary,
        "metric_catalog": metric_catalog_for(modules),
        "exports": {
            "types": export_types_for(modules),
            "privacy_denylist_version": "reports-denylist-v1",
            "candidate_rows": cvs_received,
            "role_rows": 0,
            **({"interview_rows": interviews} if interviews_enabled else {}),
            "followup_rows": followup_events,
            **({"assessment_rows": assessment_rows} if assessments_enabled else {}),
        },
        "assessments_enabled": assessments_enabled,
        "interviews_enabled": interviews_enabled,
        "offers_enabled": offers_enabled,
        # Backward-compatible keys for older UI during transition
        "breakdowns": {
            "applications_by_stage": [{"label": s["label"], "count": s["count"]} for s in funnel_rows],
            "followups_by_type": [],
            "candidates_by_role": [],
            **({"interview_status": []} if interviews_enabled else {}),
            **({"assessment_status": assessment_status} if assessments_enabled else {}),
        },
    }


def _all_modules_on() -> dict[str, bool]:
    return {key: True for key in OPTIONAL_REPORT_MODULES}


def export_types_for(modules: dict[str, bool]) -> list[str]:
    return [
        key
        for key in EXPORT_COLUMNS.keys()
        if modules.get(EXPORT_TYPE_MODULES.get(key, ""), True)
    ]


def metric_catalog_for(modules: dict[str, bool]) -> dict[str, dict[str, str]]:
    omit: set[str] = set()
    if not modules.get("interviews", True):
        omit.add("interviews")
    if not modules.get("employment_offers", True):
        omit.add("offers")
    return {key: value for key, value in METRIC_CATALOG.items() if key not in omit}


def _compute_funnel(
    cur: Any,
    *,
    company: str,
    reviewable: str,
    filters: dict[str, Any],
    modules: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    modules = modules or _all_modules_on()
    job_clause = ""
    params: list[Any] = [company]
    if filters.get("position_code"):
        job_clause = " AND upper(a.position_code)=%s"
        params.append(filters["position_code"])

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")

    def _in_window(ts_expr: str) -> tuple[str, list[Any]]:
        clauses = []
        p: list[Any] = []
        if date_from:
            clauses.append(f"({ts_expr})::date >= %s::date")
            p.append(date_from)
        if date_to:
            clauses.append(f"({ts_expr})::date <= %s::date")
            p.append(date_to)
        if not clauses:
            return "TRUE", []
        return " AND ".join(clauses), p

    # Lifecycle first entries
    window_sql, window_params = _in_window("fe.first_entered_at")
    cur.execute(
        f"""
        WITH first_entry AS (
          SELECT e.app_key, e.to_stage, MIN(e.created_at) AS first_entered_at
          FROM application_lifecycle_events e
          JOIN applications a ON a.company_code=e.company_code AND a.app_key=e.app_key
          WHERE e.company_code=%s AND {reviewable} {job_clause}
            AND e.to_stage IN ('cv_processing','ready_for_review','shortlisted','interview','hired')
          GROUP BY e.app_key, e.to_stage
        )
        SELECT to_stage, COUNT(*) AS n
        FROM first_entry fe
        WHERE {window_sql}
        GROUP BY to_stage
        """,
        (*params, *window_params),
    )
    life = {str(r["to_stage"]): int(r["n"] or 0) for r in cur.fetchall()}

    # CV received: prefer lifecycle cv_processing; also include apps with CV and no event yet via COALESCE clock
    cv_window, cv_params = _in_window("COALESCE(fe.first_entered_at, a.cv_received_at::timestamptz, a.ingested_at)")
    cur.execute(
        f"""
        WITH first_cv AS (
          SELECT a.app_key, MIN(e.created_at) AS first_entered_at
          FROM applications a
          LEFT JOIN application_lifecycle_events e
            ON e.company_code=a.company_code AND e.app_key=a.app_key AND e.to_stage='cv_processing'
          WHERE a.company_code=%s AND {reviewable} {job_clause}
            AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object' OR e.app_key IS NOT NULL)
          GROUP BY a.app_key
        )
        SELECT COUNT(*) AS n
        FROM first_cv fe
        JOIN applications a ON a.app_key=fe.app_key
        WHERE a.company_code=%s AND {cv_window}
        """,
        (*params, company, *cv_params),
    )
    cv_received = int((cur.fetchone() or {}).get("n") or 0)

    # Offers first sent / accepted
    offer_sent = 0
    offer_accepted = 0
    if modules.get("employment_offers", True):
        offer_window, offer_params = _in_window("fe.first_at")
        cur.execute(
            f"""
            WITH first_sent AS (
              SELECT eo.app_key, MIN(COALESCE(eo.sent_at, eo.updated_at, eo.created_at)) AS first_at
              FROM employment_offers eo
              JOIN applications a ON a.company_code=eo.company_code AND a.app_key=eo.app_key
              WHERE eo.company_code=%s AND {reviewable} {job_clause}
                AND (eo.status IN ('sent','accepted','declined','expired','withdrawn') OR eo.sent_at IS NOT NULL)
              GROUP BY eo.app_key
            )
            SELECT COUNT(*) AS n FROM first_sent fe WHERE {offer_window}
            """,
            (*params, *offer_params),
        )
        offer_sent = int((cur.fetchone() or {}).get("n") or 0)

        cur.execute(
            f"""
            WITH first_acc AS (
              SELECT eo.app_key, MIN(COALESCE(eo.responded_at, eo.updated_at, eo.created_at)) AS first_at
              FROM employment_offers eo
              JOIN applications a ON a.company_code=eo.company_code AND a.app_key=eo.app_key
              WHERE eo.company_code=%s AND {reviewable} {job_clause} AND eo.status='accepted'
              GROUP BY eo.app_key
            )
            SELECT COUNT(*) AS n FROM first_acc fe WHERE {offer_window}
            """,
            (*params, *offer_params),
        )
        offer_accepted = int((cur.fetchone() or {}).get("n") or 0)

    counts = {
        "cv_received": cv_received,
        "ready_for_review": int(life.get("ready_for_review") or 0),
        "shortlisted": int(life.get("shortlisted") or 0),
        "interview": int(life.get("interview") or 0),
        "offer_sent": offer_sent,
        "offer_accepted": offer_accepted,
        "hired": int(life.get("hired") or 0),
    }

    rows: list[dict[str, Any]] = []
    prev: int | None = None
    for key, label in FUNNEL_STEPS:
        if not modules.get(FUNNEL_STEP_MODULES.get(key, ""), True):
            continue
        n = int(counts.get(key) or 0)
        conversion = None
        if prev is not None and prev > 0:
            conversion = round((n / prev) * 100.0, 1)
        elif prev == 0:
            conversion = 0.0
        rows.append(
            {
                "key": key,
                "label": label,
                "count": n,
                "conversion_from_previous_pct": conversion,
            }
        )
        prev = n
    return rows


def _compute_hiring_speed(
    cur: Any,
    *,
    company: str,
    reviewable: str,
    filters: dict[str, Any],
    modules: dict[str, bool] | None = None,
) -> dict[str, Any]:
    modules = modules or _all_modules_on()
    job_clause = ""
    params: list[Any] = [company]
    if filters.get("position_code"):
        job_clause = " AND upper(a.position_code)=%s"
        params.append(filters["position_code"])

    def window(alias_ts: str) -> tuple[str, list[Any]]:
        clauses = []
        p: list[Any] = []
        if filters.get("date_from"):
            clauses.append(f"({alias_ts})::date >= %s::date")
            p.append(filters["date_from"])
        if filters.get("date_to"):
            clauses.append(f"({alias_ts})::date <= %s::date")
            p.append(filters["date_to"])
        return (" AND ".join(clauses) if clauses else "TRUE"), p

    # start clock: COALESCE(cv_received_at, ingested_at)
    start_expr = "COALESCE(a.cv_received_at::timestamptz, a.ingested_at)"

    # time to first review
    w, wp = window("r.first_review")
    cur.execute(
        f"""
        WITH first_review AS (
          SELECT e.app_key, MIN(e.created_at) AS first_review
          FROM application_lifecycle_events e
          JOIN applications a ON a.company_code=e.company_code AND a.app_key=e.app_key
          WHERE e.company_code=%s AND {reviewable} {job_clause} AND e.to_stage='ready_for_review'
          GROUP BY e.app_key
        )
        SELECT EXTRACT(EPOCH FROM (r.first_review - {start_expr})) / 86400.0 AS days
        FROM first_review r
        JOIN applications a ON a.app_key=r.app_key
        WHERE a.company_code=%s AND {w} AND {start_expr} IS NOT NULL AND r.first_review >= {start_expr}
        """,
        (*params, company, *wp),
    )
    to_review = [float(r["days"]) for r in cur.fetchall() if r.get("days") is not None]

    to_interview: list[float] = []
    if modules.get("interviews", True):
        w, wp = window("i.first_interview")
        cur.execute(
            f"""
            WITH first_interview AS (
              SELECT e.app_key, MIN(e.created_at) AS first_interview
              FROM application_lifecycle_events e
              JOIN applications a ON a.company_code=e.company_code AND a.app_key=e.app_key
              WHERE e.company_code=%s AND {reviewable} {job_clause} AND e.to_stage='interview'
              GROUP BY e.app_key
            )
            SELECT EXTRACT(EPOCH FROM (i.first_interview - {start_expr})) / 86400.0 AS days
            FROM first_interview i
            JOIN applications a ON a.app_key=i.app_key
            WHERE a.company_code=%s AND {w} AND {start_expr} IS NOT NULL AND i.first_interview >= {start_expr}
            """,
            (*params, company, *wp),
        )
        to_interview = [float(r["days"]) for r in cur.fetchall() if r.get("days") is not None]

    w, wp = window("h.first_hired")
    cur.execute(
        f"""
        WITH first_hired AS (
          SELECT e.app_key, MIN(e.created_at) AS first_hired
          FROM application_lifecycle_events e
          JOIN applications a ON a.company_code=e.company_code AND a.app_key=e.app_key
          WHERE e.company_code=%s AND {reviewable} {job_clause} AND e.to_stage='hired'
          GROUP BY e.app_key
        )
        SELECT EXTRACT(EPOCH FROM (h.first_hired - {start_expr})) / 86400.0 AS days
        FROM first_hired h
        JOIN applications a ON a.app_key=h.app_key
        WHERE a.company_code=%s AND {w} AND {start_expr} IS NOT NULL AND h.first_hired >= {start_expr}
        """,
        (*params, company, *wp),
    )
    to_hire = [float(r["days"]) for r in cur.fetchall() if r.get("days") is not None]

    interviews_on = bool(modules.get("interviews", True))
    return {
        "unit": "calendar_days",
        "label": "Calendar elapsed time (not business days)",
        "avg_days_to_first_review": _avg_days(to_review),
        **({"avg_days_to_interview": _avg_days(to_interview)} if interviews_on else {}),
        "avg_days_to_hire": _avg_days(to_hire),
        "sample_sizes": {
            "first_review": len(to_review),
            **({"interview": len(to_interview)} if interviews_on else {}),
            "hire": len(to_hire),
        },
        "start_clock": "COALESCE(cv_received_at, ingested_at)",
    }


def _compute_source_summary(cur: Any, *, company: str, production: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
    ingest_filter, ingest_params = _filter_sql("a", filters, clock_expr="a.ingested_at")
    cur.execute(
        f"""
        SELECT
          a.app_key,
          a.status,
          a.data_source,
          a.raw_json
        FROM applications a
        WHERE a.company_code=%s AND {production} AND {ingest_filter}
        """,
        (company, *ingest_params),
    )
    tallies: dict[str, dict[str, int]] = {b: {"applications": 0, "hires": 0} for b in TRUSTED_SOURCE_BUCKETS}
    for row in cur.fetchall():
        raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
        bucket = trusted_source_bucket(dict(row), raw)
        if bucket not in tallies:
            bucket = "unknown"
        tallies[bucket]["applications"] += 1
        if str(row.get("status") or "").lower() == "hired":
            tallies[bucket]["hires"] += 1
    return [
        {"source": key, "applications": vals["applications"], "hires": vals["hires"]}
        for key, vals in tallies.items()
        if vals["applications"] or vals["hires"] or key == "unknown"
    ]


def _ranking_summary(orch: Any, *, company_code: str, position_code: str) -> dict[str, Any]:
    try:
        import candidate_ranking as cr
    except Exception as exc:
        return {"available": False, "error": f"ranking_import_failed:{exc}", "hr_decides": True, "advisory": True}
    try:
        run = cr.current_run(orch, company_code=company_code, position_code=position_code)
    except Exception as exc:
        return {"available": False, "error": str(exc), "hr_decides": True, "advisory": True}
    if not run:
        return {
            "available": False,
            "position_code": position_code,
            "message": "No current Ranking run for this job.",
            "hr_decides": True,
            "advisory": True,
        }
    items = list(run.get("items") or [])
    buckets = {"eligible": 0, "requirement_not_met": 0, "insufficient_information": 0, "criteria_not_evaluated": 0}
    for item in items:
        key = str(item.get("eligibility_bucket") or "criteria_not_evaluated")
        if key not in buckets:
            key = "criteria_not_evaluated"
        buckets[key] += 1
    return {
        "available": True,
        "position_code": position_code,
        "run_id": str(run.get("run_id")),
        "pool_total": int(run.get("pool_total") or len(items)),
        "eligible": int(run.get("eligible_count") or buckets["eligible"]),
        "requirement_not_met": int(run.get("not_met_count") or buckets["requirement_not_met"]),
        "unknown": int(run.get("unknown_count") or buckets["insufficient_information"]),
        "criteria_not_evaluated": buckets["criteria_not_evaluated"],
        "stale": bool(run.get("stale_reason")) or not bool(run.get("is_current")),
        "stale_reason": run.get("stale_reason"),
        "scoring_config_version": run.get("scoring_config_version"),
        "denylist_version": run.get("denylist_version"),
        "advisory": True,
        "hr_decides": True,
        "message": "Ranking is advisory. HR decides.",
    }


def _modules_from_flags(assessments_enabled: bool, interviews_enabled: bool) -> dict[str, bool]:
    return {
        "assessments": bool(assessments_enabled),
        "interviews": bool(interviews_enabled),
        "employment_offers": True,
    }


def _assert_export_type_enabled(report_type: str, modules: dict[str, bool]) -> None:
    owner = EXPORT_TYPE_MODULES.get(report_type)
    if owner and not modules.get(owner, True):
        raise ReportsError(f"{owner}_module_disabled")


def _omitted_candidate_columns(modules: dict[str, bool]) -> set[str]:
    return {
        column
        for column, owner in CANDIDATE_EXPORT_COLUMN_MODULES.items()
        if not modules.get(owner, True)
    }


def export_headers(
    report_type: str,
    *,
    locale: str = "en",
    assessments_enabled: bool = True,
    interviews_enabled: bool = True,
) -> list[str]:
    key = "ar" if str(locale).lower().startswith("ar") else "en"
    mapping = EXPORT_HEADERS_AR if key == "ar" else EXPORT_HEADERS_EN
    modules = _modules_from_flags(assessments_enabled, interviews_enabled)
    _assert_export_type_enabled(report_type, modules)
    headers = list(mapping.get(report_type) or [])
    if not headers:
        raise ReportsError("unknown_report_type")
    columns = list(EXPORT_COLUMNS[report_type])
    if report_type == "candidates":
        # Drop columns whose module is off, keeping headers aligned to columns.
        for column in _omitted_candidate_columns(modules):
            if column in columns:
                index = columns.index(column)
                columns.pop(index)
                headers.pop(index)
    assert_no_sensitive_columns(columns)
    return headers


def export_columns_for(
    report_type: str,
    *,
    assessments_enabled: bool = True,
    interviews_enabled: bool = True,
) -> list[str]:
    columns = list(EXPORT_COLUMNS.get(report_type) or [])
    if not columns:
        raise ReportsError("unknown_report_type")
    modules = _modules_from_flags(assessments_enabled, interviews_enabled)
    _assert_export_type_enabled(report_type, modules)
    if report_type == "candidates":
        omitted = _omitted_candidate_columns(modules)
        columns = [col for col in columns if col not in omitted]
    return columns


def iter_export_rows(
    orch: Any,
    *,
    company_code: str,
    report_type: str,
    filters: dict[str, Any],
    assessments_enabled: bool | None = None,
    interviews_enabled: bool | None = None,
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
    jobs_visibility_sql: str | None = None,
    jobs_visibility_params: list[Any] | None = None,
) -> Iterable[list[Any]]:
    if report_type not in EXPORT_COLUMNS:
        raise ReportsError("unknown_report_type")
    resolved = resolve_report_modules(
        orch,
        str(company_code or "").strip().upper(),
        assessments_enabled=assessments_enabled,
        interviews_enabled=interviews_enabled,
        offers_enabled=True,
    )
    assessments_enabled = resolved["assessments"]
    interviews_enabled = resolved["interviews"]
    _assert_export_type_enabled(report_type, resolved)
    cols = export_columns_for(
        report_type,
        assessments_enabled=assessments_enabled,
        interviews_enabled=interviews_enabled,
    )
    assert_no_sensitive_columns(cols)
    company = str(company_code).strip().upper()
    reviewable = _reviewable_sql(orch, "a")
    ingest_filter, ingest_params = _filter_sql("a", filters, clock_expr="a.ingested_at")
    vis = str(visibility_sql or "").strip()
    vis_clause = f" AND ({vis})" if vis else ""
    vis_params = list(visibility_params or [])
    job_vis = str(jobs_visibility_sql or "").strip()
    job_params = list(jobs_visibility_params or [])

    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if report_type == "candidates":
                select_parts = [
                    "COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.raw_json->>'name', a.phone) AS candidate",
                    "a.phone",
                    "c.email",
                    "COALESCE(NULLIF(a.position_title, ''), a.position_code) AS job",
                    "a.status",
                    "COALESCE(a.screening_status, a.raw_json->'screening'->>'status') AS screening",
                ]
                join_parts: list[str] = ["LEFT JOIN candidates c ON c.phone=a.phone"]
                if assessments_enabled:
                    select_parts.append("la.status AS assessment")
                    join_parts.append(
                        "LEFT JOIN LATERAL ("
                        " SELECT aa.status FROM assessment_attempts aa"
                        " WHERE aa.company_code=a.company_code AND aa.app_key=a.app_key"
                        " ORDER BY aa.updated_at DESC LIMIT 1"
                        ") la ON TRUE"
                    )
                if interviews_enabled:
                    select_parts.append("li.status AS interview")
                    join_parts.append(
                        "LEFT JOIN LATERAL ("
                        " SELECT ci.status FROM candidate_interviews ci"
                        " WHERE ci.company_code=a.company_code AND ci.app_key=a.app_key"
                        " ORDER BY ci.scheduled_start DESC NULLS LAST LIMIT 1"
                        ") li ON TRUE"
                    )
                select_parts.append(
                    "CASE WHEN a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object'"
                    " THEN 'Yes' ELSE 'No' END AS cv_received"
                )
                select_parts.append("a.updated_at")
                cur.execute(
                    f"""
                    SELECT {', '.join(select_parts)}
                    FROM applications a
                    {' '.join(join_parts)}
                    WHERE a.company_code=%s AND {reviewable} AND {ingest_filter}{vis_clause}
                    ORDER BY a.updated_at DESC NULLS LAST
                    """,
                    (company, *ingest_params, *vis_params),
                )
            elif report_type == "roles":
                import jobs_queue_contract as _jobs_contract

                _roles_effective_status = _jobs_contract.effective_job_status_sql("p.status")
                positions_ok = job_vis if job_vis else "TRUE"
                cur.execute(
                    f"""
                    WITH app_stats AS (
                      SELECT
                        a.position_code,
                        COALESCE(MAX(a.position_title), a.position_code) AS position_title,
                        COUNT(*) AS application_count,
                        COUNT(*) FILTER (WHERE {_jobs_contract.active_pipeline_predicate("a")}) AS active_count,
                        COUNT(*) FILTER (WHERE upper(COALESCE(a.status,'')) IN ('READY_FOR_REVIEW','SCREENING_COMPLETE','REVIEW_PENDING')) AS ready_for_review,
                        MAX(a.updated_at) AS latest_application_at
                      FROM applications a
                      WHERE a.company_code=%s AND {reviewable} AND {ingest_filter}{vis_clause}
                      GROUP BY a.position_code
                    )
                    SELECT
                      COALESCE(p.title, s.position_title, p.position_code, s.position_code) AS job,
                      COALESCE(p.position_code, s.position_code) AS position_code,
                      p.apply_code,
                      CASE
                        WHEN p.position_code IS NOT NULL THEN {_roles_effective_status}
                        WHEN COALESCE(s.active_count,0) > 0 THEN 'open'
                        ELSE 'closed'
                      END AS status,
                      COALESCE(s.application_count,0) AS applications,
                      COALESCE(s.active_count,0) AS active_applications,
                      COALESCE(s.ready_for_review,0) AS ready_for_review,
                      s.latest_application_at
                    FROM positions p
                    FULL OUTER JOIN app_stats s ON s.position_code=p.position_code
                    WHERE COALESCE(p.company_code, %s)=%s
                      AND (%s::text IS NULL OR upper(COALESCE(p.position_code, s.position_code))=%s)
                      AND (
                        (p.position_code IS NOT NULL AND ({positions_ok}))
                        OR (p.position_code IS NULL AND s.position_code IS NOT NULL)
                      )
                    ORDER BY active_applications DESC, applications DESC, job
                    """,
                    (
                        company,
                        *ingest_params,
                        *vis_params,
                        company,
                        company,
                        filters.get("position_code"),
                        filters.get("position_code"),
                        *job_params,
                    ),
                )
            elif report_type == "assessments":
                cur.execute(
                    f"""
                    SELECT
                      COALESCE(aa.candidate_name, NULLIF(c.name,''), a.raw_json->>'candidate_name', aa.phone) AS candidate,
                      aa.phone,
                      COALESCE(NULLIF(aa.position_title,''), aa.position_code, a.position_title, a.position_code) AS job,
                      aa.status,
                      s.percent,
                      s.band,
                      aa.completed_at,
                      aa.updated_at
                    FROM assessment_attempts aa
                    JOIN applications a ON a.company_code=aa.company_code AND a.app_key=aa.app_key
                    LEFT JOIN candidates c ON c.phone=aa.phone
                    LEFT JOIN assessment_scores s ON s.attempt_id=aa.attempt_id
                    WHERE aa.company_code=%s AND {reviewable} AND {ingest_filter}{vis_clause}
                    ORDER BY aa.updated_at DESC
                    """,
                    (company, *ingest_params, *vis_params),
                )
            elif report_type == "interviews":
                cur.execute(
                    f"""
                    SELECT
                      COALESCE(ci.candidate_name, NULLIF(c.name,''), a.raw_json->>'candidate_name', ci.phone) AS candidate,
                      ci.phone,
                      ci.candidate_email,
                      COALESCE(NULLIF(ci.position_title,''), ci.position_code, a.position_title, a.position_code) AS job,
                      ci.status,
                      ci.feedback_status,
                      ci.scheduled_start,
                      ci.scheduled_end,
                      CASE WHEN ci.candidate_notified OR ci.candidate_invited OR ci.calendar_invite_sent THEN 'Yes' ELSE 'No' END AS invite_sent,
                      ci.updated_at
                    FROM candidate_interviews ci
                    JOIN applications a ON a.company_code=ci.company_code AND a.app_key=ci.app_key
                    LEFT JOIN candidates c ON c.phone=ci.phone
                    WHERE ci.company_code=%s AND {reviewable} AND {ingest_filter}{vis_clause}
                    ORDER BY ci.scheduled_start DESC NULLS LAST
                    """,
                    (company, *ingest_params, *vis_params),
                )
            elif report_type == "followups":
                import prehire_overview as _po

                follow_pred = _po.follow_up_needed_exists("a")
                cur.execute(
                    f"""
                    SELECT DISTINCT ON (a.app_key)
                      COALESCE(NULLIF(c.name,''), a.raw_json->>'candidate_name', a.phone) AS candidate,
                      ode.target_phone,
                      COALESCE(NULLIF(a.position_title,''), a.position_code) AS job,
                      CASE
                        WHEN ode.last_error='conversation_closed' THEN 'Contact candidate'
                        WHEN ode.last_error='conversation_inactive' THEN 'Follow up with candidate'
                        WHEN ode.last_error IN ('missing_candidate_conversation_id','no_usable_conversation_id') THEN 'Needs contact review'
                        WHEN ode.status='failed' THEN 'Needs follow-up'
                        ELSE COALESCE(NULLIF(ode.status,''), 'Needs HR attention')
                      END AS followup_type,
                      CASE
                        WHEN ode.last_error='conversation_closed' THEN 'Contact the candidate or choose the best contact method.'
                        WHEN ode.last_error='conversation_inactive' THEN 'Follow up with the candidate.'
                        WHEN ode.last_error IN ('missing_candidate_conversation_id','no_usable_conversation_id') THEN 'Review the candidate phone or email before contacting them.'
                        WHEN ode.status='failed' THEN 'Try another contact method.'
                        ELSE 'Needs HR attention.'
                      END AS recommended_action,
                      ode.created_at
                    FROM applications a
                    LEFT JOIN LATERAL (
                      SELECT ode.target_phone, ode.status, ode.last_error, ode.created_at
                      FROM outbound_delivery_events ode
                      WHERE ode.company_code=a.company_code AND ode.subject_key=a.app_key
                        AND COALESCE(ode.status,'') NOT IN ('sent','recovered')
                        AND ode.recovered_at IS NULL
                        AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                      ORDER BY ode.created_at DESC
                      LIMIT 1
                    ) ode ON TRUE
                    LEFT JOIN candidates c ON c.phone=a.phone
                    WHERE a.company_code=%s AND {reviewable} AND {ingest_filter}{vis_clause}
                      AND {follow_pred}
                    ORDER BY a.app_key, ode.created_at DESC NULLS LAST
                    """,
                    (company, *ingest_params, *vis_params),
                )
            elif report_type == "followup_delivery_history":
                cur.execute(
                    f"""
                    SELECT
                      COALESCE(NULLIF(c.name,''), a.raw_json->>'candidate_name', a.phone) AS candidate,
                      ode.target_phone,
                      COALESCE(NULLIF(a.position_title,''), a.position_code) AS job,
                      COALESCE(ode.channel, 'message') AS channel,
                      ode.status,
                      COALESCE(ode.last_error, '') AS error,
                      ode.created_at
                    FROM outbound_delivery_events ode
                    JOIN applications a ON a.app_key=ode.subject_key AND a.company_code=ode.company_code
                    LEFT JOIN candidates c ON c.phone=a.phone
                    WHERE a.company_code=%s AND {reviewable} AND {ingest_filter}{vis_clause}
                      AND COALESCE(ode.status,'') NOT IN ('sent','recovered')
                      AND ode.recovered_at IS NULL
                      AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                    ORDER BY ode.created_at DESC
                    """,
                    (company, *ingest_params, *vis_params),
                )
            else:
                raise ReportsError("unknown_report_type")

            for row in cur.fetchall():
                payload = dict(row)
                # Privacy scrub
                for denied in SENSITIVE_DENYLIST:
                    payload.pop(denied, None)
                if report_type == "candidates":
                    payload["status"] = _label(STAGE_LABELS, payload.get("status"))
                    payload["screening"] = "Complete" if str(payload.get("screening") or "").lower() in {"complete", "completed"} else _label(STAGE_LABELS, payload.get("screening"))
                    if "assessment" in payload:
                        payload["assessment"] = _label(ASSESSMENT_STATE_LABELS, payload.get("assessment"))
                    if "interview" in payload:
                        payload["interview"] = _label(INTERVIEW_STATE_LABELS, payload.get("interview"))
                elif report_type == "roles":
                    payload["status"] = "Open" if str(payload.get("status") or "").lower() in {"open", "active", "published", "has_applications"} else "Closed"
                elif report_type == "assessments":
                    payload["status"] = _label(ASSESSMENT_STATE_LABELS, payload.get("status"))
                    payload["band"] = _label(BAND_LABELS, payload.get("band"))
                elif report_type == "interviews":
                    payload["status"] = _label(INTERVIEW_STATE_LABELS, payload.get("status"))
                    payload["feedback_status"] = _label(REVIEW_LABELS, payload.get("feedback_status"))
                elif report_type == "followup_delivery_history":
                    payload["status"] = _label({"failed": "Failed", "sent": "Sent", "queued": "Queued"}, payload.get("status"))
                    payload["error"] = safe_delivery_issue(payload.get("error"))
                    payload["channel"] = "WhatsApp" if str(payload.get("channel") or "").lower() in {"whatsapp", "octopus"} else ("Email" if str(payload.get("channel") or "").lower() in {"email", "gmail"} else "Message")
                elif report_type == "followups":
                    if "status" in payload:
                        payload["status"] = _label({"failed": "Failed", "sent": "Sent", "queued": "Queued"}, payload.get("status"))
                # Nulls stay blank, never zero.
                yield ["" if payload.get(c) is None else payload.get(c) for c in cols]


def record_export_audit(
    orch: Any,
    *,
    company_code: str,
    actor_user_id: str | None,
    report_type: str,
    filters: dict[str, Any],
    row_count: int,
    report_stamp: str,
) -> None:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO report_export_audits(
                  company_code, actor_user_id, report_type, metric_version, report_stamp, filters, row_count
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
                """,
                (
                    company_code,
                    actor_user_id,
                    report_type,
                    METRIC_VERSION,
                    report_stamp,
                    __import__("json").dumps(filters),
                    int(row_count),
                ),
            )
        conn.commit()


def rows_to_csv(headers: list[str], rows: Iterable[list[Any]]) -> tuple[str, int]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    count = 0
    for row in rows:
        writer.writerow(row)
        count += 1
    return buf.getvalue(), count
