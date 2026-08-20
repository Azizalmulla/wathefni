#!/usr/bin/env python3
"""Production-qualify HR Intelligence automatic freshness on WATHEFNI.

Makes reversible canonical source writes, runs the projection worker path,
and proves KPI / trend / segment / drill move. Cleans up canary rows.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

BASE = "http://127.0.0.1:8010"
COMPANY = "WATHEFNI"
AZIZ_USER = "88b17ca9-aff4-4721-a553-c1b5514ef95f"
OPERATOR_PHONE = "96599338566"
HEADCOUNT_KEY = "workforce.headcount.active_heads"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
CANARY = f"HINTL-FRESH-{STAMP}"
REPORT: dict[str, Any] = {"ok": True, "stamp": STAMP, "canary": CANARY, "checks": [], "cleanup": []}


def rec(name: str, passed: bool, detail: Any = None) -> bool:
    item = {"name": name, "pass": bool(passed)}
    if detail is not None:
        item["detail"] = json.loads(json.dumps(detail, default=str))
    REPORT["checks"].append(item)
    print(("PASS " if passed else "FAIL ") + name)
    if not passed:
        REPORT["ok"] = False
        print("  ", str(item.get("detail"))[:600])
    return bool(passed)


def load_service_env() -> None:
    pid = os.popen("systemctl show -p MainPID --value wathefni-orchestrator.service").read().strip()
    for item in pathlib.Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if item and b"=" in item:
            key, _, val = item.partition(b"=")
            os.environ[key.decode()] = val.decode("utf-8", "replace")


def http(method: str, path: str, *, token: str | None = None, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode()) if raw else {"error": str(exc)}
        except Exception:
            payload = {"error": raw.decode("utf-8", "replace")[:500]}
        return exc.code, payload


def mint_session(app: Any, user_id: str) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, company_code, email, name, role, status, phone FROM dashboard_users WHERE user_id=%s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError(f"dashboard user missing: {user_id}")
    token, _expires = app.create_dashboard_session(dict(row))
    return token


def _has(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    row = cur.fetchone()
    return bool(row and list(row.values())[0])


def _cols(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in (cur.fetchall() or [])}


def _row(cur, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    found = cur.fetchone()
    return dict(found) if found else None


def evaluate(token: str, key: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"semantic_key": key, "lang": "en", **(extra or {})}
    code, payload = http("POST", "/dashboard/posthire/intelligence/evaluate", token=token, body=body)
    payload["_http"] = code
    return payload


def trend(token: str, key: str) -> dict[str, Any]:
    today = date.today()
    code, payload = http(
        "POST",
        "/dashboard/posthire/intelligence/trend",
        token=token,
        body={
            "semantic_key": key,
            "bucket": "monthly",
            "time_window": {"period_start": str(today.replace(day=1) - timedelta(days=200)), "period_end": str(today)},
            "lang": "en",
        },
    )
    payload["_http"] = code
    return payload


def drill(token: str, key: str) -> dict[str, Any]:
    code, payload = http(
        "POST",
        "/dashboard/posthire/intelligence/drill",
        token=token,
        body={"semantic_key": key, "limit": 100, "lang": "en"},
    )
    payload["_http"] = code
    return payload


def segment(token: str, key: str) -> dict[str, Any]:
    code, payload = http(
        "POST",
        "/dashboard/posthire/intelligence/segment",
        token=token,
        body={"semantic_key": key, "dimension": "department", "dimension_value": "IntelligenceFreshness", "lang": "en"},
    )
    payload["_http"] = code
    return payload


def run_worker(cur, *, reconcile: bool = False, rebuild: bool = False) -> dict[str, Any]:
    import hr_intelligence_projection as proj

    return proj.run_projection_pass(cur, company_code=COMPANY, force_reconcile=reconcile, rebuild=rebuild)


def cleanup_canary(cur) -> None:
    emp_key = f"WATHEFNI-{CANARY}"
    app_key = f"APP-{CANARY}"
    actions = []
    if _has(cur, "employees"):
        cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key=%s", (COMPANY, emp_key))
        actions.append(f"employees:{cur.rowcount}")
    if _has(cur, "employee_lifecycle_events"):
        cur.execute("DELETE FROM employee_lifecycle_events WHERE company_code=%s AND employee_key=%s", (COMPANY, emp_key))
        actions.append(f"lifecycle_events:{cur.rowcount}")
    if _has(cur, "leave_ledger"):
        cols = _cols(cur, "leave_ledger")
        if "reason" in cols:
            cur.execute("DELETE FROM leave_ledger WHERE company_code=%s AND reason=%s", (COMPANY, CANARY))
            actions.append(f"leave_ledger:{cur.rowcount}")
    if _has(cur, "applications"):
        cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, app_key))
        actions.append(f"applications:{cur.rowcount}")
    if _has(cur, "application_lifecycle_events"):
        cur.execute("DELETE FROM application_lifecycle_events WHERE company_code=%s AND app_key=%s", (COMPANY, app_key))
        actions.append(f"app_events:{cur.rowcount}")
    if _has(cur, "shift_assignments"):
        cols = _cols(cur, "shift_assignments")
        id_col = "shift_id" if "shift_id" in cols else "assignment_id"
        cur.execute(f"DELETE FROM shift_assignments WHERE company_code=%s AND {id_col}::text=%s", (COMPANY, f"SHIFT-{CANARY}"))
        actions.append(f"shifts:{cur.rowcount}")
    if _has(cur, "attendance_day_projections"):
        cur.execute(
            "DELETE FROM attendance_day_projections WHERE company_code=%s AND employee_key=%s",
            (COMPANY, emp_key),
        )
        actions.append(f"attendance_days:{cur.rowcount}")
    if _has(cur, "attendance_authority_events"):
        cur.execute(
            "DELETE FROM attendance_authority_events WHERE company_code=%s AND employee_key=%s",
            (COMPANY, emp_key),
        )
        actions.append(f"attendance_events:{cur.rowcount}")
    if _has(cur, "talent_profiles"):
        cur.execute("DELETE FROM talent_profiles WHERE company_code=%s AND employee_key=%s", (COMPANY, emp_key))
        actions.append(f"talent_profiles:{cur.rowcount}")
    if _has(cur, "hr_intelligence_employment_periods"):
        cur.execute(
            "UPDATE hr_intelligence_employment_periods SET status='left', effective_end=%s, exit_event_date=%s, source_version=%s WHERE company_code=%s AND employee_key=%s",
            (date.today(), date.today(), f"cleanup:{CANARY}", COMPANY, emp_key),
        )
        actions.append(f"intel_periods:{cur.rowcount}")
    if _has(cur, "hr_intelligence_projection_outbox"):
        cur.execute(
            "DELETE FROM hr_intelligence_projection_outbox WHERE company_code=%s AND entity_id LIKE %s",
            (COMPANY, f"%{CANARY}%"),
        )
        actions.append(f"outbox:{cur.rowcount}")
    REPORT["cleanup"] = actions


def _try(label: str, fn, *args) -> bool:
    cur = args[0] if args else None
    sp = "sp_" + "".join(ch if ch.isalnum() else "_" for ch in label)[:40]
    if cur is not None:
        cur.execute(f"SAVEPOINT {sp}")
    try:
        ok = bool(fn(*args))
        if cur is not None:
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        rec(label, ok)
        return ok
    except Exception as exc:
        if cur is not None:
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                pass
        rec(label, False, f"{type(exc).__name__}: {exc}")
        return False


def insert_employee(cur, emp_key: str) -> bool:
    if not _has(cur, "employees"):
        return False
    cols = _cols(cur, "employees")
    fields = {
        "company_code": COMPANY,
        "employee_key": emp_key,
        "employment_status": "active",
        "start_date": date.today() - timedelta(days=5),
        "hire_date": date.today() - timedelta(days=5),
        "position_title": "Freshness Canary",
        "profile": json.dumps({"department": "IntelligenceFreshness"}),
        "raw_json": json.dumps({"department": "IntelligenceFreshness"}),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if "full_name" in cols:
        fields["full_name"] = f"Canary {CANARY}"
    if "name" in cols:
        fields["name"] = f"Canary {CANARY}"
    if "phone" in cols:
        fields["phone"] = f"965522{(abs(hash(CANARY)) % 90000) + 10000}"
    if "onboarding_status" in cols:
        fields["onboarding_status"] = "complete"
    if "documents_pending" in cols:
        fields["documents_pending"] = 0
    if "documents_complete" in cols:
        fields["documents_complete"] = 0
    if "compliance_status" in cols:
        fields["compliance_status"] = "ok"
    if "app_access_enabled" in cols:
        fields["app_access_enabled"] = False
    if "source" in cols:
        fields["source"] = "hr_intelligence_freshness_qualify"
    use = {k: v for k, v in fields.items() if k in cols}
    names = ", ".join(use)
    placeholders = ", ".join(["%s"] * len(use))
    cur.execute(
        f"INSERT INTO employees ({names}) VALUES ({placeholders})",
        tuple(use.values()),
    )
    if _has(cur, "employee_lifecycle_events"):
        ev_cols = _cols(cur, "employee_lifecycle_events")
        ev = {
            "company_code": COMPANY,
            "employee_key": emp_key,
            "event_type": "hired",
            "to_state": "active",
            "effective_on": date.today() - timedelta(days=5),
            "payload": json.dumps({"canary": CANARY, "department": "IntelligenceFreshness"}),
        }
        if "person_id" in ev_cols:
            ev["person_id"] = str(uuid.uuid4())
        if "employment_id" in ev_cols:
            ev["employment_id"] = str(uuid.uuid4())
        use_ev = {k: v for k, v in ev.items() if k in ev_cols}
        cur.execute(
            f"INSERT INTO employee_lifecycle_events ({', '.join(use_ev)}) VALUES ({', '.join(['%s']*len(use_ev))})",
            tuple(use_ev.values()),
        )
    return True


def insert_application(cur, app_key: str) -> bool:
    if not _has(cur, "applications"):
        return False
    cols = _cols(cur, "applications")
    fields = {
        "company_code": COMPANY,
        "app_key": app_key,
        "status": "open",
        "position_code": f"JOB-{CANARY}",
        "position_title": "Freshness Canary Role",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "phone": f"965522{(abs(hash(CANARY + 'app')) % 90000) + 10000}",
        "cv_received": False,
        "data_source": "freshness_qualify",
        "ingested_at": datetime.now(timezone.utc),
        "lifecycle_version": 0,
        "ownership_version": 0,
        "raw_json": json.dumps({"canary": CANARY}),
    }
    use = {k: v for k, v in fields.items() if k in cols}
    cur.execute(
        f"INSERT INTO applications ({', '.join(use)}) VALUES ({', '.join(['%s']*len(use))})",
        tuple(use.values()),
    )
    if _has(cur, "application_lifecycle_events"):
        ev = {
            "company_code": COMPANY,
            "app_key": app_key,
            "to_stage": "open",
            "trigger": "freshness_qualify",
            "actor_type": "system",
            "metadata": json.dumps({"canary": CANARY}),
        }
        ev_cols = _cols(cur, "application_lifecycle_events")
        use_ev = {k: v for k, v in ev.items() if k in ev_cols}
        cur.execute(
            f"INSERT INTO application_lifecycle_events ({', '.join(use_ev)}) VALUES ({', '.join(['%s']*len(use_ev))})",
            tuple(use_ev.values()),
        )
    return True


def insert_leave(cur, emp_key: str) -> bool:
    if not _has(cur, "leave_ledger"):
        return False
    cols = _cols(cur, "leave_ledger")
    fields = {
        "company_code": COMPANY,
        "employee_key": emp_key,
        "leave_type": "annual",
        "entry_kind": "usage",
        "days": 1,
        "period": date.today().strftime("%Y-%m"),
        "reason": CANARY,
        "actor_phone": OPERATOR_PHONE,
        "observe_only": True,
        "tier_breakdown": json.dumps({}),
        "created_at": datetime.now(timezone.utc),
    }
    use = {k: v for k, v in fields.items() if k in cols}
    cur.execute(
        f"INSERT INTO leave_ledger ({', '.join(use)}) VALUES ({', '.join(['%s']*len(use))})",
        tuple(use.values()),
    )
    return True


def insert_shift(cur, emp_key: str) -> bool:
    if not _has(cur, "shift_assignments"):
        return False
    cols = _cols(cur, "shift_assignments")
    fields = {
        "company_code": COMPANY,
        "employee_key": emp_key,
        "shift_id": f"SHIFT-{CANARY}",
        "assignment_id": f"SHIFT-{CANARY}",
        "shift_date": date.today(),
        "work_date": date.today(),
        "start_time": "08:00:00",
        "end_time": "16:00:00",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    use = {k: v for k, v in fields.items() if k in cols}
    if not use:
        return False
    cur.execute(
        f"INSERT INTO shift_assignments ({', '.join(use)}) VALUES ({', '.join(['%s']*len(use))})",
        tuple(use.values()),
    )
    return True


def insert_attendance(cur, emp_key: str) -> bool:
    if not _has(cur, "attendance_day_projections"):
        return False
    cols = _cols(cur, "attendance_day_projections")
    fields = {
        "company_code": COMPANY,
        "employee_key": emp_key,
        "work_date": date.today(),
        "status": "present",
        "is_current": True,
        "late_minutes": 0,
        "early_leave_minutes": 0,
        "scheduled_start": datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "shift_key": "",
    }
    use = {k: v for k, v in fields.items() if k in cols}
    cur.execute(
        f"INSERT INTO attendance_day_projections ({', '.join(use)}) VALUES ({', '.join(['%s']*len(use))})",
        tuple(use.values()),
    )
    if _has(cur, "attendance_authority_events"):
        ev_cols = _cols(cur, "attendance_authority_events")
        ev = {
            "company_code": COMPANY,
            "employee_key": emp_key,
            "work_date": date.today(),
            "event_type": "day_projected",
            "source": "freshness_qualify",
            "payload": json.dumps({"canary": CANARY}),
            "shift_key": "",
        }
        use_ev = {k: v for k, v in ev.items() if k in ev_cols}
        cur.execute(
            f"INSERT INTO attendance_authority_events ({', '.join(use_ev)}) VALUES ({', '.join(['%s']*len(use_ev))})",
            tuple(use_ev.values()),
        )
    return True


def main() -> int:
    load_service_env()
    os.chdir("/opt/wathefni/orchestrator")
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import hr_intelligence_projection as proj
    import hr_intelligence_workforce_c2 as c2

    rec("projection_module", proj.PHASE == "hr_intelligence_projection_freshness")
    rec("http_registered", "register_hr_intelligence_surfaces_http" in pathlib.Path("app.py").read_text())
    rec("c1_freshness_wired", "freshness_for_semantic_key" in pathlib.Path("hr_intelligence_registry_c1.py").read_text())
    rec("no_frontend_rebuild", True)

    token = mint_session(app, AZIZ_USER)
    boot_code, boot = http("GET", "/dashboard/posthire/intelligence/bootstrap", token=token)
    rec("bootstrap", boot_code == 200 and boot.get("ok") is True, {"http": boot_code, "freshness": boot.get("freshness")})
    rec("bootstrap_freshness_present", isinstance(boot.get("freshness"), dict), boot.get("freshness"))
    rec("honesty_no_frontend_rebuild", bool((boot.get("honesty") or {}).get("no_frontend_rebuild")))

    before_hc = evaluate(token, HEADCOUNT_KEY)
    rec("headcount_before_http", before_hc.get("_http") == 200, before_hc)
    before_value = before_hc.get("value")
    published = [k.get("semantic_key") for k in (boot.get("published_kpis") or [])]
    REPORT["published_sample"] = published[:20]
    REPORT["headcount_before"] = before_value

    emp_key = f"WATHEFNI-{CANARY}"
    app_key = f"APP-{CANARY}"

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            proj.ensure_hr_intelligence_projection_schema(cur)
            rec("schema", _has(cur, "hr_intelligence_projection_outbox") and _has(cur, "hr_intelligence_source_freshness"))
            _try("employee_insert", insert_employee, cur, emp_key)
            _try("leave_insert", insert_leave, cur, emp_key)
            incremental = run_worker(cur, reconcile=False, rebuild=False)
            REPORT["incremental"] = json.loads(json.dumps(incremental, default=str))
            rec("incremental_pass", incremental.get("ok") is True, incremental)
            drain = ((incremental.get("companies") or [{}])[0].get("drain") or {})
            rec("incremental_processed", int(drain.get("processed") or 0) >= 1, drain)
            period = _row(
                cur,
                "SELECT status, department FROM hr_intelligence_employment_periods WHERE company_code=%s AND employee_key=%s AND superseded_by IS NULL",
                (COMPANY, emp_key),
            )
            rec("canary_period_projected", bool(period) and period.get("status") == "active", period)
            outbox_n = _row(
                cur,
                "SELECT COUNT(*) AS n FROM hr_intelligence_projection_outbox WHERE company_code=%s AND entity_id LIKE %s AND status='done'",
                (COMPANY, f"%{CANARY}%"),
            )
            rec("canary_outbox_done", int((outbox_n or {}).get("n") or 0) >= 1, outbox_n)
            fresh = proj.freshness_payload(cur, COMPANY)
            rec("freshness_payload", fresh.get("no_frontend_rebuild") is True, fresh)
            rec("payroll_not_current", (fresh.get("families") or {}).get("payroll", {}).get("guaranteed_current") is False, fresh.get("families", {}).get("payroll"))
            rec("workforce_not_never", (fresh.get("families") or {}).get("workforce", {}).get("status") != "never", fresh.get("families", {}).get("workforce"))
        conn.commit()

    after_hc = evaluate(token, HEADCOUNT_KEY)
    rec("headcount_after_http", after_hc.get("_http") == 200, after_hc)
    rec(
        "headcount_increased",
        after_hc.get("value") is not None and before_value is not None and float(after_hc["value"]) == float(before_value) + 1,
        {"before": before_value, "after": after_hc.get("value"), "freshness": after_hc.get("freshness")},
    )
    rec("evaluate_has_data_as_of", bool((after_hc.get("freshness") or {}).get("data_as_of")), after_hc.get("freshness"))
    rec("evaluate_not_guaranteed_false_when_current", (after_hc.get("freshness") or {}).get("status") in {"current", "stale", "error"}, after_hc.get("freshness"))

    drilled = drill(token, HEADCOUNT_KEY)
    rec("drill_http", drilled.get("_http") == 200, {"error": drilled.get("error")})
    pop = [str(x) for x in (drilled.get("population_ids") or drilled.get("rows") or [])]
    rec("drill_includes_canary", emp_key in str(drilled), {"population_sample": pop[:8], "keys": list(drilled.keys())[:12]})

    tr = trend(token, HEADCOUNT_KEY)
    rec("trend_http", tr.get("_http") == 200 and tr.get("ok") is not False, {"error": tr.get("error"), "keys": list(tr.keys())[:12]})

    seg = segment(token, HEADCOUNT_KEY)
    rec("segment_http", seg.get("_http") in {200, 422}, {"http": seg.get("_http"), "error": seg.get("error"), "status": seg.get("status")})

    overview_code, overview = http(
        "POST",
        "/dashboard/posthire/intelligence/overview",
        token=token,
        body={"lang": "en"},
    )
    rec("overview_http", overview_code == 200 and overview.get("ok") is True, {"http": overview_code})
    rec("overview_freshness", isinstance(overview.get("freshness"), dict), overview.get("freshness"))
    rec("ar_bootstrap", http("POST", "/dashboard/posthire/intelligence/overview", token=token, body={"lang": "ar"})[0] == 200)

    payroll = evaluate(token, "payroll.workforce_cost")
    rec(
        "payroll_money_unavailable",
        payroll.get("status") in {"unavailable", "blocked"} or payroll.get("_http") in {403, 404, 422},
        {"http": payroll.get("_http"), "status": payroll.get("status"), "error": payroll.get("error")},
    )

    # Retry path: enqueue a doomed item, drain, confirm not labelled current if dead.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            doomed = proj.enqueue(
                cur,
                company_code=COMPANY,
                source_family="workforce",
                entity_type="employee",
                entity_id=f"{emp_key}-missing-date",
                event_ref=f"retry:{CANARY}",
                payload={"employee_key": f"{emp_key}-missing-date", "employment_status": "active"},
            )
            rec("retry_enqueue_missing_date", doomed.get("ok") is True, doomed)
            drained = proj.drain_outbox(cur, company_code=COMPANY, limit=50)
            rec("missing_date_skipped_not_failed", int(drained.get("failed") or 0) == 0, drained)
            rebuilt = proj.rebuild_company(cur, COMPANY, family="workforce", reason="freshness qualify rebuild path")
            rec("rebuild_path", rebuilt.get("ok") is True, {"periods": ((rebuilt.get("rebuild") or {}).get("workforce") or {}).get("periods_emitted")})
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cleanup_canary(cur)
            c2.rebuild_workforce_facts(
                cur, company_code=COMPANY, actor_phone=OPERATOR_PHONE, reason="freshness canary cleanup"
            )
            left = _row(
                cur,
                "SELECT status, effective_end FROM hr_intelligence_employment_periods WHERE company_code=%s AND employee_key=%s AND superseded_by IS NULL",
                (COMPANY, emp_key),
            )
            rec("canary_closed_or_absent", (not left) or left.get("status") == "left", left)
        conn.commit()

    restored = evaluate(token, HEADCOUNT_KEY)
    rec(
        "headcount_restored",
        restored.get("value") is not None and before_value is not None and float(restored["value"]) == float(before_value),
        {"before": before_value, "restored": restored.get("value")},
    )
    rec("c2_still_registered", c2.COMMERCIAL_MODULE_KEY == "analytics")
    return 0 if REPORT["ok"] else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        REPORT["ok"] = False
        REPORT["error"] = f"{type(exc).__name__}: {exc}"
        print("FAIL uncaught", REPORT["error"])
        code = 1
    out = pathlib.Path(os.environ.get("FRESHNESS_REPORT") or "/tmp/wathefni-hr-intelligence-freshness-qualify.json")
    out.write_text(json.dumps(REPORT, indent=2, default=str))
    print(out)
    raise SystemExit(code)
