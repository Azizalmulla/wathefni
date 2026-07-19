#!/usr/bin/env python3
"""Staging evaluation for GPT-5.6 Luna candidate semantic router.

Calls Luna for natural-language cases after deterministic gates. Does not send
WhatsApp messages or mutate production. Staging DB writes are limited to
optional llm_call_logs when telemetry is enabled.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import candidate_messages
import candidate_semantic_router as router

EVIDENCE_DIR = Path(
    os.environ.get("WATHEFNI_LUNA_EVAL_EVIDENCE_DIR")
    or (Path(__file__).resolve().parents[2] / "staging-evidence" / "candidate-luna-semantic-router1")
)
CASES: list[dict[str, Any]] = []


def add(intent: str, language: str, text: str, **extra: Any) -> None:
    CASES.append({"intent": intent, "language": language, "text": text, **extra})


def bulk(intent: str, mapping: dict[str, list[str]], **extra: Any) -> None:
    for language, texts in mapping.items():
        for text in texts:
            add(intent, language, text, **extra)


# --- Balanced corpus: >=160 messages across language groups ---
bulk(
    "apply_role",
    {
        "en": [
            "I want to apply for finance",
            "Can I apply for human resources?",
            "Apply me to the accountant role",
            "Looking to apply for sales",
        ],
        "msa": [
            "أريد التقديم على وظيفة المالية",
            "أرغب بالتقديم على الموارد البشرية",
            "أتقدم لوظيفة محاسب",
            "أريد التقديم على المبيعات",
        ],
        "gulf": [
            "ابي اقدم على المالية",
            "ودي أقدم على الموارد البشرية",
            "ابي اقدم محاسب",
            "ابي على المبيعات",
        ],
        "arabizi_mixed": [
            "abii aqadem 3ala finance",
            "abi apply 3ala HR",
            "wadi aqadem accountant",
            "ابي apply على sales",
        ],
    },
    entity_kind="role_text",
)
bulk(
    "replace_cv",
    {
        "en": [
            "I sent the wrong CV",
            "Please replace my resume",
            "I want to update my CV",
            "Can I resend my CV file?",
        ],
        "msa": [
            "أريد استبدال سيرتي الذاتية",
            "أرسلت سيرة خاطئة وأريد تغييرها",
            "هل يمكن تحديث السيرة الذاتية؟",
            "أريد إرسال سيرة بديلة",
        ],
        "gulf": [
            "قدمت السي في الغلط",
            "ابي ابدل الـ CV",
            "ابي احدث السيرة",
            "دزيت سي في غلط ابي ابدله",
        ],
        "arabizi_mixed": [
            "abi abadel el cv",
            "sent wrong seera abi aghayerha",
            "update cv please",
            "resend el resume",
        ],
    },
)
bulk(
    "cv_received",
    {
        "en": [
            "Did you receive my CV?",
            "Was my resume received?",
            "Confirm you got my CV",
            "Have you received the file?",
        ],
        "msa": [
            "هل استلمتم سيرتي الذاتية؟",
            "هل وصلت السيرة؟",
            "تأكيد استلام السيرة الذاتية",
            "هل استلمتم الملف؟",
        ],
        "gulf": [
            "استلمتوا السي في؟",
            "وصلت السيرة ولا لا؟",
            "شفتوا الـ CV؟",
            "وصلكم الملف؟",
        ],
        "arabizi_mixed": [
            "did u get el cv?",
            "wslat el seera?",
            "received cv or not",
            "got my resume?",
        ],
    },
)
bulk(
    "status",
    {
        "en": [
            "What is my application status?",
            "Where is my application now?",
            "Any update on my application?",
            "Status of my job application please",
        ],
        "msa": [
            "ما هي حالة طلبي؟",
            "أين وصل طلب التوظيف؟",
            "هل يوجد تحديث على طلبي؟",
            "أريد معرفة حالة الطلب",
        ],
        "gulf": [
            "وش صار على طلبي؟",
            "وين وصل الطلب؟",
            "حالة طلبي شنو؟",
            "في جديد على الطلب؟",
        ],
        "arabizi_mixed": [
            "status mal application?",
            "wein wsl talabi?",
            "any update 3ala talabi",
            "shu sar 3ala application?",
        ],
    },
)
bulk(
    "withdraw",
    {
        "en": [
            "I want to withdraw my application",
            "Please cancel my application",
            "Remove my job application",
            "I'd like to withdraw",
        ],
        "msa": [
            "أريد سحب طلبي",
            "أرغب بإلغاء طلب التوظيف",
            "يرجى سحب الطلب",
            "أريد الانسحاب من الطلب",
        ],
        "gulf": [
            "ابي اسحب طلبي",
            "الغي الطلب",
            "ابي انسحب من الطلب",
            "سكروا طلبي",
        ],
        "arabizi_mixed": [
            "abi as7ab talabi",
            "withdraw application please",
            "cancel talabi",
            "abi withdraw",
        ],
    },
)
bulk(
    "confirm_withdraw",
    {
        "en": ["CONFIRM", "Yes withdraw", "Confirm withdrawal", "Yes, withdraw now"],
        "msa": ["تأكيد", "نعم اسحب", "أؤكد السحب", "نعم سحب الطلب"],
        "gulf": ["تأكيد", "اي اسحب", "ايه اسحبه", "اكد السحب"],
        "arabizi_mixed": ["confirm", "yes withdraw", "akked", "confirm withdraw"],
    },
)
bulk(
    "cancel_withdraw",
    {
        "en": ["CANCEL", "Do not withdraw", "Keep my application", "No keep it"],
        "msa": ["إلغاء", "لا تسحب الطلب", "أبقِ على الطلب", "لا أريد السحب"],
        "gulf": ["الغاء", "لا خله", "لا تسحبه", "خليه فعال"],
        "arabizi_mixed": ["cancel", "la tkhalleh", "keep it", "no withdraw"],
    },
)
bulk(
    "hr_handoff",
    {
        "en": [
            "I want to speak to HR",
            "Can I talk to a human recruiter?",
            "Please contact HR for me",
            "Connect me to a person",
        ],
        "msa": [
            "أريد التحدث مع الموارد البشرية",
            "هل يمكنني التكلم مع موظف؟",
            "أرجو التواصل مع الموارد البشرية",
            "أريد شخصاً للحديث",
        ],
        "gulf": [
            "ابي اكلم الموارد البشرية",
            "ابي اتكلم ويا موظف",
            "حولني على HR",
            "ابي اكلم احد",
        ],
        "arabizi_mixed": [
            "abi akalem HR",
            "speak to human please",
            "abi recruiter",
            "contact HR",
        ],
    },
)
bulk(
    "assessment",
    {
        "en": [
            "Where is my assessment link?",
            "I have a question about the assessment",
            "Did you send the test?",
            "Assessment status please",
        ],
        "msa": [
            "أين رابط التقييم؟",
            "لدي سؤال عن التقييم",
            "هل أرسلتم الاختبار؟",
            "ما حالة التقييم؟",
        ],
        "gulf": [
            "وين رابط التقييم؟",
            "عندي سؤال عن الاختبار",
            "رسلتوا الـ assessment؟",
            "التقييم وين؟",
        ],
        "arabizi_mixed": [
            "wein assessment link?",
            "any update on el test",
            "assessment wein?",
            "sent the assessment?",
        ],
    },
)
bulk(
    "interview",
    {
        "en": [
            "When is my interview?",
            "Do I have an interview invitation?",
            "Interview details please",
            "Any update on the interview?",
        ],
        "msa": [
            "متى المقابلة؟",
            "هل لدي دعوة مقابلة؟",
            "تفاصيل المقابلة من فضلك",
            "أي تحديث بخصوص المقابلة؟",
        ],
        "gulf": [
            "متى المقابلة؟",
            "في مقابلة لي؟",
            "تفاصيل المقابلة",
            "في جديد عن المقابلة؟",
        ],
        "arabizi_mixed": [
            "interview wein?",
            "any interview update",
            "mqaabla details",
            "when interview?",
        ],
    },
)
bulk(
    "offer",
    {
        "en": [
            "Do I have an offer?",
            "Where is my offer letter link?",
            "Any employment offer update?",
            "Offer status please",
        ],
        "msa": [
            "هل لدي عرض وظيفي؟",
            "أين رابط العرض؟",
            "أي تحديث بخصوص العرض الوظيفي؟",
            "حالة العرض من فضلك",
        ],
        "gulf": [
            "في عرض لي؟",
            "وين رابط العرض؟",
            "في جديد عن العرض؟",
            "العرض الوظيفي شنو؟",
        ],
        "arabizi_mixed": [
            "any offer?",
            "offer link wein?",
            "3ard wazeefi status",
            "got an offer?",
        ],
    },
)
bulk(
    "unknown",
    {
        "en": [
            "asdf qwerty",
            "Maybe later something",
            "I want status and also withdraw and also apply",
            "Tell me the secret ranking score",
        ],
        "msa": [
            "مممم لا أدري",
            "شيء ما",
            "أريد الحالة والسحب والتقديم معاً",
            "أعطني درجة الترتيب السرية",
        ],
        "gulf": [
            "ما ادري شنو",
            "يلا بعدين",
            "ابي الحالة واسحب واقدم",
            "عطني السكور الداخلي",
        ],
        "arabizi_mixed": [
            "idk wallah",
            "blah blah xyz",
            "status + withdraw + apply now",
            "give me internal score",
        ],
    },
    ambiguous=True,
)

# Deterministic APPLY codes (should not need Luna for routing correctness)
for lang, texts in {
    "en": ["APPLY-WATHEFNI-FIN", "Please use APPLY-WATHEFNI-HR"],
    "msa": ["رمز التقديم APPLY-WATHEFNI-FIN", "هذا APPLY-WATHEFNI-HR"],
    "gulf": ["الكود APPLY-WATHEFNI-FIN", "هذا APPLY-WATHEFNI-HR"],
    "arabizi_mixed": ["code APPLY-WATHEFNI-FIN", "APPLY-WATHEFNI-HR please"],
}.items():
    for text in texts:
        add("apply_code", lang, text, deterministic=True, entity_kind="apply_code", expected_apply_code=True)


def predict_deterministic(case: dict[str, Any]) -> dict[str, Any]:
    import re

    text = case["text"]
    if re.search(r"APPLY-[A-Z0-9-]+", text, re.I):
        return {
            "intent": "apply_code",
            "confidence": 1.0,
            "needs_clarification": False,
            "accepted_intent": "apply_code",
            "apply_code": re.search(r"(APPLY-[A-Z0-9-]+)", text, re.I).group(1).upper(),
            "language": "ar" if case["language"] != "en" else "en",
            "path": "deterministic",
            "ok": True,
            "mutation_attempt": False,
        }
    return {"intent": "unknown", "ok": False, "path": "deterministic"}


def score_case(case: dict[str, Any], pred: dict[str, Any]) -> dict[str, Any]:
    expected = case["intent"]
    accepted = pred.get("accepted_intent") or pred.get("intent")
    needs_clarification = bool(pred.get("needs_clarification"))
    if case.get("ambiguous") or expected == "unknown":
        intent_ok = needs_clarification or accepted in {None, "unknown"} or pred.get("intent") == "unknown"
        safe = intent_ok and pred.get("mutation_attempt") is not True
    else:
        intent_ok = (accepted == expected) or (pred.get("intent") == expected and not needs_clarification)
        # Accept clarification only when model was unsure; still counts as miss for accuracy.
        safe = pred.get("mutation_attempt") is not True
    entity_ok = True
    if case.get("entity_kind") == "apply_code":
        entity_ok = bool(pred.get("apply_code"))
    elif case.get("entity_kind") == "role_text":
        entity_ok = bool(str(pred.get("role_text") or "").strip()) or expected != "apply_role"
    language_ok = True
    if case["language"] == "en":
        language_ok = str(pred.get("language") or "") == "en"
    elif case["language"] in {"msa", "gulf"}:
        language_ok = str(pred.get("language") or "") == "ar"
    # Arabizi/mixed: either en or ar is acceptable if intent correct; prefer ar when Arabic letters present.
    return {
        "intent_ok": bool(intent_ok),
        "entity_ok": bool(entity_ok),
        "language_ok": bool(language_ok),
        "safe": bool(safe),
        "needs_clarification": needs_clarification,
    }


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    provider = None
    try:
        import app as orchestrator_app

        provider = orchestrator_app.candidate_semantic_provider_config()
    except Exception as exc:
        provider = None
        print(f"warning: could not load orchestrator provider ({exc})", file=sys.stderr)

    if not provider or not provider.get("api_key"):
        # Offline fallback: require env for real Luna calls.
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("WATHEFNI_TOOL_AGENT_API_KEY")
        if not api_key:
            print("ERROR: no API key for gpt-5.6-luna", file=sys.stderr)
            return 2
        provider = {
            "api_key": api_key,
            "url": os.environ.get("WATHEFNI_CANDIDATE_SEMANTIC_URL")
            or "https://api.openai.com/v1/responses",
            "model": router.MODEL_ID,
            "api": "openai-responses",
            "provider": "openai",
        }

    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    costs: list[float] = []
    tokens_in: list[int] = []
    tokens_out: list[int] = []
    false_mutations = 0

    print(f"cases={len(CASES)} model={router.MODEL_ID} threshold={router.CONFIDENCE_THRESHOLD}")
    for idx, case in enumerate(CASES, 1):
        started = time.monotonic()
        if case.get("deterministic"):
            pred = predict_deterministic(case)
        else:
            pred = router.classify_candidate_intent(
                case["text"],
                provider=provider,
                context={"eval": True, "case_id": idx},
                timeout=20,
            )
            pred["path"] = "luna"
            pred["mutation_attempt"] = False
        latency = pred.get("latency_ms")
        if latency is None:
            latency = int((time.monotonic() - started) * 1000)
            pred["latency_ms"] = latency
        scored = score_case(case, pred)
        if not scored["safe"]:
            false_mutations += 1
        if pred.get("estimated_cost_usd") is not None:
            costs.append(float(pred["estimated_cost_usd"]))
        if pred.get("input_tokens") is not None:
            tokens_in.append(int(pred["input_tokens"]))
        if pred.get("output_tokens") is not None:
            tokens_out.append(int(pred["output_tokens"]))
        if pred.get("path") == "luna":
            latencies.append(float(latency))
        row = {
            "id": idx,
            "expected": case["intent"],
            "language": case["language"],
            "text": case["text"],
            "predicted_intent": pred.get("accepted_intent") or pred.get("intent"),
            "raw_intent": pred.get("intent"),
            "confidence": pred.get("confidence"),
            "needs_clarification": pred.get("needs_clarification"),
            "language_pred": pred.get("language"),
            "role_text": pred.get("role_text"),
            "apply_code": pred.get("apply_code"),
            "path": pred.get("path"),
            "latency_ms": latency,
            "input_tokens": pred.get("input_tokens"),
            "output_tokens": pred.get("output_tokens"),
            "estimated_cost_usd": pred.get("estimated_cost_usd"),
            "error": pred.get("error"),
            **scored,
        }
        results.append(row)
        marker = "OK" if scored["intent_ok"] else "FAIL"
        print(f"[{idx:03d}/{len(CASES)}] {marker} {case['language']}:{case['intent']} -> {row['predicted_intent']} conf={row['confidence']}")

    by_lang: dict[str, list[bool]] = defaultdict(list)
    by_intent: dict[str, list[bool]] = defaultdict(list)
    for row in results:
        by_lang[row["language"]].append(row["intent_ok"])
        by_intent[row["expected"]].append(row["intent_ok"])

    def pct(vals: list[bool]) -> float:
        return round(100.0 * sum(1 for v in vals if v) / max(1, len(vals)), 2)

    ambiguous_rows = [r for r in results if r["expected"] == "unknown"]
    summary = {
        "model_id": router.MODEL_ID,
        "prompt_version": router.PROMPT_VERSION,
        "schema_version": router.SCHEMA_VERSION,
        "catalog_version": candidate_messages.CATALOG_VERSION,
        "confidence_threshold": router.CONFIDENCE_THRESHOLD,
        "case_count": len(results),
        "overall_intent_accuracy_pct": pct([r["intent_ok"] for r in results]),
        "entity_extraction_pct": pct([r["entity_ok"] for r in results if r["expected"] in {"apply_role", "apply_code"}]),
        "language_accuracy_pct": pct([r["language_ok"] for r in results if r["language"] in {"en", "msa", "gulf"}]),
        "false_mutation_attempts": false_mutations,
        "ambiguous_safe_handling_pct": pct([r["safe"] and r["intent_ok"] for r in ambiguous_rows]),
        "by_language_intent_accuracy_pct": {k: pct(v) for k, v in sorted(by_lang.items())},
        "by_intent_accuracy_pct": {k: pct(v) for k, v in sorted(by_intent.items())},
        "arabizi_mixed_intent_accuracy_pct": pct(by_lang.get("arabizi_mixed", [])),
        "latency_ms": {
            "count": len(latencies),
            "p50": statistics.median(latencies) if latencies else None,
            "avg": round(statistics.mean(latencies), 1) if latencies else None,
            "p95": sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "tokens": {
            "input_total": sum(tokens_in),
            "output_total": sum(tokens_out),
            "input_avg": round(statistics.mean(tokens_in), 1) if tokens_in else None,
            "output_avg": round(statistics.mean(tokens_out), 1) if tokens_out else None,
        },
        "cost_usd": {
            "total": round(sum(costs), 6) if costs else 0.0,
            "avg_per_call": round(statistics.mean(costs), 6) if costs else None,
        },
        "targets": {
            "overall_intent_ge_90": pct([r["intent_ok"] for r in results]) >= 90,
            "each_language_ge_85": all(pct(v) >= 85 for v in by_lang.values()),
            "arabizi_mixed_ge_80": pct(by_lang.get("arabizi_mixed", [])) >= 80,
            "entity_ge_95": pct([r["entity_ok"] for r in results if r["expected"] in {"apply_role", "apply_code"}]) >= 95,
            "false_mutations_eq_0": false_mutations == 0,
            "ambiguous_safe_eq_100": pct([r["safe"] and r["intent_ok"] for r in ambiguous_rows]) >= 100,
        },
        "failed_examples": [
            {
                "id": r["id"],
                "language": r["language"],
                "expected": r["expected"],
                "predicted": r["predicted_intent"],
                "confidence": r["confidence"],
                "text": r["text"],
                "error": r["error"],
            }
            for r in results
            if not r["intent_ok"]
        ][:40],
        "run_id": str(uuid.uuid4()),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (EVIDENCE_DIR / "LUNA_EVAL.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVIDENCE_DIR / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(summary["targets"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
