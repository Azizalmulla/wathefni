"""Canonical Pre-Hiring Jobs authority (Phase 1).

Postgres `positions` is the sole runtime authority for job existence and
lifecycle. Applications never synthesize jobs. Intake accepts only `open`.
"""

from __future__ import annotations

import os
import re
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from psycopg2.extras import Json

JOB_STATUSES = ("draft", "open", "paused", "closed")
ACCEPTING_APPLICATIONS_STATUS = "open"
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

UPDATE positions SET job_id = gen_random_uuid() WHERE job_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS positions_job_id_uidx ON positions (job_id);
CREATE UNIQUE INDEX IF NOT EXISTS positions_company_code_uidx ON positions (company_code, position_code);

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
    out = {
        "job_id": str(row.get("job_id") or "") or None,
        "company_code": company,
        "position_code": code,
        "job_key": code,
        "title": row.get("title") or code,
        "title_en": row.get("title") or code,
        "title_ar": row.get("title_ar"),
        "position_title": row.get("title") or code,
        "description": description or "",
        "description_en": description or "",
        "description_ar": row.get("description_ar") or "",
        "requirements": req_en if isinstance(req_en, list) else [],
        "requirements_en": req_en if isinstance(req_en, list) else [],
        "requirements_ar": req_ar if isinstance(req_ar, list) else [],
        "department": row.get("department"),
        "location": row.get("location"),
        "employment_type": row.get("employment_type"),
        "work_arrangement": row.get("work_arrangement"),
        "contract_type": row.get("contract_type"),
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
        "accepts_applications": accepts_applications(status),
        "apply_code": apply_code,
        "application_key": apply_code,
        "application_link": apply_link(apply_code),
        "qr_value": apply_link(apply_code),
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
    title = str(payload.get("title") or payload.get("title_en") or "").strip()
    if not title:
        raise JobsError("missing_title", "English title is required.", http_status=422)
    position_code = str(payload.get("position_code") or "").strip().upper() or slug_position_code(title)
    status = "draft" if as_draft else "open"
    apply_code = f"APPLY-{company}-{position_code}"
    now = datetime.now(timezone.utc)
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
                    payload.get("title_ar") or None,
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
            vac = vacancy_counts(cur, company=company, position_code=position_code, approved_headcount=vacancies_i)
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
            title = str(payload.get("title") or payload.get("title_en") or current.get("title") or "").strip()
            if not title:
                raise JobsError("missing_title", "English title is required.", http_status=422)
            req_en = payload.get("requirements_en") if isinstance(payload.get("requirements_en"), list) else (
                payload.get("requirements") if isinstance(payload.get("requirements"), list) else current.get("requirements_en") or current.get("requirements") or []
            )
            req_ar = payload.get("requirements_ar") if isinstance(payload.get("requirements_ar"), list) else (current.get("requirements_ar") or [])
            vacancies = payload.get("vacancies") if "vacancies" in payload else current.get("vacancies")
            vacancies_i = int(vacancies) if vacancies is not None and str(vacancies) != "" else None
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
                    payload.get("title_ar") if "title_ar" in payload else current.get("title_ar"),
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
            vac = vacancy_counts(cur, company=company, position_code=code, approved_headcount=data.get("vacancies"))
    return serialize_job(data, vacancy=vac)


def file_based_positions_enabled() -> bool:
    """Legacy Octopus file inventory is quarantined unless explicitly enabled."""
    return str(os.environ.get("WATHEFNI_FILE_POSITIONS_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}
