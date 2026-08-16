#!/usr/bin/env python3
"""Attendance Wave 2G — production dark persistence canary (synthetic only).

Proves durable Postgres capture-ops on production with CAPTURE_INGEST=off.
Never connects a customer device or ingests real punches.
Uses WATHEFNI + W2G-SYNTH| / ATTW2G markers only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
import uuid
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
RESULTS: list[dict[str, Any]] = []


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL

    def _j(v: Any) -> Any:
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (datetime, date, time)):
            return v.isoformat()
        if isinstance(v, dict):
            return {str(k): _j(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_j(x) for x in v]
        if hasattr(v, "isoformat"):
            try:
                return v.isoformat()
            except Exception:  # noqa: BLE001
                pass
        return str(v)

    RESULTS.append({"label": label, "ok": bool(cond), "detail": _j(detail)})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    if (os.environ.get("WATHEFNI_ENV") or "").lower() != "production":
        print("REFUSE: WATHEFNI_ENV must be production")
        return 2

    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_STORE"] = "postgres"
    # Keep ingest off regardless of caller
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = "off"

    try:
        import app
        import attendance_authority_wave1 as core
        import attendance_capture_contract as contract
        import attendance_capture_ops as ops
        import attendance_capture_pipeline as pipeline_mod
        import attendance_capture_postgres as cap
        import attendance_capture_secrets as secrets
        from attendance_capture_contract import as_kuwait
    except Exception as exc:  # noqa: BLE001
        print("BOOT_FAIL", exc)
        traceback.print_exc()
        return 2

    core.reset_authority_services_for_tests()
    ops.reset_capture_ops_for_tests()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = cur.fetchone()["db"]
    check("production db", db == "wathefni", db)
    check("store mode postgres", ops.capture_store_mode() == "postgres", ops.capture_store_mode())
    check("capture ops on", app.attendance_capture_ops_enabled() is True)
    check("capture ingest off", app.attendance_capture_ingest_enabled() is False)
    check("import off", app.attendance_import_enabled() is False)
    check("authority synthetic only", app.attendance_authority_synthetic_only() is True)

    # Preflight: process-local was pre-2G; after deploy store must be postgres
    check("CAPTURE_STORE env postgres", (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_STORE") or "").lower() == "postgres")

    tag = uuid.uuid4().hex[:8]
    marker = f"ATTW2G-{tag}"
    company = "WATHEFNI"
    other = "OTHERCO"
    manager_phone = f"96552430{tag[:4]}"
    emp_phone = f"96552431{tag[:4]}"
    emp_key = f"W2G-SYNTH|{tag}"
    other_emp_key = f"W2G-SYNTH|OUT-{tag}"
    day = date(2026, 8, 27)
    shift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }

    def resolve(company_code: str, employee_key: str) -> dict[str, Any] | None:
        if company_code.upper() != company:
            return None
        if employee_key == emp_key:
            return {"employee_key": emp_key, "phone": emp_phone, "name": f"W2G-{tag}", "company_code": company}
        return None

    def manager_scope(company_code: str, actor: str, employee: str) -> bool:
        return company_code == company and employee == emp_key and actor == manager_phone

    store = cap.PostgresCaptureStore(connect=app.db_connect, manager_scope_allows=manager_scope)
    store.ensure_schema()
    store.cleanup_synthetic(marker)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            demo_n = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI' AND metadata->>'demo_seed'='wathefni_v1'"
            )
            demo_seed = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)",
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            four = int(cur.fetchone()["n"])
    check("42 attendance rows pre", demo_n == 42, demo_n)
    check("42 demo_seed rows pre", demo_seed == 42, demo_seed)
    check("four reals present pre", four == 4, four)

    site = store.register_site(company_code=company, name=f"{marker}-Site")
    check("register site", bool(site.get("site_id")), site)
    site_id = str(site["site_id"])

    cross_dev = store.register_device(company_code=company, site_id=site_id, terminal_sn=f"{marker}-SN", actor_company=other)
    check("cross-tenant device denied", not cross_dev.get("ok"), cross_dev)

    dev = store.register_device(company_code=company, site_id=site_id, terminal_sn=f"{marker}-SN")
    check("register device", bool(dev.get("ok")), dev)
    device_id = str(dev["device"]["device_id"])

    secrets_in = {"username": "lab", "password": f"plain-should-never-persist-{tag}", "token": f"tok-{tag}"}
    reg = store.register_connector(
        company_code=company,
        site_id=site_id,
        device_id=device_id,
        secrets=secrets_in,
        connector_version=f"{marker}-v1",
        actor_phone=manager_phone,
    )
    check("register connector sealed", bool(reg.get("ok")) and reg.get("secrets") == secrets.REDACTED, reg)
    connector_id = reg["connector"]["connector_id"]
    row_v = int(reg["connector"]["row_version"])

    act = store.activate(connector_id, expected_row_version=row_v, actor_phone=manager_phone)
    check("activate", act.get("ok"), act)
    row_v = int(act["connector"]["row_version"])

    rot = store.rotate_credentials(
        connector_id,
        new_secrets={"username": "lab", "password": f"rotated-{tag}"},
        expected_row_version=row_v,
        actor_phone=manager_phone,
    )
    check("rotate sealed", rot.get("ok") and rot.get("secrets") == secrets.REDACTED, rot)
    row_v = int(rot["connector"]["row_version"])

    stale = store.rotate_credentials(
        connector_id, new_secrets={"password": "nope"}, expected_row_version=row_v - 1, actor_phone=manager_phone
    )
    check("stale rotate fail-closed", not stale.get("ok") and stale.get("error") == "stale_row_version", stale)

    secret_scan = store.assert_no_plaintext_secrets()
    check("no plaintext secrets in DB", secret_scan.get("ok"), secret_scan)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sealed_ref, previous_sealed_ref FROM attendance_capture_credentials WHERE connector_id=%s",
                (connector_id,),
            )
            creds = cur.fetchall()
    leaked = []
    for c in creds:
        for col in ("sealed_ref", "previous_sealed_ref"):
            val = c.get(col) or ""
            if f"plain-should-never-persist-{tag}" in val or f"rotated-{tag}" in val:
                leaked.append(col)
            if val and val != "[REVOKED]" and not str(val).startswith("gAAAA"):
                leaked.append(f"non_fernet:{col}")
    check("credential rows Fernet-only", not leaked, leaked)

    health = store.upsert_health(
        connector_id=connector_id,
        company_code=company,
        site_id=site_id,
        agent_health={
            "status": "degraded",
            "last_sync_at": as_kuwait("2026-08-27T08:00:00").isoformat(),
            "lag_seconds": 400,
            "failure_count": 2,
            "last_error": "lab_lag",
            "checkpoint": f"cp-{marker}-1",
            "connector_version": f"{marker}-v1",
        },
    )
    check("health degraded", health.get("status") == "degraded", health)

    cp1 = store.save_checkpoint(connector_id=connector_id, company_code=company, checkpoint=f"cp-{marker}-1")
    check("checkpoint save", cp1.get("ok") and cp1.get("checkpoint") == f"cp-{marker}-1", cp1)
    cp_dup = store.save_checkpoint(connector_id=connector_id, company_code=company, checkpoint=f"cp-{marker}-1")
    check("checkpoint duplicate exactly-once", cp_dup.get("ok") and cp_dup.get("duplicate") is True, cp_dup)
    cp2 = store.save_checkpoint(connector_id=connector_id, company_code=company, checkpoint=f"cp-{marker}-2")
    check("checkpoint advance", cp2.get("ok") and not cp2.get("duplicate"), cp2)

    punch_payload = {
        "company_code": company,
        "source": "biotime",
        "source_event_id": f"biotime:w2g-{marker}-1",
        "device_user_id": f"DU-{marker}",
        "punched_at": as_kuwait("2026-08-27T09:05:00").isoformat(),
        "direction": "in",
        "capture_method": "card",
        "device_id": f"{marker}-SN",
        "connector_id": connector_id,
        "raw_ref": {"id": 1},
        "metadata": {},
        "employee_key": None,
    }
    enq = store.enqueue_remediation(
        company_code=company,
        kind="unknown_employee",
        connector_id=connector_id,
        device_user_id=f"DU-{marker}",
        device_id=f"{marker}-SN",
        source_event_id=punch_payload["source_event_id"],
        payload=punch_payload,
        idempotency_key=f"unk-{marker}",
    )
    check("unknown mapping queued", enq.get("ok") and not enq.get("duplicate"), enq)
    item_id = str(enq["item"]["item_id"])
    item_rv = int(enq["item"]["row_version"])

    # process restart simulation
    store2 = cap.PostgresCaptureStore(connect=app.db_connect, manager_scope_allows=manager_scope)
    check("checkpoint survives restart", store2.get_checkpoint(connector_id) == f"cp-{marker}-2")
    open_after = store2.list_open_remediation(company)
    check(
        "unknown mapping remains queued after restart",
        any(str(i["item_id"]) == item_id and i["status"] == "open" for i in open_after),
        [{"item_id": str(i["item_id"]), "status": i["status"]} for i in open_after[:5]],
    )
    health_after = store2.list_health(company)
    check(
        "health survives restart",
        any(h["connector_id"] == connector_id and h.get("status") == "degraded" for h in health_after),
        health_after[:3],
    )
    recovered = store2.mark_recovered(connector_id, last_sync_at=as_kuwait("2026-08-27T09:10:00").isoformat())
    check("health recover", recovered and recovered.get("status") == "online", recovered)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_capture_health_events WHERE connector_id=%s",
                (connector_id,),
            )
            he_n = int(cur.fetchone()["n"])
    check("health event history retained", he_n >= 1, he_n)

    cross = store2.approve_mapping(
        item_id, employee_key=emp_key, expected_row_version=item_rv, actor_phone=manager_phone, actor_company=other, replay=False
    )
    check("cross-tenant approve denied", not cross.get("ok") and cross.get("error") == "cross_tenant_denied", cross)

    self_deny = store2.approve_mapping(
        item_id,
        employee_key=emp_key,
        expected_row_version=item_rv,
        actor_phone=emp_phone,
        actor_company=company,
        actor_is_manager=True,
        employee_phone=emp_phone,
        replay=False,
    )
    check("manager self-action denied", not self_deny.get("ok") and self_deny.get("error") == "manager_self_action_denied", self_deny)

    scope_deny = store2.approve_mapping(
        item_id, employee_key=other_emp_key, expected_row_version=item_rv, actor_phone=manager_phone, actor_company=company, replay=False
    )
    check("manager scope denied", not scope_deny.get("ok") and scope_deny.get("error") == "manager_scope_denied", scope_deny)

    results_conc: list[dict[str, Any]] = []

    def _approve_once() -> None:
        s = cap.PostgresCaptureStore(connect=app.db_connect, manager_scope_allows=manager_scope)
        results_conc.append(
            s.approve_mapping(
                item_id,
                employee_key=emp_key,
                expected_row_version=item_rv,
                actor_phone=manager_phone,
                actor_company=company,
                replay=False,
            )
        )

    t1 = threading.Thread(target=_approve_once)
    t2 = threading.Thread(target=_approve_once)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    oks = [r for r in results_conc if r.get("ok")]
    fails = [r for r in results_conc if not r.get("ok")]
    check("concurrent approve: exactly one success", len(oks) == 1, results_conc)
    check(
        "concurrent approve: other fail-closed",
        len(fails) == 1 and fails[0].get("error") in {"stale_row_version", "item_not_open"},
        fails,
    )

    rej_enq = store2.enqueue_remediation(
        company_code=company,
        kind="duplicate_conflict",
        connector_id=connector_id,
        payload={"marker": marker},
        idempotency_key=f"rej-{marker}",
    )
    rej_id = str(rej_enq["item"]["item_id"])
    rej_rv = int(rej_enq["item"]["row_version"])
    rej1 = store2.reject(rej_id, expected_row_version=rej_rv, actor_phone=manager_phone, actor_company=company, reason="lab")
    check("reject ok", rej1.get("ok"), rej1)
    rej3 = store2.reject(
        rej_id, expected_row_version=int(rej1["item"]["row_version"]), actor_phone=manager_phone, actor_company=company
    )
    check("reject idempotent", rej3.get("ok") and rej3.get("duplicate") is True, rej3)

    punch2 = dict(punch_payload)
    punch2["source_event_id"] = f"biotime:w2g-{marker}-replay"
    punch2["device_user_id"] = f"DU-R-{marker}"
    enq_r = store2.enqueue_remediation(
        company_code=company,
        kind="unknown_employee",
        connector_id=connector_id,
        device_user_id=f"DU-R-{marker}",
        device_id=f"{marker}-SN",
        source_event_id=punch2["source_event_id"],
        payload=punch2,
        idempotency_key=f"unk-r-{marker}",
    )
    rid = str(enq_r["item"]["item_id"])
    rrv = int(enq_r["item"]["row_version"])

    auth_svc = core.get_authority_service(company)
    pipeline = pipeline_mod.CapturePipeline(
        authority_service=auth_svc,
        mapping=contract.InMemoryMappingStore(),
        employee_resolver=resolve,
        connector_id=connector_id,
        require_mapping=True,
    )
    store2.pipeline = pipeline

    approve_replay = store2.approve_mapping(
        rid,
        employee_key=emp_key,
        expected_row_version=rrv,
        actor_phone=manager_phone,
        actor_company=company,
        replay=True,
        shift=shift,
    )
    check(
        "approve+replay reaches authority",
        approve_replay.get("ok") and (approve_replay.get("replay") or {}).get("ok"),
        approve_replay,
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_punches WHERE company_code=%s AND source_event_id=%s",
                (company, punch2["source_event_id"]),
            )
            punch_count_1 = int(cur.fetchone()["n"])
    check("authority punch exactly once", punch_count_1 == 1, punch_count_1)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT row_version FROM attendance_capture_remediation WHERE item_id=%s", (rid,))
            mid = dict(cur.fetchone())
    replay_dup = store2.replay_item(
        rid,
        expected_row_version=int(mid["row_version"]),
        actor_phone=manager_phone,
        actor_company=company,
        shift=shift,
    )
    check("replay idempotent duplicate", replay_dup.get("ok") and replay_dup.get("duplicate") is True, replay_dup)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_punches WHERE company_code=%s AND source_event_id=%s",
                (company, punch2["source_event_id"]),
            )
            punch_count_2 = int(cur.fetchone()["n"])
    check("authority punch still exactly once", punch_count_2 == 1, punch_count_2)

    recon = store2.reconcile_with_authority(company)
    check("reconcile capture↔authority", recon.get("ok") and recon.get("matched_in_authority", 0) >= 1, recon)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT event_id FROM attendance_capture_audit_events WHERE connector_id=%s LIMIT 1", (connector_id,))
            ev = cur.fetchone()
            immutable_ok = False
            if ev:
                try:
                    cur.execute("UPDATE attendance_capture_audit_events SET action='tamper' WHERE event_id=%s", (ev["event_id"],))
                except Exception as exc:  # noqa: BLE001
                    immutable_ok = "immutable" in str(exc).lower() or "attendance_capture_audit" in str(exc)
                    conn.rollback()
    check("audit events immutable", immutable_ok)

    ops.reset_capture_ops_for_tests()
    ov = ops.overview(company)
    check("ops overview store_mode postgres", ov.get("store_mode") == "postgres", ov.get("flags"))

    # freezes
    if os.environ.get("ATTW2G_SKIP_FREEZE", "").strip().lower() in {"1", "true", "yes", "on"}:
        check("freeze skipped", True)
    else:
        for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
            path = ROOT / script
            if not path.exists():
                check(f"freeze {script}", False, "missing")
                continue
            proc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), capture_output=True, text=True)
            check(f"freeze {script}", proc.returncode == 0, (proc.stdout + proc.stderr)[-500:])

    # cleanup synthetic capture + authority punches for marker
    store2.cleanup_synthetic(marker)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.allow_authority_cleanup','1', true)")
            try:
                cur.execute(
                    "DELETE FROM attendance_punches WHERE company_code=%s AND source_event_id LIKE %s",
                    (company, f"%{marker}%"),
                )
                cur.execute(
                    "DELETE FROM attendance_day_projections WHERE company_code=%s AND employee_key LIKE %s",
                    (company, f"%{marker}%"),
                )
            except Exception:  # noqa: BLE001
                conn.rollback()
            else:
                conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            demo_n2 = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)",
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            four2 = int(cur.fetchone()["n"])
            # remaining capture rows for this marker
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_capture_sites WHERE name ILIKE %s",
                (f"%{marker}%",),
            )
            left_sites = int(cur.fetchone()["n"])
    check("42 attendance rows post", demo_n2 == 42, demo_n2)
    check("four reals present post", four2 == 4, four2)
    check("marker sites cleaned", left_sites == 0, left_sites)

    evid = os.environ.get("ATTW2G_EVID")
    if evid:
        scan = secrets.scan_paths([evid])
        qgate = secrets.qualify_or_block(scan)
        check("evidence leak scan", qgate.get("ok") is True, {"blocked": qgate.get("blocked"), "files": qgate.get("files_scanned")})

    out = {"pass": PASS, "fail": FAIL, "db": db, "marker": marker, "results": RESULTS, "version": cap.CAPTURE_OPS_VERSION}
    out_path = os.environ.get("ATTW2G_RESULTS")
    if out_path:
        Path(out_path).write_text(secrets.redact_text(json.dumps(out, indent=2, default=str)), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "db": db, "marker": marker}, indent=2))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
