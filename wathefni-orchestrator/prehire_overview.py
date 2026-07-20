"""Canonical Pre-Hiring Overview authority.

Single source of truth for:
  - action_counts (ready_for_review, assessment_pending, follow_up_needed)
  - next_action priority (deterministic, no model authority)
  - company-wide work queue
  - role pressure / prioritize-by-role

Overview, Reports headlines, mobile priorities (pre-hire section), and Admin
Assistant read tools must call these helpers — never recalculate in the client
or the model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

READY_FOR_REVIEW_STATUSES = ("screening_complete", "review_pending", "ready_for_review")
ASSESSMENT_ELIGIBLE_STATUSES = (
    "screening_complete",
    "review_pending",
    "ready_for_review",
    "shortlisted",
)
ASSESSMENT_PENDING_STATUSES = ("", "pending")

DEFAULT_SLA_HOURS = {
    "follow_up_hours": 24,
    "ready_for_review_hours": 48,
    "assessment_pending_hours": 72,
    "interview_scheduling_hours": 72,
}

# Deterministic action keys (stable API contract).
ACTION_FOLLOW_UP = "follow_up_failed_delivery"
ACTION_READY_FOR_REVIEW = "ready_for_review"
ACTION_ASSESSMENT_PENDING = "send_pending_assessments"
ACTION_INTERVIEW_SCHEDULING = "interview_scheduling_debt"
ACTION_ROLE_PRIORITY = "prioritize_role"


def reviewable_predicate(alias: str = "a") -> str:
    return (
        f"COALESCE({alias}.data_source, {alias}.raw_json->>'data_source', 'production')='production' "
        f"AND ({alias}.cv_received IS TRUE OR jsonb_typeof({alias}.raw_json->'cv') = 'object')"
    )


def ready_for_review_predicate(alias: str = "a") -> str:
    statuses = ", ".join(f"'{s}'" for s in READY_FOR_REVIEW_STATUSES)
    return f"{alias}.status IN ({statuses})"


def assessment_pending_predicate(
    alias: str = "a",
    assessment_status_expr: str | None = None,
) -> str:
    """Match Candidates assessment_status=awaiting and Overview assessment_pending."""
    statuses = ", ".join(f"'{s}'" for s in ASSESSMENT_ELIGIBLE_STATUSES)
    expr = assessment_status_expr or (
        f"COALESCE(la.assessment_status, {alias}.raw_json->'assessment'->>'status', '')"
    )
    return (
        f"{alias}.status IN ({statuses}) "
        f"AND {expr} IN ('', 'pending')"
    )


def follow_up_needed_exists(alias: str = "a") -> str:
    """Exact same EXISTS used by Candidates follow_up=needed."""
    return f"""
        EXISTS (
          SELECT 1
          FROM outbound_delivery_events ode
          WHERE ode.subject_key={alias}.app_key
            AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
            AND ode.recovered_at IS NULL
            AND (ode.status='failed' OR ode.last_error IS NOT NULL)
        )
    """


def latest_assessment_lateral(alias: str = "a") -> str:
    return f"""
        LEFT JOIN LATERAL (
          SELECT aa.status AS assessment_status, aa.updated_at AS assessment_updated_at, aa.created_at AS assessment_created_at
          FROM assessment_attempts aa
          WHERE aa.company_code={alias}.company_code AND aa.app_key={alias}.app_key
          ORDER BY aa.updated_at DESC, aa.created_at DESC
          LIMIT 1
        ) la ON TRUE
    """


def resolve_sla_hours(settings: dict[str, Any] | None) -> dict[str, int]:
    blob = settings if isinstance(settings, dict) else {}
    overview = blob.get("prehire_overview_sla") if isinstance(blob.get("prehire_overview_sla"), dict) else {}
    out = dict(DEFAULT_SLA_HOURS)
    for key, default in DEFAULT_SLA_HOURS.items():
        raw = overview.get(key, blob.get(key))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        out[key] = max(1, min(value, 24 * 30))
    return out


def _age_hours(value: Any, *, now: datetime | None = None) -> float:
    if value is None:
        return 0.0
    moment = value
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if not isinstance(moment, datetime):
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    return max(0.0, (ref - moment.astimezone(timezone.utc)).total_seconds() / 3600.0)


def compute_action_counts(
    *,
    company: str,
    db_connect: Callable[[], Any],
    assessments_enabled: bool = True,
) -> dict[str, int]:
    """Company-wide Overview / Reports headline counts.

    Definitions (canonical):
      ready_for_review  — reviewable apps in READY_FOR_REVIEW_STATUSES
      assessment_pending — reviewable apps eligible for assessment with status ''|pending
      follow_up_needed — distinct reviewable apps matching Candidates follow_up=needed

    assessment_pending is always computed from the canonical application cohort so
    Reports/Overview/Assistant share one number. Callers that lack the assessments
    module should hide the card / next-action candidate, not redefine the count.
    """
    del assessments_enabled  # reserved for callers; count stays definitionally stable
    reviewable = reviewable_predicate("a")
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  COUNT(*) FILTER (WHERE {ready_for_review_predicate("a")}) AS ready_for_review,
                  COUNT(*) FILTER (
                    WHERE {assessment_pending_predicate("a")}
                  ) AS assessment_pending,
                  COUNT(*) FILTER (WHERE {follow_up_needed_exists("a")}) AS follow_up_needed
                FROM applications a
                {latest_assessment_lateral("a")}
                WHERE a.company_code=%s
                  AND {reviewable}
                """,
                (company,),
            )
            row = cur.fetchone() or {}
    return {
        "ready_for_review": int(row.get("ready_for_review") or 0),
        "assessment_pending": int(row.get("assessment_pending") or 0),
        "follow_up_needed": int(row.get("follow_up_needed") or 0),
    }


def _destination_candidates(**filters: Any) -> dict[str, Any]:
    clean = {k: v for k, v in filters.items() if v not in (None, "", [])}
    return {"page": "candidates", "filters": clean}


def _destination_ranking(position_code: str | None = None) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if position_code:
        filters["position_code"] = position_code
    return {"page": "ranking", "filters": filters}


def compute_role_priority(
    *,
    company: str,
    db_connect: Callable[[], Any],
    assessments_enabled: bool = True,
) -> dict[str, Any] | None:
    """Pick the single role that most needs attention from canonical signals."""
    reviewable = reviewable_predicate("a")
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  COALESCE(NULLIF(a.position_code, ''), '') AS position_code,
                  COALESCE(NULLIF(MAX(a.position_title), ''), NULLIF(MAX(a.position_code), ''), 'Unassigned role') AS position_title,
                  COUNT(*) FILTER (WHERE {ready_for_review_predicate("a")}) AS ready_count,
                  COUNT(*) FILTER (WHERE {follow_up_needed_exists("a")}) AS follow_up_count,
                  COUNT(*) FILTER (
                    WHERE {assessment_pending_predicate("a")}
                  ) AS assessment_pending_count,
                  COUNT(*) FILTER (
                    WHERE a.status NOT IN ('hired','rejected','withdrawn')
                  ) AS active_count,
                  MIN(COALESCE(a.updated_at, a.ingested_at)) FILTER (
                    WHERE {ready_for_review_predicate("a")}
                  ) AS oldest_ready_at,
                  MAX(EXTRACT(EPOCH FROM (NOW() - COALESCE(a.updated_at, a.ingested_at))) / 3600.0) FILTER (
                    WHERE {ready_for_review_predicate("a")}
                  ) AS oldest_ready_hours
                FROM applications a
                {latest_assessment_lateral("a")}
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND COALESCE(NULLIF(a.position_code, ''), '') <> ''
                GROUP BY COALESCE(NULLIF(a.position_code, ''), '')
                HAVING COUNT(*) FILTER (
                  WHERE a.status NOT IN ('hired','rejected','withdrawn')
                ) > 0
                """,
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return None

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        ready = int(row.get("ready_count") or 0)
        follow = int(row.get("follow_up_count") or 0)
        pending = int(row.get("assessment_pending_count") or 0) if assessments_enabled else 0
        active = int(row.get("active_count") or 0)
        oldest_hours = float(row.get("oldest_ready_hours") or 0.0)
        # Low supply: open role with few active applicants.
        low_supply = 1 if 0 < active <= 2 else 0
        score = (
            follow * 40.0
            + ready * 25.0
            + pending * 15.0
            + min(oldest_hours, 168.0) * 0.2
            + low_supply * 10.0
        )
        reasons: list[str] = []
        if follow:
            reasons.append(f"{follow} candidate{'s' if follow != 1 else ''} need follow-up")
        if ready:
            reasons.append(f"{ready} ready for review")
        if pending:
            reasons.append(f"{pending} awaiting assessment")
        if oldest_hours >= 48 and ready:
            reasons.append(f"oldest ready ~{int(oldest_hours)}h")
        if low_supply:
            reasons.append("low candidate supply")
        if not reasons:
            reasons.append(f"{active} active application{'s' if active != 1 else ''}")
        scored.append(
            (
                score,
                {
                    "position_code": row["position_code"],
                    "position_title": row["position_title"],
                    "ready_count": ready,
                    "follow_up_count": follow,
                    "assessment_pending_count": pending,
                    "active_count": active,
                    "oldest_ready_hours": round(oldest_hours, 1),
                    "priority": int(min(99, max(1, round(score)))),
                    "reason": "; ".join(reasons),
                    "destination": _destination_candidates(
                        position=row["position_code"],
                        sort="ready_for_review",
                        review_status="ready",
                    ),
                    "ranking_destination": _destination_ranking(row["position_code"]),
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], str(item[1]["position_code"])))
    winner = scored[0][1]
    if scored[0][0] <= 0:
        return None
    return winner


def compute_next_action(
    *,
    company: str,
    db_connect: Callable[[], Any],
    assessments_enabled: bool = True,
    interviews_enabled: bool = True,
    settings: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Deterministic priority winner for Overview hero.

    Scores use only canonical SQL facts + SLA thresholds from company_settings
    (prehire_overview_sla) with safe defaults. No model authority.
    """
    sla = resolve_sla_hours(settings)
    counts = compute_action_counts(
        company=company,
        db_connect=db_connect,
        assessments_enabled=assessments_enabled,
    )
    reviewable = reviewable_predicate("a")
    now = now or datetime.now(timezone.utc)

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  MIN(ode.created_at) AS oldest_follow_up_at,
                  COUNT(DISTINCT a.app_key) AS follow_apps
                FROM applications a
                JOIN outbound_delivery_events ode ON ode.subject_key=a.app_key
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND {follow_up_needed_exists("a")}
                  AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
                  AND ode.recovered_at IS NULL
                  AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                """,
                (company,),
            )
            follow_meta = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT MIN(COALESCE(a.updated_at, a.ingested_at)) AS oldest_ready_at
                FROM applications a
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND {ready_for_review_predicate("a")}
                """,
                (company,),
            )
            ready_meta = dict(cur.fetchone() or {})

            assessment_meta: dict[str, Any] = {}
            if assessments_enabled and counts["assessment_pending"]:
                cur.execute(
                    f"""
                    SELECT MIN(COALESCE(a.updated_at, a.ingested_at)) AS oldest_assessment_wait_at
                    FROM applications a
                    {latest_assessment_lateral("a")}
                    WHERE a.company_code=%s
                      AND {reviewable}
                      AND {assessment_pending_predicate("a")}
                    """,
                    (company,),
                )
                assessment_meta = dict(cur.fetchone() or {})

            interview_debt = 0
            oldest_interview_at = None
            if interviews_enabled:
                cur.execute(
                    f"""
                    SELECT
                      COUNT(DISTINCT a.app_key) AS debt,
                      MIN(COALESCE(a.updated_at, a.ingested_at)) AS oldest_at
                    FROM applications a
                    LEFT JOIN LATERAL (
                      SELECT ci.status AS interview_status
                      FROM candidate_interviews ci
                      WHERE ci.company_code=a.company_code AND ci.app_key=a.app_key
                      ORDER BY ci.scheduled_start DESC NULLS LAST, ci.updated_at DESC
                      LIMIT 1
                    ) li ON TRUE
                    WHERE a.company_code=%s
                      AND {reviewable}
                      AND a.status IN ('shortlisted','ready_for_review','screening_complete','review_pending')
                      AND li.interview_status IS NULL
                    """,
                    (company,),
                )
                interview_row = dict(cur.fetchone() or {})
                interview_debt = int(interview_row.get("debt") or 0)
                oldest_interview_at = interview_row.get("oldest_at")

    candidates: list[dict[str, Any]] = []

    follow_total = counts["follow_up_needed"]
    if follow_total:
        age = _age_hours(follow_meta.get("oldest_follow_up_at"), now=now)
        over_sla = age >= sla["follow_up_hours"]
        priority = 70 + min(25, follow_total * 4) + (10 if over_sla else 0) + min(10, int(age // 24))
        candidates.append(
            {
                "action": ACTION_FOLLOW_UP,
                "priority": int(min(99, priority)),
                "reason": (
                    f"{follow_total} candidate{'s' if follow_total != 1 else ''} have failed delivery events"
                    + (f"; oldest is {max(1, int(age // 24))} day{'s' if age >= 48 else ''}" if age >= 24 else "")
                ),
                "total_matching": follow_total,
                "destination": _destination_candidates(follow_up="needed"),
                "authority_source": "prehire_overview.follow_up_needed",
            }
        )

    ready_total = counts["ready_for_review"]
    if ready_total:
        age = _age_hours(ready_meta.get("oldest_ready_at"), now=now)
        over_sla = age >= sla["ready_for_review_hours"]
        priority = 55 + min(20, ready_total * 3) + (12 if over_sla else 0) + min(8, int(age // 24))
        candidates.append(
            {
                "action": ACTION_READY_FOR_REVIEW,
                "priority": int(min(99, priority)),
                "reason": (
                    f"{ready_total} candidate{'s' if ready_total != 1 else ''} ready for an HR decision"
                    + (f"; oldest waiting ~{int(age)}h" if over_sla else "")
                ),
                "total_matching": ready_total,
                "destination": _destination_candidates(review_status="ready", sort="ready_for_review"),
                "authority_source": "prehire_overview.ready_for_review",
            }
        )

    assess_total = counts["assessment_pending"]
    if assessments_enabled and assess_total:
        age = _age_hours(assessment_meta.get("oldest_assessment_wait_at"), now=now)
        over_sla = age >= sla["assessment_pending_hours"]
        priority = 45 + min(18, assess_total * 3) + (10 if over_sla else 0)
        candidates.append(
            {
                "action": ACTION_ASSESSMENT_PENDING,
                "priority": int(min(99, priority)),
                "reason": (
                    f"{assess_total} candidate{'s' if assess_total != 1 else ''} awaiting assessment send"
                    + (f"; oldest waiting ~{int(age)}h" if over_sla else "")
                ),
                "total_matching": assess_total,
                "destination": _destination_candidates(assessment_status="awaiting"),
                "authority_source": "prehire_overview.assessment_pending",
            }
        )

    if interviews_enabled and interview_debt:
        age = _age_hours(oldest_interview_at, now=now)
        over_sla = age >= sla["interview_scheduling_hours"]
        priority = 40 + min(15, interview_debt * 2) + (10 if over_sla else 0)
        candidates.append(
            {
                "action": ACTION_INTERVIEW_SCHEDULING,
                "priority": int(min(99, priority)),
                "reason": f"{interview_debt} shortlisted/ready candidate{'s' if interview_debt != 1 else ''} still need interview scheduling",
                "total_matching": interview_debt,
                "destination": {"page": "interviews", "filters": {"status": "needs_scheduling"}},
                "authority_source": "prehire_overview.interview_scheduling_debt",
            }
        )

    role = compute_role_priority(
        company=company,
        db_connect=db_connect,
        assessments_enabled=assessments_enabled,
    )
    if role and int(role.get("priority") or 0) >= 50:
        candidates.append(
            {
                "action": ACTION_ROLE_PRIORITY,
                "priority": int(role["priority"]),
                "reason": f"{role['position_title']}: {role['reason']}",
                "total_matching": int(role.get("ready_count") or 0) + int(role.get("follow_up_count") or 0),
                "destination": role["ranking_destination"],
                "authority_source": "prehire_overview.role_priority",
                "role": {
                    "position_code": role["position_code"],
                    "position_title": role["position_title"],
                },
            }
        )

    # Stable tie-break: higher priority, then fixed action order, then total.
    order = {
        ACTION_FOLLOW_UP: 0,
        ACTION_READY_FOR_REVIEW: 1,
        ACTION_ASSESSMENT_PENDING: 2,
        ACTION_INTERVIEW_SCHEDULING: 3,
        ACTION_ROLE_PRIORITY: 4,
    }
    if not candidates:
        return {
            "action": "none",
            "priority": 0,
            "reason": "No urgent hiring actions right now.",
            "total_matching": 0,
            "destination": {"page": "overview", "filters": {}},
            "authority_source": "prehire_overview.next_action",
            "label": "suggested_next_action",
            "sla_hours": sla,
            "as_of": now.astimezone(timezone.utc).isoformat(),
        }

    candidates.sort(
        key=lambda item: (
            -int(item["priority"]),
            order.get(str(item["action"]), 99),
            -int(item.get("total_matching") or 0),
            str(item["action"]),
        )
    )
    winner = dict(candidates[0])
    winner["label"] = "suggested_next_action"
    winner["sla_hours"] = sla
    winner["as_of"] = now.astimezone(timezone.utc).isoformat()
    winner["alternatives"] = [
        {"action": c["action"], "priority": c["priority"], "total_matching": c["total_matching"]}
        for c in candidates[1:4]
    ]
    return winner


def compute_work_queue(
    *,
    company: str,
    db_connect: Callable[[], Any],
    assessments_enabled: bool = True,
    interviews_enabled: bool = True,
    settings: dict[str, Any] | None = None,
    limit: int = 25,
    cursor: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Company-wide prioritized work queue with cursor pagination.

    Cursor format: "{priority:03d}:{action}:{app_key}" descending walk.
    """
    sla = resolve_sla_hours(settings)
    now = now or datetime.now(timezone.utc)
    reviewable = reviewable_predicate("a")
    limit = max(1, min(int(limit or 25), 100))

    items: list[dict[str, Any]] = []
    with db_connect() as conn:
        with conn.cursor() as cur:
            # Follow-up rows
            cur.execute(
                f"""
                SELECT
                  a.app_key,
                  COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.phone) AS candidate_name,
                  COALESCE(NULLIF(a.position_title, ''), a.position_code) AS position_title,
                  a.position_code,
                  MIN(ode.created_at) AS event_at,
                  MAX(EXTRACT(EPOCH FROM (NOW() - ode.created_at)) / 3600.0) AS age_hours
                FROM applications a
                LEFT JOIN candidates c ON c.phone=a.phone
                JOIN outbound_delivery_events ode ON ode.subject_key=a.app_key
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND {follow_up_needed_exists("a")}
                  AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
                  AND ode.recovered_at IS NULL
                  AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                GROUP BY a.app_key, candidate_name, position_title, a.position_code
                """,
                (company,),
            )
            for row in cur.fetchall():
                age = float(row.get("age_hours") or 0.0)
                priority = 70 + min(20, int(age // 12)) + (10 if age >= sla["follow_up_hours"] else 0)
                items.append(
                    _queue_item(
                        action_type=ACTION_FOLLOW_UP,
                        app_key=row["app_key"],
                        candidate_name=row.get("candidate_name"),
                        position_code=row.get("position_code"),
                        position_title=row.get("position_title"),
                        reason="Failed candidate delivery needs HR follow-up",
                        priority=priority,
                        age_hours=age,
                        destination=_destination_candidates(follow_up="needed", q=row["app_key"]),
                        authority_source="prehire_overview.follow_up_needed",
                        as_of=now,
                    )
                )

            # Ready for review
            cur.execute(
                f"""
                SELECT
                  a.app_key,
                  COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.phone) AS candidate_name,
                  COALESCE(NULLIF(a.position_title, ''), a.position_code) AS position_title,
                  a.position_code,
                  COALESCE(a.updated_at, a.ingested_at) AS event_at,
                  EXTRACT(EPOCH FROM (NOW() - COALESCE(a.updated_at, a.ingested_at))) / 3600.0 AS age_hours
                FROM applications a
                LEFT JOIN candidates c ON c.phone=a.phone
                WHERE a.company_code=%s
                  AND {reviewable}
                  AND {ready_for_review_predicate("a")}
                """,
                (company,),
            )
            for row in cur.fetchall():
                age = float(row.get("age_hours") or 0.0)
                priority = 55 + min(15, int(age // 12)) + (10 if age >= sla["ready_for_review_hours"] else 0)
                items.append(
                    _queue_item(
                        action_type=ACTION_READY_FOR_REVIEW,
                        app_key=row["app_key"],
                        candidate_name=row.get("candidate_name"),
                        position_code=row.get("position_code"),
                        position_title=row.get("position_title"),
                        reason="Candidate is ready for an HR decision",
                        priority=priority,
                        age_hours=age,
                        destination=_destination_candidates(review_status="ready", sort="ready_for_review", q=row["app_key"]),
                        authority_source="prehire_overview.ready_for_review",
                        as_of=now,
                    )
                )

            if assessments_enabled:
                cur.execute(
                    f"""
                    SELECT
                      a.app_key,
                      COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.phone) AS candidate_name,
                      COALESCE(NULLIF(a.position_title, ''), a.position_code) AS position_title,
                      a.position_code,
                      COALESCE(a.updated_at, a.ingested_at) AS event_at,
                      EXTRACT(EPOCH FROM (NOW() - COALESCE(a.updated_at, a.ingested_at))) / 3600.0 AS age_hours
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    {latest_assessment_lateral("a")}
                    WHERE a.company_code=%s
                      AND {reviewable}
                      AND {assessment_pending_predicate("a")}
                    """,
                    (company,),
                )
                for row in cur.fetchall():
                    age = float(row.get("age_hours") or 0.0)
                    priority = 45 + min(12, int(age // 18)) + (8 if age >= sla["assessment_pending_hours"] else 0)
                    items.append(
                        _queue_item(
                            action_type=ACTION_ASSESSMENT_PENDING,
                            app_key=row["app_key"],
                            candidate_name=row.get("candidate_name"),
                            position_code=row.get("position_code"),
                            position_title=row.get("position_title"),
                            reason="Assessment send is pending",
                            priority=priority,
                            age_hours=age,
                            destination=_destination_candidates(assessment_status="awaiting", q=row["app_key"]),
                            authority_source="prehire_overview.assessment_pending",
                            as_of=now,
                        )
                    )

            if interviews_enabled:
                cur.execute(
                    f"""
                    SELECT
                      a.app_key,
                      COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.phone) AS candidate_name,
                      COALESCE(NULLIF(a.position_title, ''), a.position_code) AS position_title,
                      a.position_code,
                      COALESCE(a.updated_at, a.ingested_at) AS event_at,
                      EXTRACT(EPOCH FROM (NOW() - COALESCE(a.updated_at, a.ingested_at))) / 3600.0 AS age_hours
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    LEFT JOIN LATERAL (
                      SELECT ci.status AS interview_status
                      FROM candidate_interviews ci
                      WHERE ci.company_code=a.company_code AND ci.app_key=a.app_key
                      ORDER BY ci.scheduled_start DESC NULLS LAST, ci.updated_at DESC
                      LIMIT 1
                    ) li ON TRUE
                    WHERE a.company_code=%s
                      AND {reviewable}
                      AND a.status IN ('shortlisted','ready_for_review','screening_complete','review_pending')
                      AND li.interview_status IS NULL
                    """,
                    (company,),
                )
                for row in cur.fetchall():
                    age = float(row.get("age_hours") or 0.0)
                    priority = 40 + min(10, int(age // 24))
                    items.append(
                        _queue_item(
                            action_type=ACTION_INTERVIEW_SCHEDULING,
                            app_key=row["app_key"],
                            candidate_name=row.get("candidate_name"),
                            position_code=row.get("position_code"),
                            position_title=row.get("position_title"),
                            reason="Interview scheduling still needed",
                            priority=priority,
                            age_hours=age,
                            destination={"page": "interviews", "filters": {}},
                            authority_source="prehire_overview.interview_scheduling_debt",
                            as_of=now,
                        )
                    )

    # Deduplicate by (action_type, app_key) keeping highest priority.
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item["action_type"]), str(item.get("app_key") or item.get("position_code") or ""))
        prev = best.get(key)
        if prev is None or int(item["priority"]) > int(prev["priority"]):
            best[key] = item
    ordered = sorted(
        best.values(),
        key=lambda item: (
            -int(item["priority"]),
            str(item["action_type"]),
            str(item.get("app_key") or ""),
        ),
    )

    start = 0
    if cursor:
        for idx, item in enumerate(ordered):
            token = _cursor_token(item)
            if token == cursor:
                start = idx + 1
                break

    page = ordered[start : start + limit]
    next_cursor = _cursor_token(page[-1]) if start + limit < len(ordered) and page else None
    return {
        "company_code": company,
        "ok": True,
        "as_of": now.astimezone(timezone.utc).isoformat(),
        "authority_source": "prehire_overview.work_queue",
        "total": len(ordered),
        "limit": limit,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
        "items": page,
        "sla_hours": sla,
    }


def _cursor_token(item: dict[str, Any]) -> str:
    return f"{int(item['priority']):03d}:{item['action_type']}:{item.get('app_key') or item.get('position_code') or ''}"


def _queue_item(
    *,
    action_type: str,
    app_key: str | None,
    candidate_name: str | None,
    position_code: str | None,
    position_title: str | None,
    reason: str,
    priority: int,
    age_hours: float,
    destination: dict[str, Any],
    authority_source: str,
    as_of: datetime,
) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "app_key": app_key,
        "candidate_name": candidate_name,
        "position_code": position_code,
        "position_title": position_title,
        "reason": reason,
        "priority": int(min(99, max(1, priority))),
        "age_hours": round(float(age_hours or 0.0), 1),
        "destination": destination,
        "authority_source": authority_source,
        "as_of": as_of.astimezone(timezone.utc).isoformat(),
    }


def build_overview_authority(
    *,
    company: str,
    db_connect: Callable[[], Any],
    get_company_settings: Callable[[str], dict[str, Any]],
    assessments_enabled: bool = True,
    interviews_enabled: bool = True,
) -> dict[str, Any]:
    settings = get_company_settings(company) or {}
    counts = compute_action_counts(
        company=company,
        db_connect=db_connect,
        assessments_enabled=assessments_enabled,
    )
    next_action = compute_next_action(
        company=company,
        db_connect=db_connect,
        assessments_enabled=assessments_enabled,
        interviews_enabled=interviews_enabled,
        settings=settings,
    )
    role = compute_role_priority(
        company=company,
        db_connect=db_connect,
        assessments_enabled=assessments_enabled,
    )
    return {
        "action_counts": counts,
        "next_action": next_action,
        "role_priority": role,
        "definitions": {
            "ready_for_review": {
                "entity": "applications",
                "statuses": list(READY_FOR_REVIEW_STATUSES),
                "destination_filters": {"review_status": "ready", "sort": "ready_for_review"},
            },
            "assessment_pending": {
                "entity": "applications",
                "statuses": list(ASSESSMENT_ELIGIBLE_STATUSES),
                "assessment_status": list(ASSESSMENT_PENDING_STATUSES),
                "destination_filters": {"assessment_status": "awaiting"},
            },
            "follow_up_needed": {
                "entity": "applications",
                "matches": "Candidates follow_up=needed",
                "destination_filters": {"follow_up": "needed"},
            },
        },
        "as_of": datetime.now(timezone.utc).isoformat(),
        "authority_source": "prehire_overview",
    }
