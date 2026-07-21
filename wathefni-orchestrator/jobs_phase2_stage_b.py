"""Jobs Phase 2 Stage B — context → application conversion authority.

Converts a uniquely bound temporary job context into a canonical awaiting_cv
application after explicit apply confirmation or a qualifying CV (preview_sent_at
set). Fail-closed; no production tenant fallback; Stage A eligibility preserved.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import recruiting_lifecycle as _rl

STAGE_B_MARKER = "STAGEB-CANARY"
CONVERT_CONFIRM_PREFIX = "jobctx-convert:"
CONVERT_CV_PREFIX = "jobctx-convert-cv:"
PREVIEW_SENT_PREFIX = "jobctx-preview-sent:"

_CONFIRM_EN = re.compile(
    r"\b("
    r"ready\s+to\s+apply|i('?m|\s+am)\s+ready\s+to\s+apply|yes[,\s]+apply|"
    r"confirm\s+apply|i\s+want\s+to\s+apply(\s+now)?|apply\s+now|"
    r"start\s+(my\s+)?application|please\s+apply"
    r")\b",
    re.I,
)
_CONFIRM_AR = re.compile(
    r"(جاهز(ة)?\s+للتقديم|أريد\s+التقديم|ابي\s+اقدم|أبي\s+أقدم|"
    r"نعم[،,]?\s*(قدم|التقديم)|أكد\s+التقديم|ابدأ\s+التقديم|"
    r"قدم\s+الآن|يلا\s+قدم)",
    re.I,
)


def stage_b_enabled() -> bool:
    raw = (os.environ.get("WATHEFNI_STAGE_B_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "on", "yes"}


def stage_b_canary_only() -> bool:
    raw = (os.environ.get("WATHEFNI_STAGE_B_CANARY_ONLY") or "1").strip().lower()
    return raw in {"1", "true", "on", "yes", ""}


def stage_b_live_whatsapp_enabled() -> bool:
    raw = (os.environ.get("WATHEFNI_STAGE_B_LIVE_WHATSAPP") or "").strip().lower()
    return raw in {"1", "true", "on", "yes"}


def stage_b_stamp_dry_run() -> bool:
    """Stamp preview_sent_at on dry-run accept so Stage B can be tested without WA."""
    raw = (os.environ.get("WATHEFNI_STAGE_B_STAMP_DRY_RUN") or "1").strip().lower()
    return raw in {"1", "true", "on", "yes", ""}


def stage_b_rate_limit_per_hour() -> int:
    try:
        return max(1, int((os.environ.get("WATHEFNI_STAGE_B_RATE_LIMIT_PER_HOUR") or "8").strip()))
    except ValueError:
        return 8


def _split_csv_env(name: str, *, default: str = "") -> set[str]:
    raw = (os.environ.get(name) or default).strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def public_canary_positions() -> set[str]:
    """Position codes that may use Stage B convert for anyone (staging public canary)."""
    return _split_csv_env(
        "WATHEFNI_STAGE_B_PUBLIC_POSITIONS",
        default="STAGEB_07210227",
    )


def public_canary_apply_codes() -> set[str]:
    """Exact APPLY codes that may use Stage B convert for anyone."""
    return _split_csv_env(
        "WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES",
        default="APPLY-WATHEFNI-STAGEB_07210227",
    )


def normalize_apply_code(apply_code: str | None) -> str:
    return str(apply_code or "").strip().upper()


def normalize_position_code(position_code: str | None) -> str:
    return str(position_code or "").strip().upper()


def is_public_canary_job(
    *,
    position_code: str | None = None,
    apply_code: str | None = None,
) -> bool:
    pos = normalize_position_code(position_code)
    code = normalize_apply_code(apply_code)
    if pos and pos in public_canary_positions():
        return True
    if code and code in public_canary_apply_codes():
        return True
    return False


def stage_b_convert_allowed_for_job(
    *,
    position_code: str | None = None,
    apply_code: str | None = None,
) -> bool:
    """Stage B convert is enabled only when the flag is on and the job is in scope.

    With WATHEFNI_STAGE_B_CANARY_ONLY=1 (staging default), only the dedicated
    public canary position/APPLY code may convert — for any candidate phone.
    No sender-phone allowlist.
    """
    if not stage_b_enabled():
        return False
    if not stage_b_canary_only():
        # Full Stage B (not used for this staging public canary window).
        return True
    return is_public_canary_job(position_code=position_code, apply_code=apply_code)


# Back-compat wrappers (phone allowlist removed; always job-scoped via callers).
def candidate_allowlist() -> set[str]:
    return set()


def phone_allowlisted(phone: str | None, *, digits_fn: Any) -> bool:
    return False


def stage_b_convert_allowed(phone: str | None, *, digits_fn: Any) -> bool:
    """Deprecated phone gate — always False; use stage_b_convert_allowed_for_job."""
    return False


def parse_apply_confirm(text: str | None) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if _CONFIRM_EN.search(raw) or _CONFIRM_AR.search(raw):
        return True
    normalized = re.sub(r"\s+", " ", raw.lower()).strip()
    return normalized in {
        "apply",
        "apply now",
        "ready",
        "جاهز",
        "جاهزة",
        "قدم",
        "أقدم",
    }


def ensure_stage_b_schema(cur: Any) -> None:
    cur.execute(
        """
        ALTER TABLE IF EXISTS candidate_job_contexts
          ADD COLUMN IF NOT EXISTS converted_at timestamptz;
        ALTER TABLE IF EXISTS candidate_job_contexts
          ADD COLUMN IF NOT EXISTS application_app_key text;
        ALTER TABLE IF EXISTS candidate_job_contexts
          ADD COLUMN IF NOT EXISTS convert_idempotency_key text;
        ALTER TABLE IF EXISTS candidate_job_contexts
          ADD COLUMN IF NOT EXISTS preview_delivery_id text;
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS candidate_job_contexts_convert_idem_uidx
          ON candidate_job_contexts (convert_idempotency_key)
          WHERE convert_idempotency_key IS NOT NULL;
        """
    )


def stamp_preview_sent(
    legacy: Any,
    *,
    context_id: str,
    delivery: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Idempotently set preview_sent_at after a genuine (or dry-run) delivery ack."""
    ctx = str(context_id or "").strip()
    if not ctx:
        return {"ok": False, "error": "missing_context_id"}
    delivery = delivery or {}
    key = idempotency_key or f"{PREVIEW_SENT_PREFIX}{ctx}:{delivery.get('delivery_id') or delivery.get('status') or 'ack'}"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE candidate_job_contexts
                SET preview_sent_at = COALESCE(preview_sent_at, now()),
                    preview_delivery_id = COALESCE(preview_delivery_id, %s),
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE context_id = %s::uuid
                  AND status = 'awaiting_apply_confirmation'
                RETURNING *
                """,
                (
                    str(delivery.get("delivery_id") or delivery.get("conversation_id") or "")[:200] or None,
                    legacy.Json(
                        legacy.json_safe(
                            {
                                "preview_sent_idempotency_key": key,
                                "preview_delivery": {
                                    "ok": bool(delivery.get("ok")),
                                    "dry_run": bool(delivery.get("dry_run")),
                                    "status": delivery.get("status"),
                                    "force_live": bool(delivery.get("force_live")),
                                },
                            }
                        )
                    ),
                    ctx,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return {"ok": False, "error": "context_not_stampable"}
    return {"ok": True, "context": legacy.json_safe(dict(row))}


def _lock_key(phone: str, account_id: str | None, conversation_id: str | None) -> str:
    return "|".join((phone, str(account_id or ""), str(conversation_id or "")))


def _active_same_role(cur: Any, *, phone: str, company: str, position: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *
        FROM applications
        WHERE phone=%s
          AND company_code=%s
          AND position_code=%s
          AND lower(COALESCE(status, '')) NOT IN ('rejected', 'withdrawn', 'hired')
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
        LIMIT 1
        """,
        (phone, company, position),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _pending_media_rows(
    cur: Any,
    *,
    phone: str,
    account_id: str | None,
    conversation_id: str | None,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM candidate_pending_media
        WHERE phone=%s
          AND COALESCE(account_id, '')=COALESCE(%s, '')
          AND (%s IS NULL OR conversation_id=%s)
          AND status='pending'
          AND expires_at > now()
        ORDER BY created_at ASC
        """,
        (phone, account_id, conversation_id, conversation_id),
    )
    return [dict(row) for row in cur.fetchall()]


def convert_job_context_to_application(
    legacy: Any,
    request: Any,
    *,
    trigger: str,
    idempotency_key: str,
    media: dict[str, Any] | None = None,
    canary_marker: str | None = None,
) -> dict[str, Any]:
    """Transactional convert per Stage B contract §3.2."""
    phone = legacy.digits(request.sender_phone)
    if not phone:
        return {"ok": False, "error": "missing_phone", "application_created": False}

    trigger_key = str(trigger or "").strip().lower()
    if trigger_key not in {"apply_confirm", "qualifying_cv"}:
        return {"ok": False, "error": "invalid_convert_trigger", "application_created": False}

    marker = canary_marker or STAGE_B_MARKER
    data_source, data_source_detail = legacy.data_source_from_request(request)

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_stage_b_schema(cur)
            _rl.ensure_lifecycle_schema(cur)
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (_lock_key(phone, request.account_id, request.conversation_id),),
            )

            # Idempotent replay via convert_idempotency_key
            cur.execute(
                """
                SELECT *
                FROM candidate_job_contexts
                WHERE convert_idempotency_key=%s
                LIMIT 1
                """,
                (idempotency_key,),
            )
            prior = cur.fetchone()
            if prior:
                prior = dict(prior)
                app_key = str(prior.get("application_app_key") or "")
                application = None
                if app_key:
                    cur.execute("SELECT * FROM applications WHERE app_key=%s LIMIT 1", (app_key,))
                    row = cur.fetchone()
                    application = dict(row) if row else None
                conn.commit()
                return {
                    "ok": True,
                    "idempotent": True,
                    "application_created": False,
                    "application": legacy.json_safe(application) if application else None,
                    "job_context": legacy.json_safe(prior),
                    "trigger": trigger_key,
                }

            cur.execute(
                """
                SELECT *
                FROM candidate_job_contexts
                WHERE phone=%s
                  AND COALESCE(account_id, '')=COALESCE(%s, '')
                  AND (%s IS NULL OR conversation_id=%s)
                  AND status='awaiting_apply_confirmation'
                  AND expires_at > now()
                ORDER BY updated_at DESC
                LIMIT 2
                FOR UPDATE
                """,
                (phone, request.account_id, request.conversation_id, request.conversation_id),
            )
            contexts = [dict(row) for row in cur.fetchall()]
            if len(contexts) != 1:
                return {
                    "ok": False,
                    "error": "job_context_not_unique" if contexts else "job_context_missing",
                    "application_created": False,
                }
            context = contexts[0]
            if not stage_b_convert_allowed_for_job(
                position_code=str(context.get("position_code") or ""),
                apply_code=str(context.get("apply_code") or ""),
            ):
                return {
                    "ok": False,
                    "error": "stage_b_job_not_enabled",
                    "application_created": False,
                    "job_context": legacy.json_safe(context),
                }
            if not context.get("preview_sent_at"):
                return {
                    "ok": False,
                    "error": "preview_not_sent",
                    "application_created": False,
                    "job_context": legacy.json_safe(context),
                }

            # Rate limit: cap new Stage B canary application creates per phone/hour.
            cur.execute(
                """
                SELECT count(*) AS n
                FROM applications
                WHERE phone=%s
                  AND COALESCE(raw_json->>'stage_b_canary','')='true'
                  AND COALESCE(ingested_at, created_at::timestamptz) > now() - interval '1 hour'
                """,
                (phone,),
            )
            recent = int((cur.fetchone() or {}).get("n") or 0)
            # existing same-role short-circuit below still allowed even if rate limited
            rate_limited = recent >= stage_b_rate_limit_per_hour()

            apply_code = str(context.get("apply_code") or "").strip().upper()
            resolved = legacy.resolve_public_role_by_apply_code(apply_code)
            role = resolved.get("role") if isinstance(resolved.get("role"), dict) else None
            if not resolved.get("ok") or not role:
                return {
                    "ok": False,
                    "error": resolved.get("error") or "job_not_accepting",
                    "details": resolved.get("details"),
                    "application_created": False,
                    "job_context": legacy.json_safe(context),
                }

            company = str(role.get("company_code") or context.get("company_code") or "").strip().upper()
            position = str(role.get("position_code") or context.get("position_code") or "").strip()
            title = str(role.get("title_en") or role.get("title") or position)
            is_canary = is_public_canary_job(
                position_code=position,
                apply_code=apply_code,
            )
            existing = _active_same_role(cur, phone=phone, company=company, position=position)
            if existing:
                cur.execute(
                    """
                    UPDATE candidate_job_contexts
                    SET status='converted',
                        converted_at=COALESCE(converted_at, now()),
                        application_app_key=%s,
                        convert_idempotency_key=%s,
                        updated_at=now(),
                        metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                    WHERE context_id=%s
                    RETURNING *
                    """,
                    (
                        existing.get("app_key"),
                        idempotency_key,
                        legacy.Json(
                            legacy.json_safe(
                                {
                                    "convert_trigger": trigger_key,
                                    "convert_outcome": "existing_application",
                                    "stage_b_marker": marker,
                                }
                            )
                        ),
                        context.get("context_id"),
                    ),
                )
                converted_ctx = dict(cur.fetchone())
                if request.conversation_id:
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
                        """,
                        (
                            company,
                            str(request.conversation_id),
                            request.account_id,
                            phone,
                            existing.get("app_key"),
                            "explicit_apply" if trigger_key == "apply_confirm" else "qualifying_cv",
                            legacy.Json(legacy.json_safe({"stage_b_marker": marker, "trigger": trigger_key})),
                        ),
                    )
                attached = None
                pending_rows = _pending_media_rows(
                    cur,
                    phone=phone,
                    account_id=request.account_id,
                    conversation_id=request.conversation_id,
                )
                attach_media = media
                if not attach_media and pending_rows:
                    attach_media = pending_rows[-1].get("media") if isinstance(pending_rows[-1].get("media"), dict) else None
                if attach_media and legacy.has_current_media_upload(attach_media):
                    attached = legacy.register_candidate_cv_file(
                        cur,
                        application=existing,
                        media=attach_media,
                        metadata={
                            "conversation_id": request.conversation_id,
                            "account_id": request.account_id,
                            "raw_text": request.raw_text,
                            "candidate_locale": context.get("preview_locale"),
                            "stage_b_marker": marker,
                        },
                    )
                    if attached.get("ok") and pending_rows:
                        cur.execute(
                            """
                            UPDATE candidate_pending_media
                            SET status='attached', updated_at=now()
                            WHERE pending_id = ANY(%s::uuid[])
                            """,
                            ([row["pending_id"] for row in pending_rows],),
                        )
                conn.commit()
                return {
                    "ok": True,
                    "application_created": False,
                    "existing_application": True,
                    "application": legacy.json_safe(existing),
                    "job_context": legacy.json_safe(converted_ctx),
                    "role": role,
                    "cv_attach": legacy.json_safe(attached) if attached else None,
                    "trigger": trigger_key,
                }

            if rate_limited:
                return {
                    "ok": False,
                    "error": "stage_b_rate_limited",
                    "application_created": False,
                    "job_context": legacy.json_safe(context),
                    "rate_limit_per_hour": stage_b_rate_limit_per_hour(),
                }

            # New application — include epoch so terminal re-apply gets a new key.
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            app_key = f"{phone}-{company}-{position}"
            cur.execute("SELECT 1 FROM applications WHERE app_key=%s LIMIT 1", (app_key,))
            if cur.fetchone():
                app_key = f"{phone}-{company}-{position}-{suffix}"

            locale = legacy._candidate_messages.normalize_locale(context.get("preview_locale"))
            raw_json = {
                "candidate_locale": locale,
                "source_conversation_id": request.conversation_id,
                "account_id": request.account_id,
                "jobs_phase2_stage": "B",
                "stage_b_marker": marker if is_canary else None,
                "stage_b_canary": is_canary,
                "stage_b_canary_position": position if is_canary else None,
                "stage_b_canary_apply_code": apply_code if is_canary else None,
                "convert_trigger": trigger_key,
                "job_context_id": str(context.get("context_id")),
                "data_source": data_source,
                "data_source_detail": data_source_detail,
                "source_channel": context.get("source_channel"),
                "source_ref_token": context.get("source_ref_token"),
                "source_campaign": context.get("source_campaign"),
            }
            cur.execute(
                """
                INSERT INTO candidates
                  (phone, current_status, active_company_code, active_position_code, raw_json, data_source, data_source_detail)
                VALUES (%s, 'awaiting_cv', %s, %s, %s, %s, %s)
                ON CONFLICT (phone) DO UPDATE SET
                  current_status='awaiting_cv',
                  active_company_code=EXCLUDED.active_company_code,
                  active_position_code=EXCLUDED.active_position_code,
                  raw_json = COALESCE(candidates.raw_json,'{}'::jsonb) || EXCLUDED.raw_json,
                  data_source=EXCLUDED.data_source,
                  data_source_detail=COALESCE(EXCLUDED.data_source_detail, candidates.data_source_detail),
                  updated_at=now()
                """,
                (
                    phone,
                    company,
                    position,
                    legacy.Json(legacy.json_safe({"stage_b_marker": marker, "candidate_locale": locale})),
                    data_source,
                    data_source_detail,
                ),
            )
            cur.execute(
                """
                INSERT INTO applications
                  (app_key, phone, company_code, position_code, apply_code, position_title,
                   status, current_step, cv_received, screening_status, raw_json,
                   data_source, data_source_detail, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,'awaiting_cv','cv_request',false,'not_started',%s,%s,%s,CURRENT_DATE,CURRENT_DATE)
                RETURNING *
                """,
                (
                    app_key,
                    phone,
                    company,
                    position,
                    apply_code,
                    title,
                    legacy.Json(legacy.json_safe(raw_json)),
                    data_source,
                    data_source_detail,
                ),
            )
            application = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO application_lifecycle_events
                  (company_code, app_key, from_stage, to_stage, trigger,
                   actor_type, actor_phone, channel, idempotency_key, metadata)
                VALUES (%s,%s,NULL,'awaiting_cv','explicit_apply','candidate',%s,
                        'whatsapp',%s,%s)
                ON CONFLICT (company_code, idempotency_key)
                  WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
                DO NOTHING
                """,
                (
                    company,
                    app_key,
                    phone,
                    idempotency_key,
                    legacy.Json(
                        legacy.json_safe(
                            {
                                "job_context_id": str(context.get("context_id")),
                                "trigger": trigger_key,
                                "stage_b_canary": is_canary,
                                "stage_b_marker": marker if is_canary else None,
                            }
                        )
                    ),
                ),
            )

            bound_reason = "explicit_apply" if trigger_key == "apply_confirm" else "qualifying_cv"
            if request.conversation_id:
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
                    """,
                    (
                        company,
                        str(request.conversation_id),
                        request.account_id,
                        phone,
                        app_key,
                        bound_reason,
                        legacy.Json(legacy.json_safe({"stage_b_marker": marker, "trigger": trigger_key})),
                    ),
                )

            cur.execute(
                """
                UPDATE candidate_job_contexts
                SET status='converted',
                    converted_at=now(),
                    application_app_key=%s,
                    convert_idempotency_key=%s,
                    updated_at=now(),
                    metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                WHERE context_id=%s
                RETURNING *
                """,
                (
                    app_key,
                    idempotency_key,
                    legacy.Json(
                        legacy.json_safe(
                            {
                                "convert_trigger": trigger_key,
                                "convert_outcome": "created",
                                "stage_b_marker": marker,
                            }
                        )
                    ),
                    context.get("context_id"),
                ),
            )
            converted_ctx = dict(cur.fetchone())

            attached = None
            pending_rows = _pending_media_rows(
                cur,
                phone=phone,
                account_id=request.account_id,
                conversation_id=request.conversation_id,
            )
            attach_media = media
            if not attach_media and pending_rows:
                attach_media = pending_rows[-1].get("media") if isinstance(pending_rows[-1].get("media"), dict) else None
            if attach_media and legacy.has_current_media_upload(attach_media):
                attached = legacy.register_candidate_cv_file(
                    cur,
                    application=application,
                    media=attach_media,
                    metadata={
                        "conversation_id": request.conversation_id,
                        "account_id": request.account_id,
                        "raw_text": request.raw_text,
                        "candidate_locale": locale,
                        "stage_b_marker": marker,
                    },
                )
                if attached.get("ok") and pending_rows:
                    cur.execute(
                        """
                        UPDATE candidate_pending_media
                        SET status='attached', updated_at=now()
                        WHERE pending_id = ANY(%s::uuid[])
                        """,
                        ([row["pending_id"] for row in pending_rows],),
                    )

        conn.commit()

    # Post-commit lifecycle transition when CV attached
    if attached and attached.get("ok") and not attached.get("duplicate"):
        _rl.mark_cv_received(
            legacy,
            application=application,
            channel="whatsapp",
            conversation_id=request.conversation_id,
        )

    return {
        "ok": True,
        "application_created": True,
        "application": legacy.json_safe(application),
        "job_context": legacy.json_safe(converted_ctx),
        "role": role,
        "cv_attach": legacy.json_safe(attached) if attached else None,
        "trigger": trigger_key,
        "bound_reason": bound_reason,
    }


def deliver_and_stamp_job_preview(
    legacy: Any,
    *,
    request: Any,
    context: dict[str, Any],
    preview_text: str,
    company_code: str | None,
) -> dict[str, Any]:
    """Send preview (live for public canary jobs when enabled) and stamp preview_sent_at."""
    context_id = str(context.get("context_id") or "")
    phone = legacy.digits(request.sender_phone)
    force_live = bool(
        stage_b_live_whatsapp_enabled()
        and is_public_canary_job(
            position_code=str(context.get("position_code") or ""),
            apply_code=str(context.get("apply_code") or ""),
        )
    )
    send_kwargs: dict[str, Any] = {
        "account_id": request.account_id,
        "phone": phone,
        "text": preview_text,
        "subject_type": "candidate_job_context",
        "subject_key": context_id,
        "message_kind": "job_context_preview",
        "company_code": company_code,
        "audience": "candidate",
    }
    # force_live is honored by send_octopus_whatsapp when present
    try:
        send = legacy.send_octopus_whatsapp(**send_kwargs, force_live=force_live)
    except TypeError:
        send = legacy.send_octopus_whatsapp(**send_kwargs)

    send = dict(send or {})
    send["force_live"] = force_live
    stamped = False
    stamp_result = None
    should_stamp = bool(send.get("ok")) and (
        force_live or (bool(send.get("dry_run")) and stage_b_stamp_dry_run()) or not legacy.delivery_is_dry_run()
    )
    if should_stamp and context_id:
        stamp_result = stamp_preview_sent(
            legacy,
            context_id=context_id,
            delivery={
                **send,
                "delivery_id": send.get("conversation_id") or send.get("status") or ("live" if force_live else "dry_run"),
            },
        )
        stamped = bool(stamp_result.get("ok"))

    # Suppress channel double-send only when we actually live-sent from orchestrator.
    suppress_reply = bool(force_live and send.get("ok") and not send.get("dry_run"))
    return {
        "ok": bool(send.get("ok")),
        "send": legacy.json_safe(send),
        "stamped": stamped,
        "stamp": legacy.json_safe(stamp_result) if stamp_result else None,
        "suppress_reply": suppress_reply,
        "force_live": force_live,
    }
