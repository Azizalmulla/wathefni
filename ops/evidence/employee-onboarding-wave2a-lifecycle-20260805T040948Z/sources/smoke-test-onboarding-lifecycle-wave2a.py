#!/usr/bin/env python3
"""Local smoke for Onboarding Wave 2A lifecycle foundation."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import onboarding_lifecycle_wave2a as lc


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise SystemExit(f"FAIL {name}: {detail}")
    print(f"PASS {name}")


def main() -> None:
    check("received maps to processing", lc.normalize_status("received") == lc.STATE_PROCESSING)
    check("accepted complete", lc.is_lifecycle_complete("accepted"))
    check("processing not complete", not lc.is_lifecycle_complete("processing"))
    check("replacement not complete", not lc.is_lifecycle_complete("replacement_required"))

    bank = {
        "item_id": "bank_details",
        "status": "pending",
        "owner": "employee",
        "authority": "ess",
        "collection_mode": "ess_encrypted",
        "required": True,
    }
    check("bank responsible employee", lc.responsible_party(bank) == "employee")
    check("bank no upload action", "upload" not in lc.actions_for_item(bank, can_upload=True, lifecycle_on=True))

    doc = {
        "item_id": "civil_id",
        "status": "pending",
        "owner": "employee",
        "authority": "onboarding",
        "collection_mode": "document",
        "document_type": "civil_id",
        "item_type": "document",
        "required": True,
    }
    check("doc upload action", "upload" in lc.actions_for_item(doc, can_upload=True, lifecycle_on=True))

    processing = {**doc, "status": "processing", "file_id": "abc"}
    acts = lc.actions_for_item(processing, can_upload=True, lifecycle_on=True)
    check("processing has preview", "preview" in acts)
    check("processing no upload", "upload" not in acts and "replace" not in acts)
    check("processing group reviewed", lc.group_key_for_item(processing) == "being_reviewed")

    rejected = {**doc, "status": "replacement_required", "file_id": "abc", "rejection_reason": "Blurry"}
    acts2 = lc.actions_for_item(rejected, can_upload=True, lifecycle_on=True)
    check("replacement has resubmit", "resubmit" in acts2 or "replace" in acts2)
    check("replacement your actions", lc.group_key_for_item(rejected) == "your_actions")

    hr = {
        "item_id": "department_assigned",
        "status": "pending",
        "owner": "hr",
        "authority": "onboarding",
        "collection_mode": "none",
        "required": False,
    }
    check("hr item not employee visible", not lc._employee_visible(hr))

    os.environ["WATHEFNI_ONBOARDING_LIFECYCLE_V2A"] = "on"
    os.environ["WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST"] = "WATHEFNI-96599338566"
    check("flag on for aziz", lc.lifecycle_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-96599338566"))
    check(
        "flag off for unknown",
        not lc.lifecycle_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-OTHER"),
    )
    print("OK wave2a local smoke")


if __name__ == "__main__":
    main()
