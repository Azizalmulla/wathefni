#!/usr/bin/env python3
"""R3 audited script inventory — live tree only (skips ops/evidence)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORCH = REPO / "wathefni-orchestrator"
SKIP = {"evidence", ".venv", "node_modules", "dist", "dist-preview", "__pycache__"}

PRODUCTION_DEFAULTS = (
    'os.environ.setdefault("WATHEFNI_ENV", "production")',
    "os.environ.setdefault('WATHEFNI_ENV', 'production')",
)


def live_py() -> list[Path]:
    out: list[Path] = []
    for root in (ORCH, REPO / "ops"):
        for path in root.rglob("*.py"):
            if any(part in SKIP for part in path.parts):
                continue
            if path.name in {"r3-data-safety-inventory.py", "smoke-test-r3-data-safety.py", "production_data_safety.py"}:
                continue
            out.append(path)
    return sorted(out)


def classify(path: Path, text: str) -> dict:
    rel = str(path.relative_to(REPO))
    name = path.name
    guards = []
    if "activate_fixture_tooling_from_argv" in text:
        guards.append("activate_fixture_tooling_from_argv")
    if "require_fixture_tooling" in text:
        guards.append("require_fixture_tooling")
    if "require_non_production_ops" in text:
        guards.append("require_non_production_ops")
    if "require_production_maintenance" in text:
        guards.append("require_production_maintenance")
    if "require_explicit_environment" in text:
        guards.append("require_explicit_environment")
    if "require_destructive_scope" in text:
        guards.append("require_destructive_scope")
    role = "other"
    if name.startswith("ops-seed-"):
        role = "visual_fixture_seed"
    elif "production-matrix" in name:
        role = "pilot_matrix"
    elif name.startswith("canary-prod-"):
        role = "mutating_canary"
    elif "screenshot" in name or name.endswith("-ui-prod.py"):
        role = "read_oriented_prod_canary"
    elif "backfill" in name or name.startswith("correct-production-"):
        role = "production_maintenance"
    elif "staging-matrix" in name or "staging-proof" in name:
        role = "staging_matrix"
    disposition = "retained"
    if any(p in text for p in PRODUCTION_DEFAULTS):
        disposition = "unsafe_production_default"
    elif "require_production_maintenance" in text:
        disposition = "retained_production_maintenance"
    elif any(g in text for g in ("require_fixture_tooling", "activate_fixture_tooling_from_argv", "require_non_production_ops")):
        disposition = "retained_fail_closed_non_production"
    elif "require_explicit_environment" in text:
        disposition = "retained_explicit_env_no_production_default"
    return {
        "path": rel,
        "role": role,
        "guards": guards,
        "disposition": disposition,
        "unscoped_company_modules_delete": "DELETE FROM company_modules" in text
        and "company_code" not in text.lower(),
    }


def wathefni_scan() -> dict:
    app_py = (ORCH / "app.py").read_text(encoding="utf-8")
    return {
        "implicit_or_wathefni_in_app_py": app_py.count('or "WATHEFNI"') + app_py.count("or 'WATHEFNI'"),
        "require_company_code_call_sites": app_py.count("require_company_code("),
        "wathefni_default_company_symbol": "WATHEFNI_DEFAULT_COMPANY" in app_py,
        "canary_identity_still_named": '"WATHEFNI"' in app_py or "'WATHEFNI'" in app_py,
    }


def main() -> int:
    rows = [classify(path, path.read_text(encoding="utf-8", errors="replace")) for path in live_py()]
    payload = {
        "contract": "r3-data-safety-v1",
        "wathefni": wathefni_scan(),
        "counts_by_disposition": {},
        "scripts": rows,
    }
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    payload["counts_by_disposition"] = counts
    out = Path(os.environ.get("R3_INVENTORY_OUT") or "-")
    text = json.dumps(payload, indent=2)
    if str(out) == "-":
        print(text)
    else:
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out} scripts={len(rows)} dispositions={counts}")
    return 1 if counts.get("unsafe_production_default") else 0


if __name__ == "__main__":
    sys.exit(main())
