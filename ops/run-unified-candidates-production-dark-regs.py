#!/usr/bin/env python3
"""Safe production-dark / unit frozen packs (no destructive synthetic production data)."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ORCH = Path("/opt/wathefni/orchestrator")
EVIDENCE = Path(os.environ["DARK_EVIDENCE"])
ENV = {
    **os.environ,
    "WATHEFNI_ENV": "production",
    "WATHEFNI_ENVIRONMENT": "production",
    "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.env",
    "WATHEFNI_WORKSPACE": "/root/.openclaw/workspaces/company-wathefni",
    "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
    "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
    "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni",
    "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-production-isolation-v1",
    "WATHEFNI_DELIVERY_MODE": os.environ.get("WATHEFNI_DELIVERY_MODE", ""),
    "WATHEFNI_CANONICAL_LIFECYCLE": "true",
    "PYTHONPATH": str(ORCH),
}

# Prefer unit/safe packs that do not insert destructive production records.
PACKS = [
    ("unit", "test_unified_candidates.py"),
    ("unit", "smoke-test-canonical-recruiting-lifecycle.py"),
    ("unit", "smoke-test-prehire-overview-unit.py"),
    ("unit", "smoke-test-prehire-assistant-parity.py"),
    ("unit", "smoke-test-offer-lifecycle.py"),
    ("unit", "smoke-test-assessments.py"),
    ("unit", "smoke-test-jobs-phase2-stage-a-unit.py"),
    ("unit", "smoke-test-tenant-isolation-harness.py"),
    ("readonly_note", "ops/candidates-c3-production-audit.py"),
]


def main() -> int:
    results = []
    for kind, name in PACKS:
        path = ORCH / name
        log = EVIDENCE / f"reg-{Path(name).name}.log"
        row = {"pack": name, "kind": kind, "exists": path.exists()}
        if not path.exists():
            row["status"] = "missing"
            print("MISSING", name)
            results.append(row)
            continue
        if kind == "readonly_note" and not path.exists():
            row["status"] = "missing"
            results.append(row)
            continue
        t0 = time.time()
        with log.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(
                ["/opt/wathefni/orchestrator/.venv/bin/python", str(path)],
                cwd=str(ORCH),
                env=ENV,
                stdout=fh,
                stderr=subprocess.STDOUT,
                text=True,
            )
        row.update(
            {
                "status": "pass" if proc.returncode == 0 else "fail",
                "rc": proc.returncode,
                "elapsed_s": round(time.time() - t0, 2),
                "log": str(log),
            }
        )
        print(row["status"].upper(), name, f"rc={proc.returncode}")
        results.append(row)
    out = {
        "pass": sum(1 for r in results if r.get("status") == "pass"),
        "fail": sum(1 for r in results if r.get("status") == "fail"),
        "missing": sum(1 for r in results if r.get("status") == "missing"),
        "results": results,
    }
    (EVIDENCE / "frozen-regressions.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("pass", "fail", "missing")}, indent=2))
    return 0 if out["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
