"""Attendance Import V1 — end-to-end contract harness.

Two layers:
  A. Pure pipeline (attendance_import.py, no DB): parsing, file-safety limits,
     biometric column dropping, strict device-id matching, dedupe, shift-aware
     derivation incl. a cross-midnight overnight shift, and state-hash conflict
     detection.
  B. DB-backed (app.py commit/reverse helpers, throwaway companies): commit
     writes attendance records + tagged events, clean reverse, conflict-safe
     reverse (no clobber of post-import edits), locked-period guard, updated-row
     prior-state restore, and strict company scoping.

Run with the orchestrator venv + staging/prod postgres env, e.g.:
  WATHEFNI_POSTGRES_ENV=... /opt/wathefni/orchestrator/.venv/bin/python smoke-test-attendance-import.py
"""

from __future__ import annotations

import io
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

import attendance_import as ai
import app

TEST_CO = "ATTIMPORTSMOKE"
OTHER_CO = "ATTIMPORTOTHER"
KWT = timezone(timedelta(hours=3))  # Asia/Kuwait, matches default company tz


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


# ---------------------------------------------------------------------------
# Part A — pure pipeline
# ---------------------------------------------------------------------------

def _csv(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def part_a(checks: Checks) -> None:
    # File safety.
    checks.check("A1 rejects non-CSV/XLSX extension", lambda: ai.parse_tabular(b"x", "punches.txt")[3] is not None)
    checks.check("A2 rejects oversized file", lambda: ai.parse_tabular(b"x" * (ai.MAX_BYTES + 1), "big.csv")[3] is not None)

    def too_many_rows() -> bool:
        body = ["id,timestamp"] + [f"{i},2026-01-01 09:0{i % 10}:00" for i in range(ai.MAX_ROWS + 5)]
        return ai.parse_tabular(_csv(body), "many.csv")[3] is not None
    checks.check("A3 rejects too-many-rows file", too_many_rows)

    # Biometric columns dropped, never returned.
    raw = _csv(["id,timestamp,Fingerprint,FaceTemplate", "1001,2026-01-01 09:00:00,AABBCC,ZZZZ"])
    rows, headers, dropped, err = ai.parse_tabular(raw, "bio.csv")
    checks.check("A4 parse ok", lambda: err is None and len(rows) == 1)
    checks.check("A5 biometric headers detected", lambda: "Fingerprint" in dropped and "FaceTemplate" in dropped)
    checks.check("A6 biometric values not in parsed row", lambda: "Fingerprint" not in rows[0] and "FaceTemplate" not in rows[0])

    # CSV == XLSX parity.
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "timestamp", "type"])
    ws.append([1001, "2026-01-01 09:00:00", "IN"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_rows, _, _, xerr = ai.parse_tabular(buf.getvalue(), "p.xlsx")
    checks.check("A7 xlsx parses", lambda: xerr is None and len(xlsx_rows) == 1 and xlsx_rows[0].get("id") == "1001")

    # Mapping suggestion + usability.
    mp = ai.suggest_mapping(["User ID", "Date/Time", "In/Out", "Fingerprint"])
    checks.check("A8 suggests external_id + timestamp + direction", lambda: mp.get("external_id") == "User ID" and mp.get("timestamp") == "Date/Time" and mp.get("direction") == "In/Out")
    checks.check("A9 mapping_is_usable needs id+time", lambda: ai.mapping_is_usable({"external_id": "x"})[0] is False and ai.mapping_is_usable({"external_id": "x", "timestamp": "t"})[0] is True)

    # Coerce + direction.
    mapping = {"external_id": "id", "timestamp": "ts", "direction": "dir"}
    p = ai.coerce_punch({"id": "1001", "ts": "2026-01-01 09:00:00", "dir": "IN"}, mapping, KWT, 1)
    checks.check("A10 coerce sets aware dt + direction in", lambda: p["dt"].tzinfo is not None and p["direction"] == "in")
    bad = ai.coerce_punch({"id": "1001", "ts": "not-a-date", "dir": "OUT"}, mapping, KWT, 2)
    checks.check("A11 bad datetime flagged", lambda: "bad_datetime" in bad["issues"])

    # Strict matching: device id only, no name/phone.
    punches = [
        ai.coerce_punch({"id": "1001", "ts": "2026-01-01 09:00:00"}, {"external_id": "id", "timestamp": "ts"}, KWT, 1),
        ai.coerce_punch({"id": "9999", "ts": "2026-01-01 09:00:00"}, {"external_id": "id", "timestamp": "ts"}, KWT, 2),
    ]
    ai.match_punches(punches, {"1001": "emp-a"})
    checks.check("A12 matches by device id", lambda: punches[0]["employee_key"] == "emp-a")
    checks.check("A13 unknown id is unmatched (no name/phone fallback)", lambda: punches[1]["employee_key"] is None and "unmatched_employee" in punches[1]["issues"])

    # Dedupe within window.
    dup = [
        ai.coerce_punch({"id": "1001", "ts": "2026-01-01 09:00:00", "dir": "IN"}, mapping, KWT, 1),
        ai.coerce_punch({"id": "1001", "ts": "2026-01-01 09:00:30", "dir": "IN"}, mapping, KWT, 2),
    ]
    ai.match_punches(dup, {"1001": "emp-a"})
    ai.mark_duplicates(dup)
    checks.check("A14 near-duplicate punch flagged", lambda: "duplicate_punch" in dup[1]["issues"])

    # Derivation — normal day, one record with in + out.
    day = date(2026, 1, 5)
    shifts = {"emp-a": [{"shift_id": "s1", "shift_date": day, "start_time": time(9, 0), "end_time": time(17, 0)}]}
    norm = [
        ai.coerce_punch({"id": "1001", "ts": "2026-01-05 09:02:00", "dir": "IN"}, mapping, KWT, 1),
        ai.coerce_punch({"id": "1001", "ts": "2026-01-05 17:10:00", "dir": "OUT"}, mapping, KWT, 2),
    ]
    ai.match_punches(norm, {"1001": "emp-a"})
    ai.mark_duplicates(norm)
    recs = ai.derive_records(norm, shifts, KWT)
    checks.check("A15 normal day -> single record", lambda: len(recs) == 1)
    checks.check("A16 record has check_in and check_out", lambda: recs[0]["check_in_at"] is not None and recs[0]["check_out_at"] is not None and recs[0]["attendance_date"] == day)

    # Derivation — CROSS-MIDNIGHT overnight shift (22:00 -> 06:00 next day).
    ov_shifts = {"emp-n": [{"shift_id": "sN", "shift_date": day, "start_time": time(22, 0), "end_time": time(6, 0)}]}
    ov = [
        ai.coerce_punch({"id": "2002", "ts": "2026-01-05 23:30:00", "dir": "IN"}, mapping, KWT, 1),
        ai.coerce_punch({"id": "2002", "ts": "2026-01-06 06:20:00", "dir": "OUT"}, mapping, KWT, 2),
    ]
    ai.match_punches(ov, {"2002": "emp-n"})
    ai.mark_duplicates(ov)
    ov_recs = ai.derive_records(ov, ov_shifts, KWT)
    checks.check("A17 overnight punches collapse to ONE record", lambda: len(ov_recs) == 1)
    checks.check("A18 overnight record attributed to shift_date (start day)", lambda: ov_recs[0]["attendance_date"] == day and ov_recs[0]["shift_id"] == "sN")
    checks.check("A19 overnight record spans both calendar days", lambda: ov_recs[0]["check_in_at"].day == 5 and ov_recs[0]["check_out_at"].day == 6)

    # missing checkout flagged.
    mc = [ai.coerce_punch({"id": "1001", "ts": "2026-01-05 09:02:00", "dir": "IN"}, mapping, KWT, 1)]
    ai.match_punches(mc, {"1001": "emp-a"})
    mc_recs = ai.derive_records(mc, shifts, KWT)
    checks.check("A20 missing checkout flagged", lambda: "missing_checkout" in mc_recs[0]["issues"])

    # state_hash stability + sensitivity.
    base = {"check_in_at": norm[0]["dt"], "check_out_at": norm[1]["dt"], "status": "present", "late_minutes": 0, "early_leave_minutes": 0}
    changed = dict(base, check_out_at=norm[1]["dt"] + timedelta(minutes=30))
    checks.check("A21 state_hash stable", lambda: ai.state_hash(base) == ai.state_hash(dict(base)))
    checks.check("A22 state_hash changes when record changes", lambda: ai.state_hash(base) != ai.state_hash(changed))


# ---------------------------------------------------------------------------
# Part B — DB-backed commit/reverse
# ---------------------------------------------------------------------------

def _purge() -> None:
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for co in (TEST_CO, OTHER_CO):
                    cur.execute("DELETE FROM attendance_events WHERE company_code=%s", (co,))
                    cur.execute("DELETE FROM attendance_import_batch_rows WHERE company_code=%s", (co,))
                    cur.execute("DELETE FROM attendance_import_batches WHERE company_code=%s", (co,))
                    cur.execute("DELETE FROM attendance_records WHERE company_code=%s", (co,))
                    cur.execute("DELETE FROM payroll_timesheets WHERE company_code=%s", (co,))
                    cur.execute("DELETE FROM shift_assignments WHERE company_code=%s", (co,))
                    cur.execute("DELETE FROM employees WHERE company_code=%s", (co,))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN purge: {exc}")


def _emp(company: str, key: str, name: str, device_id: str | None) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO employees (employee_key, company_code, name, phone, device_user_id, updated_at) VALUES (%s,%s,%s,%s,%s,now()) ON CONFLICT (employee_key) DO UPDATE SET device_user_id=EXCLUDED.device_user_id",
                (key, company, name, app.digits("9650000" + key[-4:].rjust(4, "0")), device_id),
            )
        conn.commit()


def _shift(company: str, key: str, d: date, start: time, end: time) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO shift_assignments (company_code, employee_key, shift_date, start_time, end_time) VALUES (%s,%s,%s,%s,%s) RETURNING shift_id",
                (company, key, d, start, end),
            )
            sid = str(cur.fetchone()["shift_id"])
        conn.commit()
    return sid


def _records(company: str, key: str) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM attendance_records WHERE company_code=%s AND employee_key=%s ORDER BY attendance_date", (company, key))
            return [dict(r) for r in cur.fetchall()]


def part_b(checks: Checks) -> None:
    d = date(2026, 2, 10)
    mapping = {"external_id": "id", "timestamp": "ts", "direction": "dir"}

    # Employees + shifts.
    _emp(TEST_CO, "ai-normal", "Normal Worker", "1001")
    _emp(TEST_CO, "ai-night", "Night Worker", "2002")
    _emp(TEST_CO, "ai-locked", "Locked Worker", "3003")
    _emp(TEST_CO, "ai-update", "Update Worker", "4004")
    _emp(TEST_CO, "ai-conflict", "Conflict Worker", "5005")
    _emp(OTHER_CO, "ai-other", "Other Co Worker", "1001")  # same device id, different company
    _emp(TEST_CO, "ai-nodev", "No Device Worker", None)

    _shift(TEST_CO, "ai-normal", d, time(9, 0), time(17, 0))
    s_night = _shift(TEST_CO, "ai-night", d, time(22, 0), time(6, 0))
    s_locked = _shift(TEST_CO, "ai-locked", d, time(9, 0), time(17, 0))
    s_update = _shift(TEST_CO, "ai-update", d, time(9, 0), time(17, 0))
    _shift(TEST_CO, "ai-conflict", d, time(9, 0), time(17, 0))

    # Lock ai-locked's period via an approved timesheet.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO payroll_timesheets (company_code, employee_key, period_start, period_end, status) VALUES (%s,%s,%s,%s,'approved')",
                (TEST_CO, "ai-locked", d - timedelta(days=5), d + timedelta(days=5)),
            )
        conn.commit()

    # Pre-existing MANUAL record for ai-update (no checkout) so import UPDATES it.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO attendance_records (company_code, employee_key, shift_id, attendance_date, check_in_at, status, source_text) VALUES (%s,%s,%s,%s,%s,'present','manual')",
                (TEST_CO, "ai-update", s_update, d, datetime(2026, 2, 10, 8, 0, tzinfo=KWT)),
            )
        conn.commit()

    # Build one CSV covering all employees (incl. overnight + a missing checkout via locked).
    body = [
        "id,ts,dir",
        f"1001,{d} 09:03:00,IN",
        f"1001,{d} 17:05:00,OUT",
        f"2002,{d} 23:30:00,IN",                       # overnight in
        f"2002,{d + timedelta(days=1)} 06:20:00,OUT",  # overnight out (next day)
        f"3003,{d} 09:00:00,IN",                       # locked period -> skipped
        f"3003,{d} 17:00:00,OUT",
        f"4004,{d} 17:30:00,OUT",                      # updates manual record (adds checkout)
        f"5005,{d} 09:10:00,IN",
        f"5005,{d} 17:10:00,OUT",
        f"7777,{d} 09:00:00,IN",                       # unknown device -> unmatched
    ]
    raw = _csv(body)

    out = app.attendance_import_run_commit(TEST_CO, raw, "device.csv", mapping, "ZK main", "96599999999")
    batch_id = out["batch_id"]

    # B1 normal day record created from import, tagged source.
    nr = _records(TEST_CO, "ai-normal")
    checks.check("B1 normal record created from import", lambda: len(nr) == 1 and nr[0]["check_in_at"] is not None and nr[0]["check_out_at"] is not None)
    checks.check("B2 record metadata flags fingerprint_import", lambda: (nr[0]["metadata"] or {}).get("source") == "fingerprint_import" and (nr[0]["metadata"] or {}).get("import_batch_id") == batch_id)

    # B3 tagged punch events exist for the batch.
    def events_tagged() -> bool:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS c FROM attendance_events WHERE company_code=%s AND import_batch_id=%s", (TEST_CO, batch_id))
                return int(cur.fetchone()["c"]) >= 2
    checks.check("B3 punch events tagged with import_batch_id", events_tagged)

    # B4 overnight -> single record on shift_date spanning both days.
    ov = _records(TEST_CO, "ai-night")
    checks.check("B4 overnight single record on shift_date", lambda: len(ov) == 1 and ov[0]["attendance_date"] == d and str(ov[0]["shift_id"]) == s_night)
    checks.check("B5 overnight record spans midnight", lambda: ov[0]["check_in_at"].astimezone(KWT).day == 10 and ov[0]["check_out_at"].astimezone(KWT).day == 11)

    # B6 locked period skipped (no record written).
    checks.check("B6 locked-period employee skipped (no record)", lambda: _records(TEST_CO, "ai-locked") == [])
    checks.check("B7 commit counts report skipped_locked", lambda: out["counts"].get("skipped_locked", 0) >= 1)

    # B8 unmatched + company scoping: other company untouched.
    checks.check("B8 unmatched id counted", lambda: out["counts"].get("unmatched", 0) >= 1)
    checks.check("B9 same device id in OTHER company not affected", lambda: _records(OTHER_CO, "ai-other") == [])

    # B10 updated record: manual record gained a checkout.
    upd = _records(TEST_CO, "ai-update")
    checks.check("B10 manual record updated with checkout", lambda: len(upd) == 1 and upd[0]["check_out_at"] is not None)

    # --- Conflict-safe reverse: edit ai-conflict's record AFTER import ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE attendance_records SET check_out_at=%s WHERE company_code=%s AND employee_key=%s",
                (datetime(2026, 2, 10, 19, 0, tzinfo=KWT), TEST_CO, "ai-conflict"),
            )
        conn.commit()

    rev = app.attendance_import_run_reverse(TEST_CO, batch_id, "96599999999")

    # B11 clean created record removed by reverse.
    checks.check("B11 reverse deleted clean created record", lambda: _records(TEST_CO, "ai-normal") == [])

    # B12 reverse removed events for all NON-conflict records; conflict record's
    # events are intentionally preserved (it was edited after import).
    def batch_events_by_emp() -> dict[str, int]:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employee_key, count(*) AS c FROM attendance_events WHERE import_batch_id=%s GROUP BY employee_key", (batch_id,))
                return {str(r["employee_key"]): int(r["c"]) for r in cur.fetchall()}
    checks.check("B12 reverse removed events for non-conflict records only", lambda: all(emp == "ai-conflict" for emp in batch_events_by_emp()))

    # B13 conflict NOT clobbered (edited record survives, counted as conflict).
    conf = _records(TEST_CO, "ai-conflict")
    checks.check("B13 conflict record preserved (not deleted)", lambda: len(conf) == 1 and conf[0]["check_out_at"].astimezone(KWT).hour == 19)
    checks.check("B14 reverse reports >=1 conflict", lambda: rev["conflicts"] >= 1)

    # B15 updated record restored to prior manual state (checkout cleared).
    upd2 = _records(TEST_CO, "ai-update")
    checks.check("B15 updated record restored to prior (no checkout)", lambda: len(upd2) == 1 and upd2[0]["check_out_at"] is None and upd2[0]["check_in_at"] is not None)

    # B16 batch marked reversed; second reverse rejected.
    def already_reversed() -> bool:
        try:
            app.attendance_import_run_reverse(TEST_CO, batch_id, "x")
            return False
        except app.HTTPException as exc:
            return exc.status_code == 409
    checks.check("B16 double-reverse rejected (409)", already_reversed)

    # B17 flag gating: guard returns 404 when flag OFF, passes RBAC layer when ON.
    import os

    prev = os.environ.get("WATHEFNI_ATTENDANCE_IMPORT")
    os.environ.pop("WATHEFNI_ATTENDANCE_IMPORT", None)

    def flag_off_404() -> bool:
        try:
            app._attendance_import_guard({"company_code": TEST_CO, "actor_role": "owner", "actor_user_id": "x"}, write=True)
            return False
        except app.HTTPException as exc:
            return exc.status_code == 404
    checks.check("B17 endpoints hidden (404) when flag OFF", flag_off_404)
    if prev is not None:
        os.environ["WATHEFNI_ATTENDANCE_IMPORT"] = prev


def main() -> None:
    print("attendance import V1 — pure pipeline + DB commit/reverse")
    checks = Checks()
    part_a(checks)
    _purge()
    try:
        part_b(checks)
    finally:
        _purge()
    code = checks.report()
    print("\nATTENDANCE IMPORT HARNESS: " + ("FAILURES PRESENT (see punch-list above)" if code else "ALL CHECKS PASSED"))
    sys.exit(code)


if __name__ == "__main__":
    main()
