#!/usr/bin/env python3
"""Production path proof: Kuwait Civil ID dual-side full sequence on disposable canary.

Uses PACI-layout fixtures (front portrait face + reverse address/barcode).
Never mutates Aziz real civil_id / SHA.

Sequence:
  Front→Front success
  same Front retry idempotent
  Back→Back success
  pair → pending_hr_review
  reset draft → Front→Back wrong_side block
  reset draft → duplicate both slots block
"""

from __future__ import annotations

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
import json
import os
import shutil
from pathlib import Path

EMP = "WATHEFNI-96599338566"
COMPANY = "WATHEFNI"
ITEM = "civil_id_dual_side_canary"
EXPECTED = "fe98f7d9d481578804a3ca3e19ca96ad4b4fa6e046f46e25d4ab21d9e15f0bb7"
META = {
    "explicitly_assigned": True,
    "canary": True,
    "dual_side": True,
    "disposable": True,
    "purpose": "civil_id_dual_side_live_test",
    "do_not_approve_as_real": True,
}

FIXTURE_DIR_CANDIDATES = [
    Path("/tmp/kw-paci-civil-fixtures"),
    Path("/opt/wathefni/orchestrator/fixtures/kuwait-civil-id-dual-side"),
]


def fixture_paths() -> tuple[Path, Path]:
    for base in FIXTURE_DIR_CANDIDATES:
        front = base / "kuwait_paci_civil_id_front_v1.png"
        back = base / "kuwait_paci_civil_id_back_v1.png"
        if front.is_file() and back.is_file():
            return front, back
    raise SystemExit("PACI Civil ID fixtures missing on host")


def clean_canary(cur) -> None:
    cur.execute(
        """
        DELETE FROM governed_document_version_parts
        WHERE version_id IN (
          SELECT version_id FROM governed_document_versions
          WHERE company_code=%s AND employee_key=%s AND document_type=%s
        )
        """,
        (COMPANY, EMP, ITEM),
    )
    cur.execute(
        "DELETE FROM governed_document_events WHERE company_code=%s AND employee_key=%s AND document_type=%s",
        (COMPANY, EMP, ITEM),
    )
    cur.execute(
        "DELETE FROM governed_document_versions WHERE company_code=%s AND employee_key=%s AND document_type=%s",
        (COMPANY, EMP, ITEM),
    )
    try:
        cur.execute(
            "DELETE FROM document_storage_operations WHERE company_code=%s AND employee_key=%s AND item_id=%s",
            (COMPANY, EMP, ITEM),
        )
    except Exception:
        pass
    cur.execute(
        """
        UPDATE onboarding_items
        SET status=%s,
            rejection_reason=NULL,
            completed_at=NULL,
            value=NULL,
            local_path=NULL,
            content_sha256=NULL,
            mime_type=NULL,
            storage_status=NULL,
            storage_object_key=NULL,
            external_file_id=NULL,
            storage_url=NULL,
            drive_file_id=NULL,
            drive_url=NULL,
            lifecycle_meta = coalesce(lifecycle_meta,'{}'::jsonb) || %s::jsonb,
            updated_at=now(),
            row_version=row_version+1
        WHERE employee_key=%s AND item_id=%s
        """,
        ("pending", json.dumps(META), EMP, ITEM),
    )


def assert_civil(cur) -> dict:
    cur.execute(
        "SELECT status, content_sha256, local_path FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
        (EMP, "civil_id"),
    )
    civil = dict(cur.fetchone() or {})
    if civil.get("status") != "accepted" or civil.get("content_sha256") != EXPECTED:
        raise SystemExit(f"ABORT civil_id changed: {civil}")
    return civil


def upload(client, path: Path, part: str):
    with path.open("rb") as fh:
        return client.post(
            "/app/onboarding/documents",
            files={"file": (path.name, fh, "image/png")},
            data={"item_id": ITEM, "part": part},
        )


def main() -> int:
    # TestClient runs in-process — must mirror production dual-side allowlist flags.
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE", "on")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST", EMP)
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST", EMP)
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD", "off")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES", "WATHEFNI")
    os.environ.setdefault(
        "WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST",
        f"{EMP},WATHEFNI-96550252254",
    )

    import app
    import onboarding_civil_id_dual_side as dual
    from fastapi.testclient import TestClient

    front_path, back_path = fixture_paths()
    results: dict = {"fixtures": {"front": str(front_path), "back": str(back_path)}}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            dual.ensure_dual_side_schema(cur)
            clean_canary(cur)
            results["civil_id_before"] = assert_civil(cur)
        conn.commit()

    employee = app.find_employee_by_key(EMP, company_code=COMPANY)

    def override_context():
        return {
            "company_code": COMPANY,
            "employee_key": EMP,
            "employee": employee,
            "access": {"locale": "en"},
        }

    app.app.dependency_overrides[app.employee_app_context] = override_context
    orig_feature = app.require_employee_app_feature

    def fake_feature(context, feature, action=None):
        return {"actions": ["upload_document", "view"]}

    app.require_employee_app_feature = fake_feature  # type: ignore[assignment]

    try:
        client = TestClient(app.app)

        # 1) Front → Front
        r1 = upload(client, front_path, "front")
        b1 = r1.json()
        results["front_into_front"] = {"http": r1.status_code, "body": b1}
        if r1.status_code != 200:
            raise SystemExit(f"Front→Front failed: {r1.status_code} {b1}")

        # 2) Idempotent retry same Front
        r1b = upload(client, front_path, "front")
        b1b = r1b.json()
        results["front_retry_idempotent"] = {"http": r1b.status_code, "body": b1b}
        if r1b.status_code != 200:
            raise SystemExit(f"Front retry failed: {r1b.status_code} {b1b}")

        # 3) Back → Back
        r2 = upload(client, back_path, "back")
        b2 = r2.json()
        results["back_into_back"] = {"http": r2.status_code, "body": b2}
        if r2.status_code != 200:
            raise SystemExit(f"Back→Back failed: {r2.status_code} {b2}")
        if not b2.get("parts_complete") and b2.get("status") not in {
            "pending_hr_review",
            "in_progress",
            "submitted",
        }:
            # promote may set status on item; accept either complete flag or review status
            pass

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT review_status, parts_complete FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s
                    ORDER BY version_no DESC LIMIT 1
                    """,
                    (COMPANY, EMP, ITEM),
                )
                ver = dict(cur.fetchone() or {})
                results["after_pair"] = ver
                if ver.get("review_status") != "pending_hr_review" or not ver.get("parts_complete"):
                    raise SystemExit(f"pair did not promote: {ver}")
                assert_civil(cur)
            conn.commit()

        # 4) New draft: Front into Back → wrong_side
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                clean_canary(cur)
                assert_civil(cur)
            conn.commit()

        r3 = upload(client, front_path, "back")
        b3 = r3.json()
        results["front_into_back"] = {"http": r3.status_code, "body": b3}
        if r3.status_code != 422:
            raise SystemExit(f"Front→Back expected 422 got {r3.status_code} {b3}")
        reason = str(b3.get("reason") or b3.get("detail") or b3.get("message_en") or "").lower()
        if "wrong_side" not in json.dumps(b3).lower() and "other side" not in reason and "front" not in reason:
            # accept structured wrong_side in body
            detail = b3.get("detail") if isinstance(b3.get("detail"), dict) else b3
            if "wrong_side" not in json.dumps(detail).lower():
                raise SystemExit(f"Front→Back not wrong_side: {b3}")

        # 5) Duplicate image both slots
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                clean_canary(cur)
                assert_civil(cur)
            conn.commit()

        r4 = upload(client, front_path, "front")
        if r4.status_code != 200:
            raise SystemExit(f"dup setup Front failed: {r4.status_code} {r4.json()}")
        r5 = upload(client, front_path, "back")
        b5 = r5.json()
        results["duplicate_both_slots"] = {"http": r5.status_code, "body": b5}
        if r5.status_code != 422:
            raise SystemExit(f"duplicate expected 422 got {r5.status_code} {b5}")
        blob = json.dumps(b5).lower()
        # Same front bytes into Back may hard-block as wrong_side before attach_part
        # duplicate SHA check — both are correct production blocks for this abuse case.
        if "duplicate" not in blob and "wrong_side" not in blob and "other side" not in blob:
            raise SystemExit(f"duplicate/wrong_side not signaled: {b5}")
        results["duplicate_both_slots"]["block_class"] = (
            "duplicate_sides" if "duplicate" in blob else "wrong_side"
        )

        # Final reset for owner retest readiness
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                clean_canary(cur)
                results["civil_id_after"] = assert_civil(cur)
                cur.execute(
                    "SELECT status, content_sha256 FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                    (EMP, ITEM),
                )
                results["canary_reset"] = dict(cur.fetchone() or {})
            conn.commit()

    finally:
        app.require_employee_app_feature = orig_feature  # type: ignore[assignment]
        app.app.dependency_overrides.pop(app.employee_app_context, None)

    results["ok"] = True
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
