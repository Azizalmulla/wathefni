#!/usr/bin/env python3
"""Onboarding freeze regression gates (offline / import-time).

Fails if future post-hire work weakens controlled-rollout invariants:
  - load_onboarding_items is sole read authority; no candidates.read in loader
  - tenant join + bank mask / plaintext bank forbidden
  - HR_MUTATE company allowlist + SEED default-off helpers
  - optimistic concurrency + audit on mark path
  - default_kuwait@2.0.0 pin + FOUR_REALS markers
  - cancel/reschedule history preserved markers
  - manager/tenant scope wiring in list/detail
  - freeze docs + Cursor rule + sibling E360/prehire freezes present

No DB required. No production mutations.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
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


def _loader_chunk(app_src: str) -> str:
    start = app_src.find("def load_onboarding_items")
    if start < 0:
        return ""
    end = app_src.find("\ndef ", start + 1)
    return app_src[start:end if end > start else start + 4000]


def main() -> int:
    import onboarding_wave2 as w2

    app_src = _src(ROOT / "app.py")
    w2_src = _src(ROOT / "onboarding_wave2.py")
    ar_src = _src(ROOT / "action_registry.py")
    loader = _loader_chunk(app_src)

    # --- read authority / no recruiter bleed ---
    check("load_onboarding_items exists", "def load_onboarding_items" in app_src)
    check("loader joins employees", "JOIN employees" in loader)
    check("loader has no candidates.read", "candidates.read" not in loader)
    check("employee_onboarding_items wraps load", "def employee_onboarding_items" in app_src)
    # Ensure wrapper does not reintroduce recruiter entitlement in its short body
    wrap_start = app_src.find("def employee_onboarding_items")
    wrap = app_src[wrap_start : wrap_start + 800] if wrap_start >= 0 else ""
    check("wrapper has no candidates.read", "candidates.read" not in wrap)

    # --- bank plaintext ---
    check("plaintext bank helper", "def onboarding_plaintext_bank_forbidden" in app_src)
    check("receipt rejects bank_details", "bank_via_ess_required" in app_src)
    check("mask_onboarding_item_for_read", "def mask_onboarding_item_for_read" in app_src)
    check("wave2 bank ess authority", 'authority="ess"' in w2_src or "authority='ess'" in w2_src or 'authority="ess"' in w2_src.replace("'", '"'))
    bank = w2.get_template_item("bank_details")
    check(
        "canonical bank ESS encrypted",
        bank is not None
        and str(getattr(bank, "authority", "") or "").lower() == "ess"
        and str(getattr(bank, "collection_mode", "") or "") == "ess_encrypted",
        bank,
    )

    # --- flags / company gate ---
    check("SEED helper", "def onboarding_seed_enabled" in app_src)
    check("HR_MUTATE helper", "def onboarding_hr_mutate_enabled" in app_src)
    check("HR_MUTATE companies helper", "def onboarding_hr_mutate_companies" in app_src)
    check("HR_MUTATE company gate", "def onboarding_hr_mutate_enabled_for_company" in app_src)
    check("mutate allowed_for helper", "def onboarding_hr_mutate_allowed_for" in app_src)
    # Defaults: unset / off → False (process-local)
    saved_seed = os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
    saved_mut = os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
    saved_co = os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES", None)
    try:
        import app as app_mod

        # Helpers read os.environ live — with vars unset they must be off / empty
        check("SEED defaults off when unset", app_mod.onboarding_seed_enabled() is False)
        check("HR_MUTATE defaults off when unset", app_mod.onboarding_hr_mutate_enabled() is False)
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "on"
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES"] = "WATHEFNI"
        check("company allowlist WATHEFNI", app_mod.onboarding_hr_mutate_enabled_for_company("WATHEFNI") is True)
        check("company allowlist OTHERCO denied", app_mod.onboarding_hr_mutate_enabled_for_company("OTHERCO") is False)
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
        check("SEED stays off for 'off'", app_mod.onboarding_seed_enabled() is False)
    finally:
        for key, val in (
            ("WATHEFNI_ONBOARDING_SEED", saved_seed),
            ("WATHEFNI_ONBOARDING_HR_MUTATE", saved_mut),
            ("WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES", saved_co),
        ):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    # --- template pin ---
    check("canonical template id", w2.CANONICAL_TEMPLATE_ID == "default_kuwait")
    check("canonical version 2.0.0", w2.CANONICAL_TEMPLATE_VERSION == "2.0.0")
    check("FOUR_REALS defined", len(getattr(w2, "FOUR_REALS", ())) == 4)
    check("is_four_real_employee helper", hasattr(w2, "is_four_real_employee"))
    check("migration plan read-only marker", "Does not apply" in (w2.plan_legacy_migration.__doc__ or "") or "read-only" in (w2.plan_legacy_migration.__doc__ or "").lower())

    # --- concurrency + audit ---
    check("mark_item_wave2 expected_row_version", "expected_row_version" in w2_src)
    check("stale_item_version error", "stale_item_version" in w2_src)
    check("record_onboarding_audit", "def record_onboarding_audit" in w2_src)
    check("mark_onboarding_item uses expected_row_version", "expected_row_version" in app_src)
    check("cancel history preserved", "history_preserved" in w2_src)
    check("cancel_onboarding registered", '"cancel_onboarding"' in ar_src or "name=\"cancel_onboarding\"" in ar_src or "cancel_onboarding" in ar_src)
    check("reschedule_onboarding registered", "reschedule_onboarding" in ar_src)

    # --- tenant / manager scope ---
    check("list_onboarding_page exists", "def list_onboarding_page" in app_src)
    list_start = app_src.find("def list_onboarding_page")
    list_chunk = app_src[list_start : list_start + 3500] if list_start >= 0 else ""
    check("list uses _employee_scope_where", "_employee_scope_where" in list_chunk)
    detail_start = app_src.find("def dashboard_posthire_onboarding_detail")
    detail_chunk = app_src[detail_start : detail_start + 2500] if detail_start >= 0 else ""
    check("detail uses context_manager_allows_employee", "context_manager_allows_employee" in detail_chunk)
    check("mark checks manager_scope_allows_employee", "manager_scope_allows_employee" in app_src)

    # --- retired_legacy excluded from counts ---
    check("retired_legacy recognized", "retired_legacy" in app_src)

    # --- freeze docs + cursor rule ---
    ops = REPO / "ops"
    freeze_doc = ops / "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"
    check("onboarding freeze doc present", freeze_doc.is_file())
    freeze_txt = freeze_doc.read_text(encoding="utf-8") if freeze_doc.is_file() else ""
    for needle in [
        "HR production use",
        "scoped GO",
        "Talal",
        "disabled",
        "default_kuwait@2.0.0",
        "ESS-owned",
        "ONBOARDING_SEED",
        "smoke-test-onboarding-freeze-regression.py",
        "Attendance",
        "Employees 360",
        "Wave D",
    ]:
        check(f"freeze doc mentions {needle}", needle in freeze_txt)

    rule = REPO / ".cursor" / "rules" / "onboarding-freeze.mdc"
    check("cursor onboarding freeze rule present", rule.is_file())

    # Sibling freezes must remain
    check(
        "E360 freeze intact",
        (ops / "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md").is_file(),
    )
    for name in [
        "PREHIRING_UNIFIED_INBOUND_CV_FINAL_ENFORCEMENT_AND_FREEZE.md",
        "PREHIRING_CANDIDATE_KNOWLEDGE_FINAL_LIVE_RELEASE_AND_FREEZE.md",
    ]:
        check(f"prehire freeze intact {name}", (ops / name).is_file())

    # Forbid silent unqualified DELETE FROM onboarding_items in wave2 (ast string scan)
    tree = ast.parse(w2_src)
    dangerous = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.lower()
            if "delete from onboarding_items" in s and "where" not in s:
                dangerous.append(node.value[:80])
    check("wave2 no unqualified onboarding_items wipe SQL", not dangerous, dangerous)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
