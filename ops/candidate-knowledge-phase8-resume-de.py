#!/usr/bin/env python3
"""Resume Phase 8 Stages D–E after C PASS (uses orchestrator venv site-packages)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

for site in (
    "/opt/wathefni/orchestrator/.venv/lib/python3.12/site-packages",
    "/opt/wathefni/orchestrator/.venv/lib/python3.11/site-packages",
):
    if Path(site).exists():
        sys.path.insert(0, site)

sys.path.insert(0, "/opt/wathefni/staging/orchestrator")

SPEC = importlib.util.spec_from_file_location(
    "ck_p8_exec",
    "/opt/wathefni/staging/evidence/candidate-knowledge-phase8/candidate-knowledge-phase8-staging-execute.py",
)
harness = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(harness)


def main() -> int:
    OUT = harness.OUT
    OUT.mkdir(parents=True, exist_ok=True)
    env = harness._load_env()
    os.environ.update(env)
    Ctx = harness._connect_ctx(env)
    report = {
        "generated_at": harness._now(),
        "health_start": harness.health(),
        "stages": {
            "A": {"status": "PASS", "note": "service install completed prior"},
            "B": json.loads((OUT / "stage-b.json").read_text()),
            "C": json.loads((OUT / "stage-c.json").read_text()),
        },
    }
    print("STAGE_D_START", flush=True)
    report["stages"]["D"] = harness.stage_d(env, Ctx)
    print("STAGE_D", report["stages"]["D"]["status"], flush=True)
    (OUT / "stage-d.json").write_text(json.dumps(report["stages"]["D"], indent=2, default=str) + "\n")

    print("STAGE_E_START", flush=True)
    report["stages"]["E"] = harness.stage_e(env, Ctx)
    print("STAGE_E", report["stages"]["E"]["status"], flush=True)
    (OUT / "stage-e.json").write_text(json.dumps(report["stages"]["E"], indent=2, default=str) + "\n")

    harness.set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
    )
    report["health_end"] = harness.health()
    report["flags_final"] = {
        k: harness._load_env().get(k)
        for k in (
            "WATHEFNI_CANDIDATE_KNOWLEDGE",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER",
            "WATHEFNI_CK_SHADOW_TOOLS_ENABLED",
            "WATHEFNI_CK_VOYAGE_ENABLED",
            "WATHEFNI_CK_SEMANTIC_SEARCH",
        )
    }
    statuses = [report["stages"][s]["status"] for s in ("A", "B", "C", "D", "E")]
    if any(st == "BLOCKER" for st in statuses):
        report["status"] = "BLOCKER"
    elif any(st == "FAIL" for st in statuses):
        report["status"] = "FAIL"
    else:
        report["status"] = "PASS"
    report["production_dark_go"] = report["status"] == "PASS"
    (OUT / "phase8-staging-summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "production_dark_go": report["production_dark_go"],
                "stages": {k: v["status"] for k, v in report["stages"].items()},
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
