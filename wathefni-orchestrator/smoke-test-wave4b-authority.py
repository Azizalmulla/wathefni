#!/usr/bin/env python3
"""Wave 4B backend authority closure — local source/unit proofs. No production writes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

PASS = FAIL = 0


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    import attendance_authority_wave1 as auth
    import candidate_ranking
    import jobs_permission_expand as jobs_perms
    import ranking_result_presentation as rrp
    import workspace_capability as wc

    expanded = jobs_perms.expand_effective_jobs_permissions({"settings.manage"})
    check("settings.manage expands jobs mutations", jobs_perms.SETTINGS_MANAGE_COMPAT_JOBS <= expanded)
    check("settings.manage does not expand jobs.read", "jobs.read" not in expanded)
    check(
        "prehire.read expands jobs.read only",
        jobs_perms.expand_effective_jobs_permissions({"prehire.read"}) == {"prehire.read", "jobs.read"},
    )
    check("empty permissions stay empty", jobs_perms.expand_effective_jobs_permissions([]) == set())
    check("employees.read is not inferred from settings.manage", "employees.read" not in expanded)

    check(
        "action inbox empty perms fail closed",
        wc.action_inbox_has_entitled_source({"leave"}, set()) is False,
    )
    check(
        "action inbox settings.manage is not a directory substitute",
        wc.action_inbox_has_entitled_source({"leave"}, {"settings.manage", "users.manage"}) is False,
    )
    check(
        "action inbox employees.read entitles people compose",
        wc.action_inbox_has_entitled_source({"leave"}, {"employees.read"}) is True,
    )
    check(
        "action inbox wildcard entitles people compose",
        wc.action_inbox_has_entitled_source({"leave"}, {"*:*"}) is True,
    )

    emp = next(s for s in wc.WORKSPACE_SURFACES if s["id"] == "nav.employees")
    check(
        "employees nav denied without employees.read",
        wc.resolve_surface(emp, {"leave"}, {"settings.manage", "users.manage"}).get("offerable") is False,
    )
    check(
        "employees nav allowed with employees.read",
        wc.resolve_surface(emp, {"leave"}, {"employees.read"}).get("offerable") is True,
    )
    check(
        "employees nav allowed with *:*",
        wc.resolve_surface(emp, {"leave"}, {"*:*"}).get("offerable") is True,
    )
    leave_nav = set(wc.resolve_workspace_authority(["leave"], "owner")["nav_ids"])
    check("owner leave-only still includes employees via fixture grant", "employees" in leave_nav)

    approved = {
        "status": "completed",
        "late_minutes": 0,
        "early_leave_minutes": 0,
        "exception_state": "none",
        "approval_status": "approved",
        "payroll_eligible": True,
        "metadata": {},
    }
    incomplete = {
        "status": "incomplete",
        "late_minutes": 0,
        "early_leave_minutes": 0,
        "exception_state": "missing_check_out",
        "approval_status": "unapproved",
        "payroll_eligible": False,
        "metadata": {"exception_state": "missing_check_out", "approval_status": "unapproved", "payroll_eligible": False},
    }
    check("approved life_state", auth.derive_attendance_life_state(approved) == "approved")
    check("incomplete life_state", auth.derive_attendance_life_state(incomplete) == "incomplete")
    stamped = auth.attach_attendance_life_contract(dict(incomplete))
    check("compat emits life_state", stamped.get("life_state") == "incomplete")
    check("compat emits EN exclusion", "Excluded from Payroll" in str(stamped.get("payroll_exclusion_reason_en") or ""))
    check("compat emits AR exclusion", "مستبعد" in str(stamped.get("payroll_exclusion_reason_ar") or ""))
    compat = auth.projection_to_compat_record(
        {
            "projection_id": "p1",
            "company_code": "ATTW1",
            "employee_key": "E1",
            "work_date": "2026-08-19",
            "status": "completed",
            "late_minutes": 0,
            "early_leave_minutes": 0,
            "exception_state": "none",
            "approval_status": "approved",
            "payroll_eligible": True,
            "metadata": {},
        }
    )
    check("projection compat life_state approved", compat.get("life_state") == "approved")
    check("approved day has no payroll exclusion", compat.get("payroll_exclusion_reason") is None)

    for key, weight in candidate_ranking.SOFT_COMPONENT_WEIGHTS.items():
        check(f"ranking component {key} max matches weight", rrp._COMPONENTS[key][2] == weight)

    item = {
        "component_scores": {"skills_alignment": 21.0, "experience_alignment": 10.0},
        "advisory_score": 70,
        "eligibility_bucket": "eligible",
        "required_evidence_complete": True,
        "evidence_coverage": 0.9,
        "name": "Ada",
    }
    contract = rrp._component_score_contract(item, locale="en")
    check("skills max emitted", contract.get("skills_alignment", {}).get("max") == 30.0)
    check("skills weight emitted", contract.get("skills_alignment", {}).get("weight") == 30.0)
    presentation = rrp.present_candidate(item, locale="en")
    check("presentation score carries components", isinstance((presentation.get("score") or {}).get("components"), dict))
    decision = rrp.build_ranking_decision(item, presentation=presentation, locale="en")
    check("ranking_decision keeps numeric component_scores", decision.get("component_scores", {}).get("skills_alignment") == 21.0)
    check(
        "ranking_decision emits component_score_meta max",
        (decision.get("component_score_meta") or {}).get("skills_alignment", {}).get("max") == 30.0,
    )

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("bootstrap expands jobs permissions", "expand_effective_jobs_permissions" in app_src)
    check("wildcard honored in dashboard_context_has_permission", '"*:*" in perms' in app_src)
    check("app.py has no empty-perm fail-open", "if not perms:" not in app_src)
    wc_src = (ROOT / "workspace_capability.py").read_text(encoding="utf-8")
    check("employees soft gate removed", "admin_workspace" not in wc_src)
    check("action inbox no empty-perm fail-open", "or not perms" not in wc_src)

    import app

    base = {
        "company_code": "WAVE4B",
        "actor_user_id": "u1",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "u1",
        "permission_subject_company": "WAVE4B",
    }
    check(
        "runtime *:* grants jobs.create",
        app.dashboard_context_has_permission({**base, "permissions": ["*:*"]}, "jobs.create") is True,
    )
    check(
        "runtime settings.manage expands jobs.create",
        app.dashboard_has_jobs_permission({**base, "permissions": ["settings.manage"]}, "jobs.create") is True,
    )
    check(
        "runtime settings.manage does not grant employees.read",
        app.dashboard_context_has_permission({**base, "permissions": ["settings.manage"]}, "employees.read") is False,
    )
    check(
        "runtime empty permissions fail closed",
        app.dashboard_context_has_permission({**base, "permissions": []}, "jobs.read") is False,
    )
    check(
        "runtime prehire.read expands jobs.read",
        app.dashboard_has_jobs_permission({**base, "permissions": ["prehire.read"]}, "jobs.read") is True,
    )
    owner_perms = set(app.dashboard_effective_permissions_for_user({"role": "owner"}))
    check("owner emission includes jobs.create", "jobs.create" in owner_perms)
    check("owner emission still grant-only for employees.read", "employees.read" not in owner_perms)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
