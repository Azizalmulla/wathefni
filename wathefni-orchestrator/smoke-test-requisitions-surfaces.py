#!/usr/bin/env python3
"""Requisitions Surface Wave — unit smoke (no DB). Preserves frozen requisitions SM."""
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
    print("    requisitions surfaces — wiring + freeze preservation")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import requisitions as rq
    import requisitions_surfaces as surfaces
    import requisitions_http as http

    check("http register present", hasattr(http, "register_requisitions_http"))
    check("queue_payload", callable(surfaces.queue_payload))
    check("detail_payload", callable(surfaces.detail_payload))
    check("explain_status", callable(surfaces.explain_status))
    check("list_requisitions surface-only", callable(surfaces.list_requisitions))
    check("frozen SM draft→pending", rq.can_transition("draft", "pending_approval"))
    check("frozen SM pending→approved", rq.can_transition("pending_approval", "approved"))
    check("frozen SM filled terminal", not rq.can_transition("filled", "open"))
    src = (orch / "requisitions.py").read_text(encoding="utf-8")
    check("frozen SM mentions SoD", "self_approval_forbidden" in src)

    app_src = (orch / "app.py").read_text(encoding="utf-8")
    check("app registers requisitions_http", "register_requisitions_http" in app_src)
    check("requisitions RBAC perms", "requisitions.read" in app_src and "requisitions.approve" in app_src)

    op_src = (orch / "operator_mobile.py").read_text(encoding="utf-8")
    check("hr mobile capability requisitions_review", "requisitions_review" in op_src)

    web = root / "apps" / "wathefni-dashboard" / "src"
    check("HR Web workspace", (web / "prehire/RequisitionsWorkspace.tsx").is_file())
    ws = (web / "prehire/RequisitionsWorkspace.tsx").read_text(encoding="utf-8")
    check("web RTL via dir", "dir={isAr ? 'rtl' : 'ltr'}" in ws)
    check("web decision framing", "who is blocking" in ws.lower() or "من يمنع" in ws or "Needs approval" in ws)
    check("web SoD note", "self-approve" in ws.lower() or "لا يعتمد" in ws)

    mobile = root / "apps" / "wathefni-employee-mobile"
    check("HR mobile queue", (mobile / "src/hr/features/requisitions/HRRequisitionsQueueView.tsx").is_file())
    check("HR mobile detail", (mobile / "src/hr/features/requisitions/HRRequisitionDetailView.tsx").is_file())
    check("no employee ESS requisitions", not (mobile / "app/requisitions.tsx").is_file())
    check(
        "assistant deep link",
        "requisitions: '/hr/requisitions'"
        in (mobile / "src/hr/features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8"),
    )

    en = (mobile / "src/i18n/en.json").read_text(encoding="utf-8")
    ar = (mobile / "src/i18n/ar.json").read_text(encoding="utf-8")
    check("EN i18n hrRequisitions", "hrRequisitions" in en)
    check("AR i18n hrRequisitions", "hrRequisitions" in ar and "طلبات التوظيف" in ar)

    freeze = root / "ops" / "REQUISITIONS_WAVE1_BACKEND_FREEZE.md"
    check("backend freeze intact", freeze.is_file() and "FROZEN" in freeze.read_text(encoding="utf-8"))

    cap = (web / "lib/workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.requisitions surface", "nav.requisitions" in cap)
    check("nav.probation surface present", "nav.probation" in cap)
    check("nav.preboarding surface present", "nav.preboarding" in cap)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("REQUISITIONS_SURFACES_UNIT_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
