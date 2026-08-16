#!/usr/bin/env python3
import json, os, time, urllib.error, urllib.request
from pathlib import Path

for line in Path("/tmp/orch-environ.env").read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ[k] = v

import app as A
import employee_bank_ess as B

COMPANY = "WATHEFNI"
AZIZ = "WATHEFNI-96599338566"
OUT = Path("/tmp/aziz-real-bank-acceptance.json")
R = {
    "checks": [],
    "failed": 0,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "defect_fixed": "stale_withdrawn_terminal_history_predating_bank_of_record",
}

def check(name, ok, detail=None):
    R["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        R["failed"] += 1
    print(("PASS" if ok else "FAIL"), name, "::", json.dumps(detail, default=str)[:450])
    return bool(ok)

def http(method, path, *, token=None, hr=None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if hr:
        headers["X-Dashboard-Token"] = hr
        headers["Authorization"] = f"Bearer {hr}"
    req = urllib.request.Request(f"http://127.0.0.1:8010{path}", method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw

def synth(text):
    s = json.dumps(text, default=str)
    return any(n in s for n in ("Walkthrough", "Hsbshshsh", "Snsnbsbsu", "KW30TEST"))

emp = A.find_employee_by_key(AZIZ, company_code=COMPANY)
token = str(A.create_employee_session(COMPANY, AZIZ, str(emp.get("phone")))["token"])
with A.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM dashboard_users
            WHERE company_code=%s
              AND lower(coalesce(role,'')) IN ('owner','admin','hr_admin','hr')
            ORDER BY created_at
            LIMIT 1
            """,
            (COMPANY,),
        )
        hr_user = dict(cur.fetchone() or {})
    conn.commit()
hr = str(A.create_dashboard_session(hr_user)[0])

code_b, bank = http("GET", "/app/bank", token=token)
R["bank"] = bank
disp = ((bank.get("verified") or {}).get("display") or {})
check("/app/bank HTTP 200", code_b == 200, {"http": code_b})
check(
    "Bank shows verified bank of record",
    bank.get("has_verified_bank") is True and isinstance(bank.get("verified"), dict),
    {
        "has_verified_bank": bank.get("has_verified_bank"),
        "bank_name": disp.get("bank_name"),
        "holder": disp.get("account_holder"),
        "iban_last4": disp.get("iban_last4"),
        "verified_by_stage": (bank.get("verified") or {}).get("verified_by_stage"),
    },
)
check(
    "No synthetic Walkthrough/test data remains in /app/bank",
    not synth(bank),
    {
        "bank_name": disp.get("bank_name"),
        "holder": disp.get("account_holder"),
        "iban_last4": disp.get("iban_last4"),
        "submission_state": bank.get("submission_state"),
        "submission": bank.get("submission"),
    },
)
check(
    "Synthetic last4 0000 is not the current verified IBAN",
    str(disp.get("iban_last4") or "") != "0000",
    {"iban_last4": disp.get("iban_last4")},
)
pe = bank.get("payroll_effective")
check("Payroll-effective row present after Apply", isinstance(pe, dict) and bool(pe.get("display")), pe)
sub_state = str(bank.get("submission_state") or "").lower()
sub_raw = str(((bank.get("submission") or {}).get("state") or "")).lower()
check(
    "Submission is none or approved/applied (not stale withdrawn)",
    sub_state in {"approved", "none", ""} or sub_raw == "applied",
    {
        "submission_state": bank.get("submission_state"),
        "submission_state_raw": (bank.get("submission") or {}).get("state"),
        "next_step": bank.get("next_step"),
    },
)

code_a, appb = http("GET", "/app/onboarding", token=token)
code_p, prof = http("GET", "/app/profile", token=token)
code_d, drawer = http("GET", f"/dashboard/posthire/onboarding/{AZIZ}", hr=hr)
code_q, queue = http("GET", "/dashboard/posthire/onboarding?limit=500", hr=hr)

comp_a = (appb.get("completion") or {}) if isinstance(appb, dict) else {}
onb = (prof.get("onboarding") or {}) if isinstance(prof, dict) else {}
comp_p = onb.get("completion") or {}
comp_d = (drawer.get("completion") or {}) if isinstance(drawer, dict) else {}

def tup(c):
    na = c.get("next_action") or {}
    return {
        "state": c.get("state"),
        "satisfied": c.get("satisfied_count"),
        "required": c.get("required_total"),
        "owner": na.get("owner"),
        "message_en": na.get("message_en") or na.get("message"),
    }

app_t = tup(comp_a)
prof_t = tup(comp_p if isinstance(comp_p, dict) else {})
if not prof_t.get("state"):
    prof_t["state"] = onb.get("completion_state")
if not prof_t.get("owner"):
    na = onb.get("next_action") or {}
    prof_t["owner"] = na.get("owner")
    prof_t["message_en"] = na.get("message_en") or na.get("message")
drawer_t = tup(comp_d)

row = None
if isinstance(queue, dict):
    for bucket in ("in_progress", "completed", "not_started", "employees", "items", "data"):
        for r in queue.get(bucket) or []:
            if isinstance(r, dict) and r.get("employee_key") == AZIZ:
                row = r
                break
        if row:
            break
absent = row is None
R["surfaces"] = {
    "employee_app": app_t,
    "employee_profile": prof_t,
    "hr_drawer": drawer_t,
    "hr_queue": {"absent_from_queue": absent},
    "http": {"app": code_a, "profile": code_p, "drawer": code_d, "queue": code_q},
}

check("Onboarding completed on employee app", app_t["state"] == "completed" and app_t["owner"] in {"none", None}, app_t)
check("Onboarding completed on employee profile", prof_t["state"] == "completed" and prof_t["owner"] in {"none", None}, prof_t)
check("Onboarding completed on HR drawer", drawer_t["state"] == "completed" and drawer_t["owner"] in {"none", None}, drawer_t)
check("Absent from active onboarding queue", absent is True, {"absent": absent})

base = (app_t["state"], app_t["satisfied"], app_t["required"], app_t["owner"])
mism = []
for name, t in (("profile", prof_t), ("drawer", drawer_t)):
    got = (t["state"], t["satisfied"], t["required"], t["owner"])
    if got != base:
        mism.append({"name": name, "got": got, "want": base})
check("App / profile / drawer agree on state·progress·owner·next action", len(mism) == 0, {"base": base, "mismatches": mism})

items_d = drawer.get("items") if isinstance(drawer, dict) else None
bank_item = next((i for i in (items_d or []) if i.get("item_id") == "bank_details"), None)
all_items = []
if isinstance(appb, dict):
    for g in ("your_actions", "being_reviewed", "handled_by_others", "completed"):
        for i in appb.get(g) or []:
            all_items.append({**i, "_group": g})
bank_app = next((i for i in all_items if i.get("item_id") == "bank_details"), None)
check(
    "bank_details accepted on HR drawer",
    str((bank_item or {}).get("status") or "").lower() in {"accepted", "complete", "completed", "verified"},
    {"status": (bank_item or {}).get("status")},
)
check(
    "bank_details under completed on employee app",
    (bank_app or {}).get("_group") == "completed",
    {"group": (bank_app or {}).get("_group")},
)

with A.db_connect() as conn:
    with conn.cursor() as cur:
        B.ensure_bank_ess_schema(cur)
        cur.execute(
            """
            SELECT request_id::text, fingerprint, display, superseded_at IS NULL AS live, created_at
            FROM employee_bank_effective
            WHERE company_code=%s AND employee_key=%s
            ORDER BY created_at DESC
            """,
            (COMPANY, AZIZ),
        )
        eff = [dict(r) for r in cur.fetchall() or []]
        live = [e for e in eff if e.get("live")]
        cur.execute(
            """
            SELECT request_id::text, fingerprint, display, revoked_at, verified_at
            FROM employee_bank_verified
            WHERE company_code=%s AND employee_key=%s
            ORDER BY verified_at DESC
            """,
            (COMPANY, AZIZ),
        )
        ver = [dict(r) for r in cur.fetchall() or []]
        live_ver = [v for v in ver if v.get("revoked_at") is None]
        cur.execute(
            """
            SELECT request_id::text, state, updated_at
            FROM employee_ess_requests
            WHERE company_code=%s AND employee_key=%s AND request_type='bank_detail_change'
            ORDER BY updated_at DESC
            """,
            (COMPANY, AZIZ),
        )
        reqs = [dict(r) for r in cur.fetchall() or []]
        reconcile_fn = getattr(B, "reconcile_onboarding_bank_item", None) or getattr(B, "sync_onboarding_bank_item")
        r1 = reconcile_fn(cur, company_code=COMPANY, employee_key=AZIZ)
        r2 = reconcile_fn(cur, company_code=COMPANY, employee_key=AZIZ)
    conn.commit()

R["db"] = {
    "live_effective": live,
    "live_verified_count": len(live_ver),
    "reconcile": {"first": r1, "second": r2},
}
check("Exactly one live effective bank row", len(live) == 1, {"count": len(live)})
check("Live effective is not synthetic", live and not synth(live[0].get("display")), live[0].get("display") if live else None)
check("Current verified is not synthetic", live_ver and not synth(live_ver[0].get("display")), live_ver[0].get("display") if live_ver else None)
check(
    "Reconcile is idempotent (no write)",
    (r1 is None or r1.get("changed") is False) and (r2 is None or r2.get("changed") is False),
    {"first": r1, "second": r2},
)
check(
    "Live fingerprint is not the walkthrough fingerprint",
    (live[0].get("fingerprint") if live else None) != "c4e2fb083889b894",
    {"fingerprint": live[0].get("fingerprint") if live else None},
)
open_states = {"submitted", "pending_hr", "pending_manager", "pending_payroll", "approved", "needs_information", "draft"}
open_reqs = [r for r in reqs if str(r.get("state") or "").lower() in open_states]
check("No open/active bank request remaining", not open_reqs, {"open": open_reqs})

OUT.write_text(json.dumps(R, indent=2, default=str))
print("ACCEPTANCE_PASS" if R["failed"] == 0 else "ACCEPTANCE_FAIL")
print("failed", R["failed"], "of", len(R["checks"]))
raise SystemExit(0 if R["failed"] == 0 else 1)
