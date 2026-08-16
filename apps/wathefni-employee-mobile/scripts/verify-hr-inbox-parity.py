#!/usr/bin/env python3
"""HR Inbox matches Employee Notifications ledger — shared primitives only."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/inbox/HRInboxParityView.tsx").read_text(encoding="utf-8")
tab = (ROOT / "app/hr/(tabs)/inbox.tsx").read_text(encoding="utf-8")
ledger = (ROOT / "src/components/inboxLedger.tsx").read_text(encoding="utf-8")
employee = (ROOT / "src/features/remaining/RemainingViews.tsx").read_text(encoding="utf-8")
ia = (ROOT / "src/hr/shell/ia.ts").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("Inbox tab uses parity view", "HRInboxParityView" in tab)
check("Wordmark + EditorialHeading + FadeIn", all(x in view for x in ("Wordmark", "EditorialHeading", "FadeIn")))
check("shared InboxLedgerRow", "InboxLedgerRow" in view and "InboxLedgerRow" in ledger)
check("Employee Notifications uses shared ledger", "InboxLedgerRow" in employee and "NotificationInboxRow" in employee)
check("SectionHeader + ShowMoreButton", "SectionHeader" in view and "ShowMoreButton" in view)
check("emphasized unread accent treatment", "emphasized" in view and "accentColor" in view)
check("palette accent not ink/black", "inboxAccentForSection" in (ROOT / "src/hr/features/inbox/inboxComposition.ts").read_text() and "backgroundColor: colors.ink" not in ledger)
check("Inbox allowlist only", "INBOX_SECTION_TYPES" in view and "INBOX_SECTION_TYPES" in ia)
check("no ActionableCard / PrioritySectionList", "ActionableCard" not in view and "PrioritySectionList" not in view)
check("no invented design system cards", "PastelCard" not in view and "AmbientCard" not in view)
keys = ["hrInbox.title", "hrInbox.waitingCount", "hrInbox.clear", "hrInbox.empty"]
check("hrInbox keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-inbox-parity: GREEN")
