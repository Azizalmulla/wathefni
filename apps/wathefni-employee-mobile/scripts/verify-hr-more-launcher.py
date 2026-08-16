#!/usr/bin/env python3
"""HR More launcher — operations + account, no Hiring duplicates, entitlement-gated."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/more/HRMoreLauncherView.tsx").read_text(encoding="utf-8")
launcher = (ROOT / "src/hr/features/more/moreLauncher.ts").read_text(encoding="utf-8")
tab = (ROOT / "app/hr/(tabs)/more.tsx").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("More tab uses launcher view", "HRMoreLauncherView" in tab)
check("Wordmark + EditorialHeading", "Wordmark" in view and "EditorialHeading" in view)
check("operations modules present", all(k in launcher for k in ("attendance", "shifts", "onboarding", "documents", "tasks")))
check("no Candidates/Interviews on More", "candidates" not in launcher and "interviews" not in launcher)
check("Hiring group removed", "'hiring'" not in launcher and "groupHiring" not in view)
check("Account: settings + sign out", "hrMore.settings" in view and "hrMore.signOut" in view)
check("delivery alerts locked + gated", "deliveryAlerts" in launcher and "Delivery alerts lock" in launcher)
check("assistant under More + gated", "assistant" in launcher and "'assistant'" in launcher and "/hr/assistant" in launcher)
check("workspace.enabled + capability gate", "workspaces[link.workspace]" in launcher and "hasAnyCapability" in launcher)
check("quiet ListRows not dashboard cards", "ListRow" in view and "AmbientCard" not in view and "ActionableCard" not in view)
keys = [
    "hrMore.title",
    "hrMore.groupOperations",
    "hrMore.groupAccount",
    "hrMore.deliveryAlerts",
    "hrMore.assistant",
    "hrMore.emptyOpsTitle",
]
check("hrMore keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-more-launcher: GREEN")
