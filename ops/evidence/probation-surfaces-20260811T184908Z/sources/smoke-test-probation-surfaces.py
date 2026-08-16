#!/usr/bin/env python3
"""Probation Surface Wave — unit smoke (no DB). Preserves frozen probation SM."""
from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    probation surfaces — wiring + freeze preservation")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import probation as pr
    import probation_surfaces as surfaces
    import probation_http as http

    check("http register present", hasattr(http, "register_probation_http"))
    check("queue_payload", callable(surfaces.queue_payload))
    check("detail_payload", callable(surfaces.detail_payload))
    check("employee_self_payload", callable(surfaces.employee_self_payload))
    check("explain_status", callable(surfaces.explain_status))
    check("list_cases surface-only", callable(surfaces.list_cases))
    check("frozen SM active→under_review", pr.can_transition_case("active", "under_review"))
    check("frozen SM under_review→confirmed", pr.can_transition_case("under_review", "confirmed"))
    check("frozen SM confirmed terminal", not pr.can_transition_case("confirmed", "active"))

    app_src = (orch / "app.py").read_text(encoding="utf-8")
    check("app registers probation_http", "register_probation_http" in app_src)
    check("probation RBAC perms", "probation.read" in app_src and "probation.decide" in app_src)
    check("employee feature probation", '"probation"' in app_src and "complete_item" in app_src)

    op_src = (orch / "operator_mobile.py").read_text(encoding="utf-8")
    check("hr mobile capability probation_review", "probation_review" in op_src)

    web = root / "apps" / "wathefni-dashboard" / "src"
    check("HR Web workspace", (web / "posthire/ProbationWorkspace.tsx").is_file())
    ws = (web / "posthire/ProbationWorkspace.tsx").read_text(encoding="utf-8")
    check("web RTL via dir", "dir={isAr ? 'rtl' : 'ltr'}" in ws)
    check("web decision framing", "Who is on probation" in ws or "من في التجربة" in ws)
    check("web not generic checklist-only", "decision_required" in ws.lower() or "Decision required" in ws)

    mobile = root / "apps" / "wathefni-employee-mobile"
    check("HR mobile queue", (mobile / "src/hr/features/probation/HRProbationQueueView.tsx").is_file())
    check("HR mobile detail", (mobile / "src/hr/features/probation/HRProbationDetailView.tsx").is_file())
    check("employee app screen", (mobile / "app/probation.tsx").is_file())
    emp = (mobile / "app/probation.tsx").read_text(encoding="utf-8")
    check("employee strips confidential", "confidential" in emp.lower() or "employeeProbation" in emp)
    check("assistant deep link", "probation: '/hr/probation'" in (mobile / "src/hr/features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8"))

    en = (mobile / "src/i18n/en.json").read_text(encoding="utf-8")
    ar = (mobile / "src/i18n/ar.json").read_text(encoding="utf-8")
    check("EN i18n hrProbation", "hrProbation" in en)
    check("AR i18n hrProbation", "hrProbation" in ar and "فترة التجربة" in ar)

    freeze = root / "ops" / "PROBATION_WAVE1_BACKEND_FREEZE.md"
    check("backend freeze intact", freeze.is_file() and "FROZEN" in freeze.read_text(encoding="utf-8"))

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PROBATION_SURFACES_UNIT_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
