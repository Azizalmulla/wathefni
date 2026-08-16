#!/usr/bin/env python3
"""Surgically patch foundation-green staging app.py with document-journey hooks only."""

from __future__ import annotations

from pathlib import Path
import sys

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/kw-doc-journey-staging/app.py.staging-base")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/kw-doc-journey-staging/app.py.patched")
LOCAL = Path(__file__).resolve().parents[1] / "app.py"
if not LOCAL.exists():
    LOCAL = Path("/Users/azizalmulla/Desktop/claw/wathefni-orchestrator/app.py")

src = BASE.read_text(encoding="utf-8")
local = LOCAL.read_text(encoding="utf-8")


def must_replace(hay: str, old: str, new: str, label: str) -> str:
    if old not in hay:
        raise SystemExit(f"missing anchor for {label}")
    count = hay.count(old)
    if count != 1:
        raise SystemExit(f"anchor for {label} matched {count} times (want 1)")
    return hay.replace(old, new, 1)


def slice_local(start_marker: str, end_marker: str) -> str:
    a = local.find(start_marker)
    if a < 0:
        raise SystemExit(f"local missing start {start_marker[:60]}")
    b = local.find(end_marker, a)
    if b < 0:
        raise SystemExit(f"local missing end {end_marker[:60]}")
    return local[a:b]


# 1) Schema hook after foundation
src = must_replace(
    src,
    """            import kuwait_first_client_foundation as _kw_foundation

            _kw_foundation.ensure_foundation_schema(cur)
            import interview_lifecycle as _interviews
""",
    """            import kuwait_first_client_foundation as _kw_foundation

            _kw_foundation.ensure_foundation_schema(cur)
            import kuwait_pilot_document_journey as _kw_doc_journey

            _kw_doc_journey.ensure_document_journey_schema(cur)
            import interview_lifecycle as _interviews
""",
    "schema_hook",
)

# 2) Dual-write + version registration
old_dual_start = '    if document_type in {"civil_id", "passport", "medical", "education_cert"}:'
old_dual_end = "\n\ndef find_candidate_application_for_file"
a = src.find(old_dual_start)
b = src.find(old_dual_end, a)
if a < 0 or b < 0:
    raise SystemExit("dual-write block not found")
new_dual = slice_local("    # Kuwait pilot: dual-write via canonical map", "\ndef find_candidate_application_for_file")
src = src[:a] + new_dual + src[b:]

# 3) Category-aware onboarding requiredness
old_seed = '''    cur.execute("SELECT item_id FROM onboarding_items WHERE employee_key=%s", (employee_key,))
    existing = {str(row["item_id"]) for row in cur.fetchall() if row.get("item_id")}
    seeded = 0
    for order, (item_id, label, category, item_type, required, owner) in enumerate(specs):
        if item_id in existing:
            continue
        document_type = item_id if item_type == "document" else None
        cur.execute(
            """
            INSERT INTO onboarding_items
                (employee_key, item_id, label, category, item_type, required, owner,
                 sort_order, document_type, status, raw_json, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s, now())
            """,
            (
                employee_key, item_id, label, category, item_type, bool(required), owner,
                order, document_type,
                Json(seed_meta),
            ),
        )
        seeded += cur.rowcount or 0
'''
new_seed = slice_local(
    "    # Category-aware requiredness for residence / work_permit",
    "    if seeded:",
)
src = must_replace(src, old_seed, new_seed, "seed_requiredness")

# 4) Labels / status wording
src = must_replace(
    src,
    """COMPLIANCE_DOC_LABELS = {
    "civil_id": "Civil ID",
    "passport": "Passport",
    "residency": "Residence permit",
    "residence": "Residence permit",
    "residency_iqama": "Residence permit (legacy id)",
    "work_permit": "Work Permit",
    "medical": "Medical Document",
    "education_cert": "Education Certificate",
}
# Five HR-facing buckets. Order matters: it is the order HR should work through.
COMPLIANCE_BUCKETS = ("expired", "expiring_soon", "missing", "needs_review", "valid")
COMPLIANCE_STATUS_LABELS = {
    "expired": "Expired",
    "expiring_soon": "Expiring soon",
    "missing": "Missing",
    "needs_review": "Needs review",
    "valid": "Valid",
}
""",
    """COMPLIANCE_DOC_LABELS = {
    "civil_id": "Civil ID",
    "passport": "Passport",
    "residency": "Residence",
    "residence": "Residence",
    "residency_iqama": "Residence (legacy id)",
    "work_permit": "Work permit",
    "employment_contract": "Employment contract",
    "medical": "Medical certificate",
    "education_cert": "Education certificate",
}
COMPLIANCE_DOC_LABELS_AR = {
    "civil_id": "البطاقة المدنية",
    "passport": "جواز السفر",
    "residency": "الإقامة",
    "residence": "الإقامة",
    "residency_iqama": "الإقامة (معرّف قديم)",
    "work_permit": "إذن العمل",
    "employment_contract": "عقد العمل",
    "medical": "الشهادة الطبية",
    "education_cert": "الشهادة التعليمية",
}
# Five HR-facing buckets. Order matters: it is the order HR should work through.
COMPLIANCE_BUCKETS = ("expired", "expiring_soon", "missing", "needs_review", "valid")
COMPLIANCE_STATUS_LABELS = {
    "expired": "Expired",
    "expiring_soon": "Expiring soon",
    "missing": "Missing",
    "needs_review": "Pending HR review",
    "valid": "HR reviewed",
    "pending_hr_review": "Pending HR review",
    "hr_reviewed": "HR reviewed",
    "rejected_reupload": "Rejected — re-upload required",
}
""",
    "labels",
)

# 5) mark_compliance_reviewed
a = src.find("def mark_compliance_reviewed")
b = src.find("\ndef extraction_field_values", a)
if a < 0 or b < 0:
    raise SystemExit("mark_compliance_reviewed not found")
new_mark = slice_local("def mark_compliance_reviewed", "\ndef extraction_field_values")
src = src[:a] + new_mark + src[b:]

# 6) documents feature upload_document
src = must_replace(
    src,
    """    "documents": {
        "dependency_mode": "any",
        "module_keys": ("onboarding", "compliance"),
        "actions": ("view", "download"),
    },
""",
    """    "documents": {
        "dependency_mode": "any",
        "module_keys": ("onboarding", "compliance"),
        "actions": ("view", "download", "upload_document"),
    },
""",
    "documents_actions",
)

# 7) App documents + renew + review routes
a = src.find('@app.get("/app/documents")\ndef app_documents')
b = src.find('@app.get("/app/documents/{file_id}")\ndef app_document_file', a)
if a < 0 or b < 0:
    raise SystemExit("app documents routes not found")
new_routes = slice_local(
    '@app.get("/app/documents")\ndef app_documents',
    '@app.get("/app/documents/{file_id}")\ndef app_document_file',
)
src = src[:a] + new_routes + src[b:]

# Safety gates
if 'document_type in {"civil_id", "passport", "medical", "education_cert"}' in src:
    raise SystemExit("hardcoded dual-write allowlist still present")
if "kuwait_pilot_document_journey" not in src:
    raise SystemExit("journey module not wired")
if '@app.post("/app/documents/renew")' not in src:
    raise SystemExit("renew route missing")
if "not PACI" not in src and "not PACI, MOI" not in src:
    raise SystemExit("legitimacy note missing")

OUT.write_text(src, encoding="utf-8")
print(f"wrote {OUT} bytes={OUT.stat().st_size}")
print("ok")
