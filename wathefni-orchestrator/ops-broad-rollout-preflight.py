#!/usr/bin/env python3
"""Preflight + Aziz synthetic bank cleanup + Talal 403 + cohort inventory.

Clears Aziz's walkthrough synthetic payroll-effective bank through audited
supersede + profile soft-delete. Does NOT invent replacement bank values —
Aziz must submit real details via Bank ESS after cleanup.

Writes JSON evidence to OUT_PATH.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

for line in Path("/tmp/orch-environ.env").read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k, v)

import app as A  # noqa: E402
import employee_bank_ess as B  # noqa: E402
import onboarding_completion_contract as C  # noqa: E402
import onboarding_lifecycle_wave2a as LC  # noqa: E402

COMPANY = "WATHEFNI"
AZIZ = "WATHEFNI-96599338566"
TALAL = "WATHEFNI-96550252254"
OUT = Path(os.environ.get("OUT_PATH") or "/tmp/broad-preflight.json")
RESULTS: dict[str, Any] = {"checks": [], "failed": 0}


def check(name: str, ok: bool, detail: Any = None) -> bool:
    RESULTS["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        RESULTS["failed"] += 1
    print(("PASS" if ok else "FAIL"), name, "::", json.dumps(detail, default=str)[:400])
    return bool(ok)


def mint(key: str) -> str:
    emp = A.find_employee_by_key(key, company_code=COMPANY)
    return str(A.create_employee_session(COMPANY, key, str(emp.get("phone")))["token"])


def http(method: str, path: str, *, token: str | None = None, hr_token: str | None = None):
    import urllib.error
    import urllib.request

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if hr_token:
        headers["X-Dashboard-Session"] = hr_token
    req = urllib.request.Request(
        f"http://127.0.0.1:8010{path}",
        method=method,
        headers=headers,
        data=None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        return e.code, detail


def clear_aziz_synthetic_bank() -> dict[str, Any]:
    """Audited removal of walkthrough synthetic payroll bank. No invented values."""
    out: dict[str, Any] = {"actions": []}
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            B.ensure_bank_ess_schema(cur)
            before = B.current_effective(cur, company_code=COMPANY, employee_key=AZIZ)
            out["before_effective"] = before
            if before:
                display = before.get("display") or {}
                is_synth = (
                    str(display.get("iban_last4") or "") == "0000"
                    or "Walkthrough" in str(display.get("account_holder") or "")
                    or "Walkthrough" in str(display.get("bank_name") or "")
                    or str(display.get("bank_name") or "") in {"Hsbshshsh"}
                )
                out["classified_synthetic"] = is_synth
                if not is_synth:
                    out["skipped"] = "live effective does not look synthetic"
                    conn.commit()
                    return out
                cur.execute(
                    """
                    UPDATE employee_bank_effective
                    SET superseded_at=now()
                    WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
                    RETURNING request_id::text, fingerprint
                    """,
                    (COMPANY, AZIZ),
                )
                superseded = [dict(r) for r in cur.fetchall() or []]
                out["actions"].append({"supersede_effective": superseded})
                # Soft-delete the ESS bank profile so it cannot be re-read as truth.
                cur.execute(
                    """
                    UPDATE employee_ess_bank_profiles
                    SET deleted_at=now(),
                        deletion_reason=%s
                    WHERE company_code=%s AND employee_key=%s AND deleted_at IS NULL
                    RETURNING version, bank_fingerprint
                    """,
                    (
                        "walkthrough_synthetic_cleared_pre_broad_rollout",
                        COMPANY,
                        AZIZ,
                    ),
                )
                profiles = [dict(r) for r in cur.fetchall() or []]
                out["actions"].append({"soft_delete_profile": profiles})
            # Re-open bank_details for employee action; do not invent a bank.
            cur.execute(
                """
                SELECT item_id, status, required, owner, authority, category,
                       collection_mode, lifecycle_meta, rejection_reason
                FROM onboarding_items
                WHERE employee_key=%s AND item_id='bank_details'
                """,
                (AZIZ,),
            )
            item = dict(cur.fetchone() or {})
            if item:
                LC.set_item_lifecycle(
                    cur,
                    employee_key=AZIZ,
                    item_id="bank_details",
                    new_status="pending",
                    clear_rejection=True,
                    meta_patch={
                        "source": "broad_rollout_preflight",
                        "phase": "pending",
                        "cleared_fingerprint": (before or {}).get("fingerprint"),
                        "reason": "walkthrough_synthetic_bank_cleared",
                    },
                )
                LC.sync_completion_contract(
                    cur, employee_key=AZIZ, actor="broad_rollout_preflight"
                )
                out["actions"].append({"bank_item_reset": "pending"})
            # Reconcile must leave the item open (no effective, profile deleted).
            recon = B.reconcile_onboarding_bank_item(
                cur, company_code=COMPANY, employee_key=AZIZ
            )
            out["reconcile"] = recon
            after = B.current_effective(cur, company_code=COMPANY, employee_key=AZIZ)
            out["after_effective"] = after
            cur.execute(
                """
                SELECT status, rejection_reason FROM onboarding_items
                WHERE employee_key=%s AND item_id='bank_details'
                """,
                (AZIZ,),
            )
            out["after_item"] = dict(cur.fetchone() or {})
        conn.commit()
    return out


def real_employee_cohort() -> list[dict[str, Any]]:
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key, name, employment_status, onboarding_status, phone
                FROM employees
                WHERE company_code=%s
                  AND employee_key LIKE 'WATHEFNI-965%%'
                  AND employee_key NOT LIKE '%%SHW%%'
                  AND employee_key NOT LIKE '%%5497%%'
                  AND employee_key NOT LIKE '%%REALBLOCK%%'
                  AND employee_key NOT LIKE '%%TERM%%'
                  AND coalesce(employment_status,'') NOT IN ('terminated','deleted','inactive')
                ORDER BY name NULLS LAST
                """,
                (COMPANY,),
            )
            rows = [dict(r) for r in cur.fetchall() or []]
        conn.commit()
    return rows


def main() -> int:
    RESULTS["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # --- rollback artifact presence (local to VPS) ---
    stamp = "20260806T200247Z"
    paths = {
        "backend_app": f"/opt/wathefni/backups/onboarding-next-item-{stamp}/app.py",
        "backend_contract": f"/opt/wathefni/backups/onboarding-next-item-{stamp}/onboarding_completion_contract.py",
        "dashboard": f"/opt/wathefni/backups/dashboard-onboarding-ux-{stamp}",
        "reconcile_api": f"/opt/wathefni/backups/onboarding-completion-reconcile-{stamp}",
    }
    present = {k: Path(v).exists() for k, v in paths.items()}
    check("rollback artifacts present on VPS", all(present.values()), present)
    # Usability: backup files are non-empty and parseable.
    usable = {}
    for k, p in paths.items():
        path = Path(p)
        if path.is_file():
            usable[k] = path.stat().st_size > 1000
        elif path.is_dir():
            usable[k] = (
                any(path.rglob("*.js"))
                or any(path.rglob("*.html"))
                or any(path.rglob("*.py"))
            )
        else:
            usable[k] = False
    check("rollback artifacts non-empty / usable", all(usable.values()), usable)

    # --- Aziz cleanup ---
    cleanup = clear_aziz_synthetic_bank()
    RESULTS["aziz_cleanup"] = cleanup
    check(
        "Aziz synthetic effective bank cleared",
        cleanup.get("after_effective") is None
        and (
            bool(cleanup.get("classified_synthetic"))
            or cleanup.get("before_effective") is None
            or bool(cleanup.get("skipped"))
        ),
        {
            "before": bool(cleanup.get("before_effective")),
            "after": cleanup.get("after_effective"),
            "item": cleanup.get("after_item"),
            "already_clear": cleanup.get("before_effective") is None,
        },
    )
    check(
        "Aziz bank_details is open for real submission",
        str((cleanup.get("after_item") or {}).get("status") or "")
        in {"pending", "in_progress", "replacement_required"},
        cleanup.get("after_item"),
    )

    # --- Talal negative control ---
    talal_token = mint(TALAL)
    code, me = http("GET", "/app/me", token=talal_token)
    features = (me.get("features") or {}) if isinstance(me, dict) else {}
    bank_feat = features.get("bank") if isinstance(features, dict) else None
    code_b, bank = http("GET", "/app/bank", token=talal_token)
    code_o, onb = http("GET", "/app/onboarding", token=talal_token)
    open_bank = False
    if isinstance(onb, dict):
        for g in ("your_actions", "being_reviewed", "handled_by_others", "completed"):
            for item in onb.get(g) or []:
                if item.get("item_id") == "bank_details":
                    acts = item.get("actions") or []
                    open_bank = "open_bank" in acts
    check(
        "Talal /app/bank returns 403",
        code_b == 403,
        {"http": code_b, "detail": bank if code_b >= 400 else None},
    )
    check(
        "Talal has no open_bank action",
        open_bank is False,
        {"open_bank": open_bank, "bank_feature": bank_feat},
    )
    err = ""
    if isinstance(bank, dict):
        err = str(((bank.get("detail") or bank).get("error") if isinstance(bank.get("detail") or bank, dict) else "") or "")
        if not err and isinstance(bank.get("detail"), dict):
            err = str(bank["detail"].get("error") or "")
    check(
        "Talal 403 is eligibility denial (not a crash)",
        code_b == 403 and err in {"bank_ess_not_allowlisted", "ess_bank_not_allowlisted", "bank_ess_disabled"},
        {"error": err},
    )

    # --- Cohort inventory for gradual expansion ---
    cohort = real_employee_cohort()
    RESULTS["real_employees"] = cohort
    RESULTS["proposed_wave1_keys"] = [
        r["employee_key"]
        for r in cohort
        if r["employee_key"] not in {TALAL}  # Talal stays negative control
    ]
    check(
        "cohort inventory has real employees beyond canary",
        len(RESULTS["proposed_wave1_keys"]) >= 2,
        {"count": len(RESULTS["proposed_wave1_keys"]), "keys": RESULTS["proposed_wave1_keys"]},
    )

    # --- Aziz still eligible for bank after cleanup ---
    aziz_token = mint(AZIZ)
    code_ab, abody = http("GET", "/app/bank", token=aziz_token)
    check("Aziz /app/bank still reachable after cleanup", code_ab == 200, {"http": code_ab})

    OUT.write_text(json.dumps(RESULTS, indent=2, default=str))
    print("PREFLIGHT_OK" if RESULTS["failed"] == 0 else "PREFLIGHT_FAILED")
    print("wrote", OUT)
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
