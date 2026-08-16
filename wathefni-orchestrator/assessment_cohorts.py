"""Shared assessment cohort authority (Wave 3).

One contract for Overview, Candidates filters, Assessments page, and profile.
Counts are distinct confirmed people (same identity as Overview Wave 1) with
application counts published beside them.

States:
  - ready_to_send      first send (eligible, no assigned attempt)
  - sent_pending       assigned pending, delivery not failed
  - in_progress        assigned in_progress, delivery not failed
  - expired            assigned expired → resend needed
  - resend_needed      alias of expired (stable cohort key for CTAs)
  - delivery_failed    pending/in_progress with failed delivery
  - completed          completed attempts

Mutually exclusive actionable cohorts (an application appears in at most one
of: ready_to_send, sent_pending, in_progress, expired/resend_needed,
delivery_failed). Completed is separate and non-actionable for send/resend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

ASSESSMENT_ELIGIBLE_STATUSES = (
    "screening_complete",
    "review_pending",
    "ready_for_review",
    "shortlisted",
)

UNIT_PEOPLE = "people"
UNIT_APPLICATIONS = "applications"

COHORT_READY_TO_SEND = "assessment_ready_to_send"
COHORT_SENT_PENDING = "assessment_sent_pending"
COHORT_IN_PROGRESS = "assessment_in_progress"
COHORT_EXPIRED = "assessment_expired"
COHORT_RESEND_NEEDED = "assessment_resend_needed"
COHORT_DELIVERY_FAILED = "assessment_delivery_failed"
COHORT_COMPLETED = "assessment_completed"
COHORT_ATTENTION = "assessment_attention"

ACTION_READY_TO_SEND = "assessment_ready_to_send"
ACTION_RESEND = "assessment_resend_needed"
ACTION_DELIVERY_FAILED = "assessment_delivery_failed"
ACTION_IN_PROGRESS = "assessment_in_progress"
ACTION_SENT_PENDING = "assessment_sent_pending"

DELIVERY_FAILED_STATUSES = ("failed", "send_failed", "invitation_failed")

TAB_BY_COHORT = {
    COHORT_READY_TO_SEND: "send",
    COHORT_SENT_PENDING: "sent_pending",
    COHORT_IN_PROGRESS: "in_progress",
    COHORT_EXPIRED: "resend",
    COHORT_RESEND_NEEDED: "resend",
    COHORT_DELIVERY_FAILED: "delivery_failed",
    COHORT_COMPLETED: "completed",
}

PRIMARY_ACTION_BY_COHORT = {
    COHORT_READY_TO_SEND: "send_assessment",
    COHORT_SENT_PENDING: "resend_assessment",
    COHORT_IN_PROGRESS: "view_assessment",
    COHORT_EXPIRED: "resend_assessment",
    COHORT_RESEND_NEEDED: "resend_assessment",
    COHORT_DELIVERY_FAILED: "resend_assessment",
    COHORT_COMPLETED: "view_assessment_report",
}


def reviewable_predicate(alias: str = "a") -> str:
    return (
        f"COALESCE({alias}.data_source, {alias}.raw_json->>'data_source', 'production')='production' "
        f"AND ({alias}.cv_received IS TRUE OR jsonb_typeof({alias}.raw_json->'cv') = 'object')"
    )


def candidates_join(alias: str = "a", candidate_alias: str = "c") -> str:
    return f"LEFT JOIN candidates {candidate_alias} ON {candidate_alias}.phone={alias}.phone"


def latest_assessment_lateral(alias: str = "a") -> str:
    return f"""
        LEFT JOIN LATERAL (
          SELECT aa.status AS assessment_status,
                 aa.updated_at AS assessment_updated_at,
                 aa.created_at AS assessment_created_at,
                 aa.delivery_status AS assessment_delivery_status,
                 aa.expires_at AS assessment_expires_at
          FROM assessment_attempts aa
          WHERE aa.company_code={alias}.company_code AND aa.app_key={alias}.app_key
          ORDER BY aa.updated_at DESC, aa.created_at DESC
          LIMIT 1
        ) la ON TRUE
    """


def person_identity_sql(alias: str = "a", candidate_alias: str = "c") -> str:
    email_expr = (
        f"lower(trim(BOTH FROM COALESCE("
        f"NULLIF({candidate_alias}.email, ''), "
        f"NULLIF({alias}.raw_json->>'candidate_email', ''), "
        f"NULLIF({alias}.raw_json->>'email', ''), "
        f"NULLIF({alias}.raw_json->'candidate'->>'email', ''), "
        f"'')))"
    )
    phone_raw = (
        f"COALESCE("
        f"CASE WHEN {alias}.phone IS NOT NULL AND {alias}.phone !~* '^imp-' THEN {alias}.phone END, "
        f"NULLIF({alias}.raw_json->>'candidate_phone', ''), "
        f"NULLIF({alias}.raw_json->'candidate'->>'phone', ''), "
        f"'')"
    )
    phone_digits = f"regexp_replace({phone_raw}, '[^0-9]', '', 'g')"
    return (
        f"CASE "
        f"WHEN {email_expr} LIKE '%%@%%' AND {email_expr} !~* '^imp-' "
        f"THEN 'email:' || {email_expr} "
        f"WHEN length({phone_digits}) >= 8 "
        f"THEN 'phone:' || {phone_digits} "
        f"ELSE 'singleton:' || {alias}.app_key "
        f"END"
    )


def _status_expr(alias: str = "a") -> str:
    return f"COALESCE(la.assessment_status, {alias}.raw_json->'assessment'->>'status', '')"


def _delivery_expr(alias: str = "a") -> str:
    return (
        f"COALESCE(la.assessment_delivery_status, "
        f"{alias}.raw_json->'assessment'->>'delivery_status', '')"
    )


def eligible_application_predicate(alias: str = "a") -> str:
    statuses = ", ".join(f"'{s}'" for s in ASSESSMENT_ELIGIBLE_STATUSES)
    return f"{alias}.status IN ({statuses})"


def delivery_failed_sql(delivery_expr: str) -> str:
    values = ", ".join(f"'{s}'" for s in DELIVERY_FAILED_STATUSES)
    return f"{delivery_expr} IN ({values})"


def normalize_cohort_key(cohort_key: str | None) -> str:
    key = str(cohort_key or "").strip().lower()
    aliases = {
        "ready_to_send": COHORT_READY_TO_SEND,
        "first_send": COHORT_READY_TO_SEND,
        "sent_pending": COHORT_SENT_PENDING,
        "pending": COHORT_SENT_PENDING,
        "in_progress": COHORT_IN_PROGRESS,
        "expired": COHORT_EXPIRED,
        "resend": COHORT_RESEND_NEEDED,
        "resend_needed": COHORT_RESEND_NEEDED,
        "delivery_failed": COHORT_DELIVERY_FAILED,
        "completed": COHORT_COMPLETED,
        "attention": COHORT_ATTENTION,
        "assessment_pending": COHORT_ATTENTION,
        "awaiting": COHORT_ATTENTION,
    }
    return aliases.get(key, key)


def cohort_predicate(
    cohort_key: str,
    alias: str = "a",
    *,
    status_expr: str | None = None,
    delivery_expr: str | None = None,
) -> str:
    """SQL boolean for one cohort. Requires latest_assessment lateral `la` when needed."""
    key = normalize_cohort_key(cohort_key)
    status = status_expr or _status_expr(alias)
    delivery = delivery_expr or _delivery_expr(alias)
    eligible = eligible_application_predicate(alias)
    failed = delivery_failed_sql(delivery)

    if key == COHORT_READY_TO_SEND:
        return f"({eligible} AND ({status} = '' OR {status} IS NULL))"
    if key == COHORT_SENT_PENDING:
        return f"({eligible} AND {status} = 'pending' AND NOT ({failed}))"
    if key == COHORT_IN_PROGRESS:
        return f"({eligible} AND {status} = 'in_progress' AND NOT ({failed}))"
    if key in {COHORT_EXPIRED, COHORT_RESEND_NEEDED}:
        return f"({eligible} AND {status} = 'expired')"
    if key == COHORT_DELIVERY_FAILED:
        return f"({eligible} AND {status} IN ('pending','in_progress') AND {failed})"
    if key == COHORT_COMPLETED:
        return f"({eligible} AND {status} = 'completed')"
    if key == COHORT_ATTENTION:
        return (
            f"({eligible} AND ("
            f"  {status} IN ('pending','in_progress','expired')"
            f"  OR ({status} IN ('pending','in_progress') AND {failed})"
            f"))"
        )
    return "FALSE"


def classify_attempt_state(
    *,
    assessment_status: str | None,
    delivery_status: str | None = None,
    application_status: str | None = None,
) -> str | None:
    """Return cohort key for one application/attempt snapshot, or None if ineligible."""
    app_status = str(application_status or "").strip().lower()
    if app_status and app_status not in ASSESSMENT_ELIGIBLE_STATUSES:
        return None
    status = str(assessment_status or "").strip().lower()
    delivery = str(delivery_status or "").strip().lower()
    failed = delivery in DELIVERY_FAILED_STATUSES
    if not status:
        return COHORT_READY_TO_SEND
    if status in {"pending", "in_progress"} and failed:
        return COHORT_DELIVERY_FAILED
    if status == "pending":
        return COHORT_SENT_PENDING
    if status == "in_progress":
        return COHORT_IN_PROGRESS
    if status == "expired":
        return COHORT_RESEND_NEEDED
    if status == "completed":
        return COHORT_COMPLETED
    return None


def allowed_actions_for_cohort(cohort_key: str | None, *, can_manage: bool) -> list[str]:
    if not can_manage or not cohort_key:
        return []
    key = normalize_cohort_key(cohort_key)
    if key == COHORT_EXPIRED:
        key = COHORT_RESEND_NEEDED
    primary = PRIMARY_ACTION_BY_COHORT.get(key)
    if not primary:
        return []
    out = [primary]
    if key == COHORT_DELIVERY_FAILED:
        out.append("review_assessment_delivery")
    if key in {COHORT_SENT_PENDING, COHORT_IN_PROGRESS, COHORT_DELIVERY_FAILED, COHORT_RESEND_NEEDED}:
        if "resend_assessment" not in out:
            out.append("resend_assessment")
    return list(dict.fromkeys(out))


def destination_assessments(cohort_key: str, **extra: Any) -> dict[str, Any]:
    tab = TAB_BY_COHORT.get(cohort_key, "send")
    filters: dict[str, Any] = {
        "assessment_cohort": cohort_key,
        "overview_cohort": cohort_key,
        "cohort_key": cohort_key,
        "tab": tab,
    }
    filters.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return {"page": "assessments", "filters": filters, "cohort_key": cohort_key}


def destination_candidates(cohort_key: str, **extra: Any) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "assessment_cohort": cohort_key,
        "overview_cohort": cohort_key,
        "cohort_key": cohort_key,
    }
    status_map = {
        COHORT_READY_TO_SEND: "none",
        COHORT_SENT_PENDING: "pending",
        COHORT_IN_PROGRESS: "in_progress",
        COHORT_EXPIRED: "expired",
        COHORT_RESEND_NEEDED: "expired",
        COHORT_DELIVERY_FAILED: "pending",
        COHORT_COMPLETED: "completed",
        COHORT_ATTENTION: "awaiting",
    }
    if cohort_key in status_map:
        filters["assessment_status"] = status_map[cohort_key]
    filters.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return {"page": "candidates", "filters": filters, "cohort_key": cohort_key}


def _empty_block(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "unit": UNIT_PEOPLE,
        "people_count": 0,
        "application_count": 0,
        "people": 0,
        "applications": 0,
        "display_count": 0,
        "primary_action": PRIMARY_ACTION_BY_COHORT.get(key),
        "destination": destination_assessments(key),
        "candidates_destination": destination_candidates(key),
    }


def compute_assessment_cohorts(
    *,
    company: str,
    db_connect: Callable[[], Any],
    assessments_enabled: bool = True,
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
) -> dict[str, Any]:
    """Application (+ people) counts for every assessment cohort.

    When visibility_sql is set, counts share detail/assignment scope with the
    opened Send queue. Application counts must never fall back to attempt
    status_counts.
    """
    now = datetime.now(timezone.utc).isoformat()
    keys = [
        COHORT_READY_TO_SEND,
        COHORT_SENT_PENDING,
        COHORT_IN_PROGRESS,
        COHORT_EXPIRED,
        COHORT_RESEND_NEEDED,
        COHORT_DELIVERY_FAILED,
        COHORT_COMPLETED,
        COHORT_ATTENTION,
    ]
    if not assessments_enabled:
        cohorts = {k: _empty_block(k) for k in keys}
        return {
            "enabled": False,
            "as_of": now,
            "authority_source": "assessment_cohorts",
            "scope": "disabled",
            "cohorts": cohorts,
            "primary": None,
            "definitions": cohort_definitions(),
        }

    reviewable = reviewable_predicate("a")
    person_key = person_identity_sql("a", "c")
    join_c = candidates_join("a", "c")
    select_parts = []
    for key in keys:
        pred = cohort_predicate(key, "a")
        select_parts.append(f"COUNT(*) FILTER (WHERE {pred}) AS {key}_apps")
        select_parts.append(
            f"COUNT(DISTINCT CASE WHEN {pred} THEN {person_key} END) AS {key}_people"
        )

    vis_sql = str(visibility_sql or "").strip()
    vis_params = list(visibility_params or [])
    vis_clause = f" AND ({vis_sql})" if vis_sql else ""
    params: list[Any] = [company, *vis_params]

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  {", ".join(select_parts)}
                FROM applications a
                {join_c}
                {latest_assessment_lateral("a")}
                WHERE a.company_code=%s
                  AND {reviewable}
                  {vis_clause}
                """,
                tuple(params),
            )
            row = dict(cur.fetchone() or {})

    cohorts: dict[str, Any] = {}
    for key in keys:
        people = int(row.get(f"{key}_people") or 0)
        apps = int(row.get(f"{key}_apps") or 0)
        if key == COHORT_RESEND_NEEDED:
            people = int(row.get(f"{COHORT_EXPIRED}_people") or people)
            apps = int(row.get(f"{COHORT_EXPIRED}_apps") or apps)
        # Send + Completed badges use application_count. Attention stays people
        # for Overview legacy aggregate only.
        if key == COHORT_ATTENTION:
            unit = UNIT_PEOPLE
            display = people
        else:
            unit = UNIT_APPLICATIONS
            display = apps
        cohorts[key] = {
            "key": key,
            "unit": unit,
            "people_count": people,
            "application_count": apps,
            "people": people,
            "applications": apps,
            "display_count": display,
            "primary_action": PRIMARY_ACTION_BY_COHORT.get(key),
            "destination": destination_assessments(key),
            "candidates_destination": destination_candidates(key),
            "authority_source": "assessment_cohorts",
        }

    primary = pick_primary_assessment_action(cohorts)
    return {
        "enabled": True,
        "as_of": now,
        "authority_source": "assessment_cohorts",
        "scope": "detail_visibility" if vis_sql else "company",
        "cohorts": cohorts,
        "primary": primary,
        "definitions": cohort_definitions(),
    }


def pick_primary_assessment_action(cohorts: dict[str, Any]) -> dict[str, Any] | None:
    """Highest-priority actionable assessment CTA for Overview."""
    mapping = [
        (ACTION_DELIVERY_FAILED, COHORT_DELIVERY_FAILED, "Review delivery failures"),
        (ACTION_RESEND, COHORT_RESEND_NEEDED, "Resend expired assessments"),
        (ACTION_READY_TO_SEND, COHORT_READY_TO_SEND, "Send assessments"),
        (ACTION_SENT_PENDING, COHORT_SENT_PENDING, "View sent assessments"),
        (ACTION_IN_PROGRESS, COHORT_IN_PROGRESS, "View in-progress assessments"),
    ]
    for action, key, label in mapping:
        block = cohorts.get(key) if isinstance(cohorts.get(key), dict) else {}
        people = int(block.get("people_count") or block.get("people") or 0)
        apps = int(block.get("application_count") or block.get("applications") or 0)
        if people <= 0:
            continue
        return {
            "action": action,
            "cohort_key": key,
            "label": label,
            "unit": UNIT_PEOPLE,
            "people_count": people,
            "application_count": apps,
            "total_matching": people,
            "destination": block.get("destination") or destination_assessments(key),
            "candidates_destination": block.get("candidates_destination") or destination_candidates(key),
            "primary_action": block.get("primary_action") or PRIMARY_ACTION_BY_COHORT.get(key),
            "authority_source": "assessment_cohorts.primary",
        }
    return None


def cohort_definitions() -> dict[str, Any]:
    return {
        COHORT_READY_TO_SEND: {
            "label": "Ready to send",
            "means": "Eligible application with no assigned assessment attempt",
            "cta": "Send",
            "primary_action": "send_assessment",
        },
        COHORT_SENT_PENDING: {
            "label": "Sent / pending",
            "means": "Assigned attempt status=pending and delivery not failed",
            "cta": "View / resend",
            "primary_action": "resend_assessment",
        },
        COHORT_IN_PROGRESS: {
            "label": "In progress",
            "means": "Assigned attempt status=in_progress and delivery not failed",
            "cta": "View in progress",
            "primary_action": "view_assessment",
        },
        COHORT_EXPIRED: {
            "label": "Expired",
            "means": "Assigned attempt status=expired",
            "cta": "Resend",
            "primary_action": "resend_assessment",
        },
        COHORT_RESEND_NEEDED: {
            "label": "Resend needed",
            "means": "Same records as expired",
            "cta": "Resend",
            "primary_action": "resend_assessment",
            "alias_of": COHORT_EXPIRED,
        },
        COHORT_DELIVERY_FAILED: {
            "label": "Delivery failed",
            "means": "Open attempt (pending/in_progress) with failed delivery",
            "cta": "Review delivery failure",
            "primary_action": "resend_assessment",
        },
        COHORT_COMPLETED: {
            "label": "Completed",
            "means": "Assigned attempt status=completed",
            "cta": "View report",
            "primary_action": "view_assessment_report",
        },
        COHORT_ATTENTION: {
            "label": "Assessment attention",
            "means": "Assigned pending|in_progress|expired (aggregate; not a send CTA label)",
            "note": "Never label this aggregate as 'Send pending assessments'",
        },
    }


def next_action_candidate_from_cohorts(cohorts_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Shape compatible with prehire_overview.compute_next_action candidates."""
    primary = cohorts_payload.get("primary") if isinstance(cohorts_payload, dict) else None
    if not isinstance(primary, dict) or int(primary.get("people_count") or 0) <= 0:
        return None
    action = str(primary.get("action") or "")
    people = int(primary.get("people_count") or 0)
    apps = int(primary.get("application_count") or 0)
    priority_map = {
        ACTION_DELIVERY_FAILED: 58,
        ACTION_RESEND: 52,
        ACTION_READY_TO_SEND: 48,
        ACTION_SENT_PENDING: 35,
        ACTION_IN_PROGRESS: 30,
    }
    priority = priority_map.get(action, 45) + min(18, people * 3)
    reasons = {
        ACTION_DELIVERY_FAILED: (
            f"{people} candidate{'s' if people != 1 else ''} have assessment delivery failures"
            + (f" ({apps} applications)" if apps != people else "")
        ),
        ACTION_RESEND: (
            f"{people} candidate{'s' if people != 1 else ''} need assessment resend"
            + (f" ({apps} applications)" if apps != people else "")
        ),
        ACTION_READY_TO_SEND: (
            f"{people} candidate{'s' if people != 1 else ''} ready for first assessment send"
            + (f" ({apps} applications)" if apps != people else "")
        ),
        ACTION_SENT_PENDING: (
            f"{people} candidate{'s' if people != 1 else ''} have assessments sent and waiting"
            + (f" ({apps} applications)" if apps != people else "")
        ),
        ACTION_IN_PROGRESS: (
            f"{people} candidate{'s' if people != 1 else ''} have assessments in progress"
            + (f" ({apps} applications)" if apps != people else "")
        ),
    }
    return {
        "action": action,
        "priority": int(min(99, priority)),
        "unit": UNIT_PEOPLE,
        "reason": reasons.get(action, primary.get("label") or "Assessment work"),
        "total_matching": people,
        "people_count": people,
        "application_count": apps,
        "destination": primary.get("destination"),
        "authority_source": "assessment_cohorts",
        "cohort_key": primary.get("cohort_key"),
    }
