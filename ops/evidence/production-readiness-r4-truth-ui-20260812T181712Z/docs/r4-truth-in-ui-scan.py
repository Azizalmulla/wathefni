#!/usr/bin/env python3
"""Classify high-risk truth-state patterns in production dashboard client source.

Does not fail the run. Named R4 blockers are enforced by smoke-test-r4-truth-in-ui.py.
This scan is evidence: P0/P1 vs safe display defaults.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DASH = REPO / "apps" / "wathefni-dashboard" / "src"

NAMED = {
    "pages/InterviewsPage.tsx",
    "pages/OverviewPage.tsx",
    "posthire/PostHire.tsx",
    "pages/NotificationsPage.tsx",
    "App.tsx",
    "components/candidates/CandidateGovernedProfile.tsx",
    "lib/workspaceCapability.ts",
    "lib/dashboardNavigation.ts",
}

SKIP_SUFFIX = (".test.ts", ".test.tsx", ".repro.test.tsx")

OR_EMPTY = re.compile(r"(\w+(?:\.\w+)*)\s*\|\|\s*\[\]")
NULLISH_EMPTY = re.compile(r"(\w+(?:\.\w+)*)\s*\?\?\s*\[\]")
CATCH_EMPTY_RETURN = re.compile(r"catch\s*\([^)]*\)\s*\{\s*return\s*\[\]", re.S)
CATCH_SET_EMPTY = re.compile(r"catch\s*(?:\([^)]*\))?\s*\{\s*[^}]{0,200}set[A-Z]\w+\(\[\]\)", re.S)


def classify(rel: str, kind: str, snippet: str) -> str:
    if rel in NAMED and kind in {"catch_return_empty", "catch_set_empty"}:
        if "Error(true)" in snippet or "LoadError" in snippet or "listError" in snippet:
            return "safe_after_error_flag"
        return "p0_named_surface"
    if kind in {"or_empty", "nullish_empty"}:
        if rel in NAMED:
            return "named_display_default_review"
        return "safe_display_default"
    return "review"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    findings: list[dict[str, object]] = []
    for path in sorted(DASH.rglob("*.tsx")) + sorted(DASH.rglob("*.ts")):
        rel = str(path.relative_to(DASH))
        if rel.endswith(SKIP_SUFFIX) or "/test/" in f"/{rel}":
            continue
        text = path.read_text(encoding="utf-8")
        for rx, kind in (
            (OR_EMPTY, "or_empty"),
            (NULLISH_EMPTY, "nullish_empty"),
            (CATCH_EMPTY_RETURN, "catch_return_empty"),
            (CATCH_SET_EMPTY, "catch_set_empty"),
        ):
            for match in rx.finditer(text):
                start = text.rfind("\n", 0, match.start()) + 1
                line = text.count("\n", 0, match.start()) + 1
                snippet = text[match.start() : match.end()][:160]
                findings.append(
                    {
                        "file": rel,
                        "line": line,
                        "kind": kind,
                        "class": classify(rel, kind, text[max(0, match.start() - 200) : match.end() + 80]),
                        "snippet": snippet.replace("\n", " "),
                    }
                )
    p0 = [f for f in findings if str(f["class"]).startswith("p0")]
    named = [f for f in findings if f["class"] == "named_display_default_review"]
    payload = {
        "counts": {
            "total": len(findings),
            "p0_named_surface": len(p0),
            "named_display_default_review": len(named),
            "safe_display_default": sum(1 for f in findings if f["class"] == "safe_display_default"),
        },
        "p0": p0,
        "named_review": named[:80],
        "note": "R4 fixes named blocker surfaces. Remaining || [] after a successful payload or for local UI lists are classified as safe display defaults.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"    scan wrote {out} ({payload['counts']})")
    if p0:
        print("    R4_SCAN_NAMED_P0")
        return 1
    print("    R4_SCAN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
