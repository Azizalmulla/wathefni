#!/usr/bin/env python3
import json
import os
import re
import subprocess
import time
from collections import defaultdict


PROFILE = os.environ.get("RIDERS_MINI_BENCH_PROFILE", "delivery").strip() or "delivery"
OUTPUT_PATH = os.environ.get("RIDERS_MINI_BENCH_OUTPUT", "/tmp/riders-mini-bench-results.json").strip()
TIMEOUT_SECONDS = int(os.environ.get("RIDERS_MINI_BENCH_TIMEOUT_SECONDS", "120"))
AGENTS = [
    agent.strip()
    for agent in os.environ.get("RIDERS_MINI_BENCH_AGENTS", "riders,riders-mini").split(",")
    if agent.strip()
]

CASES = [
    {
        "id": "pricing_en_clean",
        "prompt": "What is the price from Salmiya to Farwaniya?",
        "expected": [
            ("structured_price", r"Price:\s*\d+\.\d{3}\s*KWD"),
            ("pickup_name", r"Salmiya"),
            ("dropoff_name", r"Farwaniya"),
        ],
        "forbidden": [],
    },
    {
        "id": "pricing_arabizi_noisy",
        "prompt": "pls 7wly to slwa how much",
        "expected": [
            ("structured_price", r"Price:\s*\d+\.\d{3}\s*KWD"),
            ("pickup_name", r"Hawalli"),
            ("dropoff_name", r"Salwa"),
        ],
        "forbidden": [],
    },
    {
        "id": "service_comparison",
        "prompt": "Hawalli to Salwa, what about express sedan?",
        "expected": [
            ("express_label", r"express"),
            ("price_present", r"\d+\.\d{3}\s*KWD"),
        ],
        "forbidden": [],
    },
    {
        "id": "tracking_guard",
        "prompt": "Track my order",
        "expected": [
            ("asks_for_order_id", r"ORDER-"),
        ],
        "forbidden": [
            ("fake_tracking_result", r"tracking_url"),
        ],
    },
    {
        "id": "passenger_rejection",
        "prompt": "Will you drop me to the airport?",
        "expected": [
            ("rejects_people_transport", r"deliver items and packages|do not transport people"),
        ],
        "forbidden": [
            ("pricing_leak", r"Price:\s*\d+\.\d{3}\s*KWD"),
        ],
    },
]


def extract_reply(stdout: str) -> str:
    try:
        start = stdout.find("{")
        if start == -1:
            return stdout[:1500].strip()
        data = json.loads(stdout[start:])
        result = data.get("result", data)
        payloads = result.get("payloads", []) if isinstance(result, dict) else []
        texts = [payload.get("text") for payload in payloads if isinstance(payload, dict) and payload.get("text")]
        reply = "\n".join(texts).strip()
        return reply[:1500]
    except Exception:
        return stdout[:1500].strip()


def run_case(agent: str, case: dict) -> dict:
    started = time.time()
    cmd = [
        "openclaw",
        "--profile",
        PROFILE,
        "agent",
        "--local",
        "--agent",
        agent,
        "--message",
        case["prompt"],
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        elapsed = round(time.time() - started, 1)
        reply = extract_reply(result.stdout)
        stderr_excerpt = (result.stderr or "").strip()[:1500]
        if not reply and result.returncode != 0 and stderr_excerpt:
            reply = f"[ERROR] {stderr_excerpt}"
        passed_checks = []
        failed_checks = []
        for label, pattern in case["expected"]:
            if re.search(pattern, reply, re.IGNORECASE):
                passed_checks.append(label)
            else:
                failed_checks.append(f"missing:{label}")
        for label, pattern in case["forbidden"]:
            if re.search(pattern, reply, re.IGNORECASE):
                failed_checks.append(f"forbidden:{label}")
            else:
                passed_checks.append(f"not_{label}")
        score = len(passed_checks) / max(1, len(case["expected"]) + len(case["forbidden"]))
        return {
            "case_id": case["id"],
            "prompt": case["prompt"],
            "agent": agent,
            "elapsed_s": elapsed,
            "exit": result.returncode,
            "reply": reply,
            "stderr_excerpt": stderr_excerpt,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "score": round(score, 3),
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - started, 1)
        return {
            "case_id": case["id"],
            "prompt": case["prompt"],
            "agent": agent,
            "elapsed_s": elapsed,
            "exit": -1,
            "reply": "[TIMEOUT]",
            "stderr_excerpt": "",
            "passed_checks": [],
            "failed_checks": ["timeout"],
            "score": 0.0,
        }


def main() -> None:
    results = []
    summary = defaultdict(lambda: {"cases": 0, "score_total": 0.0, "elapsed_total": 0.0, "failures": 0})

    for case in CASES:
        for agent in AGENTS:
            entry = run_case(agent, case)
            results.append(entry)
            bucket = summary[agent]
            bucket["cases"] += 1
            bucket["score_total"] += entry["score"]
            bucket["elapsed_total"] += entry["elapsed_s"]
            if entry["exit"] != 0 or entry["failed_checks"]:
                bucket["failures"] += 1
            print(
                f"[{agent}] {case['id']}: score={entry['score']:.3f} elapsed={entry['elapsed_s']:.1f}s "
                f"failures={','.join(entry['failed_checks']) or 'none'}"
            )

    aggregate = {
        agent: {
            "cases": bucket["cases"],
            "avg_score": round(bucket["score_total"] / max(1, bucket["cases"]), 3),
            "avg_elapsed_s": round(bucket["elapsed_total"] / max(1, bucket["cases"]), 1),
            "failed_cases": bucket["failures"],
        }
        for agent, bucket in summary.items()
    }

    payload = {
        "profile": PROFILE,
        "agents": AGENTS,
        "cases": [case["id"] for case in CASES],
        "results": results,
        "summary": aggregate,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    print("")
    for agent in AGENTS:
        bucket = aggregate.get(agent)
        if not bucket:
            continue
        print(
            f"{agent}: avg_score={bucket['avg_score']:.3f} avg_elapsed={bucket['avg_elapsed_s']:.1f}s "
            f"failed_cases={bucket['failed_cases']}/{bucket['cases']}"
        )
    print(f"\nDONE - results at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
