#!/usr/bin/env python3
"""P3 name-identity guard smoke against wathefni_p3_safe_updates_test.xlsx.

Expected preview totals on live WATHEFNI roster:
  create=1 (Lulwa)
  update=2 (Fahad email/title, Mariam manager)
  skip=1 (Noura)
  review=1 (Different Salem Name via external ID → material name)
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ORCH = os.environ.get("ORCH_ROOT") or os.path.dirname(os.path.abspath(__file__))
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")

FIXTURE = Path(
    os.environ.get("EMF_P3_FIXTURE")
    or "/opt/wathefni/orchestrator/fixtures-wathefni_p3_safe_updates_test.xlsx"
)


def _fail(msg: str) -> None:
    print(f"FAIL emf-p3-name-guard: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def main() -> None:
    import employee_migration_foundation as emf
    import app as legacy

    if not FIXTURE.is_file():
        _fail(f"fixture missing: {FIXTURE}")
    if emf.CONTRACT_VERSION < "1.1.1":
        _fail(f"expected contract >= 1.1.1, got {emf.CONTRACT_VERSION}")

    # Unit: normalization / material check
    if not emf._names_compatible("Salem Aldosari", "Salem Al-Dosari"):
        _fail("al- spacing should be compatible")
    if not emf._names_compatible("Fahad Alenezi", "fahad  alenezi"):
        _fail("case/spacing should be compatible")
    if emf._names_compatible("Salem Aldosari", "Different Salem Name"):
        _fail("Different Salem Name must be material")
    if not emf._names_compatible(
        "Salem Aldosari",
        "Salem A.",
        known_aliases=["Salem A."],
    ):
        _fail("known alias should be compatible")
    _ok("name compatibility helpers")

    company = "WATHEFNI"
    context = {
        "company_code": company,
        "user_id": "smoke-emf-p3-name",
        "email": "smoke-emf-p3-name@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin
    legacy.require_employee_roster_admin = lambda ctx, permission="employees.manage": company  # type: ignore[assignment]
    legacy.company_has_module = lambda code, module: False  # type: ignore[assignment]

    try:
        raw = FIXTURE.read_bytes()
        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=raw,
            filename=FIXTURE.name,
            source_system=None,
            idempotency_key=f"p3-name-guard-{uuid.uuid4().hex[:10]}",
        )
        totals = preview.get("totals") or {}
        create = int(totals.get("create") or 0)
        update = int(totals.get("update") or 0)
        skip = int(totals.get("skip") or 0)
        review = int(totals.get("review") if totals.get("review") is not None else totals.get("conflict") or 0)
        print(f"TOTALS create={create} update={update} skip={skip} review={review}")
        if (create, update, skip, review) != (1, 2, 1, 1):
            _fail(f"expected 1/2/1/1 got {create}/{update}/{skip}/{review}")

        created_names = {r["name"] for r in preview["results"]["created"]}
        updated_names = {r["name"] for r in preview["results"]["updated"]}
        skipped_names = {r["name"] for r in preview["results"]["skipped"]}
        review_rows = preview["results"]["needs_review"]
        if "Lulwa Alshammari" not in created_names:
            _fail(f"Lulwa missing from create: {created_names}")
        if "Fahad Alenezi" not in updated_names or "Mariam Almulla" not in updated_names:
            _fail(f"Fahad/Mariam missing from update: {updated_names}")
        if "Noura Almutairi" not in skipped_names:
            _fail(f"Noura missing from skip: {skipped_names}")
        if len(review_rows) != 1 or "Different Salem Name" not in review_rows[0]["name"]:
            _fail(f"Salem review unexpected: {review_rows}")
        if not (review_rows[0].get("name_identity_review") and review_rows[0].get("approvable")):
            _fail("Salem row missing name_identity_review/approvable")
        if review_rows[0].get("employee_key") != "WATHEFNI-96550010006":
            _fail(f"must keep Salem employee_key mapping, got {review_rows[0].get('employee_key')}")

        # Approve name change → moves to will_update; mapping/key unchanged
        row_id = review_rows[0].get("row_id")
        if not row_id:
            _fail("review row missing row_id")
        approved = emf.approve_identity_name_change(
            legacy,
            context,
            batch_id=preview["batch_id"],
            row_id=str(row_id),
        )
        at = approved.get("totals") or {}
        if int(at.get("review") or 0) != 0 or int(at.get("update") or 0) != 3:
            _fail(f"after approve expected update=3 review=0 got {at}")
        if not any(
            r.get("name") == "Different Salem Name" and r.get("status") == "will_update"
            for r in (approved["results"].get("updated") or [])
        ):
            _fail("approved Salem not in will_update")

        # Mapping still points at same key
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key FROM employee_source_mappings
                    WHERE company_code=%s AND source_system=%s AND external_employee_id=%s AND active
                    """,
                    (company, "test_erp", "ERP-EMP-1006"),
                )
                hit = cur.fetchone()
                conn.commit()
        if not hit or str(hit["employee_key"] if isinstance(hit, dict) else hit[0]) != "WATHEFNI-96550010006":
            _fail("source mapping broken after approve")
        _ok("exact fixture preview 1/2/1/1 + approve preserves mapping")
        print("OK employee migration foundation P3 name-identity guard smoke")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]


if __name__ == "__main__":
    main()
