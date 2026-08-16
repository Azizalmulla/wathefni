#!/usr/bin/env python3
"""HR Document Reviews — needs_review compliance queue contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT.parents[1] / "wathefni-orchestrator"

queue = (ROOT / "src/hr/features/documents/HRDocumentReviewsQueueView.tsx").read_text(encoding="utf-8")
detail = (ROOT / "src/hr/features/documents/HRDocumentReviewDetailView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/documents/documentsComposition.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/documents/documentsDemoGate.ts").read_text(encoding="utf-8")
index = (ROOT / "app/hr/documents/index.tsx").read_text(encoding="utf-8")
detail_route = (ROOT / "app/hr/documents/[employeeKey]/[documentType].tsx").read_text(encoding="utf-8")
api = (ROOT / "src/hr/api/mobile.ts").read_text(encoding="utf-8")
types = (ROOT / "src/hr/api/types.ts").read_text(encoding="utf-8")
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")
config = (ROOT / "app.config.js").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
backend = (ORCH / "operator_mobile_data.py").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("queue route", "HRDocumentReviewsQueueView" in index)
check("detail route", "HRDocumentReviewDetailView" in detail_route)
check("default needs_review API", "status" in api and "needs_review" in api.split("documents:")[1].split("documentDetail")[0])
check("no submitted_at invent", "submitted_at" not in types.split("export type DocumentReview")[1].split("export type Onboarding")[0])
check("normalize has expiry/confidence", "days_until_expiry" in norm and "extraction_confidence" in norm and "submitted_at" not in norm.split("normalizeDocument")[1].split("normalizeOnboardingItem")[0])
check("preview before decide", "openAuthenticatedFile" in detail or "openPreview" in detail)
check("mark reviewed + expected_status", "markReviewed" in detail and "expected_status" in detail)
check("editorial lead + unboxed record facts", "expiryLead" in detail and "sectionRecord" in detail)
check("ConfirmationSheet outside scroll", detail.rfind("ConfirmationSheet") > detail.rfind("PageScrollView"))
check("no Send Reminder", "remind" not in detail.lower() or "Last reminded" in detail or "lastReminded" in detail)
check("onboarding fallback routes to onboarding", "/onboarding/" in queue and "source === 'onboarding'" in queue)
check("demo gated", "documentsDemoEnabled" in gate and "__demo_doc_emp__" in gate)
check("demo has compliance + onboarding fallback", "onboardingFallback" in comp and "compliance" in comp)
check("app.config documentsDemo", "documentsDemo:" in config and "EXPO_PUBLIC_HR_DOCUMENTS_DEMO" in config)
check("backend default needs_review", 'or "needs_review"' in backend and "mobile_document_reviews" in backend)
check("priorities emit document_reviews", '"type": "document_reviews"' in backend)
check("no onboarding fan when compliance", "Do not fan onboarding" in backend or "never surface non-needs_review" in backend)

keys = [
    "hrDocuments.title",
    "hrDocuments.queueHint",
    "hrDocuments.markReviewed",
    "hrDocuments.onboardingFallbackHint",
    "hrMore.documents",
]
check("hrDocuments keys EN+AR", all(k in en and k in ar for k in keys))
check("More label is Document reviews", en.get("hrMore.documents") == "Document reviews")
print("hr-documents-reviews: GREEN")
