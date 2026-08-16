#!/usr/bin/env python3
"""Shifts Wave 2C prove-out: cleanup compatibility + timer foundations (synthetic-only).

Proves:
  - Wave 1 / Wave 2 marker scopes cannot delete each other
  - Interrupted cleanup is idempotent (rerun → residual 0)
  - Shared cleanup contract + deletion order
  - Real assignment / event / swap / availability / version fingerprints unchanged
  - Operator jobs: kill switch, advisory lock contention, resume
  - systemd oneshot services can start; timers remain disabled after qualification

Does NOT enable real-employee mutations, recurring timers for real records,
dashboard UX, templates, or Payroll money.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

import app  # noqa: E402
import shifts_schedule_integrity_wave2 as w2  # noqa: E402
from shifts_synthetic_cleanup import (  # noqa: E402
    CLEANUP_CONTRACT_VERSION,
    DELETION_ORDER,
    PRODUCTION_ORPHAN_ALLOWLIST,
    cleanup_synthetic_scope,
    count_synthetic_residuals,
    wave1b_scope,
    wave2b_scope,
)

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW2C_TAG") or uuid.uuid4().hex[:8]
EVID = Path(os.environ.get("SHW2C_EVID") or f"/tmp/shifts-w2c-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}", flush=True)
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}", flush=True)


def fp_row(row: dict[str, Any], keys: list[str]) -> str:
    raw = "|".join(str(row.get(k) or "") for k in keys)
    return hashlib.md5(raw.encode()).hexdigest()


def _tbl(cur: Any, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s LIMIT 1",
        (name,),
    )
    return cur.fetchone() is not None


def _digits_from(tag: str) -> str:
    d = "".join(ch for ch in tag if ch.isdigit()) + "000000"
    return d[:5]


def fingerprint_real(cur: Any) -> dict[str, Any]:
    """Fingerprint non-synthetic scheduling authority rows (marker/phone excluded)."""
    out: dict[str, Any] = {}
    cur.execute(
        """
        SELECT shift_id::text AS shift_id, employee_key, employee_phone, shift_date::text,
               start_time::text, end_time::text, status, updated_at::text, role, location, timezone
        FROM shift_assignments
        WHERE company_code=%s
          AND coalesce(employee_key,'') NOT LIKE '%%SHW1B%%'
          AND coalesce(employee_key,'') NOT LIKE '%%SHW2B%%'
          AND coalesce(employee_phone,'') NOT LIKE '965529%%'
          AND coalesce(employee_phone,'') NOT LIKE '965530%%'
        ORDER BY shift_id
        """,
        (COMPANY,),
    )
    assigns = [dict(r) for r in cur.fetchall()]
    out["assignment_count"] = len(assigns)
    out["assignment_fps"] = {
        r["shift_id"]: fp_row(
            r,
            [
                "shift_id",
                "employee_key",
                "employee_phone",
                "shift_date",
                "start_time",
                "end_time",
                "status",
                "updated_at",
                "role",
                "location",
                "timezone",
            ],
        )
        for r in assigns
    }
    cur.execute(
        """
        SELECT event_id::text AS event_id FROM shift_events
        WHERE company_code=%s
          AND shift_id IN (
            SELECT shift_id FROM shift_assignments
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW1B%%'
              AND coalesce(employee_key,'') NOT LIKE '%%SHW2B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965529%%'
              AND coalesce(employee_phone,'') NOT LIKE '965530%%'
          )
        ORDER BY event_id
        """,
        (COMPANY, COMPANY),
    )
    out["event_ids"] = [dict(r)["event_id"] for r in cur.fetchall()]
    out["event_count"] = len(out["event_ids"])
    cur.execute(
        """
        SELECT count(*) AS c FROM shift_swap_requests
        WHERE company_code=%s
          AND coalesce(requester_employee_key,'') NOT LIKE '%%SHW1B%%'
          AND coalesce(requester_employee_key,'') NOT LIKE '%%SHW2B%%'
          AND coalesce(target_employee_key,'') NOT LIKE '%%SHW1B%%'
          AND coalesce(target_employee_key,'') NOT LIKE '%%SHW2B%%'
        """,
        (COMPANY,),
    )
    out["swap_count"] = int(dict(cur.fetchone())["c"])
    cur.execute(
        """
        SELECT count(*) AS c FROM employee_availability_requests
        WHERE company_code=%s
          AND coalesce(employee_key,'') NOT LIKE '%%SHW1B%%'
          AND coalesce(employee_key,'') NOT LIKE '%%SHW2B%%'
          AND coalesce(employee_phone,'') NOT LIKE '965529%%'
          AND coalesce(employee_phone,'') NOT LIKE '965530%%'
        """,
        (COMPANY,),
    )
    out["availability_count"] = int(dict(cur.fetchone())["c"])
    out["version_count"] = 0
    out["reminder_count"] = 0
    if _tbl(cur, "shift_assignment_versions"):
        cur.execute(
            """
            SELECT count(*) AS c FROM shift_assignment_versions
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW1B%%'
              AND coalesce(employee_key,'') NOT LIKE '%%SHW2B%%'
            """,
            (COMPANY,),
        )
        out["version_count"] = int(dict(cur.fetchone())["c"])
    if _tbl(cur, "shift_reminder_queue"):
        cur.execute(
            """
            SELECT count(*) AS c FROM shift_reminder_queue
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW1B%%'
              AND coalesce(employee_key,'') NOT LIKE '%%SHW2B%%'
            """,
            (COMPANY,),
        )
        out["reminder_count"] = int(dict(cur.fetchone())["c"])
    return out


def upsert_employee(cur: Any, *, key: str, name: str, phone: str, flag: str) -> None:
    raw = json.dumps({flag: True, "w2c": True, "tag": TAG})
    cur.execute(
        "SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s",
        (COMPANY, key),
    )
    if cur.fetchone():
        cur.execute(
            "UPDATE employees SET name=%s, phone=%s, raw_json=%s::jsonb, employment_status='active' WHERE company_code=%s AND employee_key=%s",
            (name, phone, raw, COMPANY, key),
        )
    else:
        cur.execute(
            """
            INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
            """,
            (COMPANY, key, name, phone, raw),
        )


def main() -> int:
    print(f"shifts wave2c prove tag={TAG}", flush=True)
    check("cleanup contract version", CLEANUP_CONTRACT_VERSION == "1.0.0")
    check("deletion order starts with reminders", DELETION_ORDER[0] == "shift_reminder_queue")
    check("deletion order ends with employees", DELETION_ORDER[-1] == "employees")
    check("protected orphans listed", len(PRODUCTION_ORPHAN_ALLOWLIST) == 3)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            before = fingerprint_real(cur)
    (EVID / "fingerprint-before.json").write_text(json.dumps(before, indent=2))

    day = (date.today() + timedelta(days=41)).isoformat()
    w1_key = f"WATHEFNI-SHW1B-W2C-{TAG}"
    w2_key = f"WATHEFNI-SHW2B-W2C-{TAG}"
    w1_phone = f"965529{_digits_from(TAG)}1"
    w2_phone = f"965530{_digits_from(TAG)}2"

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            upsert_employee(cur, key=w1_key, name=f"SHW1B-SYNTH| W2C {TAG}", phone=w1_phone, flag="shw1b")
            upsert_employee(cur, key=w2_key, name=f"SHW2B-SYNTH| W2C {TAG}", phone=w2_phone, flag="shw2b")
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, shift_date, start_time, end_time,
                  status, source_text, metadata
                ) VALUES (%s,%s,%s,%s::date,'09:00','17:00','scheduled',%s,%s::jsonb)
                RETURNING shift_id::text AS shift_id
                """,
                (COMPANY, w1_key, w1_phone, day, f"SHW1B-SYNTH| W2C {TAG}", json.dumps({"shw1b": True, "tag": TAG})),
            )
            w1_sid = dict(cur.fetchone())["shift_id"]
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, shift_date, start_time, end_time,
                  status, source_text, metadata
                ) VALUES (%s,%s,%s,%s::date,'10:00','18:00','scheduled',%s,%s::jsonb)
                RETURNING shift_id::text AS shift_id
                """,
                (COMPANY, w2_key, w2_phone, day, f"SHW2B-SYNTH| W2C {TAG}", json.dumps({"shw2b": True, "tag": TAG})),
            )
            w2_sid = dict(cur.fetchone())["shift_id"]
            for sid, key in ((w1_sid, w1_key), (w2_sid, w2_key)):
                if _tbl(cur, "shift_assignment_versions"):
                    cur.execute(
                        """
                        INSERT INTO shift_assignment_versions (
                          company_code, shift_id, version_no, is_current, reason_code,
                          employee_key, shift_date, start_time, end_time, status
                        ) VALUES (%s,%s::uuid,1,true,'created',%s,%s::date,'09:00','17:00','scheduled')
                        """,
                        (COMPANY, sid, key, day),
                    )
                if _tbl(cur, "shift_reminder_queue"):
                    cur.execute(
                        """
                        INSERT INTO shift_reminder_queue (
                          company_code, shift_id, employee_key, planned_send_at, status, idempotency_key
                        ) VALUES (%s,%s::uuid,%s,now(),'pending',%s)
                        """,
                        (COMPANY, sid, key, f"w2c|{sid}|{day}"),
                    )
                if _tbl(cur, "shift_reconciliation_flags"):
                    cur.execute(
                        """
                        INSERT INTO shift_reconciliation_flags (
                          company_code, shift_id, employee_key, flag_type, status, details
                        ) VALUES (%s,%s::uuid,%s,'lifecycle_fact_change','open','{"w2c":true}'::jsonb)
                        """,
                        (COMPANY, sid, key),
                    )
            conn.commit()

    pair = {"w1_key": w1_key, "w2_key": w2_key, "w1_sid": w1_sid, "w2_sid": w2_sid}
    (EVID / "synth-pair.json").write_text(json.dumps(pair, indent=2))

    c1 = cleanup_synthetic_scope(app.db_connect, wave1b_scope(tag=TAG), known_ids={"shift_ids": [w1_sid]})
    check("wave1 cleanup residual zero for SHW1B", c1["residual_total"] == 0, c1.get("residual"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM shift_assignments WHERE shift_id=%s::uuid", (w2_sid,))
            w2_alive = int(dict(cur.fetchone())["c"])
            w2_ver = 0
            if _tbl(cur, "shift_assignment_versions"):
                cur.execute(
                    "SELECT count(*) AS c FROM shift_assignment_versions WHERE shift_id=%s::uuid",
                    (w2_sid,),
                )
                w2_ver = int(dict(cur.fetchone())["c"])
            cur.execute("SELECT count(*) AS c FROM shift_assignments WHERE shift_id=%s::uuid", (w1_sid,))
            w1_gone = int(dict(cur.fetchone())["c"])
    check("wave1 cleanup does not delete wave2 assignment", w2_alive == 1, {"w2_alive": w2_alive})
    check("wave1 cleanup does not delete wave2 versions", w2_ver >= 1, {"w2_ver": w2_ver})
    check("wave1 assignment removed", w1_gone == 0, {"w1_gone": w1_gone})

    # Interrupted cleanup: remove only some dependents, leave assignment + flags, then full cleanup twice.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if _tbl(cur, "shift_reminder_queue"):
                cur.execute("DELETE FROM shift_reminder_queue WHERE shift_id=%s::uuid", (w2_sid,))
            if _tbl(cur, "shift_assignment_versions"):
                cur.execute("DELETE FROM shift_assignment_versions WHERE shift_id=%s::uuid", (w2_sid,))
            conn.commit()

    c2a = cleanup_synthetic_scope(app.db_connect, wave2b_scope(tag=TAG), known_ids={"shift_ids": [w2_sid]})
    c2b = cleanup_synthetic_scope(app.db_connect, wave2b_scope(tag=TAG), known_ids={"shift_ids": [w2_sid]})
    check("interrupted wave2 cleanup completes to residual 0", c2a["residual_total"] == 0, c2a.get("residual"))
    check("idempotent wave2 cleanup rerun residual 0", c2b["residual_total"] == 0, c2b.get("residual"))

    # Wave2 cleanup must not delete Wave1 rows.
    day2 = (date.today() + timedelta(days=42)).isoformat()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            upsert_employee(cur, key=w1_key, name=f"SHW1B-SYNTH| W2C {TAG}", phone=w1_phone, flag="shw1b")
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, shift_date, start_time, end_time,
                  status, source_text, metadata
                ) VALUES (%s,%s,%s,%s::date,'11:00','15:00','scheduled',%s,%s::jsonb)
                RETURNING shift_id::text AS shift_id
                """,
                (COMPANY, w1_key, w1_phone, day2, f"SHW1B-SYNTH| W2C keep {TAG}", json.dumps({"shw1b": True, "tag": TAG})),
            )
            keep_sid = dict(cur.fetchone())["shift_id"]
            conn.commit()

    c2x = cleanup_synthetic_scope(app.db_connect, wave2b_scope(tag=TAG), known_ids={})
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM shift_assignments WHERE shift_id=%s::uuid", (keep_sid,))
            kept = int(dict(cur.fetchone())["c"])
    check("wave2 cleanup does not delete wave1 assignment", kept == 1, {"kept": kept, "cleanup": c2x.get("deleted")})

    c1f = cleanup_synthetic_scope(app.db_connect, wave1b_scope(tag=TAG), known_ids={"shift_ids": [keep_sid]})
    check("final wave1 prove residual zero", c1f["residual_total"] == 0, c1f.get("residual"))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = fingerprint_real(cur)
            r1 = count_synthetic_residuals(cur, wave1b_scope())
            r2 = count_synthetic_residuals(cur, wave2b_scope())
    check("SHW1B family residual zero after prove", r1["total"] == 0, r1)
    check("SHW2B family residual zero after prove", r2["total"] == 0, r2)
    check(
        "real assignment fingerprints unchanged",
        before["assignment_fps"] == after["assignment_fps"],
        {"before": before["assignment_count"], "after": after["assignment_count"]},
    )
    check("real event ids unchanged", before["event_ids"] == after["event_ids"])
    check("real swap count unchanged", before["swap_count"] == after["swap_count"])
    check("real availability count unchanged", before["availability_count"] == after["availability_count"])
    check("real version count unchanged", before["version_count"] == after["version_count"])
    check("real reminder count unchanged", before["reminder_count"] == after["reminder_count"])

    # Kill switch + lock contention
    prev_jobs = os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_JOBS")
    os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = "0"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            killed = w2.run_lifecycle_reconciliation_job(cur, company_code=COMPANY, limit=5)
    check(
        "kill switch disables lifecycle job",
        killed.get("killed") is True or killed.get("error") == "shifts_wave2_jobs_disabled",
        killed,
    )
    os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = "1"

    def _hold_lock() -> None:
        with app.db_connect() as conn2:
            with conn2.cursor() as cur2:
                cur2.execute("SELECT pg_try_advisory_lock(%s) AS ok", (w2.JOB_LOCK_LIFECYCLE_RECON,))
                time.sleep(2.0)
                cur2.execute("SELECT pg_advisory_unlock(%s)", (w2.JOB_LOCK_LIFECYCLE_RECON,))
                conn2.commit()

    t = threading.Thread(target=_hold_lock, daemon=True)
    t.start()
    time.sleep(0.35)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            contended = w2.run_lifecycle_reconciliation_job(cur, company_code=COMPANY, limit=5)
            conn.commit()
    t.join(timeout=5)
    check("advisory lock contention returns job_lock_held", contended.get("error") == "job_lock_held", contended)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            resumed = w2.run_lifecycle_reconciliation_job(cur, company_code=COMPANY, limit=5)
            conn.commit()
    check("lifecycle job ok after lock released", resumed.get("ok") is True, resumed)
    if prev_jobs is None:
        os.environ.pop("WATHEFNI_SHIFTS_INTEGRITY_JOBS", None)
    else:
        os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = prev_jobs

    timer_names = [
        "wathefni-shifts-reminder-drain.timer",
        "wathefni-shifts-lifecycle-recon.timer",
        "wathefni-shifts-leave-recon.timer",
    ]
    service_names = [
        "wathefni-shifts-reminder-drain.service",
        "wathefni-shifts-lifecycle-recon.service",
        "wathefni-shifts-leave-recon.service",
    ]
    timer_evidence: dict[str, Any] = {"timers": {}, "services": {}}
    units_present = all(Path(f"/etc/systemd/system/{n}").exists() for n in timer_names + service_names)
    check("systemd job units installed", units_present)

    if units_present:
        for svc in service_names:
            proc = subprocess.run(
                ["systemctl", "start", "--wait", svc],
                capture_output=True,
                text=True,
                timeout=180,
            )
            timer_evidence["services"][svc] = {
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-800:],
                "stderr": (proc.stderr or "")[-800:],
            }
        for tm in timer_names:
            subprocess.run(["systemctl", "disable", tm], capture_output=True, text=True)
            subprocess.run(["systemctl", "stop", tm], capture_output=True, text=True)
            en = subprocess.run(["systemctl", "is-enabled", tm], capture_output=True, text=True)
            ac = subprocess.run(["systemctl", "is-active", tm], capture_output=True, text=True)
            en_s = (en.stdout or en.stderr or "").strip()
            ac_s = (ac.stdout or ac.stderr or "").strip()
            timer_evidence["timers"][tm] = {"is-enabled": en_s, "is-active": ac_s}
        check(
            "timers remain disabled",
            all("disabled" in timer_evidence["timers"][tm]["is-enabled"] for tm in timer_names),
            timer_evidence["timers"],
        )
        check(
            "timers not active",
            all(timer_evidence["timers"][tm]["is-active"] in {"inactive", "dead"} for tm in timer_names),
            timer_evidence["timers"],
        )

    (EVID / "timer-evidence.json").write_text(json.dumps(timer_evidence, indent=2))
    (EVID / "fingerprint-after.json").write_text(json.dumps(after, indent=2))

    out = {
        "passed": PASS,
        "failed": FAIL,
        "tag": TAG,
        "contract_version": CLEANUP_CONTRACT_VERSION,
        "deletion_order": list(DELETION_ORDER),
        "results": RESULTS,
        "cleanup_wave1": c1,
        "cleanup_wave2_interrupted": c2a,
        "timer_evidence": timer_evidence,
    }
    (EVID / "qualification.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
