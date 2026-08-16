#!/usr/bin/env python3
"""PT7 — Assistant Talent intelligence unit/honesty prove."""
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
    print("    pt7 assistant — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import action_registry as registry
    import assistant_capability_catalog as catalog
    import talent_assistant_pt7 as pt7
    import tool_call_orchestrator as tools

    h = pt7.honesty_payload()
    check("stamp", pt7.PASS_STAMP == "PT7_ASSISTANT_TALENT_INTELLIGENCE_FULL_PASS")
    check("deterministic services", h.get("calls_deterministic_services") is True)
    check("no prompt math", h.get("no_prompt_recreated_talent_math") is True)
    check("no mutation tools", h.get("no_mutation_tools") is True)
    check("same WHY as UI", h.get("same_why_as_ui") is True)
    pt7.register_assistant_tools()
    for name in pt7.READ_TOOLS:
        spec = registry.spec_for(name)
        check(f"registered {name}", spec is not None and callable(spec.executor), spec)
        check(f"permission mapped {name}", name in tools.TOOL_PERMISSION_MAP, tools.TOOL_PERMISSION_MAP.get(name))
        check(f"{name} not confirm-mutate", spec is not None and spec.requires_confirmation is False)
    for name in pt7.FORBIDDEN_MUTATIONS:
        check(f"no mutation {name}", registry.spec_for(name) is None)
    check("catalog posthire_talent", "posthire_talent" in catalog.CAPABILITY_IDS)
    check("catalog posthire_performance", "posthire_performance" in catalog.CAPABILITY_IDS)
    src = (root / "talent_assistant_pt7.py").read_text(encoding="utf-8")
    check("explain uses get_why", "pt2.get_why" in src)
    check("does not claim HiPo from derived", "Designated HiPo is" in src)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT7_ASSISTANT_TALENT_INTELLIGENCE_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
