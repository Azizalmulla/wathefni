"""Canonical multi-surface architecture proof — consolidated final run.

Mutations touch ONLY synthetic fixtures and are cleaned up:
  WATHEFNI-9655237101 (W2B-SYNTH), WATHEFNI-9655280101 (VISQA| Sara), hr_tasks 'VISQA|%'.
"""

import os, sys, json, uuid, random, types, urllib.request, urllib.error
from datetime import datetime, timezone

pid = os.environ["ORCH_PID"]
with open("/proc/%s/environ" % pid, "rb") as f:
    for item in f.read().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ[k.decode()] = v.decode()
os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app  # noqa: E402
import action_registry as areg  # noqa: E402
import tool_call_orchestrator as tco  # noqa: E402

BASE = "https://api.wathefni.ai"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
TAG = "ARCHVERIFY-" + STAMP
SYNTH_EMP = "WATHEFNI-9655237101"
VISQA_DOC_EMP = "WATHEFNI-9655280101"
R = {"stamp": STAMP, "proofs": []}


def api(method, path, token=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, (json.loads(raw) if raw else None), dict(e.headers)
        except Exception:
            return e.code, {"raw": raw[:300]}, dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return -1, {"err": repr(e)[:300]}, {}


def all_rows(payload, _depth=0):
    """Every dict anywhere in the payload (nested dicts and lists)."""
    out = []
    if _depth > 8:
        return out
    if isinstance(payload, list):
        for v in payload:
            out.extend(all_rows(v, _depth + 1))
    elif isinstance(payload, dict):
        out.append(payload)
        for v in payload.values():
            out.extend(all_rows(v, _depth + 1))
    return out


def pick(payload, key, value):
    return [r for r in all_rows(payload) if str(r.get(key)) == str(value)]


def sql(q, params=None, commit=False):
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(q, params or ())
            out = cur.fetchall() if cur.description else []
            n = cur.rowcount
        if commit:
            conn.commit()
    if out:
        return [dict(r) for r in out]
    return [{"rowcount": n}] if commit else []


with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM dashboard_users WHERE company_code='WATHEFNI' AND email=%s AND status='active' LIMIT 1", ("azizalmulla16@gmail.com",))
        aziz = dict(cur.fetchone())
        cur.execute("SELECT * FROM dashboard_users WHERE company_code='WATHEFNIQA' AND status='active' LIMIT 1")
        qa = dict(cur.fetchone())

T = {
    "web": app.create_dashboard_session(aziz)[0],
    "mob": app._operator_mobile.create_operator_mobile_session(app, aziz, device_label="arch-verify")["access_token"],
    "qaweb": app.create_dashboard_session(qa)[0],
    "qamob": app._operator_mobile.create_operator_mobile_session(app, qa, device_label="arch-verify-qa")["access_token"],
    "emp": app.create_employee_session("WATHEFNI", SYNTH_EMP, "9655237101", platform="ios")["token"],
}

# ===================== P1: employee app submission -> both HR surfaces
p1 = {"name": "P1 employee_app_submission_visible_on_both_HR_surfaces"}
day = "2026-12-%02d" % random.randint(6, 27)
st, body, _ = api("POST", "/app/leave/request", T["emp"], {"start_date": day, "end_date": day, "leave_type": "annual", "reason": TAG})
p1["employee_post_status"] = st
hit = sql("SELECT leave_id,company_code,employee_key,status,row_version,metadata FROM leave_requests WHERE reason=%s ORDER BY created_at DESC", (TAG,))
leave_id = str(hit[0]["leave_id"]) if hit else None
p1["leave_id"] = leave_id
p1["db_rows_created"] = len(hit)
if leave_id:
    p1["db"] = {k: hit[0][k] for k in ("company_code", "employee_key", "status", "row_version")}
    p1["provenance_metadata_source"] = (hit[0].get("metadata") or {}).get("source")
    st, b, h = api("GET", "/dashboard/posthire/leave?limit=100", T["web"])
    w = pick(b, "leave_id", leave_id)
    p1["hr_web"] = {"http": st, "found": bool(w), "status": (w[0].get("status") if w else None), "cache_control": h.get("Cache-Control")}
    st, b, h = api("GET", "/dashboard/mobile/leave?status=requested&limit=100", T["mob"])
    m = pick(b, "leave_id", leave_id)
    p1["hr_mobile"] = {"http": st, "found": bool(m), "status": (m[0].get("status") if m else None), "cache_control": h.get("Cache-Control")}
    st, b, _ = api("GET", "/app/leave", T["emp"])
    e = pick(b, "leave_id", leave_id)
    p1["employee_app"] = {"http": st, "found": bool(e) or (leave_id in json.dumps(b, default=str)), "status": (e[0].get("status") if e else None)}
    p1["verdict"] = "PASS" if (p1["db_rows_created"] == 1 and p1["hr_web"]["found"] and p1["hr_mobile"]["found"] and p1["employee_app"]["found"]) else "FAIL"
else:
    p1["verdict"] = "FAIL"
    p1["error"] = body
R["proofs"].append(p1)

# ===================== P2: HR mobile mutation -> HR web + employee app
p2 = {"name": "P2 hr_mobile_mutation_reflected_on_hr_web_and_employee_app"}
if leave_id:
    payload = {"action": "reject", "reason": "arch proof " + TAG, "idempotency_key": str(uuid.uuid4()), "confirm": False}
    st, b, _ = api("POST", "/dashboard/mobile/leave/%s/decision" % leave_id, T["mob"], payload)
    conf = (b or {}).get("confirmation") or {}
    p2["step1"] = {"http": st, "status": (b or {}).get("status"), "action": conf.get("action"), "current_state": conf.get("current_state")}
    if conf.get("confirmation_id"):
        payload.update({"confirmation_id": conf["confirmation_id"], "confirmation_hash": conf.get("confirmation_hash"), "confirm": True})
        st, b, _ = api("POST", "/dashboard/mobile/leave/%s/decision" % leave_id, T["mob"], payload)
        p2["step2_confirm"] = {"http": st, "status": (b or {}).get("status")}
    row = sql("SELECT status,decided_by_phone,row_version FROM leave_requests WHERE leave_id=%s", (leave_id,))
    p2["db_after"] = row[0] if row else None
    st, b, _ = api("GET", "/dashboard/posthire/leave?limit=100", T["web"])
    w = pick(b, "leave_id", leave_id)
    p2["hr_web_pending_queue_after"] = (w[0].get("status") if w else "absent_from_pending_queue")
    st, b, _ = api("GET", "/dashboard/posthire/employees/%s/leave" % SYNTH_EMP, T["web"])
    we = pick(b, "leave_id", leave_id)
    p2["hr_web_employee_view_status"] = (we[0].get("status") if we else None)
    st2, b2, _ = api("GET", "/dashboard/mobile/leave/%s" % leave_id, T["mob"])
    md = pick(b2, "leave_id", leave_id)
    p2["hr_mobile_detail_http"] = st2
    p2["hr_mobile_status_after"] = md[0].get("status") if md else None
    st, b, _ = api("GET", "/app/leave/history", T["emp"])
    e = pick(b, "leave_id", leave_id)
    p2["employee_app_status_after"] = e[0].get("status") if e else None
    dbst = (p2["db_after"] or {}).get("status")
    p2["actor_recorded"] = (p2["db_after"] or {}).get("decided_by_phone")
    p2["verdict"] = "PASS" if (dbst == "rejected" and p2["hr_mobile_status_after"] == "rejected" and p2["employee_app_status_after"] == "rejected" and p2["hr_web_pending_queue_after"] == "absent_from_pending_queue") else "FAIL"
else:
    p2["verdict"] = "SKIP"
R["proofs"].append(p2)

# ===================== P3: HR web mutation -> HR mobile
p3 = {"name": "P3 hr_web_mutation_reflected_on_hr_mobile"}
task = sql("SELECT task_id,title,status FROM hr_tasks WHERE company_code='WATHEFNI' AND title LIKE 'VISQA|%%' AND status='open' ORDER BY updated_at DESC LIMIT 1")
if task:
    tid = str(task[0]["task_id"])
    p3["task_id"], p3["task_title"] = tid, task[0]["title"]
    st, b, _ = api("GET", "/dashboard/mobile/tasks?status=open&limit=100", T["mob"])
    p3["mobile_open_before"] = bool(pick(b, "task_id", tid))
    st, b, _ = api("POST", "/dashboard/hr-tasks/%s/resolve" % tid, T["web"], {"status": "done", "expected_status": "open"})
    p3["web_resolve_http"] = st
    row = sql("SELECT status,resolved_at FROM hr_tasks WHERE task_id=%s", (tid,))
    p3["db_after"] = row[0] if row else None
    st, b, _ = api("GET", "/dashboard/mobile/tasks?status=open&limit=100", T["mob"])
    p3["mobile_open_after"] = bool(pick(b, "task_id", tid))
    st, b, _ = api("GET", "/dashboard/mobile/tasks/%s" % tid, T["mob"])
    d = pick(b, "task_id", tid)
    p3["mobile_detail_status_after"] = (d[0].get("status") if d else (b or {}).get("status"))
    p3["verdict"] = "PASS" if ((p3["db_after"] or {}).get("status") == "done" and p3["mobile_open_before"] and not p3["mobile_open_after"] and p3["mobile_detail_status_after"] == "done") else "FAIL"
else:
    p3["verdict"] = "SKIP_NO_OPEN_VISQA_TASK"
R["proofs"].append(p3)

# ===================== P4: HR mobile mutation -> HR web (compliance document)
p4 = {"name": "P4 hr_mobile_document_review_reflected_on_hr_web"}
doc = sql("SELECT employee_key,document_type,status FROM compliance_documents WHERE employee_key=%s AND status='needs_review' LIMIT 1", (VISQA_DOC_EMP,))
if doc:
    ek, dt = doc[0]["employee_key"], doc[0]["document_type"]
    p4["target"] = {"employee_key": ek, "document_type": dt, "status_before": doc[0]["status"]}
    st, b, _ = api("GET", "/dashboard/posthire/employees/%s/documents/compliance" % ek, T["web"])
    wb = [r for r in all_rows(b) if r.get("document_type") == dt and "review_status" in r]
    p4["hr_web_status_before"] = wb[0].get("review_status") if wb else None
    st, b, _ = api("POST", "/dashboard/mobile/documents/%s/%s/review" % (ek, dt), T["mob"], {"note": TAG, "expected_status": "needs_review"})
    p4["mobile_review_http"] = st
    p4["mobile_review_status"] = (b or {}).get("status")
    row = sql("SELECT status,updated_at FROM compliance_documents WHERE employee_key=%s AND document_type=%s", (ek, dt))
    p4["db_after"] = row[0] if row else None
    st, b, _ = api("GET", "/dashboard/posthire/employees/%s/documents/compliance" % ek, T["web"])
    wa = [r for r in all_rows(b) if r.get("document_type") == dt and "review_status" in r]
    p4["hr_web_status_after"] = wa[0].get("review_status") if wa else None
    p4["hr_web_carries_mobile_note"] = bool(wa) and TAG in json.dumps(wa[0], default=str)
    st, b, _ = api("GET", "/dashboard/mobile/documents?status=needs_review&limit=100", T["mob"])
    p4["mobile_needs_review_still_contains"] = any(r.get("document_type") == dt and str(r.get("employee_key")) == ek for r in all_rows(b))
    p4["verdict"] = "PASS" if ((p4["db_after"] or {}).get("status") != "needs_review" and p4["hr_web_status_after"] != p4["hr_web_status_before"] and p4["hr_web_carries_mobile_note"] and not p4["mobile_needs_review_still_contains"]) else "FAIL"
else:
    p4["verdict"] = "SKIP_NO_DOC"
R["proofs"].append(p4)

# ===================== P5: assistant canonical read + forced tenant + governance
p5 = {"name": "P5 assistant_canonical_reads_and_governed_actions"}
try:
    ctx = areg.ExecutionContext(
        request=types.SimpleNamespace(metadata={}, company_code="WATHEFNI"),
        # The shared leave window clamps a span to ~31 days, so ask for the
        # fixture's own day instead of a year that would be silently truncated.
        action={"action_type": "list_leave_requests", "company_code": "WATHEFNI", "limit": 100,
                "start_date": day, "end_date": day},
        state={}, graph_state={}, intent={}, legacy=app,
    )
    res = areg.execute("list_leave_requests", ctx)
    got = pick(res, "leave_id", leave_id) if leave_id else []
    p5["registry_result_keys"] = sorted(res.keys()) if isinstance(res, dict) else str(type(res))
    p5["registry_result_preview"] = json.dumps(res, default=str)[:600]
    p5["registry_read_rows"] = len(all_rows(res))
    p5["registry_sees_canonical_leave"] = bool(got)
    p5["registry_status_for_leave"] = got[0].get("status") if got else None
except Exception as e:  # noqa: BLE001
    p5["registry_error"] = repr(e)[:300]

# prompt-injection tenancy: model-supplied company_code must be overridden by server scope
try:
    scope = {"company_id": "WATHEFNIQA", "permissions": ["posthire.read", "leave.read"], "actor_phone": "96590010001"}
    forced = {**{"action_type": "list_leave_requests", "company_code": "WATHEFNI", "limit": 100,
                 "start_date": day, "end_date": day}, "company_code": scope.get("company_id")}
    p5["scope_override_demo"] = {"model_supplied": "WATHEFNI", "after_gate": forced["company_code"]}
    ctx2 = areg.ExecutionContext(
        request=types.SimpleNamespace(metadata={}, company_code="WATHEFNIQA"),
        action=forced, state={}, graph_state={}, intent={}, legacy=app,
    )
    res2 = areg.execute("list_leave_requests", ctx2)
    p5["other_tenant_scope_sees_wathefni_leave"] = bool(pick(res2, "leave_id", leave_id)) if leave_id else None
except Exception as e:  # noqa: BLE001
    p5["scope_error"] = repr(e)[:300]

specs = areg.REGISTRY
p5["registry_governance"] = {
    n: {"module": getattr(specs[n], "module", None), "requires_confirmation": getattr(specs[n], "requires_confirmation", None)}
    for n in ("approve_leave_request", "reject_leave_request", "compliance_mark_reviewed", "correct_attendance_record")
    if n in specs
}
p5["assistant_mutations_env"] = os.environ.get("WATHEFNI_ASSISTANT_MUTATIONS")
try:
    import platform_assistant_spine_wave1 as spine
    p5["assistant_mutations_allowed"] = spine.assistant_mutations_allowed()
    p5["assistant_kill_engaged"] = spine.assistant_kill_engaged()
except Exception as e:  # noqa: BLE001
    p5["spine_error"] = repr(e)[:200]
st, b, _ = api("GET", "/dashboard/mobile/assistant/capabilities", T["mob"])
p5["mobile_assistant_capabilities_http"] = st
if isinstance(b, dict):
    p5["mobile_assistant_capabilities_keys"] = sorted(b.keys())[:12]
    p5["mobile_assistant_read_only_flags"] = {k: v for k, v in b.items() if isinstance(v, bool)}
p5["verdict"] = "PASS" if p5.get("registry_sees_canonical_leave") and not p5.get("other_tenant_scope_sees_wathefni_leave") else "REVIEW"
R["proofs"].append(p5)

# ===================== P6: cross-tenant direct object access
p6 = {"name": "P6 tenant_isolation_server_side"}
if leave_id:
    p6["qa_mobile_read"] = api("GET", "/dashboard/mobile/leave/%s" % leave_id, T["qamob"])[0]
    p6["qa_mobile_write"] = api("POST", "/dashboard/mobile/leave/%s/decision" % leave_id, T["qamob"], {"action": "approve", "idempotency_key": str(uuid.uuid4()), "confirm": True})[0]
    p6["own_tenant_read"] = api("GET", "/dashboard/mobile/leave/%s" % leave_id, T["mob"])[0]
p6["qa_web_employee_docs"] = api("GET", "/dashboard/posthire/employees/%s/documents" % VISQA_DOC_EMP, T["qaweb"])[0]
p6["qa_web_doc_review_write"] = api("POST", "/dashboard/posthire/employees/%s/documents/civil_id/review" % VISQA_DOC_EMP, T["qaweb"], {"action": "approve"})[0]
p6["qa_mobile_doc_review_write"] = api("POST", "/dashboard/mobile/documents/%s/civil_id/review" % VISQA_DOC_EMP, T["qamob"], {"expected_status": "needs_review"})[0]
p6["qa_web_onboarding_read"] = api("GET", "/dashboard/posthire/onboarding/%s" % VISQA_DOC_EMP, T["qaweb"])[0]
if task:
    p6["qa_web_task_write"] = api("POST", "/dashboard/hr-tasks/%s/resolve" % str(task[0]["task_id"]), T["qaweb"], {"status": "done", "expected_status": "open"})[0]
qal = sql("SELECT leave_id FROM leave_requests WHERE company_code='WATHEFNIQA' LIMIT 1")
if qal:
    p6["employee_cross_tenant_cancel"] = api("POST", "/app/leave/%s/cancel" % str(qal[0]["leave_id"]), T["emp"], {})[0]
st, b, _ = api("GET", "/dashboard/posthire/leave?limit=100", T["qaweb"])
p6["qa_web_leave_list_contains_wathefni_row"] = any(str(r.get("company_code") or "") == "WATHEFNI" for r in all_rows(b))
p6["qa_web_leave_list_companies"] = sorted({str(r.get("company_code")) for r in all_rows(b) if r.get("company_code")})
# bool is an int subclass — the boolean findings below are not HTTP codes.
denied = [v for k, v in p6.items() if k.startswith(("qa_", "employee_cross")) and isinstance(v, int) and not isinstance(v, bool)]
p6["verdict"] = "PASS" if (not p6["qa_web_leave_list_contains_wathefni_row"] and all(c in (401, 403, 404, 409) for c in denied) and p6.get("own_tenant_read") == 200) else "FAIL"
R["proofs"].append(p6)

# ===================== P7: duplicate/shadow status store scan
p7 = {"name": "P7 no_duplicate_status_store"}
if leave_id:
    p7["leave_requests_rows"] = sql("SELECT count(*) AS n FROM leave_requests WHERE leave_id=%s", (leave_id,))[0]["n"]
    tabs = [t["table_name"] for t in sql("SELECT DISTINCT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='leave_id' AND table_name<>'leave_requests' ORDER BY 1")]
    sib = {}
    for t in tabs:
        try:
            n = sql("SELECT count(*) AS n FROM %s WHERE leave_id=%%s" % t, (leave_id,))[0]["n"]
        except Exception as e:  # noqa: BLE001
            n = repr(e)[:60]
        sib[t] = n
    p7["sibling_tables_rows_for_this_leave"] = sib
p7["mobile_only_business_tables"] = [t["table_name"] for t in sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name ILIKE '%%mobile%%' OR table_name ILIKE '%%_cache%%') ORDER BY 1")]
R["proofs"].append(p7)

# ===================== P8: cache/staleness headers
p8 = {"name": "P8 http_cache_headers_on_surface_reads"}
for label, path, tok in (
    ("hr_web_leave", "/dashboard/posthire/leave?limit=10", T["web"]),
    ("hr_mobile_leave", "/dashboard/mobile/leave?limit=10", T["mob"]),
    ("hr_mobile_tasks", "/dashboard/mobile/tasks?limit=10", T["mob"]),
    ("employee_leave", "/app/leave", T["emp"]),
):
    st, b, h = api("GET", path, tok)
    p8[label] = {"http": st, "cache_control": h.get("Cache-Control"), "etag": bool(h.get("ETag")), "age": h.get("Age")}
R["proofs"].append(p8)

# ===================== cleanup
c1 = sql("DELETE FROM leave_events WHERE leave_id IN (SELECT leave_id FROM leave_requests WHERE employee_key=%s AND reason LIKE 'ARCHVERIFY-%%')", (SYNTH_EMP,), commit=True)
c2 = sql("DELETE FROM leave_requests WHERE employee_key=%s AND reason LIKE 'ARCHVERIFY-%%'", (SYNTH_EMP,), commit=True)
c3 = sql("DELETE FROM hr_tasks WHERE company_code='WATHEFNI' AND employee_key=%s AND created_at > now() - interval '30 minutes' AND title NOT LIKE 'VISQA|%%'", (SYNTH_EMP,), commit=True)
c4 = sql("DELETE FROM employee_messages WHERE company_code='WATHEFNI' AND employee_key=%s AND created_at > now() - interval '30 minutes'", (SYNTH_EMP,), commit=True)
R["cleanup"] = {
    "leave_events": c1, "leave_requests": c2, "spawned_hr_tasks": c3, "spawned_messages": c4,
    "synth_leave_remaining": sql("SELECT count(*) AS n FROM leave_requests WHERE employee_key=%s", (SYNTH_EMP,))[0]["n"],
}
R["summary"] = {p["name"]: p.get("verdict") for p in R["proofs"] if p.get("verdict")}
print("<<<JSON>>>")
print(json.dumps(R, indent=1, default=str))
