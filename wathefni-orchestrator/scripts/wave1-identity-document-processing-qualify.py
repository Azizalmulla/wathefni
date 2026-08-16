#!/usr/bin/env python3
"""Identity Document Processing Wave 1 — Mistral vs GPT qualification.

Compares the new Mistral Document AI identity path against the current GPT-vision
path on the labeled synthetic corpus. Does not deploy or change production
authority. Does not use CV V2. Does not use GPT as automatic fallback for Mistral.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

CORPUS = REPO / "ops/evidence/identity-wave1-corpus-20260804"
LABELS = CORPUS / "labels.jsonl"
EVID = REPO / "ops/evidence/identity-wave1-qualify-20260804"
RESULTS = EVID / "results"

COMPARE_FIELDS = [
    "document_type",
    "document_number",
    "full_name_ar",
    "full_name_en",
    "nationality",
    "date_of_birth",
    "issue_date",
    "expiry_date",
    "employer_or_sponsor",
    "side",
]

# Approximate GPT-5.x vision cost proxy when usage is unavailable (USD / image).
GPT_VISION_COST_PROXY_USD = float(os.environ.get("WATHEFNI_IDENTITY_GPT_COST_PROXY") or "0.02")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    text = re.sub(r"\s+", " ", text)
    return text


def norm_key(value: Any) -> str | None:
    text = normalize(value)
    if text is None:
        return None
    return re.sub(r"[^0-9A-Za-z\u0600-\u06FF]+", "", text).upper()


def arabic_chars(text: str | None) -> str:
    if not text:
        return ""
    return "".join(ch for ch in text if "\u0600" <= ch <= "\u06FF")


def score_field(expected: Any, got: Any, *, field: str) -> dict[str, Any]:
    exp = normalize(expected)
    act = normalize(got)
    if exp is None and act is None:
        return {"match": True, "kind": "both_missing"}
    if exp is None and act is not None:
        return {"match": False, "kind": "invented"}
    if exp is not None and act is None:
        return {"match": False, "kind": "missing"}
    if field in {"document_number"}:
        ok = norm_key(exp) == norm_key(act)
        return {"match": ok, "kind": "exact" if ok else "incorrect"}
    if field in {"full_name_ar"}:
        ea, aa = arabic_chars(exp), arabic_chars(act)
        if ea and aa:
            ok = ea == aa or ea in aa or aa in ea
            return {"match": ok, "kind": "arabic" if ok else "arabic_corrupt"}
    ok = norm_key(exp) == norm_key(act) or (norm_key(exp) or "") in (norm_key(act) or "") or (
        norm_key(act) or ""
    ) in (norm_key(exp) or "")
    return {"match": ok, "kind": "fuzzy" if ok else "incorrect"}


def load_labels() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with LABELS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _openclaw_provider_key(name: str = "openai-sse") -> tuple[str | None, str | None, str | None]:
    """Load apiKey/baseUrl/api from /root/.openclaw/openclaw.json when present."""

    for path in (
        Path("/root/.openclaw/openclaw.json"),
        Path.home() / ".openclaw/openclaw.json",
    ):
        if not path.exists():
            continue
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
            providers = ((cfg.get("models") or {}).get("providers") or {})
            # Prefer openai-sse (production planner) then openai.
            for key in (name, "openai-sse", "openai"):
                row = providers.get(key)
                if isinstance(row, dict) and row.get("apiKey"):
                    api = str(row.get("api") or ("openai-responses" if key == "openai-sse" else "chat-completions"))
                    return (
                        str(row.get("apiKey")),
                        str(row.get("baseUrl") or "https://api.openai.com/v1"),
                        api,
                    )
        except Exception:
            continue
    return None, None, None


def planner_provider_from_env() -> dict[str, str] | None:
    """Mirror of app.planner_provider_config for bench-only GPT calls."""

    oc_key, oc_base, oc_api = _openclaw_provider_key()
    api_key = (
        os.environ.get("WATHEFNI_TOOL_AGENT_API_KEY")
        or os.environ.get("WATHEFNI_PLANNER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or oc_key
    )
    if not api_key:
        return None
    api_kind = os.environ.get("WATHEFNI_TOOL_AGENT_API") or oc_api or "openai-responses"
    base_url = os.environ.get("WATHEFNI_TOOL_AGENT_BASE_URL") or oc_base or "https://api.openai.com/v1"
    explicit_url = os.environ.get("WATHEFNI_TOOL_AGENT_URL") or os.environ.get("WATHEFNI_PLANNER_URL")
    if explicit_url:
        url = explicit_url
    elif api_kind == "openai-responses":
        url = f"{base_url.rstrip('/')}/responses"
    else:
        url = (
            "https://openrouter.ai/api/v1/chat/completions"
            if os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY") and not oc_key
            else f"{base_url.rstrip('/')}/chat/completions"
        )
    model = (
        os.environ.get("WATHEFNI_TOOL_AGENT_MODEL")
        or os.environ.get("WATHEFNI_PLANNER_MODEL")
        or "gpt-5.6-terra"
    )
    return {"api_key": api_key, "url": url, "model": model, "api": api_kind}


def estimate_gpt_cost_usd(usage: dict[str, Any] | None) -> float:
    """Rough GPT-5.x vision cost from token usage; falls back to proxy."""

    if not isinstance(usage, dict):
        return GPT_VISION_COST_PROXY_USD
    inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    if inp <= 0 and out <= 0:
        return GPT_VISION_COST_PROXY_USD
    # Conservative public-rate proxy (USD / 1M tokens).
    return round((inp / 1_000_000.0) * 2.50 + (out / 1_000_000.0) * 10.0, 6)


def extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def extract_model_text(parsed: dict[str, Any]) -> str:
    output_text = parsed.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    chunks: list[str] = []
    for item in parsed.get("output") or []:
        for content in (item or {}).get("content") or []:
            if isinstance(content, dict):
                text = content.get("text") or content.get("output_text")
                if isinstance(text, str):
                    chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    message = ((parsed.get("choices") or [{}])[0].get("message") or {})
    content = message.get("content")
    return content if isinstance(content, str) else ""


def gpt_identity_extract(*, path: Path, document_type: str) -> dict[str, Any]:
    """Current GPT-vision identity path (bench mirror of app.extract_compliance_document_metadata)."""

    provider = planner_provider_from_env()
    if not provider:
        return {
            "ok": False,
            "extraction_status": "failed",
            "extraction_error": "missing_openai_key",
            "provider": "gpt",
            "cost_usd": 0.0,
            "latency_ms": 0,
            "fields": {},
        }
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data_uri = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    system = (
        "You extract compliance metadata from Kuwaiti employee onboarding documents. "
        "Read the current uploaded image/file only. Do not use quoted chat text as evidence. "
        "Return JSON only. Use ISO dates YYYY-MM-DD when visible. If a field is not visible, return null. "
        "For Civil ID, look for Civil ID number and card expiry. For passport, look for passport number, nationality, issue date, and expiry date."
    )
    prompt = json.dumps(
        {
            "document_type": document_type,
            "reply_text": "",
            "json_schema": {
                "document_type": "civil_id | passport | medical | residency | work_permit | unknown",
                "document_number": "string or null",
                "issued_date": "YYYY-MM-DD or null",
                "expiry_date": "YYYY-MM-DD or null",
                "nationality": "string or null",
                "full_name": "string or null",
                "full_name_ar": "string or null",
                "full_name_en": "string or null",
                "side": "front | back | single | unknown",
                "employer_or_sponsor": "string or null",
                "date_of_birth": "YYYY-MM-DD or null",
                "confidence": "number 0 to 1",
                "reason": "short string",
            },
        },
        ensure_ascii=False,
    )
    # Production app.py currently sends temperature=0, which Terra rejects.
    # Bench uses the same model/API shape but omits temperature so the current
    # intended GPT path can be scored fairly (and the temp=0 breakage is reported).
    if provider.get("api") == "openai-responses":
        body = {
            "model": provider["model"],
            "input": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_uri},
                    ],
                },
            ],
        }
    else:
        body = {
            "model": provider["model"],
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
        }
        if "terra" not in provider["model"].lower():
            body["temperature"] = 0
    started = time.perf_counter()
    req = urllib_request.Request(
        provider["url"],
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=90) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
        latency_ms = int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        detail = ""
        try:
            if hasattr(exc, "read"):
                detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = ""
        return {
            "ok": False,
            "extraction_status": "failed",
            "extraction_error": f"{exc}:{detail}" if detail else str(exc),
            "provider": "gpt",
            "model": provider["model"],
            "cost_usd": 0.0,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "fields": {},
            "note": "production_app_sends_temperature_0_which_terra_rejects",
        }
    result = extract_json_object(extract_model_text(parsed)) or {}
    try:
        confidence = float(result.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    fields = {
        "document_type": result.get("document_type"),
        "document_number": result.get("document_number"),
        "full_name_ar": result.get("full_name_ar"),
        "full_name_en": result.get("full_name_en") or result.get("full_name"),
        "nationality": result.get("nationality"),
        "date_of_birth": result.get("date_of_birth"),
        "issue_date": result.get("issued_date") or result.get("issue_date"),
        "expiry_date": result.get("expiry_date"),
        "employer_or_sponsor": result.get("employer_or_sponsor"),
        "side": result.get("side"),
        "full_name": result.get("full_name"),
    }
    status = "extracted" if confidence >= 0.55 else ("failed" if not result else "low_confidence")
    usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
    return {
        "ok": status == "extracted",
        "extraction_status": status,
        "confidence": confidence,
        "provider": "gpt",
        "model": provider["model"],
        "cost_usd": estimate_gpt_cost_usd(usage),
        "latency_ms": latency_ms,
        "fields": fields,
        "authoritative": False,
        "raw": result,
        "usage": usage,
        "api": provider.get("api"),
        "temperature_omitted_for_terra": True,
    }


def mistral_fields(result: dict[str, Any]) -> dict[str, Any]:
    fields = result.get("fields") or {}
    out: dict[str, Any] = {}
    for key in COMPARE_FIELDS + ["full_name"]:
        cell = fields.get(key)
        if isinstance(cell, dict):
            out[key] = cell.get("value")
        else:
            out[key] = None
    return out


def evaluate(label: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    per: dict[str, Any] = {}
    matches = 0
    scored = 0
    invented = 0
    missing = 0
    incorrect = 0
    arabic_ok = None
    for key in COMPARE_FIELDS:
        expected = label.get(key)
        got = fields.get(key)
        # GPT legacy often lacks side / ar/en / employer — still score when label has value
        s = score_field(expected, got, field=key)
        per[key] = s
        if expected is None and got is None:
            continue
        scored += 1
        if s["match"]:
            matches += 1
        elif s["kind"] == "invented":
            invented += 1
        elif s["kind"] == "missing":
            missing += 1
        else:
            incorrect += 1
        if key == "full_name_ar" and expected:
            arabic_ok = bool(s["match"])
    return {
        "field_accuracy": (matches / scored) if scored else 0.0,
        "matches": matches,
        "scored": scored,
        "invented": invented,
        "missing": missing,
        "incorrect": incorrect,
        "arabic_ok": arabic_ok,
        "per_field": per,
        "hr_review_burden": invented + missing + incorrect + (0 if (fields.get("document_number") and (fields.get("full_name_en") or fields.get("full_name_ar"))) else 1),
    }


def summarize(rows: list[dict[str, Any]], path_key: str) -> dict[str, Any]:
    path_rows = [r for r in rows if r.get(path_key)]
    if not path_rows:
        return {"n": 0}
    acc = [float(r[path_key]["eval"]["field_accuracy"]) for r in path_rows]
    lat = [int(r[path_key].get("latency_ms") or 0) for r in path_rows]
    cost = [float(r[path_key].get("cost_usd") or 0.0) for r in path_rows]
    invented = sum(int(r[path_key]["eval"]["invented"]) for r in path_rows)
    missing = sum(int(r[path_key]["eval"]["missing"]) for r in path_rows)
    incorrect = sum(int(r[path_key]["eval"]["incorrect"]) for r in path_rows)
    burden = sum(int(r[path_key]["eval"]["hr_review_burden"]) for r in path_rows)
    arabic = [r[path_key]["eval"]["arabic_ok"] for r in path_rows if r[path_key]["eval"]["arabic_ok"] is not None]
    needs_review = sum(1 for r in path_rows if r[path_key].get("extraction_status") == "needs_review")
    return {
        "n": len(path_rows),
        "mean_field_accuracy": round(sum(acc) / len(acc), 4),
        "mean_latency_ms": int(sum(lat) / len(lat)),
        "total_cost_usd": round(sum(cost), 6),
        "mean_cost_usd": round(sum(cost) / len(cost), 6),
        "invented_fields": invented,
        "missing_fields": missing,
        "incorrect_fields": incorrect,
        "hr_review_burden_proxy": burden,
        "arabic_integrity_rate": round(sum(1 for x in arabic if x) / len(arabic), 4) if arabic else None,
        "needs_review_count": needs_review,
    }


def failure_classes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classes: dict[str, int] = {}
    for r in rows:
        m = r.get("mistral") or {}
        if m.get("extraction_status") == "needs_review":
            classes["mistral_needs_review"] = classes.get("mistral_needs_review", 0) + 1
        if m.get("extraction_error"):
            key = f"mistral_error:{str(m.get('extraction_error'))[:40]}"
            classes[key] = classes.get(key, 0) + 1
        for field, s in ((m.get("eval") or {}).get("per_field") or {}).items():
            if not s.get("match") and s.get("kind") not in {"both_missing"}:
                key = f"mistral_{s['kind']}:{field}"
                classes[key] = classes.get(key, 0) + 1
        g = r.get("gpt") or {}
        for field, s in ((g.get("eval") or {}).get("per_field") or {}).items():
            if not s.get("match") and s.get("kind") not in {"both_missing"}:
                key = f"gpt_{s['kind']}:{field}"
                classes[key] = classes.get(key, 0) + 1
    return [{"class": k, "count": v} for k, v in sorted(classes.items(), key=lambda x: (-x[1], x[0]))]


def decide_gates(mistral_sum: dict[str, Any], gpt_sum: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Staging authority GO if Mistral is usable and not worse on core identity fields.
    m_acc = float(mistral_sum.get("mean_field_accuracy") or 0)
    g_acc = float(gpt_sum.get("mean_field_accuracy") or 0)
    invented = int(mistral_sum.get("invented_fields") or 0)
    needs = int(mistral_sum.get("needs_review_count") or 0)
    circuit_ok = all(
        "circuit_open" not in str((r.get("mistral") or {}).get("extraction_error") or "")
        for r in rows
    )
    no_gpt_fallback = all(
        (r.get("mistral") or {}).get("provider") == "mistral" or (r.get("mistral") or {}).get("extraction_status") == "needs_review"
        for r in rows
    )
    provenance_ok = all(
        isinstance(((r.get("mistral") or {}).get("fields") or {}).get("document_number"), dict)
        or (r.get("mistral") or {}).get("extraction_status") == "needs_review"
        for r in rows
    )
    # Require Mistral mean accuracy >= 0.70 and not >15pp worse than GPT; zero invented preferred.
    staging_go = (
        m_acc >= 0.70
        and m_acc + 0.01 >= (g_acc - 0.15)
        and invented == 0
        and circuit_ok
        and no_gpt_fallback
        and provenance_ok
        and needs < max(1, int(0.35 * max(1, mistral_sum.get("n") or 1)))
    )
    return {
        "STAGING_AUTHORITY_GO": "GO" if staging_go else "NO-GO",
        "PRODUCTION_DEPLOY_THIS_WAVE": "NO-GO",
        "reasons": {
            "mistral_mean_field_accuracy": m_acc,
            "gpt_mean_field_accuracy": g_acc,
            "invented_fields": invented,
            "needs_review_count": needs,
            "circuit_ok": circuit_ok,
            "no_gpt_fallback": no_gpt_fallback,
            "provenance_ok": provenance_ok,
        },
        "smallest_production_cutover_wave": {
            "wave": "Identity Document Processing Wave 2 — Staging Authority → Production Shadow then Canary",
            "steps": [
                "1) Staging: flip onboarding extract/classify/verify to identity_document_extraction under shadow flag",
                "2) Staging authority canary for civil_id+passport only with HR confirmation gate unchanged",
                "3) Production shadow (write proposals, GPT still live) for 1 week",
                "4) Production canary company WATHEFNI then expand residency/work_permit/medical",
                "5) Remove GPT extract/verify/classify calls for identity after dual-run parity",
            ],
            "do_not_change": [
                "CV extraction",
                "Ranking",
                "Candidate Knowledge",
                "Migration Wave 1",
                "document_processing_foundation route matrix until cutover owner GO",
            ],
        },
    }


def gpt_dependency_map() -> dict[str, Any]:
    return {
        "primary_extractor": {
            "symbol": "app.extract_compliance_document_metadata",
            "file": "wathefni-orchestrator/app.py",
            "approx_lines": "30121-30220",
            "provider": "planner_provider_config() → default gpt-5.6-terra",
            "input": "media_data_uri(media) vision image",
            "fields": [
                "document_type",
                "document_number",
                "issued_date",
                "expiry_date",
                "nationality",
                "full_name",
                "date_of_birth",
                "confidence",
                "reason",
            ],
            "confidence_gate": "extracted if confidence >= 0.55 else low_confidence",
            "known_breakage": (
                "app.extract_compliance_document_metadata sends temperature=0; "
                "gpt-5.6-terra on openai-responses rejects temperature. "
                "Wave 1 bench omits temperature to score the intended GPT path."
            ),
        },
        "related_gpt_callers": [
            {
                "symbol": "app.verify_onboarding_media_item",
                "approx_lines": "29955+",
                "gate": "confidence >= 0.65",
            },
            {
                "symbol": "app.classify_onboarding_media_upload",
                "approx_lines": "30034+",
                "gate": "confidence >= 0.75",
            },
        ],
        "storage_authority": {
            "tables": ["employee_documents", "compliance_documents", "governed_document_versions"],
            "ocr_proposal_authoritative": False,
            "hr_confirmation_required": True,
        },
        "foundation_route_matrix": {
            "document_class": "identity",
            "structuring": "identity_processor_current_gpt_vision",
            "authority_in_this_wave": "legacy_gpt_vision_until_replacement_qualified",
            "ocr_policy": "do_not_use_cv_v2",
            "note": "Route matrix not mutated in Wave 1 qualification",
        },
        "replacement_module": "wathefni-orchestrator/identity_document_extraction.py",
        "gpt_auto_fallback_in_new_path": False,
        "cv_v2_usage": False,
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (EVID / "docs").mkdir(parents=True, exist_ok=True)

    if not LABELS.exists():
        build = ROOT / "scripts/build-identity-wave1-synthetic-corpus.py"
        print(f"building corpus via {build}", flush=True)
        os.system(f"{sys.executable} {build}")

    # Load secrets if present (local or VPS)
    for secrets in (
        Path("/root/.openclaw/secrets/mistral.env"),
        Path.home() / ".openclaw/secrets/mistral.env",
        Path("/root/.openclaw/secrets/openai.env"),
        Path.home() / ".openclaw/secrets/openai.env",
    ):
        if secrets.exists():
            for line in secrets.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    os.environ["WATHEFNI_IDENTITY_MISTRAL_EXTRACT"] = "qualify"
    # Ensure we do not touch CV V2 flags as authority
    os.environ.setdefault("WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK", "off")

    import identity_document_extraction as ide

    ide.reset_circuit_for_tests()
    labels = load_labels()
    rows: list[dict[str, Any]] = []

    for label in labels:
        path = Path(label["absolute_path"])
        print(f"qualify {label['id']}", flush=True)
        mistral = ide.extract_identity_document(
            path=path,
            expected_type=label["document_type"],
            subject_key=label["id"],
        )
        m_fields = mistral_fields(mistral)
        mistral_out = {
            "extraction_status": mistral.get("extraction_status"),
            "extraction_error": mistral.get("extraction_error"),
            "confidence": mistral.get("confidence"),
            "provider": mistral.get("provider"),
            "model": mistral.get("model"),
            "cost_usd": mistral.get("cost_usd"),
            "latency_ms": mistral.get("latency_ms"),
            "authoritative": mistral.get("authoritative"),
            "hr_confirmation_required": mistral.get("hr_confirmation_required"),
            "validation": mistral.get("validation"),
            "duplicate_keys": ide.duplicate_keys(mistral),
            "fields": mistral.get("fields"),
            "flat_fields": m_fields,
            "eval": evaluate(label, m_fields),
            "envelope_contract": (mistral.get("envelope") or {}).get("contract"),
            "attempts": mistral.get("attempts"),
        }

        gpt = gpt_identity_extract(path=path, document_type=label["document_type"])
        gpt_out = {
            **gpt,
            "eval": evaluate(label, gpt.get("fields") or {}),
        }

        row = {
            "id": label["id"],
            "label": {k: label.get(k) for k in COMPARE_FIELDS + ["lang", "variant", "document_relationship"]},
            "mistral": mistral_out,
            "gpt": gpt_out,
        }
        rows.append(row)
        (RESULTS / f"{label['id']}.json").write_text(
            json.dumps(row, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    mistral_sum = summarize(rows, "mistral")
    gpt_sum = summarize(rows, "gpt")
    gates = decide_gates(mistral_sum, gpt_sum, rows)
    report = {
        "stamp": "20260804",
        "created_at": utc_now(),
        "corpus": str(CORPUS),
        "n_fixtures": len(rows),
        "gpt_dependency_map": gpt_dependency_map(),
        "mistral_summary": mistral_sum,
        "gpt_summary": gpt_sum,
        "comparison": {
            "accuracy_delta_mistral_minus_gpt": round(
                float(mistral_sum.get("mean_field_accuracy") or 0)
                - float(gpt_sum.get("mean_field_accuracy") or 0),
                4,
            ),
            "latency_delta_ms_mistral_minus_gpt": int(
                int(mistral_sum.get("mean_latency_ms") or 0) - int(gpt_sum.get("mean_latency_ms") or 0)
            ),
            "cost_ratio_mistral_over_gpt": (
                round(
                    float(mistral_sum.get("total_cost_usd") or 0)
                    / max(float(gpt_sum.get("total_cost_usd") or 0), 1e-9),
                    4,
                )
                if gpt_sum.get("total_cost_usd")
                else None
            ),
            "hr_burden_delta_mistral_minus_gpt": int(
                int(mistral_sum.get("hr_review_burden_proxy") or 0)
                - int(gpt_sum.get("hr_review_burden_proxy") or 0)
            ),
        },
        "failure_classes": failure_classes(rows),
        "gates": gates,
        "constraints_honored": {
            "no_cv_v2": True,
            "no_gpt_auto_fallback": True,
            "hr_final_authority": True,
            "no_production_deploy": True,
            "foundation_route_matrix_unchanged": True,
        },
        "rows": rows,
    }
    (EVID / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: report[k] for k in ("mistral_summary", "gpt_summary", "comparison", "gates")}, indent=2), flush=True)
    return 0 if gates["STAGING_AUTHORITY_GO"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
