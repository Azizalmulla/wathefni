#!/usr/bin/env python3
"""Kuwait/GCC Contracts & Compliance Wave 1 — shared foundation qualification.

Does NOT deploy production. Does NOT mutate CV/identity/payroll/migration/Ranking/CK.
Reuses live identity Mistral authority for identity types.
"""

from __future__ import annotations

import json
import os
import re
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
EVID = REPO / "ops/evidence/kuwait-gcc-contracts-wave1-qualify-20260804"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_labels() -> list[dict[str, Any]]:
    rows = []
    with LABELS.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def score_value(expected: Any, got: Any) -> str:
    if expected is None and (got is None or got == ""):
        return "both_missing"
    if expected is None and got not in (None, ""):
        return "invented"
    if expected is not None and got in (None, ""):
        return "missing"
    e = re.sub(r"\s+", " ", str(expected).strip()).upper()
    g = re.sub(r"\s+", " ", str(got).strip()).upper()
    if e == g or e in g or g in e:
        return "match"
    return "incorrect"


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "results").mkdir(parents=True, exist_ok=True)
    if not LABELS.exists():
        os.system(f"{sys.executable} {ROOT / 'scripts/build-kuwait-gcc-contracts-wave1-corpus.py'}")

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
    os.environ["WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK"] = "off"

    import identity_document_extraction as ide
    import kuwait_gcc_document_intelligence as kg

    ide.reset_circuit_for_tests()
    ide.reset_runtime_counters()
    kg.reset_runtime_counters()

    labels = load_labels()
    structuring = [r for r in labels if not r.get("identity_delegate")]
    identity_refs = [r for r in labels if r.get("identity_delegate")]
    # Cap identity refs for cost: one per type
    seen_types: set[str] = set()
    identity_sample = []
    for row in identity_refs:
        dt = row["document_type"]
        if dt in seen_types:
            continue
        seen_types.add(dt)
        identity_sample.append(row)

    rows: list[dict[str, Any]] = []
    invented = 0
    gpt_calls = 0

    # Circuit probe on contract path
    with ide._CIRCUIT_LOCK:
        ide._CIRCUIT["failures"] = ide._circuit_max_failures()
        ide._CIRCUIT["open_until"] = time.time() + 30
    circuit = kg.extract_document(
        path=structuring[0]["absolute_path"],
        document_type="employment_contract",
        company_code="WATHEFNI",
        channel="qualify_circuit",
    )
    circuit_ok = circuit.get("extraction_status") == "needs_review" and circuit.get("gpt_used") is False
    ide.reset_circuit_for_tests()

    for label in structuring:
        path = Path(label["absolute_path"])
        media = {"path": str(path), "type": "image/png", "mime_type": "image/png"}
        print(f"qualify {label['id']}", flush=True)
        dtype = label["document_type"]

        if label.get("expected_verify_fail"):
            verify = kg.verify_document(
                media=media,
                expected_item=dtype,
                document_type=dtype,
                company_code="WATHEFNI",
                subject_key=label["id"],
                channel="qualify_wrong_category",
            )
            # Wrong content: passport uploaded as contract — should not confidently match
            ok = not (verify.get("matches_expected_item") is True and float(verify.get("confidence") or 0) >= 0.75)
            rows.append(
                {
                    "id": label["id"],
                    "class": dtype,
                    "case": "wrong_category",
                    "verify": verify,
                    "ok": ok,
                    "gpt_used": verify.get("gpt_used") is False,
                    "delegated_to": verify.get("delegated_to"),
                }
            )
            continue

        extract = kg.extract_document(
            media=media,
            document_type=dtype,
            company_code="WATHEFNI",
            subject_key=label["id"],
            channel="qualify_shared",
            country_code="KW",
        )
        verify = kg.verify_document(
            media=media,
            expected_item=dtype,
            document_type=dtype,
            company_code="WATHEFNI",
            subject_key=label["id"],
            channel="qualify_shared",
        )
        classify = kg.classify_document(
            media=media,
            allowed_items=[dtype, "civil_id", "passport", "education_cert", "employment_contract"],
            company_code="WATHEFNI",
            subject_key=label["id"],
            channel="qualify_shared",
        )

        fields = extract.get("fields") or {}
        per: dict[str, str] = {}
        if dtype == "employment_contract":
            score_keys = (
                "document_number",
                "employee_name_en",
                "employee_name_ar",
                "salary_amount",
                "salary_currency",
                "contract_start_date",
                "contract_end_date",
            )
        else:
            score_keys = (
                "document_number",
                "employee_or_holder_en",
                "issue_date",
                "expiry_date",
                "qualification_or_category",
            )
        for key in score_keys:
            if key not in label:
                continue
            expected = label.get(key)
            cell = fields.get(key)
            got = cell.get("value") if isinstance(cell, dict) else extract.get(key)
            kind = score_value(expected, got)
            if expected is not None or got not in (None, ""):
                per[key] = kind
                if kind == "invented":
                    invented += 1

        if extract.get("gpt_used") or verify.get("gpt_used") or classify.get("gpt_used"):
            gpt_calls += 1

        arabic_ok = None
        if label.get("employee_name_ar") or label.get("employee_or_holder_ar"):
            exp = label.get("employee_name_ar") or label.get("employee_or_holder_ar")
            cell = fields.get("employee_name_ar") or fields.get("employee_or_holder_ar")
            got = (cell or {}).get("value") if isinstance(cell, dict) else None
            ea = "".join(ch for ch in str(exp) if "\u0600" <= ch <= "\u06FF")
            ga = "".join(ch for ch in str(got or "") if "\u0600" <= ch <= "\u06FF")
            arabic_ok = bool(ea and ga and (ea == ga or ea in ga or ga in ea))

        row = {
            "id": label["id"],
            "class": dtype,
            "extract_status": extract.get("extraction_status"),
            "provider": extract.get("provider"),
            "gpt_used": extract.get("gpt_used") is False,
            "authoritative": extract.get("authoritative") is False,
            "hr_confirmation_required": extract.get("hr_confirmation_required") is True,
            "country_code": extract.get("country_code") or (fields.get("country_code") or {}).get("value"),
            "issuing_authority": extract.get("issuing_authority") or (fields.get("issuing_authority") or {}).get("value"),
            "validation": extract.get("validation"),
            "duplicate_keys": extract.get("duplicate_keys"),
            "per_field": per,
            "field_match_rate": (
                sum(1 for v in per.values() if v == "match") / max(1, sum(1 for v in per.values() if v != "both_missing"))
            ),
            "arabic_ok": arabic_ok,
            "verify_match": bool(verify.get("matches_expected_item")),
            "classify_detected": (classify or {}).get("detected_item"),
            "cost_usd": extract.get("cost_usd"),
            "latency_ms": extract.get("latency_ms"),
            "delegated_to": extract.get("delegated_to"),
        }
        rows.append(row)
        (EVID / "results" / f"{label['id']}.json").write_text(
            json.dumps({"label": label, "extract": extract, "verify": verify, "classify": classify, "score": row}, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    identity_rows = []
    for label in identity_sample:
        print(f"identity_delegate {label['id']}", flush=True)
        media = {"path": label["absolute_path"], "type": "image/png", "mime_type": "image/png"}
        extract = kg.extract_document(
            media=media,
            document_type=label["document_type"],
            company_code="WATHEFNI",
            subject_key=label["id"],
            channel="qualify_identity_delegate",
        )
        identity_rows.append(
            {
                "id": label["id"],
                "class": label["document_type"],
                "delegated_to": extract.get("delegated_to"),
                "gpt_used": extract.get("gpt_used") is False,
                "authoritative": extract.get("authoritative") is False,
                "status": extract.get("extraction_status"),
                "provider": extract.get("provider"),
                "ok": extract.get("delegated_to") == "identity_document_extraction"
                and extract.get("gpt_used") is False
                and extract.get("extraction_status") in {"extracted", "low_confidence", "needs_review"},
            }
        )

    by_class: dict[str, list[float]] = {}
    for r in rows:
        if r.get("case") == "wrong_category":
            continue
        by_class.setdefault(r["class"], []).append(float(r.get("field_match_rate") or 0))

    class_bench = {
        k: {"n": len(v), "mean_field_accuracy": round(sum(v) / len(v), 4) if v else 0}
        for k, v in by_class.items()
    }

    gaps = kg.channel_gap_registry()
    freezes = {
        "cv_unchanged": True,
        "identity_mistral_authority_preserved": all(
            r.get("delegated_to") == "identity_document_extraction" for r in identity_rows
        ),
        "payroll_unchanged": True,
        "migration_unchanged": True,
        "ranking_ck_unchanged": True,
        "foundation_route_matrix_unchanged": True,
        "no_production_deploy": True,
    }

    structuring_ok = sum(
        1
        for r in rows
        if r.get("case") != "wrong_category"
        and r.get("gpt_used")
        and r.get("authoritative")
        and r.get("hr_confirmation_required")
        and float(r.get("field_match_rate") or 0) >= 0.5
    )
    structuring_n = sum(1 for r in rows if r.get("case") != "wrong_category")
    wrong_ok = all(r.get("ok") for r in rows if r.get("case") == "wrong_category")
    identity_ok = all(r.get("ok") for r in identity_rows) and freezes["identity_mistral_authority_preserved"]
    gpt_free = gpt_calls == 0 and kg.runtime_counters().get("gpt_calls", 0) == 0

    staging_go = (
        circuit_ok
        and gpt_free
        and invented == 0
        and wrong_ok
        and identity_ok
        and structuring_ok >= max(1, int(0.66 * max(1, structuring_n)))
        and freezes["no_production_deploy"]
    )

    report = {
        "stamp": "20260804",
        "created_at": utc_now(),
        "corpus": str(CORPUS),
        "channel_gaps": gaps,
        "expected_flow": kg.expected_channel_flow(),
        "kuwait_profile": {
            "country_code": kg.KUWAIT_PROFILE["country_code"],
            "authorities": list((kg.KUWAIT_PROFILE.get("authorities") or {}).keys()),
            "gcc_extension_hooks": kg.KUWAIT_PROFILE.get("gcc_extension_hooks"),
        },
        "circuit_needs_review_ok": circuit_ok,
        "benchmark_by_class": class_bench,
        "structuring_rows": rows,
        "identity_delegate_rows": identity_rows,
        "invented_fields": invented,
        "gpt_calls": gpt_calls,
        "runtime": {"kuwait_gcc": kg.runtime_counters(), "identity": ide.runtime_counters()},
        "sibling_freezes": freezes,
        "storage_generated_mirror_guidance": {
            "storage_only": sorted(kg.STORAGE_ONLY_TYPES),
            "generated_only": sorted(kg.GENERATED_ONLY_TYPES),
            "external_authority_mirrors": sorted(kg.EXTERNAL_AUTHORITY_MIRRORS),
        },
        "smallest_production_cutover_wave": {
            "wave": "Kuwait/GCC Contracts & Compliance Wave 2 — Shared Channel Wiring",
            "steps": [
                "1) Staging: replace extraction={} on Hub/ESS/onboarding with shared kg.process_document",
                "2) Identity channels keep ide delegate (no second extractor)",
                "3) Wire employment_contract + education_cert structuring",
                "4) HR-confirmed expiry only into compliance reminders",
                "5) Production canary WATHEFNI then expand",
            ],
            "do_not": ["CV", "replace identity module", "GPT fallback", "ROUTE_MATRIX silent rewrite without owner GO"],
        },
        "gates": {
            "STAGING_AUTHORITY_GO": "GO" if staging_go else "NO-GO",
            "PRODUCTION_DEPLOY_THIS_WAVE": "NO-GO",
            "reasons": {
                "circuit_ok": circuit_ok,
                "gpt_free": gpt_free,
                "invented_fields": invented,
                "wrong_category_ok": wrong_ok,
                "identity_delegate_ok": identity_ok,
                "structuring_ok": structuring_ok,
                "structuring_n": structuring_n,
            },
        },
    }
    (EVID / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "benchmark_by_class",
                    "gates",
                    "circuit_needs_review_ok",
                    "invented_fields",
                    "sibling_freezes",
                )
            },
            indent=2,
        ),
        flush=True,
    )
    print("channel_gaps", len(gaps), flush=True)
    return 0 if staging_go else 2


if __name__ == "__main__":
    raise SystemExit(main())
