#!/usr/bin/env python3
"""HR Home visual parity contract — Employee composition primitives only."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/home/HRHomeParityView.tsx").read_text(encoding="utf-8")
tabs = (ROOT / "app/hr/(tabs)/_layout.tsx").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
fmt = (ROOT / "src/lib/format.ts").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("uses PageScreen/PageScrollView", "PageScreen" in view and "PageScrollView" in view)
check("uses Wordmark (not Wathefni HR)", "Wordmark" in view and "Wathefni HR" not in view)
check("uses EditorialHeading + FadeIn", "EditorialHeading" in view and "FadeIn" in view)
check("uses AmbientCard + AmbientIconTile", "AmbientCard" in view and "AmbientIconTile" in view)
check("uses ListRow + StatusChip", "ListRow" in view and "StatusChip" in view)
parity = (ROOT / "src/hr/features/home/homeParityComposition.ts").read_text()
ui = (ROOT / "src/components/ui.tsx").read_text()
check("quiet row icons not ambient tiles", "iconTint={colors.surfaceMuted}" in view)
check("progress via StatusChip tones", "hrHomeProgressTone" in parity)
check(
    "chip semantics yellow/blue/pink/green",
    "'yellow' | 'blue' | 'pink' | 'green'" in parity
    and "blue:" in ui
    and "scheduleComposition.planned.fill" in ui,
)
check("in progress is blue not neutral", "return 'blue'" in parity and "return 'neutral'" not in parity)
check("green hero locked", 'module="leave"' in view)
check("no clinical StatusChip parade", "hrHomeStatusKey" in (ROOT / "src/hr/features/home/homeParityComposition.ts").read_text())
check("uses statusLabel (no raw enums in UI)", "item.status}" not in view)
check("ambient color roles present", "homeComposition" in view)
check("not_started humanized", "not_started" in fmt and en.get("status.not_started") == "Not started")
check("ar not_started", ar.get("status.not_started") == "لم يبدأ")
check("hrHome keys EN+AR", all(k in en and k in ar for k in [
    "hrHome.heading", "hrHome.waitingSection", "hrHome.caughtUpTitle", "hrHome.seeInbox",
    "hrHome.scopeCompany", "hrHome.scopeTeam",
]))
check("tab labels EN+AR", all(k in en and k in ar for k in [
    "tabs.people", "tabs.inbox", "tabs.hiring", "tabs.more",
]))
check("tabs use employee useI18n + tabFeedback", "useI18n" in tabs and "tabFeedback" in tabs)
check("no module grid", "workspaceRoutes" not in view and "ActionableCard" not in view)
check("overflow to Inbox", "/hr/inbox" in view and "hrHome.seeInbox" in view)
check("no locale clutter on Home", "setLocale" not in view)
check(
    "pull refresh not tied to isFetching",
    "pullRefreshing" in view
    and "refreshing={refreshing}" in view
    and "isLoading || priorities.isFetching" not in view
    and "refreshing={loading}" not in view,
)
check(
    "initial load separate from pull spinner",
    "isLoading && !priorities.data" in view,
)
print("hr-home-parity: GREEN")
