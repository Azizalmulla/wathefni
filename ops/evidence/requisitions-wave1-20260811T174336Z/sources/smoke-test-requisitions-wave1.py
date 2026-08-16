#!/usr/bin/env python3
"""Wave 1 — Requisitions authority unit smoke (no DB required).

Pins:
  - schema pack + version
  - requisition state machine
  - runtime flag default OFF + allowlist helper
  - rollback guidance
  - job publish gate wired in prehire_jobs (static)
  - ensure_requisitions_schema wired in app.ensure_schema (static)
  - no Requisitions UI surface claimed this slice

Run: python3 smoke-test-requisitions-wave1.py
"""
from __future__ import annotations

import os
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
    print("    requisitions wave1 — SM + flags + publish-gate wiring")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import requisitions as rq

    check("schema version pinned", rq.REQUISITIONS_SCHEMA_VERSION == "1.0.0")
    check("sql pack exists", rq._SCHEMA.is_file())

    # --- State machine --------------------------------------------------------
    check("draft→pending_approval", rq.can_transition("draft", "pending_approval"))
    check("pending_approval→approved", rq.can_transition("pending_approval", "approved"))
    check("pending_approval→rejected", rq.can_transition("pending_approval", "rejected"))
    check("rejected→draft", rq.can_transition("rejected", "draft"))
    check("approved→open", rq.can_transition("approved", "open"))
    check("open→filled", rq.can_transition("open", "filled"))
    check("open→cancelled", rq.can_transition("open", "cancelled"))
    check("approved not→filled", not rq.can_transition("approved", "filled"))
    check("filled terminal", not rq.can_transition("filled", "open"))
    check("cancelled terminal", not rq.can_transition("cancelled", "draft"))

    # --- Flags ----------------------------------------------------------------
    prev_flag = os.environ.pop("WATHEFNI_REQUISITIONS", None)
    prev_cos = os.environ.pop("WATHEFNI_REQUISITIONS_COMPANIES", None)
    try:
        check("runtime flag default off", rq.requisitions_runtime_flag_on() is False)
        os.environ["WATHEFNI_REQUISITIONS"] = "on"
        check("runtime flag on", rq.requisitions_runtime_flag_on() is True)
        os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = "ACME, beta "
        allow = rq.requisitions_company_allowlist()
        check("allowlist normalizes", allow == {"ACME", "BETA"}, allow)
        os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = ""
        check("empty allowlist = nobody", rq.requisitions_company_allowlist() == set())
    finally:
        if prev_flag is None:
            os.environ.pop("WATHEFNI_REQUISITIONS", None)
        else:
            os.environ["WATHEFNI_REQUISITIONS"] = prev_flag
        if prev_cos is None:
            os.environ.pop("WATHEFNI_REQUISITIONS_COMPANIES", None)
        else:
            os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = prev_cos

    rb = rq.rollback_guidance()
    check("rollback guidance present", isinstance(rb, dict) and "runtime" in rb and "data" in rb)

    # --- Static wiring --------------------------------------------------------
    prehire = (orch / "prehire_jobs.py").read_text(encoding="utf-8")
    check(
        "prehire_jobs calls assert_job_publish_allowed",
        "assert_job_publish_allowed" in prehire and "import requisitions" in prehire,
    )
    check(
        "publish/reopen/resume path gated",
        'action == "publish"' in prehire and "assert_job_publish_allowed" in prehire,
    )
    app_src = (orch / "app.py").read_text(encoding="utf-8")
    check(
        "app.ensure_schema wires ensure_requisitions_schema",
        "ensure_requisitions_schema" in app_src and "import requisitions" in app_src,
    )

    # No UI claim this slice
    dash = orch.parent / "apps" / "wathefni-dashboard" / "src"
    ui_hits = []
    if dash.is_dir():
        for p in dash.rglob("*.tsx"):
            try:
                txt = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if "RequisitionsPage" in txt or "requisitions.read" in txt:
                ui_hits.append(str(p.relative_to(dash)))
    check("no Requisitions UI page claimed", ui_hits == [], ui_hits)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("REQUISITIONS_WAVE1_UNIT_FAIL")
        return 1
    print("REQUISITIONS_WAVE1_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
