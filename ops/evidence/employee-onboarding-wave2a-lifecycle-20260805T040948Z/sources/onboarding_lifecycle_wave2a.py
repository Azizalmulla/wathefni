#!/usr/bin/env python3
"""Onboarding Wave 2A — shared document/checklist lifecycle foundation.

Single authority for employee-app and HR web transitions. Feature-flagged;
does not implement bank ESS, OCR classify/verify parity, or template overlays.

Canonical employee-facing states (stored on onboarding_items.status when flag on):
  pending → in_progress → submitted → processing → accepted
  submitted|processing → rejected → replacement_required → submitted
  * → waived | blocked

Legacy `received` is never employee-facing when the flag is on: mapped/backfilled
to `processing` (awaiting HR). Weak-confidence historical uploads are not auto-rejected.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

_ON = frozenset({"1", "true", "yes", "on", "enabled"})

# Canonical states (employee + HR shared contract).
STATE_PENDING = "pending"
STATE_IN_PROGRESS = "in_progress"
STATE_SUBMITTED = "submitted"
STATE_PROCESSING = "processing"
STATE_ACCEPTED = "accepted"
STATE_REJECTED = "rejected"
STATE_REPLACEMENT_REQUIRED = "replacement_required"
STATE_WAIVED = "waived"
STATE_BLOCKED = "blocked"

CANONICAL_STATES = frozenset(
    {
        STATE_PENDING,
        STATE_IN_PROGRESS,
        STATE_SUBMITTED,
        STATE_PROCESSING,
        STATE_ACCEPTED,
        STATE_REJECTED,
        STATE_REPLACEMENT_REQUIRED,
        STATE_WAIVED,
        STATE_BLOCKED,
    }
)

# Legacy / alternate spellings → canonical (read path + backfill).
LEGACY_STATUS_MAP: dict[str, str] = {
    "pending": STATE_PENDING,
    "missing": STATE_PENDING,
    "requested": STATE_PENDING,
    "in_progress": STATE_IN_PROGRESS,
    "submitted": STATE_SUBMITTED,
    "processing": STATE_PROCESSING,
    # Ambiguous historical receipt → awaiting HR review (not final).
    "received": STATE_PROCESSING,
    "needs_review": STATE_PROCESSING,
    "accepted": STATE_ACCEPTED,
    "complete": STATE_ACCEPTED,
    "completed": STATE_ACCEPTED,
    "verified": STATE_ACCEPTED,
    "approved": STATE_ACCEPTED,
    "reviewed": STATE_ACCEPTED,
    "rejected": STATE_REJECTED,
    "replacement_required": STATE_REPLACEMENT_REQUIRED,
    "reupload_required": STATE_REPLACEMENT_REQUIRED,
    "waived": STATE_WAIVED,
    "cancelled_onboarding": STATE_WAIVED,
    "blocked": STATE_BLOCKED,
    "abandoned_employment_ended": STATE_BLOCKED,
    "retired_legacy": STATE_WAIVED,
}

# Who may initiate each transition (service owner).
TRANSITION_OWNERS: dict[tuple[str, str], str] = {
    (STATE_PENDING, STATE_IN_PROGRESS): "employee_app|hr|system",
    (STATE_PENDING, STATE_SUBMITTED): "employee_app",
    (STATE_IN_PROGRESS, STATE_SUBMITTED): "employee_app",
    (STATE_SUBMITTED, STATE_PROCESSING): "document_pipeline",
    (STATE_PROCESSING, STATE_ACCEPTED): "hr_review",
    (STATE_SUBMITTED, STATE_ACCEPTED): "hr_review",
    (STATE_PROCESSING, STATE_REJECTED): "hr_review",
    (STATE_SUBMITTED, STATE_REJECTED): "hr_review",
    (STATE_REJECTED, STATE_REPLACEMENT_REQUIRED): "hr_review",
    (STATE_PROCESSING, STATE_REPLACEMENT_REQUIRED): "hr_review",
    (STATE_REPLACEMENT_REQUIRED, STATE_SUBMITTED): "employee_app",
    (STATE_ACCEPTED, STATE_REPLACEMENT_REQUIRED): "hr_review",  # rare re-open
    (STATE_PENDING, STATE_WAIVED): "hr_review",
    (STATE_IN_PROGRESS, STATE_WAIVED): "hr_review",
    (STATE_PROCESSING, STATE_WAIVED): "hr_review",
    (STATE_REPLACEMENT_REQUIRED, STATE_WAIVED): "hr_review",
    (STATE_PENDING, STATE_BLOCKED): "system|hr_review",
    (STATE_IN_PROGRESS, STATE_BLOCKED): "system|hr_review",
}

COMPLETE_STATES = frozenset({STATE_ACCEPTED, STATE_WAIVED})
EMPLOYEE_ACTION_STATES = frozenset(
    {STATE_PENDING, STATE_IN_PROGRESS, STATE_REPLACEMENT_REQUIRED, STATE_REJECTED}
)
REVIEW_STATES = frozenset({STATE_SUBMITTED, STATE_PROCESSING})

DOCUMENT_COLLECTION_MODES = frozenset({"document", "file", "media"})


def lifecycle_enabled(*, company_code: str | None = None, employee_key: str | None = None) -> bool:
    if (os.environ.get("WATHEFNI_ONBOARDING_LIFECYCLE_V2A") or "").strip().lower() not in _ON:
        return False
    companies = {
        c.strip().upper()
        for c in (os.environ.get("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    }
    if company_code and str(company_code).upper() not in companies:
        return False
    allow = {
        k.strip()
        for k in (os.environ.get("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST") or "").split(",")
        if k.strip()
    }
    if allow and employee_key and str(employee_key).strip() not in allow:
        return False
    return True


def ensure_lifecycle_schema(cur: Any) -> None:
    cur.execute(
        """
        ALTER TABLE onboarding_items
          ADD COLUMN IF NOT EXISTS rejection_reason text,
          ADD COLUMN IF NOT EXISTS completed_at timestamptz,
          ADD COLUMN IF NOT EXISTS lifecycle_meta jsonb NOT NULL DEFAULT '{}'::jsonb
        """
    )


def normalize_status(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    if not key:
        return STATE_PENDING
    if key in CANONICAL_STATES:
        return key
    return LEGACY_STATUS_MAP.get(key, STATE_PENDING)


def is_lifecycle_complete(status: str | None) -> bool:
    return normalize_status(status) in COMPLETE_STATES


def responsible_party(item: dict[str, Any]) -> str:
    """Who the item is waiting on right now."""
    status = normalize_status(item.get("status"))
    authority = str(item.get("authority") or "").lower()
    owner = str(item.get("owner") or "").lower()
    category = str(item.get("category") or "").lower()
    item_id = str(item.get("item_id") or "").lower()
    collection = str(item.get("collection_mode") or item.get("item_type") or "").lower()

    if status in COMPLETE_STATES:
        return "none"
    if status == STATE_BLOCKED:
        return "system"
    if status in REVIEW_STATES:
        return "hr"
    if status in {STATE_REPLACEMENT_REQUIRED, STATE_REJECTED}:
        return "employee"
    if authority == "ess" or collection == "ess_encrypted" or item_id == "bank_details":
        return "employee"  # Wave 2B will surface bank UI; still employee-owned
    if authority == "compliance_mirror" or category == "compliance_gov":
        return "compliance"
    if category == "payroll_bank" or item_id in {
        "salary_transfer_details",
        "salary_allowances_confirmed",
        "payroll_status",
    }:
        return "payroll" if status not in EMPLOYEE_ACTION_STATES else "payroll"
    if owner in {"hr", "system"} and collection not in DOCUMENT_COLLECTION_MODES | {"ack", "text", "date"}:
        return "hr" if owner == "hr" else "system"
    if owner == "employee" or collection in DOCUMENT_COLLECTION_MODES | {"ack", "text", "date", "ess_encrypted"}:
        return "employee"
    if owner == "hr":
        return "hr"
    if owner == "system":
        return "system"
    return "hr"


def _is_document_item(item: dict[str, Any]) -> bool:
    mode = str(item.get("collection_mode") or "").lower()
    itype = str(item.get("item_type") or "").lower()
    return bool(item.get("document_type")) or mode in DOCUMENT_COLLECTION_MODES or itype == "document"


def _employee_visible(item: dict[str, Any]) -> bool:
    """Surface employee-owned actionable + optional docs; hide pure HR/system rails."""
    owner = str(item.get("owner") or "").lower()
    authority = str(item.get("authority") or "").lower()
    mode = str(item.get("collection_mode") or "").lower()
    item_id = str(item.get("item_id") or "").lower()
    if authority == "compliance_mirror":
        return False
    if item_id == "bank_details" or mode == "ess_encrypted":
        return True  # visible but Wave 2A actions empty for bank submit
    if owner == "employee":
        return True
    # HR-owned document the employee already submitted still needs visibility in review/completed
    status = normalize_status(item.get("status"))
    if _is_document_item(item) and status in REVIEW_STATES | COMPLETE_STATES | {
        STATE_REPLACEMENT_REQUIRED,
        STATE_REJECTED,
    }:
        return True
    return False


def actions_for_item(
    item: dict[str, Any],
    *,
    can_upload: bool,
    lifecycle_on: bool,
) -> list[str]:
    if not lifecycle_on:
        # Legacy: document upload only when pending-ish
        if can_upload and _is_document_item(item) and not is_lifecycle_complete(item.get("status")):
            st = str(item.get("status") or "").lower()
            if st in {"received", "complete", "completed", "verified", "approved", "reviewed"}:
                return ["preview"] if item.get("file_id") else []
            return ["upload"]
        return []

    status = normalize_status(item.get("status"))
    mode = str(item.get("collection_mode") or "").lower()
    item_id = str(item.get("item_id") or "").lower()
    actions: list[str] = []
    if item.get("file_id") or item.get("current_file_id"):
        actions.append("preview")
        actions.append("view_versions")
    if mode == "ess_encrypted" or item_id == "bank_details":
        # Wave 2B — no submit yet
        return actions
    if not _is_document_item(item):
        return actions
    if not can_upload:
        return actions
    if status in {STATE_PENDING, STATE_IN_PROGRESS}:
        actions.append("upload")
    if status == STATE_REPLACEMENT_REQUIRED:
        actions.append("replace")
        actions.append("resubmit")
    if status == STATE_REJECTED:
        actions.append("resubmit")
    # Do not allow replace while processing/accepted (approved evidence protected)
    return actions


def group_key_for_item(item: dict[str, Any]) -> str:
    status = normalize_status(item.get("status"))
    party = responsible_party(item)
    if status in COMPLETE_STATES:
        return "completed"
    if status in REVIEW_STATES:
        return "being_reviewed"
    if party in {"hr", "payroll", "compliance", "system"} and status in EMPLOYEE_ACTION_STATES:
        # Employee-owned but waiting on someone else is rare; still "your_actions" if they must act
        pass
    if party == "employee" and status in EMPLOYEE_ACTION_STATES | {STATE_PENDING, STATE_IN_PROGRESS}:
        return "your_actions"
    if party in {"hr", "payroll", "compliance", "system"}:
        return "handled_by_others"
    if status in EMPLOYEE_ACTION_STATES:
        return "your_actions"
    return "handled_by_others"


def decorate_item(
    item: dict[str, Any],
    *,
    file_id: str | None = None,
    version: dict[str, Any] | None = None,
    can_upload: bool = False,
    lifecycle_on: bool = True,
) -> dict[str, Any]:
    row = dict(item)
    raw_status = row.get("status")
    status = normalize_status(raw_status) if lifecycle_on else str(raw_status or "pending")
    row["status"] = status
    row["legacy_status"] = raw_status
    row["authority"] = row.get("authority") or "onboarding"
    row["collection_mode"] = row.get("collection_mode") or row.get("item_type") or "document"
    row["owner"] = row.get("owner") or "employee"
    row["responsible_party"] = responsible_party(row) if lifecycle_on else (
        "employee" if str(row.get("owner") or "") == "employee" else "hr"
    )
    row["file_id"] = file_id or row.get("file_id")
    if version:
        row["current_version_id"] = str(version.get("version_id") or "") or None
        row["current_version_no"] = version.get("version_no")
        row["review_status"] = version.get("review_status")
        row["version_filename"] = version.get("filename")
        row["version_mime_type"] = version.get("mime_type")
        if version.get("rejection_reason") and not row.get("rejection_reason"):
            row["rejection_reason"] = version.get("rejection_reason")
        if version.get("file_id") and not row.get("file_id"):
            row["file_id"] = str(version.get("file_id"))
    row["replacement_required"] = status == STATE_REPLACEMENT_REQUIRED
    row["waiting_on"] = row["responsible_party"]
    row["completed_at"] = row.get("completed_at")
    row["actions"] = actions_for_item(row, can_upload=can_upload, lifecycle_on=lifecycle_on)
    row["group"] = group_key_for_item(row) if lifecycle_on else (
        "completed" if str(raw_status or "").lower() in {"received", "complete", "completed", "verified"} else "your_actions"
    )
    return row


def load_latest_versions_by_type(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, dict[str, Any]]:
    """Latest governed version per document_type (prefer pending review, else highest version_no)."""
    cur.execute(
        """
        SELECT DISTINCT ON (document_type)
          version_id, document_type, version_no, file_id, filename, mime_type,
          review_status, is_current, rejection_reason, created_at, reviewed_at
        FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s
        ORDER BY document_type,
          CASE review_status
            WHEN 'pending_hr_review' THEN 0
            WHEN 'rejected_reupload' THEN 1
            WHEN 'hr_reviewed' THEN 2
            ELSE 3
          END,
          version_no DESC
        """,
        (str(company_code).upper(), employee_key),
    )
    out: dict[str, dict[str, Any]] = {}
    for r in cur.fetchall() or []:
        row = dict(r)
        out[str(row.get("document_type") or "")] = row
    return out


def build_employee_projection(
    items: list[dict[str, Any]],
    *,
    company_code: str,
    employee_key: str,
    file_index: dict[str, str],
    versions_by_type: dict[str, dict[str, Any]],
    can_upload: bool,
    lifecycle_on: bool,
) -> dict[str, Any]:
    decorated: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("item_id") or "")
        doc_type = str(item.get("document_type") or item_id)
        fid = file_index.get(item_id) or file_index.get(doc_type)
        version = versions_by_type.get(doc_type) or versions_by_type.get(item_id)
        # Prefer canonical compliance type keys used in governed versions
        if not version and doc_type:
            for k, v in versions_by_type.items():
                if k == doc_type or k.replace("-", "_") == doc_type:
                    version = v
                    break
        row = decorate_item(
            item,
            file_id=fid,
            version=version,
            can_upload=can_upload,
            lifecycle_on=lifecycle_on,
        )
        if lifecycle_on and not _employee_visible(row):
            continue
        decorated.append(row)

    groups = {
        "your_actions": [],
        "being_reviewed": [],
        "handled_by_others": [],
        "completed": [],
    }
    for row in decorated:
        groups.setdefault(row.get("group") or "handled_by_others", []).append(row)

    required = [i for i in decorated if i.get("required") is True]
    accepted = [i for i in required if is_lifecycle_complete(i.get("status"))]
    open_required = [i for i in required if not is_lifecycle_complete(i.get("status"))]

    return {
        "lifecycle_version": "2a" if lifecycle_on else "legacy",
        "items": decorated,
        "groups": groups,
        "your_actions": groups["your_actions"],
        "being_reviewed": groups["being_reviewed"],
        "handled_by_others": groups["handled_by_others"],
        "completed": groups["completed"],
        # Legacy keys kept for older clients during canary.
        "pending": [i for i in open_required if i.get("group") == "your_actions"],
        "received": groups["completed"] + groups["being_reviewed"],
        "required_total": len(required),
        "received_count": len(accepted),
        "pending_count": len(open_required),
        "accepted_count": len(accepted),
    }


def set_item_lifecycle(
    cur: Any,
    *,
    employee_key: str,
    item_id: str,
    new_status: str,
    rejection_reason: str | None = None,
    clear_rejection: bool = False,
    completed_at: datetime | None = None,
    meta_patch: dict[str, Any] | None = None,
) -> None:
    from psycopg2.extras import Json

    status = normalize_status(new_status)
    meta = dict(meta_patch or {})
    meta["lifecycle_updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["lifecycle_status"] = status
    if rejection_reason:
        meta["rejection_reason"] = rejection_reason

    completed = completed_at
    if status in COMPLETE_STATES and completed is None:
        completed = datetime.now(timezone.utc)
    if status not in COMPLETE_STATES:
        completed = None

    if clear_rejection:
        cur.execute(
            """
            UPDATE onboarding_items
            SET status=%s,
                rejection_reason=NULL,
                completed_at=%s,
                lifecycle_meta = COALESCE(lifecycle_meta, '{}'::jsonb) || %s::jsonb,
                updated_at=now()
            WHERE employee_key=%s AND item_id=%s
            """,
            (status, completed, Json(meta), employee_key, item_id),
        )
    elif rejection_reason is not None:
        cur.execute(
            """
            UPDATE onboarding_items
            SET status=%s,
                rejection_reason=%s,
                completed_at=%s,
                lifecycle_meta = COALESCE(lifecycle_meta, '{}'::jsonb) || %s::jsonb,
                updated_at=now()
            WHERE employee_key=%s AND item_id=%s
            """,
            (status, rejection_reason, completed, Json(meta), employee_key, item_id),
        )
    else:
        cur.execute(
            """
            UPDATE onboarding_items
            SET status=%s,
                completed_at=%s,
                lifecycle_meta = COALESCE(lifecycle_meta, '{}'::jsonb) || %s::jsonb,
                updated_at=now()
            WHERE employee_key=%s AND item_id=%s
            """,
            (status, completed, Json(meta), employee_key, item_id),
        )


def apply_employee_document_submit(
    cur: Any,
    *,
    employee_key: str,
    item_id: str,
    file_id: str | None,
    version_id: str | None,
    content_sha256: str | None,
) -> str:
    """Employee upload → submitted then processing (sync pipeline). Returns final status."""
    set_item_lifecycle(
        cur,
        employee_key=employee_key,
        item_id=item_id,
        new_status=STATE_SUBMITTED,
        clear_rejection=True,
        meta_patch={
            "last_submit_file_id": file_id,
            "last_submit_version_id": version_id,
            "last_submit_sha256": content_sha256,
            "phase": "submitted",
        },
    )
    set_item_lifecycle(
        cur,
        employee_key=employee_key,
        item_id=item_id,
        new_status=STATE_PROCESSING,
        clear_rejection=True,
        meta_patch={
            "last_submit_file_id": file_id,
            "last_submit_version_id": version_id,
            "last_submit_sha256": content_sha256,
            "phase": "processing",
            "awaiting": "hr_review",
        },
    )
    return STATE_PROCESSING


def apply_hr_approve_to_checklist(
    cur: Any,
    *,
    employee_key: str,
    document_type: str,
) -> list[str]:
    """Map HR approve of a document type onto matching onboarding item(s)."""
    cur.execute(
        """
        SELECT item_id FROM onboarding_items
        WHERE employee_key=%s AND (item_id=%s OR document_type=%s)
        """,
        (employee_key, document_type, document_type),
    )
    ids = [str(r["item_id"]) for r in (cur.fetchall() or [])]
    for iid in ids:
        set_item_lifecycle(
            cur,
            employee_key=employee_key,
            item_id=iid,
            new_status=STATE_ACCEPTED,
            clear_rejection=True,
            meta_patch={"phase": "accepted", "source": "hr_approve"},
        )
    return ids


def apply_hr_reject_to_checklist(
    cur: Any,
    *,
    employee_key: str,
    document_type: str,
    reason: str,
) -> list[str]:
    cur.execute(
        """
        SELECT item_id FROM onboarding_items
        WHERE employee_key=%s AND (item_id=%s OR document_type=%s)
        """,
        (employee_key, document_type, document_type),
    )
    ids = [str(r["item_id"]) for r in (cur.fetchall() or [])]
    for iid in ids:
        # rejected → replacement_required (mandatory reason)
        set_item_lifecycle(
            cur,
            employee_key=employee_key,
            item_id=iid,
            new_status=STATE_REJECTED,
            rejection_reason=reason,
            meta_patch={"phase": "rejected", "source": "hr_reject"},
        )
        set_item_lifecycle(
            cur,
            employee_key=employee_key,
            item_id=iid,
            new_status=STATE_REPLACEMENT_REQUIRED,
            rejection_reason=reason,
            meta_patch={"phase": "replacement_required", "source": "hr_reject"},
        )
    return ids


def backfill_received_to_processing(
    cur: Any,
    *,
    company_code: str,
    employee_keys: list[str] | None = None,
) -> int:
    """Deterministic canary backfill: received → processing. Never auto-reject."""
    ensure_lifecycle_schema(cur)
    if employee_keys:
        cur.execute(
            """
            UPDATE onboarding_items oi
            SET status='processing',
                lifecycle_meta = COALESCE(oi.lifecycle_meta, '{}'::jsonb)
                  || jsonb_build_object(
                       'backfilled_from', 'received',
                       'backfill_wave', '2a',
                       'backfilled_at', now()
                     ),
                updated_at=now()
            FROM employees e
            WHERE oi.employee_key = e.employee_key
              AND e.company_code=%s
              AND oi.employee_key = ANY(%s)
              AND lower(oi.status)='received'
            """,
            (str(company_code).upper(), list(employee_keys)),
        )
    else:
        cur.execute(
            """
            UPDATE onboarding_items oi
            SET status='processing',
                lifecycle_meta = COALESCE(oi.lifecycle_meta, '{}'::jsonb)
                  || jsonb_build_object(
                       'backfilled_from', 'received',
                       'backfill_wave', '2a',
                       'backfilled_at', now()
                     ),
                updated_at=now()
            FROM employees e
            WHERE oi.employee_key = e.employee_key
              AND e.company_code=%s
              AND lower(oi.status)='received'
            """,
            (str(company_code).upper(),),
        )
    return int(cur.rowcount or 0)


def find_idempotent_pending_version(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    content_sha256: str | None,
) -> dict[str, Any] | None:
    if not content_sha256:
        return None
    cur.execute(
        """
        SELECT * FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_type=%s
          AND file_sha256=%s
          AND review_status='pending_hr_review'
        ORDER BY version_no DESC
        LIMIT 1
        """,
        (str(company_code).upper(), employee_key, document_type, content_sha256),
    )
    row = cur.fetchone()
    return dict(row) if row else None
