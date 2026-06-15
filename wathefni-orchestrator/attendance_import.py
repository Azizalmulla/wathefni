"""Attendance Import V1 — pure pipeline (no DB, no network, no app import).

Wathefni imports attendance from a company's EXISTING fingerprint/attendance
device export (CSV/XLSX). It stores ONLY punch events (stable id + timestamp +
direction). It must NEVER store fingerprints, faceprints, biometric templates,
biometric images, or any raw biometric data. Any biometric-looking column is
detected, ignored, and never persisted.

This module is intentionally I/O-free so it can be unit-smoke-tested without a
database. app.py owns all DB reads/writes and calls these helpers.

Stages: parse -> normalize(coerce) -> match -> dedupe -> derive (shift-aware,
overnight-safe). Plus state_hash() for conflict-safe reverse.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

# --- File safety limits (guardrail #3) --------------------------------------
MAX_BYTES = 8 * 1024 * 1024          # 8 MB upload ceiling
MAX_ROWS = 20000                     # punch rows ceiling per file
ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xlsm")

# Shift-aware grouping windows (guardrail #2: overnight/cross-midnight).
GRACE_BEFORE = timedelta(hours=4)    # punch may precede shift start (early arrival)
GRACE_AFTER = timedelta(hours=4)     # punch may follow shift end (late departure)
DUP_WINDOW = timedelta(minutes=2)    # same employee+direction within window = duplicate

# Columns we will ever read from a device export. Everything else is ignored.
TARGET_FIELDS = ("external_id", "timestamp", "punch_date", "punch_time", "direction", "device", "name")

# Biometric-looking headers are dropped and never persisted.
_BIOMETRIC_RE = re.compile(r"(finger|face|template|minutiae|biometric|\bbio\b|thumb|iris|photo|image|picture)", re.I)

_DIRECTION_IN = {"in", "i", "0", "checkin", "check-in", "check in", "ci", "duty on", "on", "entry", "enter", "دخول", "حضور"}
_DIRECTION_OUT = {"out", "o", "1", "checkout", "check-out", "check out", "co", "duty off", "off", "exit", "leave", "خروج", "انصراف"}

# Header auto-detection aliases -> canonical target field.
_HEADER_ALIASES: dict[str, str] = {
    "id": "external_id", "userid": "external_id", "user_id": "external_id", "employeeid": "external_id",
    "employee_id": "external_id", "empid": "external_id", "emp_id": "external_id", "deviceuserid": "external_id",
    "device_user_id": "external_id", "staffid": "external_id", "staff_id": "external_id", "staffno": "external_id",
    "staff_no": "external_id", "pin": "external_id", "ac_no": "external_id", "acno": "external_id", "badge": "external_id",
    "badgeno": "external_id", "card": "external_id", "cardno": "external_id", "no": "external_id",
    "timestamp": "timestamp", "datetime": "timestamp", "date_time": "timestamp", "punchtime": "timestamp",
    "punch_time": "punch_time", "time": "punch_time", "logtime": "timestamp", "log_time": "timestamp",
    "date": "punch_date", "punchdate": "punch_date", "punch_date": "punch_date", "day": "punch_date",
    "direction": "direction", "type": "direction", "status": "direction", "inout": "direction", "in_out": "direction",
    "state": "direction", "mode": "direction", "verifytype": "direction", "punch_state": "direction",
    "device": "device", "devicename": "device", "device_name": "device", "terminal": "device", "machine": "device",
    "branch": "device", "location": "device",
    "name": "name", "employeename": "name", "employee_name": "name", "fullname": "name", "full_name": "name",
    "اسم": "name", "الاسم": "name",
}


# ---------------------------------------------------------------------------
# Header utilities
# ---------------------------------------------------------------------------

def normalize_header(value: Any) -> str:
    # Collapse common device-export separators (space, dash, slash, dot, colon)
    # to underscores so "Date/Time", "In/Out", "user-id" all alias cleanly.
    return re.sub(r"[\s\-/.:]+", "_", str(value or "").strip().lower()).strip("_")


def detect_biometric_columns(headers: list[str]) -> list[str]:
    """Headers that look like biometric data; these are dropped, never stored."""
    return [h for h in headers if h and _BIOMETRIC_RE.search(str(h))]


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Best-effort {canonical_field: source_header} from common device exports.
    Biometric columns are never suggested."""
    biometric = set(detect_biometric_columns(headers))
    out: dict[str, str] = {}
    for h in headers:
        if not h or h in biometric:
            continue
        canon = _HEADER_ALIASES.get(normalize_header(h))
        if canon and canon not in out:
            out[canon] = h
    return out


def mapping_is_usable(mapping: dict[str, str]) -> tuple[bool, str | None]:
    if not mapping.get("external_id"):
        return False, "Map the device/staff ID column (this is how we match employees)."
    if not (mapping.get("timestamp") or (mapping.get("punch_date") and mapping.get("punch_time"))):
        return False, "Map a timestamp column, or a date column and a time column."
    return True, None


# ---------------------------------------------------------------------------
# Parse (CSV/XLSX) — returns raw rows keyed by ORIGINAL header + header list.
# Biometric columns are dropped here so they are never persisted downstream.
# ---------------------------------------------------------------------------

def parse_tabular(raw: bytes, filename: str) -> tuple[list[dict[str, str]], list[str], list[str], str | None]:
    """Returns (rows, headers, dropped_biometric_headers, error)."""
    name = str(filename or "").lower()
    if not name.endswith(ALLOWED_EXTENSIONS):
        return [], [], [], "Please upload a CSV or XLSX file exported from your attendance device."
    if not raw:
        return [], [], [], "The file is empty."
    if len(raw) > MAX_BYTES:
        return [], [], [], f"This file is too large. Please keep imports under {MAX_BYTES // (1024 * 1024)} MB."
    try:
        if name.endswith((".xlsx", ".xlsm")):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                return [], [], [], "We couldn't read this spreadsheet."
            iterator = ws.iter_rows(values_only=True)
            try:
                header_row = next(iterator)
            except StopIteration:
                return [], [], [], "The file is empty."
            headers = [str(h).strip() if h is not None else "" for h in header_row]
            biometric = set(detect_biometric_columns(headers))
            rows: list[dict[str, str]] = []
            for values in iterator:
                if values is None:
                    continue
                rec: dict[str, str] = {}
                for h, val in zip(headers, values):
                    if not h or h in biometric or val is None:
                        continue
                    if isinstance(val, datetime):
                        text = val.isoformat()
                    elif isinstance(val, (date, time)):
                        text = val.isoformat()
                    elif isinstance(val, float) and val.is_integer():
                        text = str(int(val))
                    else:
                        text = str(val).strip()
                    if text:
                        rec[h] = text
                if rec:
                    rows.append(rec)
                if len(rows) > MAX_ROWS:
                    return [], headers, sorted(biometric), f"This file has too many rows. Please import up to {MAX_ROWS} punches per file."
            return rows, [h for h in headers if h], sorted(biometric), None
        # CSV
        text = raw.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], [], [], "The file is empty or missing a header row."
        headers = [str(h).strip() for h in reader.fieldnames if h is not None]
        biometric = set(detect_biometric_columns(headers))
        rows = []
        for raw_rec in reader:
            rec = {}
            for h in headers:
                if h in biometric:
                    continue
                value = str(raw_rec.get(h) or "").strip()
                if value:
                    rec[h] = value
            if rec:
                rows.append(rec)
            if len(rows) > MAX_ROWS:
                return [], headers, sorted(biometric), f"This file has too many rows. Please import up to {MAX_ROWS} punches per file."
        return rows, [h for h in headers if h], sorted(biometric), None
    except Exception as exc:  # noqa: BLE001 - never crash on a bad upload
        return [], [], [], f"We couldn't read this file ({type(exc).__name__}). Please upload a clean CSV or XLSX."


# ---------------------------------------------------------------------------
# Coerce one raw row -> normalized punch (no biometric fields).
# ---------------------------------------------------------------------------

def _parse_dt(value: str) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    # Try ISO first.
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    fmts = (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
    )
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _parse_date(value: str) -> date | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _parse_time(value: str) -> time | None:
    s = str(value or "").strip()
    if not s:
        return None
    for f in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return datetime.strptime(s.upper(), f).time()
        except ValueError:
            continue
    return None


def classify_direction(value: str) -> str | None:
    s = str(value or "").strip().lower()
    if not s:
        return None
    if s in _DIRECTION_IN:
        return "in"
    if s in _DIRECTION_OUT:
        return "out"
    # token contains
    if any(tok in s for tok in ("checkin", "check-in", "check in", "دخول", "حضور", "entry")):
        return "in"
    if any(tok in s for tok in ("checkout", "check-out", "check out", "خروج", "انصراف", "exit")):
        return "out"
    return None


def coerce_punch(row: dict[str, str], mapping: dict[str, str], tz: tzinfo, row_number: int) -> dict[str, Any]:
    """Returns a normalized punch with an `issues` list. No biometric fields."""
    issues: list[str] = []

    def col(field: str) -> str:
        src = mapping.get(field)
        return str(row.get(src) or "").strip() if src else ""

    external_id = col("external_id")
    if not external_id:
        issues.append("missing_external_id")

    dt: datetime | None = None
    if mapping.get("timestamp"):
        dt = _parse_dt(col("timestamp"))
    elif mapping.get("punch_date") or mapping.get("punch_time"):
        d = _parse_date(col("punch_date"))
        t = _parse_time(col("punch_time"))
        if d and t:
            dt = datetime.combine(d, t)
        elif d and not t:
            dt = datetime.combine(d, time(0, 0))
            issues.append("missing_time")
    if dt is None:
        issues.append("bad_datetime")
    else:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)

    direction = classify_direction(col("direction")) if mapping.get("direction") else None
    direction_explicit = direction is not None
    if mapping.get("direction") and direction is None and col("direction"):
        issues.append("unknown_direction")

    return {
        "row_number": row_number,
        "external_id": external_id,
        "dt": dt,
        "direction": direction,
        "direction_explicit": direction_explicit,
        "device": col("device") or None,
        "name_hint": col("name") or None,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Match / dedupe
# ---------------------------------------------------------------------------

def match_punches(punches: list[dict[str, Any]], device_id_to_employee: dict[str, str]) -> None:
    """Sets punch['employee_key'] from a STRICT device_user_id -> employee_key map.
    No name/phone auto-match. Unmatched punches get issue 'unmatched_employee'."""
    for p in punches:
        ext = str(p.get("external_id") or "").strip()
        emp = device_id_to_employee.get(ext) if ext else None
        p["employee_key"] = emp
        if not emp and "missing_external_id" not in p["issues"]:
            p["issues"].append("unmatched_employee")


def mark_duplicates(punches: list[dict[str, Any]]) -> None:
    """Flag near-identical punches (same employee+direction within DUP_WINDOW)."""
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for p in punches:
        if not p.get("employee_key") or p.get("dt") is None:
            continue
        keyed.setdefault((p["employee_key"], p.get("direction") or "?"), []).append(p)
    for group in keyed.values():
        group.sort(key=lambda x: x["dt"])
        last: datetime | None = None
        for p in group:
            if last is not None and (p["dt"] - last) <= DUP_WINDOW:
                if "duplicate_punch" not in p["issues"]:
                    p["issues"].append("duplicate_punch")
            else:
                last = p["dt"]


# ---------------------------------------------------------------------------
# Derive attendance records (shift-aware, overnight-safe).
# `shifts_by_employee[employee_key]` = list of {shift_id, shift_date(date),
# start_time(time), end_time(time)}.
# ---------------------------------------------------------------------------

def _shift_window(shift: dict[str, Any], tz: tzinfo) -> tuple[datetime, datetime] | None:
    d = shift.get("shift_date")
    st = shift.get("start_time")
    et = shift.get("end_time")
    if not isinstance(d, date) or not isinstance(st, time) or not isinstance(et, time):
        return None
    start_dt = datetime.combine(d, st, tzinfo=tz)
    end_dt = datetime.combine(d, et, tzinfo=tz)
    if et <= st:  # overnight shift crosses midnight
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def attribute_shift(punch_dt: datetime, shifts: list[dict[str, Any]], tz: tzinfo) -> dict[str, Any] | None:
    """Find the shift a punch belongs to, allowing overnight shifts and a grace
    window. Picks the shift whose window (±grace) contains the punch, nearest start."""
    best: dict[str, Any] | None = None
    best_dist: timedelta | None = None
    for shift in shifts:
        win = _shift_window(shift, tz)
        if not win:
            continue
        start_dt, end_dt = win
        if (start_dt - GRACE_BEFORE) <= punch_dt <= (end_dt + GRACE_AFTER):
            dist = abs(punch_dt - start_dt)
            if best_dist is None or dist < best_dist:
                best, best_dist = shift, dist
    return best


def derive_records(
    punches: list[dict[str, Any]],
    shifts_by_employee: dict[str, list[dict[str, Any]]],
    tz: tzinfo,
) -> list[dict[str, Any]]:
    """Group valid, matched, non-duplicate punches into one record per
    (employee, shift|work-date). first IN -> check_in, last OUT -> check_out.

    Direction inference (guardrail): when a punch has no explicit direction, we
    infer per (employee, work-date) by chronological order (1st=in, alternating),
    and flag the group 'inferred_direction' (low confidence)."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    # Only consider punches that can be applied.
    appliable = [
        p for p in punches
        if p.get("employee_key") and p.get("dt") is not None
        and "duplicate_punch" not in p["issues"] and "bad_datetime" not in p["issues"]
    ]
    # Resolve shift + work date for each punch.
    for p in appliable:
        shifts = shifts_by_employee.get(p["employee_key"], [])
        shift = attribute_shift(p["dt"], shifts, tz)
        if shift:
            p["_shift"] = shift
            p["_work_date"] = shift.get("shift_date")
            p["_group_key"] = str(shift.get("shift_id"))
        else:
            p["_shift"] = None
            p["_work_date"] = p["dt"].astimezone(tz).date()
            p["_group_key"] = "date:" + p["_work_date"].isoformat()

    # Infer directions per (employee, group) where missing.
    by_group_emp: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for p in appliable:
        by_group_emp.setdefault((p["employee_key"], p["_group_key"]), []).append(p)
    for plist in by_group_emp.values():
        plist.sort(key=lambda x: x["dt"])
        if any(p["direction"] is None for p in plist):
            # No reliable direction: infer by order, alternating in/out.
            for idx, p in enumerate(plist):
                if p["direction"] is None:
                    p["direction"] = "in" if idx % 2 == 0 else "out"
                    p["inferred"] = True

    for (emp, gkey), plist in by_group_emp.items():
        plist.sort(key=lambda x: x["dt"])
        ins = [p for p in plist if p["direction"] == "in"]
        outs = [p for p in plist if p["direction"] == "out"]
        check_in = min((p["dt"] for p in ins), default=None)
        check_out = max((p["dt"] for p in outs), default=None)
        shift = next((p["_shift"] for p in plist if p.get("_shift")), None)
        work_date = plist[0]["_work_date"]
        issues: list[str] = []
        if any(p.get("inferred") for p in plist):
            issues.append("inferred_direction")
        if check_in and not check_out:
            issues.append("missing_checkout")
        if check_out and not check_in:
            issues.append("missing_checkin")
        if not shift:
            issues.append("no_scheduled_shift")
        groups[(emp, gkey)] = {
            "employee_key": emp,
            "shift_id": str(shift.get("shift_id")) if shift else None,
            "attendance_date": work_date,
            "check_in_at": check_in,
            "check_out_at": check_out,
            "punch_count": len(plist),
            "row_numbers": sorted(p["row_number"] for p in plist),
            "issues": issues,
        }
    return list(groups.values())


# ---------------------------------------------------------------------------
# Conflict-safe reverse (guardrail #1): hash the import-owned fields so reverse
# can detect post-import manual/other-import edits and refuse to clobber.
# ---------------------------------------------------------------------------

def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    return str(value)


def state_hash(record: dict[str, Any]) -> str:
    """Stable hash of the fields an import owns. Used to detect later edits."""
    payload = {
        "check_in_at": _iso(record.get("check_in_at")),
        "check_out_at": _iso(record.get("check_out_at")),
        "status": str(record.get("status") or ""),
        "late_minutes": int(record.get("late_minutes") or 0),
        "early_leave_minutes": int(record.get("early_leave_minutes") or 0),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def summarize_outcomes(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.get("outcome", "unknown")] = counts.get(r.get("outcome", "unknown"), 0) + 1
    return counts
