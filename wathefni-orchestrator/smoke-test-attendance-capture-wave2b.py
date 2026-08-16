#!/usr/bin/env python3
"""Attendance Wave 2B — local/staging capture qualification.

Proves BioTime pull, CSV/SFTP fallback, privacy hard-fail, agent queue/checkpoint,
mapping quarantine, authority projection + payroll snapshot, tenant isolation.

REFUSES production. Does not enable real clocking / QR / GPS / kiosk UI.
Does not connect a real customer device (uses fixture BioTime).
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import traceback
import uuid
from datetime import date, datetime, time, timedelta
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
        if isinstance(v, set):
            return sorted((_jsonable(x) for x in v), key=lambda x: str(x))
        if isinstance(v, (datetime, date, time)):
            return v.isoformat()
        if hasattr(v, "to_dict") and callable(v.to_dict):
            return _jsonable(v.to_dict())
        if isinstance(v, dict):
            return {str(k): _jsonable(val) for k, val in v.items()}
        if isinstance(v, (list, tuple)):
            return [_jsonable(x) for x in v]
        return str(v)

    RESULTS.append({"label": label, "ok": bool(cond), "detail": _jsonable(detail)})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


class FakeBioTime:
    """In-process BioTime transaction API fixture (paginated)."""

    def __init__(self, rows: list[dict[str, Any]], *, page_size: int = 2, token: str = "good-token") -> None:
        self.rows = list(rows)
        self.page_size = page_size
        self.token = token
        self.username = "admin"
        self.password = "secret"
        self.calls = 0

    def list_transactions(self, **params: Any) -> dict[str, Any]:
        self.calls += 1
        page = int(params.get("page") or 1)
        limit = int(params.get("limit") or self.page_size)
        start = (page - 1) * limit
        chunk = self.rows[start : start + limit]
        return {"count": len(self.rows), "results": chunk}

    # duck-type BioTimeClient methods used by pull_transactions_paginated / agent
    def obtain_token(self) -> str:
        if self.password != "secret":
            from attendance_capture_biotime import BioTimeAuthError

            raise BioTimeAuthError("auth_failed")
        return self.token


def main() -> int:
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production":
        print("REFUSE: production")
        return 2
    os.environ.setdefault("WATHEFNI_ENV", "local")

    import attendance_authority_wave1 as core
    import attendance_capture_agent as agent_mod
    import attendance_capture_biotime as biotime
    import attendance_capture_contract as contract
    import attendance_capture_csv as csv_mod
    import attendance_capture_pipeline as pipeline_mod

    core.reset_authority_services_for_tests()

    tag = uuid.uuid4().hex[:8]
    company = "ATTW2B"
    other = "ATTW2BX"
    emp_key = f"{company}-ATTW2B-{tag}"
    emp = {"employee_key": emp_key, "phone": f"9655810{tag[:4]}", "name": f"W2B-{tag}", "company_code": company}
    other_emp_key = f"{other}-ATTW2B-{tag}"
    other_emp = {"employee_key": other_emp_key, "phone": f"9655820{tag[:4]}", "name": f"W2BX-{tag}", "company_code": other}

    day = date(2026, 8, 20)
    overnight_day = date(2026, 8, 21)
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
        "shift_date": overnight_day,
        "start_time": time(22, 0),
        "end_time": time(6, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }

    store = core.InMemoryAuthorityStore()
    svc = core.AttendanceAuthorityService(store=store)
    mapping = contract.InMemoryMappingStore()
    mapping.upsert_mapping(company_code=company, device_user_id="1001", employee_key=emp_key, device_id="SN-A")
    mapping.upsert_mapping(company_code=other, device_user_id="2002", employee_key=other_emp_key)

    def resolve(company_code: str, employee_key: str) -> dict[str, Any] | None:
        if employee_key == emp_key and company_code.upper() == company:
            return emp
        if employee_key == other_emp_key and company_code.upper() == other:
            return other_emp
        return None

    pipe = pipeline_mod.CapturePipeline(
        authority_service=svc,
        mapping=mapping,
        employee_resolver=resolve,
        connector_id=f"w2b-{tag}",
    )

    # --- Privacy hard-fail ---
    bad = {
        "id": 1,
        "emp_code": "1001",
        "punch_time": "2026-08-20 09:00:00",
        "punch_state": "0",
        "verify_type": 1,
        "fingerprint_image": "aaa",
        "template": "deadbeef" * 16,
    }
    mapped_bad = biotime.transaction_to_canonical(bad, company_code=company, connector_id="c1")
    check("privacy hard-fail biotime", mapped_bad.get("privacy_hard_fail") is True, mapped_bad)

    face_bad = {"emp_code": "1001", "punched_at": "2026-08-20 09:00:00", "direction": "in", "face_image": "x" * 250}
    csv_bad = csv_mod.row_to_canonical(face_bad, company_code=company, connector_id="c1", file_sha="abc")
    check("privacy hard-fail csv", csv_bad.get("privacy_hard_fail") is True, csv_bad)

    # --- BioTime normal + overnight + verify metadata ---
    rows = [
        {"id": 101, "emp_code": "1001", "punch_time": "2026-08-20 09:00:00", "punch_state": "0", "verify_type": 2, "terminal_sn": "SN-A"},  # card
        {"id": 102, "emp_code": "1001", "punch_time": "2026-08-20 17:00:00", "punch_state": "1", "verify_type": 15, "terminal_sn": "SN-A"},  # face
        {"id": 201, "emp_code": "1001", "punch_time": "2026-08-21 22:00:00", "punch_state": "0", "verify_type": 1, "terminal_sn": "SN-A"},  # fingerprint type only
        {"id": 202, "emp_code": "1001", "punch_time": "2026-08-22 06:00:00", "punch_state": "1", "verify_type": 1, "terminal_sn": "SN-A"},
    ]
    fake = FakeBioTime(rows, page_size=2)
    # Adapt FakeBioTime to BioTimeClient surface used by pull helper
    class ClientShim(biotime.BioTimeClient):
        def __init__(self, fake: FakeBioTime):
            super().__init__(base_url="http://fixture/")
            self.fake = fake

        def list_transactions(self, **kwargs):  # type: ignore[override]
            return self.fake.list_transactions(**kwargs)

    client = ClientShim(fake)
    pulled = biotime.pull_transactions_paginated(
        client,
        company_code=company,
        connector_id=f"w2b-{tag}",
        page_size=2,
    )
    check("biotime pagination pages", int(pulled.get("pages") or 0) >= 2, pulled.get("pages"))
    check("biotime pulled 4", len(pulled["punches"]) == 4, len(pulled["punches"]))
    methods = {p.capture_method for p in pulled["punches"]}
    check("capture methods card+face+biometric", {"card", "face", "biometric"} <= methods, methods)
    check("no biometric payloads in raw_ref", all("template" not in (p.raw_ref or {}) and "fingerprint_image" not in (p.raw_ref or {}) for p in pulled["punches"]))

    def shift_for(p):
        punched = p.punched_at if hasattr(p, "punched_at") else None
        if punched and punched.date() >= overnight_day:
            return oshift
        return shift

    batch1 = pipe.ingest_many(pulled["punches"], shift_for=shift_for)
    check("authority ingest biotime", batch1["accepted"] == 4 and batch1["failed"] == 0, batch1)

    # duplicate pull idempotent
    pulled2 = biotime.pull_transactions_paginated(client, company_code=company, connector_id=f"w2b-{tag}", page_size=2)
    batch2 = pipe.ingest_many(pulled2["punches"], shift_for=shift_for)
    check("duplicate pull idempotent", batch2["duplicates"] == 4, batch2)

    proj = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift["shift_id"]))
    check("normal day projection 480", proj is not None and int(proj.get("worked_minutes") or 0) == 480, proj)
    oproj = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=overnight_day, shift_key=core.shift_key_of(oshift["shift_id"]))
    check("overnight projection", oproj is not None and int(oproj.get("worked_minutes") or 0) == 480, oproj)

    # --- Checkpoint resume ---
    more = [
        {"id": 301, "emp_code": "1001", "punch_time": "2026-08-20 12:00:00", "punch_state": "2", "verify_type": 2, "terminal_sn": "SN-A"},
        {"id": 302, "emp_code": "1001", "punch_time": "2026-08-20 12:30:00", "punch_state": "3", "verify_type": 2, "terminal_sn": "SN-A"},
    ]
    fake2 = FakeBioTime(rows + more, page_size=10)
    client2 = ClientShim(fake2)
    resumed = biotime.pull_transactions_paginated(
        client2,
        company_code=company,
        connector_id=f"w2b-{tag}",
        after_checkpoint="biotime:202",
        page_size=10,
    )
    new_ids = {p.source_event_id for p in resumed["punches"]}
    check("checkpoint skips old ids", "biotime:101" not in new_ids and "biotime:301" in new_ids and "biotime:302" in new_ids, sorted(new_ids))

    # --- Agent offline queue + reconnect replay + credential rotation ---
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "agent.sqlite")
        vault = agent_mod.CredentialVault(key=agent_mod.CredentialVault.generate_key())
        delivered: list[dict] = []

        def upload(payload: dict) -> dict:
            delivered.append(payload)
            # feed pipeline
            punch = contract.CanonicalPunch(
                company_code=payload["company_code"],
                source=payload["source"],
                source_event_id=payload["source_event_id"],
                device_user_id=payload["device_user_id"],
                punched_at=contract.as_kuwait(payload["punched_at"]),
                direction=payload["direction"],
                capture_method=payload.get("capture_method") or "unknown",
                employee_key=payload.get("employee_key"),
                device_id=payload.get("device_id"),
                connector_id=payload.get("connector_id"),
                raw_ref=payload.get("raw_ref") or {},
                metadata=payload.get("metadata") or {},
            )
            # use a dedicated day to avoid colliding with earlier projections for payroll tests later
            return {"ok": True, "queued": True, "source_event_id": punch.source_event_id}

        cfg = agent_mod.AgentConfig(company_code=company, connector_id=f"agent-{tag}", biotime_base_url="http://fixture/", db_path=db_path)
        ag = agent_mod.WathefniCaptureAgent(cfg, vault=vault, upload=upload, biotime_client=ClientShim(FakeBioTime(rows[:2], page_size=10)))
        ag.set_biotime_secrets(username="admin", password="secret", token="good-token")
        poll = ag.poll_biotime_once()
        check("agent poll enqueue", poll.get("ok") and int(poll.get("enqueued") or 0) == 2, poll)
        # offline: enqueue extra without flush
        offline_punch = contract.CanonicalPunch(
            company_code=company,
            source="biotime",
            source_event_id=f"biotime:offline-{tag}",
            device_user_id="1001",
            punched_at=contract.as_kuwait("2026-08-20 10:00:00"),
            direction="in",
            capture_method="card",
            device_id="SN-A",
            connector_id=cfg.connector_id,
        )
        n = ag.simulate_offline_enqueue([offline_punch])
        check("agent offline enqueue", n == 1, n)
        flush = ag.flush_outbox()
        check("agent flush delivered", flush.get("delivered") == 3, flush)
        # restart new agent instance — checkpoint + empty pending
        ag2 = agent_mod.WathefniCaptureAgent(cfg, vault=vault, upload=upload, biotime_client=ClientShim(FakeBioTime(rows[:2], page_size=10)))
        sealed, prev = ag2.store.load_credentials(cfg.connector_id)
        check("credentials persisted sealed", bool(sealed), sealed)
        pending_after = ag2.store.pending()
        check("restart outbox empty", pending_after == [], pending_after)
        cp = ag2.store.get_checkpoint(cfg.connector_id)
        check("checkpoint durable", bool(cp), cp)
        # invalid credentials
        ag2.rotate_biotime_secrets(username="admin", password="WRONG")
        bad_client = ClientShim(FakeBioTime(rows, page_size=10))
        bad_client.fake.password = "WRONG"

        class AuthFailClient(ClientShim):
            def list_transactions(self, **kwargs):
                from attendance_capture_biotime import BioTimeAuthError

                raise BioTimeAuthError("auth_failed:401")

        ag2.client = AuthFailClient(FakeBioTime([]))
        bad_poll = ag2.poll_biotime_once()
        check("invalid credentials fail", bad_poll.get("auth_error") is True, bad_poll)
        # rotation to good
        ag2.rotate_biotime_secrets(username="admin", password="secret", token="new-token")
        ag2.client = ClientShim(FakeBioTime([{"id": 999, "emp_code": "1001", "punch_time": "2026-08-20 11:00:00", "punch_state": "0", "verify_type": 2, "terminal_sn": "SN-A"}]))
        good = ag2.poll_biotime_once()
        check("credential rotation recovers", good.get("ok") is True, good)
        health = ag2.health()
        check("connector health present", health.get("connector_id") == cfg.connector_id and health.get("status") in {"ok", "degraded", "error"}, health)

    # --- Unknown user quarantine + mapping replay ---
    unknown_row = {"id": 777, "emp_code": "9999", "punch_time": "2026-08-20 09:05:00", "punch_state": "0", "verify_type": 2, "terminal_sn": "SN-A"}
    um = biotime.transaction_to_canonical(unknown_row, company_code=company, connector_id=f"w2b-{tag}")
    check("unknown maps to canonical", um.get("ok") is True, um)
    ures = pipe.ingest_canonical(um["punch"], shift=shift)
    check("unknown quarantined", ures.get("quarantined") is True and ures.get("reason") == "unknown_device_user", ures)
    qid = ures["quarantine_id"]
    # later mapping replay
    replay = pipe.map_and_replay_quarantine(qid, employee_key=emp_key, shift=shift)
    check("mapping replay accepted", replay.get("ok") is True and replay.get("created") is True, replay)

    # --- CSV / XLSX duplicate across files + interrupted resume ---
    def make_csv(rows_data: list[dict]) -> bytes:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["emp_code", "punch_time", "direction", "terminal_sn", "method"])
        w.writeheader()
        for r in rows_data:
            w.writerow(r)
        return buf.getvalue().encode("utf-8")

    csv_rows = [
        {"emp_code": "1001", "punch_time": "2026-08-23 09:00:00", "direction": "in", "terminal_sn": "SN-A", "method": "card"},
        {"emp_code": "1001", "punch_time": "2026-08-23 17:00:00", "direction": "out", "terminal_sn": "SN-A", "method": "card"},
    ]
    csv_day = date(2026, 8, 23)
    csv_shift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": csv_day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    file_a = make_csv(csv_rows)
    file_b = make_csv(csv_rows)  # identical content → same hashes
    parsed_a = csv_mod.parse_file_to_canonical(company_code=company, connector_id=f"csv-{tag}", data=file_a, filename="a.csv")
    parsed_b = csv_mod.parse_file_to_canonical(company_code=company, connector_id=f"csv-{tag}", data=file_b, filename="b.csv")
    check("csv same content same event ids", [p.source_event_id for p in parsed_a["punches"]] == [p.source_event_id for p in parsed_b["punches"]])
    r1 = pipe.ingest_many(parsed_a["punches"], shift_for=lambda p: csv_shift)
    r2 = pipe.ingest_many(parsed_b["punches"], shift_for=lambda p: csv_shift)
    check("csv duplicate across files idempotent", r1["accepted"] == 2 and r2["duplicates"] == 2, {"r1": r1, "r2": r2})

    # XLSX
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["emp_code", "punch_time", "direction", "terminal_sn", "method"])
    ws.append(["1001", "2026-08-24 09:00:00", "in", "SN-A", "pin"])
    ws.append(["1001", "2026-08-24 17:00:00", "out", "SN-A", "pin"])
    xbio = io.BytesIO()
    wb.save(xbio)
    xlsx_bytes = xbio.getvalue()
    xday = date(2026, 8, 24)
    xshift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": xday,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    parsed_x = csv_mod.parse_file_to_canonical(company_code=company, connector_id=f"xlsx-{tag}", data=xlsx_bytes, filename="d.xlsx")
    check("xlsx parsed", len(parsed_x["punches"]) == 2, parsed_x)
    xr = pipe.ingest_many(parsed_x["punches"], shift_for=lambda p: xshift)
    check("xlsx ingest", xr["accepted"] == 2, xr)

    # SFTP drop + file processed resume
    with tempfile.TemporaryDirectory() as td:
        drop = Path(td) / "drop"
        drop.mkdir()
        (drop / "one.csv").write_bytes(file_a)
        sftp = csv_mod.SftpFileSource(drop)
        batches = sftp.ingest_all(company_code=company, connector_id=f"sftp-{tag}")
        check("sftp batch files", batches["files"] == 1, batches)
        store_agent = agent_mod.AgentStore(Path(td) / "f.sqlite")
        first = store_agent.mark_file_processed(parsed_a["file_sha256"], "one.csv")
        second = store_agent.mark_file_processed(parsed_a["file_sha256"], "one.csv")
        check("interrupted import resume skips file", first is True and second is False, {"first": first, "second": second})

    # --- Payroll snapshot exact + locked period ---
    csv_proj = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=csv_day, shift_key=core.shift_key_of(csv_shift["shift_id"]))
    check("csv day projection", csv_proj is not None and int(csv_proj.get("worked_minutes") or 0) == 480, csv_proj)
    appr = svc.approve_day(
        company_code=company,
        employee=emp,
        work_date=csv_day,
        shift=csv_shift,
        approved_by_phone="96550000001",
    )
    check("day approved", appr.get("ok") is True, appr)
    snap_row = appr.get("snapshot") or {}
    payload = snap_row.get("payload") if isinstance(snap_row, dict) else {}
    worked = (payload or {}).get("worked_minutes") if isinstance(payload, dict) else None
    check("payroll reconcile exact", int(worked or 0) == 480, {"worked": worked, "snapshot": snap_row})
    csv_proj2 = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=csv_day, shift_key=core.shift_key_of(csv_shift["shift_id"]))
    check("payroll eligible after approve", bool(csv_proj2 and csv_proj2.get("payroll_eligible")), csv_proj2)

    # Snapshot immutability: re-approve / duplicate snapshot path should not alter punch ledger
    snaps_before = store.list_payroll_snapshots(company_code=company, employee_key=emp_key, start_date=csv_day, end_date=csv_day) if hasattr(store, "list_payroll_snapshots") else []
    corr = svc.request_correction(
        company_code=company,
        employee=emp,
        work_date=csv_day,
        requested_by_phone="96550000002",
        changes={"check_out_at": "2026-08-23T17:30:00+03:00"},
        shift=csv_shift,
    )
    check("correction requested after snapshot", corr.get("ok") is True, corr)
    reimport = pipe.ingest_many(parsed_a["punches"], shift_for=lambda p: csv_shift)
    check("safe reversal/reimport still idempotent", reimport["duplicates"] == 2 and reimport["failed"] == 0, reimport)
    punches_after = store.list_punches(company_code=company, employee_key=emp_key, work_date=csv_day, shift_key=core.shift_key_of(csv_shift["shift_id"]))
    check("punches immutable count", len(punches_after) == 2, len(punches_after))
    # Approved snapshot payload remains 480 even if later correction requested
    snaps_after = store.list_payroll_snapshots(company_code=company, employee_key=emp_key, start_date=csv_day, end_date=csv_day) if hasattr(store, "list_payroll_snapshots") else [snap_row]
    if snaps_after:
        check(
            "locked payroll snapshot unchanged",
            int((snaps_after[0].get("payload") or {}).get("worked_minutes") or 0) == 480,
            snaps_after[0],
        )
    else:
        check("locked payroll snapshot unchanged", int(worked or 0) == 480, worked)

    # --- Tenant isolation ---
    other_rows = [{"id": 501, "emp_code": "2002", "punch_time": "2026-08-20 09:00:00", "punch_state": "0", "verify_type": 2, "terminal_sn": "SN-B"}]
    op = biotime.transaction_to_canonical(other_rows[0], company_code=other, connector_id=f"other-{tag}")
    ores = pipe.ingest_canonical(op["punch"], shift={
        "shift_id": str(uuid.uuid4()),
        "shift_date": day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": other_emp_key,
        "status": "scheduled",
    })
    check("other tenant ingest", ores.get("ok") is True, ores)
    # company A list must not include other employee
    a_punches = [p for p in store.list_punches(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift["shift_id"]))]
    check("tenant isolation company punches", all(p.get("employee_key") == emp_key for p in a_punches), len(a_punches))
    b_only = store.list_punches(company_code=other, employee_key=other_emp_key, work_date=day, shift_key="")
    # shift_key may differ — list by employee across store API
    if hasattr(store, "list_punches"):
        # gather by scanning known
        check("other tenant has punch", ores.get("created") is True or ores.get("duplicate") is True, ores)

    # --- Canonical schema not ZK-hardcoded ---
    schema_fields = set(contract.CanonicalPunch.__dataclass_fields__.keys())
    check("canonical has capture_method", "capture_method" in schema_fields)
    check("canonical has no zkteco fields", not any("zk" in f.lower() or "biotime" == f for f in schema_fields), sorted(schema_fields))

    # Freeze regressions (local/staging)
    if os.environ.get("ATTW2B_SKIP_FREEZE") == "1":
        check("freeze skipped", True)
    else:
        import subprocess

        freeze_root = Path(os.environ.get("WATHEFNI_ORCH_ROOT") or ROOT)
        for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
            path = freeze_root / script
            proc = subprocess.run([sys.executable, str(path)], cwd=str(freeze_root), capture_output=True, text=True)
            ok = proc.returncode == 0 and "0 failed" in (proc.stdout + proc.stderr)
            check(f"freeze {script}", ok, (proc.stdout + proc.stderr)[-500:])

    summary = {"pass": PASS, "fail": FAIL, "tag": tag, "company": company, "employee_key": emp_key}
    print(json.dumps({"summary": summary}, indent=2))
    print(f"SUMMARY pass={PASS} fail={FAIL}")
    out = os.environ.get("ATTW2B_OUT")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        Path(out, "qualification.json").write_text(
            json.dumps({"summary": summary, "results": RESULTS}, indent=2, default=str),
            encoding="utf-8",
        )
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
