"""Database services for Wathefni's proprietary assessment product.

All functions operate on a caller-owned cursor so state changes can be composed
into one transaction. Live scoring inputs come only from frozen content versions.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

import assessment_lifecycle as lifecycle


def _dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def freeze_current_content_version(
    cur: Any,
    *,
    company_code: str,
    battery_key: str,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Freeze approved live content and deterministic rules, once per digest."""

    company = str(company_code or "GLOBAL").upper()
    cur.execute(
        """
        SELECT *
        FROM assessment_batteries
        WHERE battery_key=%s AND is_active IS TRUE
          AND company_code IN (%s, 'GLOBAL')
        ORDER BY CASE WHEN company_code=%s THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        (battery_key, company, company),
    )
    battery = _dict(cur.fetchone())
    if not battery:
        raise lifecycle.AssessmentAuthorityError(
            "missing_active_assessment_battery",
            "No active Wathefni assessment battery is available.",
            status_code=409,
        )
    cur.execute(
        """
        SELECT item_id, battery_key, section, item_order, prompt_text, choices,
               answer_key, scoring, difficulty, raw_json, content_version,
               authoring_status
        FROM assessment_items
        WHERE battery_key=%s AND authoring_status='approved' AND retired_at IS NULL
        ORDER BY item_order, item_id
        """,
        (battery_key,),
    )
    items = [dict(row) for row in cur.fetchall()]
    if not items:
        raise lifecycle.AssessmentAuthorityError(
            "missing_assessment_items",
            "The active battery has no approved items.",
            status_code=409,
        )
    cur.execute(
        """
        SELECT norm_key, company_code, battery_key, section, sample_size,
               percentiles, source, raw_json
        FROM assessment_norm_groups
        WHERE battery_key=%s AND company_code IN (%s, 'GLOBAL') AND is_active IS TRUE
        ORDER BY CASE WHEN company_code=%s THEN 0 ELSE 1 END, section, updated_at DESC
        """,
        (battery_key, company, company),
    )
    norm_groups = [dict(row) for row in cur.fetchall()]
    scoring_rules = battery.get("scoring_rules_json") if isinstance(battery.get("scoring_rules_json"), dict) else {}
    scoring_rules = {
        **scoring_rules,
        "norm_groups": norm_groups,
        "authority": "deterministic_frozen_wathefni_content",
    }
    battery_snapshot = {
        key: battery.get(key)
        for key in (
            "battery_key",
            "company_code",
            "name",
            "version",
            "sections",
            "raw_json",
            "content_version",
            "report_logic_version",
        )
    }
    payload = {
        "battery_snapshot": battery_snapshot,
        "items_snapshot": items,
        "scoring_rules_snapshot": scoring_rules,
        "report_logic_version": str(battery.get("report_logic_version") or "wathefni_report_v1"),
        "norm_version": str(
            (battery.get("raw_json") or {}).get("norm_version")
            if isinstance(battery.get("raw_json"), dict)
            else ""
        )
        or "wathefni_ability_v1_local",
    }
    digest = lifecycle.content_digest(payload)
    content_version = int(battery.get("content_version") or 1)
    cur.execute(
        """
        INSERT INTO assessment_content_versions
          (company_code, battery_key, content_version, battery_snapshot,
           items_snapshot, scoring_rules_snapshot, report_logic_version,
           norm_version, content_sha256, created_by_user_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, content_sha256) DO UPDATE
          SET content_sha256=EXCLUDED.content_sha256
        RETURNING *
        """,
        (
            str(battery.get("company_code") or "GLOBAL").upper(),
            battery_key,
            content_version,
            Json(battery_snapshot),
            Json(items),
            Json(scoring_rules),
            payload["report_logic_version"],
            payload["norm_version"],
            digest,
            created_by_user_id,
        ),
    )
    version = dict(cur.fetchone())
    cur.execute(
        "UPDATE assessment_batteries SET frozen_at=COALESCE(frozen_at,now()) WHERE battery_key=%s",
        (battery_key,),
    )
    cur.execute(
        """
        UPDATE assessment_items
        SET approved_at=COALESCE(approved_at,now())
        WHERE battery_key=%s AND authoring_status='approved'
        """,
        (battery_key,),
    )
    return version


def content_version_by_id(
    cur: Any,
    assessment_version_id: str,
    *,
    company_code: str | None = None,
) -> dict[str, Any] | None:
    params: list[Any] = [assessment_version_id]
    company_sql = ""
    if company_code:
        company_sql = "AND company_code IN (%s,'GLOBAL')"
        params.append(str(company_code).upper())
    cur.execute(
        f"SELECT * FROM assessment_content_versions WHERE assessment_version_id=%s {company_sql} LIMIT 1",
        params,
    )
    return _dict(cur.fetchone())


def version_items(version: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = (version or {}).get("items_snapshot")
    return [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def version_item_at(version: dict[str, Any] | None, index: int) -> dict[str, Any] | None:
    items = version_items(version)
    return items[index] if 0 <= index < len(items) else None


def version_norm_lookup(version: dict[str, Any] | None) -> dict[str, Any]:
    rules = (version or {}).get("scoring_rules_snapshot")
    groups = rules.get("norm_groups") if isinstance(rules, dict) else []
    selected: dict[str, Any] = {}
    if isinstance(groups, list):
        for group in reversed(groups):
            if isinstance(group, dict) and group.get("section"):
                selected[str(group["section"])] = group
    return selected


def validate_take_token(
    cur: Any,
    *,
    attempt_id: str,
    raw_token: str | None,
    company_code: str | None = None,
    for_update: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not raw_token:
        raise lifecycle.AssessmentAuthorityError("token_required", "Assessment link token is required.", status_code=403)
    company_sql = ""
    params: list[Any] = [attempt_id, lifecycle.token_hash(raw_token)]
    if company_code:
        company_sql = "AND a.company_code=%s"
        params.append(str(company_code).upper())
    lock_sql = "FOR UPDATE OF a" if for_update else ""
    cur.execute(
        f"""
        SELECT
          a.*,
          t.token_id,
          t.expires_at AS token_expires_at,
          t.revoked_at AS token_revoked_at,
          t.revoked_reason AS token_revoked_reason
        FROM assessment_attempts a
        JOIN assessment_tokens t
          ON t.attempt_id=a.attempt_id AND t.company_code=a.company_code
        WHERE a.attempt_id=%s AND t.token_hash=%s AND t.purpose='take'
          {company_sql}
        LIMIT 1
        {lock_sql}
        """,
        params,
    )
    joined = _dict(cur.fetchone())
    if not joined:
        raise lifecycle.AssessmentAuthorityError("invalid_assessment_token", "Assessment link is invalid.", status_code=403)
    attempt = {key: value for key, value in joined.items() if not key.startswith("token_")}
    token = {
        "token_id": joined.get("token_id"),
        "expires_at": joined.get("token_expires_at"),
        "revoked_at": joined.get("token_revoked_at"),
        "revoked_reason": joined.get("token_revoked_reason"),
    }
    terminal_errors = {
        "cancelled": ("attempt_cancelled", "Assessment attempt was cancelled."),
        "expired": ("attempt_expired", "Assessment attempt has expired."),
        "completed": ("attempt_completed", "Assessment attempt is already completed."),
    }
    status = str(attempt.get("status") or "")
    if status in terminal_errors:
        code, message = terminal_errors[status]
        raise lifecycle.AssessmentAuthorityError(code, message, status_code=409)
    if token["revoked_at"]:
        raise lifecycle.AssessmentAuthorityError("token_revoked", "Assessment link has been revoked.", status_code=403)
    if token["expires_at"] and token["expires_at"] <= datetime.now(timezone.utc):
        raise lifecycle.AssessmentAuthorityError("token_expired", "Assessment link has expired.", status_code=403)
    return attempt, token


def expire_attempt_if_due(
    cur: Any,
    attempt: dict[str, Any],
    *,
    actor_type: str = "system",
) -> dict[str, Any]:
    expires_at = attempt.get("expires_at")
    status = str(attempt.get("status") or "")
    if status not in lifecycle.OPEN_ATTEMPT_STATUSES or not expires_at or expires_at > datetime.now(timezone.utc):
        return attempt
    cur.execute(
        """
        UPDATE assessment_attempts
        SET status='expired', expired_at=COALESCE(expired_at,now()), updated_at=now()
        WHERE attempt_id=%s AND company_code=%s AND status IN ('pending','in_progress')
        RETURNING *
        """,
        (attempt["attempt_id"], attempt["company_code"]),
    )
    expired = _dict(cur.fetchone()) or attempt
    lifecycle.revoke_active_tokens(
        cur,
        attempt_id=str(attempt["attempt_id"]),
        company_code=str(attempt["company_code"]),
        reason="attempt_expired",
        actor_type=actor_type,
    )
    lifecycle.record_event(
        cur,
        attempt_id=str(attempt["attempt_id"]),
        company_code=str(attempt["company_code"]),
        event_type="expired",
        actor_type=actor_type,
        from_status=status,
        to_status="expired",
    )
    return expired


def create_invitation(
    cur: Any,
    *,
    attempt_id: str,
    company_code: str,
    app_key: str,
    channel: str,
    token_id: str,
    message_kind: str,
    status: str = "pending",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO assessment_invitations
          (attempt_id, company_code, app_key, channel, status, token_id,
           message_kind, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            attempt_id,
            str(company_code).upper(),
            app_key,
            channel,
            status,
            token_id,
            message_kind,
            Json(metadata or {}),
        ),
    )
    return dict(cur.fetchone())


def update_invitation_delivery(
    cur: Any,
    *,
    invitation_id: str,
    company_code: str,
    status: str,
    outbound_event_id: str | None = None,
    last_error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if status not in lifecycle.DELIVERY_STATUSES:
        raise lifecycle.AssessmentAuthorityError("invalid_delivery_status", "Unsupported assessment delivery status.")
    cur.execute(
        """
        UPDATE assessment_invitations
        SET status=%s,
            outbound_event_id=COALESCE(%s,outbound_event_id),
            sent_at=CASE WHEN %s='sent' THEN COALESCE(sent_at,now()) ELSE sent_at END,
            failed_at=CASE WHEN %s='failed' THEN COALESCE(failed_at,now()) ELSE failed_at END,
            last_error=%s,
            metadata=metadata || %s::jsonb,
            updated_at=now()
        WHERE invitation_id=%s AND company_code=%s
        RETURNING *
        """,
        (
            status,
            outbound_event_id,
            status,
            status,
            last_error,
            lifecycle.canonical_json(metadata or {}),
            invitation_id,
            str(company_code).upper(),
        ),
    )
    return _dict(cur.fetchone())


def deterministic_draft_review(draft: dict[str, Any]) -> dict[str, Any]:
    """Run schema/content checks only; never approve or publish."""

    prompt = str(draft.get("prompt_text") or "").strip()
    choices = draft.get("choices") if isinstance(draft.get("choices"), list) else []
    keys = [str(choice.get("key") or "").upper() for choice in choices if isinstance(choice, dict)]
    answer_key = str(draft.get("proposed_answer_key") or "").upper()
    findings: dict[str, Any] = {
        "schema_valid": bool(prompt and 2 <= len(choices) <= 6 and len(keys) == len(set(keys))),
        "answer_key_present": bool(answer_key and answer_key in keys),
        "choice_count": len(choices),
        "duplicate_choice_keys": sorted({key for key in keys if keys.count(key) > 1}),
        "answer_leakage": bool(answer_key and re.search(rf"\b(?:answer|correct)\s*(?:is|:)\s*{re.escape(answer_key)}\b", prompt, re.I)),
        "empty_choices": [
            index for index, choice in enumerate(choices)
            if not isinstance(choice, dict) or not str(choice.get("text") or "").strip()
        ],
    }
    findings["passed"] = bool(
        findings["schema_valid"]
        and findings["answer_key_present"]
        and not findings["answer_leakage"]
        and not findings["empty_choices"]
    )
    return findings


def authoring_enabled(environment: str | None, flag_value: str | None) -> bool:
    if str(environment or "").strip().lower() == "production":
        return False
    return str(flag_value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
