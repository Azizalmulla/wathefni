#!/usr/bin/env python3
"""Bundle markers for Held CV Assign Job UX (explicit selection only)."""
from __future__ import annotations

import os
from pathlib import Path

WWW = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")


def main() -> int:
    bundles = list((WWW / "assets").glob("CandidatesPage-*.js"))
    # Held card may live in CandidatesPage chunk or a shared chunk — scan both.
    candidates = list((WWW / "assets").glob("CandidatesPage-*.js"))
    held_chunks = list((WWW / "assets").glob("*Held*"))
    # Also scan all JS for markers if chunk naming differs.
    texts = []
    for path in candidates or []:
        texts.append((path.name, path.read_text(errors="ignore")))
    if not texts:
        for path in (WWW / "assets").glob("*.js"):
            text = path.read_text(errors="ignore")
            if "held-intake-review" in text or "Held CVs waiting for a job" in text:
                texts.append((path.name, text))
    assert texts, f"no held-intake bundle under {WWW / 'assets'}"

    needles = (
        "data-held-assign-scope",
        "held-bulk-toolbar",
        "held-bulk-copy",
        "Assign job",
        "all selected candidates will receive the same job",
        "held-intake-review",
    )
    forbidden = (
        "picked.length ? picked : group.app_keys",
        "selectedCount || group.count",
    )
    matched = None
    for name, text in texts:
        if all(n in text for n in needles[:3]) or ("held-intake-review" in text and "Assign job" in text):
            matched = (name, text)
            break
    assert matched, f"markers not found in {[n for n,_ in texts]}"
    name, text = matched
    for needle in needles:
        assert needle in text, f"missing {needle} in {name}"
    for bad in forbidden:
        assert bad not in text, f"forbidden fallback still present: {bad}"
    print("BUNDLE", name)
    print("HELD_ASSIGN_UX_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
