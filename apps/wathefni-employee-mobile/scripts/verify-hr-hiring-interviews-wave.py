#!/usr/bin/env python3
"""Hiring + Candidates list + Interviews cream/honesty wave contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))

cand = (ROOT / "src/hr/features/recruiting/CandidatesQueueView.tsx").read_text(encoding="utf-8")
jobs = (ROOT / "src/hr/features/recruiting/JobsPositionsView.tsx").read_text(encoding="utf-8")
iview = (ROOT / "src/hr/features/recruiting/InterviewsQueueView.tsx").read_text(encoding="utf-8")
idetail = (ROOT / "src/hr/features/recruiting/InterviewDetailView.tsx").read_text(encoding="utf-8")
cream = (ROOT / "src/hr/features/recruiting/CreamQueueScreen.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/hiring/hiringComposition.ts").read_text(encoding="utf-8")
home = (ROOT / "src/hr/features/hiring/HRHiringHomeView.tsx").read_text(encoding="utf-8")
links = (ROOT / "src/hr/features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8")
api = (ROOT / "src/hr/api/mobile.ts").read_text(encoding="utf-8")
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")
routes = (ROOT / "src/hr/features/operations/routes.tsx").read_text(encoding="utf-8")
layout = (ROOT / "app/hr/_layout.tsx").read_text(encoding="utf-8")
jobs_route = (ROOT / "app/hr/jobs/index.tsx").read_text(encoding="utf-8")
cand_route = (ROOT / "app/hr/candidates/[appKey].tsx").read_text(encoding="utf-8")
caps = (ROOT / "src/hr/capabilities.ts").read_text(encoding="utf-8")
nav = (ROOT / "src/hr/navigation.ts").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("cream PageScreen + HrPushedNav shared", "PageScreen" in cream and "HrPushedNav" in cream and "ListRow" in cream)
check("CandidatesQueueView cream + position param", "CandidatesQueueView" in cand and "position" in cand and "requiresPosition" in cand)
check("JobsPositionsView opens scoped candidates", "/candidates?position=" in jobs)
check("Interviews cream list + detail", "InterviewsQueueView" in iview and "InterviewDetailView" in idetail)
check("notes send expected_updated_at + expected_version", "expected_updated_at" in idetail and "expected_version" in idetail)
check("notes stale codes handled inline", "stale_interview_notes" in idetail and "missing_expected_version" in idetail)
check("notes invalidate hiring+interviews caches", "hr-hiring-interviews" in idetail and "mobile-priorities" in idetail)
check("routes thin-wrap cream views", "CandidatesQueueView" in routes and "InterviewDetailView" in routes)
check("jobs stack + route registered", 'name="jobs/index"' in layout and "JobsPositionsView" in jobs_route)
check("hiring browse omits assessments", "canAssessments" not in home and "assessments" not in comp.split("browseKeysForCapabilities")[1].split("return keys")[0])
check("browseDestination jobs path", "return '/hr/jobs'" in comp)
check("assistant interview_id only", "interview_id" in links and "Never treat app_key" in links)
check("assistant ranking→jobs base", "ranking: '/hr/jobs'" in links)
check("assessments web-only", "assessments" in links and "WEB_ONLY_PAGES" in links)
check("API positions + candidates opts", "positions:" in api and "position?: string" in api)
check("normalize preserves requires_position", "requires_position" in norm and "normalizeCandidatesCollection" in norm)
check("destinationAvailable /jobs", "path === '/jobs'" in caps)
check("canonical parent /jobs → hiring", "p === '/jobs'" in nav)
check("schedule stays interviews list", "router.push('/hr/interviews'" in cand_route)

keys = [
    "hrCandidates.requiresPositionTitle",
    "hrCandidates.rankingUnavailableTitle",
    "hrJobs.title",
    "hrInterviews.staleTitle",
    "hrHiring.priorityReviewTitle",
    "hrHiring.browseRankingBody",
    "hrCandidate.scheduleInterview",
]
check("EN+AR recruiting honesty keys", all(k in en and k in ar for k in keys))
check("schedule copy not fake detail", "Open interviews" in en["hrCandidate.scheduleInterview"])
check("AR requires position present", "منصب" in ar["hrCandidates.requiresPositionTitle"])

print("hr-hiring-interviews-wave: GREEN")
