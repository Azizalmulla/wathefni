"""Ranking pool contract — matching / rankable / eligible / top_n.

Approved product contract:

* ranking.pool.matching — exact job, production, usable CV (reviewable), same
  tenant + assignment/visibility as Candidates; exclude hired/rejected/withdrawn/
  archived.
* ranking.pool.rankable — matching ∧ required evidence complete ∧ bucket in
  {eligible, not_applicable}.
* ranking.pool.eligible — hard-criteria eligible only (distinct from rankable).
* ranking.pool.excluded — requirement_not_met / insufficient_information /
  restricted-held; retained for explanation; never leaderboard-ranked.
* ranking.run.top_n — slice only from rankable (never fill with unrankable).
* Assessment remains unused by default; may affect score/order only when
  explicitly approved, selected, completed, and position-matched.
"""

from __future__ import annotations

from typing import Any

# Lifecycle exclusions for ranking.pool.matching (aligned with Jobs active_pipeline).
MATCHING_EXCLUDED_STATUSES = ("hired", "rejected", "withdrawn", "archived")

RANKABLE_BUCKETS = frozenset({"eligible", "not_applicable"})
EXCLUDED_BUCKETS = frozenset({"requirement_not_met", "insufficient_information"})
EVALUATED_BUCKETS = frozenset({"eligible", "not_applicable", "requirement_not_met", "insufficient_information"})

RESTRICTED_MISSING_PREFIXES = ("ck_ranking_denied:",)


def matching_lifecycle_predicate(alias: str = "a") -> str:
    excluded = ", ".join(f"'{status}'" for status in MATCHING_EXCLUDED_STATUSES)
    return f"{alias}.status NOT IN ({excluded})"


def job_match_predicate(alias: str = "a") -> str:
    """Exact position_code OR title-with-spaces (same as Ranking loader)."""
    return (
        f"(upper({alias}.position_code)=%s OR upper(coalesce({alias}.position_title,''))=%s)"
    )


def is_rankable_item(item: dict[str, Any] | None) -> bool:
    """ranking.pool.rankable membership."""
    row = item if isinstance(item, dict) else {}
    bucket = str(row.get("eligibility_bucket") or "").strip().lower()
    if bucket not in RANKABLE_BUCKETS:
        return False
    complete = row.get("required_evidence_complete")
    if complete is None:
        prov = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
        complete = prov.get("required_evidence_complete")
        if complete is None and "required_evidence_complete" in (row.get("component_scores") or {}):
            complete = True
    if complete is False:
        return False
    if is_restricted_held(row):
        return False
    return True


def is_restricted_held(item: dict[str, Any] | None) -> bool:
    row = item if isinstance(item, dict) else {}
    ck = row.get("ck_ranking_reader") if isinstance(row.get("ck_ranking_reader"), dict) else {}
    if ck.get("active") and not ck.get("eligible", True):
        return True
    for code in list(row.get("required_missing") or []):
        text = str(code or "")
        if any(text.startswith(prefix) or prefix.rstrip(":") in text for prefix in RESTRICTED_MISSING_PREFIXES):
            return True
        if "ck_ranking_denied" in text.lower():
            return True
    return False


def is_excluded_from_leaderboard(item: dict[str, Any] | None) -> bool:
    """True when item must not receive soft_rank / top_n membership."""
    return not is_rankable_item(item)


def reconcile_pool_counters(items: list[dict[str, Any]] | None) -> dict[str, int]:
    """Fully reconcile evaluated matching items into named counters."""
    rows = list(items or [])
    eligible = 0
    not_applicable = 0
    requirement_not_met = 0
    insufficient_information = 0
    restricted_held = 0
    rankable = 0
    for row in rows:
        bucket = str(row.get("eligibility_bucket") or "").strip().lower()
        if is_restricted_held(row):
            restricted_held += 1
        if bucket == "eligible":
            eligible += 1
        elif bucket == "not_applicable":
            not_applicable += 1
        elif bucket == "requirement_not_met":
            requirement_not_met += 1
        elif bucket == "insufficient_information":
            insufficient_information += 1
        if is_rankable_item(row):
            rankable += 1
    matching = len(rows)
    evaluated_sum = eligible + not_applicable + requirement_not_met + insufficient_information
    return {
        "matching_count": matching,
        "rankable_count": rankable,
        "eligible_count": eligible,
        "not_applicable_count": not_applicable,
        "not_met_count": requirement_not_met,
        "unknown_count": insufficient_information,
        "restricted_held_count": restricted_held,
        "evaluated_sum": evaluated_sum,
        "reconciles": evaluated_sum == matching,
    }


def rankable_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [row for row in list(items or []) if is_rankable_item(row)]


def top_n_rankable(items: list[dict[str, Any]] | None, top_n: int | None) -> list[dict[str, Any]]:
    """ranking.run.top_n — slice only from rankable; never fill with unrankable."""
    rankable = rankable_items(items)
    if top_n is None or top_n <= 0:
        return rankable
    return rankable[: int(top_n)]
