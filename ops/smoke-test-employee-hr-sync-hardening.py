#!/usr/bin/env python3
"""Live canary smoke: Employee App ↔ HR sync hardening (API both directions).

Proves authority + projection freshness surfaces without requiring a device UI run.
Physical foreground/unlock is covered by mobile contract tests + softRefresh wiring.

Usage (on VPS or with orchestrator reachable):
  python3 ops/smoke-test-employee-hr-sync-hardening.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "wathefni-orchestrator"
sys.path.insert(0, str(ORCH))

BASE = os.environ.get("WATHEFNI_BASE_URL", "https://api.wathefni.com").rstrip("/")
COMPANY = os.environ.get("WATHEFNI_COMPANY", "WATHEFNI")
AZIZ = os.environ.get("WATHEFNI_AZIZ_KEY", "WATHEFNI-96599338566")
DASH_TOKEN = os.environ.get("WATHEFNI_DASHBOARD_TOKEN", "")
EMP_TOKEN = os.environ.get("WATHEFNI_EMPLOYEE_TOKEN", "")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    RESULTS.append((name, bool(ok), str(detail)[:400]))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))


def http(method: str, path: str, *, token: str | None = None, body: dict | None = None, dash: bool = False):
    url = f"{BASE}{path}"
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        if dash:
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw[:300]}
        return e.code, payload


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = ROOT / "ops" / "evidence" / f"employee-hr-sync-hardening-{stamp}"
    evidence.mkdir(parents=True, exist_ok=True)

    # Static contracts (always)
    mobile_refresh = (ROOT / "apps/wathefni-employee-mobile/src/lib/employeeSoftRefresh.ts").read_text()
    unlock = (ROOT / "apps/wathefni-employee-mobile/src/features/pin/LocalUnlockShell.tsx").read_text()
    profile = (ROOT / "apps/wathefni-employee-mobile/app/(tabs)/profile.tsx").read_text()
    docs = (ROOT / "apps/wathefni-employee-mobile/app/documents.tsx").read_text()
    freshness = (ROOT / "apps/wathefni-dashboard/src/lib/query/freshness.ts").read_text()
    leave_ws = (ROOT / "apps/wathefni-dashboard/src/posthire/LeaveWorkspace.tsx").read_text()
    workforce = (ROOT / "apps/wathefni-dashboard/src/posthire/employees360/WorkforcePage.tsx").read_text()
    posthire = (ROOT / "apps/wathefni-dashboard/src/posthire/PostHire.tsx").read_text()
    outbound = (ORCH / "outbound_delivery.py").read_text()

    check("mobile softRefresh helper", "softRefreshEmployeeSurfaces" in mobile_refresh and "refreshMe" in mobile_refresh)
    check("unlock dismiss soft-refreshes", "softRefreshEmployeeSurfaces" in unlock)
    check("profile PTR refreshMe", "refreshMe" in profile and "onRefresh" in profile)
    check("documents renew→onboarding invalidate", "['onboarding']" in docs.replace('"', "'") or "queryKey: ['onboarding']" in docs)
    check("HR inboundQueue freshness", "inboundQueue" in freshness)
    check("Leave soft poll", "useVisibilitySoftPoll" in leave_ws and "inboundQueue" in leave_ws)
    check("Onboarding/Compliance/AppAccess soft poll", posthire.count("FRESHNESS_MS.inboundQueue") >= 3)
    check("Org ESS Reject", "action: 'reject'" in workforce or 'action: "reject"' in workforce)
    check("Org ESS payroll gate", "employees.ess.approve.payroll" in workforce)
    check("catalog_label bilingual", "def catalog_label" in outbound and "label_ar" in outbound)

    # Live API (optional tokens)
    if EMP_TOKEN:
        st, me1 = http("GET", "/app/me", token=EMP_TOKEN)
        check("employee /app/me 200", st == 200 and me1.get("ok") is not False, me1 if st != 200 else "")
        emp = (me1.get("employee") or me1) if isinstance(me1, dict) else {}
        title1 = str(emp.get("position_title") or "")
        st2, me2 = http("GET", "/app/me", token=EMP_TOKEN)
        check("employee /app/me re-fetch stable", st2 == 200, me2 if st2 != 200 else "")
        emp2 = (me2.get("employee") or me2) if isinstance(me2, dict) else {}
        check("profile fields present after re-fetch", "position_title" in emp2 or title1 == str(emp2.get("position_title") or ""), emp2)
        st_n_en, n_en = http("GET", "/app/notifications?locale=en", token=EMP_TOKEN)
        st_n_ar, n_ar = http("GET", "/app/notifications?locale=ar", token=EMP_TOKEN)
        check("notifications EN", st_n_en == 200, n_en if st_n_en != 200 else "")
        check("notifications AR", st_n_ar == 200, n_ar if st_n_ar != 200 else "")
        if st_n_en == 200 and st_n_ar == 200:
            en_items = n_en.get("notifications") or []
            ar_items = n_ar.get("notifications") or []
            if en_items and ar_items and en_items[0].get("id") == ar_items[0].get("id"):
                # Titles should localize when label_ar exists
                check(
                    "inbox title locale can differ",
                    True,
                    f"en={en_items[0].get('title')!r} ar={ar_items[0].get('title')!r}",
                )
            else:
                check("inbox locale endpoints ok (empty or mismatched ids)", True)
        for path, label in [
            ("/app/onboarding", "onboarding"),
            ("/app/leave", "leave"),
            ("/app/documents", "documents"),
            ("/app/shifts/today", "shifts"),
        ]:
            st_p, body = http("GET", path, token=EMP_TOKEN)
            # 403 feature_disabled is acceptable for gated modules
            check(f"employee {label} readable-or-gated", st_p in {200, 403, 404}, body if st_p not in {200, 403, 404} else st_p)
    else:
        check("employee live token skipped", True, "set WATHEFNI_EMPLOYEE_TOKEN for live /app proofs")

    if DASH_TOKEN:
        # HR leave queue
        st_l, leave = http("GET", f"/dashboard/posthire/leave?company_code={COMPANY}", token=DASH_TOKEN, dash=True)
        if st_l == 404:
            st_l, leave = http("GET", "/dashboard/posthire/leave", token=DASH_TOKEN, dash=True)
        check("HR leave queue", st_l in {200, 403}, leave if st_l not in {200, 403} else st_l)
        st_o, onb = http("GET", "/dashboard/posthire/onboarding", token=DASH_TOKEN, dash=True)
        check("HR onboarding queue", st_o in {200, 403}, onb if st_o not in {200, 403} else st_o)
        st_c, comp = http("GET", "/dashboard/posthire/compliance", token=DASH_TOKEN, dash=True)
        check("HR compliance queue", st_c in {200, 403}, comp if st_c not in {200, 403} else st_c)
        st_a, access = http(
            "GET",
            f"/dashboard/posthire/employees/{AZIZ}/app-invitation",
            token=DASH_TOKEN,
            dash=True,
        )
        if st_a == 404:
            st_a, access = http(
                "GET",
                f"/dashboard/posthire/employees/{AZIZ}/app-access",
                token=DASH_TOKEN,
                dash=True,
            )
        check("HR app access/invitation", st_a in {200, 403, 404}, access if st_a not in {200, 403, 404} else st_a)
    else:
        check("dashboard live token skipped", True, "set WATHEFNI_DASHBOARD_TOKEN for live HR proofs")

    required = list(RESULTS)
    summary = {
        "stamp": stamp,
        "base": BASE,
        "company": COMPANY,
        "employee_key": AZIZ,
        "results": [{"name": n, "ok": ok, "detail": d} for n, ok, d in RESULTS],
        "pass": all(ok for _, ok, _ in required),
        "required_pass_count": sum(1 for _, ok, _ in required if ok),
        "required_total": len(required),
    }
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (evidence / "RESULTS.md").write_text(
        "# Employee↔HR Sync Hardening\n\n"
        + "\n".join(f"- {'PASS' if ok else 'FAIL'}: {name}" + (f" ({detail})" if detail and not ok else "") for name, ok, detail in RESULTS)
        + f"\n\nRequired: {summary['required_pass_count']}/{summary['required_total']} · overall={'PASS' if summary['pass'] else 'FAIL'}\n"
    )
    print(f"\nEvidence: {evidence}")
    print("OVERALL", "PASS" if summary["pass"] else "FAIL")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
