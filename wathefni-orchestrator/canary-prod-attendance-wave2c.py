#!/usr/bin/env python3
"""Attendance Wave 2C — production synthetic BioTime + CSV canary.

Lab BioTime fixture only. Synthetic ATTW2C employees only.
Never connects a real customer device. Never enables real clocking.
Cleans synthetic authority rows afterward; leaves 42 demo rows + four reals untouched.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import tempfile
import traceback
import uuid
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

PASS = 0
FAIL = 0
RESULTS: list[dict[str, Any]] = []
SYNTHETIC_IDS: dict[str, Any] = {}

SECRET_PATTERNS = re.compile(r"(lab_synth_only|lab-token-synth-only|WATHEFNI_CAPTURE_CREDENTIAL_KEY|password\s*[:=]\s*\S+)", re.I)


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, set):
        return sorted(str(x) for x in v)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if hasattr(v, "to_dict"):
        return _jsonable(v.to_dict())
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return str(v)


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL
    detail_s = _jsonable(detail)
    # Never retain secrets in evidence details
    blob = json.dumps(detail_s, default=str)
    if SECRET_PATTERNS.search(blob):
        detail_s = {"redacted": True, "note": "secret-like content stripped from evidence"}
    RESULTS.append({"label": label, "ok": bool(cond), "detail": detail_s})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail_s}")


def main() -> int:
    if (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production":
        print("REFUSE: WATHEFNI_ENV must be production")
        return 2

    import app
    import attendance_authority_postgres as pg
    import attendance_authority_wave1 as core
    import attendance_capture_agent as agent_mod
    import attendance_capture_biotime as biotime
    import attendance_capture_contract as contract
    import attendance_capture_csv as csv_mod
    import attendance_capture_lab_biotime as lab
    import attendance_capture_pipeline as pipeline_mod

    core.reset_authority_services_for_tests()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = cur.fetchone()["db"]
    check("production database", db == "wathefni", db)
    check("authority on", core.attendance_authority_enabled() is True)
    check("synthetic only on", core.attendance_authority_synthetic_only() is True)
    check("companies WATHEFNI", "WATHEFNI" in core.attendance_authority_companies())
    check("store postgres", pg.authority_store_mode() == "postgres")
    check("import off", not app.attendance_import_enabled())
    for key in core.FOUR_REAL_ATTENDANCE_KEYS:
        check(
            f"real denied {key}",
            core.attendance_authority_allowed_for("WATHEFNI", {"employee_key": key, "phone": key.split("-")[-1]}) is False,
        )

    # Baseline fingerprint
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            before_n = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'")
            before_demo = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|' ORDER BY attendance_id::text)) AS fp
                FROM attendance_records WHERE company_code='WATHEFNI'
                """
            )
            before_fp = cur.fetchone()["fp"]
    check("baseline 42 rows", before_n == 42 and before_demo == 42, {"n": before_n, "demo": before_demo})

    tag = uuid.uuid4().hex[:8]
    company = "WATHEFNI"
    phone = f"965524{tag[:6]}"
    emp_key = f"WATHEFNI-ATTW2C-{tag}"
    device_user_id = f"9{tag[:3]}"  # synthetic lab id, not a real phone
    terminal_sn = f"LAB-W2C-{tag[:6].upper()}"
    connector_id = f"w2c-lab-{tag}"
    emp = {"employee_key": emp_key, "phone": phone, "name": f"W2C-SYNTH|{tag}", "company_code": company}
    SYNTHETIC_IDS.update(
        {
            "tag": tag,
            "employee_key": emp_key,
            "phone": phone,
            "device_user_id": device_user_id,
            "terminal_sn": terminal_sn,
            "connector_id": connector_id,
        }
    )
    check("synthetic allowed", core.attendance_authority_allowed_for(company, emp) is True)

    day = date(2026, 9, 10)
    overnight = date(2026, 9, 11)
    shift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    oshift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": overnight,
        "start_time": time(22, 0),
        "end_time": time(6, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    SYNTHETIC_IDS["shift_id"] = shift["shift_id"]
    SYNTHETIC_IDS["oshift_id"] = oshift["shift_id"]

    # Lab BioTime fixture — synthetic only
    rows = lab.default_rows(device_user_id, terminal_sn)
    lab.assert_synthetic_only(rows)
    check("lab fixture synthetic only", True, {"emp_codes": sorted({r["emp_code"] for r in rows}), "sn": terminal_sn})
    # credentials for lab — values never printed into evidence via check()
    lab_user = os.environ.get("W2C_LAB_USER") or "lab_synth"
    lab_pass = os.environ.get("W2C_LAB_PASS") or "lab_synth_only"
    lab_token = os.environ.get("W2C_LAB_TOKEN") or "lab-token-synth-only"
    state = lab.LabBioTimeState(rows, username=lab_user, password=lab_pass, token=lab_token)
    httpd = lab.serve("127.0.0.1", 19199, state)
    base_url = "http://127.0.0.1:19199/"

    store = pg.PostgresAuthorityStore(app.db_connect)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pg.ensure_attendance_authority_postgres_schema(cur)
        conn.commit()
    svc = core.AttendanceAuthorityService(store=store)
    mapping = contract.InMemoryMappingStore()
    mapping.upsert_mapping(company_code=company, device_user_id=device_user_id, employee_key=emp_key, device_id=terminal_sn)

    def resolve(cc: str, ek: str) -> dict[str, Any] | None:
        if cc.upper() == company and ek == emp_key:
            return emp
        return None

    pipe = pipeline_mod.CapturePipeline(
        authority_service=svc,
        mapping=mapping,
        employee_resolver=resolve,
        connector_id=connector_id,
    )

    # Privacy rejection
    poison = {
        "id": 9999,
        "emp_code": device_user_id,
        "punch_time": "2026-09-10 09:01:00",
        "punch_state": "0",
        "verify_type": 1,
        "fingerprint_image": "x",
        "template": "ab" * 80,
        "terminal_sn": terminal_sn,
    }
    bad = biotime.transaction_to_canonical(poison, company_code=company, connector_id=connector_id)
    check("privacy reject images/templates", bad.get("privacy_hard_fail") is True, {"error": bad.get("error"), "keys": bad.get("forbidden_keys")})

    # BioTime pull via real HTTP client
    client = biotime.BioTimeClient(base_url=base_url, username=lab_user, password=lab_pass, token=lab_token)
    pulled = biotime.pull_transactions_paginated(client, company_code=company, connector_id=connector_id, page_size=2)
    check("biotime pagination", int(pulled.get("pages") or 0) >= 2, pulled.get("pages"))
    check("biotime pulled 4", len(pulled["punches"]) == 4, len(pulled["punches"]))
    methods = {p.capture_method for p in pulled["punches"]}
    check("metadata card+face+biometric types", {"card", "face", "biometric"} <= methods, sorted(methods))
    check(
        "no biometric payloads retained",
        all(
            "template" not in (p.raw_ref or {})
            and "fingerprint_image" not in (p.raw_ref or {})
            and "face_image" not in (p.raw_ref or {})
            for p in pulled["punches"]
        ),
    )

    def shift_for(p):
        at = p.punched_at if hasattr(p, "punched_at") else None
        if at and at.date() >= overnight:
            return oshift
        return shift

    batch = pipe.ingest_many(pulled["punches"], shift_for=shift_for)
    check("authority ingest biotime", batch["accepted"] == 4 and batch["failed"] == 0 and batch["quarantined"] == 0, batch)
    dup = pipe.ingest_many(pulled["punches"], shift_for=shift_for)
    check("duplicate pull idempotent", dup["duplicates"] == 4, dup)

    proj = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift["shift_id"]))
    check("normal projection 480", proj is not None and int(proj.get("worked_minutes") or 0) == 480, {"worked": (proj or {}).get("worked_minutes")})
    oproj = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=overnight, shift_key=core.shift_key_of(oshift["shift_id"]))
    check("overnight projection 480", oproj is not None and int(oproj.get("worked_minutes") or 0) == 480, {"worked": (oproj or {}).get("worked_minutes")})
    if proj:
        SYNTHETIC_IDS["projection_id"] = str(proj.get("projection_id"))

    # Checkpoint resume with extra lab rows
    with state.lock:
        state.rows.extend(
            [
                {"id": 2301, "emp_code": device_user_id, "punch_time": "2026-09-10 12:00:00", "punch_state": "2", "verify_type": 2, "terminal_sn": terminal_sn},
                {"id": 2302, "emp_code": device_user_id, "punch_time": "2026-09-10 12:30:00", "punch_state": "3", "verify_type": 2, "terminal_sn": terminal_sn},
            ]
        )
    resumed = biotime.pull_transactions_paginated(
        client, company_code=company, connector_id=connector_id, after_checkpoint="biotime:2202", page_size=10
    )
    ids = {p.source_event_id for p in resumed["punches"]}
    check("checkpoint resume", "biotime:2101" not in ids and "biotime:2301" in ids, sorted(ids))

    # Agent durability
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "agent.sqlite")
        # Prefer env-provided key; generate ephemeral if absent (still sealed at rest in agent db)
        key = os.environ.get("WATHEFNI_CAPTURE_CREDENTIAL_KEY") or agent_mod.CredentialVault.generate_key()
        vault = agent_mod.CredentialVault(key=key)
        delivered: list[str] = []

        def upload(payload: dict) -> dict:
            delivered.append(payload["source_event_id"])
            return {"ok": True}

        cfg = agent_mod.AgentConfig(company_code=company, connector_id=connector_id, biotime_base_url=base_url, db_path=db_path, page_size=10)
        ag = agent_mod.WathefniCaptureAgent(cfg, vault=vault, upload=upload, biotime_client=client)
        ag.set_biotime_secrets(username=lab_user, password=lab_pass, token=lab_token)
        poll = ag.poll_biotime_once()
        check("agent poll enqueue", poll.get("ok") is True and int(poll.get("enqueued") or 0) >= 1, {"enqueued": poll.get("enqueued"), "pages": poll.get("pages")})
        offline = contract.CanonicalPunch(
            company_code=company,
            source="biotime",
            source_event_id=f"biotime:offline-{tag}",
            device_user_id=device_user_id,
            punched_at=contract.as_kuwait("2026-09-10 10:00:00"),
            direction="in",
            capture_method="card",
            device_id=terminal_sn,
            connector_id=connector_id,
        )
        n = ag.simulate_offline_enqueue([offline])
        check("agent offline queue", n == 1)
        flush = ag.flush_outbox(limit=1000)
        check("agent reconnect replay", int(flush.get("delivered") or 0) >= 2, flush)
        # restart
        ag2 = agent_mod.WathefniCaptureAgent(cfg, vault=vault, upload=upload, biotime_client=client)
        sealed, _prev = ag2.store.load_credentials(connector_id)
        check("credentials sealed durable", bool(sealed) and "lab_synth" not in str(sealed))
        check("restart outbox empty", ag2.store.pending() == [])
        cp = ag2.store.get_checkpoint(connector_id)
        check("checkpoint durable", bool(cp), cp)
        SYNTHETIC_IDS["checkpoint"] = cp
        # invalid credentials
        class AuthFail(biotime.BioTimeClient):
            def list_transactions(self, **kwargs):  # type: ignore[override]
                raise biotime.BioTimeAuthError("auth_failed:401")

        ag2.client = AuthFail(base_url=base_url)
        bad_poll = ag2.poll_biotime_once()
        check("invalid credentials fail", bad_poll.get("auth_error") is True)
        ag2.rotate_biotime_secrets(username=lab_user, password=lab_pass, token=lab_token)
        ag2.client = biotime.BioTimeClient(base_url=base_url, username=lab_user, password=lab_pass, token=lab_token)
        good = ag2.poll_biotime_once()
        check("credential rotation recovers", good.get("ok") is True)
        health = ag2.health()
        check(
            "connector health model",
            health.get("connector_id") == connector_id and health.get("status") in {"ok", "degraded", "error"},
            {"status": health.get("status"), "checkpoint": health.get("checkpoint"), "version": health.get("connector_version")},
        )
        # failure state after auth error retained count
        check("health tracks errors", int(health.get("error_count") or 0) >= 1, health.get("error_count"))

    # Unknown user quarantine + mapped replay
    unknown = {
        "id": 8888,
        "emp_code": "9999",
        "punch_time": "2026-09-10 09:05:00",
        "punch_state": "0",
        "verify_type": 2,
        "terminal_sn": terminal_sn,
    }
    um = biotime.transaction_to_canonical(unknown, company_code=company, connector_id=connector_id)
    ures = pipe.ingest_canonical(um["punch"], shift=shift)
    check("unknown quarantined", ures.get("quarantined") is True, ures.get("reason"))
    SYNTHETIC_IDS["quarantine_id"] = ures.get("quarantine_id")
    replay = pipe.map_and_replay_quarantine(ures["quarantine_id"], employee_key=emp_key, shift=shift)
    check("mapped quarantine replay", replay.get("ok") is True, {"created": replay.get("created"), "duplicate": replay.get("duplicate")})

    # CSV / XLSX idempotent + interrupted resume
    def make_csv(rows_data: list[dict]) -> bytes:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["emp_code", "punch_time", "direction", "terminal_sn", "method"])
        w.writeheader()
        for r in rows_data:
            w.writerow(r)
        return buf.getvalue().encode("utf-8")

    csv_day = date(2026, 9, 13)
    csv_shift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": csv_day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    csv_rows = [
        {"emp_code": device_user_id, "punch_time": "2026-09-13 09:00:00", "direction": "in", "terminal_sn": terminal_sn, "method": "card"},
        {"emp_code": device_user_id, "punch_time": "2026-09-13 17:00:00", "direction": "out", "terminal_sn": terminal_sn, "method": "card"},
    ]
    file_a = make_csv(csv_rows)
    file_b = make_csv(csv_rows)
    pa = csv_mod.parse_file_to_canonical(company_code=company, connector_id=connector_id, data=file_a, filename="a.csv")
    pb = csv_mod.parse_file_to_canonical(company_code=company, connector_id=connector_id, data=file_b, filename="b.csv")
    check("csv same content same ids", [p.source_event_id for p in pa["punches"]] == [p.source_event_id for p in pb["punches"]])
    r1 = pipe.ingest_many(pa["punches"], shift_for=lambda _p: csv_shift)
    r2 = pipe.ingest_many(pb["punches"], shift_for=lambda _p: csv_shift)
    check("csv duplicate across files", r1["accepted"] == 2 and r2["duplicates"] == 2, {"r1": r1["accepted"], "r2_dup": r2["duplicates"]})

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["emp_code", "punch_time", "direction", "terminal_sn", "method"])
    ws.append([device_user_id, "2026-09-14 09:00:00", "in", terminal_sn, "pin"])
    ws.append([device_user_id, "2026-09-14 17:00:00", "out", terminal_sn, "pin"])
    bio = io.BytesIO()
    wb.save(bio)
    xday = date(2026, 9, 14)
    xshift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": xday,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    px = csv_mod.parse_file_to_canonical(company_code=company, connector_id=connector_id, data=bio.getvalue(), filename="d.xlsx")
    xr = pipe.ingest_many(px["punches"], shift_for=lambda _p: xshift)
    check("xlsx ingest", xr["accepted"] == 2, xr)

    with tempfile.TemporaryDirectory() as td:
        drop = Path(td) / "drop"
        drop.mkdir()
        (drop / "one.csv").write_bytes(file_a)
        sftp = csv_mod.SftpFileSource(drop)
        batches = sftp.ingest_all(company_code=company, connector_id=connector_id)
        check("sftp drop parse", batches["files"] == 1)
        astore = agent_mod.AgentStore(Path(td) / "f.sqlite")
        first = astore.mark_file_processed(pa["file_sha256"], "one.csv")
        second = astore.mark_file_processed(pa["file_sha256"], "one.csv")
        check("interrupted import resume", first is True and second is False)

    # Payroll snapshot + correction survives reimport
    csv_proj = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=csv_day, shift_key=core.shift_key_of(csv_shift["shift_id"]))
    check("csv day projection 480", csv_proj is not None and int(csv_proj.get("worked_minutes") or 0) == 480)
    appr = svc.approve_day(company_code=company, employee=emp, work_date=csv_day, shift=csv_shift, approved_by_phone="96550000001")
    check("day approved + snapshot", appr.get("ok") is True, {"payroll_eligible": (appr.get("projection") or {}).get("payroll_eligible")})
    snap = appr.get("snapshot") or {}
    worked = int((snap.get("payload") or {}).get("worked_minutes") or 0)
    check("payroll reconcile exact", worked == 480, {"worked": worked, "snapshot_id": snap.get("snapshot_id")})
    SYNTHETIC_IDS["snapshot_id"] = str(snap.get("snapshot_id"))
    corr = svc.request_correction(
        company_code=company,
        employee=emp,
        work_date=csv_day,
        requested_by_phone="96550000002",
        changes={"check_out_at": "2026-09-13T17:30:00+03:00"},
        shift=csv_shift,
    )
    check("correction after snapshot", corr.get("ok") is True)
    # approve correction so it materializes punches; then reimport must not wipe
    if corr.get("ok"):
        cid = corr["correction"]["correction_id"]
        reviewed = svc.review_correction(
            company_code=company,
            correction_id=str(cid),
            decision="approved",
            decided_by_phone="96550000001",
            employee=emp,
            shift=csv_shift,
        )
        check("correction approved", reviewed.get("ok") is True, reviewed.get("error"))
    reimport = pipe.ingest_many(pa["punches"], shift_for=lambda _p: csv_shift)
    check("reimport idempotent after correction", reimport["duplicates"] == 2 and reimport["failed"] == 0, reimport)
    snaps = store.list_payroll_snapshots(company_code=company, employee_key=emp_key, start_date=csv_day, end_date=csv_day)
    check(
        "reversal does not alter approved snapshot",
        snaps and int((snaps[0].get("payload") or {}).get("worked_minutes") or 0) == 480,
        {"n": len(snaps), "worked": (snaps[0].get("payload") or {}).get("worked_minutes") if snaps else None},
    )

    # Tenant isolation: other company synthetic must not appear in WATHEFNI lists for this emp
    other_company_punch = contract.CanonicalPunch(
        company_code="OTHERCO",
        source="biotime",
        source_event_id=f"biotime:other-{tag}",
        device_user_id=device_user_id,
        punched_at=contract.as_kuwait("2026-09-10 09:00:00"),
        direction="in",
        capture_method="card",
        device_id=terminal_sn,
        connector_id=f"other-{tag}",
        employee_key=emp_key,
    )
    # Pipeline require_mapping with OTHERCO — authority company gate may reject; ensure WATHEFNI punches unchanged count
    before_p = store.list_punches(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift["shift_id"]))
    # Direct store append attempt via ingest with wrong company should not pollute WATHEFNI if company gate fails
    try:
        other_res = pipe.ingest_canonical(other_company_punch, shift=shift)
    except Exception as exc:  # noqa: BLE001
        other_res = {"ok": False, "error": repr(exc)}
    after_p = store.list_punches(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift["shift_id"]))
    check("cross-tenant isolation", len(before_p) == len(after_p), {"before": len(before_p), "after": len(after_p), "other": other_res.get("error") or other_res.get("ok")})

    # Secrets must not appear in evidence JSON we emit
    evidence_blob = json.dumps({"results": RESULTS, "ids": SYNTHETIC_IDS}, default=str)
    check("secrets absent from evidence", SECRET_PATTERNS.search(evidence_blob) is None)

    # Cleanup synthetic authority data
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.allow_authority_cleanup','1', true)")
            for table in (
                "attendance_compat_drift",
                "attendance_authority_events",
                "attendance_payroll_snapshots",
                "attendance_corrections",
                "attendance_day_projections",
                "attendance_punches",
            ):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s AND employee_key=%s", (company, emp_key))
            cur.execute("SELECT COUNT(*) AS n FROM attendance_punches WHERE employee_key=%s", (emp_key,))
            left_p = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM attendance_day_projections WHERE employee_key=%s", (emp_key,))
            left_d = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            after_n = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'")
            after_demo = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|' ORDER BY attendance_id::text)) AS fp
                FROM attendance_records WHERE company_code='WATHEFNI'
                """
            )
            after_fp = cur.fetchone()["fp"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM employees WHERE employee_key = ANY(%s)",
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            four = int(cur.fetchone()["n"])
        conn.commit()
    check("synthetic punches cleaned", left_p == 0)
    check("synthetic projections cleaned", left_d == 0)
    check("demo rows untouched count", after_n == 42 and after_demo == 42, {"n": after_n, "demo": after_demo})
    check("demo fingerprint unchanged", after_fp == before_fp)
    check("four reals still present", four == 4, four)

    httpd.shutdown()

    summary = {"pass": PASS, "fail": FAIL}
    out = {
        "summary": summary,
        "synthetic_ids": SYNTHETIC_IDS,
        "results": RESULTS,
    }
    print(json.dumps({"summary": summary, "synthetic_ids": SYNTHETIC_IDS}, indent=2, default=str))
    print(f"SUMMARY pass={PASS} fail={FAIL}")
    out_dir = os.environ.get("WAVE2C_CANARY_OUT")
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        Path(out_dir, "canary-evidence.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
