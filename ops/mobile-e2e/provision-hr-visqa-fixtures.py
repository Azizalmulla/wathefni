#!/usr/bin/env python3
"""Provision production-safe synthetic HR mobile VisQA fixtures (WATHEFNI).

Seeds real canonical tables so HR mobile queues/details render like production.
Never uses EXPO_PUBLIC_HR_*_DEMO frontend stubs. Never touches Aziz/Talal.

Modules (3–5 rows each):
  - Document Reviews (needs_review + files)
  - Onboarding (HR-actionable items)
  - HR Tasks (open)
  - Delivery Alerts (employee_messages, hr_task_id NULL)
  - Attendance exceptions
  - Shift swaps (requested) when assignments can be created

Marker: hr_mobile_visqa_v1
Synthetic phones: 9655280101–9655280103 (VISQA| …)

Usage:
  python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py
  python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py --cleanup
  python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets  # noqa: E402

SSH_HOST = os.environ.get("MOBILE_E2E_SSH_HOST", "root@76.13.63.68")
API_BASE = os.environ.get("MOBILE_E2E_API_BASE", "https://api.wathefni.ai").rstrip("/")
LOCAL_FIXTURE_ENV = Path.home() / ".config" / "wathefni" / "visqa-fixtures.env"
MARKER = "hr_mobile_visqa_v1"

REMOTE_SCRIPT = r'''
import hashlib, json, os, sys, uuid
from datetime import date, datetime, timedelta, time as dtime, timezone
from pathlib import Path

pid = os.environ["ORCH_PID"]
with open(f"/proc/{pid}/environ", "rb") as f:
    for item in f.read().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")

os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app
from psycopg2.extras import Json

COMPANY = "WATHEFNI"
MARKER = "hr_mobile_visqa_v1"
MODE = os.environ.get("FIXTURE_MODE", "provision")
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}
MINI_PDF = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

EMPLOYEES = [
    {
        "phone": "9655280101",
        "name": "VISQA| Sara Al-Mutairi",
        "position_title": "Store Manager",
        "department": "Retail",
        "role": "docs",
    },
    {
        # 965523* + W2B-SYNTH| satisfies onboarding synthetic-canary seed gate (SEED stays off).
        "phone": "9655238102",
        "name": "W2B-SYNTH| VISQA Fahad Al-Sabah",
        "position_title": "Warehouse Operative",
        "department": "Operations",
        "role": "onboarding",
    },
    {
        # 965524* + W2G-SYNTH| → attendance authority synthetic-only path
        "phone": "9655248103",
        "name": "W2G-SYNTH| VISQA Noura Hassan",
        "position_title": "Sales Associate",
        "department": "Sales",
        "role": "ops",
    },
]

def key_for(phone: str) -> str:
    return f"{COMPANY}-{phone}"

KEYS = [key_for(e["phone"]) for e in EMPLOYEES]

def fixture_dir() -> Path:
    root = Path(os.environ.get("WATHEFNI_WORKSPACE") or "/root/.openclaw/workspaces/company-wathefni")
    path = root / "fixtures" / MARKER / STAMP
    path.mkdir(parents=True, exist_ok=True)
    return path

def write_pdf(name: str) -> tuple[Path, str, int]:
    path = fixture_dir() / name
    body = MINI_PDF + f"\n% {MARKER}:{STAMP}:{name}\n".encode()
    path.write_bytes(body)
    return path, hashlib.sha256(body).hexdigest(), len(body)

def cleanup(cur) -> dict:
    deleted = {
        "messages": 0, "tasks": 0, "attendance": 0, "projections": 0, "swaps": 0, "shift_assignments": 0,
        "compliance": 0, "files": 0, "versions": 0, "events": 0,
        "onboarding_items": 0, "employees_left": 0,
    }
    # Delivery alerts / tasks / attendance / swaps by marker
    cur.execute(
        """
        DELETE FROM employee_messages
         WHERE company_code=%s
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
             OR employee_key = ANY(%s)
           )
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
             OR COALESCE(template_key,'') LIKE 'visqa_%%'
           )
        """,
        (COMPANY, MARKER, KEYS, MARKER),
    )
    deleted["messages"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM hr_tasks
         WHERE company_code=%s
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
             OR title LIKE 'VISQA|%%'
           )
        """,
        (COMPANY, MARKER),
    )
    deleted["tasks"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM attendance_records
         WHERE company_code=%s
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
             OR employee_key = ANY(%s)
           )
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
           )
        """,
        (COMPANY, MARKER, KEYS, MARKER),
    )
    deleted["attendance"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM attendance_day_projections
         WHERE company_code=%s
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
             OR employee_key = ANY(%s)
           )
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(metadata->>'qa','')='__visqa__'
           )
        """,
        (COMPANY, MARKER, KEYS, MARKER),
    )
    deleted["projections"] = cur.rowcount
    cur.execute(
        """
        UPDATE shift_swap_requests
           SET status='cancelled', updated_at=now(),
               metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb
         WHERE company_code=%s
           AND (
             COALESCE(metadata->>'marker','')=%s
             OR COALESCE(reason,'') LIKE %s
           )
        """,
        (json.dumps({"visqa_cleanup": True, "stamp": STAMP}), COMPANY, MARKER, f"%{MARKER}%"),
    )
    deleted["swaps"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM shift_assignments
         WHERE company_code=%s
           AND COALESCE(metadata->>'marker','')=%s
        """,
        (COMPANY, MARKER),
    )
    deleted["shift_assignments"] = cur.rowcount
    # Document journey rows for VisQA employees
    cur.execute(
        """
        DELETE FROM governed_document_events
         WHERE company_code=%s AND employee_key = ANY(%s)
           AND (
             COALESCE(reason,'')=%s
             OR COALESCE(new_state->>'fixture','')=%s
             OR COALESCE(new_state->>'marker','')=%s
           )
        """,
        (COMPANY, KEYS, MARKER, MARKER, MARKER),
    )
    deleted["events"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM governed_document_versions
         WHERE company_code=%s AND employee_key = ANY(%s)
           AND (
             COALESCE(confirmed_metadata->>'fixture','')=%s
             OR COALESCE(confirmed_metadata->>'marker','')=%s
           )
        """,
        (COMPANY, KEYS, MARKER, MARKER),
    )
    deleted["versions"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM file_registry
         WHERE company_code=%s AND subject_type='employee' AND subject_key = ANY(%s)
           AND (
             COALESCE(metadata->>'fixture','')=%s
             OR COALESCE(metadata->>'marker','')=%s
           )
        """,
        (COMPANY, KEYS, MARKER, MARKER),
    )
    deleted["files"] = cur.rowcount
    cur.execute(
        """
        DELETE FROM compliance_documents
         WHERE company_code=%s AND employee_key = ANY(%s)
           AND (
             COALESCE(raw_json->>'marker','')=%s
             OR COALESCE(raw_json->>'fixture','')=%s
             OR document_type LIKE 'visqa_%%'
           )
        """,
        (COMPANY, KEYS, MARKER, MARKER),
    )
    deleted["compliance"] = cur.rowcount
    # Onboarding VisQA employee only
    onboarding_key = key_for("9655238102")
    cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s", (onboarding_key,))
    deleted["onboarding_items"] = cur.rowcount
    cur.execute(
        """
        UPDATE employees
           SET onboarding_status='not_started',
               employment_status='left',
               updated_at=now(),
               raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
         WHERE company_code=%s AND employee_key = ANY(%s)
           AND COALESCE(raw_json->>'marker','')=%s
        """,
        (json.dumps({"visqa_cleanup": True, "stamp": STAMP}), COMPANY, KEYS, MARKER),
    )
    deleted["employees_left"] = cur.rowcount
    return deleted

def ensure_employees(cur) -> None:
    for e in EMPLOYEES:
        ek = key_for(e["phone"])
        if ek in PROTECTED:
            raise SystemExit(f"refusing protected key {ek}")
        profile = {"department": e["department"], "team": e["department"], "visqa": True}
        raw = {"marker": MARKER, "fixture": MARKER, "stamp": STAMP, "synthetic": True, "qa": "__visqa__"}
        cur.execute(
            """
            INSERT INTO employees (
              company_code, employee_key, phone, name, position_title,
              onboarding_status, employment_status, profile, raw_json,
              hire_date, start_date, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,%s,
              %s,'active',%s,%s,
              CURRENT_DATE - 120, CURRENT_DATE - 90, now(), now()
            )
            ON CONFLICT (employee_key) DO UPDATE SET
              phone=EXCLUDED.phone,
              name=EXCLUDED.name,
              position_title=EXCLUDED.position_title,
              employment_status='active',
              onboarding_status=EXCLUDED.onboarding_status,
              profile=EXCLUDED.profile,
              raw_json = COALESCE(employees.raw_json,'{}'::jsonb) || EXCLUDED.raw_json,
              updated_at=now()
            """,
            (
                COMPANY,
                ek,
                e["phone"],
                e["name"],
                e["position_title"],
                "in_progress" if e["role"] == "onboarding" else "completed",
                Json(profile),
                Json(raw),
            ),
        )

def insert_file(cur, *, phone: str, employee_key: str, document_type: str, filename: str) -> str:
    path, digest, size = write_pdf(filename)
    file_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO file_registry (
          file_id, company_code, owner_phone, subject_type, subject_key, file_kind,
          document_type, original_filename, source_path, local_path,
          storage_provider, content_sha256, mime_type, size_bytes, storage_status,
          metadata, raw_json, stored_at, updated_at
        ) VALUES (
          %s,%s,%s,'employee',%s,'compliance_document',
          %s,%s,%s,%s,
          'local',%s,'application/pdf',%s,'stored',
          %s,%s,now(),now()
        )
        """,
        (
            file_id, COMPANY, phone, employee_key, document_type, filename,
            str(path), str(path), digest, size,
            Json({"fixture": MARKER, "marker": MARKER, "stamp": STAMP}),
            Json({"fixture": MARKER, "marker": MARKER, "stamp": STAMP}),
        ),
    )
    return file_id

def upsert_compliance(cur, *, employee_key: str, document_type: str, label: str, status: str, expiry, confidence=None, days_until=None):
    cur.execute(
        """
        INSERT INTO compliance_documents (
          company_code, employee_key, document_type, label, status, expiry_date,
          days_until_expiry, warning_days, extraction_confidence, last_checked_at,
          reminder_count, raw_json, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,
          %s,30,%s,now(),
          0,%s,now()
        )
        ON CONFLICT (employee_key, document_type) DO UPDATE SET
          company_code=EXCLUDED.company_code,
          label=EXCLUDED.label,
          status=EXCLUDED.status,
          expiry_date=EXCLUDED.expiry_date,
          days_until_expiry=EXCLUDED.days_until_expiry,
          extraction_confidence=EXCLUDED.extraction_confidence,
          last_checked_at=now(),
          raw_json=EXCLUDED.raw_json,
          notes=NULL,
          updated_at=now()
        """,
        (
            COMPANY, employee_key, document_type, label, status, expiry,
            days_until, confidence,
            Json({"marker": MARKER, "fixture": MARKER, "stamp": STAMP, "qa": "__visqa__"}),
        ),
    )

def seed_documents(cur) -> list[dict]:
    today = date.today()
    sara = next(e for e in EMPLOYEES if e["role"] == "docs")
    ek = key_for(sara["phone"])
    phone = sara["phone"]
    specs = [
        ("civil_id", "Civil ID", "needs_review", today + timedelta(days=210), 210, 0.92),
        ("passport", "Passport", "needs_review", today + timedelta(days=18), 18, 0.81),
        ("residence", "Residency", "needs_review", today + timedelta(days=9), 9, 0.74),
        ("work_permit", "Work permit", "needs_review", today + timedelta(days=120), 120, 0.66),
    ]
    out = []
    for dtype, label, status, expiry, days, conf in specs:
        fid = insert_file(cur, phone=phone, employee_key=ek, document_type=dtype, filename=f"{dtype}-{STAMP}.pdf")
        upsert_compliance(cur, employee_key=ek, document_type=dtype, label=label, status=status, expiry=expiry, confidence=conf, days_until=days)
        out.append({"employee_key": ek, "document_type": dtype, "label": label, "file_id": fid, "days_until_expiry": days})
    return out

def seed_onboarding(cur) -> dict:
    fahad = next(e for e in EMPLOYEES if e["role"] == "onboarding")
    ek = key_for(fahad["phone"])
    emp = app.find_employee_by_key(ek, company_code=COMPANY) or {
        "employee_key": ek, "company_code": COMPANY, "phone": fahad["phone"], "name": fahad["name"],
        "start_date": date.today() - timedelta(days=14),
    }
    try:
        import onboarding_lifecycle_wave2a as lifecycle
        lifecycle.ensure_lifecycle_schema(cur)
    except Exception:
        pass
    count = 0
    try:
        count = int(app.seed_onboarding_items(cur, emp) or 0)
    except Exception as exc:
        count = 0
        seed_err = str(exc)
    else:
        seed_err = None

    # Manual HR-actionable rows if template seed was blocked (SEED off / non-canary).
    hr_specs = [
        ("passport", "Passport", "document", "processing"),
        ("offer_letter", "Offer letter", "document", "submitted"),
        ("civil_id", "Civil ID", "document", "needs_review"),
        ("residence", "Residency", "document", "processing"),
    ]
    for item_id, label, item_type, status in hr_specs:
        cur.execute(
            """
            INSERT INTO onboarding_items (
              employee_key, item_id, label, item_type, required, document_type, status,
              owner, sort_order, lifecycle_meta, raw_json, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,TRUE,%s,%s,
              'hr',10,%s,%s,now(),now()
            )
            ON CONFLICT (employee_key, item_id) DO UPDATE SET
              status=EXCLUDED.status,
              label=EXCLUDED.label,
              lifecycle_meta = COALESCE(onboarding_items.lifecycle_meta,'{}'::jsonb) || EXCLUDED.lifecycle_meta,
              raw_json = COALESCE(onboarding_items.raw_json,'{}'::jsonb) || EXCLUDED.raw_json,
              updated_at=now()
            """,
            (
                ek, item_id, label, item_type, item_id, status,
                Json({"fixture": MARKER, "marker": MARKER, "stamp": STAMP}),
                Json({"fixture": MARKER, "marker": MARKER, "stamp": STAMP, "qa": "__visqa__"}),
            ),
        )

    cur.execute(
        """
        UPDATE onboarding_items
           SET lifecycle_meta = COALESCE(lifecycle_meta,'{}'::jsonb) || %s::jsonb,
               raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
               updated_at=now()
         WHERE employee_key=%s
        """,
        (Json({"fixture": MARKER, "marker": MARKER, "stamp": STAMP}), Json({"fixture": MARKER, "marker": MARKER, "stamp": STAMP}), ek),
    )
    cur.execute(
        """
        UPDATE employees SET onboarding_status='in_progress', updated_at=now()
         WHERE employee_key=%s AND company_code=%s
        """,
        (ek, COMPANY),
    )
    return {
        "employee_key": ek,
        "seeded_template_items": count,
        "seed_error": seed_err,
        "hr_items": [x[0] for x in hr_specs],
    }

def seed_tasks(cur) -> list[str]:
    ids = []
    sara = key_for("9655280101")
    noura = key_for("9655248103")
    # priority=high + fresh updated_at so default limit=30 queue shows VISQA first.
    rows = [
        (sara, "delivery_failed", "outbound", "high", "VISQA| WhatsApp delivery failed — Civil ID reminder", "Last attempt returned conversation_inactive. Follow up so the employee can renew."),
        (noura, "app_activation_handoff", "employee_app", "high", "VISQA| App activation needs HR follow-up", "Invite accepted but first sign-in did not complete."),
        (sara, "candidate_handoff", "recruiting", "high", "VISQA| Candidate handoff waiting on HR", "Automation paused for a recruiter handoff."),
        (None, "account_deletion", "privacy", "high", "VISQA| Account deletion request — company follow-up", "Company-wide VisQA task (no employee_key)."),
    ]
    for emp_key, ttype, source, priority, title, detail in rows:
        tid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO hr_tasks (
              task_id, company_code, employee_key, task_type, source, title, detail,
              status, priority, metadata, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,
              'open',%s,%s,now(),now()
            )
            """,
            (
                tid, COMPANY, emp_key, ttype, source, title, detail, priority,
                Json({"marker": MARKER, "qa": "__visqa__", "stamp": STAMP}),
            ),
        )
        ids.append(tid)
    return ids

def seed_delivery_alerts(cur) -> list[str]:
    ids = []
    noura = key_for("9655248103")
    sara = key_for("9655280101")
    # Mobile title = flow_label/flow — prefix VISQA| so the queue is identifiable.
    specs = [
        (noura, "needs_hr_action", "VISQA| Onboarding", "session:no_usable_conversation_id", "WhatsApp session unavailable"),
        (sara, "failed", "VISQA| Compliance", "whatsapp:template_paused", "Template delivery failed"),
        (noura, "throttled", "VISQA| Leave", "rate_limit:outbound", "Outbound throttled — retry later"),
    ]
    for emp_key, status, flow, err, preview in specs:
        mid = str(uuid.uuid4())
        phone = emp_key.split("-", 1)[-1]
        cur.execute(
            """
            INSERT INTO employee_messages (
              message_id, company_code, employee_key, flow, template_key, criticality,
              status, channel_used, last_error, attempts, body_preview, hr_task_id,
              target_phone, metadata, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,%s,'standard',
              %s,'whatsapp_session',%s,2,%s,NULL,
              %s,%s,now(),now()
            )
            """,
            (
                mid, COMPANY, emp_key, flow, f"visqa_{status}",
                status, err, f"VISQA| {preview}",
                phone,
                Json({"marker": MARKER, "qa": "__visqa__", "stamp": STAMP}),
            ),
        )
        ids.append(mid)
    return ids

def seed_attendance(cur) -> list[str]:
    """Seed authority projections (SYNTHETIC_ONLY) + legacy mirror rows for unresolved + today."""
    ids = []
    noura = next(e for e in EMPLOYEES if e["role"] == "ops")
    ek = key_for(noura["phone"])
    today = app.kuwait_today() if hasattr(app, "kuwait_today") else date.today()

    # App Unresolved uses start=today-92, end=today-1. Backend clamps the span to
    # the first ~31 days from that start — so seed unresolved rows there, not "last week".
    lookback_start = today - timedelta(days=92)
    while lookback_start.weekday() >= 5:
        lookback_start += timedelta(days=1)
    specs = [
        # Today tab (bare ?status=exceptions also defaults to today)
        (today, "late", 28, 0, dtime(9, 28), dtime(17, 2), "lateness", "Late check-in"),
        # Unresolved tab — inside clamped window lookback_start .. +30d
        (lookback_start + timedelta(days=3), "absent", 0, 0, None, None, "absence", "No show"),
        (lookback_start + timedelta(days=10), "early_leave", 0, 45, dtime(9, 1), dtime(16, 15), "early_leave", "Left early"),
        (lookback_start + timedelta(days=17), "incomplete", 0, 0, dtime(9, 5), None, "missing_check_out", "Missing check-out"),
    ]

    # Prefer authority service insert so mobile list (authority path) sees rows.
    svc = None
    try:
        import attendance_authority_wave1 as auth
        if auth.attendance_authority_enabled_for_company(COMPANY):
            svc = auth.get_authority_service(COMPANY) if hasattr(auth, "get_authority_service") else None
            if svc is None and hasattr(app, "_attendance_authority"):
                svc = app._attendance_authority.get_authority_service(COMPANY)
    except Exception:
        svc = None

    for day, status, late, early, cin, cout, exc_state, note in specs:
        cin_ts = datetime.combine(day, cin) if cin else None
        cout_ts = datetime.combine(day, cout) if cout else None
        meta = {"marker": MARKER, "qa": "__visqa__", "stamp": STAMP, "notes": f"[{MARKER}] {note}"}
        proj = {
            "company_code": COMPANY,
            "employee_key": ek,
            "employee_phone": noura["phone"],
            "employee_name": noura["name"],
            "work_date": day,
            "shift_key": "",
            "status": status,
            "exception_state": exc_state,
            "approval_status": "unapproved",
            "payroll_eligible": False,
            "check_in_at": cin_ts,
            "check_out_at": cout_ts,
            "scheduled_start": dtime(9, 0),
            "scheduled_end": dtime(17, 0),
            "late_minutes": late,
            "early_leave_minutes": early,
            "worked_minutes": 0,
            "metadata": meta,
            "manual_correction": False,
        }
        pid = None
        if svc is not None:
            try:
                saved = svc.insert_projection(proj)
                pid = str(saved.get("projection_id") or "")
            except Exception as exc:
                # Fall through to SQL insert below
                pid = None
                proj_err = str(exc)
            else:
                proj_err = None
        if not pid:
            pid = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO attendance_day_projections (
                  projection_id, company_code, employee_key, employee_phone, employee_name,
                  work_date, shift_key, version, is_current, status, exception_state,
                  approval_status, payroll_eligible, check_in_at, check_out_at,
                  scheduled_start, scheduled_end, late_minutes, early_leave_minutes,
                  metadata, created_at, updated_at
                ) VALUES (
                  %s,%s,%s,%s,%s,
                  %s,'',1,true,%s,%s,
                  'unapproved',false,%s,%s,
                  %s,%s,%s,%s,
                  %s,now(),now()
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    pid, COMPANY, ek, noura["phone"], noura["name"],
                    day, status, exc_state, cin_ts, cout_ts,
                    dtime(9, 0), dtime(17, 0), late, early,
                    Json(meta),
                ),
            )
        # Legacy mirror (harmless; authority list uses projections)
        aid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO attendance_records (
              attendance_id, company_code, employee_key, employee_phone, employee_name,
              attendance_date, scheduled_start, scheduled_end,
              check_in_at, check_out_at, status, late_minutes, early_leave_minutes,
              notes, metadata, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,%s,
              %s,'09:00','17:00',
              %s,%s,%s,%s,%s,
              %s,%s,now(),now()
            )
            """,
            (
                aid, COMPANY, ek, noura["phone"], noura["name"],
                day, cin_ts, cout_ts, status, late, early,
                f"[{MARKER}] {note}",
                Json({**meta, "projection_id": pid}),
            ),
        )
        ids.append(pid or aid)
    return ids

def seed_shift_swaps(cur) -> list[str]:
    """Best-effort: two assignments + one requested swap. Uses SAVEPOINT so failures never roll back other modules."""
    ids = []
    cur.execute("SAVEPOINT visqa_swaps")
    try:
        sara = key_for("9655280101")
        noura = key_for("9655248103")
        day = date.today() + timedelta(days=3)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        for sid, ek, phone, name in (
            (sid_a, sara, "9655280101", "VISQA| Sara Al-Mutairi"),
            (sid_b, noura, "9655248103", "VISQA| Noura Hassan"),
        ):
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  shift_id, company_code, employee_key, employee_phone, employee_name,
                  shift_date, start_time, end_time, location, role, status,
                  metadata, created_at, updated_at
                ) VALUES (
                  %s,%s,%s,%s,%s,
                  %s,'09:00','17:00','Salmiya store','Floor','scheduled',
                  %s, now(), now()
                )
                """,
                (
                    sid, COMPANY, ek, phone, name, day,
                    Json({"marker": MARKER, "qa": "__visqa__", "stamp": STAMP}),
                ),
            )
        swap_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO shift_swap_requests (
              swap_id, company_code, requester_employee_key, target_employee_key,
              requester_shift_id, target_shift_id, shift_date, status, reason,
              metadata, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,
              %s,%s,%s,'requested',%s,
              %s,now(),now()
            )
            """,
            (
                swap_id, COMPANY, sara, noura,
                sid_a, sid_b, day,
                f"[{MARKER}] Family appointment — disposable VisQA swap",
                Json({"marker": MARKER, "qa": "__visqa__", "stamp": STAMP}),
            ),
        )
        ids.append(swap_id)
        cur.execute("RELEASE SAVEPOINT visqa_swaps")
        return ids
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT visqa_swaps")
        return {"error": str(exc), "ids": ids}

# —— main ——
with app.db_connect() as conn:
    with conn.cursor() as cur:
        if MODE == "cleanup":
            deleted = cleanup(cur)
            conn.commit()
            print(json.dumps({"ok": True, "mode": "cleanup", "deleted": deleted, "marker": MARKER}))
            raise SystemExit(0)

        # Idempotent reset then provision
        cleanup(cur)
        ensure_employees(cur)
        docs = seed_documents(cur)
        onboarding = seed_onboarding(cur)
        tasks = seed_tasks(cur)
        alerts = seed_delivery_alerts(cur)
        attendance = seed_attendance(cur)
        swaps = seed_shift_swaps(cur)
        conn.commit()
        print(json.dumps({
            "ok": True,
            "mode": "provision",
            "marker": MARKER,
            "stamp": STAMP,
            "employees": [{"key": key_for(e["phone"]), "name": e["name"], "role": e["role"]} for e in EMPLOYEES],
            "documents": docs,
            "onboarding": onboarding,
            "task_ids": tasks,
            "delivery_alert_ids": alerts,
            "attendance_ids": attendance,
            "shift_swap_ids": swaps if isinstance(swaps, list) else swaps,
        }, default=str))
'''


def _ssh(mode: str) -> dict[str, Any]:
    remote = (
        "pid=$(systemctl show -p MainPID --value wathefni-orchestrator); "
        "export ORCH_PID=$pid FIXTURE_MODE="
        + mode
        + "; "
        "/opt/wathefni/orchestrator/.venv/bin/python - <<'PY'\n"
        + REMOTE_SCRIPT
        + "\nPY"
    )
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SSH_HOST, remote],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"SSH fixture failed rc={proc.returncode}: {proc.stderr[-1200:]}\n{proc.stdout[-800:]}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"No JSON from fixture SSH. stdout={proc.stdout[-800:]!r}")
    # last JSON object
    return json.loads(lines[-1])


def _api(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else {"error": raw}
        except Exception:
            return exc.code, {"error": raw}


def _mint_aziz_owner_token() -> dict[str, Any]:
    """Mint a real operator-mobile token for azizalmulla16@gmail.com (owner).

    E2E HR login is NOT the owner app session — never treat e2ehr visibility as Aziz truth.
    """
    remote = r'''
import json, os, sys
pid = os.environ["ORCH_PID"]
with open(f"/proc/{pid}/environ", "rb") as f:
    for item in f.read().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ[k.decode()] = v.decode()
os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM dashboard_users
             WHERE company_code=%s AND email=%s AND status=%s
             LIMIT 1
            """,
            ("WATHEFNI", "azizalmulla16@gmail.com", "active"),
        )
        row = cur.fetchone()
if not row:
    print(json.dumps({"ok": False, "error": "aziz_owner_missing"}))
    raise SystemExit(1)
user = dict(row)
tokens = app._operator_mobile.create_operator_mobile_session(
    app, user, device_label="visqa-aziz-verify"
)
print(json.dumps({
    "ok": True,
    "access_token": tokens.get("access_token"),
    "user_id": str(user.get("user_id")),
    "email": user.get("email"),
    "role": user.get("role"),
}))
'''
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            SSH_HOST,
            "ORCH_PID=$(systemctl show -p MainPID --value wathefni-orchestrator) "
            "/opt/wathefni/orchestrator/.venv/bin/python - <<'PY'\n" + remote + "\nPY",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Aziz token mint failed: {proc.stderr[-800:]}{proc.stdout[-400:]}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError("Aziz token mint returned no JSON")
    data = json.loads(lines[-1])
    if not data.get("ok") or not data.get("access_token"):
        raise RuntimeError(f"Aziz token mint bad payload: {data}")
    return data


def _is_visqa_item(it: dict[str, Any]) -> bool:
    blob = json.dumps(it, default=str)
    if MARKER in blob or "VISQA" in blob or "W2B-SYNTH" in blob or "W2G-SYNTH" in blob:
        return True
    return any(
        k in blob
        for k in ("WATHEFNI-9655280101", "WATHEFNI-9655238102", "WATHEFNI-9655248103")
    )


def verify(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify VisQA rows on the exact mobile endpoints Aziz's app uses."""
    from datetime import date, timedelta

    actor = _mint_aziz_owner_token()
    token = str(actor["access_token"])
    today = date.today()
    unresolved_start = (today - timedelta(days=92)).isoformat()
    unresolved_end = (today - timedelta(days=1)).isoformat()

    surfaces = [
        {
            "surface": "documents",
            "path": "/dashboard/mobile/documents?status=needs_review",
            "expected_min": 3,
        },
        {
            "surface": "onboarding",
            "path": "/dashboard/mobile/onboarding",
            "expected_min": 1,
        },
        {
            "surface": "tasks",
            "path": "/dashboard/mobile/tasks?status=open",
            "expected_min": 3,
        },
        {
            "surface": "delivery_alerts",
            "path": "/dashboard/mobile/delivery-alerts",
            "expected_min": 3,
        },
        {
            "surface": "attendance_exceptions_bare",
            "path": "/dashboard/mobile/attendance?status=exceptions",
            "expected_min": 1,
        },
        {
            "surface": "attendance_unresolved",
            "path": (
                f"/dashboard/mobile/attendance?status=exceptions"
                f"&start_date={unresolved_start}&end_date={unresolved_end}&limit=100"
            ),
            "expected_min": 3,
        },
        {
            "surface": "shift_swaps",
            "path": "/dashboard/mobile/shift-swaps?status=requested",
            "expected_min": 1,
        },
    ]

    matrix = []
    for spec in surfaces:
        code, body = _api("GET", spec["path"], token=token)
        items = (body or {}).get("items") if isinstance(body, dict) else None
        if not isinstance(items, list):
            items = []
        hits = [it for it in items if isinstance(it, dict) and _is_visqa_item(it)]
        expected = int(spec["expected_min"])
        actual = len(hits)
        verdict = "PASS" if code == 200 and actual >= expected else "FAIL"
        matrix.append(
            {
                "surface": spec["surface"],
                "path": spec["path"],
                "http": code,
                "returned_count": len(items),
                "total": (body or {}).get("total") if isinstance(body, dict) else None,
                "expected_visqa_min": expected,
                "actual_visqa": actual,
                "verdict": verdict,
                "api_window": {
                    "start_date": (body or {}).get("start_date") if isinstance(body, dict) else None,
                    "end_date": (body or {}).get("end_date") if isinstance(body, dict) else None,
                },
            }
        )

    detail = None
    if payload and payload.get("documents"):
        d0 = payload["documents"][0]
        ek = d0["employee_key"]
        dtype = d0["document_type"]
        c, body = _api("GET", f"/dashboard/mobile/documents/{ek}/{dtype}", token=token)
        doc = (
            (body or {}).get("document") or (body or {}).get("item")
            if isinstance(body, dict)
            else None
        )
        detail = {
            "http": c,
            "has_item": isinstance(doc, dict) and bool(doc),
            "label": (doc or {}).get("label") if isinstance(doc, dict) else None,
        }

    ok = all(row["verdict"] == "PASS" for row in matrix)
    return {
        "ok": ok,
        "actor": {
            "user_id": actor.get("user_id"),
            "email": actor.get("email"),
            "role": actor.get("role"),
        },
        "matrix": matrix,
        "document_detail": detail,
        "seeded": ok,
    }


def write_env(payload: dict[str, Any]) -> Path:
    LOCAL_FIXTURE_ENV.parent.mkdir(parents=True, exist_ok=True)
    docs = payload.get("documents") or []
    tasks = payload.get("task_ids") or []
    lines = [
        f"# Auto-generated by provision-hr-visqa-fixtures.py — DO NOT COMMIT",
        f"VISQA_MARKER={MARKER}",
        f"VISQA_STAMP={payload.get('stamp','')}",
        f"VISQA_DOC_EMPLOYEE_KEY={(docs[0].get('employee_key') if docs else '')}",
        f"VISQA_DOC_TYPE={(docs[0].get('document_type') if docs else '')}",
        f"VISQA_TASK_ID={(tasks[0] if tasks else '')}",
        f"VISQA_ONBOARDING_KEY={((payload.get('onboarding') or {}).get('employee_key') or '')}",
        f"VISQA_ATTENDANCE_ID={((payload.get('attendance_ids') or [''])[0])}",
        f"VISQA_PAYLOAD={json.dumps(payload, default=str)}",
        "",
    ]
    LOCAL_FIXTURE_ENV.write_text("\n".join(lines))
    try:
        os.chmod(LOCAL_FIXTURE_ENV, 0o600)
    except OSError:
        pass
    return LOCAL_FIXTURE_ENV


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    load_secrets(override=True)

    if args.cleanup:
        result = _ssh("cleanup")
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.verify_only:
        result = verify()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    provisioned = _ssh("provision")
    path = write_env(provisioned)
    # brief settle for read replicas / caches if any
    time.sleep(1)
    verified = verify(provisioned)
    out = {"provision": provisioned, "verify": verified, "fixture_env": str(path)}
    print(json.dumps(out, indent=2, default=str))
    return 0 if provisioned.get("ok") and verified.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
