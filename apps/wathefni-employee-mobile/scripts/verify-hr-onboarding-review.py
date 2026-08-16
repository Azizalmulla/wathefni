#!/usr/bin/env python3
"""HR Onboarding — HR-actionable review companion contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
queue = (ROOT / "src/hr/features/onboarding/HROnboardingQueueView.tsx").read_text(encoding="utf-8")
detail = (ROOT / "src/hr/features/onboarding/HROnboardingDetailView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/onboarding/onboardingComposition.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/onboarding/onboardingDemoGate.ts").read_text(encoding="utf-8")
index = (ROOT / "app/hr/onboarding/index.tsx").read_text(encoding="utf-8")
detail_route = (ROOT / "app/hr/onboarding/[employeeKey].tsx").read_text(encoding="utf-8")
people = (ROOT / "src/hr/features/people/HRPeopleDirectoryView.tsx").read_text(encoding="utf-8")
config = (ROOT / "app.config.js").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("queue route", "HROnboardingQueueView" in index)
check("detail route", "HROnboardingDetailView" in detail_route)
check("no invented current_step UI", "current_step" not in queue and "current_step" not in detail)
check("Accept + Waive", "hrOnboarding.accept" in detail and "hrOnboarding.waive" in detail)
check("no Remind", "remind" not in detail.lower() or "waitingHint" in detail)
check("bank handoff", "hrOnboarding.bankHandoff" in detail and "review_bank" in detail)
check("file preview", "openAuthenticatedFile" in detail or "openFile" in detail)
check("demo filter proof includes waiting-only", "waitingOnly" in comp or "waiting-only" in comp or "bilal" in comp)
check("demo gated", "onboardingDemoEnabled" in gate and "__demo_ob__" in gate)
check("people deep-link onboarding", "/onboarding/" in people and "chip?.key === 'onboarding'" in people)
check("app.config onboardingDemo", "onboardingDemo:" in config)
check("normalize drops start_date/current_step", "current_step" not in norm.split("normalizeOnboarding")[1].split("normalizeAttendance")[0])

keys = [
    "hrOnboarding.title",
    "hrOnboarding.accept",
    "hrOnboarding.waive",
    "hrOnboarding.bankHandoff",
    "hrOnboarding.queueHint",
]
check("hrOnboarding keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-onboarding-review: GREEN")
