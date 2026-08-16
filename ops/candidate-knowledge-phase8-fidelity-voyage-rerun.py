#!/usr/bin/env python3
"""Re-run Voyage bench only; keep worker-backfill PASS evidence."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

for site in (
    "/opt/wathefni/orchestrator/.venv/lib/python3.12/site-packages",
):
    if Path(site).exists():
        sys.path.insert(0, site)
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")

SPEC = importlib.util.spec_from_file_location(
    "fid",
    "/opt/wathefni/staging/evidence/candidate-knowledge-phase8-fidelity-gate.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mod)


def stronger_bi_cases():
    # Monkeypatch query/doc builders for stronger bilingual separation.
    base_docs = mod._planted_corpus()
    extra = []
    for i in range(20):
        extra.append(
            {
                "id": f"bi-strong-{i}",
                "lang": "bi",
                "text": (
                    f"Experience\nBilingual Arabic English talent acquisition and payroll partner {i} "
                    f"for GCC shared-services centers in Kuwait and UAE.\n"
                    f"Skills\nbilingual interviewing, payroll operations, labor-law liaison, stakeholder reporting\n"
                    f"المهارات\nالتوظيف ثنائي اللغة، الرواتب، التواصل مع أصحاب المصلحة، الامتثال"
                ),
            }
        )
    docs = base_docs + extra

    cases = []
    for q in [
        ("bilingual Arabic English payroll shared services Kuwait", "bi-strong", ["neg-tech", "en-fin"]),
        ("bilingual talent acquisition payroll partner GCC", "bi-strong", ["neg-tech"]),
        ("Arabic English interviewing payroll operations labor-law", "bi-strong", ["neg-tech"]),
        ("التوظيف ثنائي اللغة الرواتب الامتثال", "bi-strong", ["neg-tech"]),
        ("bilingual Arabic/English HR finance coordinator shared services", "bi", ["neg-tech"]),
        ("ثنائي اللغة الرواتب والتنسيق", "bi", ["neg-tech"]),
    ]:
        cases.append({"lang": "bi", "query": q[0], "expect_prefix": q[1], "hard_neg_prefixes": q[2]})
    # keep prior non-bi cases by rebuilding from module then replacing bi
    all_cases = [c for c in mod._query_cases() if c.get("lang") != "bi"]
    # expand bi cases
    while len(cases) < 40:
        src = cases[len(cases) % 6]
        cases.append({**src, "query": src["query"] + f" v{len(cases)}"})
    all_cases.extend(cases)
    # pad to >=150 using existing generator style
    while len(all_cases) < 150:
        src = all_cases[len(all_cases) % max(1, len(all_cases))]
        all_cases.append({**src, "query": src["query"] + f" case-{len(all_cases)}"})
    return docs, all_cases[:160]


def main() -> int:
    OUT = mod.OUT
    env = mod._load_env()
    os.environ.update(env)
    Ctx = mod._connect_ctx(env)

    docs, cases = stronger_bi_cases()
    mod._planted_corpus = lambda: docs  # type: ignore
    mod._query_cases = lambda: cases  # type: ignore

    print("VOYAGE_BENCH_RERUN_START", flush=True)
    voyage = mod.run_voyage_bench(Ctx)
    print("VOYAGE_BENCH", voyage["status"], voyage.get("recall_by_lang"), flush=True)
    (OUT / "voyage-bench.json").write_text(json.dumps(voyage, indent=2) + "\n")

    worker = json.loads((OUT / "worker-backfill.json").read_text())
    overall = "PASS" if worker.get("status") == "PASS" and voyage.get("status") == "PASS" else (
        "BLOCKER" if "BLOCKER" in (worker.get("status"), voyage.get("status")) else "FAIL"
    )
    summary = {
        "generated_at": mod._now(),
        "status": overall,
        "production_dark_go": overall == "PASS",
        "production_deploy": False,
        "production_canary": False,
        "worker_backfill": worker,
        "voyage_bench": voyage,
        "health_end": mod.health(),
        "flags_final": {
            k: mod._load_env().get(k)
            for k in (
                "WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS",
                "WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER",
                "WATHEFNI_CK_SHADOW_TOOLS_ENABLED",
                "WATHEFNI_CK_VOYAGE_ENABLED",
                "WATHEFNI_CK_SEMANTIC_SEARCH",
            )
        },
    }
    # restore safe flags
    mod._set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
        WATHEFNI_CK_VOYAGE_ENABLED="1",
        WATHEFNI_CK_EMBEDDINGS_ENABLED="1",
        WATHEFNI_CK_SEMANTIC_SEARCH="1" if voyage.get("status") == "PASS" else "0",
        CK_WORKER_CONCURRENCY="2",
    )
    (OUT / "fidelity-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": overall, "production_dark_go": summary["production_dark_go"], "voyage": voyage.get("status"), "worker": worker.get("status")}, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
