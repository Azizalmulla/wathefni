"""Civil ID front+back dual-side — attempt-scoped draft versions.

One checklist item (`civil_id` or disposable canary) · two parts on one governed
version · draft_parts until pair gate passes · same version promoted to
pending_hr_review. Never mixes historical opposite sides into a new attempt.

Flags (default off):
  WATHEFNI_CIVIL_ID_DUAL_SIDE
  WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES
  WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger("wathefni.onboarding_civil_id_dual_side")

_ON = frozenset({"1", "true", "yes", "on", "enabled"})

FLAG = "WATHEFNI_CIVIL_ID_DUAL_SIDE"
FLAG_COMPANIES = "WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES"
FLAG_ALLOWLIST = "WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST"

PARTS_SCHEMA = "civil_id_v1"
LEGACY_SCHEMA = "legacy_single"
STATUS_DRAFT_PARTS = "draft_parts"
PART_FRONT = "front"
PART_BACK = "back"
REQUIRED_PARTS = (PART_FRONT, PART_BACK)

DUAL_SIDE_ITEMS = frozenset({"civil_id", "civil_id_dual_side_canary"})
CANARY_ITEM = "civil_id_dual_side_canary"

# DocVal alias target for the disposable canary (validation only; storage lane stays canary).
CANARY_VALIDATION_ALIAS = "civil_id"


class DualSideError(Exception):
    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        status_code: int = 422,
        message_en: str | None = None,
        message_ar: str | None = None,
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status_code = status_code
        self.message_en = message_en or message or code
        self.message_ar = message_ar or message_en or message or code
        self.extra = extra or {}


def _env_on(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in _ON


def _parse_list(raw: str | None) -> set[str]:
    return {p.strip() for p in str(raw or "").split(",") if p.strip()}


def dual_side_flag_on() -> bool:
    return _env_on(FLAG)


def dual_side_enabled(*, company_code: str | None, employee_key: str | None) -> bool:
    if not dual_side_flag_on():
        return False
    company = str(company_code or "").strip().upper()
    key = str(employee_key or "").strip()
    companies = {c.upper() for c in _parse_list(os.environ.get(FLAG_COMPANIES))}
    allow = _parse_list(os.environ.get(FLAG_ALLOWLIST))
    if companies and company not in companies:
        return False
    if allow and key not in allow:
        return False
    return True


def is_dual_side_item(item_id: str | None) -> bool:
    return str(item_id or "").strip().lower() in DUAL_SIDE_ITEMS


def dual_side_applies(
    *,
    company_code: str | None,
    employee_key: str | None,
    item_id: str | None,
) -> bool:
    return dual_side_enabled(company_code=company_code, employee_key=employee_key) and is_dual_side_item(item_id)


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value)
    return json.dumps(value) if not isinstance(value, (str, bytes)) else value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dual_side_schema(cur: Any) -> None:
    """Extend governed versions for draft_parts + parts table. Idempotent."""
    import kuwait_pilot_document_journey as journey

    journey.ensure_document_journey_schema(cur)

    cur.execute(
        """
        ALTER TABLE governed_document_versions
          ADD COLUMN IF NOT EXISTS parts_schema text,
          ADD COLUMN IF NOT EXISTS parts_complete boolean NOT NULL DEFAULT false
        """
    )
    # Widen review_status CHECK to include draft_parts (idempotent).
    cur.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS def
        FROM pg_constraint
        WHERE conrelid = 'governed_document_versions'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%review_status%'
        """
    )
    needs_widen = True
    for row in cur.fetchall() or []:
        d = dict(row) if not isinstance(row, dict) else row
        defn = str(d.get("def") or "")
        name = str(d.get("conname") or "")
        if "draft_parts" in defn:
            needs_widen = False
        elif name:
            cur.execute(f"ALTER TABLE governed_document_versions DROP CONSTRAINT IF EXISTS {name}")
    if needs_widen:
        cur.execute(
            """
            ALTER TABLE governed_document_versions
              ADD CONSTRAINT governed_document_versions_review_status_check
              CHECK (review_status IN (
                'draft_parts','pending_hr_review','hr_reviewed','rejected_reupload',
                'superseded','expiring_soon','expired'
              ))
            """
        )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS governed_document_version_parts (
          part_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          version_id uuid NOT NULL REFERENCES governed_document_versions(version_id) ON DELETE CASCADE,
          part_key text NOT NULL,
          file_id text,
          file_sha256 text,
          filename text,
          mime_type text,
          detected_side text,
          ocr_proposal jsonb NOT NULL DEFAULT '{}'::jsonb,
          doc_validation jsonb NOT NULL DEFAULT '{}'::jsonb,
          hr_warning boolean NOT NULL DEFAULT false,
          uploaded_by text,
          uploaded_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (version_id, part_key),
          CHECK (part_key IN ('front','back'))
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS governed_document_version_parts_version_idx
          ON governed_document_version_parts (version_id)
        """
    )


def normalize_part(part: str | None) -> str:
    raw = str(part or "").strip().lower()
    if raw in REQUIRED_PARTS:
        return raw
    raise DualSideError(
        "part_required",
        "Upload the Civil ID front or back.",
        status_code=400,
        message_en="Choose Front or Back for this Civil ID upload.",
        message_ar="اختر الوجه الأمامي أو الخلفي لرفع البطاقة المدنية.",
    )


def _side_value(extraction: dict[str, Any] | None, verification: dict[str, Any] | None = None) -> str:
    for blob in (verification, extraction):
        if not isinstance(blob, dict):
            continue
        side = str(blob.get("side") or "").strip().lower()
        if side in {"front", "back", "single", "unknown"}:
            return side
        fields = blob.get("fields") if isinstance(blob.get("fields"), dict) else {}
        cell = fields.get("side")
        if isinstance(cell, dict) and cell.get("value"):
            s = str(cell.get("value") or "").strip().lower()
            if s in {"front", "back", "single", "unknown"}:
                return s
    return "unknown"


def _doc_number(extraction: dict[str, Any] | None) -> str:
    if not isinstance(extraction, dict):
        return ""
    for key in ("document_number", "civil_id_number", "id_number"):
        val = extraction.get(key)
        if val:
            return str(val).strip().upper().replace(" ", "")
    fields = extraction.get("fields") if isinstance(extraction.get("fields"), dict) else {}
    for key in ("document_number", "civil_id_number"):
        cell = fields.get(key)
        if isinstance(cell, dict) and cell.get("value"):
            return str(cell.get("value")).strip().upper().replace(" ", "")
        if cell:
            return str(cell).strip().upper().replace(" ", "")
    return ""


def validate_part_side(
    *,
    expected_part: str,
    extraction: dict[str, Any] | None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-part side gate. unknown is soft (HR warning); never satisfies 'missing'."""
    expected = normalize_part(expected_part)
    detected = _side_value(extraction, verification)
    hr_warning = False
    if detected in {"front", "back"} and detected != expected:
        raise DualSideError(
            "wrong_side",
            f"This looks like the Civil ID {detected}, but you selected {expected}.",
            status_code=422,
            message_en=f"This looks like the Civil ID {detected}. Please upload it as {detected}, or choose the correct side.",
            message_ar=(
                f"يبدو أن هذه صورة الوجه {('الأمامي' if detected == 'front' else 'الخلفي')} للبطاقة المدنية. "
                f"يرجى رفعها بالجانب الصحيح."
            ),
            extra={"expected_part": expected, "detected_side": detected},
        )
    if detected in {"unknown", "single"}:
        hr_warning = True
    return {"detected_side": detected, "hr_warning": hr_warning, "expected_part": expected}


def load_parts(cur: Any, version_id: str) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM governed_document_version_parts
        WHERE version_id=%s
        """,
        (version_id,),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall() or []:
        d = dict(row)
        out[str(d.get("part_key"))] = d
    return out


def parts_projection(parts: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    parts = parts or {}
    front = parts.get(PART_FRONT)
    back = parts.get(PART_BACK)

    def _slot(row: Mapping[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {"present": False, "file_id": None, "filename": None, "detected_side": None, "hr_warning": False}
        return {
            "present": True,
            "file_id": str(row.get("file_id") or "") or None,
            "filename": row.get("filename"),
            "mime_type": row.get("mime_type"),
            "file_sha256": row.get("file_sha256"),
            "detected_side": row.get("detected_side"),
            "hr_warning": bool(row.get("hr_warning")),
            "uploaded_at": row.get("uploaded_at"),
        }

    front_ok = bool(front and front.get("file_id"))
    back_ok = bool(back and back.get("file_id"))
    return {
        "schema": PARTS_SCHEMA,
        "front": _slot(front),
        "back": _slot(back),
        "parts_complete": front_ok and back_ok,
        "missing": [p for p, ok in ((PART_FRONT, front_ok), (PART_BACK, back_ok)) if not ok],
    }


def find_open_draft(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_type=%s
          AND review_status=%s
        ORDER BY version_no DESC
        LIMIT 1
        FOR UPDATE
        """,
        (str(company_code).upper(), employee_key, document_type, STATUS_DRAFT_PARTS),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def create_draft_attempt(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    uploaded_by: str | None,
    upload_source: str = "employee_dual_side",
) -> dict[str, Any]:
    import kuwait_pilot_document_journey as journey

    company = str(company_code).upper()
    ensure_dual_side_schema(cur)
    version_no = journey._next_version_no(cur, company, employee_key, document_type)
    cur.execute(
        """
        INSERT INTO governed_document_versions(
          company_code, employee_key, document_type, version_no, file_id, file_sha256,
          filename, mime_type, review_status, is_current, ocr_proposal,
          uploaded_by, upload_source, parts_schema, parts_complete
        )
        VALUES (%s,%s,%s,%s,NULL,NULL,NULL,NULL,%s,false,%s,%s,%s,%s,false)
        RETURNING *
        """,
        (
            company,
            employee_key,
            document_type,
            version_no,
            STATUS_DRAFT_PARTS,
            _json(legacy, {"parts_schema": PARTS_SCHEMA, "authoritative": False}),
            uploaded_by,
            upload_source,
            PARTS_SCHEMA,
        ),
    )
    row = dict(cur.fetchone())
    journey._append_event(
        cur,
        legacy,
        company_code=company,
        employee_key=employee_key,
        document_type=document_type,
        version_id=str(row["version_id"]),
        actor_user_id=uploaded_by,
        actor_kind="employee",
        action="dual_side_draft_created",
        reason=None,
        old_state={},
        new_state={"version_id": str(row["version_id"]), "review_status": STATUS_DRAFT_PARTS},
    )
    return row


def ensure_draft_attempt(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    uploaded_by: str | None,
    force_new: bool = False,
) -> dict[str, Any]:
    """Return open draft, or create one. force_new abandons prior draft (replacement)."""
    ensure_dual_side_schema(cur)
    if force_new:
        open_draft = find_open_draft(
            cur, company_code=company_code, employee_key=employee_key, document_type=document_type
        )
        if open_draft:
            cur.execute(
                """
                UPDATE governed_document_versions
                SET review_status='superseded', updated_at=now(), is_current=false
                WHERE version_id=%s AND review_status=%s
                """,
                (open_draft["version_id"], STATUS_DRAFT_PARTS),
            )
        return create_draft_attempt(
            cur,
            legacy,
            company_code=company_code,
            employee_key=employee_key,
            document_type=document_type,
            uploaded_by=uploaded_by,
        )
    existing = find_open_draft(
        cur, company_code=company_code, employee_key=employee_key, document_type=document_type
    )
    if existing:
        return existing
    return create_draft_attempt(
        cur,
        legacy,
        company_code=company_code,
        employee_key=employee_key,
        document_type=document_type,
        uploaded_by=uploaded_by,
    )


def evaluate_pair_gate(parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Both required parts must be present; duplicate/mismatch block; unknown → HR warn."""
    front = parts.get(PART_FRONT)
    back = parts.get(PART_BACK)
    if not front or not front.get("file_id"):
        return {"ok": False, "reason": "parts_incomplete", "missing": [PART_FRONT]}
    if not back or not back.get("file_id"):
        return {"ok": False, "reason": "parts_incomplete", "missing": [PART_BACK]}

    front_sha = str(front.get("file_sha256") or "")
    back_sha = str(back.get("file_sha256") or "")
    if front_sha and back_sha and front_sha == back_sha:
        return {"ok": False, "reason": "duplicate_sides", "message": "Front and back cannot be the same file."}

    front_side = str(front.get("detected_side") or "unknown").lower()
    back_side = str(back.get("detected_side") or "unknown").lower()
    if front_side == "back" or back_side == "front":
        return {"ok": False, "reason": "side_mismatch", "message": "Sides appear swapped or mismatched."}
    if front_side in {"front", "back"} and back_side in {"front", "back"} and front_side == back_side:
        return {"ok": False, "reason": "duplicate_sides", "message": "Both uploads look like the same side."}

    front_ocr = front.get("ocr_proposal") if isinstance(front.get("ocr_proposal"), dict) else {}
    back_ocr = back.get("ocr_proposal") if isinstance(back.get("ocr_proposal"), dict) else {}
    n1 = _doc_number(front_ocr)
    n2 = _doc_number(back_ocr)
    if n1 and n2 and n1 != n2:
        return {
            "ok": False,
            "reason": "identity_mismatch",
            "message": "Civil ID numbers on front and back do not match.",
        }

    hr_warnings: list[str] = []
    if front_side in {"unknown", "single"} or bool(front.get("hr_warning")):
        hr_warnings.append("front_side_uncertain")
    if back_side in {"unknown", "single"} or bool(back.get("hr_warning")):
        hr_warnings.append("back_side_uncertain")

    return {
        "ok": True,
        "reason": None,
        "hr_review_recommended": bool(hr_warnings),
        "hr_warnings": hr_warnings,
        "document_number": n1 or n2 or None,
    }


def attach_part(
    cur: Any,
    legacy: Any,
    *,
    version_id: str,
    part_key: str,
    file_id: str | None,
    file_sha256: str | None,
    filename: str | None,
    mime_type: str | None,
    detected_side: str | None,
    ocr_proposal: dict[str, Any] | None,
    doc_validation: dict[str, Any] | None,
    hr_warning: bool,
    uploaded_by: str | None,
) -> dict[str, Any]:
    part = normalize_part(part_key)
    parts = load_parts(cur, version_id)

    # Duplicate same SHA as the opposite part on this attempt.
    other_key = PART_BACK if part == PART_FRONT else PART_FRONT
    other = parts.get(other_key)
    if other and file_sha256 and str(other.get("file_sha256") or "") == str(file_sha256):
        raise DualSideError(
            "duplicate_sides",
            "Front and back must be different photos.",
            message_en="Front and back must be different photos of your Civil ID.",
            message_ar="يجب أن تكون صورة الوجه الأمامي مختلفة عن صورة الوجه الخلفي.",
        )

    same = parts.get(part)
    if same and file_sha256 and str(same.get("file_sha256") or "") == str(file_sha256):
        return {"idempotent": True, "part": dict(same), "parts": parts}

    # Duplicate same side with different bytes replaces in-place on this draft only.
    cur.execute(
        """
        INSERT INTO governed_document_version_parts(
          version_id, part_key, file_id, file_sha256, filename, mime_type,
          detected_side, ocr_proposal, doc_validation, hr_warning, uploaded_by
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (version_id, part_key) DO UPDATE SET
          file_id=EXCLUDED.file_id,
          file_sha256=EXCLUDED.file_sha256,
          filename=EXCLUDED.filename,
          mime_type=EXCLUDED.mime_type,
          detected_side=EXCLUDED.detected_side,
          ocr_proposal=EXCLUDED.ocr_proposal,
          doc_validation=EXCLUDED.doc_validation,
          hr_warning=EXCLUDED.hr_warning,
          uploaded_by=EXCLUDED.uploaded_by,
          uploaded_at=now(),
          updated_at=now()
        RETURNING *
        """,
        (
            version_id,
            part,
            file_id,
            file_sha256,
            filename,
            mime_type,
            detected_side,
            _json(legacy, ocr_proposal or {}),
            _json(legacy, doc_validation or {}),
            bool(hr_warning),
            uploaded_by,
        ),
    )
    row = dict(cur.fetchone())
    updated = load_parts(cur, version_id)
    return {"idempotent": False, "part": row, "parts": updated}


def promote_draft_to_hr_review(
    cur: Any,
    legacy: Any,
    *,
    version: Mapping[str, Any],
    parts: Mapping[str, Mapping[str, Any]],
    pair_result: Mapping[str, Any],
    actor_user_id: str | None,
) -> dict[str, Any]:
    """Promote the same draft version — never create a disconnected second version."""
    import kuwait_pilot_document_journey as journey

    if str(version.get("review_status")) != STATUS_DRAFT_PARTS:
        raise DualSideError("not_draft", "This Civil ID attempt is not an open draft.", status_code=409)

    gate = pair_result if pair_result.get("ok") else evaluate_pair_gate(parts)
    if not gate.get("ok"):
        raise DualSideError(
            str(gate.get("reason") or "parts_incomplete"),
            str(gate.get("message") or "Both Civil ID sides are required before HR review."),
            status_code=422,
            message_en=str(gate.get("message") or "Upload both the front and back of your Civil ID."),
            message_ar="يرجى رفع الوجه الأمامي والخلفي للبطاقة المدنية قبل المراجعة.",
            extra=dict(gate),
        )

    front = parts[PART_FRONT]
    back = parts[PART_BACK]
    # Authoritative display file = front; both retained on parts table.
    primary_file_id = str(front.get("file_id") or "") or None
    primary_sha = str(front.get("file_sha256") or "") or None
    primary_name = str(front.get("filename") or "civil_id_front") 
    primary_mime = front.get("mime_type")

    front_ocr = front.get("ocr_proposal") if isinstance(front.get("ocr_proposal"), dict) else {}
    back_ocr = back.get("ocr_proposal") if isinstance(back.get("ocr_proposal"), dict) else {}
    merged_ocr = {
        "authoritative": False,
        "parts_schema": PARTS_SCHEMA,
        "parts": {"front": front_ocr, "back": back_ocr},
        "document_number": gate.get("document_number") or _doc_number(front_ocr) or _doc_number(back_ocr),
        "expiry_date": front_ocr.get("expiry_date") or back_ocr.get("expiry_date"),
        "issue_date": front_ocr.get("issue_date") or front_ocr.get("issued_date") or back_ocr.get("issue_date"),
        "hr_review_recommended": bool(gate.get("hr_review_recommended")),
        "hr_warnings": list(gate.get("hr_warnings") or []),
        "pair_validated_at": _now_iso(),
    }

    cur.execute(
        """
        UPDATE governed_document_versions
        SET review_status='pending_hr_review',
            parts_complete=true,
            parts_schema=%s,
            file_id=%s,
            file_sha256=%s,
            filename=%s,
            mime_type=%s,
            document_number=COALESCE(%s, document_number),
            ocr_proposal=%s,
            updated_at=now()
        WHERE version_id=%s AND review_status=%s
        RETURNING *
        """,
        (
            PARTS_SCHEMA,
            primary_file_id,
            primary_sha,
            primary_name,
            primary_mime,
            merged_ocr.get("document_number"),
            _json(legacy, merged_ocr),
            version["version_id"],
            STATUS_DRAFT_PARTS,
        ),
    )
    promoted = cur.fetchone()
    if not promoted:
        raise DualSideError("promote_conflict", "Could not promote this Civil ID draft.", status_code=409)
    promoted_d = dict(promoted)

    journey._append_event(
        cur,
        legacy,
        company_code=str(version.get("company_code")),
        employee_key=str(version.get("employee_key")),
        document_type=str(version.get("document_type")),
        version_id=str(version["version_id"]),
        actor_user_id=actor_user_id,
        actor_kind="employee",
        action="dual_side_promoted_to_hr_review",
        reason=None,
        old_state={"review_status": STATUS_DRAFT_PARTS},
        new_state={
            "review_status": "pending_hr_review",
            "parts_complete": True,
            "hr_warnings": list(gate.get("hr_warnings") or []),
        },
    )
    return promoted_d


def assert_version_approvable(cur: Any, version: Mapping[str, Any]) -> None:
    """HR must not approve incomplete dual-side drafts."""
    schema = str(version.get("parts_schema") or "")
    status = str(version.get("review_status") or "")
    if status == STATUS_DRAFT_PARTS:
        raise DualSideError(
            "parts_incomplete",
            "Civil ID front and back are still being collected.",
            status_code=409,
            message_en="Wait until both Civil ID sides are submitted before approving.",
            message_ar="انتظر حتى يتم رفع وجهي البطاقة المدنية قبل الموافقة.",
        )
    if schema == PARTS_SCHEMA:
        if not bool(version.get("parts_complete")):
            raise DualSideError(
                "parts_incomplete",
                "Both Civil ID sides are required before approval.",
                status_code=409,
            )
        parts = load_parts(cur, str(version["version_id"]))
        gate = evaluate_pair_gate(parts)
        if not gate.get("ok"):
            raise DualSideError(
                str(gate.get("reason") or "parts_incomplete"),
                str(gate.get("message") or "Pair validation failed."),
                status_code=409,
                extra=dict(gate),
            )


def decorate_dual_side_item(
    item: dict[str, Any],
    *,
    version: dict[str, Any] | None,
    parts: dict[str, dict[str, Any]] | None,
    can_upload: bool,
    lifecycle_on: bool,
) -> dict[str, Any]:
    """Annotate checklist projection with parts + side-specific actions."""
    import onboarding_lifecycle_wave2a as lc

    row = dict(item)
    status = lc.normalize_status(row.get("status")) if lifecycle_on else str(row.get("status") or "pending")
    proj = parts_projection(parts)
    review_status = str((version or {}).get("review_status") or row.get("review_status") or "")
    schema = str((version or {}).get("parts_schema") or "")

    # Accepted legacy single-file stays accepted / untouched UX.
    legacy_accepted = status in {lc.STATE_ACCEPTED, lc.STATE_WAIVED} and schema != PARTS_SCHEMA
    if legacy_accepted:
        row["civil_id_parts"] = {
            "schema": LEGACY_SCHEMA,
            "legacy_single": True,
            "parts_complete": True,
            "front": {"present": bool(row.get("file_id")), "file_id": row.get("file_id")},
            "back": {"present": False, "file_id": None},
            "missing": [],
        }
        # Keep standard preview/view_versions; no side upload actions.
        return row

    row["civil_id_parts"] = {
        **proj,
        "version_id": str((version or {}).get("version_id") or "") or None,
        "review_status": review_status or None,
        "attempt_open": review_status == STATUS_DRAFT_PARTS,
    }
    if proj["front"]["present"] and proj["front"].get("file_id"):
        row["file_id"] = proj["front"]["file_id"]
    elif proj["back"]["present"] and proj["back"].get("file_id") and not row.get("file_id"):
        row["file_id"] = proj["back"]["file_id"]

    actions = list(row.get("actions") or [])
    # Replace generic upload with side slots while collecting.
    collecting = status in {
        lc.STATE_PENDING,
        lc.STATE_IN_PROGRESS,
        lc.STATE_REPLACEMENT_REQUIRED,
        lc.STATE_REJECTED,
    } or review_status == STATUS_DRAFT_PARTS
    under_review = status in {lc.STATE_SUBMITTED, lc.STATE_PROCESSING} or review_status == "pending_hr_review"

    filtered = [a for a in actions if a not in {"upload", "replace", "resubmit"}]
    if can_upload and collecting and not under_review:
        if not proj["front"]["present"]:
            filtered.append("upload_front")
        else:
            filtered.append("replace_front")
            filtered.append("preview_front")
        if not proj["back"]["present"]:
            filtered.append("upload_back")
        else:
            filtered.append("replace_back")
            filtered.append("preview_back")
        if status == lc.STATE_REPLACEMENT_REQUIRED:
            filtered.append("resubmit")
    elif under_review or status in {lc.STATE_ACCEPTED, lc.STATE_WAIVED}:
        if proj["front"]["present"]:
            filtered.append("preview_front")
        if proj["back"]["present"]:
            filtered.append("preview_back")
        if "preview" not in filtered and row.get("file_id"):
            filtered.append("preview")
        if "view_versions" not in filtered:
            filtered.append("view_versions")

    # Dedupe preserve order
    seen: set[str] = set()
    row["actions"] = [a for a in filtered if not (a in seen or seen.add(a))]
    row["parts_complete"] = bool(proj.get("parts_complete")) and review_status != STATUS_DRAFT_PARTS
    return row


def http_error_detail(exc: DualSideError) -> dict[str, Any]:
    detail = {
        "error": f"document_validation_{exc.code}" if not str(exc.code).startswith("document_") else exc.code,
        "reason": exc.code,
        "message": exc.message_en,
        "message_en": exc.message_en,
        "message_ar": exc.message_ar,
        "validation": {
            "gate": "civil_id_dual_side",
            "decision": "block",
            "reason": exc.code,
        },
    }
    detail.update(exc.extra)
    return detail


def load_version_parts_bundle(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    document_types: list[str],
) -> dict[str, dict[str, Any]]:
    """Latest dual-side-aware version + parts keyed by document_type."""
    ensure_dual_side_schema(cur)
    if not document_types:
        return {}
    cur.execute(
        """
        SELECT DISTINCT ON (document_type)
          version_id, document_type, version_no, file_id, filename, mime_type,
          review_status, is_current, rejection_reason, created_at, reviewed_at,
          parts_schema, parts_complete, ocr_proposal, file_sha256
        FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_type = ANY(%s)
        ORDER BY document_type,
          CASE review_status
            WHEN 'draft_parts' THEN 0
            WHEN 'pending_hr_review' THEN 1
            WHEN 'rejected_reupload' THEN 2
            WHEN 'hr_reviewed' THEN 3
            ELSE 4
          END,
          version_no DESC
        """,
        (str(company_code).upper(), employee_key, list(document_types)),
    )
    out: dict[str, dict[str, Any]] = {}
    for r in cur.fetchall() or []:
        row = dict(r)
        vid = str(row.get("version_id") or "")
        row["parts"] = load_parts(cur, vid) if vid else {}
        out[str(row.get("document_type") or "")] = row
    return out
