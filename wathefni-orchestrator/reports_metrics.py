"""Canonical Reports contract (reports-contract-v2).

One backend-authoritative payload for Overview cards, breakdowns, and export
counts. Consumes locked peer contracts — does not redefine them.

Overview:
  open_roles              = jobs open-status (positions)
  active_applications     = jobs.active_pipeline ∧ reviewable (+ visibility)
  ready_for_review        = prehire_overview people unit
  interview_scheduling_debt = prehire_overview.interview_scheduling_debt (apps)
  assessment_pending      = prehire_overview.assessment_pending people (never completed)
  followups_current       = prehire_overview.follow_up_needed people

Breakdowns:
  applications_by_stage   = candidates_stage_contract buckets ∧ reviewable
  applications_by_role    = active_pipeline by role (labeled)
  assessment_status       = every attempt + vocabulary labels
  interview_status        = interview_queue_contract normalize + human labels

Exports counts ≡ CSV row universe under the same visibility scope.
"""

from __future__ import annotations

from typing import Any, Callable

import candidates_stage_contract as _stages
import interview_queue_contract as _iqc
import jobs_queue_contract as _jobs
import prehire_overview as _overview

METRIC_VERSION = "reports-contract-v2"

STAGE_BUCKET_LABELS = {
    "en": {
        _stages.STAGE_BUCKET_NEW: "New",
        _stages.STAGE_BUCKET_READY: "Ready for review",
        _stages.STAGE_BUCKET_SHORTLISTED: "Shortlisted",
        _stages.STAGE_BUCKET_INTERVIEW: "Interview",
        _stages.STAGE_BUCKET_HIRED: "Hired",
        _stages.STAGE_BUCKET_REJECTED: "Rejected",
        _stages.STAGE_BUCKET_WITHDRAWN: "Withdrawn",
        _stages.STAGE_BUCKET_ARCHIVED: "Archived",
        _stages.STAGE_BUCKET_UNKNOWN: "Unknown",
    },
    "ar": {
        _stages.STAGE_BUCKET_NEW: "جديد",
        _stages.STAGE_BUCKET_READY: "جاهز للمراجعة",
        _stages.STAGE_BUCKET_SHORTLISTED: "القائمة المختصرة",
        _stages.STAGE_BUCKET_INTERVIEW: "المقابلة",
        _stages.STAGE_BUCKET_HIRED: "تم التعيين",
        _stages.STAGE_BUCKET_REJECTED: "مرفوض",
        _stages.STAGE_BUCKET_WITHDRAWN: "منسحب",
        _stages.STAGE_BUCKET_ARCHIVED: "مؤرشف",
        _stages.STAGE_BUCKET_UNKNOWN: "غير معروف",
    },
}

STAGE_BUCKET_ORDER = (
    _stages.STAGE_BUCKET_NEW,
    _stages.STAGE_BUCKET_READY,
    _stages.STAGE_BUCKET_SHORTLISTED,
    _stages.STAGE_BUCKET_INTERVIEW,
    _stages.STAGE_BUCKET_HIRED,
    _stages.STAGE_BUCKET_REJECTED,
    _stages.STAGE_BUCKET_WITHDRAWN,
    _stages.STAGE_BUCKET_ARCHIVED,
    _stages.STAGE_BUCKET_UNKNOWN,
)

ASSESSMENT_STATUS_LABELS = {
    "en": {
        "pending": "Sent pending",
        "in_progress": "In progress",
        "expired": "Expired",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "unknown": "Unknown",
    },
    "ar": {
        "pending": "مُرسل بانتظار البدء",
        "in_progress": "قيد التنفيذ",
        "expired": "منتهي",
        "completed": "مكتمل",
        "cancelled": "ملغى",
        "unknown": "غير معروف",
    },
}

INTERVIEW_STATUS_LABELS = {
    "en": {
        "scheduled": "Scheduled",
        "rescheduled": "Rescheduled",
        "completed": "Completed",
        "no_show": "No-show",
        "cancelled": "Cancelled",
        "unknown": "Unknown",
    },
    "ar": {
        "scheduled": "مجدولة",
        "rescheduled": "أُعيدت جدولتها",
        "completed": "مكتملة",
        "no_show": "لم يحضر",
        "cancelled": "ملغاة",
        "unknown": "غير معروف",
    },
}


def _locale_key(locale: str | None) -> str:
    return "ar" if str(locale or "").lower().startswith("ar") else "en"


def _vis_clause(visibility_sql: str | None) -> tuple[str, list[Any]]:
    vis = str(visibility_sql or "").strip()
    if not vis:
        return "", []
    return f" AND ({vis})", []


def _metric(
    key: str,
    label: str,
    value: int | float | None,
    *,
    unit: str,
    current_or_history: str,
    source_authority: str,
    export_key: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": int(value or 0) if value is not None and not isinstance(value, dict) else value,
        "unit": unit,
        "current_or_history": current_or_history,
        "source_authority": source_authority,
        "export_key": export_key,
        **(extra or {}),
    }


def stage_bucket_for_row(status: Any, record_state: Any = None) -> str | None:
    """Lifecycle bucket for Reports stage bars; held/Talent Pool → None (omit)."""
    row = {"status": status, "record_state": record_state}
    if _stages.is_talent_pool_stage_exempt(row):
        return None
    bucket = _stages.display_stage_bucket(row)
    if bucket in {_stages.STAGE_BUCKET_NONE}:
        return None
    return bucket


def merge_stage_breakdown(
    rows: list[dict[str, Any]],
    *,
    locale: str = "en",
) -> list[dict[str, Any]]:
    """Bucket raw status rows via candidates_stage_contract; drop held/none."""
    labels = STAGE_BUCKET_LABELS[_locale_key(locale)]
    merged: dict[str, int] = {key: 0 for key in STAGE_BUCKET_ORDER}
    for row in rows:
        bucket = stage_bucket_for_row(row.get("status") or row.get("label"), row.get("record_state"))
        if not bucket:
            continue
        if bucket not in merged:
            merged[bucket] = 0
        merged[bucket] += int(row.get("count") or 0)
    out: list[dict[str, Any]] = []
    for key in STAGE_BUCKET_ORDER:
        count = int(merged.get(key) or 0)
        if not count:
            continue
        out.append(
            {
                "key": key,
                "label": labels.get(key, key),
                "count": count,
            }
        )
    return out


def label_assessment_status(status: Any, *, locale: str = "en") -> dict[str, Any]:
    raw = str(status or "").strip().lower() or "unknown"
    key = raw if raw in ASSESSMENT_STATUS_LABELS["en"] else "unknown"
    return {
        "key": key,
        "status": key,
        "label": ASSESSMENT_STATUS_LABELS[_locale_key(locale)].get(key, key),
        "count": 0,
    }


def label_interview_status(status: Any, *, locale: str = "en") -> dict[str, Any]:
    normalized = _iqc.normalize_status(status, default="unknown") or "unknown"
    if normalized not in INTERVIEW_STATUS_LABELS["en"]:
        normalized = "unknown"
    return {
        "key": normalized,
        "status": normalized,
        "label": INTERVIEW_STATUS_LABELS[_locale_key(locale)].get(normalized, normalized),
        "count": 0,
    }


def _interview_scheduling_debt_count(
    cur: Any,
    *,
    company: str,
    reviewable: str,
    visibility_sql: str | None,
    visibility_params: list[Any] | None,
) -> int:
    vis_sql, _ = _vis_clause(visibility_sql)
    params = [company, *(visibility_params or [])]
    debt = _overview.interview_scheduling_debt_predicate("a", interview_status_expr="li.interview_status")
    cur.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM applications a
        LEFT JOIN LATERAL (
          SELECT ci.status AS interview_status
          FROM candidate_interviews ci
          WHERE ci.company_code=a.company_code AND ci.app_key=a.app_key
          ORDER BY ci.scheduled_start DESC NULLS LAST
          LIMIT 1
        ) li ON TRUE
        WHERE a.company_code=%s
          AND {reviewable}
          {vis_sql}
          AND {debt}
        """,
        params,
    )
    return int((cur.fetchone() or {}).get("n") or 0)


def _count_roles_export(
    cur: Any,
    *,
    company: str,
    reviewable: str,
    visibility_sql: str | None,
    visibility_params: list[Any] | None,
    jobs_visibility_sql: str | None,
    jobs_visibility_params: list[Any] | None,
) -> int:
    """Same universe as reports_v1 roles export (positions ∪ reviewable apps)."""
    app_vis, _ = _vis_clause(visibility_sql)
    job_vis = str(jobs_visibility_sql or "").strip()
    job_clause = f" AND ({job_vis})" if job_vis else ""
    params: list[Any] = [
        company,
        *(jobs_visibility_params or []),
        company,
        *(visibility_params or []),
    ]
    cur.execute(
        f"""
        WITH report_roles AS (
          SELECT p.position_code
          FROM positions p
          WHERE p.company_code=%s{job_clause}
          UNION
          SELECT a.position_code
          FROM applications a
          WHERE a.company_code=%s AND {reviewable}{app_vis}
            AND COALESCE(a.position_code, '') <> ''
        )
        SELECT COUNT(*) AS n FROM report_roles
        """,
        params,
    )
    return int((cur.fetchone() or {}).get("n") or 0)


def build_reports_metrics(
    *,
    company: str,
    db_connect: Callable[[], Any],
    reviewable_predicate: Callable[[str], str],
    action_counts: dict[str, Any],
    assessments_enabled: bool,
    interviews_enabled: bool,
    locale: str = "en",
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
    jobs_visibility_sql: str | None = None,
    jobs_visibility_params: list[Any] | None = None,
) -> dict[str, Any]:
    """Build metrics + breakdowns + export counts (canonical Reports contract)."""
    reviewable = reviewable_predicate("a")
    vis_sql, _ = _vis_clause(visibility_sql)
    vis_params = list(visibility_params or [])
    locale_key = _locale_key(locale)
    open_status_sql = _jobs.effective_job_status_sql("p.status")
    active_pipeline = _jobs.active_pipeline_predicate("a")
    job_vis = str(jobs_visibility_sql or "").strip()
    job_clause = f" AND ({job_vis})" if job_vis else ""

    with db_connect() as conn:
        with conn.cursor() as cur:
            # Open roles — jobs open-status + optional jobs assignment scope
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT p.position_code) FILTER (
                         WHERE ({open_status_sql}) = 'open'
                       ) AS open_roles
                FROM positions p
                WHERE p.company_code=%s{job_clause}
                """,
                (company, *(jobs_visibility_params or [])),
            )
            open_roles = int((cur.fetchone() or {}).get("open_roles") or 0)

            # Active applications = active_pipeline ∧ reviewable ∧ visibility
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND {active_pipeline}
                  {vis_sql}
                """,
                (company, *vis_params),
            )
            active_applications = int((cur.fetchone() or {}).get("n") or 0)

            # Stage breakdown — reviewable only; bucket via stage contract
            cur.execute(
                f"""
                SELECT a.status AS status,
                       COALESCE(a.raw_json->>'record_state', '') AS record_state,
                       COUNT(*) AS count
                FROM applications a
                WHERE a.company_code=%s
                  AND {reviewable}
                  {vis_sql}
                GROUP BY a.status, COALESCE(a.raw_json->>'record_state', '')
                """,
                (company, *vis_params),
            )
            stage_raw = [dict(r) for r in cur.fetchall()]
            stage_rows = merge_stage_breakdown(stage_raw, locale=locale_key)

            # Active applications by role
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(a.position_title,''), NULLIF(a.position_code,''), 'Unassigned role') AS label,
                       COUNT(*) AS count
                FROM applications a
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND {active_pipeline}
                  {vis_sql}
                GROUP BY COALESCE(NULLIF(a.position_title,''), NULLIF(a.position_code,''), 'Unassigned role')
                ORDER BY count DESC, label
                LIMIT 50
                """,
                (company, *vis_params),
            )
            role_breakdown = [
                {
                    "label": str(r["label"]),
                    "count": int(r["count"] or 0),
                    "scope": "active_pipeline",
                }
                for r in cur.fetchall()
            ]

            assessment_rows: list[dict[str, Any]] = []
            if assessments_enabled:
                cur.execute(
                    f"""
                    SELECT COALESCE(NULLIF(aa.status,''),'unknown') AS status, COUNT(*) AS count
                    FROM assessment_attempts aa
                    JOIN applications a ON a.company_code=aa.company_code AND a.app_key=aa.app_key
                    WHERE aa.company_code=%s AND {reviewable}{vis_sql}
                    GROUP BY COALESCE(NULLIF(aa.status,''),'unknown')
                    ORDER BY count DESC, status
                    """,
                    (company, *vis_params),
                )
                merged_assess: dict[str, int] = {}
                for r in cur.fetchall():
                    labeled = label_assessment_status(r["status"], locale=locale_key)
                    key = labeled["key"]
                    merged_assess[key] = merged_assess.get(key, 0) + int(r["count"] or 0)
                assessment_rows = [
                    {**label_assessment_status(key, locale=locale_key), "count": count}
                    for key, count in sorted(merged_assess.items(), key=lambda item: (-item[1], item[0]))
                ]

            interview_rows: list[dict[str, Any]] = []
            if interviews_enabled:
                cur.execute(
                    f"""
                    SELECT COALESCE(NULLIF(ci.status,''),'unknown') AS status, COUNT(*) AS count
                    FROM candidate_interviews ci
                    JOIN applications a ON a.company_code=ci.company_code AND a.app_key=ci.app_key
                    WHERE ci.company_code=%s AND {reviewable}{vis_sql}
                    GROUP BY COALESCE(NULLIF(ci.status,''),'unknown')
                    ORDER BY count DESC, status
                    """,
                    (company, *vis_params),
                )
                merged_int: dict[str, int] = {}
                for r in cur.fetchall():
                    labeled = label_interview_status(r["status"], locale=locale_key)
                    key = labeled["key"]
                    merged_int[key] = merged_int.get(key, 0) + int(r["count"] or 0)
                interview_rows = [
                    {**label_interview_status(key, locale=locale_key), "count": count}
                    for key, count in sorted(merged_int.items(), key=lambda item: (-item[1], item[0]))
                ]

            # Delivery failure history
            cur.execute(
                f"""
                SELECT COUNT(*) AS events
                FROM outbound_delivery_events ode
                JOIN applications a ON a.app_key=ode.subject_key AND a.company_code=ode.company_code
                WHERE a.company_code=%s AND {reviewable}{vis_sql}
                  AND COALESCE(ode.status,'') NOT IN ('sent','recovered')
                  AND ode.recovered_at IS NULL
                  AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                """,
                (company, *vis_params),
            )
            delivery_history_events = int((cur.fetchone() or {}).get("events") or 0)

            # Export counts (same scopes as CSV)
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {reviewable}{vis_sql}
                """,
                (company, *vis_params),
            )
            candidate_rows = int((cur.fetchone() or {}).get("n") or 0)

            role_rows = _count_roles_export(
                cur,
                company=company,
                reviewable=reviewable,
                visibility_sql=visibility_sql,
                visibility_params=vis_params,
                jobs_visibility_sql=jobs_visibility_sql,
                jobs_visibility_params=jobs_visibility_params,
            )

            assessment_export_rows = 0
            if assessments_enabled:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM assessment_attempts aa
                    JOIN applications a ON a.company_code=aa.company_code AND a.app_key=aa.app_key
                    WHERE aa.company_code=%s AND {reviewable}{vis_sql}
                    """,
                    (company, *vis_params),
                )
                assessment_export_rows = int((cur.fetchone() or {}).get("n") or 0)

            interview_export_rows = 0
            if interviews_enabled:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM candidate_interviews ci
                    JOIN applications a ON a.company_code=ci.company_code AND a.app_key=ci.app_key
                    WHERE ci.company_code=%s AND {reviewable}{vis_sql}
                    """,
                    (company, *vis_params),
                )
                interview_export_rows = int((cur.fetchone() or {}).get("n") or 0)

            # Current follow-ups export = distinct apps with open delivery failure (matches followups export)
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT a.app_key) AS n
                FROM applications a
                WHERE a.company_code=%s AND {reviewable}{vis_sql}
                  AND {_overview.follow_up_needed_exists("a")}
                """,
                (company, *vis_params),
            )
            followup_export_rows = int((cur.fetchone() or {}).get("n") or 0)

            interview_debt = 0
            if interviews_enabled:
                interview_debt = _interview_scheduling_debt_count(
                    cur,
                    company=company,
                    reviewable=reviewable,
                    visibility_sql=visibility_sql,
                    visibility_params=vis_params,
                )

    ready_for_review = int(action_counts.get("ready_for_review") or 0)
    followups_current = int(action_counts.get("follow_up_needed") or 0)
    assessment_pending = int(action_counts.get("assessment_pending") or 0)

    overview_labels = {
        "en": {
            "open_roles": "Open roles",
            "active_applications": "Active applications",
            "ready_for_review": "Ready for review",
            "interview_scheduling_debt": "Candidates needing interview scheduling",
            "assessment_pending": "Assessments needing action",
            "followups_current": "Current follow-ups",
        },
        "ar": {
            "open_roles": "الوظائف المفتوحة",
            "active_applications": "الطلبات النشطة",
            "ready_for_review": "جاهز للمراجعة",
            "interview_scheduling_debt": "مرشحون يحتاجون جدولة مقابلة",
            "assessment_pending": "تقييمات تحتاج إجراء",
            "followups_current": "المتابعات الحالية",
        },
    }[locale_key]

    metrics = [
        _metric(
            "open_roles",
            overview_labels["open_roles"],
            open_roles,
            unit="role",
            current_or_history="current",
            source_authority="jobs_queue_contract.open_status",
            export_key="roles",
        ),
        _metric(
            "active_applications",
            overview_labels["active_applications"],
            active_applications,
            unit="application",
            current_or_history="current",
            source_authority="jobs_queue_contract.active_pipeline",
            export_key="candidates",
        ),
        _metric(
            "ready_for_review",
            overview_labels["ready_for_review"],
            ready_for_review,
            unit="people",
            current_or_history="current",
            source_authority="prehire_overview.ready_for_review",
            export_key="candidates",
        ),
        _metric(
            "followups_current",
            overview_labels["followups_current"],
            followups_current,
            unit="people",
            current_or_history="current",
            source_authority="prehire_overview.follow_up_needed",
            export_key="followups",
        ),
        _metric(
            "delivery_failure_history",
            "Delivery failure history" if locale_key == "en" else "سجل فشل التسليم",
            delivery_history_events,
            unit="event",
            current_or_history="history",
            source_authority="outbound_delivery_events",
            export_key="followup_delivery_history",
        ),
    ]
    if interviews_enabled:
        metrics.append(
            _metric(
                "interview_scheduling_debt",
                overview_labels["interview_scheduling_debt"],
                interview_debt,
                unit="application",
                current_or_history="current",
                source_authority="prehire_overview.interview_scheduling_debt",
                export_key="interviews",
            )
        )
    if assessments_enabled:
        metrics.append(
            _metric(
                "assessment_pending",
                overview_labels["assessment_pending"],
                assessment_pending,
                unit="people",
                current_or_history="current",
                source_authority="prehire_overview.assessment_pending",
                export_key="assessments",
            )
        )

    breakdowns = {
        "applications_by_stage": stage_rows,
        "applications_by_role": role_breakdown,
        "assessment_status": assessment_rows,
        "interview_status": interview_rows,
    }

    exports = {
        "candidate_rows": candidate_rows,
        "role_rows": role_rows,
        "assessment_rows": assessment_export_rows if assessments_enabled else 0,
        "interview_rows": interview_export_rows if interviews_enabled else 0,
        "followup_rows": followup_export_rows,
        "followup_delivery_history_rows": delivery_history_events,
        # Correct key — do not overload followup_rows with delivery history
        "types": [
            key
            for key in (
                "candidates",
                "roles",
                "assessments",
                "interviews",
                "followups",
                "followup_delivery_history",
            )
            if key not in {"assessments", "interviews"}
            or (key == "assessments" and assessments_enabled)
            or (key == "interviews" and interviews_enabled)
        ],
    }

    overview = {
        "open_roles": open_roles,
        "active_applications": active_applications,
        "ready_for_review": ready_for_review,
        "interview_scheduling_debt": interview_debt if interviews_enabled else 0,
        "assessment_pending": assessment_pending if assessments_enabled else 0,
        "followups_current": followups_current,
        "units": {
            "open_roles": "role",
            "active_applications": "application",
            "ready_for_review": "people",
            "interview_scheduling_debt": "application",
            "assessment_pending": "people",
            "followups_current": "people",
        },
    }

    return {
        "version": METRIC_VERSION,
        "metric_version": METRIC_VERSION,
        "locale": locale_key,
        "metrics": metrics,
        "overview": overview,
        "breakdowns": breakdowns,
        "exports": exports,
        "role_export_total": role_rows,
        # Legacy summary aliases for older clients (correct meanings)
        "summary": {
            "ready_for_review": ready_for_review,
            "followups": followups_current,
            "followups_needed": followups_current,
            "followup_delivery_events": delivery_history_events,
            "assessment_pending": assessment_pending if assessments_enabled else 0,
            "interview_scheduling_debt": interview_debt if interviews_enabled else 0,
            "active_applications": active_applications,
            "open_roles": open_roles,
        },
    }


def build_canonical_reports_payload(
    *,
    company: str,
    db_connect: Callable[[], Any],
    reviewable_predicate: Callable[[str], str],
    assessments_enabled: bool,
    interviews_enabled: bool,
    locale: str = "en",
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
    jobs_visibility_sql: str | None = None,
    jobs_visibility_params: list[Any] | None = None,
    visibility_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single Reports GET payload — no dual authority merge."""
    partial = False
    error: str | None = None
    try:
        action_counts = _overview.compute_action_counts(
            company=company,
            db_connect=db_connect,
            assessments_enabled=assessments_enabled,
            visibility_sql=visibility_sql,
            visibility_params=visibility_params,
        )
    except Exception as exc:  # noqa: BLE001 — surface partial state
        action_counts = {
            "ready_for_review": 0,
            "assessment_pending": 0,
            "follow_up_needed": 0,
        }
        partial = True
        error = f"action_counts_failed:{exc.__class__.__name__}"

    try:
        body = build_reports_metrics(
            company=company,
            db_connect=db_connect,
            reviewable_predicate=reviewable_predicate,
            action_counts=action_counts,
            assessments_enabled=assessments_enabled,
            interviews_enabled=interviews_enabled,
            locale=locale,
            visibility_sql=visibility_sql,
            visibility_params=visibility_params,
            jobs_visibility_sql=jobs_visibility_sql,
            jobs_visibility_params=jobs_visibility_params,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "company_code": company,
            "metric_version": METRIC_VERSION,
            "partial": True,
            "error": f"reports_metrics_failed:{exc.__class__.__name__}",
            "overview": {},
            "metrics": {"version": METRIC_VERSION, "metrics": [], "breakdowns": {}},
            "breakdowns": {
                "applications_by_stage": [],
                "applications_by_role": [],
                "assessment_status": [],
                "interview_status": [],
            },
            "exports": {
                "candidate_rows": 0,
                "role_rows": 0,
                "assessment_rows": 0,
                "interview_rows": 0,
                "followup_rows": 0,
                "followup_delivery_history_rows": 0,
                "types": [],
            },
            "summary": {},
            "assessments_enabled": assessments_enabled,
            "interviews_enabled": interviews_enabled,
            **(visibility_meta or {}),
        }

    if partial:
        body["partial"] = True
        body["error"] = error
    else:
        body["partial"] = False
        body["error"] = None

    return {
        "ok": True,
        "company_code": company,
        "metric_version": body["metric_version"],
        "locale": body["locale"],
        "partial": body["partial"],
        "error": body.get("error"),
        "overview": body["overview"],
        "metrics": {
            "version": body["version"],
            "metrics": body["metrics"],
            "breakdowns": body["breakdowns"],
            "role_export_total": body["role_export_total"],
        },
        "breakdowns": body["breakdowns"],
        "exports": body["exports"],
        "summary": body["summary"],
        "assessments_enabled": assessments_enabled,
        "interviews_enabled": interviews_enabled,
        "advisory": True,
        "hr_decides": True,
        **(visibility_meta or {}),
    }
