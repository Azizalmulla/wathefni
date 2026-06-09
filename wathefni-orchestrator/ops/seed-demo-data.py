"""Reversible demo-data seed for the Wathefni dashboard (demo-readiness).

Fills the modules that are otherwise empty in a fresh company so a live demo
shows real data across Employee 360, attendance, shifts, leave and the ranked
Next Actions engine. Everything it writes is tagged so it can be removed cleanly:

  - attendance_records / shift_assignments / leave_requests rows carry
    metadata->>'demo_seed' = 'wathefni_v1'
  - compliance_documents are UPDATED in place (not inserted), with the original
    expiry_date/status stashed under raw_json->'_demo_backup' so `clean` restores
    them exactly.

Usage (run on the target host with the service env):
  python3 ops/seed-demo-data.py seed   [COMPANY]
  python3 ops/seed-demo-data.py clean  [COMPANY]
  python3 ops/seed-demo-data.py status [COMPANY]

COMPANY defaults to WATHEFNI. Idempotent: `seed` calls `clean` first.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

MARKER = "wathefni_v1"
TZ = "Asia/Kuwait"


def _import_app():
    here = Path(__file__).resolve()
    for cand in (here.parent, here.parent.parent, Path.cwd()):
        if (cand / "app.py").exists():
            sys.path.insert(0, str(cand))
            break
    import app  # noqa: E402

    return app


def _weekdays_back(n: int) -> list[date]:
    """Last n Kuwait working days (Sun–Thu), most recent first then sorted asc."""
    out: list[date] = []
    d = date.today()
    while len(out) < n:
        # Kuwait weekend: Friday(4), Saturday(5) in Python weekday() (Mon=0)
        if d.weekday() not in (4, 5):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _upcoming_weekdays(n: int) -> list[date]:
    out: list[date] = []
    d = date.today() + timedelta(days=1)
    while len(out) < n:
        if d.weekday() not in (4, 5):
            out.append(d)
        d += timedelta(days=1)
    return out


def _employees(app, company: str) -> list[dict]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT employee_key, phone, name FROM employees WHERE company_code=%s AND employee_key<>'' ORDER BY created_at NULLS LAST",
                (company,),
            )
            return [dict(r) for r in cur.fetchall()]


def clean(app, company: str) -> dict:
    now = datetime.now(timezone.utc)
    removed = {"attendance": 0, "shifts": 0, "leave": 0, "compliance_restored": 0}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_records WHERE company_code=%s AND metadata->>'demo_seed'=%s", (company, MARKER))
            removed["attendance"] = cur.rowcount
            cur.execute("DELETE FROM shift_assignments WHERE company_code=%s AND metadata->>'demo_seed'=%s", (company, MARKER))
            removed["shifts"] = cur.rowcount
            cur.execute("DELETE FROM leave_requests WHERE company_code=%s AND metadata->>'demo_seed'=%s", (company, MARKER))
            removed["leave"] = cur.rowcount
            # Restore any compliance rows we tweaked, from their stashed backup.
            cur.execute(
                "SELECT employee_key, document_type, raw_json FROM compliance_documents WHERE company_code=%s AND raw_json ? '_demo_backup'",
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                backup = (r.get("raw_json") or {}).get("_demo_backup") or {}
                raw = dict(r.get("raw_json") or {})
                raw.pop("_demo_backup", None)
                cur.execute(
                    "UPDATE compliance_documents SET expiry_date=%s, status=%s, raw_json=%s::jsonb, updated_at=%s "
                    "WHERE employee_key=%s AND document_type=%s",
                    (
                        backup.get("expiry_date"),
                        backup.get("status") or "missing",
                        json.dumps(raw),
                        now,
                        r["employee_key"],
                        r["document_type"],
                    ),
                )
                removed["compliance_restored"] += 1
            conn.commit()
    return removed


def seed(app, company: str) -> dict:
    clean(app, company)
    emps = _employees(app, company)
    if not emps:
        return {"error": "no employees", "company": company}
    now = datetime.now(timezone.utc)
    meta = json.dumps({"demo_seed": MARKER})
    counts = {"attendance": 0, "shifts": 0, "leave": 0, "compliance_tweaked": 0}
    work_days = _weekdays_back(14)
    up_days = _upcoming_weekdays(5)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for idx, emp in enumerate(emps):
                ek, ph, nm = emp["employee_key"], emp.get("phone"), emp.get("name")
                hero = idx == 0  # first employee gets a richer (late/absent) pattern
                for i, d in enumerate(work_days):
                    status, late, ci, co = "present", 0, time(8, 58), time(17, 3)
                    if hero and i in (2, 9):
                        status, late, ci, co = "absent", 0, None, None
                    elif hero and i in (4, 7, 11):
                        status, late, ci, co = "late", 25, time(9, 25), time(17, 5)
                    cin = datetime.combine(d, ci, tzinfo=timezone.utc) if ci else None
                    cout = datetime.combine(d, co, tzinfo=timezone.utc) if co else None
                    cur.execute(
                        """INSERT INTO attendance_records
                           (attendance_id, company_code, employee_key, employee_phone, employee_name,
                            attendance_date, scheduled_start, scheduled_end, check_in_at, check_out_at,
                            status, late_minutes, early_leave_minutes, metadata, created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                        (str(uuid.uuid4()), company, ek, ph, nm, d, time(9, 0), time(17, 0),
                         cin, cout, status, late, 0, meta, now, now),
                    )
                    counts["attendance"] += 1
                for d in up_days:
                    cur.execute(
                        """INSERT INTO shift_assignments
                           (shift_id, company_code, employee_key, employee_phone, employee_name,
                            shift_date, start_time, end_time, timezone, role, location, status,
                            metadata, created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                        (str(uuid.uuid4()), company, ek, ph, nm, d, time(9, 0), time(17, 0), TZ,
                         "Branch staff", "Main Branch", "scheduled", meta, now, now),
                    )
                    counts["shifts"] += 1

            # Two pending leave requests so the leave module + Next Actions show decisions.
            if len(emps) >= 1:
                e = emps[0]
                cur.execute(
                    """INSERT INTO leave_requests
                       (leave_id, company_code, employee_key, employee_phone, employee_name,
                        start_date, end_date, leave_type, status, reason, requested_at, metadata, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (str(uuid.uuid4()), company, e["employee_key"], e.get("phone"), e.get("name"),
                     date.today() + timedelta(days=7), date.today() + timedelta(days=9), "annual",
                     "requested", "Family trip", now, meta, now, now),
                )
                counts["leave"] += 1
            if len(emps) >= 2:
                e = emps[1]
                cur.execute(
                    """INSERT INTO leave_requests
                       (leave_id, company_code, employee_key, employee_phone, employee_name,
                        start_date, end_date, leave_type, status, reason, requested_at, metadata, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (str(uuid.uuid4()), company, e["employee_key"], e.get("phone"), e.get("name"),
                     date.today() + timedelta(days=3), date.today() + timedelta(days=3), "sick",
                     "requested", "Medical appointment", now, meta, now, now),
                )
                counts["leave"] += 1

            # Hero employee compliance variety (reversible: original stashed in raw_json).
            hero_key = emps[0]["employee_key"]
            tweaks = {
                "civil_id": {"expiry_date": date.today() - timedelta(days=10), "status": "valid"},   # expired -> critical
                "passport": {"expiry_date": date.today() + timedelta(days=15), "status": "valid"},   # expiring soon
                "medical": {"expiry_date": None, "status": "received"},                               # needs review
            }
            for dtype, new in tweaks.items():
                cur.execute(
                    "SELECT expiry_date, status, raw_json FROM compliance_documents WHERE company_code=%s AND employee_key=%s AND document_type=%s",
                    (company, hero_key, dtype),
                )
                row = cur.fetchone()
                if not row:
                    continue
                row = dict(row)
                raw = dict(row.get("raw_json") or {})
                if "_demo_backup" not in raw:
                    ed = row.get("expiry_date")
                    raw["_demo_backup"] = {
                        "expiry_date": ed.isoformat() if hasattr(ed, "isoformat") else ed,
                        "status": row.get("status"),
                    }
                cur.execute(
                    "UPDATE compliance_documents SET expiry_date=%s, status=%s, raw_json=%s::jsonb, updated_at=%s "
                    "WHERE company_code=%s AND employee_key=%s AND document_type=%s",
                    (new["expiry_date"], new["status"], json.dumps(raw), now, company, hero_key, dtype),
                )
                counts["compliance_tweaked"] += cur.rowcount
            conn.commit()
    counts["hero_employee"] = emps[0]["employee_key"]
    counts["employees"] = len(emps)
    return counts


def status(app, company: str) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) c FROM attendance_records WHERE company_code=%s AND metadata->>'demo_seed'=%s", (company, MARKER))
            a = cur.fetchone()["c"]
            cur.execute("SELECT count(*) c FROM shift_assignments WHERE company_code=%s AND metadata->>'demo_seed'=%s", (company, MARKER))
            s = cur.fetchone()["c"]
            cur.execute("SELECT count(*) c FROM leave_requests WHERE company_code=%s AND metadata->>'demo_seed'=%s", (company, MARKER))
            l = cur.fetchone()["c"]
            cur.execute("SELECT count(*) c FROM compliance_documents WHERE company_code=%s AND raw_json ? '_demo_backup'", (company,))
            c = cur.fetchone()["c"]
    return {"attendance": a, "shifts": s, "leave": l, "compliance_tweaked": c}


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    company = (sys.argv[2] if len(sys.argv) > 2 else "WATHEFNI").upper()
    app = _import_app()
    if mode == "seed":
        print(json.dumps(seed(app, company)))
    elif mode == "clean":
        print(json.dumps(clean(app, company)))
    else:
        print(json.dumps(status(app, company)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
