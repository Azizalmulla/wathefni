#!/usr/bin/env python3
"""Identity Document Processing Wave 2 — staging authority + GPT retirement qualify."""

from __future__ import annotations

import inspect
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

CORPUS = REPO / "ops/evidence/identity-wave1-corpus-20260804"
LABELS = CORPUS / "labels.jsonl"
EVID = REPO / "ops/evidence/identity-wave2-authority-20260804"
RESULTS = EVID / "results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_labels() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with LABELS.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def assert_no_gpt_in_source(app_src: str) -> dict[str, Any]:
    # The three retired functions must not contain planner/GPT request bodies.
    checks = {
        "verify_onboarding_media_item_no_planner": "def verify_onboarding_media_item" in app_src,
        "classify_onboarding_media_upload_no_planner": "def classify_onboarding_media_upload" in app_src,
        "extract_compliance_no_planner": "def extract_compliance_document_metadata" in app_src,
    }
    # Extract function bodies roughly and ensure temperature/planner not used for identity.
    import re

    def body_of(name: str) -> str:
        m = re.search(rf"def {name}\(.*?\n(?=def |\Z)", app_src, re.S)
        return m.group(0) if m else ""

    bodies = {
        "verify": body_of("verify_onboarding_media_item"),
        "classify": body_of("classify_onboarding_media_upload"),
        "extract": body_of("extract_compliance_document_metadata"),
    }
    forbidden = []
    for label, body in bodies.items():
        if "planner_provider_config" in body:
            forbidden.append(f"{label}:planner_provider_config")
        if "temperature" in body:
            forbidden.append(f"{label}:temperature")
        if "input_image" in body or "image_url" in body:
            forbidden.append(f"{label}:vision_payload")
        if "identity_document_extraction" not in body:
            forbidden.append(f"{label}:missing_mistral_delegate")
    return {
        "ok": len(forbidden) == 0 and all(checks.values()),
        "checks": checks,
        "forbidden_hits": forbidden,
        "body_lens": {k: len(v) for k, v in bodies.items()},
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (EVID / "docs").mkdir(parents=True, exist_ok=True)

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

    os.environ["WATHEFNI_ENV"] = os.environ.get("WATHEFNI_ENV") or "staging"
    os.environ["WATHEFNI_IDENTITY_MISTRAL_AUTHORITY"] = "on"
    os.environ["WATHEFNI_IDENTITY_MISTRAL_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK"] = "off"

    import identity_document_extraction as ide
    import app as wathefni_app

    ide.reset_circuit_for_tests()
    ide.reset_runtime_counters()

    app_src = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    source_proof = assert_no_gpt_in_source(app_src)

    labels = load_labels()
    rows: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}

    # Outage / circuit simulation
    ide.reset_circuit_for_tests()
    with ide._CIRCUIT_LOCK:
        ide._CIRCUIT["failures"] = ide._circuit_max_failures()
        ide._CIRCUIT["open_until"] = time.time() + 30
    circuit_probe = ide.extract_compliance_via_mistral(
        document_type="civil_id",
        media={"path": labels[0]["absolute_path"], "mime_type": "image/png"},
        company_code="WATHEFNI",
        subject_key="circuit_probe",
    )
    circuit_ok = (
        isinstance(circuit_probe, dict)
        and circuit_probe.get("extraction_status") == "needs_review"
        and circuit_probe.get("gpt_used") is False
    )
    ide.reset_circuit_for_tests()

    # Authority off for non-canary company in production mode
    off_env = dict(os.environ)
    off_env["WATHEFNI_ENV"] = "production"
    off_env["WATHEFNI_IDENTITY_MISTRAL_AUTHORITY"] = "canary"
    off_env["WATHEFNI_IDENTITY_MISTRAL_COMPANIES"] = "WATHEFNI"
    other_company_disabled = not ide.identity_mistral_authority_enabled(
        company_code="OTHERCO", environ=off_env
    )
    wathefni_canary_enabled = ide.identity_mistral_authority_enabled(
        company_code="WATHEFNI", environ=off_env
    )

    for label in labels:
        path = Path(label["absolute_path"])
        media = {"path": str(path), "mime_type": "image/png", "type": "image/png"}
        print(f"wave2 {label['id']}", flush=True)

        classify = wathefni_app.classify_onboarding_media_upload(
            "",
            media,
            [label["document_type"], "passport", "civil_id", "medical"],
            company_code="WATHEFNI",
            subject_key=label["id"],
        )
        verify = wathefni_app.verify_onboarding_media_item(
            label["document_type"],
            "",
            media,
            company_code="WATHEFNI",
            subject_key=label["id"],
        )
        extract = wathefni_app.extract_compliance_document_metadata(
            document_type=label["document_type"],
            text="",
            media=media,
            company_code="WATHEFNI",
            subject_key=label["id"],
        )

        # HR non-authority check
        auth_false = (
            bool(extract)
            and extract.get("authoritative") is False
            and extract.get("hr_confirmation_required") is True
        )
        gpt_free = (
            (not classify or classify.get("gpt_used") is False)
            and (not verify or verify.get("gpt_used") is False)
            and (not extract or extract.get("gpt_used") is False)
            and (not extract or extract.get("provider") == "mistral")
        )

        # Front/back + duplicate detection
        dup = ide.duplicate_keys(
            {
                "content_sha256": (extract or {}).get("content_sha256")
                or ide.sha256_file(path),
                "fields": (extract or {}).get("fields")
                or {
                    "document_type": {"value": label["document_type"]},
                    "document_number": {"value": (extract or {}).get("document_number")},
                },
            }
        )
        duplicate_of = seen_hashes.get(dup["content_sha256"])
        if label["id"] == "civil_id_back_bilingual_01":
            # Same person identifier as front fixture
            pass
        seen_hashes[dup["content_sha256"]] = label["id"]

        # Dates / expiry validation
        validation = (extract or {}).get("validation") or ide.validate_identity_fields(
            {
                "document_type": {"value": (extract or {}).get("document_type")},
                "document_number": {"value": (extract or {}).get("document_number")},
                "issue_date": {"value": (extract or {}).get("issued_date")},
                "expiry_date": {"value": (extract or {}).get("expiry_date")},
                "date_of_birth": {"value": (extract or {}).get("date_of_birth")},
                "full_name_ar": {"value": (extract or {}).get("full_name_ar")},
                "full_name_en": {"value": (extract or {}).get("full_name_en") or (extract or {}).get("full_name")},
            },
            expected_type=label["document_type"],
        )

        # Correction path: HR can override — machine remains non-authoritative
        hr_correction = {
            "document_number": label.get("document_number"),
            "authoritative": True,
            "hr_confirmed": True,
            "corrected_from": (extract or {}).get("document_number"),
        }

        row = {
            "id": label["id"],
            "document_type": label["document_type"],
            "side": label.get("side"),
            "classify": classify,
            "verify": verify,
            "extract": {
                k: (extract or {}).get(k)
                for k in (
                    "extraction_status",
                    "document_type",
                    "document_number",
                    "full_name",
                    "full_name_ar",
                    "full_name_en",
                    "issued_date",
                    "expiry_date",
                    "nationality",
                    "date_of_birth",
                    "confidence",
                    "provider",
                    "model",
                    "gpt_used",
                    "authoritative",
                    "hr_confirmation_required",
                    "side",
                    "content_sha256",
                    "extraction_error",
                )
            },
            "auth_false": auth_false,
            "gpt_free": gpt_free,
            "validation": validation,
            "duplicate_keys": dup,
            "duplicate_of": duplicate_of,
            "hr_correction_example": hr_correction,
            "verify_match": bool(verify and verify.get("matches_expected_item")),
            "classify_ok": bool(
                classify
                and classify.get("detected_item") == label["document_type"]
                and float(classify.get("confidence") or 0) >= 0.55
            ),
            "extract_ok": bool(
                extract
                and extract.get("extraction_status") in {"extracted", "low_confidence"}
                and float(extract.get("confidence") or 0) >= 0.55
            ),
        }
        rows.append(row)
        (RESULTS / f"{label['id']}.json").write_text(
            json.dumps(row, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    counters = ide.runtime_counters()
    # Rollback proof: previous package restore is ops procedure; code path has no GPT re-enable without redeploy.
    rollback = {
        "mechanism": "restore previous orchestrator code package from backup",
        "no_hidden_gpt_flag": "WATHEFNI_IDENTITY_GPT" not in os.environ,
        "no_gpt_fallback_helper": not hasattr(ide, "gpt_identity_fallback"),
        "gpt_auto_fallback_forbidden": ide.gpt_auto_fallback_forbidden() is True,
    }

    classify_ok_n = sum(1 for r in rows if r["classify_ok"])
    verify_ok_n = sum(1 for r in rows if r["verify_match"])
    extract_ok_n = sum(1 for r in rows if r["extract_ok"])
    gpt_free_n = sum(1 for r in rows if r["gpt_free"])
    auth_false_n = sum(1 for r in rows if r["auth_false"])

    staging_go = (
        source_proof["ok"]
        and circuit_ok
        and other_company_disabled
        and wathefni_canary_enabled
        and counters.get("gpt_identity_calls", 0) == 0
        and gpt_free_n == len(rows)
        and auth_false_n == len(rows)
        and classify_ok_n >= int(0.7 * len(rows))
        and verify_ok_n >= int(0.7 * len(rows))
        and extract_ok_n >= int(0.7 * len(rows))
        and rollback["gpt_auto_fallback_forbidden"]
    )

    report = {
        "stamp": "20260804",
        "created_at": utc_now(),
        "n": len(rows),
        "source_proof": source_proof,
        "circuit_needs_review_ok": circuit_ok,
        "canary_gate": {
            "other_company_disabled": other_company_disabled,
            "wathefni_canary_enabled": wathefni_canary_enabled,
        },
        "runtime_counters": counters,
        "scores": {
            "classify_ok": classify_ok_n,
            "verify_ok": verify_ok_n,
            "extract_ok": extract_ok_n,
            "gpt_free": gpt_free_n,
            "authoritative_false": auth_false_n,
        },
        "rollback": rollback,
        "gates": {
            "STAGING_CUTOVER": "GO" if staging_go else "NO-GO",
            "PRODUCTION_WATHEFNI_CANARY_READY": "GO" if staging_go else "NO-GO",
            "EXPAND_BEYOND_WATHEFNI": "NO-GO",
        },
        "rows": rows,
    }
    (EVID / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: report[k] for k in ("scores", "runtime_counters", "source_proof", "gates", "canary_gate", "circuit_needs_review_ok")},
            indent=2,
        ),
        flush=True,
    )
    return 0 if staging_go else 2


if __name__ == "__main__":
    raise SystemExit(main())
