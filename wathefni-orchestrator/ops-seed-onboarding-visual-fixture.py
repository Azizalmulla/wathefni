#!/usr/bin/env python3
"""Seed a disposable synthetic canary for Employee App Onboarding visual QA.

Target: WATHEFNI-9655237101 (W2B-SYNTH| Onboarding Visual)
  - Phone prefix 965523 + W2B-SYNTH| name → onboarding synthetic canary gate
  - Never touches Aziz / Talal

States seeded (Wave 2A groups):
  Your actions      — bank_details pending, personal_photo pending, civil_id replacement_required
  Being reviewed    — passport processing (employee doc), offer_letter processing (HR)
  Handled by others — department_assigned + job_title_confirmed pending (HR)
  Completed         — employment_contract + several optional accepted/waived
  Realistic progress via canonical completion over required items

Cleanup deletes fixture-tagged items/files/versions for this key only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _pds  # noqa: E402

_pds.activate_fixture_tooling_from_argv()
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")
os.environ.setdefault("WATHEFNI_ONBOARDING_SYNTHETIC_CANARY", "on")
os.environ.setdefault("WATHEFNI_ONBOARDING_SYNTHETIC_PHONE_PREFIXES", "965523")
os.environ.setdefault("WATHEFNI_ONBOARDING_SYNTHETIC_NAME_PREFIX", "W2B-SYNTH|")
os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A", "on")
os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ONBOARDING_SEED", "off")  # synthetic path only
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST", "on")

COMPANY = os.environ["WATHEFNI_COMPANY_CODE"]
PHONE = "9655237101"
KEY = f"{COMPANY}-{PHONE}"
NAME = "W2B-SYNTH| Onboarding Visual"
TAG = "onboarding-visual-fixture"
STAMP = os.environ.get("ONBOARDING_VISUAL_STAMP") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}
MINI_PDF = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

# Expand allowlists in-process so seed + invite verification match live service
# after the companion drop-in conf is applied.
_ALLOW_EXTRA = KEY
for env_key in (
    "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST",
    "WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST",
):
    cur = {x.strip() for x in (os.environ.get(env_key) or "").split(",") if x.strip()}
    cur.add(_ALLOW_EXTRA)
    # Keep prior canaries so in-process imports do not strip them.
    cur.update(
        {
            "WATHEFNI-96550010001",
            "WATHEFNI-96550252254",
            "WATHEFNI-9655497001",
            "WATHEFNI-9655497002",
            "WATHEFNI-9655497003",
            "WATHEFNI-96599338566",
        }
    )
    os.environ[env_key] = ",".join(sorted(cur))

import app as legacy  # noqa: E402
import onboarding_lifecycle_wave2a as lifecycle  # noqa: E402
from psycopg2.extras import Json  # noqa: E402


def _guard() -> None:
    if KEY in PROTECTED:
        raise SystemExit(f"refusing protected canary key {KEY}")


def _fixture_dir() -> Path:
    root = Path(os.environ.get("WATHEFNI_WORKSPACE") or "/root/.openclaw/workspaces/company-wathefni")
    path = root / "fixtures" / TAG / STAMP
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup() -> dict[str, Any]:
    _guard()
    deleted = {"items": 0, "versions": 0, "files": 0, "events": 0, "assignment": 0}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM governed_document_events
                WHERE company_code=%s AND employee_key=%s
                  AND (
                    COALESCE(reason,'') = %s
                    OR COALESCE(new_state->>'fixture','') = %s
                  )
                """,
                (COMPANY, KEY, TAG, TAG),
            )
            deleted["events"] = cur.rowcount
            cur.execute(
                """
                DELETE FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s
                  AND COALESCE(confirmed_metadata->>'fixture','') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            deleted["versions"] = cur.rowcount
            cur.execute(
                """
                DELETE FROM file_registry
                WHERE company_code=%s AND subject_type='employee' AND subject_key=%s
                  AND COALESCE(metadata->>'fixture','') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            deleted["files"] = cur.rowcount
            # Dedicated synth — wipe checklist wholesale (never used for reals).
            cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s", (KEY,))
            deleted["items"] = cur.rowcount
            cur.execute(
                """
                UPDATE employee_onboarding_assignments
                SET status='not_started', updated_at=now(),
                    metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                WHERE employee_key=%s AND company_code=%s
                """,
                (json.dumps({"fixture_cleanup": TAG, "stamp": STAMP}), KEY, COMPANY),
            )
            deleted["assignment"] = cur.rowcount
            cur.execute(
                """
                UPDATE employees
                SET onboarding_status='not_started', updated_at=now()
                WHERE employee_key=%s AND company_code=%s
                """,
                (KEY, COMPANY),
            )
        conn.commit()
    return {"employee_key": KEY, "deleted": deleted, "stamp": STAMP}


def _write_pdf(name: str) -> tuple[Path, str, int]:
    path = _fixture_dir() / name
    body = MINI_PDF + f"\n% {TAG}:{STAMP}:{name}\n".encode()
    path.write_bytes(body)
    return path, hashlib.sha256(body).hexdigest(), len(body)


def _insert_file(cur: Any, *, document_type: str, filename: str) -> str:
    path, digest, size = _write_pdf(filename)
    file_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO file_registry (
          file_id, company_code, owner_phone, subject_type, subject_key, file_kind,
          document_type, original_filename, source_path, local_path,
          storage_provider, content_sha256, mime_type, size_bytes, storage_status,
          metadata, raw_json, stored_at, updated_at
        ) VALUES (
          %s,%s,%s,'employee',%s,'onboarding_document',
          %s,%s,%s,%s,
          'local',%s,'application/pdf',%s,'stored',
          %s,%s,now(),now()
        )
        RETURNING file_id
        """,
        (
            file_id,
            COMPANY,
            PHONE,
            KEY,
            document_type,
            filename,
            str(path),
            str(path),
            digest,
            size,
            Json({"fixture": TAG, "stamp": STAMP}),
            Json({"fixture": TAG, "stamp": STAMP}),
        ),
    )
    return str(cur.fetchone()["file_id"])


def _insert_version(
    cur: Any,
    *,
    document_type: str,
    file_id: str,
    review_status: str,
    rejection_reason: str | None = None,
) -> str:
    import kuwait_pilot_document_journey as journey

    journey.ensure_document_journey_schema(cur)
    # Clear prior fixture currents for this type so is_current stays unique.
    cur.execute(
        """
        UPDATE governed_document_versions
        SET is_current=false, updated_at=now()
        WHERE company_code=%s AND employee_key=%s AND document_type=%s
          AND COALESCE(confirmed_metadata->>'fixture','') = %s
        """,
        (COMPANY, KEY, document_type, TAG),
    )
    version_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO governed_document_versions (
          version_id, company_code, employee_key, document_type, version_no,
          file_id, filename, mime_type, review_status, is_current,
          rejection_reason, confirmed_metadata, upload_source, created_at, updated_at
        ) VALUES (
          %s,%s,%s,%s,1,
          %s,%s,'application/pdf',%s,true,
          %s,%s,%s,now(),now()
        )
        """,
        (
            version_id,
            COMPANY,
            KEY,
            document_type,
            file_id,
            f"{document_type}-{STAMP}.pdf",
            review_status,
            rejection_reason,
            Json({"fixture": TAG, "stamp": STAMP}),
            TAG,
        ),
    )
    return version_id


def _ensure_employee() -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (
                  company_code, employee_key, phone, name,
                  onboarding_status, employment_status, created_at, updated_at,
                  raw_json
                ) VALUES (%s,%s,%s,%s,'in_progress','active',now(),now(),%s)
                ON CONFLICT (employee_key) DO UPDATE
                SET phone=EXCLUDED.phone,
                    name=EXCLUDED.name,
                    onboarding_status='in_progress',
                    employment_status='active',
                    updated_at=now(),
                    raw_json = COALESCE(employees.raw_json,'{}'::jsonb) || EXCLUDED.raw_json
                """,
                (
                    COMPANY,
                    KEY,
                    PHONE,
                    NAME,
                    Json({"fixture": TAG, "stamp": STAMP, "synthetic": True}),
                ),
            )
        conn.commit()
    emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or {}
    if not emp.get("app_access_enabled"):
        import employee_app_access as access

        access.set_employee_app_access(
            legacy,
            {
                "company_code": COMPANY,
                "user_id": TAG,
                "actor_user_id": TAG,
                "email": f"{TAG}@wathefni.ai",
                "permissions": ["employees.manage", "onboarding.manage"],
            },
            employee_key=KEY,
            enabled=True,
            reason=TAG,
            deliver_invite=False,
        )
        emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or emp
    return emp


def _set_item(
    cur: Any,
    item_id: str,
    *,
    status: str,
    rejection_reason: str | None = None,
    completed: bool = False,
    meta_extra: dict[str, Any] | None = None,
) -> None:
    meta = {"fixture": TAG, "stamp": STAMP, **(meta_extra or {})}
    cur.execute(
        """
        UPDATE onboarding_items
        SET status=%s,
            rejection_reason=%s,
            completed_at=CASE WHEN %s THEN COALESCE(completed_at, now()) ELSE NULL END,
            lifecycle_meta = COALESCE(lifecycle_meta,'{}'::jsonb) || %s::jsonb,
            raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
            updated_at=now()
        WHERE employee_key=%s AND item_id=%s
        """,
        (
            status,
            rejection_reason,
            completed,
            Json(meta),
            Json({"fixture": TAG, "stamp": STAMP}),
            KEY,
            item_id,
        ),
    )


def seed() -> dict[str, Any]:
    _guard()
    cleanup()
    emp = _ensure_employee()
    seeded_count = 0
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            lifecycle.ensure_lifecycle_schema(cur)
            seeded_count = legacy.seed_onboarding_items(cur, emp)
            # Tag every row for this employee so cleanup is safe even if seed
            # re-ran and left untagged rows from a prior attempt.
            cur.execute(
                """
                UPDATE onboarding_items
                SET lifecycle_meta = COALESCE(lifecycle_meta,'{}'::jsonb) || %s::jsonb,
                    raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                WHERE employee_key=%s
                """,
                (Json({"fixture": TAG, "stamp": STAMP}), Json({"fixture": TAG, "stamp": STAMP}), KEY),
            )

            # --- Completed (quiet record)
            for item_id in ("employment_contract", "residence", "nda_signed"):
                _set_item(cur, item_id, status="accepted", completed=True)
            _set_item(cur, "medical_check", status="waived", completed=True)

            # --- Your actions (strong) — keep a tight set
            _set_item(cur, "personal_photo", status="pending")
            _set_item(cur, "bank_details", status="pending")
            _set_item(
                cur,
                "civil_id",
                status="replacement_required",
                rejection_reason="Photo is too blurry — please resubmit a sharper Civil ID.",
            )

            # --- Being reviewed
            _set_item(cur, "passport", status="processing")
            _set_item(cur, "offer_letter", status="processing")

            # --- Handled by others
            # Employee-visible rows in this section require a non-review /
            # non-complete status with party hr|payroll|compliance|system.
            # Dormant HR tasks are intentionally hidden by Wave 2A visibility;
            # a blocked employee item is the supported way to surface the section.
            _set_item(
                cur,
                "work_permit",
                status="blocked",
                meta_extra={"explicitly_assigned": True, "applicable": True},
            )
            _set_item(cur, "department_assigned", status="pending")
            _set_item(cur, "job_title_confirmed", status="pending")
            _set_item(cur, "first_day_checklist", status="pending")

            # Quiet the remaining optional employee pending rows so Your actions
            # stays focused (not a wall of optional template leftovers).
            keep_open = {
                "personal_photo",
                "bank_details",
                "civil_id",
                "passport",
                "offer_letter",
                "work_permit",
                "department_assigned",
                "job_title_confirmed",
                "first_day_checklist",
            }
            cur.execute(
                """
                SELECT item_id, owner, status, required
                FROM onboarding_items
                WHERE employee_key=%s
                """,
                (KEY,),
            )
            for row in cur.fetchall() or []:
                iid = str(row.get("item_id") or "")
                if iid in keep_open:
                    continue
                st = str(row.get("status") or "").lower()
                if st in {"accepted", "waived", "processing", "submitted", "replacement_required", "rejected"}:
                    continue
                # Optional leftovers → waived; required leftovers (unexpected) → accepted
                # so progress stays realistic without inventing extra employee work.
                target = "waived" if row.get("required") is False else "accepted"
                _set_item(cur, iid, status=target, completed=True)

            # Files for previewable rows (completed / review / needs-correction)
            files: dict[str, str] = {}
            for doc, review, reason in (
                ("employment_contract", "hr_reviewed", None),
                ("passport", "pending_hr_review", None),
                ("civil_id", "rejected_reupload", "Photo is too blurry — please resubmit a sharper Civil ID."),
            ):
                fid = _insert_file(cur, document_type=doc, filename=f"{doc}-{STAMP}.pdf")
                files[doc] = fid
                _insert_version(
                    cur,
                    document_type=doc,
                    file_id=fid,
                    review_status=review,
                    rejection_reason=reason,
                )

            # Keep assignment / employee status in-progress for realistic Home card.
            cur.execute(
                """
                UPDATE employees
                SET onboarding_status='in_progress', updated_at=now()
                WHERE employee_key=%s AND company_code=%s
                """,
                (KEY, COMPANY),
            )
            try:
                import onboarding_wave2 as wave2

                wave2.upsert_assignment(
                    cur,
                    employee_key=KEY,
                    company_code=COMPANY,
                    status="in_progress",
                    planned_start_date=None,
                    bump_version=True,
                    metadata={"fixture": TAG, "stamp": STAMP},
                )
            except Exception:
                pass
            try:
                legacy.recompute_employee_onboarding_counts(cur, KEY)
            except Exception:
                pass
        conn.commit()

    # Mint invite for device activation.
    invite_code = None
    invite_expires = None
    emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or emp
    invite, code = legacy.create_employee_app_invite(
        COMPANY, emp, created_by_user_id=TAG
    )
    invite_code = code
    invite_expires = (invite or {}).get("expires_at") if isinstance(invite, dict) else None

    # Authoritative projection snapshot for evidence.
    items = legacy.load_onboarding_items(employee_key=KEY, company_code=COMPANY)
    index = legacy.employee_document_index(COMPANY, KEY)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            versions = lifecycle.load_latest_versions_by_type(
                cur, company_code=COMPANY, employee_key=KEY
            )
        conn.commit()
    projection = lifecycle.build_employee_projection(
        items,
        company_code=COMPANY,
        employee_key=KEY,
        file_index=index,
        versions_by_type=versions,
        can_upload=True,
        lifecycle_on=True,
        previously_completed=False,
        bank_ess_eligible=False,
    )
    groups = {
        k: [str(i.get("item_id")) for i in (projection.get(k) or [])]
        for k in ("your_actions", "being_reviewed", "handled_by_others", "completed")
    }
    completion = projection.get("completion") or {}

    return {
        "ok": True,
        "stamp": STAMP,
        "employee_key": KEY,
        "phone": PHONE,
        "name": NAME,
        "activation_code": invite_code,
        "invite_expires_at": str(invite_expires) if invite_expires else None,
        "seeded_template_rows": seeded_count,
        "groups": groups,
        "group_counts": {k: len(v) for k, v in groups.items()},
        "required_total": projection.get("required_total"),
        "accepted_count": projection.get("accepted_count"),
        "completion_state": completion.get("state"),
        "next_action": completion.get("next_action"),
        "tag": TAG,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        out = cleanup()
    else:
        out = seed()
    text = json.dumps(out, indent=2, default=str)
    print(text)
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
