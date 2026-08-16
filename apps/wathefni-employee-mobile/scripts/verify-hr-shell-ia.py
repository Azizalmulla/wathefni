#!/usr/bin/env python3
"""HR shell IA foundation contract — Home · People · Inbox · Hiring · More."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ia = (ROOT / "src/hr/shell/ia.ts").read_text(encoding="utf-8")
tabs = (ROOT / "app/hr/(tabs)/_layout.tsx").read_text(encoding="utf-8")
home = (ROOT / "src/hr/features/home/HRHomeParityView.tsx").read_text(encoding="utf-8")
inbox = (ROOT / "app/hr/(tabs)/inbox.tsx").read_text(encoding="utf-8")
hiring = (ROOT / "app/hr/(tabs)/hiring.tsx").read_text(encoding="utf-8")
more = (ROOT / "app/hr/(tabs)/more.tsx").read_text(encoding="utf-8")
hr_layout = (ROOT / "app/hr/_layout.tsx").read_text(encoding="utf-8")
en = (ROOT / "src/hr/i18n/en.json").read_text(encoding="utf-8")
ar = (ROOT / "src/hr/i18n/ar.json").read_text(encoding="utf-8")
parity = (ROOT / "src/hr/features/home/homeParityComposition.ts").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("tabs layout exists", (ROOT / "app/hr/(tabs)/_layout.tsx").is_file())
check("root hr index removed", not (ROOT / "app/hr/index.tsx").is_file())
check("stack hosts (tabs)", 'name="(tabs)"' in hr_layout)
check("employee theme tab bar", "colors.ink" in tabs and "tabFeedback" in tabs)
check("home uses HOME_SECTION_TYPES", "HOME_SECTION_TYPES" in home)
check("home has item cap", "HOME_VISIBLE_ITEM_CAP" in parity)
check("home is not module directory", "workspaceRoutes" not in home and "ActionableCard" not in home)
check("inbox allowlist excludes delivery/hiring", "INBOX_SECTION_TYPES" in ia and "delivery_alerts" not in ia.split("INBOX_SECTION_TYPES")[1].split("]")[0])
check("inbox tab uses parity view", "HRInboxParityView" in inbox)
check("hiring separate sections", "HIRING_SECTION_TYPES" in ia)
check("more uses launcher (no Hiring duplicates)", "HRMoreLauncherView" in more)
check("people tab is directory", "HRPeopleDirectoryView" in (ROOT / "app/hr/(tabs)/people.tsx").read_text())
check("i18n tab keys en+ar", all(k in en and k in ar for k in ['"tabs.home"', '"tabs.people"', '"tabs.inbox"', '"tabs.hiring"', '"tabs.more"']))
check("no fake urgency invented in shell", "invent" not in home.lower() and "fake" not in home.lower())
print("hr-shell-ia: GREEN")
