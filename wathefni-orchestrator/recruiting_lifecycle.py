"""Canonical Recruiting Lifecycle — single application transition authority.

Application stages (only):
  awaiting_cv → cv_processing → ready_for_review → shortlisted → interview → hired
  terminal alternatives: rejected, withdrawn

Orthogonal facets (not application stages):
  CV processing, screening, interview details, intake source, candidate communication.

Gated by WATHEFNI_CANONICAL_LIFECYCLE (default OFF). Staging enables it for proof.
AI may propose transitions but never execute them without a separate human confirmation.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Canonical vocabulary
# ---------------------------------------------------------------------------

APPLICATION_STAGES = (
    "awaiting_cv",
    "cv_processing",
    "ready_for_review",
    "shortlisted",
    "interview",
    "hired",
    "rejected",
    "withdrawn",
)

TERMINAL_STAGES = frozenset({"hired", "rejected", "withdrawn"})

# Intake / import item states — never application lifecycle stages.
INTAKE_STATUSES = frozenset({"needs_role", "import_review", "import_archived"})

# Legacy application.status / current_step → canonical stage.
LEGACY_STATUS_MAP: dict[str, str] = {
    "awaiting_cv": "awaiting_cv",
    "cv_request": "awaiting_cv",
    "cv_upload": "awaiting_cv",
    "cv_received": "cv_processing",
    "cv_processing": "cv_processing",
    "screening": "cv_processing",  # screening facet may still be pending
    "screening_complete": "ready_for_review",
    "review_pending": "ready_for_review",
    "ready_for_review": "ready_for_review",
    "shortlisted": "shortlisted",
    "interview": "interview",
    "scheduled": "interview",
    "hired": "hired",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
    # Offer labels are legacy read aliases only — map into shortlisted until offer phase.
    "offered": "shortlisted",
    "offer_sent": "shortlisted",
}

# Strict allowed transitions (from → frozenset(to)).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "awaiting_cv": frozenset({"cv_processing", "withdrawn", "rejected"}),
    "cv_processing": frozenset({"ready_for_review", "awaiting_cv", "withdrawn", "rejected"}),
    "ready_for_review": frozenset({"shortlisted", "interview", "rejected", "withdrawn"}),
    "shortlisted": frozenset({"interview", "hired", "rejected", "withdrawn", "ready_for_review"}),
    "interview": frozenset({"shortlisted", "hired", "rejected", "withdrawn"}),
    "hired": frozenset(),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
}

# Human-gated decision actions → required entitlement + target stage.
HUMAN_DECISION_ACTIONS: dict[str, dict[str, str]] = {
    "shortlist": {"target": "shortlisted", "permission": "candidate.manage"},
    "reject": {"target": "rejected", "permission": "candidate.decide"},
    "hire": {"target": "hired", "permission": "candidate.decide"},
    "schedule_interview": {"target": "interview", "permission": "interview.manage"},
}

SYSTEM_TRIGGERS = frozenset(
    {
        "cv_received",
        "cv_processing_success",
        "cv_processing_failed",
        "explicit_apply",
        "intake_admit",
    }
)

COMMUNICATION_STATES = ("pending", "sent", "failed", "intentionally_skipped")

_COMMUNICATION_LEGACY_MAP: dict[str, str] = {
    "pending": "pending",
    "queued": "pending",
    "retrying": "pending",
    "throttled": "pending",
    "sent": "sent",
    "delivered": "sent",
    "delivered_whatsapp": "sent",
    "delivered_template": "sent",
    "sent_email_fallback": "sent",
    "completed": "sent",
    "recovered": "sent",
    "failed": "failed",
    "needs_hr_action": "failed",
    "suppressed": "intentionally_skipped",
    "dashboard_only": "intentionally_skipped",
    "intentionally_skipped": "intentionally_skipped",
    "skipped": "intentionally_skipped",
}

STAGE_LABELS: dict[str, str] = {
    "awaiting_cv": "Waiting for CV",
    "cv_processing": "Processing CV",
    "ready_for_review": "Ready for review",
    "shortlisted": "Shortlisted",
    "interview": "Interview",
    "hired": "Hired",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}

READY_FOR_REVIEW_TASK_TYPE = "candidate_ready_for_review"
CV_ATTENTION_TASK_TYPE = "candidate_cv_attention"

_ON_VALUES = {"1", "true", "on", "yes", "all", "enabled"}
_OFF_VALUES = {"", "0", "false", "off", "no", "disabled"}


def canonical_lifecycle_enabled() -> bool:
    """Master switch. Default OFF — production unchanged until explicitly enabled."""
    return (os.environ.get("WATHEFNI_CANONICAL_LIFECYCLE") or "").strip().lower() in _ON_VALUES


def normalize_stage(raw: Any) -> str | None:
    """Map any legacy/current status string to a canonical application stage."""
    key = str(raw or "").strip().lower()
    if not key:
        return None
    if key in INTAKE_STATUSES:
        return None  # intake is a separate facet
    if key in APPLICATION_STAGES:
        return key
    return LEGACY_STATUS_MAP.get(key)


def stage_label(raw: Any) -> str:
    stage = normalize_stage(raw) or str(raw or "").strip().lower()
    if stage in STAGE_LABELS:
        return STAGE_LABELS[stage]
    spaced = stage.replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:] if spaced else "Unknown"


def is_ready_for_review(raw: Any) -> bool:
    return normalize_stage(raw) == "ready_for_review"


def normalize_communication_status(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    if key in COMMUNICATION_STATES:
        return key
    return _COMMUNICATION_LEGACY_MAP.get(key, "pending" if key else "intentionally_skipped")


def allowed_targets(from_stage: str) -> frozenset[str]:
    return ALLOWED_TRANSITIONS.get(from_stage, frozenset())


def transition_is_allowed(from_stage: str, to_stage: str) -> bool:
    if from_stage == to_stage:
        return True  # idempotent no-op
    return to_stage in allowed_targets(from_stage)


def permission_for_target(to_stage: str) -> str | None:
    for spec in HUMAN_DECISION_ACTIONS.values():
        if spec["target"] == to_stage:
            return spec["permission"]
    return None


def human_confirmation_required(to_stage: str, *, trigger: str) -> bool:
    if trigger in SYSTEM_TRIGGERS:
        return False
    return to_stage in {"shortlisted", "interview", "hired", "rejected"}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_lifecycle_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS application_lifecycle_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          from_stage text,
          to_stage text NOT NULL,
          trigger text NOT NULL,
          actor_type text NOT NULL DEFAULT 'system',
          actor_user_id uuid,
          actor_phone text,
          channel text,
          confirmation_token text,
          idempotency_key text,
          expected_from_stage text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS application_lifecycle_events_idempotency_uq
          ON application_lifecycle_events (company_code, idempotency_key)
          WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS application_lifecycle_events_app_idx
          ON application_lifecycle_events (company_code, app_key, created_at DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_application_bindings (
          binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          conversation_id text NOT NULL,
          account_id text,
          phone text NOT NULL,
          app_key text NOT NULL,
          bound_reason text NOT NULL DEFAULT 'explicit',
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          bound_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, conversation_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS conversation_application_bindings_phone_idx
          ON conversation_application_bindings (company_code, phone, updated_at DESC)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS conversation_application_bindings_app_idx
          ON conversation_application_bindings (company_code, app_key)
        """
    )
    # Idempotent ready-for-review tasks: one open task per (company, app_key, cv_version).
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS hr_tasks_ready_for_review_open_uq
          ON hr_tasks (
            company_code,
            task_type,
            (metadata->>'app_key'),
            (COALESCE(metadata->>'cv_version', ''))
          )
          WHERE status = 'open'
            AND task_type = 'candidate_ready_for_review'
            AND metadata ? 'app_key'
        """
    )


# ---------------------------------------------------------------------------
# Conversation binding (WhatsApp)
# ---------------------------------------------------------------------------

def bind_conversation_application(
    legacy: Any,
    *,
    company_code: str,
    conversation_id: str,
    phone: str,
    app_key: str,
    account_id: str | None = None,
    bound_reason: str = "explicit",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    conv = str(conversation_id or "").strip()
    app = str(app_key or "").strip()
    phone_digits = legacy.digits(phone)
    if not company or not conv or not app or not phone_digits:
        return {"ok": False, "error": "invalid_binding_inputs"}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_application_bindings
                  (company_code, conversation_id, account_id, phone, app_key, bound_reason, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, conversation_id) DO UPDATE SET
                  account_id = COALESCE(EXCLUDED.account_id, conversation_application_bindings.account_id),
                  phone = EXCLUDED.phone,
                  app_key = EXCLUDED.app_key,
                  bound_reason = EXCLUDED.bound_reason,
                  metadata = conversation_application_bindings.metadata || EXCLUDED.metadata,
                  updated_at = now()
                RETURNING *
                """,
                (
                    company,
                    conv,
                    account_id,
                    phone_digits,
                    app,
                    bound_reason,
                    legacy.Json(legacy.json_safe(metadata or {})),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return {"ok": True, "binding": legacy.json_safe(dict(row)) if row else None}


def resolve_conversation_application(
    legacy: Any,
    *,
    phone: str | None,
    conversation_id: str | None = None,
    company_code: str | None = None,
    account_id: str | None = None,
    allow_single_eligible: bool = True,
) -> dict[str, Any]:
    """Resolve the application for a WhatsApp mutation.

    Fail closed:
      - no conversation binding and 0 or >1 eligible apps → ambiguity / missing
      - binding that does not match phone/company/non-terminal → invalid_binding
    """
    phone_digits = legacy.digits(phone)
    if not phone_digits:
        return {"ok": False, "error": "missing_phone", "application": None}
    company = str(company_code or "").strip().upper() or None
    conv = str(conversation_id or "").strip() or None

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            binding = None
            if conv:
                cur.execute(
                    """
                    SELECT *
                    FROM conversation_application_bindings
                    WHERE conversation_id=%s
                      AND (%s IS NULL OR company_code=%s)
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (conv, company, company),
                )
                binding = cur.fetchone()
                if binding:
                    binding = dict(binding)
                    if legacy.digits(binding.get("phone")) != phone_digits:
                        return {
                            "ok": False,
                            "error": "binding_phone_mismatch",
                            "application": None,
                            "binding": legacy.json_safe(binding),
                        }
                    cur.execute(
                        """
                        SELECT *
                        FROM applications
                        WHERE app_key=%s
                          AND phone=%s
                          AND (%s IS NULL OR company_code=%s)
                        LIMIT 1
                        """,
                        (binding["app_key"], phone_digits, company or binding.get("company_code"), company or binding.get("company_code")),
                    )
                    app_row = cur.fetchone()
                    if not app_row:
                        return {
                            "ok": False,
                            "error": "binding_application_missing",
                            "application": None,
                            "binding": legacy.json_safe(binding),
                        }
                    app = dict(app_row)
                    stage = normalize_stage(app.get("status"))
                    if stage in TERMINAL_STAGES:
                        return {
                            "ok": False,
                            "error": "binding_application_terminal",
                            "application": legacy.json_safe(app),
                            "stage": stage,
                            "binding": legacy.json_safe(binding),
                        }
                    if str(app.get("status") or "").strip().lower() in INTAKE_STATUSES:
                        return {
                            "ok": False,
                            "error": "binding_application_held_intake",
                            "application": legacy.json_safe(app),
                            "binding": legacy.json_safe(binding),
                        }
                    return {
                        "ok": True,
                        "application": app,
                        "stage": stage,
                        "binding": legacy.json_safe(binding),
                        "resolution": "conversation_binding",
                    }

            # No binding: list eligible non-terminal applications for this phone.
            cur.execute(
                """
                SELECT *
                FROM applications
                WHERE phone=%s
                  AND (%s IS NULL OR company_code=%s)
                  AND COALESCE(LOWER(status), '') NOT IN ('needs_role','import_review','import_archived')
                ORDER BY updated_at DESC NULLS LAST, ingested_at DESC NULLS LAST
                """,
                (phone_digits, company, company),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            eligible = []
            for row in rows:
                stage = normalize_stage(row.get("status"))
                if stage is None:
                    continue
                if stage in TERMINAL_STAGES:
                    continue
                eligible.append(row)

            if len(eligible) == 1 and allow_single_eligible:
                only = eligible[0]
                return {
                    "ok": True,
                    "application": only,
                    "stage": normalize_stage(only.get("status")),
                    "binding": None,
                    "resolution": "single_eligible",
                    "requires_bind": True,
                }
            if not eligible:
                return {
                    "ok": False,
                    "error": "no_eligible_application",
                    "application": None,
                    "matches": [],
                }
            return {
                "ok": False,
                "error": "ambiguous_applications",
                "application": None,
                "matches": [
                    {
                        "app_key": r.get("app_key"),
                        "company_code": r.get("company_code"),
                        "position_code": r.get("position_code"),
                        "status": r.get("status"),
                        "stage": normalize_stage(r.get("status")),
                    }
                    for r in eligible
                ],
            }


# ---------------------------------------------------------------------------
# Transition authority
# ---------------------------------------------------------------------------

def _load_application(cur: Any, *, app_key: str, company_code: str | None) -> dict[str, Any] | None:
    if company_code:
        cur.execute(
            "SELECT * FROM applications WHERE app_key=%s AND company_code=%s FOR UPDATE",
            (app_key, company_code),
        )
    else:
        cur.execute("SELECT * FROM applications WHERE app_key=%s FOR UPDATE", (app_key,))
    row = cur.fetchone()
    return dict(row) if row else None


def transition_application(
    legacy: Any,
    *,
    app_key: str,
    to_stage: str,
    trigger: str,
    company_code: str | None = None,
    expected_from_stage: str | None = None,
    actor_type: str = "human",
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    channel: str | None = None,
    confirmation_token: str | None = None,
    human_confirmed: bool = False,
    idempotency_key: str | None = None,
    permissions: set[str] | list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    run_hire_side_effects: bool = True,
) -> dict[str, Any]:
    """Single write authority for application stage changes.

    Fail closed on:
      - unknown target stage
      - disallowed transition
      - stale expected_from_stage
      - missing human confirmation for decision actions
      - missing permission
      - AI actor attempting a decision transition
    """
    target = normalize_stage(to_stage) or str(to_stage or "").strip().lower()
    if target not in APPLICATION_STAGES:
        return {"ok": False, "error": "invalid_target_stage", "to_stage": target}

    if actor_type == "ai" and human_confirmation_required(target, trigger=trigger):
        return {
            "ok": False,
            "error": "ai_cannot_mutate_stage",
            "message": "AI may propose this change but cannot execute it.",
            "to_stage": target,
        }

    if human_confirmation_required(target, trigger=trigger) and not human_confirmed:
        return {
            "ok": False,
            "error": "confirmation_required",
            "to_stage": target,
            "message": "Human confirmation is required for this transition.",
        }

    required_perm = permission_for_target(target) if human_confirmation_required(target, trigger=trigger) else None
    if required_perm:
        perms = {str(p) for p in (permissions or [])}
        if required_perm not in perms and actor_type != "system":
            return {
                "ok": False,
                "error": "permission_denied",
                "required_permission": required_perm,
                "to_stage": target,
            }

    company = str(company_code or "").strip().upper() or None
    idem = str(idempotency_key or "").strip() or None

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            if idem:
                cur.execute(
                    """
                    SELECT * FROM application_lifecycle_events
                    WHERE company_code = COALESCE(%s, company_code)
                      AND idempotency_key=%s
                    LIMIT 1
                    """,
                    (company, idem),
                )
                existing_event = cur.fetchone()
                if existing_event:
                    ev = dict(existing_event)
                    cur.execute(
                        "SELECT * FROM applications WHERE app_key=%s LIMIT 1",
                        (ev.get("app_key") or app_key,),
                    )
                    app_now = cur.fetchone()
                    return {
                        "ok": True,
                        "idempotent": True,
                        "from_stage": ev.get("from_stage"),
                        "to_stage": ev.get("to_stage"),
                        "application": legacy.json_safe(dict(app_now)) if app_now else None,
                        "event": legacy.json_safe(ev),
                    }

            app = _load_application(cur, app_key=app_key, company_code=company)
            if not app:
                return {"ok": False, "error": "application_not_found", "app_key": app_key}

            app_company = str(app.get("company_code") or "").strip().upper()
            if company and app_company != company:
                return {"ok": False, "error": "tenant_mismatch", "app_key": app_key}

            raw_status = str(app.get("status") or "").strip().lower()
            if raw_status in INTAKE_STATUSES and trigger not in {"intake_admit"}:
                return {
                    "ok": False,
                    "error": "held_intake_application",
                    "status": raw_status,
                    "message": "Held intake applications must be admitted before lifecycle transitions.",
                }

            from_stage = normalize_stage(raw_status)
            if from_stage is None and trigger == "intake_admit":
                from_stage = "ready_for_review"
            if from_stage is None:
                return {
                    "ok": False,
                    "error": "unmapped_status",
                    "status": raw_status,
                    "message": "Application status is not mappable to the canonical lifecycle.",
                }

            if expected_from_stage:
                expected = normalize_stage(expected_from_stage) or str(expected_from_stage).strip().lower()
                if expected != from_stage:
                    return {
                        "ok": False,
                        "error": "stale_state",
                        "from_stage": from_stage,
                        "expected_from_stage": expected,
                        "message": "Application stage changed since this action was prepared.",
                    }

            if not transition_is_allowed(from_stage, target):
                return {
                    "ok": False,
                    "error": "transition_not_allowed",
                    "from_stage": from_stage,
                    "to_stage": target,
                    "allowed": sorted(allowed_targets(from_stage)),
                }

            if from_stage == target:
                return {
                    "ok": True,
                    "idempotent": True,
                    "noop": True,
                    "from_stage": from_stage,
                    "to_stage": target,
                    "application": legacy.json_safe(app),
                }

            cur.execute(
                """
                UPDATE applications
                SET status=%s,
                    current_step=%s,
                    updated_at=CURRENT_DATE
                WHERE app_key=%s
                  AND company_code=%s
                RETURNING *
                """,
                (target, target, app["app_key"], app_company),
            )
            updated = cur.fetchone()
            if not updated:
                return {"ok": False, "error": "update_failed", "app_key": app_key}

            event_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO application_lifecycle_events (
                  event_id, company_code, app_key, from_stage, to_stage, trigger,
                  actor_type, actor_user_id, actor_phone, channel, confirmation_token,
                  idempotency_key, expected_from_stage, metadata
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    event_id,
                    app_company,
                    app["app_key"],
                    from_stage,
                    target,
                    trigger,
                    actor_type,
                    actor_user_id,
                    legacy.digits(actor_phone) or None,
                    channel,
                    confirmation_token,
                    idem,
                    expected_from_stage,
                    legacy.Json(legacy.json_safe(metadata or {})),
                ),
            )
            event = dict(cur.fetchone())
        conn.commit()

    result: dict[str, Any] = {
        "ok": True,
        "from_stage": from_stage,
        "to_stage": target,
        "application": legacy.json_safe(dict(updated)),
        "event": legacy.json_safe(event),
        "trigger": trigger,
    }

    if target == "hired" and run_hire_side_effects and hasattr(legacy, "transition_hire"):
        try:
            hire_app = dict(updated)
            posthire = legacy.transition_hire(hire_app)
            result["posthire"] = legacy.json_safe(posthire) if isinstance(posthire, dict) else {"ok": False}
            if not (isinstance(posthire, dict) and posthire.get("ok")):
                result["ok"] = False
                result["error"] = "hire_side_effects_failed"
        except Exception as exc:  # noqa: BLE001 — surface as failed hire, leave stage hired for recovery
            result["ok"] = False
            result["error"] = "hire_side_effects_failed"
            result["posthire"] = {"ok": False, "error": str(exc)}

    if target == "ready_for_review" and trigger == "cv_processing_success":
        task = ensure_ready_for_review_task(
            legacy,
            company_code=app_company,
            application=dict(updated),
            cv_version=_cv_version_from_app(dict(updated), metadata),
        )
        result["hr_task"] = task

    return result


def _cv_version_from_app(app: dict[str, Any], metadata: dict[str, Any] | None) -> str:
    if metadata and metadata.get("cv_version"):
        return str(metadata["cv_version"])
    raw = app.get("raw_json") if isinstance(app.get("raw_json"), dict) else {}
    cv = raw.get("cv") if isinstance(raw.get("cv"), dict) else {}
    storage = cv.get("storage") if isinstance(cv.get("storage"), dict) else {}
    for key in ("content_sha256", "checksum", "document_id", "file_id"):
        value = storage.get(key) or cv.get(key) or (metadata or {}).get(key)
        if value:
            return str(value)
    # Stable fallback from app_key + cv_received_at.
    seed = f"{app.get('app_key')}|{app.get('cv_received_at')}|{cv.get('path') or ''}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def ensure_ready_for_review_task(
    legacy: Any,
    *,
    company_code: str,
    application: dict[str, Any],
    cv_version: str,
) -> dict[str, Any]:
    """Create or reopen an idempotent candidate_ready_for_review HR task."""
    company = str(company_code or "").strip().upper()
    app_key = str(application.get("app_key") or "").strip()
    if not company or not app_key:
        return {"ok": False, "error": "missing_app_key"}
    version = str(cv_version or "unknown").strip()
    name = application.get("candidate_name") or application.get("phone") or "Candidate"
    title = f"Review candidate: {name}"
    detail = (
        f"CV processing completed for {app_key}. "
        f"Role: {application.get('position_title') or application.get('position_code') or 'unknown'}."
    )
    metadata = {
        "app_key": app_key,
        "cv_version": version,
        "position_code": application.get("position_code"),
        "phone": legacy.digits(application.get("phone")),
        "lifecycle": True,
    }

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT task_id, status
                FROM hr_tasks
                WHERE company_code=%s
                  AND task_type=%s
                  AND metadata->>'app_key'=%s
                  AND COALESCE(metadata->>'cv_version','')=%s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (company, READY_FOR_REVIEW_TASK_TYPE, app_key, version),
            )
            existing = cur.fetchone()
            if existing:
                existing = dict(existing)
                if existing.get("status") == "open":
                    return {
                        "ok": True,
                        "idempotent": True,
                        "created": False,
                        "task_id": str(existing["task_id"]),
                    }
                cur.execute(
                    """
                    UPDATE hr_tasks
                    SET status='open',
                        title=%s,
                        detail=%s,
                        priority='high',
                        updated_at=now(),
                        resolved_at=NULL,
                        resolved_by_phone=NULL,
                        metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                    WHERE task_id=%s
                    RETURNING task_id
                    """,
                    (title, detail, legacy.Json(legacy.json_safe(metadata)), existing["task_id"]),
                )
                row = cur.fetchone()
                conn.commit()
                return {
                    "ok": True,
                    "idempotent": True,
                    "created": False,
                    "reopened": True,
                    "task_id": str(row["task_id"]) if row else str(existing["task_id"]),
                }

            try:
                cur.execute(
                    """
                    INSERT INTO hr_tasks
                      (company_code, employee_key, task_type, source, title, detail, priority, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING task_id
                    """,
                    (
                        company,
                        None,
                        READY_FOR_REVIEW_TASK_TYPE,
                        "recruiting_lifecycle",
                        title,
                        detail,
                        "high",
                        legacy.Json(legacy.json_safe(metadata)),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return {
                    "ok": True,
                    "idempotent": False,
                    "created": True,
                    "task_id": str(row["task_id"]) if row else None,
                }
            except Exception as exc:  # noqa: BLE001 — unique race → treat as idempotent
                conn.rollback()
                cur.execute(
                    """
                    SELECT task_id FROM hr_tasks
                    WHERE company_code=%s AND task_type=%s
                      AND metadata->>'app_key'=%s
                      AND COALESCE(metadata->>'cv_version','')=%s
                      AND status='open'
                    LIMIT 1
                    """,
                    (company, READY_FOR_REVIEW_TASK_TYPE, app_key, version),
                )
                raced = cur.fetchone()
                if raced:
                    return {
                        "ok": True,
                        "idempotent": True,
                        "created": False,
                        "task_id": str(raced["task_id"]),
                        "race": True,
                    }
                return {"ok": False, "error": "task_create_failed", "detail": str(exc)}


def mark_cv_received(
    legacy: Any,
    *,
    application: dict[str, Any],
    channel: str = "whatsapp",
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """System transition: awaiting_cv → cv_processing when a CV is stored."""
    stage = normalize_stage(application.get("status"))
    if stage not in {None, "awaiting_cv", "cv_processing"}:
        # Already past CV intake — keep stage, still ok.
        return {"ok": True, "skipped": True, "stage": stage, "application": legacy.json_safe(application)}
    if stage == "cv_processing":
        return {"ok": True, "idempotent": True, "stage": stage, "application": legacy.json_safe(application)}
    return transition_application(
        legacy,
        app_key=str(application.get("app_key")),
        company_code=str(application.get("company_code") or ""),
        to_stage="cv_processing",
        trigger="cv_received",
        actor_type="system",
        channel=channel,
        human_confirmed=False,
        metadata={"conversation_id": conversation_id} if conversation_id else None,
    )


def mark_cv_ready_for_review(
    legacy: Any,
    *,
    application: dict[str, Any],
    cv_version: str | None = None,
    document_id: str | None = None,
) -> dict[str, Any]:
    """System transition after successful CV processing → ready_for_review + HR task."""
    stage = normalize_stage(application.get("status"))
    if stage in TERMINAL_STAGES:
        return {"ok": False, "error": "terminal_application", "stage": stage}
    if stage in INTAKE_STATUSES or str(application.get("status") or "").lower() in INTAKE_STATUSES:
        return {"ok": True, "skipped": True, "reason": "held_intake", "stage": stage}
    meta = {"document_id": document_id, "cv_version": cv_version}
    if stage == "ready_for_review":
        task = ensure_ready_for_review_task(
            legacy,
            company_code=str(application.get("company_code") or ""),
            application=application,
            cv_version=cv_version or _cv_version_from_app(application, meta),
        )
        return {"ok": True, "idempotent": True, "to_stage": "ready_for_review", "hr_task": task}
    # Allow from awaiting_cv / cv_processing (and legacy screening* via normalize).
    if stage not in {"awaiting_cv", "cv_processing"}:
        # Already shortlisted/interview — do not regress; still ensure task if requested.
        return {"ok": True, "skipped": True, "stage": stage, "reason": "already_advanced"}
    return transition_application(
        legacy,
        app_key=str(application.get("app_key")),
        company_code=str(application.get("company_code") or ""),
        to_stage="ready_for_review",
        trigger="cv_processing_success",
        actor_type="system",
        channel="system",
        human_confirmed=False,
        metadata=meta,
    )


def allowed_actions_for_stage(
    stage: str | None,
    permissions: set[str] | list[str] | None,
) -> list[str]:
    """Shared web/mobile action list derived from the transition matrix + RBAC."""
    if not stage or stage in TERMINAL_STAGES:
        return []
    perms = {str(p) for p in (permissions or [])}
    actions: list[str] = []
    if "shortlisted" in allowed_targets(stage) and "candidate.manage" in perms:
        actions.append("shortlist")
    if "interview" in allowed_targets(stage) and "interview.manage" in perms:
        actions.append("schedule_interview")
    if "rejected" in allowed_targets(stage) and "candidate.decide" in perms:
        actions.append("reject")
    if "hired" in allowed_targets(stage) and "candidate.decide" in perms:
        actions.append("hire")
    return actions


# Mobile candidate decision endpoint only executes these mutations. schedule_interview
# remains a web/assistant registry action; advertising it on mobile would show a
# button that execution rejects with unsupported_candidate_action.
MOBILE_EXECUTABLE_CANDIDATE_ACTIONS = frozenset({"shortlist", "reject", "hire"})

# Interview mutations that mobile currently executes (notes write). Cancel /
# reschedule / schedule remain web-only until a mobile execute path exists.
MOBILE_EXECUTABLE_INTERVIEW_ACTIONS = frozenset({"write", "write_notes", "read"})


def authorize_recruiting_action(
    action: str,
    stage: str | None,
    permissions: set[str] | list[str] | None,
) -> bool:
    """Single authority check shared by advertisement and execution gating.

    Uses the same transition matrix + permission tokens as allowed_actions_for_stage.
    Does not invent grants from role names.
    """
    requested = str(action or "").strip().lower()
    if not requested:
        return False
    return requested in allowed_actions_for_stage(stage, permissions)


def mobile_candidate_allowed_actions(
    stage: str | None,
    permissions: set[str] | list[str] | None,
) -> list[str]:
    """Candidate actions mobile may advertise — only those the decision API can run."""
    return [
        action
        for action in allowed_actions_for_stage(stage, permissions)
        if action in MOBILE_EXECUTABLE_CANDIDATE_ACTIONS
    ]


def permission_for_recruiting_action(action: str) -> str | None:
    """Permission token required to execute a recruiting human decision."""
    requested = str(action or "").strip().lower()
    if requested == "shortlist":
        return "candidate.manage"
    if requested == "schedule_interview":
        return "interview.manage"
    if requested in {"reject", "hire"}:
        return "candidate.decide"
    if requested in {"write_notes", "write", "cancel_interview", "mark_completed", "mark_no_show", "reschedule"}:
        return "interview.manage"
    return None


def transition_matrix_public() -> list[dict[str, Any]]:
    rows = []
    for src, targets in ALLOWED_TRANSITIONS.items():
        rows.append(
            {
                "from": src,
                "to": sorted(targets),
                "label": STAGE_LABELS.get(src, src),
            }
        )
    return rows


def legacy_mapping_public() -> dict[str, str]:
    return dict(LEGACY_STATUS_MAP)
