#!/usr/bin/env python3
"""Prod smoke: first Front dual-side upload path that previously 500'd.

Reproduces the live failure mode:
  DocVal allow + OCR extraction containing datetime.date → attach_part jsonb insert.

Uses FastAPI TestClient (in-process) with DocVal patched to allow, multipart
item_id=civil_id_dual_side_canary + part=front. Does not mutate real civil_id.
"""

from __future__ import annotations

import json
import os
from datetime import date
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


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")

    import app
    import onboarding_civil_id_dual_side as dual
    import onboarding_doc_validation_parity as docval
    import onboarding_lifecycle_wave2a as lc
    from fastapi.testclient import TestClient

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            dual.ensure_dual_side_schema(cur)
            clean_canary(cur)
            civil = assert_civil(cur)
        conn.commit()

    # Use a tiny real jpeg bytes (synthetic 1x1 is fine once DocVal is patched).
    img_path = Path("/tmp/dual-side-smoke-front.jpg")
    # Minimal JPEG
    img_path.write_bytes(
        bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
            "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
            "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
            "0d1832211c2132323232323232323232323232323232323232323232323232323232"
            "323232323232323232323232323232323232323232ffc00011080001000103011100"
            "02110311ffc40014000100000000000000000000000000000000ffc4001410010000"
            "0000000000000000000000000000ffda000c0301000210031000003f00bf80ffd9"
        )
    )

    employee = app.find_employee_by_key(EMP, company_code=COMPANY)

    def fake_eval(**kwargs):
        return {
            "ok": True,
            "decision": "allow",
            "gate": "soft",
            "reason": None,
            "item_id": ITEM,
            "validation_item_id": "civil_id",
            "detected_side": "front",
            "side_uncertain": False,
            "hr_review_recommended": False,
            "gpt_used": False,
            "quality_issues": [],
            "route": {"document_class": "identity"},
            "verification": {"side": "front", "detected_item": "civil_id", "confidence": 0.99},
            "extraction": {
                "side": "front",
                "document_number": "290000001234",
                "expiry_date": date(2028, 6, 1),  # the previous 500 trigger
                "issue_date": date(2020, 1, 15),
                "full_name_en": "ABDULAZIZ H R ALMULLA",
                "confidence": 0.99,
            },
            "identity_check": {"matched": True},
            "message_en": None,
            "message_ar": None,
        }

    orig_eval = docval.evaluate_employee_upload
    docval.evaluate_employee_upload = fake_eval  # type: ignore[assignment]

    def override_context():
        return {
            "company_code": COMPANY,
            "employee_key": EMP,
            "employee": employee,
            "access": {"locale": "en"},
        }

    app.app.dependency_overrides[app.employee_app_context] = override_context
    # Feature gate helpers used inside upload
    orig_feature = app.require_employee_app_feature

    def fake_feature(context, feature, action=None):
        return {"actions": ["upload_document", "view"]}

    app.require_employee_app_feature = fake_feature  # type: ignore[assignment]

    try:
        client = TestClient(app.app)
        with img_path.open("rb") as fh:
            resp = client.post(
                "/app/onboarding/documents",
                files={"file": ("front.jpg", fh, "image/jpeg")},
                data={"item_id": ITEM, "part": "front"},
            )
        body = resp.json()
        print(json.dumps({"http_status": resp.status_code, "body": body}, indent=2, default=str))
        if resp.status_code != 200:
            raise SystemExit(f"expected 200 got {resp.status_code}")
        assert body.get("item_id") == ITEM
        assert body.get("part") == "front"
        assert body.get("parts_complete") is False
    finally:
        docval.evaluate_employee_upload = orig_eval  # type: ignore[assignment]
        app.require_employee_app_feature = orig_feature  # type: ignore[assignment]
        app.app.dependency_overrides.pop(app.employee_app_context, None)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            assert_civil(cur)
            cur.execute(
                "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                (EMP, ITEM),
            )
            canary = dict(cur.fetchone())
            cur.execute(
                """
                SELECT version_id, review_status, document_type, parts_complete
                FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type=%s
                ORDER BY version_no DESC LIMIT 1
                """,
                (COMPANY, EMP, ITEM),
            )
            ver = dict(cur.fetchone() or {})
            parts = dual.load_parts(cur, str(ver["version_id"])) if ver.get("version_id") else {}
            # Prove date survived jsonb round-trip
            front_ocr = (parts.get("front") or {}).get("ocr_proposal") or {}
        conn.commit()

    proof = {
        "canary_status": canary.get("status"),
        "review_status": ver.get("review_status"),
        "document_type_lane": ver.get("document_type"),
        "front_present": bool((parts.get("front") or {}).get("file_id")),
        "back_present": bool((parts.get("back") or {}).get("file_id")),
        "ocr_expiry_serialized": front_ocr.get("expiry_date"),
    }
    print(json.dumps(proof, indent=2, default=str))
    assert proof["front_present"] and not proof["back_present"]
    assert proof["review_status"] == "draft_parts"
    assert proof["document_type_lane"] == ITEM
    assert str(proof["ocr_expiry_serialized"]).startswith("2028")
    print("FIRST_FRONT_UPLOAD_SMOKE_PASS")

    # Reset for phone retest
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            clean_canary(cur)
            assert_civil(cur)
        conn.commit()

    summary = app.employee_onboarding_summary(employee, company_code=COMPANY)
    index = app.employee_document_index(COMPANY, EMP)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            versions = lc.load_latest_versions_by_type(cur, company_code=COMPANY, employee_key=EMP)
        conn.commit()
    proj = lc.build_employee_projection(
        list(summary.get("items") or []),
        company_code=COMPANY,
        employee_key=EMP,
        file_index=index,
        versions_by_type=versions,
        can_upload=True,
        lifecycle_on=True,
    )
    row = next(i for i in proj["items"] if i.get("item_id") == ITEM)
    print(json.dumps({"status": row.get("status"), "group": row.get("group"), "actions": row.get("actions")}, indent=2))
    assert row.get("group") == "your_actions"
    assert "upload_front" in (row.get("actions") or []) and "upload_back" in (row.get("actions") or [])
    print("READY_FOR_PHONE_RETEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
