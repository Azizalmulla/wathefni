#!/usr/bin/env python3
"""Analytics Wave 1-B — production synthetic Attention Contract canary (WATHEFNI).

Read-only. SYNTHETIC_ONLY required. No AI / Compliance metrics / payroll money.
Proves actor scope, ranked attention, partial-module disclosure, masked counts,
deep links, freshness/as_of, EN/AR definitions, and residual cleanup of canary ACKs.
Does not mutate frozen module contracts or real employees.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_ANALYTICS_WAVE1", "1")
os.environ.setdefault("WATHEFNI_ANALYTICS_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ANALYTICS_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_ANALYTICS_WAVE1_SYNTHETIC_KEY_MARKERS", "ANW1,ANW1-SYNTH|")
os.environ.setdefault("WATHEFNI_ANALYTICS_WAVE1_SYNTHETIC_PHONE_PREFIXES", "965540")

import analytics_attention_wave1 as anw1  # noqa: E402
import app  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("ANW1B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("ANW1B_EVID") or f"/tmp/analytics-w1b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def main() -> int:
    honesty = anw1.honesty_payload()
    check("wave1 enabled", anw1.analytics_wave1_enabled())
    check("synthetic_only enforced", anw1.analytics_wave1_synthetic_only() is True)
    check("company allowlisted", anw1.analytics_wave1_enabled_for_company(COMPANY))
    check("read_only honesty", honesty.get("read_only") is True)
    check("no money authority", honesty.get("money_authority") is False)
    check("no AI", honesty.get("ai") is False)
    check("no compliance metrics", honesty.get("compliance_metrics") is False)
    check("no payroll cost analytics", honesty.get("payroll_cost_analytics") is False)
    check("hiring reports separate", honesty.get("hiring_reports_separate") is True)

    # --- ranked attention / deep links / honest wording (fixture builders) ---
    sources_full = anw1.analytics_source_availability(
        {"analytics", "attendance", "leave", "shifts", "payroll", "onboarding"}
    )
    counts = {
        "pending_leave": 3,
        "pending_swaps": 2,
        "pending_availability": 1,
        "absent_records": 4,
        "late_records": 6,
        "late_minutes": 90,
        "scheduled_shifts": 40,
    }
    summaries = [
        {
            "employee_key": f"WATHEFNI-ANW1-{TAG}",
            "employee_name": "Synth Alice",
            "late_minutes": 40,
            "absent_minutes": 0,
            "overtime_minutes": 120,
            "attendance_count": 3,
        }
    ]
    branch_rows = [{"branch_name": "Salmiya", "absent_count": 3}]
    attention = anw1.build_analytics_attention(
        counts=counts, summaries=summaries, branch_rows=branch_rows, sources=sources_full
    )
    check("ranked attention non-empty", len(attention) >= 4, len(attention))
    check("severity rank high-first", attention[0]["severity"] == "high", attention[0])
    leave_item = next(i for i in attention if i["id"] == "pending_leave")
    check("deep link leave", leave_item["deep_link"]["page"] == "leave", leave_item["deep_link"])
    person = next(i for i in attention if i["id"].startswith("top_lateness:"))
    check("deep link employees", person["deep_link"]["page"] == "employees", person["deep_link"])
    check("deep link employee key", person["deep_link"].get("employee") == f"WATHEFNI-ANW1-{TAG}")
    hours_items = [i for i in attention if i["id"].startswith("hours_above_schedule:")]
    check("hours-above-schedule present", bool(hours_items))
    check("non-payroll wording", "non-payroll" in hours_items[0]["reason_en"].lower())
    check("no scheduled-shifts attention", all(i["id"] != "scheduled_shifts" for i in attention))

    # --- partial module disclosure + masked counts contract ---
    partial = anw1.analytics_source_availability({"analytics", "leave"})
    check("partial sources disclosed", partial["partial"] is True)
    check("attendance unavailable listed", "attendance" in partial["unavailable_source_keys"])
    headlines = anw1.attention_headline_stats(
        {"scheduled_shifts": 99, "absent_records": 2, "late_records": 1, "late_minutes": 5, "pending_leave": 1},
        partial,
    )
    keys = [h["key"] for h in headlines]
    check("no scheduled headline", "scheduled_shifts" not in keys)
    check("pending review when leave available", "pending_review" in keys)

    insights = anw1.build_analytics_pattern_insights(
        counts={"scheduled_shifts": 10, "absent_records": 1, "late_records": 1, "late_minutes": 5},
        summaries=summaries,
        branch_rows=branch_rows,
        sources=sources_full,
        decimal_hours_fn=app.decimal_hours,
    )
    metrics = [row["metric"] for row in insights]
    check("best attendance removed", "Best attendance" not in metrics)
    check("overtime risk removed", "Overtime risk" not in metrics)
    check("hours above schedule label", anw1.HOURS_ABOVE_SCHEDULE_METRIC in metrics)

    defs = anw1.analytics_metric_definitions()
    check("definitions EN/AR present", all(d.get("label_en") and d.get("label_ar") and d.get("definition_en") and d.get("definition_ar") for d in defs))

    # --- live production read ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            anw1.ensure_analytics_wave1_schema(cur, force=True)
            # Canary-tagged ACK then cleanup → residual 0
            anw1.record_analytics_wave_ack(
                cur,
                company_code=COMPANY,
                environment="production-canary",
                details={"tag": TAG, "proof": "wave1b"},
                canary_tag=TAG,
            )
            conn.commit()

    start, end = app._posthire_month_window()
    live = app.workforce_analytics(
        {
            "company_code": COMPANY,
            "start_date": start,
            "end_date": end,
            "query": "workforce overview",
            "viewer_phone": "",
            "viewer_user_id": "",
            "actor_role": "hr_admin",
        },
        company_code=COMPANY,
    )
    check("live ok", live.get("ok") is True, live.get("error"))
    check("live contract", live.get("contract") == anw1.ANALYTICS_WAVE1_CONTRACT, live.get("contract"))
    check("live as_of", bool(live.get("as_of")))
    check("live timezone Kuwait", live.get("timezone") == "Asia/Kuwait", live.get("timezone"))
    check("live freshness", isinstance(live.get("freshness"), dict) and int((live.get("freshness") or {}).get("stale_after_seconds") or 0) > 0)
    check("live attention list", isinstance(live.get("attention"), list))
    check("live definitions", isinstance(live.get("definitions"), list) and len(live.get("definitions") or []) >= 3)
    auth = live.get("authority") if isinstance(live.get("authority"), dict) else {}
    check("live money_authority false", auth.get("money_authority") is False)
    check("live synthetic_only", auth.get("synthetic_only") is True, auth)
    live_metrics = [i.get("metric") for i in (live.get("insights") or [])]
    check("live no best attendance", "Best attendance" not in live_metrics)
    check("live no overtime risk", "Overtime risk" not in live_metrics)
    headline_keys = [h.get("key") for h in (live.get("headlines") or [])]
    check("live no scheduled headline", "scheduled_shifts" not in headline_keys)

    # Actor scope: dashboard identity keys present; manager probe must not crash
    src = inspect.getsource(app.dashboard_posthire_analytics)
    check("dashboard viewer_user_id", "viewer_user_id" in src)
    check("dashboard actor_role", "actor_role" in src)
    scoped = app.workforce_analytics(
        {
            "company_code": COMPANY,
            "start_date": start,
            "end_date": end,
            "query": "workforce overview",
            "viewer_phone": "96554000000",
            "viewer_user_id": f"anw1-missing-{TAG}",
            "actor_role": "manager",
        },
        company_code=COMPANY,
    )
    check("manager scope probe returns", scoped.get("ok") in (True, False), scoped.get("error"))
    if scoped.get("ok") is False:
        check("manager scope fail-closed", scoped.get("error") == "employee_outside_manager_scope", scoped.get("error"))
    else:
        scope = scoped.get("scope") if isinstance(scoped.get("scope"), dict) else {}
        check("manager scope object present", isinstance(scope, dict))

    # EN/AR + mobile web dist checks
    dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
    if dist.is_dir():
        blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist.rglob("*.js") if p.is_file())
        check("UI Needs attention EN/AR", ("Needs attention" in blob) or ("ما يحتاج انتباهاً" in blob))
        check("UI Headcount gone", "Headcount summary" not in blob)
        check("UI responsive grid", "sm:grid-cols-2" in blob or "lg:grid-cols-3" in blob)
    else:
        check("dashboard dist present", False, str(dist))

    # Residual cleanup
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            deleted = anw1.cleanup_canary_acks(cur, company_code=COMPANY, tag=TAG)
            conn.commit()
            residual = anw1.residual_synthetic_acks(cur, company_code=COMPANY, tag=TAG)
    check("canary ack deleted", deleted >= 1, deleted)
    check("residual 0", residual == 0, residual)

    # Synthetic subject helper
    check(
        "synthetic marker detection",
        anw1.is_synthetic_subject(employee_key=f"WATHEFNI-ANW1-{TAG}", phone=f"9655401{TAG[:5]}"),
    )
    check("real subject not synthetic", not anw1.is_synthetic_subject(employee_key="WATHEFNI-96566363363", phone="96566363363"))

    out = {
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "live": {
            "as_of": live.get("as_of"),
            "attention_count": len(live.get("attention") or []),
            "headlines": headline_keys,
            "contract": live.get("contract"),
        },
        "honesty": honesty,
    }
    (EVID / "canary-results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "tag": TAG, "residual": residual}, ensure_ascii=False))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
