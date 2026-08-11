"""Pre-Customer Hardening Wave — live regression proof.

Covers the seven blockers closed in this wave:
  H1 cross-tenant onboarding reads/writes
  H2 candidate null-tenant prevention
  H3 leave source attribution by originating surface
  H4 dual-actor task stale-write rejection
  H5 queue visibility at 30 / >50 items (honest totals + continuation)
  H6 urgent task ordering above high/normal
  H7 HR Web -> HR Mobile convergence without manual pull-to-refresh

Mutations touch synthetic fixtures only and are cleaned up at the end.
"""

import json
import os
import sys
import types
import urllib.error
import urllib.request
import uuid
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
import outbound_delivery as od  # noqa: E402

BASE = "https://api.wathefni.ai"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
TAG = "HARDEN-" + STAMP
SYNTH_EMP = "WATHEFNI-9655237101"
SYNTH_PHONE = "9655237101"
R = {"stamp": STAMP, "proofs": []}


def api(method, path, token=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
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


def make_task(title, priority="normal"):
    """Synthetic HR task via the canonical writer. Returns task_id or ''."""
    return str(
        od.create_hr_task(
            app,
            company_code="WATHEFNI",
            employee_key=SYNTH_EMP,
            title=title,
            detail="pre-customer hardening probe",
            source="hardening_probe",
            priority=priority,
            task_type="general",
        )
        or ""
    )


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
        cur.execute(
            "SELECT * FROM dashboard_users WHERE company_code='WATHEFNI' AND email=%s AND status='active' LIMIT 1",
            ("azizalmulla16@gmail.com",),
        )
        aziz = dict(cur.fetchone())
        cur.execute("SELECT * FROM dashboard_users WHERE company_code='WATHEFNIQA' AND status='active' LIMIT 1")
        qa = dict(cur.fetchone())

T = {
    "web": app.create_dashboard_session(aziz)[0],
    "web2": app.create_dashboard_session(aziz)[0],
    "mob": app._operator_mobile.create_operator_mobile_session(app, aziz, device_label="harden-a")["access_token"],
    "mob2": app._operator_mobile.create_operator_mobile_session(app, aziz, device_label="harden-b")["access_token"],
    "qaweb": app.create_dashboard_session(qa)[0],
    "qamob": app._operator_mobile.create_operator_mobile_session(app, qa, device_label="harden-qa")["access_token"],
    "emp": app.create_employee_session("WATHEFNI", SYNTH_EMP, SYNTH_PHONE, platform="ios")["token"],
}

# ============================ H1 onboarding tenant scoping
h1 = {"name": "H1 onboarding_items_tenant_scoped"}
h1["column_exists"] = bool(
    sql(
        "SELECT 1 AS ok FROM information_schema.columns WHERE table_name='onboarding_items' AND column_name='company_code'"
    )
)
h1["rows_without_company"] = sql("SELECT count(*) AS n FROM onboarding_items WHERE company_code IS NULL")[0]["n"]
h1["mismatched_against_employee"] = sql(
    """
    SELECT count(*) AS n FROM onboarding_items o
    JOIN employees e ON e.employee_key = o.employee_key
    WHERE o.company_code IS DISTINCT FROM e.company_code
    """
)[0]["n"]

# A read with no company argument must not silently span tenants.
try:
    unscoped = app.load_onboarding_items(employee_key=SYNTH_EMP)
    scoped_right = app.load_onboarding_items(employee_key=SYNTH_EMP, company_code="WATHEFNI")
    scoped_wrong = app.load_onboarding_items(employee_key=SYNTH_EMP, company_code="WATHEFNIQA")
    h1["reads"] = {
        "no_company_argument": len(unscoped or []),
        "owning_tenant": len(scoped_right or []),
        "other_tenant": len(scoped_wrong or []),
    }
    # Omitting the argument must resolve the owner, never span tenants.
    h1["unscoped_read_is_owner_scoped"] = len(unscoped or []) == len(scoped_right or [])
    h1["other_tenant_read_empty"] = len(scoped_wrong or []) == 0
except Exception as e:  # noqa: BLE001
    h1["unscoped_read_error"] = repr(e)[:200]

# Cross-tenant read/write over HTTP from the QA tenant.
h1["qa_web_onboarding_read"] = api("GET", "/dashboard/posthire/onboarding/%s" % SYNTH_EMP, T["qaweb"])[0]
h1["qa_mobile_onboarding_read"] = api("GET", "/dashboard/mobile/onboarding/%s" % SYNTH_EMP, T["qamob"])[0]
item = sql(
    "SELECT item_id, status, company_code FROM onboarding_items WHERE employee_key=%s ORDER BY item_id LIMIT 1",
    (SYNTH_EMP,),
)
if item:
    key = item[0]["item_id"]
    h1["target_item"] = {"item_id": key, "status_before": item[0]["status"], "company_code": item[0]["company_code"]}
    h1["qa_mobile_onboarding_write"] = api(
        "POST",
        "/dashboard/mobile/onboarding/%s/review" % SYNTH_EMP,
        T["qamob"],
        {
            "item_id": key,
            "outcome": "accepted",
            "idempotency_key": str(uuid.uuid4()),
            "confirm": True,
        },
    )[0]
    after = sql(
        "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s", (SYNTH_EMP, key)
    )
    h1["status_after_cross_tenant_writes"] = after[0]["status"] if after else None
    h1["cross_tenant_write_had_no_effect"] = (
        h1["status_after_cross_tenant_writes"] == h1["target_item"]["status_before"]
    )
    # Direct writer call carrying the wrong tenant must refuse, not write.
    try:
        wrong = app.mark_onboarding_item(
            {"employee_key": SYNTH_EMP, "item_id": key, "item_status": "accepted"},
            company_code="WATHEFNIQA",
            created_by_phone="96590010001",
        )
        h1["writer_wrong_tenant_result"] = json.dumps(wrong, default=str)[:200]
        h1["writer_wrong_tenant_refused"] = not bool(
            isinstance(wrong, dict) and wrong.get("ok")
        )
    except Exception as e:  # noqa: BLE001
        h1["writer_wrong_tenant_result"] = "raised:" + repr(e)[:160]
        h1["writer_wrong_tenant_refused"] = True
    after2 = sql("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s", (SYNTH_EMP, key))
    h1["status_after_direct_wrong_tenant_write"] = after2[0]["status"] if after2 else None

# A schema rejection would prove nothing about tenancy, so 422 is not accepted here.
denied_h1 = [
    v
    for k, v in h1.items()
    if k.startswith("qa_") and isinstance(v, int) and not isinstance(v, bool)
]
h1["verdict"] = (
    "PASS"
    if (
        h1["column_exists"]
        and h1["rows_without_company"] == 0
        and h1["mismatched_against_employee"] == 0
        and all(c in (401, 403, 404, 409) for c in denied_h1)
        and h1.get("cross_tenant_write_had_no_effect", False)
        and h1.get("writer_wrong_tenant_refused", False)
        and h1.get("status_after_direct_wrong_tenant_write") == h1.get("target_item", {}).get("status_before")
        and h1.get("unscoped_read_is_owner_scoped", False)
        and h1.get("other_tenant_read_empty", False)
    )
    else "FAIL"
)
R["proofs"].append(h1)

# ============================ H2 candidate tenant integrity
h2 = {"name": "H2 candidate_tenant_non_null_enforced"}
h2["null_rows"] = sql("SELECT count(*) AS n FROM candidates WHERE active_company_code IS NULL")[0]["n"]
h2["column_nullable"] = sql(
    "SELECT is_nullable FROM information_schema.columns WHERE table_name='candidates' AND column_name='active_company_code'"
)[0]["is_nullable"]
probe_phone = "96555" + STAMP[-6:]
try:
    sql(
        "INSERT INTO candidates (phone, name, active_company_code) VALUES (%s, %s, NULL)",
        (probe_phone, TAG),
        commit=True,
    )
    h2["db_accepted_null_tenant"] = True
    sql("DELETE FROM candidates WHERE phone=%s", (probe_phone,), commit=True)
except Exception as e:  # noqa: BLE001
    h2["db_accepted_null_tenant"] = False
    h2["db_rejection"] = repr(e)[:160]
# Application layer must fail closed before it ever reaches the constraint.
try:
    from pathlib import Path as _Path

    with app.db_connect() as _conn:
        with _conn.cursor() as _cur:
            imported = app.register_imported_cv(
                _cur,
                company_code="",
                batch_id="harden-" + STAMP,
                source_path=_Path("/tmp/harden-probe.pdf"),
                original_filename="harden-probe.pdf",
                candidate_name=TAG,
                candidate_phone=probe_phone,
            )
        _conn.rollback()
    h2["app_layer_result"] = json.dumps(imported, default=str)[:200]
    h2["app_layer_accepted_missing_company"] = bool(imported.get("ok"))
except Exception as e:  # noqa: BLE001
    h2["app_layer_accepted_missing_company"] = False
    h2["app_layer_rejection"] = repr(e)[:160]
sql("DELETE FROM candidates WHERE phone=%s", (probe_phone,), commit=True)
h2["verdict"] = (
    "PASS"
    if (
        h2["null_rows"] == 0
        and h2["column_nullable"] == "NO"
        and not h2["db_accepted_null_tenant"]
        and not h2["app_layer_accepted_missing_company"]
    )
    else "FAIL"
)
R["proofs"].append(h2)

# ============================ H3 leave provenance by surface
h3 = {"name": "H3 leave_source_attribution_by_surface"}
h3["surfaces"] = {}


def leave_source(reason):
    rows = sql(
        "SELECT leave_id, metadata FROM leave_requests WHERE reason=%s ORDER BY created_at DESC LIMIT 1", (reason,)
    )
    if not rows:
        return None, None
    return str(rows[0]["leave_id"]), (rows[0].get("metadata") or {}).get("source")


emp_reason = TAG + "-employee_app"
st, _, _ = api(
    "POST",
    "/app/leave/request",
    T["emp"],
    {"start_date": "2026-12-14", "end_date": "2026-12-14", "leave_type": "annual", "reason": emp_reason},
)
lid_emp, src_emp = leave_source(emp_reason)
h3["surfaces"]["employee_app"] = {"http": st, "leave_id": lid_emp, "metadata_source": src_emp}

asst_reason = TAG + "-assistant"
try:
    ctx = areg.ExecutionContext(
        request=types.SimpleNamespace(metadata={}, company_code="WATHEFNI"),
        action={
            "action_type": "request_leave",
            "company_code": "WATHEFNI",
            "employee_key": SYNTH_EMP,
            "phone": SYNTH_PHONE,
            "start_date": "2026-12-15",
            "end_date": "2026-12-15",
            "leave_type": "annual",
            "reason": asst_reason,
        },
        state={},
        graph_state={},
        intent={},
        legacy=app,
    )
    areg.execute("request_leave", ctx)
except Exception as e:  # noqa: BLE001
    h3["assistant_error"] = repr(e)[:200]
lid_asst, src_asst = leave_source(asst_reason)
h3["surfaces"]["assistant"] = {"leave_id": lid_asst, "metadata_source": src_asst}

wa_reason = TAG + "-whatsapp"
try:
    res = app.request_leave(
        {
            "employee_key": SYNTH_EMP,
            "phone": SYNTH_PHONE,
            "start_date": "2026-12-16",
            "end_date": "2026-12-16",
            "leave_type": "annual",
            "reason": wa_reason,
        },
        company_code="WATHEFNI",
        created_by_phone=SYNTH_PHONE,
        origin_surface="whatsapp",
    )
    h3["whatsapp_writer_result"] = json.dumps(res, default=str)[:160]
except Exception as e:  # noqa: BLE001
    h3["whatsapp_error"] = repr(e)[:200]
lid_wa, src_wa = leave_source(wa_reason)
h3["surfaces"]["whatsapp"] = {"leave_id": lid_wa, "metadata_source": src_wa}

h3["distinct_sources"] = sorted({v.get("metadata_source") for v in h3["surfaces"].values() if v.get("metadata_source")})
h3["verdict"] = (
    "PASS"
    if (
        h3["surfaces"]["employee_app"]["metadata_source"] == "employee_app"
        and h3["surfaces"]["whatsapp"]["metadata_source"] == "whatsapp"
        and h3["surfaces"]["assistant"]["metadata_source"] in ("assistant", "hr_assistant")
    )
    else "FAIL"
)
R["proofs"].append(h3)

# ============================ H4 dual-actor task stale-write rejection
h4 = {"name": "H4 dual_actor_task_stale_write_rejected"}
tid = make_task("HARDEN|dual actor " + STAMP)
h4["task_id"] = tid
if tid:
    # Actor A (web) and actor B (mobile) both loaded the task as open.
    h4["web_first"] = api("POST", "/dashboard/hr-tasks/%s/resolve" % tid, T["web"], {"status": "done", "expected_status": "open"})[0]
    st, body, _ = api("POST", "/dashboard/hr-tasks/%s/resolve" % tid, T["web2"], {"status": "dismissed", "expected_status": "open"})
    h4["web_second_stale"] = {"http": st, "error": (body or {}).get("detail", {}).get("error") if isinstance((body or {}).get("detail"), dict) else body}
    # Mobile v1 marks done only, so the stale probe uses done with a stale expectation.
    st, body, _ = api("POST", "/dashboard/mobile/tasks/%s/resolve" % tid, T["mob"], {"status": "done", "expected_status": "open"})
    h4["mobile_stale"] = {"http": st, "error": (body or {}).get("detail", {}).get("error") if isinstance((body or {}).get("detail"), dict) else body}
    st, body, _ = api("POST", "/dashboard/hr-tasks/%s/resolve" % tid, T["web"], {"status": "done"})
    h4["web_missing_expected_status"] = st
    final = sql("SELECT status FROM hr_tasks WHERE task_id=%s", (tid,))
    h4["final_status"] = final[0]["status"] if final else None
    h4["verdict"] = (
        "PASS"
        if (
            h4["web_first"] == 200
            and h4["web_second_stale"]["http"] == 409
            and h4["mobile_stale"]["http"] == 409
            and h4["web_missing_expected_status"] in (409, 422)
            and h4["final_status"] == "done"
        )
        else "FAIL"
    )
else:
    h4["verdict"] = "FAIL"
R["proofs"].append(h4)

# ============================ H5/H6 queue visibility at scale + urgent ordering
h5 = {"name": "H5 queue_visibility_30_and_over_50"}
h6 = {"name": "H6 urgent_tasks_sort_above_high_and_normal"}
seeded = []
try:
    for i in range(60):
        # Urgent is seeded last so only correct ordering can float it to the top.
        priority = "urgent" if i == 59 else ("normal" if i % 2 else "high")
        made = make_task("HARDEN|bulk %02d %s" % (i, STAMP), priority=priority)
        if made:
            seeded.append(made)
    h5["seeded"] = len(seeded)

    open_total = sql("SELECT count(*) AS n FROM hr_tasks WHERE company_code='WATHEFNI' AND status='open'")[0]["n"]
    h5["db_open_total"] = open_total

    st, page1, _ = api("GET", "/dashboard/mobile/tasks?status=open&offset=0&limit=30", T["mob"])
    h5["page1"] = {
        "http": st,
        "items": len((page1 or {}).get("items") or []),
        "total": (page1 or {}).get("total"),
        "has_more": (page1 or {}).get("has_more"),
    }
    st, page2, _ = api("GET", "/dashboard/mobile/tasks?status=open&offset=30&limit=30", T["mob"])
    h5["page2"] = {
        "http": st,
        "items": len((page2 or {}).get("items") or []),
        "total": (page2 or {}).get("total"),
        "has_more": (page2 or {}).get("has_more"),
    }
    ids1 = [r.get("task_id") for r in ((page1 or {}).get("items") or [])]
    ids2 = [r.get("task_id") for r in ((page2 or {}).get("items") or [])]
    h5["pages_disjoint"] = not (set(ids1) & set(ids2))
    h5["total_exceeds_first_page"] = bool(h5["page1"]["total"] and h5["page1"]["total"] > h5["page1"]["items"])
    h5["total_matches_db"] = h5["page1"]["total"] == open_total

    # Home/Inbox must report the company-wide count, not the fetched window.
    st, pri, _ = api("GET", "/dashboard/mobile/priorities?limit=30", T["mob"])
    tasks_section = [
        s for s in ((pri or {}).get("sections") or []) if str(s.get("type")) == "hr_tasks"
    ]
    h5["priorities_tasks_section"] = (
        {"items": len(tasks_section[0].get("items") or []), "total": tasks_section[0].get("total")}
        if tasks_section
        else None
    )
    h5["priorities_total_is_honest"] = bool(
        tasks_section and (tasks_section[0].get("total") or 0) >= len(tasks_section[0].get("items") or [])
    )

    h5["verdict"] = (
        "PASS"
        if (
            h5["page1"]["items"] == 30
            and h5["page1"]["has_more"] is True
            and h5["page2"]["items"] > 0
            and h5["pages_disjoint"]
            and h5["total_exceeds_first_page"]
            and h5["total_matches_db"]
            and h5["priorities_total_is_honest"]
        )
        else "FAIL"
    )

    order = [
        (r.get("task_id"), str(r.get("priority") or ""))
        for r in ((page1 or {}).get("items") or [])
    ]
    h6["first_10_priorities"] = [p for _, p in order[:10]]
    urgent_positions = [i for i, (_, p) in enumerate(order) if p == "urgent"]
    high_positions = [i for i, (_, p) in enumerate(order) if p == "high"]
    normal_positions = [i for i, (_, p) in enumerate(order) if p == "normal"]
    h6["urgent_positions"] = urgent_positions
    h6["first_high_position"] = high_positions[0] if high_positions else None
    h6["first_normal_position"] = normal_positions[0] if normal_positions else None
    h6["verdict"] = (
        "PASS"
        if (
            urgent_positions
            and (not high_positions or max(urgent_positions) < min(high_positions))
            and (not normal_positions or max(urgent_positions) < min(normal_positions))
        )
        else "FAIL"
    )

    # Other capped actionable queues must also carry honest continuation.
    h5["other_queues"] = {}
    for label, path in (
        ("documents", "/dashboard/mobile/documents?status=needs_review&offset=0&limit=30"),
        ("alerts", "/dashboard/mobile/delivery-alerts?offset=0&limit=30"),
        ("swaps", "/dashboard/mobile/shift-swaps?status=requested&offset=0&limit=30"),
        (
            "attendance",
            "/dashboard/mobile/attendance?status=exceptions&start_date=2026-07-01&end_date=2026-08-11&offset=0&limit=30",
        ),
        ("onboarding", "/dashboard/mobile/onboarding?offset=0&limit=30"),
    ):
        st, b, _ = api("GET", path, T["mob"])
        h5["other_queues"][label] = {
            "http": st,
            "items": len((b or {}).get("items") or []) if isinstance(b, dict) else None,
            "total_present": isinstance(b, dict) and ("total" in b or "total_count" in b),
            "has_more_present": isinstance(b, dict) and "has_more" in b,
        }
    h5["all_queues_expose_continuation"] = all(
        v["http"] == 200 and v["total_present"] and v["has_more_present"] for v in h5["other_queues"].values()
    )
    if not h5["all_queues_expose_continuation"] and h5["verdict"] == "PASS":
        h5["verdict"] = "FAIL"
finally:
    if seeded:
        sql("DELETE FROM hr_tasks WHERE task_id = ANY(%s::uuid[])", (seeded,), commit=True)
R["proofs"].append(h5)
R["proofs"].append(h6)

# ============================ H7 web -> mobile convergence
h7 = {"name": "H7 web_mutation_visible_to_mobile_without_manual_refresh"}
ctid = make_task("HARDEN|converge " + STAMP)
h7["task_id"] = ctid
if ctid:
    st, b, hdr = api("GET", "/dashboard/mobile/tasks?status=open&limit=100", T["mob2"])
    h7["mobile_sees_open_before"] = any(str(r.get("task_id")) == ctid for r in all_rows(b))
    h7["mobile_cache_control"] = hdr.get("Cache-Control")
    h7["web_resolve"] = api(
        "POST", "/dashboard/hr-tasks/%s/resolve" % ctid, T["web"], {"status": "done", "expected_status": "open"}
    )[0]
    # Same mobile session token, no re-auth: the next read must already converge.
    st, b, _ = api("GET", "/dashboard/mobile/tasks?status=open&limit=100", T["mob2"])
    h7["mobile_sees_open_after"] = any(str(r.get("task_id")) == ctid for r in all_rows(b))
    st, b, _ = api("GET", "/dashboard/mobile/tasks/%s" % ctid, T["mob2"])
    d = [r for r in all_rows(b) if str(r.get("task_id")) == ctid]
    h7["mobile_detail_status_after"] = (d[0].get("status") if d else (b or {}).get("status"))
    st, b, _ = api("GET", "/dashboard/mobile/priorities?limit=30", T["mob2"])
    h7["mobile_priorities_still_lists_task"] = any(str(r.get("target_id")) == ctid for r in all_rows(b))
    h7["verdict"] = (
        "PASS"
        if (
            h7["mobile_sees_open_before"]
            and h7["web_resolve"] == 200
            and not h7["mobile_sees_open_after"]
            and h7["mobile_detail_status_after"] == "done"
            and not h7["mobile_priorities_still_lists_task"]
            and str(h7["mobile_cache_control"] or "").find("no-store") >= 0
        )
        else "FAIL"
    )
    sql("DELETE FROM hr_tasks WHERE task_id=%s", (ctid,), commit=True)
else:
    h7["verdict"] = "FAIL"
R["proofs"].append(h7)

# ============================ cleanup
cleanup = {
    "harden_tasks": sql("DELETE FROM hr_tasks WHERE company_code='WATHEFNI' AND title LIKE 'HARDEN|%%'", commit=True),
    "leave_events": sql(
        "DELETE FROM leave_events WHERE leave_id IN (SELECT leave_id FROM leave_requests WHERE reason LIKE %s)",
        (TAG + "%",),
        commit=True,
    ),
    "leave_requests": sql("DELETE FROM leave_requests WHERE reason LIKE %s", (TAG + "%",), commit=True),
    "probe_candidates": sql("DELETE FROM candidates WHERE name=%s", (TAG,), commit=True),
    "spawned_messages": sql(
        "DELETE FROM employee_messages WHERE company_code='WATHEFNI' AND employee_key=%s AND created_at > now() - interval '30 minutes'",
        (SYNTH_EMP,),
        commit=True,
    ),
}
cleanup["harden_rows_remaining"] = sql(
    "SELECT count(*) AS n FROM hr_tasks WHERE title LIKE 'HARDEN|%%'"
)[0]["n"]
cleanup["synth_leave_remaining"] = sql(
    "SELECT count(*) AS n FROM leave_requests WHERE reason LIKE %s", (TAG + "%",)
)[0]["n"]
R["cleanup"] = cleanup
R["summary"] = {p["name"]: p.get("verdict") for p in R["proofs"] if p.get("verdict")}
print("<<<JSON>>>")
print(json.dumps(R, indent=1, default=str))
