#!/usr/bin/env python3
"""Clear Aziz synthetic bank so /app/bank returns empty/pending — not verified.

Root cause of the physical-app ghost record:
  prior cleanup superseded employee_bank_effective and soft-deleted the ESS
  profile, but left employee_bank_verified intact. employee_bank_status sets
  has_verified_bank from verified OR effective, and also resurfaced the latest
  applied request as submission_state=approved.

This script:
  1. Revokes all non-revoked verified rows for Aziz (audit retained)
  2. Confirms no live effective row / profile is soft-deleted
  3. Resets onboarding bank_details to pending if needed
  4. Proves GET /app/bank is empty for a new submission
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
for line in Path("/tmp/orch-environ.env").read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ[k] = v

import app as A  # noqa: E402
import employee_bank_ess as B  # noqa: E402
import onboarding_lifecycle_wave2a as LC  # noqa: E402

COMPANY = "WATHEFNI"
AZIZ = "WATHEFNI-96599338566"
OUT = Path(os.environ.get("OUT_PATH") or "/tmp/aziz-bank-synthetic-clear.json")
REASON = "walkthrough_synthetic_revoked_not_current"
RESULTS: dict[str, Any] = {"checks": [], "failed": 0, "actions": []}


def check(name: str, ok: bool, detail: Any = None) -> bool:
    RESULTS["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        RESULTS["failed"] += 1
    print(("PASS" if ok else "FAIL"), name, "::", json.dumps(detail, default=str)[:500])
    return bool(ok)


def is_synthetic_display(display: Any) -> bool:
    d = display if isinstance(display, dict) else {}
    holder = str(d.get("account_holder") or "")
    bank = str(d.get("bank_name") or "")
    last4 = str(d.get("iban_last4") or "")
    return (
        last4 == "0000"
        or "Walkthrough" in holder
        or "Walkthrough" in bank
        or bank in {"Hsbshshsh"}
        or holder in {"Snsnbsbsu", "Aziz Walkthrough", "Aziz Walkthrough Corrected"}
    )


def http_bank(token: str) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        "http://127.0.0.1:8010/app/bank",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


def main() -> int:
    emp = A.find_employee_by_key(AZIZ, company_code=COMPANY)
    token = str(A.create_employee_session(COMPANY, AZIZ, str(emp.get("phone")))["token"])

    before_code, before = http_bank(token)
    RESULTS["before"] = {"http": before_code, "body": before}
    check(
        "before: API response captured",
        before_code == 200,
        {
            "has_verified_bank": before.get("has_verified_bank"),
            "verified_bank": ((before.get("verified") or {}).get("display") or {}).get("bank_name"),
            "submission_state": before.get("submission_state"),
            "payroll_effective": before.get("payroll_effective"),
        },
    )

    with A.db_connect() as conn:
        with conn.cursor() as cur:
            B.ensure_bank_ess_schema(cur)
            cur.execute(
                """
                SELECT request_id::text, fingerprint, display, revoked_at
                FROM employee_bank_verified
                WHERE company_code=%s AND employee_key=%s
                ORDER BY verified_at DESC
                """,
                (COMPANY, AZIZ),
            )
            verified_rows = [dict(r) for r in cur.fetchall() or []]
            synthetic_ids = [
                r["request_id"]
                for r in verified_rows
                if r.get("revoked_at") is None and is_synthetic_display(r.get("display"))
            ]
            revoked = B.revoke_verified(
                cur,
                company_code=COMPANY,
                employee_key=AZIZ,
                reason=REASON,
                request_ids=synthetic_ids or None,
            )
            RESULTS["actions"].append({"revoke_verified": revoked, "targeted_ids": synthetic_ids})

            # Ensure no live effective remains.
            cur.execute(
                """
                UPDATE employee_bank_effective
                SET superseded_at=now()
                WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
                RETURNING request_id::text
                """,
                (COMPANY, AZIZ),
            )
            RESULTS["actions"].append(
                {"supersede_any_live_effective": [dict(r) for r in cur.fetchall() or []]}
            )

            # Ensure profile stays soft-deleted.
            cur.execute(
                """
                UPDATE employee_ess_bank_profiles
                SET deleted_at=COALESCE(deleted_at, now()),
                    deletion_reason=COALESCE(deletion_reason, %s)
                WHERE company_code=%s AND employee_key=%s AND deleted_at IS NULL
                RETURNING version
                """,
                (REASON, COMPANY, AZIZ),
            )
            RESULTS["actions"].append(
                {"ensure_profile_deleted": [dict(r) for r in cur.fetchall() or []]}
            )

            cur.execute(
                """
                SELECT status FROM onboarding_items
                WHERE employee_key=%s AND item_id='bank_details'
                """,
                (AZIZ,),
            )
            item = dict(cur.fetchone() or {})
            if str(item.get("status") or "") in {
                "accepted",
                "complete",
                "completed",
                "verified",
                "waived",
            }:
                LC.set_item_lifecycle(
                    cur,
                    employee_key=AZIZ,
                    item_id="bank_details",
                    new_status="pending",
                    clear_rejection=True,
                    meta_patch={
                        "source": "synthetic_bank_clear",
                        "phase": "pending",
                        "reason": REASON,
                    },
                )
                LC.sync_completion_contract(cur, employee_key=AZIZ, actor="synthetic_bank_clear")
                RESULTS["actions"].append({"bank_item_reset": "pending"})
            else:
                RESULTS["actions"].append({"bank_item_status": item.get("status")})

            B.reconcile_onboarding_bank_item(
                cur, company_code=COMPANY, employee_key=AZIZ
            )
            cur.execute(
                """
                SELECT status FROM onboarding_items
                WHERE employee_key=%s AND item_id='bank_details'
                """,
                (AZIZ,),
            )
            RESULTS["after_item"] = dict(cur.fetchone() or {})
        conn.commit()

    after_code, after = http_bank(token)
    RESULTS["after"] = {"http": after_code, "body": after}

    check("after: /app/bank HTTP 200", after_code == 200, {"http": after_code})
    check(
        "after: has_verified_bank is false",
        after.get("has_verified_bank") is False,
        {"has_verified_bank": after.get("has_verified_bank")},
    )
    check("after: verified block is null", after.get("verified") is None, after.get("verified"))
    check(
        "after: payroll_effective is null",
        after.get("payroll_effective") is None,
        after.get("payroll_effective"),
    )
    check(
        "after: submission_state is none (no synthetic history projected)",
        after.get("submission_state") in {None, "none", ""}
        and after.get("submission") is None,
        {"submission_state": after.get("submission_state"), "submission": after.get("submission")},
    )
    check(
        "after: can submit new bank details",
        after.get("can_submit_new") is True,
        {"can_submit_new": after.get("can_submit_new"), "next_step": after.get("next_step")},
    )
    check(
        "after: next step asks employee to add bank details",
        "Add your bank" in str((after.get("next_step") or {}).get("message_en") or ""),
        after.get("next_step"),
    )
    check(
        "after: no Walkthrough / 0000 values anywhere in response",
        "Walkthrough" not in json.dumps(after, default=str)
        and '"iban_last4": "0000"' not in json.dumps(after, default=str)
        and "Hsbshshsh" not in json.dumps(after, default=str),
        {
            "has_walkthrough": "Walkthrough" in json.dumps(after, default=str),
            "has_0000": "0000" in json.dumps(after, default=str),
        },
    )
    # Audit preserved
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS c FROM employee_bank_verified
                WHERE company_code=%s AND employee_key=%s AND revoked_at IS NOT NULL
                """,
                (COMPANY, AZIZ),
            )
            revoked_n = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*) AS c FROM employee_bank_effective
                WHERE company_code=%s AND employee_key=%s
                """,
                (COMPANY, AZIZ),
            )
            effective_hist = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*) AS c FROM employee_ess_requests
                WHERE company_code=%s AND employee_key=%s AND request_type='bank_detail_change'
                """,
                (COMPANY, AZIZ),
            )
            req_n = int(cur.fetchone()["c"])
        conn.commit()
    check(
        "audit history retained (revoked verified + effective + requests)",
        revoked_n >= 1 and effective_hist >= 1 and req_n >= 1,
        {"revoked_verified": revoked_n, "effective_rows": effective_hist, "requests": req_n},
    )

    OUT.write_text(json.dumps(RESULTS, indent=2, default=str))
    print("CLEAR_OK" if RESULTS["failed"] == 0 else "CLEAR_FAILED")
    print("wrote", OUT)
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
