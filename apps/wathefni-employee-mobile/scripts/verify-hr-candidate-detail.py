#!/usr/bin/env python3
"""HR Candidate detail honesty + cream migration contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/recruiting/CandidateReviewView.tsx").read_text(encoding="utf-8")
route = (ROOT / "app/hr/candidates/[appKey].tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/recruiting/candidateComposition.ts").read_text(encoding="utf-8")
backend = (
    Path(__file__).resolve().parents[3]
    / "wathefni-orchestrator/operator_mobile_data.py"
).read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("cream PageScreen + HrPushedNav", "PageScreen" in view and "HrPushedNav" in view)
check("no legacy WorkspaceHeader/plum stack", "WorkspaceHeader" not in view and "plum" not in view.lower() and 'tone="sage"' not in view and 'tone="lilac"' not in view)
check("stage tone from real stage", "candidateStageTone" in view and 'tone="info"' not in view)
check("no raw appKey chrome", "app_key.slice" not in view and "#{review" not in view)
check("localized CV empty", "hrCandidate.cvUnavailable" in view and "No CV available" not in view)
check("offer rendered when present", "hasRenderableOffer" in view and "hrCandidate.sectionOffer" in view)
check("already_decided wired in route", "already_decided" in route and "candidateIsTerminal" in route)
check("confirm action + consequence localized", "hrCandidate.shortlist" in route and "localizeCandidateConsequence" in route)
check("safe-back preserved", "useHrSafeBack" in route)
check("SOD invalidation preserved", "mobile-priorities" in route and "['candidate', appKey]" in route)
check("composition helpers present", "localizeCandidateConsequence" in comp and "candidateStageTone" in comp)
check(
    "rankings honesty surfaces job_required",
    "ranking_unavailable" in backend and "requires_position" in backend and "job_required" in backend,
)

keys = [
    "hrCandidate.eyebrow",
    "hrCandidate.cvUnavailable",
    "hrCandidate.shortlist",
    "hrCandidate.reject",
    "hrCandidate.hire",
    "hrCandidate.alreadyDecided",
    "hrCandidate.consequenceShortlist",
    "hrCandidate.consequenceReject",
    "hrCandidate.consequenceHire",
    "hrCandidate.offerStatus",
    "hrCandidate.sectionOffer",
]
check("hrCandidate keys EN+AR", all(k in en and k in ar for k in keys))

print("hr-candidate-detail: GREEN")
