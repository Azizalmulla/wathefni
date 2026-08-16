"""Multi-User Wave 5 — concurrency / collaboration safety.

Optimistic concurrency contract for shared editable HR records.
Mutations must send expected_version and/or expected_updated_at.
Stale writes return HTTP 409 with a human-readable conflict envelope —
never silent last-write-wins.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

CONFLICT_MESSAGE_EN = "This was updated by another user. Review the latest version before saving."
CONFLICT_MESSAGE_AR = "تم تحديث هذا السجل بواسطة مستخدم آخر. راجع أحدث نسخة قبل الحفظ."
SAFE_NEXT_ACTION = "reload_latest"
SAFE_NEXT_ACTION_LABEL_EN = "Refresh and review the latest version before saving."
SAFE_NEXT_ACTION_LABEL_AR = "حدّث الصفحة وراجع أحدث نسخة قبل الحفظ."

STALE_CODES = frozenset(
    {
        "stale_version",
        "stale_update",
        "stale_job_version",
        "stale_job_update",
        "stale_note_version",
        "stale_task_version",
        "stale_ownership_version",
        "stale_lifecycle_version",
        "stale_settings_version",
        "stale_settings_update",
        "stale_interview_notes",
        "stale_assessment_review",
        "missing_expected_version",
    }
)


class ConcurrencyError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        http_status: int = 409,
        details: Mapping[str, Any] | None = None,
    ):
        super().__init__(message or CONFLICT_MESSAGE_EN)
        self.code = code
        self.message = message or CONFLICT_MESSAGE_EN
        self.http_status = http_status
        self.details = dict(details or {})

    def as_detail(self) -> dict[str, Any]:
        # details may already be a full conflict envelope — avoid re-wrapping kwargs.
        if self.details.get("conflict") and self.details.get("error"):
            merged = dict(self.details)
            merged["error"] = self.code
            merged["message"] = self.message or merged.get("message") or CONFLICT_MESSAGE_EN
            return merged
        known = {
            "current_version",
            "expected_version",
            "current_updated_at",
            "expected_updated_at",
            "last_changed_by",
            "last_changed_at",
            "entity_type",
            "entity_id",
        }
        kwargs = {key: self.details[key] for key in known if key in self.details}
        extra = {
            key: value
            for key, value in self.details.items()
            if key not in known
            and key
            not in {
                "ok",
                "error",
                "message",
                "message_ar",
                "conflict",
                "safe_next_action",
                "safe_next_action_label",
                "safe_next_action_label_ar",
                "extra",
            }
        }
        if self.details.get("extra") and isinstance(self.details.get("extra"), dict):
            extra = {**self.details["extra"], **extra}
        if extra:
            kwargs["extra"] = extra
        return conflict_envelope(code=self.code, message=self.message, **kwargs)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    text = _text(value)
    return text or None


def actor_label(actor: Mapping[str, Any] | None) -> str | None:
    data = actor if isinstance(actor, Mapping) else {}
    for key in ("name", "updated_by_name", "actor_name", "email", "updated_by_email", "actor_email", "user_id", "updated_by_user_id", "actor_user_id", "phone", "updated_by_phone"):
        label = _text(data.get(key))
        if label:
            return label
    return None


def conflict_envelope(
    *,
    code: str,
    message: str | None = None,
    current_version: Any = None,
    expected_version: Any = None,
    current_updated_at: Any = None,
    expected_updated_at: Any = None,
    last_changed_by: Any = None,
    last_changed_at: Any = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    changed_by = last_changed_by
    if isinstance(changed_by, Mapping):
        changed_by_payload = {
            "user_id": _text(changed_by.get("user_id") or changed_by.get("updated_by_user_id") or changed_by.get("actor_user_id")) or None,
            "name": _text(changed_by.get("name") or changed_by.get("updated_by_name") or changed_by.get("actor_name")) or None,
            "email": _text(changed_by.get("email") or changed_by.get("updated_by_email") or changed_by.get("actor_email")) or None,
            "label": actor_label(changed_by),
        }
    elif changed_by:
        changed_by_payload = {"label": _text(changed_by)}
    else:
        changed_by_payload = None

    payload: dict[str, Any] = {
        "ok": False,
        "error": code,
        "message": message or CONFLICT_MESSAGE_EN,
        "message_ar": CONFLICT_MESSAGE_AR,
        "conflict": True,
        "current_version": current_version,
        "expected_version": expected_version,
        "current_updated_at": _iso(current_updated_at) or current_updated_at,
        "expected_updated_at": _iso(expected_updated_at) or expected_updated_at,
        "last_changed_by": changed_by_payload,
        "last_changed_at": _iso(last_changed_at) or _iso(current_updated_at) or last_changed_at,
        "safe_next_action": SAFE_NEXT_ACTION,
        "safe_next_action_label": SAFE_NEXT_ACTION_LABEL_EN,
        "safe_next_action_label_ar": SAFE_NEXT_ACTION_LABEL_AR,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }
    if extra:
        payload.update(dict(extra))
    for key in ("current_version", "expected_version"):
        raw = payload.get(key)
        if raw is None or raw == "":
            continue
        try:
            payload[key] = int(raw)
        except (TypeError, ValueError):
            pass
    return payload


def require_expected_token(
    *,
    expected_version: Any = None,
    expected_updated_at: Any = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> None:
    has_version = expected_version is not None and _text(expected_version) != ""
    has_updated = bool(_text(expected_updated_at))
    if has_version or has_updated:
        return
    raise ConcurrencyError(
        "missing_expected_version",
        message="This save needs the current version. Reload the latest record, then try again.",
        http_status=422,
        details={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "safe_next_action": SAFE_NEXT_ACTION,
        },
    )


def assert_fresh(
    *,
    current_version: Any = None,
    expected_version: Any = None,
    current_updated_at: Any = None,
    expected_updated_at: Any = None,
    last_changed_by: Any = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    code_version: str = "stale_version",
    code_updated_at: str = "stale_update",
    require_token: bool = True,
) -> None:
    if require_token:
        require_expected_token(
            expected_version=expected_version,
            expected_updated_at=expected_updated_at,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    if expected_version is not None and _text(expected_version) != "":
        try:
            expected = int(expected_version)
            current = int(current_version if current_version is not None else 0)
        except (TypeError, ValueError) as exc:
            raise ConcurrencyError(
                "missing_expected_version",
                message="Invalid version token. Reload the latest record, then try again.",
                http_status=422,
                details={"entity_type": entity_type, "entity_id": entity_id},
            ) from exc
        if expected != current:
            raise ConcurrencyError(
                code_version,
                details={
                    "current_version": current,
                    "expected_version": expected,
                    "current_updated_at": current_updated_at,
                    "last_changed_by": last_changed_by,
                    "last_changed_at": current_updated_at,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                },
            )
    if _text(expected_updated_at):
        current = _iso(current_updated_at) or _text(current_updated_at)
        expected = _iso(expected_updated_at) or _text(expected_updated_at)
        if current != expected:
            raise ConcurrencyError(
                code_updated_at,
                details={
                    "current_version": current_version,
                    "expected_version": expected_version,
                    "current_updated_at": current,
                    "expected_updated_at": expected,
                    "last_changed_by": last_changed_by,
                    "last_changed_at": current,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                },
            )


def ensure_company_settings_concurrency_schema(cur: Any) -> None:
    cur.execute(
        """
        ALTER TABLE IF EXISTS company_settings
          ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1,
          ADD COLUMN IF NOT EXISTS updated_by_user_id text,
          ADD COLUMN IF NOT EXISTS updated_by_name text,
          ADD COLUMN IF NOT EXISTS updated_by_email text
        """
    )


def settings_concurrency_meta(row: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(row or {})
    return {
        "version": int(data.get("version") or 1),
        "updated_at": _iso(data.get("updated_at")),
        "updated_by_user_id": _text(data.get("updated_by_user_id")) or None,
        "updated_by_name": _text(data.get("updated_by_name")) or None,
        "updated_by_email": _text(data.get("updated_by_email")) or None,
        "last_updated_by": actor_label(
            {
                "name": data.get("updated_by_name"),
                "email": data.get("updated_by_email"),
                "user_id": data.get("updated_by_user_id"),
            }
        ),
    }
