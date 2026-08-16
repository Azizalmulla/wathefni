#!/usr/bin/env python3
"""HR Hiring home — product pass contract (demo isolated, live composition)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/hiring/HRHiringHomeView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/hiring/hiringComposition.ts").read_text(encoding="utf-8")
demo = (ROOT / "src/hr/features/hiring/hiringDemoData.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/hiring/hiringDemoGate.ts").read_text(encoding="utf-8")
tab = (ROOT / "app/hr/(tabs)/hiring.tsx").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("Hiring tab uses home view", "HRHiringHomeView" in tab)
check("Wordmark + EditorialHeading", "Wordmark" in view and "EditorialHeading" in view)
check("destinationAvailable on open + section filter", "destinationAvailable" in view)
check("summary + priority + upcoming + browse", all(x in view for x in ("SummaryStrip", "PriorityCard", "hrHiring.upcoming", "hrHiring.browse")))
check("one AmbientCard priority (not card grid)", view.count("<AmbientCard") == 1)
check("demo gated and prefixed", "hiringDemoEnabled" in gate and "__demo__" in gate)
check("demo source isolated", "HIRING_DEMO_SOURCE" in demo and "buildHiringDemoModel" in demo and "hr_hiring_demo_v1" in gate)
check("live compose from positions+interviews+priorities", "composeHiringHome" in comp and "positions:" in comp and "uniqueJobs" not in comp)
check("browse omits assessments", "canAssessments" not in comp and "omit" in comp.lower())
check("jobs/candidates/ranking go via /hr/jobs", "return '/hr/jobs'" in comp)
check("upcoming has no EN hardcoded Interview label", "'Interview'" not in comp and "'Feedback due'" not in comp)
check("demo ids never decision-shaped", "HIRING_DEMO_ID_PREFIX" in demo and "mobileApi" not in demo and "request<" not in demo)
check("no PrioritySectionList placeholder", "PrioritySectionList" not in view and "PrioritySectionList" not in tab)
keys = [
    "hrHiring.title",
    "hrHiring.demoBanner",
    "hrHiring.needsAttention",
    "hrHiring.browseCandidates",
    "hrHiring.statusOffer",
]
check("hrHiring keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-hiring-home: GREEN")
