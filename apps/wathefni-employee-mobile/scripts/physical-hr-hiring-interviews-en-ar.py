#!/usr/bin/env python3
"""Physical EN + AR copy/honesty pass for Hiring + Candidates list + Interviews."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))

home = (ROOT / "src/hr/features/hiring/HRHiringHomeView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/hiring/hiringComposition.ts").read_text(encoding="utf-8")
cand = (ROOT / "src/hr/features/recruiting/CandidatesQueueView.tsx").read_text(encoding="utf-8")
iview = (ROOT / "src/hr/features/recruiting/InterviewsQueueView.tsx").read_text(encoding="utf-8")
idetail = (ROOT / "src/hr/features/recruiting/InterviewDetailView.tsx").read_text(encoding="utf-8")
jobs = (ROOT / "src/hr/features/recruiting/JobsPositionsView.tsx").read_text(encoding="utf-8")

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(("PASS" if ok else "FAIL"), name + (f" · {detail}" if detail else ""))
    if not ok:
        failed += 1


def arabic(s: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in s)


keys = [
    "hrHiring.statusInterview",
    "hrHiring.statusFeedbackDue",
    "hrHiring.priorityReviewTitle",
    "hrHiring.priorityRoleBody",
    "hrHiring.browseRankingBody",
    "hrCandidates.requiresPositionTitle",
    "hrCandidates.requiresPositionBody",
    "hrCandidates.rankingUnavailableTitle",
    "hrJobs.title",
    "hrInterviews.title",
    "hrInterviews.staleTitle",
    "hrInterviews.staleBody",
    "hrInterviews.notesPlaceholder",
    "hrCandidate.scheduleInterview",
]
check("EN/AR key parity", all(k in en and k in ar for k in keys))

for k in keys:
    check(f"AR arabic · {k}", arabic(ar[k]), ar[k][:48])

check("EN requires_position calm", "Choose a position" in en["hrCandidates.requiresPositionTitle"])
check("EN schedule honest list", "Open interviews" == en["hrCandidate.scheduleInterview"])
check("no EN Interview hardcode in compose", "'Interview'" not in comp and "'Feedback due'" not in comp)
check("priority uses titleKey", "titleKey" in home and "priority.titleKey" in home)
check("candidates cream + requiresPosition", "PageScreen" in cand or "CreamQueueScreen" in cand)
check("requiresPosition wired", "requiresPosition" in cand and "hrCandidates.requiresPositionTitle" in cand)
check("interviews cream list/detail", "CreamQueueScreen" in iview and "HrPushedNav" in idetail)
check("jobs cream", "CreamQueueScreen" in jobs or "PageScreen" in jobs)
check("notes tokens", "expected_updated_at" in idetail and "expected_version" in idetail)
check("stale inline not whole-page blank", "notesError" in idetail and "staleTitle" in idetail)

if failed:
    print(f"hr-hiring-interviews-en-ar-physical: FAIL ({failed})")
    sys.exit(1)
print("hr-hiring-interviews-en-ar-physical: PASS")
