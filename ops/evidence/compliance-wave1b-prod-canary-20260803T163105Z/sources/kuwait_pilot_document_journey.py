"""Kuwait pilot document journey — local remediation authority.

Upload → store → metadata → optional OCR proposal → HR review (approve/reject/
request re-upload) → expiry → employee renewal → version history.

Does NOT implement PACI/MOI/PAM verification, automatic legal compliance, or
government API integrations. "HR reviewed" never means government verified.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

# --------------------------------------------------------------------------- #
# Vocabulary (HR-facing; never "government verified")
# --------------------------------------------------------------------------- #

STATUS_PENDING_HR_REVIEW = "pending_hr_review"
STATUS_HR_REVIEWED = "hr_reviewed"
STATUS_REJECTED_REUPLOAD = "rejected_reupload"
STATUS_EXPIRING_SOON = "expiring_soon"
STATUS_EXPIRED = "expired"
STATUS_MISSING = "missing"
STATUS_SUPERSEDED = "superseded"

HR_STATUS_LABELS_EN = {
    STATUS_PENDING_HR_REVIEW: "Pending HR review",
    STATUS_HR_REVIEWED: "HR reviewed",
    STATUS_REJECTED_REUPLOAD: "Rejected — re-upload required",
    STATUS_EXPIRING_SOON: "Expiring soon",
    STATUS_EXPIRED: "Expired",
    STATUS_MISSING: "Missing",
    STATUS_SUPERSEDED: "Superseded",
    "valid": "HR reviewed",
    "needs_review": "Pending HR review",
    "received": "Pending HR review",
    "missing_expiry": "Pending HR review",
}

HR_STATUS_LABELS_AR = {
    STATUS_PENDING_HR_REVIEW: "بانتظار مراجعة الموارد البشرية",
    STATUS_HR_REVIEWED: "تمت مراجعة الموارد البشرية",
    STATUS_REJECTED_REUPLOAD: "مرفوض — يلزم إعادة الرفع",
    STATUS_EXPIRING_SOON: "ينتهي قريباً",
    STATUS_EXPIRED: "منتهي",
    STATUS_MISSING: "ناقص",
    STATUS_SUPERSEDED: "مستبدل",
    "valid": "تمت مراجعة الموارد البشرية",
    "needs_review": "بانتظار مراجعة الموارد البشرية",
    "received": "بانتظار مراجعة الموارد البشرية",
    "missing_expiry": "بانتظار مراجعة الموارد البشرية",
}

DOC_LABELS_EN = {
    "civil_id": "Civil ID",
    "passport": "Passport",
    "residence": "Residence",
    "residency": "Residence",
    "residency_iqama": "Residence (legacy id)",
    "work_permit": "Work permit",
    "employment_contract": "Employment contract",
    "medical": "Medical certificate",
    "education_cert": "Education certificate",
}

DOC_LABELS_AR = {
    "civil_id": "البطاقة المدنية",
    "passport": "جواز السفر",
    "residence": "الإقامة",
    "residency": "الإقامة",
    "residency_iqama": "الإقامة (معرّف قديم)",
    "work_permit": "إذن العمل",
    "employment_contract": "عقد العمل",
    "medical": "الشهادة الطبية",
    "education_cert": "الشهادة التعليمية",
}

DOCUMENT_REVIEW_MANAGE = "compliance.manage"
DOCUMENT_REVIEW_READ = "compliance.read"

# Permissions explicitly checked (tenant-scoped via company_code everywhere).
SENSITIVE_REPLACE_TYPES = frozenset(
    {
        "civil_id",
        "passport",
        "residence",
        "residency",
        "residency_iqama",
        "work_permit",
        "medical",
        "personal_photo",
    }
)


class DocumentJourneyError(Exception):
    def __init__(self, code: str, message: str = "", *, status_code: int = 400, extra: dict | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status_code = status_code
        self.extra = extra or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _company(code: str | None) -> str:
    return str(code or "").strip().upper()


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value)
    return value


def _doc_type_map():
    try:
        from ops.lib import doc_type_map as tm

        return tm
    except Exception:
        try:
            from lib import doc_type_map as tm  # type: ignore

            return tm
        except Exception:
            return None


def canonical_compliance_type(document_type: str | None) -> str:
    raw = str(document_type or "").strip().lower()
    tm = _doc_type_map()
    if tm is not None:
        mapped = tm.ITEM_TO_COMPLIANCE_TYPE.get(raw)
        if mapped:
            return str(mapped)
        return tm.normalize_kuwait_document_type(raw)
    if raw in {"residency_iqama", "residency", "residence"}:
        return "residence"
    return raw


def upload_synced_compliance_types() -> set[str]:
    tm = _doc_type_map()
    if tm is not None:
        return set(tm.UPLOAD_SYNCED_COMPLIANCE_TYPES)
    return {"civil_id", "passport", "medical", "education_cert", "residence", "work_permit"}


def should_dual_write_compliance(document_type: str | None) -> bool:
    return canonical_compliance_type(document_type) in upload_synced_compliance_types()


def document_label(document_type: str | None, *, locale: str = "en") -> str:
    key = canonical_compliance_type(document_type) if document_type else ""
    raw = str(document_type or "").strip().lower()
    table = DOC_LABELS_AR if str(locale).lower().startswith("ar") else DOC_LABELS_EN
    return table.get(raw) or table.get(key) or (document_type or "Document")


def hr_status_label(status: str | None, *, locale: str = "en") -> str:
    table = HR_STATUS_LABELS_AR if str(locale).lower().startswith("ar") else HR_STATUS_LABELS_EN
    return table.get(str(status or "").lower()) or str(status or "")


def is_sensitive_replace_type(document_type: str | None) -> bool:
    raw = str(document_type or "").strip().lower()
    return raw in SENSITIVE_REPLACE_TYPES or canonical_compliance_type(raw) in SENSITIVE_REPLACE_TYPES


def onboarding_required_overrides(employee_category: str | None) -> dict[str, bool]:
    """Category-aware requiredness for residence / work_permit onboarding items."""
    cat = str(employee_category or "unspecified")
    if cat == "article_18_expatriate":
        return {"residence": True, "work_permit": True}
    if cat == "kuwaiti_national":
        return {"residence": False, "work_permit": False}
    return {}


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


def ensure_document_journey_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS governed_document_versions (
          version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          document_type text NOT NULL,
          version_no integer NOT NULL,
          file_id text,
          file_sha256 text,
          filename text,
          mime_type text,
          review_status text NOT NULL DEFAULT 'pending_hr_review',
          is_current boolean NOT NULL DEFAULT false,
          issue_date date,
          expiry_date date,
          document_number text,
          ocr_proposal jsonb NOT NULL DEFAULT '{}'::jsonb,
          confirmed_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          rejection_reason text,
          uploaded_by text,
          upload_source text,
          hr_reviewer_user_id text,
          reviewed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key, document_type, version_no),
          CHECK (review_status IN (
            'pending_hr_review','hr_reviewed','rejected_reupload','superseded','expiring_soon','expired'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS governed_document_versions_emp_idx
          ON governed_document_versions (company_code, employee_key, document_type, is_current DESC, version_no DESC)
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS governed_document_versions_one_current_uq
          ON governed_document_versions (company_code, employee_key, document_type)
          WHERE is_current = true
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS governed_document_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          document_type text NOT NULL,
          version_id uuid,
          actor_user_id text,
          actor_kind text,
          action text NOT NULL,
          reason text,
          old_state jsonb NOT NULL DEFAULT '{}'::jsonb,
          new_state jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS governed_document_events_emp_idx
          ON governed_document_events (company_code, employee_key, document_type, created_at DESC)
        """
    )


def _append_event(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    version_id: str | None,
    actor_user_id: str | None,
    actor_kind: str,
    action: str,
    reason: str | None,
    old_state: dict,
    new_state: dict,
) -> None:
    cur.execute(
        """
        INSERT INTO governed_document_events(
          company_code, employee_key, document_type, version_id,
          actor_user_id, actor_kind, action, reason, old_state, new_state
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            company_code,
            employee_key,
            document_type,
            version_id,
            actor_user_id,
            actor_kind,
            action,
            reason,
            _json(legacy, old_state),
            _json(legacy, new_state),
        ),
    )


def _next_version_no(cur: Any, company: str, employee_key: str, document_type: str) -> int:
    cur.execute(
        """
        SELECT COALESCE(MAX(version_no), 0) + 1 AS n
        FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_type=%s
        """,
        (company, employee_key, document_type),
    )
    row = cur.fetchone() or {}
    return int(row.get("n") or 1)


def dual_write_compliance_from_upload(
    cur: Any,
    *,
    employee: Mapping[str, Any],
    document_type: str,
    label: str | None,
    metadata: dict,
    document_number: str | None,
    issued_date: Any,
    expiry_date: Any,
    extraction_status: str | None,
    extraction_error: str | None,
    extraction_confidence: Any,
    ocr_proposal: dict | None = None,
    notes: str | None = None,
) -> str | None:
    """Upsert compliance_documents using canonical type mapping. Returns type written."""
    ctype = canonical_compliance_type(document_type)
    if ctype not in upload_synced_compliance_types():
        return None
    employee_key = str(employee.get("employee_key") or "")
    company = _company(employee.get("company_code"))
    # Prefer existing canonical row; also read legacy residency_iqama without renaming it.
    cur.execute(
        """
        SELECT document_type FROM compliance_documents
        WHERE employee_key=%s AND document_type = ANY(%s)
        ORDER BY CASE WHEN document_type=%s THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        (employee_key, list({ctype, "residency_iqama", "residency"}), ctype),
    )
    existing = cur.fetchone()
    target_type = str((existing or {}).get("document_type") or ctype)
    # New writes always use canonical residence when no legacy row exists.
    if not existing and ctype == "residence":
        target_type = "residence"
    friendly = label or document_label(ctype)
    compliance_metadata = {**metadata, "employee_document_type": document_type, "canonical_type": ctype}
    if ocr_proposal:
        compliance_metadata["ocr_proposal"] = ocr_proposal
        compliance_metadata["ocr_authoritative"] = False
    # Pending HR review when newly received (never claim government verification).
    status = "received"
    cur.execute(
        """
        UPDATE compliance_documents
        SET status=%s,
            label=COALESCE(%s, label),
            notes=COALESCE(%s, notes),
            raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
            document_number=COALESCE(%s, document_number),
            issued_date=COALESCE(%s, issued_date),
            expiry_date=COALESCE(%s, expiry_date),
            days_until_expiry=CASE WHEN %s::date IS NULL THEN days_until_expiry ELSE (%s::date - CURRENT_DATE) END,
            extraction_status=%s,
            extraction_error=%s,
            extraction_confidence=%s,
            extracted_at=CASE WHEN %s IS NOT NULL THEN now() ELSE extracted_at END,
            renewal_status=NULL,
            updated_at=now()
        WHERE employee_key=%s AND document_type=%s
        """,
        (
            status,
            friendly,
            notes,
            json.dumps(compliance_metadata),
            document_number or None,
            issued_date,
            expiry_date,
            expiry_date,
            expiry_date,
            extraction_status,
            extraction_error,
            extraction_confidence,
            extraction_status,
            employee_key,
            target_type,
        ),
    )
    if cur.rowcount:
        return target_type
    cur.execute(
        """
        INSERT INTO compliance_documents (
            employee_key, document_type, label, status, notes, raw_json,
            document_number, issued_date, expiry_date, days_until_expiry,
            extraction_status, extraction_error, extraction_confidence, extracted_at,
            company_code, warning_days
        )
        VALUES (
            %s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,
            CASE WHEN %s::date IS NULL THEN NULL ELSE (%s::date - CURRENT_DATE) END,
            %s,%s,%s,CASE WHEN %s IS NOT NULL THEN now() ELSE NULL END,%s,
            CASE WHEN %s='passport' THEN 60 ELSE 30 END
        )
        """,
        (
            employee_key,
            ctype,
            friendly,
            status,
            notes,
            json.dumps(compliance_metadata),
            document_number or None,
            issued_date,
            expiry_date,
            expiry_date,
            expiry_date,
            extraction_status,
            extraction_error,
            extraction_confidence,
            extraction_status,
            company,
            ctype,
        ),
    )
    return ctype


def register_upload_version(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    file_id: str | None,
    file_sha256: str | None,
    filename: str | None,
    mime_type: str | None,
    issue_date: Any = None,
    expiry_date: Any = None,
    document_number: str | None = None,
    ocr_proposal: dict | None = None,
    uploaded_by: str | None,
    upload_source: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Append a new pending version. Does not displace an approved current version
    until HR approves (rejected replacements never become current)."""
    company = _company(company_code)
    ctype = canonical_compliance_type(document_type)
    ensure_document_journey_schema(cur)
    version_no = _next_version_no(cur, company, employee_key, ctype)
    cur.execute(
        """
        SELECT version_id, review_status, is_current, expiry_date, issue_date, document_number, file_id
        FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_type=%s AND is_current=true
        LIMIT 1
        """,
        (company, employee_key, ctype),
    )
    current = cur.fetchone()
    # New version is current only when there is no approved current, or current is missing/rejected.
    become_current = True
    if current and str(current.get("review_status")) == STATUS_HR_REVIEWED:
        become_current = False
    if become_current and current:
        cur.execute(
            """
            UPDATE governed_document_versions
            SET is_current=false, review_status=CASE
                  WHEN review_status='hr_reviewed' THEN 'superseded'
                  ELSE review_status END,
                updated_at=now()
            WHERE version_id=%s
            """,
            (current["version_id"],),
        )
    proposal = dict(ocr_proposal or {})
    # OCR proposals are never authoritative.
    proposal["authoritative"] = False
    cur.execute(
        """
        INSERT INTO governed_document_versions(
          company_code, employee_key, document_type, version_no, file_id, file_sha256,
          filename, mime_type, review_status, is_current, issue_date, expiry_date,
          document_number, ocr_proposal, uploaded_by, upload_source
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            ctype,
            version_no,
            file_id,
            file_sha256,
            filename,
            mime_type,
            STATUS_PENDING_HR_REVIEW,
            become_current,
            issue_date,
            expiry_date,
            document_number,
            _json(legacy, proposal),
            uploaded_by,
            upload_source,
        ),
    )
    row = dict(cur.fetchone())
    _append_event(
        cur,
        legacy,
        company_code=company,
        employee_key=employee_key,
        document_type=ctype,
        version_id=str(row["version_id"]),
        actor_user_id=actor_user_id or uploaded_by,
        actor_kind="employee" if upload_source.startswith("employee") else "hr",
        action="uploaded",
        reason=None,
        old_state={"current_version_id": str(current["version_id"]) if current else None},
        new_state={
            "version_id": str(row["version_id"]),
            "review_status": STATUS_PENDING_HR_REVIEW,
            "is_current": become_current,
            "legitimacy": "file_received_pending_hr_review",
        },
    )
    return row


def approve_version(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    version_id: str | None = None,
    actor_user_id: str | None,
    permissions: Iterable[str] | None,
    issue_date: str | None = None,
    expiry_date: str | None = None,
    document_number: str | None = None,
    reason: str | None = None,
    confirm_ocr: bool = False,
) -> dict[str, Any]:
    if DOCUMENT_REVIEW_MANAGE not in set(permissions or ()):
        raise DocumentJourneyError("permission_denied", status_code=403)
    company = _company(company_code)
    ctype = canonical_compliance_type(document_type)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_document_journey_schema(cur)
            if version_id:
                cur.execute(
                    """
                    SELECT * FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s AND version_id=%s
                    FOR UPDATE
                    """,
                    (company, employee_key, ctype, version_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s
                      AND review_status='pending_hr_review'
                    ORDER BY version_no DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (company, employee_key, ctype),
                )
            row = cur.fetchone()
            if not row:
                raise DocumentJourneyError("version_not_found", "No pending version to approve")
            old = dict(row)
            confirmed: dict[str, Any] = {}
            ocr = old.get("ocr_proposal") if isinstance(old.get("ocr_proposal"), dict) else {}
            if confirm_ocr and ocr:
                confirmed = {
                    "document_number": document_number or ocr.get("document_number"),
                    "issue_date": issue_date or ocr.get("issue_date") or ocr.get("issued_date"),
                    "expiry_date": expiry_date or ocr.get("expiry_date"),
                    "confirmed_from_ocr": True,
                }
            else:
                confirmed = {
                    "document_number": document_number if document_number is not None else old.get("document_number"),
                    "issue_date": issue_date or (str(old.get("issue_date")) if old.get("issue_date") else None),
                    "expiry_date": expiry_date or (str(old.get("expiry_date")) if old.get("expiry_date") else None),
                    "confirmed_from_ocr": False,
                }
            # Clear prior current
            cur.execute(
                """
                UPDATE governed_document_versions
                SET is_current=false,
                    review_status=CASE WHEN version_id<>%s AND is_current THEN 'superseded' ELSE review_status END,
                    updated_at=now()
                WHERE company_code=%s AND employee_key=%s AND document_type=%s AND is_current=true
                """,
                (old["version_id"], company, employee_key, ctype),
            )
            exp = confirmed.get("expiry_date")
            iss = confirmed.get("issue_date")
            cur.execute(
                """
                UPDATE governed_document_versions
                SET review_status='hr_reviewed',
                    is_current=true,
                    issue_date=COALESCE(%s::date, issue_date),
                    expiry_date=COALESCE(%s::date, expiry_date),
                    document_number=COALESCE(%s, document_number),
                    confirmed_metadata=%s,
                    hr_reviewer_user_id=%s,
                    reviewed_at=now(),
                    rejection_reason=NULL,
                    updated_at=now()
                WHERE version_id=%s
                RETURNING *
                """,
                (
                    iss,
                    exp,
                    confirmed.get("document_number"),
                    _json(legacy, confirmed),
                    actor_user_id,
                    old["version_id"],
                ),
            )
            approved = dict(cur.fetchone())
            # Sync compliance as HR reviewed (not government verified)
            cur.execute(
                """
                UPDATE compliance_documents
                SET status='valid',
                    renewal_status='reviewed',
                    document_number=COALESCE(%s, document_number),
                    issued_date=COALESCE(%s::date, issued_date),
                    expiry_date=COALESCE(%s::date, expiry_date),
                    days_until_expiry=CASE WHEN %s::date IS NULL THEN days_until_expiry ELSE (%s::date - CURRENT_DATE) END,
                    last_checked_at=now(),
                    updated_at=now(),
                    notes=COALESCE(%s, notes)
                WHERE employee_key=%s AND document_type = ANY(%s)
                """,
                (
                    confirmed.get("document_number"),
                    iss,
                    exp,
                    exp,
                    exp,
                    reason,
                    employee_key,
                    list({ctype, "residency_iqama", "residency"}),
                ),
            )
            # Close outstanding reminder bookkeeping after approved renewal
            cur.execute(
                """
                UPDATE compliance_documents
                SET reminder_count=0, last_alerted_at=NULL, updated_at=now()
                WHERE employee_key=%s AND document_type = ANY(%s)
                """,
                (employee_key, list({ctype, "residency_iqama", "residency"})),
            )
            _append_event(
                cur,
                legacy,
                company_code=company,
                employee_key=employee_key,
                document_type=ctype,
                version_id=str(approved["version_id"]),
                actor_user_id=actor_user_id,
                actor_kind="hr",
                action="approve_hr_reviewed",
                reason=reason,
                old_state={"review_status": old.get("review_status"), "is_current": old.get("is_current")},
                new_state={
                    "review_status": STATUS_HR_REVIEWED,
                    "is_current": True,
                    "legitimacy": "hr_reviewed_only_not_government_verified",
                    "confirmed_metadata": confirmed,
                },
            )
        conn.commit()
    return approved


def reject_version(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    version_id: str | None = None,
    actor_user_id: str | None,
    permissions: Iterable[str] | None,
    reason: str,
    request_reupload: bool = True,
) -> dict[str, Any]:
    if DOCUMENT_REVIEW_MANAGE not in set(permissions or ()):
        raise DocumentJourneyError("permission_denied", status_code=403)
    if not str(reason or "").strip():
        raise DocumentJourneyError("reason_required", "Rejection reason is required")
    company = _company(company_code)
    ctype = canonical_compliance_type(document_type)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_document_journey_schema(cur)
            if version_id:
                cur.execute(
                    """
                    SELECT * FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s AND version_id=%s
                    FOR UPDATE
                    """,
                    (company, employee_key, ctype, version_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s
                      AND review_status='pending_hr_review'
                    ORDER BY version_no DESC LIMIT 1
                    FOR UPDATE
                    """,
                    (company, employee_key, ctype),
                )
            row = cur.fetchone()
            if not row:
                raise DocumentJourneyError("version_not_found")
            old = dict(row)
            # Rejected replacement must NOT become/displace approved current.
            cur.execute(
                """
                UPDATE governed_document_versions
                SET review_status='rejected_reupload',
                    is_current=false,
                    rejection_reason=%s,
                    hr_reviewer_user_id=%s,
                    reviewed_at=now(),
                    updated_at=now()
                WHERE version_id=%s
                RETURNING *
                """,
                (reason, actor_user_id, old["version_id"]),
            )
            rejected = dict(cur.fetchone())
            # Restore prior hr_reviewed current if any
            cur.execute(
                """
                SELECT version_id FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type=%s
                  AND review_status='hr_reviewed'
                ORDER BY version_no DESC LIMIT 1
                """,
                (company, employee_key, ctype),
            )
            prior = cur.fetchone()
            if prior:
                cur.execute(
                    """
                    UPDATE governed_document_versions
                    SET is_current=true, updated_at=now()
                    WHERE version_id=%s
                    """,
                    (prior["version_id"],),
                )
            cur.execute(
                """
                UPDATE compliance_documents
                SET status='received',
                    renewal_status=%s,
                    notes=%s,
                    updated_at=now()
                WHERE employee_key=%s AND document_type = ANY(%s)
                """,
                (
                    "reupload_required" if request_reupload else "rejected",
                    reason,
                    employee_key,
                    list({ctype, "residency_iqama", "residency"}),
                ),
            )
            _append_event(
                cur,
                legacy,
                company_code=company,
                employee_key=employee_key,
                document_type=ctype,
                version_id=str(rejected["version_id"]),
                actor_user_id=actor_user_id,
                actor_kind="hr",
                action="reject_request_reupload" if request_reupload else "reject",
                reason=reason,
                old_state={"review_status": old.get("review_status"), "is_current": old.get("is_current")},
                new_state={
                    "review_status": STATUS_REJECTED_REUPLOAD,
                    "is_current": False,
                    "prior_current_restored": bool(prior),
                    "legitimacy": "hr_rejected_not_government_decision",
                },
            )
        conn.commit()
    return rejected


def correct_metadata(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    actor_user_id: str | None,
    permissions: Iterable[str] | None,
    issue_date: str | None = None,
    expiry_date: str | None = None,
    document_number: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    if DOCUMENT_REVIEW_MANAGE not in set(permissions or ()):
        raise DocumentJourneyError("permission_denied", status_code=403)
    company = _company(company_code)
    ctype = canonical_compliance_type(document_type)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_document_journey_schema(cur)
            cur.execute(
                """
                SELECT * FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type=%s AND is_current=true
                FOR UPDATE
                """,
                (company, employee_key, ctype),
            )
            row = cur.fetchone()
            if not row:
                # Allow metadata entry on compliance-only rows (OCR unavailable path)
                cur.execute(
                    """
                    UPDATE compliance_documents
                    SET document_number=COALESCE(%s, document_number),
                        issued_date=COALESCE(%s::date, issued_date),
                        expiry_date=COALESCE(%s::date, expiry_date),
                        days_until_expiry=CASE WHEN %s::date IS NULL THEN days_until_expiry ELSE (%s::date - CURRENT_DATE) END,
                        notes=COALESCE(%s, notes),
                        status=CASE WHEN %s::date IS NOT NULL THEN 'received' ELSE status END,
                        updated_at=now()
                    WHERE employee_key=%s AND document_type = ANY(%s)
                    RETURNING *
                    """,
                    (
                        document_number,
                        issue_date,
                        expiry_date,
                        expiry_date,
                        expiry_date,
                        reason,
                        expiry_date,
                        employee_key,
                        list({ctype, "residency_iqama", "residency"}),
                    ),
                )
                updated = cur.fetchone()
                if not updated:
                    raise DocumentJourneyError("document_not_found")
                _append_event(
                    cur,
                    legacy,
                    company_code=company,
                    employee_key=employee_key,
                    document_type=ctype,
                    version_id=None,
                    actor_user_id=actor_user_id,
                    actor_kind="hr",
                    action="correct_metadata",
                    reason=reason,
                    old_state={},
                    new_state={
                        "document_number": document_number,
                        "issue_date": issue_date,
                        "expiry_date": expiry_date,
                        "legitimacy": "hr_entered_metadata_ocr_unavailable_or_correction",
                    },
                )
                conn.commit()
                return dict(updated)
            old = dict(row)
            cur.execute(
                """
                UPDATE governed_document_versions
                SET issue_date=COALESCE(%s::date, issue_date),
                    expiry_date=COALESCE(%s::date, expiry_date),
                    document_number=COALESCE(%s, document_number),
                    confirmed_metadata = COALESCE(confirmed_metadata,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE version_id=%s
                RETURNING *
                """,
                (
                    issue_date,
                    expiry_date,
                    document_number,
                    json.dumps(
                        {
                            "document_number": document_number,
                            "issue_date": issue_date,
                            "expiry_date": expiry_date,
                            "correction_reason": reason,
                        }
                    ),
                    old["version_id"],
                ),
            )
            new = dict(cur.fetchone())
            cur.execute(
                """
                UPDATE compliance_documents
                SET document_number=COALESCE(%s, document_number),
                    issued_date=COALESCE(%s::date, issued_date),
                    expiry_date=COALESCE(%s::date, expiry_date),
                    days_until_expiry=CASE WHEN %s::date IS NULL THEN days_until_expiry ELSE (%s::date - CURRENT_DATE) END,
                    notes=COALESCE(%s, notes),
                    updated_at=now()
                WHERE employee_key=%s AND document_type = ANY(%s)
                """,
                (
                    document_number,
                    issue_date,
                    expiry_date,
                    expiry_date,
                    expiry_date,
                    reason,
                    employee_key,
                    list({ctype, "residency_iqama", "residency"}),
                ),
            )
            _append_event(
                cur,
                legacy,
                company_code=company,
                employee_key=employee_key,
                document_type=ctype,
                version_id=str(new["version_id"]),
                actor_user_id=actor_user_id,
                actor_kind="hr",
                action="correct_metadata",
                reason=reason,
                old_state={
                    "issue_date": str(old.get("issue_date") or ""),
                    "expiry_date": str(old.get("expiry_date") or ""),
                    "document_number": old.get("document_number"),
                },
                new_state={
                    "issue_date": issue_date,
                    "expiry_date": expiry_date,
                    "document_number": document_number,
                    "legitimacy": "hr_corrected_metadata",
                },
            )
        conn.commit()
    return new


def classify_display_status(row: Mapping[str, Any], *, warning_days: int = 30) -> str:
    review = str(row.get("review_status") or row.get("status") or "")
    if review == STATUS_REJECTED_REUPLOAD or review == "rejected_reupload":
        return STATUS_REJECTED_REUPLOAD
    if review in {STATUS_PENDING_HR_REVIEW, "received", "needs_review", "missing_expiry"}:
        return STATUS_PENDING_HR_REVIEW
    expiry = row.get("expiry_date")
    if isinstance(expiry, str):
        try:
            expiry = date.fromisoformat(expiry[:10])
        except Exception:
            expiry = None
    if isinstance(expiry, date):
        days = (expiry - _now().date()).days
        if days < 0:
            return STATUS_EXPIRED
        if days <= warning_days:
            return STATUS_EXPIRING_SOON
    if review in {STATUS_HR_REVIEWED, "valid", "hr_reviewed"}:
        return STATUS_HR_REVIEWED
    if review in {"missing", STATUS_MISSING}:
        return STATUS_MISSING
    return review or STATUS_MISSING


def list_employee_compliance_journey(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    locale: str = "en",
) -> list[dict[str, Any]]:
    company = _company(company_code)
    out: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_document_journey_schema(cur)
            cur.execute(
                """
                SELECT * FROM compliance_documents
                WHERE company_code=%s AND employee_key=%s
                ORDER BY document_type
                """,
                (company, employee_key),
            )
            compliance_rows = [dict(r) for r in (cur.fetchall() or [])]
            for crow in compliance_rows:
                ctype = canonical_compliance_type(crow.get("document_type"))
                cur.execute(
                    """
                    SELECT * FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s
                    ORDER BY version_no DESC
                    """,
                    (company, employee_key, ctype),
                )
                versions = [dict(v) for v in (cur.fetchall() or [])]
                current = next((v for v in versions if v.get("is_current")), versions[0] if versions else None)
                pending = next((v for v in versions if v.get("review_status") == STATUS_PENDING_HR_REVIEW), None)
                display_src = current or crow
                display = classify_display_status(
                    {
                        **crow,
                        "review_status": (current or {}).get("review_status") or crow.get("status"),
                        "expiry_date": (current or {}).get("expiry_date") or crow.get("expiry_date"),
                    },
                    warning_days=int(crow.get("warning_days") or 30),
                )
                ocr = (pending or current or {}).get("ocr_proposal") if isinstance((pending or current or {}).get("ocr_proposal"), dict) else {}
                out.append(
                    {
                        "document_type": ctype,
                        "legacy_document_type": crow.get("document_type"),
                        "label": document_label(ctype, locale=locale),
                        "label_ar": document_label(ctype, locale="ar"),
                        "review_status": display,
                        "review_status_label": hr_status_label(display, locale=locale),
                        "expiry_date": str((current or crow).get("expiry_date") or "") or None,
                        "issue_date": str((current or crow).get("issue_date") or crow.get("issued_date") or "") or None,
                        "rejection_reason": (pending or current or {}).get("rejection_reason") or crow.get("notes"),
                        "renewal_required": display in {STATUS_EXPIRED, STATUS_EXPIRING_SOON, STATUS_REJECTED_REUPLOAD},
                        "can_renew": True,
                        "current_version_id": str((current or {}).get("version_id") or "") or None,
                        "pending_version_id": str((pending or {}).get("version_id") or "") or None,
                        "current_file_id": (current or {}).get("file_id"),
                        "ocr_proposal": {k: v for k, v in ocr.items() if k != "raw"} if ocr else None,
                        "ocr_authoritative": False,
                        "legitimacy_note": "HR review confirms evidence was reviewed by authorized HR. This is not PACI, MOI, or PAM verification.",
                        "versions": [
                            {
                                "version_id": str(v.get("version_id")),
                                "version_no": v.get("version_no"),
                                "review_status": v.get("review_status"),
                                "is_current": bool(v.get("is_current")),
                                "file_id": v.get("file_id"),
                                "expiry_date": str(v.get("expiry_date") or "") or None,
                                "created_at": v.get("created_at"),
                            }
                            for v in versions
                        ],
                    }
                )
    return out


def automatic_legitimacy_checks(
    *,
    filename: str | None,
    mime_type: str | None,
    size_bytes: int | None,
    issue_date: str | None = None,
    expiry_date: str | None = None,
) -> dict[str, Any]:
    """File/date checks only — never government verification."""
    errors: list[str] = []
    allowed_ext = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".heic"}
    name = str(filename or "").lower()
    if name and not any(name.endswith(ext) for ext in allowed_ext):
        errors.append("unsupported_file_type")
    if size_bytes is not None and size_bytes > 15 * 1024 * 1024:
        errors.append("file_too_large")
    if issue_date and expiry_date:
        try:
            if date.fromisoformat(issue_date[:10]) > date.fromisoformat(expiry_date[:10]):
                errors.append("issue_after_expiry")
        except Exception:
            errors.append("invalid_date")
    return {
        "ok": not errors,
        "errors": errors,
        "meaning": "automatic_file_and_date_checks_only",
        "not": "paci_moi_pam_verification",
    }
