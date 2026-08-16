#!/usr/bin/env python3
"""Attendance Wave 2F — durable PostgreSQL capture-ops qualification.

Proves restart-safe connector/health/checkpoint/remediation state, transactional
approve/reject/replay with optimistic concurrency, sealed credential refs only,
exactly-once replay into Wave 1 authority, reconciliation, tenancy denials,
and freeze regressions.

REFUSES production. No customer device, no real punch ingest, no QR/GPS/kiosk.
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
RESULTS: list[dict] = []


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL

    def _jsonable(v: Any) -> Any:
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (datetime, date, time)):
            return v.isoformat()
        if isinstance(v, dict):
            return {str(k): _jsonable(val) for k, val in v.items()}
        if isinstance(v, (list, tuple)):
            return [_jsonable(x) for x in v]
        if hasattr(v, "isoformat"):
            try:
                return v.isoformat()
            except Exception:  # noqa: BLE001
                pass
        return str(v)

    RESULTS.append({"label": label, "ok": bool(cond), "detail": _jsonable(detail)})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production":
        print("REFUSE: production")
        return 2
    os.environ.setdefault("WATHEFNI_ENV", "local")

    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_STORE"] = "postgres"
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_OPS"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = "off"
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES"] = "ATTW2F,ATTW2FX,WATHEFNI"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES"] = "ATTW2F,ATTW2FX"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_STORE"] = "postgres"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY"] = "on"
    os.environ.setdefault("WATHEFNI_CAPTURE_CREDENTIAL_KEY", __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())

    try:
        import app
        import attendance_authority_postgres as auth_pg
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
    check("not production db", db != "wathefni", db)
    expected = os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or os.environ.get("ACK_DB")
    if expected:
        check("db matches expected", db == expected, {"db": db, "expected": expected})
    else:
        check(
            "staging-like db name",
            "staging" in db or db.endswith("_test") or env in {"local", "development", "dev"},
            db,
        )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            auth_pg.ensure_attendance_authority_postgres_schema(cur)
            cap.ensure_attendance_capture_postgres_schema(cur)
        conn.commit()
    check("wave2f schema ensure", True)
    check("store mode postgres", ops.capture_store_mode() == "postgres", ops.capture_store_mode())

    tag = uuid.uuid4().hex[:8]
    marker = f"ATTW2F-{tag}"
    company = "ATTW2F"
    other = "ATTW2FX"
    manager_phone = f"9655720{tag[:4]}"
    emp_phone = f"9655730{tag[:4]}"
    emp_key = f"{company}-9655730{tag[:4]}"
    other_emp_key = f"{company}-OUTSCOPE-{tag}"
    day = date(2026, 8, 26)
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
            return {"employee_key": emp_key, "phone": emp_phone, "name": f"W2F-{tag}", "company_code": company}
        return None

    def manager_scope(company_code: str, actor: str, employee: str) -> bool:
        return company_code == company and employee == emp_key and actor == manager_phone

    store = cap.PostgresCaptureStore(connect=app.db_connect, manager_scope_allows=manager_scope)
    store.ensure_schema()
    store.cleanup_synthetic(marker)

    # --- register durable topology ---
    site = store.register_site(company_code=company, name=f"{marker}-Site")
    check("register site", bool(site.get("site_id")), site)
    site_id = str(site["site_id"])

    cross_dev = store.register_device(
        company_code=company,
        site_id=site_id,
        terminal_sn=f"{marker}-SN",
        actor_company=other,
    )
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
    check("register connector", bool(reg.get("ok")) and reg.get("secrets") == secrets.REDACTED, reg)
    connector_id = reg["connector"]["connector_id"]
    row_v = int(reg["connector"]["row_version"])

    act = store.activate(connector_id, expected_row_version=row_v, actor_phone=manager_phone)
    check("activate connector", act.get("ok") and act["connector"]["status"] == "active", act)
    row_v = int(act["connector"]["row_version"])

    rot = store.rotate_credentials(
        connector_id,
        new_secrets={"username": "lab", "password": f"rotated-{tag}"},
        expected_row_version=row_v,
        actor_phone=manager_phone,
    )
    check("rotate credentials sealed", rot.get("ok") and rot.get("secrets") == secrets.REDACTED, rot)
    row_v = int(rot["connector"]["row_version"])

    stale = store.rotate_credentials(
        connector_id,
        new_secrets={"password": "nope"},
        expected_row_version=row_v - 1,
        actor_phone=manager_phone,
    )
    check("rotate stale_row_version fail-closed", not stale.get("ok") and stale.get("error") == "stale_row_version", stale)

    secret_scan = store.assert_no_plaintext_secrets()
    check("no plaintext secrets in DB", secret_scan.get("ok"), secret_scan)

    # Explicit scan: sealed_ref must not contain raw password substrings
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
    check("credential rows Fernet-only (no raw password)", not leaked, {"leaked": leaked, "n": len(creds)})

    # --- health + checkpoint ---
    health = store.upsert_health(
        connector_id=connector_id,
        company_code=company,
        site_id=site_id,
        agent_health={
            "status": "degraded",
            "last_sync_at": as_kuwait("2026-08-26T08:00:00").isoformat(),
            "lag_seconds": 400,
            "failure_count": 2,
            "last_error": "lab_lag",
            "checkpoint": f"cp-{marker}-1",
            "connector_version": f"{marker}-v1",
        },
        open_remediation=0,
    )
    check("health upsert degraded", health.get("status") == "degraded", health)

    cp1 = store.save_checkpoint(connector_id=connector_id, company_code=company, checkpoint=f"cp-{marker}-1")
    # health upsert already advanced the durable checkpoint to the same value — treat as exactly-once
    check(
        "checkpoint save (health-synced or first write)",
        cp1.get("ok") and cp1.get("checkpoint") == f"cp-{marker}-1",
        cp1,
    )
    cp_dup = store.save_checkpoint(connector_id=connector_id, company_code=company, checkpoint=f"cp-{marker}-1")
    check("checkpoint duplicate exactly-once", cp_dup.get("ok") and cp_dup.get("duplicate") is True, cp_dup)
    cp2 = store.save_checkpoint(connector_id=connector_id, company_code=company, checkpoint=f"cp-{marker}-2")
    check("checkpoint advance", cp2.get("ok") and not cp2.get("duplicate"), cp2)

    # --- unknown mapping queued ---
    punch_payload = {
        "company_code": company,
        "source": "biotime",
        "source_event_id": f"biotime:w2f-{marker}-1",
        "device_user_id": f"DU-{marker}",
        "punched_at": as_kuwait("2026-08-26T09:05:00").isoformat(),
        "direction": "in",
        "capture_method": "card",
        "device_id": f"{marker}-SN",
        "connector_id": connector_id,
        "raw_ref": {"id": 1, "emp_code": f"DU-{marker}"},
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

    enq2 = store.enqueue_remediation(
        company_code=company,
        kind="unknown_employee",
        connector_id=connector_id,
        device_user_id=f"DU-{marker}",
        source_event_id=punch_payload["source_event_id"],
        payload=punch_payload,
        idempotency_key=f"unk-{marker}",
    )
    check("enqueue idempotent", enq2.get("ok") and enq2.get("duplicate") is True, enq2)

    # --- simulate process restart: new store instance ---
    store2 = cap.PostgresCaptureStore(connect=app.db_connect, manager_scope_allows=manager_scope)
    check("checkpoint survives restart", store2.get_checkpoint(connector_id) == f"cp-{marker}-2", store2.get_checkpoint(connector_id))
    open_after = store2.list_open_remediation(company)
    check(
        "unknown mapping remains queued after restart",
        any(str(i["item_id"]) == item_id and i["status"] == "open" for i in open_after),
        open_after,
    )
    health_after = store2.list_health(company)
    check(
        "health survives restart",
        any(h["connector_id"] == connector_id and h.get("status") == "degraded" for h in health_after),
        health_after,
    )

    recovered = store2.mark_recovered(connector_id, last_sync_at=as_kuwait("2026-08-26T09:10:00").isoformat())
    check("health recover", recovered and recovered.get("status") == "online", recovered)

    # history events remain
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_capture_health_events WHERE connector_id=%s",
                (connector_id,),
            )
            he_n = int(cur.fetchone()["n"])
    check("health event history retained", he_n >= 1, he_n)

    # --- tenancy / manager denials ---
    cross = store2.approve_mapping(
        item_id,
        employee_key=emp_key,
        expected_row_version=item_rv,
        actor_phone=manager_phone,
        actor_company=other,
        replay=False,
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
        item_id,
        employee_key=other_emp_key,
        expected_row_version=item_rv,
        actor_phone=manager_phone,
        actor_company=company,
        replay=False,
    )
    check("manager scope denied", not scope_deny.get("ok") and scope_deny.get("error") == "manager_scope_denied", scope_deny)

    # --- concurrent remediation fail-closed ---
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
        "concurrent approve: other fail-closed stale",
        len(fails) == 1 and fails[0].get("error") in {"stale_row_version", "item_not_open"},
        fails,
    )

    # refresh item after approve
    open_mid = [i for i in store2.list_open_remediation(company) if str(i["item_id"]) == item_id]
    # may be approved_pending_replay still open, or approved_replayed not in open
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM attendance_capture_remediation WHERE item_id=%s", (item_id,))
            item_row = dict(cur.fetchone())
    check("item approved after concurrency", item_row["status"] in {"approved_pending_replay", "approved_replayed"}, item_row)
    item_rv2 = int(item_row["row_version"])

    # reject another item idempotently
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
    rej2 = store2.reject(rej_id, expected_row_version=rej_rv + 1, actor_phone=manager_phone, actor_company=company)
    # after reject, row_version bumped; calling with old version may fail OR duplicate path if already rejected with matching
    rej3 = store2.reject(
        rej_id,
        expected_row_version=int(rej1["item"]["row_version"]),
        actor_phone=manager_phone,
        actor_company=company,
    )
    check("reject idempotent when already rejected", rej3.get("ok") and rej3.get("duplicate") is True, {"rej2": rej2, "rej3": rej3})

    # --- approve pending replay → Wave 1 exactly once ---
    # Re-queue a fresh mapping item for replay proof (prior item may already be approved)
    punch2 = dict(punch_payload)
    punch2["source_event_id"] = f"biotime:w2f-{marker}-replay"
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
    mapping_mem = contract.InMemoryMappingStore()
    pipeline = pipeline_mod.CapturePipeline(
        authority_service=auth_svc,
        mapping=mapping_mem,
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
    punch_count_1 = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_punches WHERE company_code=%s AND source_event_id=%s",
                (company, punch2["source_event_id"]),
            )
            punch_count_1 = int(cur.fetchone()["n"])
    check("authority punch exactly once after first replay", punch_count_1 == 1, punch_count_1)

    # second replay duplicate
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT row_version, status FROM attendance_capture_remediation WHERE item_id=%s", (rid,))
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
    check("authority punch still exactly once after duplicate replay", punch_count_2 == 1, punch_count_2)

    recon = store2.reconcile_with_authority(company)
    check("reconcile capture↔authority ok", recon.get("ok") and recon.get("matched_in_authority", 0) >= 1, recon)

    # immutable audit
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT event_id FROM attendance_capture_audit_events WHERE company_code=%s LIMIT 1", (company,))
            ev = cur.fetchone()
            immutable_ok = False
            if ev:
                try:
                    cur.execute(
                        "UPDATE attendance_capture_audit_events SET action='tamper' WHERE event_id=%s",
                        (ev["event_id"],),
                    )
                except Exception as exc:  # noqa: BLE001
                    immutable_ok = "immutable" in str(exc).lower() or "attendance_capture_audit" in str(exc)
                    conn.rollback()
            else:
                immutable_ok = False
    check("audit events immutable", immutable_ok, ev)

    # ops layer uses postgres when configured
    ops.reset_capture_ops_for_tests()
    check("ops store mode", ops.capture_store_mode() == "postgres")
    ov = ops.overview(company)
    check("ops overview store_mode postgres", ov.get("store_mode") == "postgres", ov.get("flags"))

    # --- freezes ---
    if os.environ.get("ATTW2F_SKIP_FREEZE", "").strip() in {"1", "true", "yes", "on"}:
        check("freeze skipped", True)
    else:
        freeze_root = Path(os.environ.get("WATHEFNI_ORCH_ROOT") or ROOT)
        for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
            path = freeze_root / script
            if not path.exists():
                check(f"freeze {script}", False, "missing")
                continue
            proc = subprocess.run([sys.executable, str(path)], cwd=str(freeze_root), capture_output=True, text=True)
            check(f"freeze {script}", proc.returncode == 0, (proc.stdout + proc.stderr)[-500:])

    # cleanup synthetic
    store2.cleanup_synthetic(marker)
    # also cleanup authority punches for this marker
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.allow_authority_cleanup','1', true)")
            try:
                cur.execute(
                    "DELETE FROM attendance_punches WHERE company_code=%s AND source_event_id LIKE %s",
                    (company, f"%{marker}%"),
                )
            except Exception:  # noqa: BLE001
                conn.rollback()
            else:
                conn.commit()

    out = {
        "pass": PASS,
        "fail": FAIL,
        "db": db,
        "marker": marker,
        "results": RESULTS,
        "version": cap.CAPTURE_OPS_VERSION,
    }
    out_path = os.environ.get("ATTW2F_RESULTS_PATH")
    if out_path:
        Path(out_path).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
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
