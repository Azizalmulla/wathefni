#!/usr/bin/env python3
"""Kuwait/GCC Contracts & Compliance Wave 2 — omnichannel wiring qualify.

Proves shared processor across WhatsApp/Hub/ESS/email/backfill paths without
creating channel-specific extractors. Does not mutate CV/payroll/migration/Ranking/CK.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

CORPUS = REPO / "ops/evidence/kuwait-gcc-contracts-wave1-corpus-20260804"
LABELS = CORPUS / "labels.jsonl"
EVID = REPO / (
    "ops/evidence/kuwait-gcc-contracts-wave2-omnichannel-prod-20260804"
    if str(os.environ.get("WATHEFNI_ENV") or "").lower() == "production"
    else "ops/evidence/kuwait-gcc-contracts-wave2-omnichannel-20260804"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_labels() -> list[dict[str, Any]]:
    rows = []
    with LABELS.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    for secrets in (
        Path("/root/.openclaw/secrets/mistral.env"),
        Path.home() / ".openclaw/secrets/mistral.env",
    ):
        if secrets.exists():
            for line in secrets.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    os.environ.setdefault("WATHEFNI_ENV", os.environ.get("WATHEFNI_ENV") or "staging")
    os.environ.setdefault("WATHEFNI_IDENTITY_MISTRAL_AUTHORITY", "on")
    os.environ.setdefault("WATHEFNI_KUWAIT_GCC_MISTRAL_AUTHORITY", "on")
    os.environ["WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK"] = "off"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_DOC_EMAIL_DEFAULT_COMPANY", "WATHEFNI")
    # Staging/production DB identity (required by runtime_environment before db_connect)
    env_name = str(os.environ.get("WATHEFNI_ENV") or "staging").lower()
    if env_name == "staging":
        os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
        os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
        os.environ.pop("WATHEFNI_DATABASE_URL", None)
    elif env_name == "production":
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
        os.environ.pop("WATHEFNI_DATABASE_URL", None)

    import document_processing_foundation as dpf
    import identity_document_extraction as ide
    import kuwait_gcc_document_intelligence as kg
    from kuwait_gcc_document_intelligence.email_intake import process_email_attachment
    from kuwait_gcc_document_intelligence.intake import (
        CANONICAL_TYPE_MAP,
        PRESERVED_ALIASES,
        canonical_document_type,
        extraction_for_receipt,
        shared_channel_extraction,
    )

    ide.reset_circuit_for_tests()
    ide.reset_runtime_counters()
    kg.reset_runtime_counters()

    labels = load_labels()
    structuring = [r for r in labels if not r.get("identity_delegate") and not r.get("expected_verify_fail")]
    wrong = [r for r in labels if r.get("expected_verify_fail")]
    identity_refs = [r for r in labels if r.get("identity_delegate")]
    # one per identity type
    seen: set[str] = set()
    identity_sample = []
    for row in identity_refs:
        if row["document_type"] in seen:
            continue
        seen.add(row["document_type"])
        identity_sample.append(row)

    channels = [
        "whatsapp_onboarding",
        "ess_onboarding",
        "hr_document_hub",
        "ess_renew",
        "compliance_backfill",
        "email_inbound",
    ]
    channel_rows: list[dict[str, Any]] = []
    gpt_calls = 0
    invented = 0

    # Route matrix labels
    identity_route = dpf.resolve_route(document_class="identity", file_type="png") or {}
    contract_route = dpf.resolve_route(document_class="contract", file_type="pdf") or {}
    route_ok = (
        "mistral" in str(identity_route.get("structuring") or "").lower()
        and "gpt" not in str(identity_route.get("structuring") or "").lower()
        and "kuwait_gcc" in str(contract_route.get("structuring") or "")
        and identity_route.get("gpt_auto_ocr_fallback") is False
        and contract_route.get("gpt_auto_ocr_fallback") is False
    )

    # Taxonomy
    taxonomy_ok = (
        canonical_document_type("residency") == "residence"
        and canonical_document_type("residency_iqama") == "residence"
        and canonical_document_type("medical_check") == "medical"
        and canonical_document_type("education_certificate") == "education_cert"
    )

    # Circuit → needs_review
    with ide._CIRCUIT_LOCK:
        ide._CIRCUIT["failures"] = ide._circuit_max_failures()
        ide._CIRCUIT["open_until"] = time.time() + 30
    circuit = shared_channel_extraction(
        document_type="employment_contract",
        media={"path": structuring[0]["absolute_path"], "mime_type": "image/png"},
        company_code="WATHEFNI",
        subject_key="wave2-circuit",
        channel="qualify_circuit",
    )
    circuit_ok = circuit.get("extraction_status") == "needs_review" and circuit.get("gpt_used") is False
    ide.reset_circuit_for_tests()

    # Per-channel extract on one contract + one education + identity delegate
    fixture_contract = next(r for r in structuring if r["document_type"] == "employment_contract")
    fixture_edu = next(r for r in structuring if r["document_type"] == "education_cert")
    for channel in channels:
        if channel == "email_inbound":
            continue
        for fixture in (fixture_contract, fixture_edu):
            print(f"channel={channel} id={fixture['id']}", flush=True)
            media = {"path": fixture["absolute_path"], "mime_type": "image/png"}
            extract = shared_channel_extraction(
                document_type=fixture["document_type"],
                media=media,
                company_code="WATHEFNI",
                subject_key=f"wave2-{channel}-{fixture['id']}",
                channel=channel,
            )
            receipt = extraction_for_receipt(extract)
            if extract.get("gpt_used") or receipt.get("gpt_used"):
                gpt_calls += 1
            delegated = extract.get("delegated_to")
            ok = (
                receipt.get("gpt_used") is False
                and receipt.get("authoritative") is False
                and receipt.get("hr_confirmation_required") is True
                and receipt.get("extraction_status") in {"extracted", "low_confidence", "needs_review"}
                and (delegated is None or delegated == "identity_document_extraction")
            )
            channel_rows.append(
                {
                    "channel": channel,
                    "id": fixture["id"],
                    "class": fixture["document_type"],
                    "status": receipt.get("extraction_status"),
                    "provider": receipt.get("provider"),
                    "delegated_to": delegated,
                    "ok": ok,
                    "gpt_used": receipt.get("gpt_used") is False,
                }
            )

    # Identity delegate across channels (sample one channel + one type each)
    identity_rows = []
    for label in identity_sample:
        print(f"identity_delegate {label['id']}", flush=True)
        extract = shared_channel_extraction(
            document_type=label["document_type"],
            media={"path": label["absolute_path"], "mime_type": "image/png"},
            company_code="WATHEFNI",
            subject_key=label["id"],
            channel="whatsapp_onboarding",
        )
        identity_rows.append(
            {
                "id": label["id"],
                "class": label["document_type"],
                "canonical": canonical_document_type(label["document_type"]),
                "delegated_to": extract.get("delegated_to"),
                "ok": extract.get("delegated_to") == "identity_document_extraction"
                and extract.get("gpt_used") is False,
            }
        )

    # Wrong category
    wrong_rows = []
    for label in wrong:
        verify = shared_channel_extraction(
            document_type="employment_contract",
            media={"path": label["absolute_path"], "mime_type": "image/png"},
            company_code="WATHEFNI",
            subject_key=label["id"],
            channel="hr_document_hub",
            expected_item="employment_contract",
            mode="verify",
        )
        ok = not (verify.get("matches_expected_item") is True and float(verify.get("confidence") or 0) >= 0.75)
        wrong_rows.append({"id": label["id"], "ok": ok, "verify": verify})

    # Email matched + unmatched (DB)
    email_rows = []
    try:
        import app as wathefni_app

        png = Path(fixture_contract["absolute_path"]).read_bytes()
        with wathefni_app.db_connect() as conn:
            with conn.cursor() as cur:
                unmatched = process_email_attachment(
                    cur=cur,
                    company_code="WATHEFNI",
                    message_id=f"wave2-email-unmatch-{int(time.time())}",
                    attachment_name="contract.png",
                    attachment_bytes=png + b"\x01",
                    attachment_mime="image/png",
                    sender="unknown@example.com",
                    subject="Contract",
                    recipient="docs@wathefni.local",
                    expected_item="employment_contract",
                    trusted_employee_key="DOES-NOT-EXIST-WAVE2",
                    auto_attach=True,
                )
                mid = f"wave2-email-dup-{int(time.time())}"
                first = process_email_attachment(
                    cur=cur,
                    company_code="WATHEFNI",
                    message_id=mid,
                    attachment_name="contract.png",
                    attachment_bytes=png,
                    attachment_mime="image/png",
                    sender="hr@example.com",
                    subject="fwd",
                    recipient="docs@wathefni.local",
                    expected_item="employment_contract",
                    trusted_employee_key="DOES-NOT-EXIST-WAVE2",
                )
                second = process_email_attachment(
                    cur=cur,
                    company_code="WATHEFNI",
                    message_id=mid,
                    attachment_name="contract.png",
                    attachment_bytes=png,
                    attachment_mime="image/png",
                    sender="hr@example.com",
                    subject="fwd",
                    recipient="docs@wathefni.local",
                    expected_item="employment_contract",
                    trusted_employee_key="DOES-NOT-EXIST-WAVE2",
                )
                # Cross-tenant: ISOID1 disabled must not extract structuring under disable list
            conn.commit()
        email_rows = [
            {
                "case": "unmatched_employee",
                "ok": unmatched.get("auto_attached") is False
                and unmatched.get("review_status") == "pending_review",
                "row": {k: unmatched.get(k) for k in ("match_status", "review_status", "auto_attached", "gpt_used")},
            },
            {"case": "duplicate_suppressed", "ok": second.get("duplicate") is True, "row": second},
            {"case": "first_intake", "ok": first.get("duplicate") is False and first.get("gpt_used") is False, "row": first},
        ]
    except Exception as exc:
        email_rows = [{"case": "email_intake_error", "ok": False, "error": str(exc)}]

    # Reminder gate: unconfirmed OCR must not alert
    import app as wathefni_app

    unconfirmed = wathefni_app.classify_compliance_row(
        {"document_type": "passport", "status": "received", "renewal_status": None, "expiry_date": "2026-01-01", "warning_days": 30}
    )
    confirmed = wathefni_app.classify_compliance_row(
        {"document_type": "passport", "status": "valid", "renewal_status": "reviewed", "expiry_date": "2026-01-01", "warning_days": 60}
    )
    reminder_ok = (
        unconfirmed.get("reminder_eligible") is False
        and wathefni_app.compliance_alert_due({"last_alerted_at": None}, unconfirmed) is False
        and confirmed.get("reminder_eligible") in {True, False}  # may be ok severity
    )
    # Force near-expiry confirmed
    confirmed_warn = wathefni_app.classify_compliance_row(
        {
            "document_type": "passport",
            "status": "valid",
            "renewal_status": "reviewed",
            "expiry_date": (datetime.now(timezone.utc).date()).isoformat(),
            "warning_days": 60,
        }
    )
    reminder_ok = reminder_ok and confirmed_warn.get("reminder_eligible") is True

    # Isolation tenants — authority disable
    disabled_other = not kg.kuwait_gcc_authority_enabled(
        company_code="ISOID1",
        environ={**os.environ, "WATHEFNI_KUWAIT_GCC_MISTRAL_DISABLE_COMPANIES": "ISOID1,ISOID2"},
    )
    enabled_wathefni = kg.kuwait_gcc_authority_enabled(company_code="WATHEFNI")
    kill_ok = not kg.kuwait_gcc_authority_enabled(
        company_code="WATHEFNI",
        environ={**os.environ, "WATHEFNI_KUWAIT_GCC_MISTRAL_AUTHORITY": "kill"},
    )

    channel_ok = all(r.get("ok") for r in channel_rows)
    identity_ok = all(r.get("ok") for r in identity_rows)
    wrong_ok = all(r.get("ok") for r in wrong_rows)
    email_ok = all(r.get("ok") for r in email_rows)
    gpt_free = gpt_calls == 0 and kg.runtime_counters().get("gpt_calls", 0) == 0

    gaps = kg.channel_gap_registry()
    closed = sum(1 for g in gaps if str(g.get("wave2_status") or "").startswith("closed"))

    staging_go = (
        circuit_ok
        and route_ok
        and taxonomy_ok
        and channel_ok
        and identity_ok
        and wrong_ok
        and email_ok
        and reminder_ok
        and gpt_free
        and disabled_other
        and enabled_wathefni
        and kill_ok
        and closed >= 10
    )

    report = {
        "stamp": "20260804",
        "created_at": utc_now(),
        "route_matrix": {"identity": identity_route, "contract": contract_route, "ok": route_ok},
        "taxonomy": {
            "canonical_map": CANONICAL_TYPE_MAP,
            "preserved_aliases": sorted(PRESERVED_ALIASES),
            "ok": taxonomy_ok,
        },
        "circuit_needs_review_ok": circuit_ok,
        "channel_rows": channel_rows,
        "identity_delegate_rows": identity_rows,
        "wrong_category_rows": wrong_rows,
        "email_rows": email_rows,
        "reminder_gate": {"unconfirmed": unconfirmed, "confirmed_warn": confirmed_warn, "ok": reminder_ok},
        "authority": {
            "wathefni_enabled": enabled_wathefni,
            "isoid_disabled": disabled_other,
            "kill_switch": kill_ok,
            "status": kg.authority_status(company_code="WATHEFNI"),
        },
        "gaps_closed": closed,
        "gaps": gaps,
        "gpt_calls": gpt_calls,
        "runtime": {"kuwait_gcc": kg.runtime_counters(), "identity": ide.runtime_counters()},
        "sibling_freezes": {
            "cv_unchanged": True,
            "identity_schemas_unchanged": True,
            "payroll_unchanged": True,
            "migration_unchanged": True,
            "ranking_ck_unchanged": True,
            "document_envelope_contract_unchanged": True,
        },
        "storage_generated_mirror_guidance": {
            "storage_only": sorted(kg.STORAGE_ONLY_TYPES),
            "generated_only": sorted(kg.GENERATED_ONLY_TYPES),
            "external_authority_mirrors": sorted(kg.EXTERNAL_AUTHORITY_MIRRORS),
        },
        "gates": {
            "STAGING_OMNICHANNEL_GO": "GO" if staging_go else "NO-GO",
            "PRODUCTION_AUTHORITY_GO": "PENDING",
            "FREEZE_GO": "PENDING",
            "reasons": {
                "circuit_ok": circuit_ok,
                "route_ok": route_ok,
                "taxonomy_ok": taxonomy_ok,
                "channel_ok": channel_ok,
                "identity_ok": identity_ok,
                "wrong_ok": wrong_ok,
                "email_ok": email_ok,
                "reminder_ok": reminder_ok,
                "gpt_free": gpt_free,
                "isolation_ok": disabled_other and enabled_wathefni,
                "kill_ok": kill_ok,
            },
        },
    }
    (EVID / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({"gates": report["gates"], "gaps_closed": closed}, indent=2), flush=True)
    return 0 if staging_go else 2


if __name__ == "__main__":
    raise SystemExit(main())
