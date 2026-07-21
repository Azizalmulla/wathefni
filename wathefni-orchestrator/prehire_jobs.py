"""Canonical Pre-Hiring Jobs authority (Phase 1).

Postgres `positions` is the sole runtime authority for job existence and
lifecycle. Applications never synthesize jobs. Intake accepts only `open`.
"""

from __future__ import annotations

import os
import re
import urllib.parse
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from psycopg2.extras import Json

JOB_STATUSES = ("draft", "open", "paused", "closed")
ACCEPTING_APPLICATIONS_STATUS = "open"
JOB_VISIBILITIES = ("public", "share_only", "internal")
JOB_CONTEXT_STATUSES = ("awaiting_apply_confirmation", "declined", "converted", "expired")
JOB_ACCESS_MODES = ("exact_token", "discovery")
FULLY_REMOTE_ARRANGEMENTS = frozenset({"remote", "fully_remote", "fully remote"})
# Vacancy consumption: only successfully hired applications count.
VACANCY_CONSUMING_STATUSES = ("hired",)

# Allowed transitions: from -> frozenset(to)
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"open", "closed"}),  # publish or abandon-close
    "open": frozenset({"paused", "closed"}),
    "paused": frozenset({"open", "closed"}),  # resume or close
    "closed": frozenset({"open"}),  # reopen only
}

TRANSITION_ACTION = {
    ("draft", "open"): "publish",
    ("draft", "closed"): "close",
    ("open", "paused"): "pause",
    ("open", "closed"): "close",
    ("paused", "open"): "resume",
    ("paused", "closed"): "close",
    ("closed", "open"): "reopen",
}

JOBS_PERMISSIONS = (
    "jobs.read",
    "jobs.create",
    "jobs.edit",
    "jobs.publish",
    "jobs.close",
)

# Temporary compatibility: settings.manage implies these mutation scopes for
# existing administrators until grants are explicitly migrated.
SETTINGS_MANAGE_COMPAT_JOBS = frozenset(
    {"jobs.create", "jobs.edit", "jobs.publish", "jobs.close"}
)

SCHEMA_SQL = """
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS job_id uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS title_ar text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS description_ar text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS requirements_en jsonb;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS requirements_ar jsonb;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS location text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS employment_type text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS work_arrangement text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS contract_type text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS salary_visibility text NOT NULL DEFAULT 'hr_only';
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS vacancies integer;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS application_deadline date;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS expected_start_date date;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS hiring_manager_user_id uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS recruiter_user_id uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS published_at timestamptz;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS closed_at timestamptz;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS created_by_user_id uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS updated_by_user_id uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS title_en text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS visibility text NOT NULL DEFAULT 'public';
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS short_summary_en text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS short_summary_ar text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS content_approved_en_at timestamptz;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS content_approved_en_by uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS content_approved_ar_at timestamptz;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS content_approved_ar_by uuid;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS benefits_en text;
ALTER TABLE IF EXISTS positions ADD COLUMN IF NOT EXISTS benefits_ar text;

UPDATE positions SET job_id = gen_random_uuid() WHERE job_id IS NULL;
UPDATE positions SET title_en = title WHERE title_en IS NULL AND NULLIF(TRIM(title), '') IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS positions_job_id_uidx ON positions (job_id);
CREATE UNIQUE INDEX IF NOT EXISTS positions_company_code_uidx ON positions (company_code, position_code);
CREATE UNIQUE INDEX IF NOT EXISTS positions_apply_code_uidx
  ON positions (upper(apply_code))
  WHERE apply_code IS NOT NULL AND btrim(apply_code) <> '';

CREATE TABLE IF NOT EXISTS candidate_job_contexts (
  context_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone text NOT NULL,
  account_id text,
  conversation_id text,
  company_code text NOT NULL,
  position_code text NOT NULL,
  job_id uuid,
  apply_code text NOT NULL,
  status text NOT NULL DEFAULT 'awaiting_apply_confirmation',
  preview_rendered_at timestamptz,
  preview_sent_at timestamptz,
  preview_locale text,
  preview_template_version text,
  source_channel text,
  source_ref_token text,
  source_campaign text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  data_source text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  CONSTRAINT candidate_job_contexts_status_chk
    CHECK (status IN ('awaiting_apply_confirmation','declined','converted','expired'))
);
ALTER TABLE IF EXISTS candidate_job_contexts ADD COLUMN IF NOT EXISTS preview_rendered_at timestamptz;
CREATE INDEX IF NOT EXISTS candidate_job_contexts_phone_active_idx
  ON candidate_job_contexts (phone, status)
  WHERE status = 'awaiting_apply_confirmation';
CREATE UNIQUE INDEX IF NOT EXISTS candidate_job_contexts_one_active_uidx
  ON candidate_job_contexts (
    phone,
    COALESCE(account_id, ''),
    COALESCE(conversation_id, '')
  )
  WHERE status = 'awaiting_apply_confirmation';
CREATE INDEX IF NOT EXISTS candidate_job_contexts_conv_idx
  ON candidate_job_contexts (conversation_id, phone);

CREATE TABLE IF NOT EXISTS candidate_pending_media (
  pending_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone text NOT NULL,
  account_id text,
  conversation_id text,
  media jsonb NOT NULL,
  raw_text text,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '2 hours'),
  CONSTRAINT candidate_pending_media_status_chk
    CHECK (status IN ('pending','attached','expired'))
);
CREATE INDEX IF NOT EXISTS candidate_pending_media_lookup_idx
  ON candidate_pending_media (phone, status, expires_at);

-- Backfill bilingual/content from legacy columns and metadata when reliable.
UPDATE positions
SET description = COALESCE(
  NULLIF(TRIM(description), ''),
  NULLIF(TRIM(metadata->>'description'), ''),
  NULLIF(TRIM(raw_json->>'description'), '')
)
WHERE description IS NULL OR TRIM(description) = '';

UPDATE positions
SET requirements_en = COALESCE(
  requirements_en,
  CASE
    WHEN jsonb_typeof(requirements) = 'array' THEN requirements
    WHEN jsonb_typeof(metadata->'requirements') = 'array' THEN metadata->'requirements'
    ELSE NULL
  END
)
WHERE requirements_en IS NULL;

UPDATE positions
SET employment_type = COALESCE(
  NULLIF(TRIM(employment_type), ''),
  NULLIF(TRIM(metadata->>'employment_type'), ''),
  NULLIF(TRIM(raw_json->>'employment_type'), '')
)
WHERE employment_type IS NULL OR TRIM(employment_type) = '';

-- Normalize legacy active to open, blank to closed.
UPDATE positions SET status = 'open' WHERE LOWER(COALESCE(status, '')) IN ('', 'active');
UPDATE positions SET status = 'closed' WHERE LOWER(COALESCE(status, '')) NOT IN ('draft','open','paused','closed');
"""


class JobsError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


def apply_whatsapp_number() -> str:
    """Single env-owned APPLY destination. No silent product hardcodes."""
    number = "".join(ch for ch in str(os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER") or "").strip() if ch.isdigit())
    if not number:
        number = "".join(ch for ch in str(os.environ.get("WATHEFNI_WHATSAPP_NUMBER") or "").strip() if ch.isdigit())
    if not number:
        raise JobsError(
            "apply_whatsapp_unconfigured",
            "WATHEFNI_APPLY_WHATSAPP_NUMBER is not configured for this environment.",
            http_status=503,
        )
    return number


def apply_link(apply_code: str | None) -> str | None:
    code = str(apply_code or "").strip()
    if not code:
        return None
    try:
        number = apply_whatsapp_number()
    except JobsError:
        return None
    return f"https://wa.me/{number}?text={urllib.parse.quote(code)}"


def extract_apply_code(text: str | None) -> str | None:
    normalized = str(text or "").upper().translate(
        str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-"})
    )
    match = re.search(r"\b(APPLY-[A-Z0-9_-]+)\b", normalized)
    if not match:
        return None
    apply_code = match.group(1).strip("-")
    return apply_code if len(apply_code) <= 160 else None


def ensure_jobs_schema(cur: Any) -> None:
    for statement in SCHEMA_SQL.split(";"):
        sql = statement.strip()
        if not sql:
            continue
        # Skip comment-only fragments (semicolons inside `--` comments can split poorly).
        executable = "\n".join(
            line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")
        ).strip()
        if executable:
            if "positions_apply_code_uidx" in executable:
                cur.execute(
                    """
                    SELECT upper(apply_code) AS apply_code, COUNT(*) AS count
                    FROM positions
                    WHERE apply_code IS NOT NULL AND btrim(apply_code) <> ''
                    GROUP BY upper(apply_code)
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, upper(apply_code)
                    LIMIT 25
                    """
                )
                duplicates = [dict(row) for row in (cur.fetchall() or [])]
                if duplicates:
                    raise JobsError(
                        "duplicate_apply_codes",
                        "Duplicate APPLY codes must be remediated before enabling exact candidate intake.",
                        http_status=409,
                        details={"duplicates": duplicates},
                    )
            cur.execute(executable)


def normalize_status(value: str | None) -> str:
    status = str(value or "").strip().lower()
    if status in ("", "active"):
        return "open"
    if status not in JOB_STATUSES:
        return "closed"
    return status


def accepts_applications(status: str | None) -> bool:
    return normalize_status(status) == ACCEPTING_APPLICATIONS_STATUS


def normalize_visibility(value: str | None) -> str:
    visibility = str(value or "").strip().lower()
    return visibility if visibility in JOB_VISIBILITIES else "public"


def is_fully_remote(value: Any) -> bool:
    arrangement = re.sub(r"[-\s]+", "_", str(value or "").strip().lower())
    return arrangement in {item.replace(" ", "_") for item in FULLY_REMOTE_ARRANGEMENTS}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _requirements(row: dict[str, Any], locale: str) -> list[Any]:
    value = row.get(f"requirements_{locale}")
    if locale == "en" and value is None:
        value = row.get("requirements")
    return value if isinstance(value, list) else []


def attach_company_display_name(cur: Any, row: dict[str, Any]) -> dict[str, Any]:
    if _text(row.get("company_display_name")):
        return row
    company = _text(row.get("company_code")).upper()
    if not company:
        return row
    cur.execute(
        "SELECT NULLIF(TRIM(name), '') AS company_display_name FROM companies WHERE company_code=%s LIMIT 1",
        (company,),
    )
    company_row = cur.fetchone()
    if company_row:
        row["company_display_name"] = company_row.get("company_display_name")
    return row


def publish_blockers(row: dict[str, Any], *, require_channel: bool = True) -> list[str]:
    blockers: list[str] = []
    visibility = str(row.get("visibility") or "").strip().lower()
    if visibility not in JOB_VISIBILITIES:
        blockers.append("visibility")

    try:
        vacancies = int(row.get("vacancies"))
    except (TypeError, ValueError):
        vacancies = 0
    if vacancies < 1:
        blockers.append("vacancies")

    title_en = _text(row.get("title_en") if "title_en" in row else row.get("title"))
    title_ar = _text(row.get("title_ar"))
    en_ready = bool(
        title_en
        and _text(row.get("short_summary_en"))
        and _requirements(row, "en")
        and row.get("content_approved_en_at")
    )
    ar_ready = bool(
        title_ar
        and _text(row.get("short_summary_ar"))
        and _requirements(row, "ar")
        and row.get("content_approved_ar_at")
    )
    if not (en_ready or ar_ready):
        blockers.append("approved_language_pack")

    if not _text(row.get("location")) and not is_fully_remote(row.get("work_arrangement")):
        blockers.append("location_or_fully_remote")
    if not _text(row.get("employment_type")):
        blockers.append("employment_type")
    if not _text(row.get("position_code")) or not _text(row.get("apply_code")):
        blockers.append("apply_identity")
    if not _text(row.get("company_display_name")):
        blockers.append("company_display_name")

    salary_visibility = str(row.get("salary_visibility") or "hr_only").strip().lower()
    if salary_visibility not in {"hr_only", "public"}:
        blockers.append("salary_visibility")
    if salary_visibility == "public":
        salary_min = row.get("salary_min")
        salary_max = row.get("salary_max")
        currency = _text(row.get("currency"))
        try:
            salary_valid = (
                salary_min is not None
                and salary_max is not None
                and float(salary_min) <= float(salary_max)
                and bool(currency)
            )
        except (TypeError, ValueError):
            salary_valid = False
        if not salary_valid:
            blockers.append("public_salary")

    if require_channel:
        try:
            apply_whatsapp_number()
        except JobsError:
            blockers.append("apply_whatsapp_number")
    return blockers


def assert_job_publishable(row: dict[str, Any], *, require_channel: bool = True) -> None:
    blockers = publish_blockers(row, require_channel=require_channel)
    if blockers:
        raise JobsError(
            "job_not_publishable",
            "Complete the required job information before publishing.",
            http_status=422,
            details={"publish_blockers": blockers},
        )


def _deadline_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = _text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def job_context_expires_at(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    tenant_timezone: str | None = None,
) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    default_expiry = current + timedelta(days=14)
    deadline = _deadline_date(row.get("application_deadline"))
    if not deadline:
        return default_expiry
    timezone_name = _text(tenant_timezone or row.get("tenant_timezone") or os.environ.get("WATHEFNI_TENANT_TIMEZONE")) or "Asia/Kuwait"
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("Asia/Kuwait")
    deadline_expiry = datetime.combine(deadline + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return min(default_expiry, deadline_expiry)


def job_eligibility_snapshot(
    row: dict[str, Any],
    *,
    vacancy: dict[str, Any] | None = None,
    access_mode: str = "exact_token",
    now: datetime | None = None,
    tenant_timezone: str | None = None,
) -> dict[str, Any]:
    if access_mode not in JOB_ACCESS_MODES:
        raise ValueError(f"unsupported_job_access_mode:{access_mode}")

    raw_status = str(row.get("status") or "").strip().lower()
    if raw_status != "open":
        code = {
            "paused": "job_paused",
            "closed": "job_closed",
            "draft": "job_not_accepting",
        }.get(raw_status, "job_not_accepting")
        return {"eligible": False, "reason": code, "status": raw_status or None}

    visibility = str(row.get("visibility") or "").strip().lower()
    allowed = {"public", "share_only"} if access_mode == "exact_token" else {"public"}
    if visibility not in allowed:
        return {"eligible": False, "reason": "job_visibility_denied", "visibility": visibility or None}

    timezone_name = _text(tenant_timezone or row.get("tenant_timezone") or os.environ.get("WATHEFNI_TENANT_TIMEZONE")) or "Asia/Kuwait"
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("Asia/Kuwait")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    deadline = _deadline_date(row.get("application_deadline"))
    if deadline and current.astimezone(tz).date() > deadline:
        return {"eligible": False, "reason": "job_deadline_passed", "application_deadline": deadline.isoformat()}

    remaining = (vacancy or {}).get("remaining_vacancies", row.get("remaining_vacancies"))
    if remaining is not None:
        try:
            if int(remaining) <= 0:
                return {"eligible": False, "reason": "job_vacancies_exhausted", "remaining_vacancies": int(remaining)}
        except (TypeError, ValueError):
            return {"eligible": False, "reason": "job_vacancies_exhausted", "remaining_vacancies": None}

    content_blockers = publish_blockers(row, require_channel=False)
    if content_blockers:
        return {"eligible": False, "reason": "job_content_incomplete", "publish_blockers": content_blockers}
    return {"eligible": True, "reason": None, "status": "open", "visibility": visibility}


def assert_job_accepts_applications(
    row: dict[str, Any],
    *,
    vacancy: dict[str, Any] | None = None,
    access_mode: str = "exact_token",
    now: datetime | None = None,
    tenant_timezone: str | None = None,
) -> dict[str, Any]:
    snapshot = job_eligibility_snapshot(
        row,
        vacancy=vacancy,
        access_mode=access_mode,
        now=now,
        tenant_timezone=tenant_timezone,
    )
    if not snapshot.get("eligible"):
        reason = str(snapshot.get("reason") or "job_not_accepting")
        status = 404 if reason in {"job_visibility_denied", "job_not_accepting"} else 409
        raise JobsError(
            reason,
            "This job is not accepting applications.",
            http_status=status,
            details={key: value for key, value in snapshot.items() if key != "eligible"},
        )
    return snapshot


def job_shareability_snapshot(
    row: dict[str, Any],
    *,
    vacancy: dict[str, Any] | None = None,
    now: datetime | None = None,
    tenant_timezone: str | None = None,
) -> dict[str, Any]:
    """Canonical external-share authority for dashboard + Assistant surfaces.

    External sharing (wa.me link / QR payload) is allowed only when the job is
    currently eligible for external intake via exact APPLY token. Internal and
    otherwise ineligible jobs keep stable APPLY identity but must not expose a
    usable candidate share surface.
    """
    eligibility = job_eligibility_snapshot(
        row,
        vacancy=vacancy,
        access_mode="exact_token",
        now=now,
        tenant_timezone=tenant_timezone,
    )
    visibility = str(row.get("visibility") or "").strip().lower() or None
    if not eligibility.get("eligible"):
        return {
            "shareable": False,
            "reason": eligibility.get("reason") or "job_not_accepting",
            "visibility": visibility,
            "accepts_applications": False,
        }
    return {
        "shareable": True,
        "reason": None,
        "visibility": visibility,
        "accepts_applications": True,
    }


def assistant_external_share_fields(
    job: dict[str, Any] | None,
    *,
    vacancy: dict[str, Any] | None = None,
    now: datetime | None = None,
    tenant_timezone: str | None = None,
) -> dict[str, Any]:
    """Assistant-facing share payload. Never invents a candidate link."""
    row = job if isinstance(job, dict) else {}
    # Prefer already-serialized shareability when present; otherwise recompute.
    if "shareable" in row and "accepts_applications" in row:
        shareable = bool(row.get("shareable"))
        reason = row.get("eligibility_reason")
        apply_code = _text(row.get("apply_code")) or None
    else:
        share = job_shareability_snapshot(
            row,
            vacancy=vacancy,
            now=now,
            tenant_timezone=tenant_timezone,
        )
        shareable = bool(share.get("shareable"))
        reason = share.get("reason")
        apply_code = _text(row.get("apply_code")) or None
    link = apply_link(apply_code) if shareable and apply_code else None
    return {
        "shareable": shareable,
        "accepts_applications": shareable,
        "eligibility_reason": None if shareable else reason,
        "apply_code": apply_code,
        "application_link": link,
        "qr_value": link,
        "apply_link": link,
        "qr_image_url": None,
    }


def transition_action(from_status: str, to_status: str) -> str | None:
    return TRANSITION_ACTION.get((normalize_status(from_status), normalize_status(to_status)))


def assert_transition(from_status: str, to_status: str) -> str:
    src = normalize_status(from_status)
    dst_raw = str(to_status or "").strip().lower()
    if dst_raw not in JOB_STATUSES:
        raise JobsError(
            "invalid_job_status",
            f"Unknown job status '{to_status}'. Allowed: {', '.join(JOB_STATUSES)}.",
            http_status=422,
            details={"to": dst_raw, "allowed": list(JOB_STATUSES)},
        )
    dst = dst_raw
    if dst not in TRANSITIONS.get(src, frozenset()):
        raise JobsError(
            "invalid_job_transition",
            f"Cannot change job status from {src} to {dst}.",
            http_status=422,
            details={"from": src, "to": dst, "allowed": sorted(TRANSITIONS.get(src, frozenset()))},
        )
    action = transition_action(src, dst)
    if not action:
        raise JobsError("invalid_job_transition", f"Unsupported transition {src} -> {dst}.", http_status=422)
    return action


def permission_for_transition(action: str) -> str:
    if action in ("publish", "resume", "reopen"):
        return "jobs.publish"
    if action in ("pause", "close"):
        return "jobs.close"
    return "jobs.edit"


def slug_position_code(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(title or "").strip().upper()).strip("_")
    return (cleaned or "ROLE")[:48]


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def vacancy_counts(cur: Any, *, company: str, position_code: str, approved_headcount: int | None) -> dict[str, int | None]:
    cur.execute(
        """
        SELECT COUNT(*) AS hired
        FROM applications
        WHERE company_code=%s
          AND position_code=%s
          AND LOWER(COALESCE(status, '')) = ANY(%s)
          AND COALESCE(data_source, raw_json->>'data_source', 'production')='production'
        """,
        (company, position_code, list(VACANCY_CONSUMING_STATUSES)),
    )
    hired = int((cur.fetchone() or {}).get("hired") or 0)
    headcount = None if approved_headcount is None else max(0, int(approved_headcount))
    remaining = None if headcount is None else max(0, headcount - hired)
    return {
        "vacancies": headcount,
        "filled_vacancies": hired,
        "remaining_vacancies": remaining,
    }


def serialize_job(row: dict[str, Any], *, vacancy: dict[str, Any] | None = None, include_salary: bool = True) -> dict[str, Any]:
    company = str(row.get("company_code") or "").upper()
    code = str(row.get("position_code") or "").strip()
    apply_code = str(row.get("apply_code") or "").strip() or (f"APPLY-{company}-{code}" if code else None)
    status = normalize_status(row.get("status"))
    req_en = row.get("requirements_en")
    if req_en is None:
        req_en = row.get("requirements") or []
    req_ar = row.get("requirements_ar") or []
    description = row.get("description")
    if not description:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        description = meta.get("description") or ""
    publish_issues = publish_blockers(row)
    eligibility = job_eligibility_snapshot(row, vacancy=vacancy, access_mode="exact_token")
    share = job_shareability_snapshot(row, vacancy=vacancy)
    shareable = bool(share.get("shareable"))
    # Usable candidate share surfaces are backend-gated. Stable APPLY identity remains.
    share_link = apply_link(apply_code) if shareable else None
    out = {
        "job_id": str(row.get("job_id") or "") or None,
        "company_code": company,
        "company_display_name": row.get("company_display_name"),
        "position_code": code,
        "job_key": code,
        "title": row.get("title") or code,
        "title_en": (row.get("title_en") if "title_en" in row else row.get("title")) or None,
        "title_ar": row.get("title_ar"),
        "position_title": row.get("title") or code,
        "description": description or "",
        "description_en": description or "",
        "description_ar": row.get("description_ar") or "",
        "short_summary_en": row.get("short_summary_en") or "",
        "short_summary_ar": row.get("short_summary_ar") or "",
        "benefits_en": row.get("benefits_en") or "",
        "benefits_ar": row.get("benefits_ar") or "",
        "content_approved_en": bool(row.get("content_approved_en_at")),
        "content_approved_ar": bool(row.get("content_approved_ar_at")),
        "content_approved_en_at": _iso(row.get("content_approved_en_at")),
        "content_approved_ar_at": _iso(row.get("content_approved_ar_at")),
        "requirements": req_en if isinstance(req_en, list) else [],
        "requirements_en": req_en if isinstance(req_en, list) else [],
        "requirements_ar": req_ar if isinstance(req_ar, list) else [],
        "department": row.get("department"),
        "location": row.get("location"),
        "employment_type": row.get("employment_type"),
        "work_arrangement": row.get("work_arrangement"),
        "contract_type": row.get("contract_type"),
        "visibility": normalize_visibility(row.get("visibility")),
        "currency": row.get("currency") or "KD",
        "salary_visibility": str(row.get("salary_visibility") or "hr_only"),
        "vacancies": (vacancy or {}).get("vacancies", row.get("vacancies")),
        "filled_vacancies": (vacancy or {}).get("filled_vacancies"),
        "remaining_vacancies": (vacancy or {}).get("remaining_vacancies"),
        "application_deadline": _iso(row.get("application_deadline")),
        "expected_start_date": _iso(row.get("expected_start_date")),
        "hiring_manager_user_id": str(row.get("hiring_manager_user_id") or "") or None,
        "recruiter_user_id": str(row.get("recruiter_user_id") or "") or None,
        "status": status,
        "accepts_applications": bool(eligibility.get("eligible")),
        "eligibility_reason": eligibility.get("reason"),
        "shareable": shareable,
        "publish_ready": not publish_issues,
        "publish_blockers": publish_issues,
        "apply_code": apply_code,
        "application_key": apply_code,
        "application_link": share_link,
        "qr_value": share_link,
        "application_count": int(row.get("application_count") or 0),
        "active_count": int(row.get("active_count") or 0),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "published_at": _iso(row.get("published_at")),
        "closed_at": _iso(row.get("closed_at")),
        "created_by_user_id": str(row.get("created_by_user_id") or "") or None,
        "updated_by_user_id": str(row.get("updated_by_user_id") or "") or None,
        "version": int(row.get("version") or 1),
        "stage_counts": row.get("stage_counts") or [],
        "recent_applicants": row.get("recent_applicants") or [],
        "notifications": row.get("notifications") or [],
        "latest_applicant": row.get("latest_candidate_name") or row.get("latest_phone"),
        "latest_applicant_app_key": row.get("latest_applicant_app_key"),
        "latest_application_at": _iso(row.get("latest_application_at")),
        "authority_source": "positions",
    }
    if include_salary or str(out.get("salary_visibility") or "") == "public":
        out["salary_min"] = float(row["salary_min"]) if row.get("salary_min") is not None else None
        out["salary_max"] = float(row["salary_max"]) if row.get("salary_max") is not None else None
    else:
        out["salary_min"] = None
        out["salary_max"] = None
    return out


def create_job(
    *,
    company: str,
    db_connect: Callable[[], Any],
    actor_user_id: str | None,
    payload: dict[str, Any],
    as_draft: bool = True,
) -> dict[str, Any]:
    company = str(company or "").strip().upper()
    title_en = str(payload.get("title_en") or payload.get("title") or "").strip()
    title_ar = str(payload.get("title_ar") or "").strip()
    title = title_en or title_ar
    if not title:
        raise JobsError("missing_title", "An English or Arabic title is required.", http_status=422)
    position_code = str(payload.get("position_code") or "").strip().upper() or slug_position_code(title)
    status = "draft" if as_draft else "open"
    apply_code = f"APPLY-{company}-{position_code}"
    now = datetime.now(timezone.utc)
    visibility = str(payload.get("visibility") or "public").strip().lower()
    if visibility not in JOB_VISIBILITIES:
        raise JobsError("invalid_job_visibility", "visibility must be public, share_only, or internal.", http_status=422)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT position_code, status FROM positions WHERE company_code=%s AND position_code=%s",
                (company, position_code),
            )
            existing = cur.fetchone()
            if existing:
                raise JobsError(
                    "position_code_conflict",
                    f"A job with code {position_code} already exists. Edit that job or choose a new code.",
                    http_status=409,
                    details={"position_code": position_code, "status": normalize_status(existing.get("status"))},
                )
            job_id = str(uuid.uuid4())
            req_en = payload.get("requirements_en") if isinstance(payload.get("requirements_en"), list) else (
                payload.get("requirements") if isinstance(payload.get("requirements"), list) else []
            )
            req_ar = payload.get("requirements_ar") if isinstance(payload.get("requirements_ar"), list) else []
            vacancies = payload.get("vacancies")
            vacancies_i = int(vacancies) if vacancies is not None and str(vacancies) != "" else None
            cur.execute(
                """
                INSERT INTO positions (
                  job_id, company_code, position_code, title, title_ar, status,
                  salary_min, salary_max, currency, salary_visibility,
                  apply_code, requirements, requirements_en, requirements_ar,
                  description, description_ar, department, location,
                  employment_type, work_arrangement, contract_type,
                  vacancies, application_deadline, expected_start_date,
                  hiring_manager_user_id, recruiter_user_id,
                  metadata, raw_json,
                  published_at, created_by_user_id, updated_by_user_id,
                  version, created_at, updated_at
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,%s,
                  %s,%s,%s,
                  %s,%s,
                  %s,%s,
                  %s,%s,%s,
                  1, now(), now()
                )
                RETURNING *
                """,
                (
                    job_id,
                    company,
                    position_code,
                    title,
                    title_ar or None,
                    status,
                    payload.get("salary_min"),
                    payload.get("salary_max"),
                    str(payload.get("currency") or "KD").upper(),
                    str(payload.get("salary_visibility") or "hr_only"),
                    apply_code,
                    Json(req_en),
                    Json(req_en),
                    Json(req_ar),
                    payload.get("description") or payload.get("description_en") or "",
                    payload.get("description_ar") or "",
                    payload.get("department"),
                    payload.get("location"),
                    payload.get("employment_type"),
                    payload.get("work_arrangement"),
                    payload.get("contract_type"),
                    vacancies_i,
                    payload.get("application_deadline") or None,
                    payload.get("expected_start_date") or None,
                    payload.get("hiring_manager_user_id") or None,
                    payload.get("recruiter_user_id") or None,
                    Json(
                        {
                            "description": payload.get("description") or payload.get("description_en") or "",
                            "requirements": req_en,
                            "employment_type": payload.get("employment_type") or "",
                        }
                    ),
                    Json(
                        {
                            "code": position_code,
                            "title": title,
                            "apply_code": apply_code,
                            "company_code": company,
                        }
                    ),
                    now if status == "open" else None,
                    actor_user_id,
                    actor_user_id,
                ),
            )
            row = dict(cur.fetchone())
            approved_en = now if payload.get("approve_content_en") is True and title_en and actor_user_id else None
            approved_ar = now if payload.get("approve_content_ar") is True and title_ar and actor_user_id else None
            cur.execute(
                """
                UPDATE positions
                SET title_en=%s,
                    visibility=%s,
                    short_summary_en=%s,
                    short_summary_ar=%s,
                    benefits_en=%s,
                    benefits_ar=%s,
                    content_approved_en_at=%s,
                    content_approved_en_by=%s,
                    content_approved_ar_at=%s,
                    content_approved_ar_by=%s
                WHERE job_id=%s
                RETURNING *
                """,
                (
                    title_en or None,
                    visibility,
                    payload.get("short_summary_en") or None,
                    payload.get("short_summary_ar") or None,
                    payload.get("benefits_en") or None,
                    payload.get("benefits_ar") or None,
                    approved_en,
                    actor_user_id if approved_en else None,
                    approved_ar,
                    actor_user_id if approved_ar else None,
                    job_id,
                ),
            )
            row = dict(cur.fetchone())
            attach_company_display_name(cur, row)
            vac = vacancy_counts(cur, company=company, position_code=position_code, approved_headcount=vacancies_i)
            if status == "open":
                assert_job_publishable(row)
        conn.commit()
    return serialize_job(row, vacancy=vac)


def update_job(
    *,
    company: str,
    position_code: str,
    db_connect: Callable[[], Any],
    actor_user_id: str | None,
    payload: dict[str, Any],
    expected_updated_at: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    company = str(company or "").strip().upper()
    code = str(position_code or "").strip().upper()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM positions WHERE company_code=%s AND position_code=%s FOR UPDATE", (company, code))
            row = cur.fetchone()
            if not row:
                raise JobsError("position_not_found", "Job opening not found.", http_status=404)
            current = dict(row)
            _assert_fresh(current, expected_updated_at=expected_updated_at, expected_version=expected_version)
            # Edits never change lifecycle status.
            title_en = _text(
                payload.get("title_en")
                if "title_en" in payload
                else payload.get("title")
                if "title" in payload
                else current.get("title_en")
                if "title_en" in current
                else current.get("title") or ""
            )
            title_ar = _text(payload.get("title_ar") if "title_ar" in payload else current.get("title_ar"))
            title = title_en or title_ar
            if not title:
                raise JobsError("missing_title", "An English or Arabic title is required.", http_status=422)
            req_en = payload.get("requirements_en") if isinstance(payload.get("requirements_en"), list) else (
                payload.get("requirements") if isinstance(payload.get("requirements"), list) else current.get("requirements_en") or current.get("requirements") or []
            )
            req_ar = payload.get("requirements_ar") if isinstance(payload.get("requirements_ar"), list) else (current.get("requirements_ar") or [])
            vacancies = payload.get("vacancies") if "vacancies" in payload else current.get("vacancies")
            vacancies_i = int(vacancies) if vacancies is not None and str(vacancies) != "" else None
            visibility = str(payload.get("visibility") if "visibility" in payload else current.get("visibility") or "public").strip().lower()
            if visibility not in JOB_VISIBILITIES:
                raise JobsError("invalid_job_visibility", "visibility must be public, share_only, or internal.", http_status=422)
            summary_en = payload.get("short_summary_en") if "short_summary_en" in payload else current.get("short_summary_en")
            summary_ar = payload.get("short_summary_ar") if "short_summary_ar" in payload else current.get("short_summary_ar")
            benefits_en = payload.get("benefits_en") if "benefits_en" in payload else current.get("benefits_en")
            benefits_ar = payload.get("benefits_ar") if "benefits_ar" in payload else current.get("benefits_ar")
            en_changed = any(
                [
                    title_en
                    != _text(
                        current.get("title_en")
                        if "title_en" in current
                        else current.get("title") or ""
                    ),
                    _text(summary_en) != _text(current.get("short_summary_en")),
                    req_en != _requirements(current, "en"),
                    _text(benefits_en) != _text(current.get("benefits_en")),
                ]
            )
            ar_changed = any(
                [
                    title_ar != str(current.get("title_ar") or "").strip(),
                    _text(summary_ar) != _text(current.get("short_summary_ar")),
                    req_ar != _requirements(current, "ar"),
                    _text(benefits_ar) != _text(current.get("benefits_ar")),
                ]
            )
            now = datetime.now(timezone.utc)
            if payload.get("approve_content_en") is True and actor_user_id:
                approved_en_at, approved_en_by = now, actor_user_id
            elif payload.get("approve_content_en") is False or en_changed:
                approved_en_at, approved_en_by = None, None
            else:
                approved_en_at, approved_en_by = current.get("content_approved_en_at"), current.get("content_approved_en_by")
            if payload.get("approve_content_ar") is True and actor_user_id:
                approved_ar_at, approved_ar_by = now, actor_user_id
            elif payload.get("approve_content_ar") is False or ar_changed:
                approved_ar_at, approved_ar_by = None, None
            else:
                approved_ar_at, approved_ar_by = current.get("content_approved_ar_at"), current.get("content_approved_ar_by")
            cur.execute(
                """
                UPDATE positions SET
                  title=%s,
                  title_ar=%s,
                  description=%s,
                  description_ar=%s,
                  requirements=%s,
                  requirements_en=%s,
                  requirements_ar=%s,
                  department=%s,
                  location=%s,
                  employment_type=%s,
                  work_arrangement=%s,
                  contract_type=%s,
                  salary_min=%s,
                  salary_max=%s,
                  currency=%s,
                  salary_visibility=%s,
                  vacancies=%s,
                  application_deadline=%s,
                  expected_start_date=%s,
                  hiring_manager_user_id=%s,
                  recruiter_user_id=%s,
                  updated_by_user_id=%s,
                  version=COALESCE(version,1)+1,
                  updated_at=now(),
                  metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE company_code=%s AND position_code=%s
                RETURNING *
                """,
                (
                    title,
                    title_ar or None,
                    payload.get("description") if "description" in payload else (payload.get("description_en") if "description_en" in payload else current.get("description")),
                    payload.get("description_ar") if "description_ar" in payload else current.get("description_ar"),
                    Json(req_en),
                    Json(req_en),
                    Json(req_ar),
                    payload.get("department") if "department" in payload else current.get("department"),
                    payload.get("location") if "location" in payload else current.get("location"),
                    payload.get("employment_type") if "employment_type" in payload else current.get("employment_type"),
                    payload.get("work_arrangement") if "work_arrangement" in payload else current.get("work_arrangement"),
                    payload.get("contract_type") if "contract_type" in payload else current.get("contract_type"),
                    payload.get("salary_min") if "salary_min" in payload else current.get("salary_min"),
                    payload.get("salary_max") if "salary_max" in payload else current.get("salary_max"),
                    str(payload.get("currency") or current.get("currency") or "KD").upper(),
                    str(payload.get("salary_visibility") or current.get("salary_visibility") or "hr_only"),
                    vacancies_i,
                    payload.get("application_deadline") if "application_deadline" in payload else current.get("application_deadline"),
                    payload.get("expected_start_date") if "expected_start_date" in payload else current.get("expected_start_date"),
                    payload.get("hiring_manager_user_id") if "hiring_manager_user_id" in payload else current.get("hiring_manager_user_id"),
                    payload.get("recruiter_user_id") if "recruiter_user_id" in payload else current.get("recruiter_user_id"),
                    actor_user_id,
                    Json({"description": payload.get("description") or payload.get("description_en") or current.get("description") or "", "requirements": req_en}),
                    company,
                    code,
                ),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                """
                UPDATE positions
                SET title_en=%s,
                    visibility=%s,
                    short_summary_en=%s,
                    short_summary_ar=%s,
                    benefits_en=%s,
                    benefits_ar=%s,
                    content_approved_en_at=%s,
                    content_approved_en_by=%s,
                    content_approved_ar_at=%s,
                    content_approved_ar_by=%s
                WHERE company_code=%s AND position_code=%s
                RETURNING *
                """,
                (
                    title_en or None,
                    visibility,
                    summary_en or None,
                    summary_ar or None,
                    benefits_en or None,
                    benefits_ar or None,
                    approved_en_at,
                    approved_en_by,
                    approved_ar_at,
                    approved_ar_by,
                    company,
                    code,
                ),
            )
            updated = dict(cur.fetchone())
            attach_company_display_name(cur, updated)
            vac = vacancy_counts(cur, company=company, position_code=code, approved_headcount=vacancies_i)
        conn.commit()
    return serialize_job(updated, vacancy=vac)


def transition_job(
    *,
    company: str,
    position_code: str,
    db_connect: Callable[[], Any],
    actor_user_id: str | None,
    to_status: str,
    expected_updated_at: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    company = str(company or "").strip().upper()
    code = str(position_code or "").strip().upper()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM positions WHERE company_code=%s AND position_code=%s FOR UPDATE", (company, code))
            row = cur.fetchone()
            if not row:
                raise JobsError("position_not_found", "Job opening not found.", http_status=404)
            current = dict(row)
            attach_company_display_name(cur, current)
            _assert_fresh(current, expected_updated_at=expected_updated_at, expected_version=expected_version)
            dst_raw = str(to_status or "").strip().lower()
            if dst_raw not in JOB_STATUSES:
                raise JobsError(
                    "invalid_job_status",
                    f"Unknown job status '{to_status}'. Allowed: {', '.join(JOB_STATUSES)}.",
                    http_status=422,
                    details={"to": dst_raw, "allowed": list(JOB_STATUSES)},
                )
            # Idempotent no-op when already in the requested status.
            if normalize_status(current.get("status")) == dst_raw:
                vac = vacancy_counts(
                    cur,
                    company=company,
                    position_code=code,
                    approved_headcount=current.get("vacancies"),
                )
                result = serialize_job(current, vacancy=vac)
                result["transition_action"] = "noop"
                return result
            action = assert_transition(current.get("status"), to_status)
            dst = dst_raw
            published_at = current.get("published_at")
            closed_at = current.get("closed_at")
            if action == "publish" or action == "reopen" or action == "resume":
                assert_job_publishable(current)
                if not published_at:
                    published_at = datetime.now(timezone.utc)
                closed_at = None
            if action == "close":
                closed_at = datetime.now(timezone.utc)
            cur.execute(
                """
                UPDATE positions
                SET status=%s,
                    published_at=%s,
                    closed_at=%s,
                    updated_by_user_id=%s,
                    version=COALESCE(version,1)+1,
                    updated_at=now()
                WHERE company_code=%s AND position_code=%s
                RETURNING *
                """,
                (dst, published_at, closed_at, actor_user_id, company, code),
            )
            updated = dict(cur.fetchone())
            attach_company_display_name(cur, updated)
            vac = vacancy_counts(
                cur,
                company=company,
                position_code=code,
                approved_headcount=updated.get("vacancies"),
            )
        conn.commit()
    result = serialize_job(updated, vacancy=vac)
    result["transition_action"] = action
    return result


def _assert_fresh(row: dict[str, Any], *, expected_updated_at: str | None, expected_version: int | None) -> None:
    if expected_version is not None:
        current_version = int(row.get("version") or 1)
        if int(expected_version) != current_version:
            raise JobsError(
                "stale_job_version",
                "This job changed since you loaded it. Refresh and try again.",
                http_status=409,
                details={"expected_version": int(expected_version), "current_version": current_version},
            )
    if expected_updated_at:
        current = _iso(row.get("updated_at"))
        if str(current) != str(expected_updated_at):
            raise JobsError(
                "stale_job_update",
                "This job changed since you loaded it. Refresh and try again.",
                http_status=409,
                details={"expected_updated_at": expected_updated_at, "current_updated_at": current},
            )


def get_job(*, company: str, position_code: str, db_connect: Callable[[], Any]) -> dict[str, Any]:
    company = str(company or "").strip().upper()
    code = str(position_code or "").strip().upper()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM positions WHERE company_code=%s AND position_code=%s", (company, code))
            row = cur.fetchone()
            if not row:
                raise JobsError("position_not_found", "Job opening not found.", http_status=404)
            data = dict(row)
            attach_company_display_name(cur, data)
            vac = vacancy_counts(cur, company=company, position_code=code, approved_headcount=data.get("vacancies"))
    return serialize_job(data, vacancy=vac)


def file_based_positions_enabled() -> bool:
    """Legacy Octopus file inventory is quarantined unless explicitly enabled."""
    return str(os.environ.get("WATHEFNI_FILE_POSITIONS_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}
