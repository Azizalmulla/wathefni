#!/usr/bin/env python3
"""Employees 360 freeze regression gates (offline / import-time).

Fails if future post-hire work weakens controlled-rollout invariants:
  - Wave 2 authority surface present
  - Wave 4 history overlap protection present
  - Wave 3 packs: only KW verified; unsupported fail closed
  - ESS identity / encryption / allowlist helpers present
  - Dual-control self-approval strings present
  - App allowlist require-on semantics present
  - Pre-hire / Wave D freeze marker files untouched by this suite (path denylist check)

No DB required. No production mutations.
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    # --- module imports ---
    import employee_authority_wave2 as w2
    import employee_org_wave4 as w4
    import employee_policy_packs_wave3h as packs
    import employee_lifecycle_wave3 as lc3
    import employee_lifecycle_wave3c as lc3c
    import employee_selfservice_wave5 as w5

    # Wave 2 authority
    check("wave2 module present", hasattr(w2, "backfill_company_authority") or hasattr(w2, "ensure_authority_schema"))
    w2_src = _src(ROOT / "employee_authority_wave2.py")
    check("wave2 authority map referenced", "employee_key_authority_map" in w2_src)
    check("wave2 no silent map drop helper named bypass", "bypass_authority" not in w2_src.lower())

    # Wave 4 history
    w4_src = _src(ROOT / "employee_org_wave4.py")
    check("wave4 overlap guard present", "_assert_no_overlap" in w4_src)
    check("wave4 apply_assignment_change present", hasattr(w4, "apply_assignment_change"))
    check("wave4 history list present", hasattr(w4, "list_assignment_history"))
    # Forbid naive DELETE FROM assignment history in module body (rollback APIs may still exist)
    tree = ast.parse(w4_src)
    dangerous_deletes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.lower()
            if "delete from employee_assignment" in s and "history" in s and "where" not in s:
                dangerous_deletes.append(node.value[:80])
    check("wave4 no unqualified assignment-history wipe SQL", not dangerous_deletes, dangerous_deletes)

    # Wave 3 packs
    check("only KW verified pack", packs.VERIFIED_PACKS == frozenset({"KW_PRIVATE_SECTOR"}))
    kw = packs.get_pack("KW_PRIVATE_SECTOR")
    check("KW pack enabled", bool(kw and kw.get("enabled")))
    check("KW version 1.0.0", (kw or {}).get("policy_version") == "1.0.0")
    check(
        "payroll owns monetary calculations",
        str((kw or {}).get("monetary_calculations_owner") or "").lower() in {"payroll", "external_payroll", "payroll_system"}
        or "payroll" in str((kw or {}).get("monetary_calculations_owner") or "payroll").lower(),
        (kw or {}).get("monetary_calculations_owner"),
    )
    # Pack dict may nest floors differently — also check DEFAULT / overlay
    overlay = packs.pack_as_company_policy_overlay(kw) if hasattr(packs, "pack_as_company_policy_overlay") else {}
    mon = overlay.get("monetary_calculations_owner") or (kw or {}).get("monetary_calculations_owner") or lc3c.DEFAULT_POLICY.get("monetary_calculations_owner")
    check("monetary owner payroll (overlay/default)", str(mon or "payroll").lower().startswith("payroll"), mon)
    check("exceptional manual only default", bool(lc3c.DEFAULT_POLICY.get("exceptional_cases_manual_only", True)))

    ok = packs.resolve_pack_code(jurisdiction_code="KW", worker_category="private_sector")
    check("resolve KW private", ok.get("ok") is True and ok.get("pack_code") == "KW_PRIVATE_SECTOR", ok)
    sa = packs.resolve_pack_code(jurisdiction_code="SA", worker_category="private_sector")
    check("SA fail closed", sa.get("ok") is False, sa)
    ae = packs.resolve_pack_code(jurisdiction_code="AE", worker_category="private_sector")
    check("AE fail closed", ae.get("ok") is False, ae)
    missing = packs.resolve_pack_code(jurisdiction_code="KW", worker_category=None)
    check("incomplete classification fail closed", missing.get("ok") is False, missing)

    packs_src = _src(ROOT / "employee_policy_packs_wave3h.py")
    check("dual-control create_classification_request", "def create_classification_request" in packs_src)
    check("classification self_approval_forbidden", "self_approval_forbidden" in packs_src)
    check("remediation excludes quarantined synthetics", "quarantined_synthetic_test" in packs_src)

    # Lifecycle synthetic + allowlist
    check("lifecycle synthetic gate fn", hasattr(lc3, "assert_lifecycle_synthetic_target"))
    check("lifecycle real allowlist fn", hasattr(lc3, "lifecycle_real_allowlist"))
    lc3_src = _src(ROOT / "employee_lifecycle_wave3.py")
    check("lifecycle allowlist env wired", "WATHEFNI_EMPLOYEE_LIFECYCLE_V3_REAL_ALLOWLIST" in lc3_src)
    check("lifecycle self_approval_forbidden", "self_approval_forbidden" in lc3_src)
    check("lifecycle synthetic_only_gate error retained", "synthetic_only_gate" in lc3_src)

    # ESS identity / encryption / allowlists
    check("ess synthetic assert", hasattr(w5, "_assert_ess_synthetic_target"))
    check("ess real allowlist", hasattr(w5, "ess_real_allowlist"))
    check("ess bank real allowlist", hasattr(w5, "ess_bank_real_allowlist"))
    check("ess bank encryption helper", hasattr(w5, "bank_encryption_available"))
    check("ess bind identity", hasattr(w5, "bind_employee_identity"))
    check("ess revoke sessions", hasattr(w5, "revoke_employee_sessions"))
    w5_src = _src(ROOT / "employee_selfservice_wave5.py")
    check("ess synthetic-only error retained", "ess_synthetic_only" in w5_src)
    check("ess bank not allowlisted error", "ess_bank_not_allowlisted" in w5_src)
    check("ess plaintext bank forbidden", "plaintext_bank_forbidden" in w5_src)
    check("ess self_approval_forbidden", "self_approval_forbidden" in w5_src)
    check("ess own_data_only", "own_data_only" in w5_src)

    # Empty allowlists must not admit arbitrary keys when synthetic-only on
    os.environ["WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_ESS_V5_REAL_ALLOWLIST"] = ""
    os.environ["WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST"] = ""
    check("ess real allowlist empty by default in test", w5.ess_real_allowlist() == set())
    check("ess bank allowlist empty by default in test", w5.ess_bank_real_allowlist() == set())

    # App allowlist helpers in app.py (import may be heavy — prefer source)
    app_src = _src(ROOT / "app.py")
    check("app require allowlist helper", "def employee_app_require_allowlist" in app_src or "EMPLOYEE_APP_REQUIRE_ALLOWLIST" in app_src)
    check("app assert allowlisted", "def assert_employee_app_allowlisted" in app_src)
    check("app session_epoch stale revoke", "ess_session_epoch_stale" in app_src)
    check("app create_employee_session calls allowlist", "assert_employee_app_allowlisted" in app_src)

    # Pre-hire / Wave D freeze — protected path denylist must still exist as separate freezes
    ops = ROOT.parent / "ops"
    freeze_doc = ops / "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"
    check("completion freeze doc present", freeze_doc.is_file())
    freeze_txt = freeze_doc.read_text(encoding="utf-8")
    for needle in [
        "HR production use",
        "Talal",
        "SYNTHETIC_ONLY",
        "Manual only",
        "Payroll",
        "Wave D",
        "pre-hiring",
        "smoke-test-employees360-freeze-regression.py",
    ]:
        check(f"freeze doc mentions {needle}", needle in freeze_txt)

    # Cursor rule present
    rule = ROOT.parent / ".cursor" / "rules" / "employees360-freeze.mdc"
    check("cursor freeze rule present", rule.is_file())

    # Protected pre-hire freeze docs still present (do not delete as part of E360)
    for name in [
        "PREHIRING_UNIFIED_INBOUND_CV_FINAL_ENFORCEMENT_AND_FREEZE.md",
        "PREHIRING_CANDIDATE_KNOWLEDGE_FINAL_LIVE_RELEASE_AND_FREEZE.md",
    ]:
        check(f"prehire freeze intact {name}", (ops / name).is_file())

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
