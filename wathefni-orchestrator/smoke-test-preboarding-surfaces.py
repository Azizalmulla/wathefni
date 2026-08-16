#!/usr/bin/env python3
"""Preboarding Surface Wave — static + authority contract smoke (no UI rewrite of SM)."""
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
    print("    preboarding surfaces — wiring + freeze + EN/AR + module gates")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import preboarding as pb
    import preboarding_surfaces as surfaces
    import preboarding_http as http

    check("backend freeze doc", (root / "ops/PREBOARDING_WAVE1_BACKEND_FREEZE.md").is_file())
    check("http register present", hasattr(http, "register_preboarding_http"))
    check("list_assignments helper", callable(pb.list_assignments))
    check("surfaces queue helper", callable(surfaces.queue_payload))
    check("employee self helper", callable(surfaces.employee_self_payload))
    check("explain blockers helper", callable(surfaces.explain_blockers))

    # Ready still derived
    items = [{"item_key": "a", "required": True, "status": "pending", "depends_on": []}]
    check("ready not cosmetic", surfaces.enrich_assignment({"status": "in_progress", "readiness": {}}, items)["readiness"]["ready"] is False)

    app_src = (orch / "app.py").read_text(encoding="utf-8")
    check("app registers preboarding_http", "register_preboarding_http" in app_src)
    check("preboarding feature in employee contract", '"preboarding"' in app_src and "complete_item" in app_src)
    check("pending_start access mode", "preboarding_only" in app_src or "employee_preboarding_only" in app_src)
    check("preboarding RBAC perms", "preboarding.read" in app_src and "preboarding.waive_item" in app_src)

    op_src = (orch / "operator_mobile.py").read_text(encoding="utf-8")
    check("hr mobile capability preboarding_review", "preboarding_review" in op_src)

    web = root / "apps/wathefni-dashboard/src"
    check("HR Web workspace", (web / "posthire/PreboardingWorkspace.tsx").is_file())
    api = (web / "lib/api.ts").read_text(encoding="utf-8")
    check("web api client", "getPosthirePreboarding" in api and "postPreboardingWaive" in api)
    app_tsx = (web / "App.tsx").read_text(encoding="utf-8")
    check("web nav EN", "preboarding" in app_tsx and "Preboarding" in app_tsx)
    check("web nav AR", "التهيئة قبل الالتحاق" in app_tsx)
    check("web RTL via dir", "dir={isAr ? 'rtl' : 'ltr'}" in (web / "posthire/PreboardingWorkspace.tsx").read_text(encoding="utf-8"))

    mobile = root / "apps/wathefni-employee-mobile"
    check("HR mobile queue", (mobile / "src/hr/features/preboarding/HRPreboardingQueueView.tsx").is_file())
    check("HR mobile detail", (mobile / "src/hr/features/preboarding/HRPreboardingDetailView.tsx").is_file())
    check("employee preboarding screen", (mobile / "app/preboarding.tsx").is_file())
    en = (mobile / "src/i18n/en.json").read_text(encoding="utf-8")
    ar = (mobile / "src/i18n/ar.json").read_text(encoding="utf-8")
    check("mobile EN keys", "hrPreboarding" in en and "employeePreboarding" in en)
    check("mobile AR keys", "hrPreboarding" in ar and "قبل الالتحاق" in ar)
    check("assistant deep link", "preboarding: '/hr/preboarding'" in (mobile / "src/hr/features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8"))
    check("employee route composition", "'/preboarding': { feature: 'preboarding' }" in (mobile / "src/composition/employeeAppComposition.ts").read_text(encoding="utf-8"))

    # Module-off / freeze: no SM change to converted→ready
    check("converted still terminal", not pb.can_transition_assignment("converted", "ready"))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("PREBOARDING_SURFACES_UNIT_FAIL")
        return 1
    print("PREBOARDING_SURFACES_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
