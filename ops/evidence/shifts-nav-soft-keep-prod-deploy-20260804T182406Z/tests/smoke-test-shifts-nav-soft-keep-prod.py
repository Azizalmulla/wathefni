#!/usr/bin/env python3
"""Bundle markers for Shifts range soft-keep."""
from __future__ import annotations

import os
from pathlib import Path

WWW = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")


def main() -> int:
    bundles = list((WWW / "assets").glob("PostHire-*.js"))
    assert len(bundles) == 1, bundles
    text = bundles[0].read_text(errors="ignore")
    for needle in (
        "data-shifts-range-soft-keep",
        "data-shifts-range-pending",
        "commitIfLatest",
        "data-shifts-iq-wave2",
        "data-shifts-updating",
        "data-shifts-visual-direction",
    ):
        assert needle in text, needle
    print("BUNDLE", bundles[0].name)
    print("NAV_SOFT_KEEP_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
