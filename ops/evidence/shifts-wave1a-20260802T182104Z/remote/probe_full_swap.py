#!/usr/bin/env python3
"""Create two shifts + swap + approve with stubs — isolate hang."""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
print("boot", flush=True)
import app
import shifts_authority_wave1 as sw1

app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}
app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}
print("imported", flush=True)

company = "WATHEFNI"
sfx = uuid.uuid4().hex[:8]
a_key = f"WATHEFNI-SHW1P-{sfx}"
b_key = f"WATHEFNI-SHW1Q-{sfx}"
phone_a = f"965528{sfx[:6]}"
phone_b = f"965528{sfx[1:6]}8"
actor = "96588009911"
day = date.today() + timedelta(days=21)

with app.db_connect() as conn:
    with conn.cursor() as cur:
        sw1.ensure_shifts_authority_wave1_schema(cur)
        for key, phone, name in ((a_key, phone_a, "Probe A"), (b_key, phone_b, "Probe B")):
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now()) ON CONFLICT DO NOTHING
                """,
                (company, key, name, phone),
            )
        conn.commit()
print("employees", flush=True)

ra = app.create_shift_assignment(
    {"employee_key": a_key, "date": day.isoformat(), "start_time": "08:00", "end_time": "12:00", "idempotency_key": f"p-a-{sfx}"},
    company_code=company,
    created_by_phone=actor,
)
rb = app.create_shift_assignment(
    {"employee_key": b_key, "date": day.isoformat(), "start_time": "13:00", "end_time": "17:00", "idempotency_key": f"p-b-{sfx}"},
    company_code=company,
    created_by_phone=actor,
)
print("created", ra.get("ok"), rb.get("ok"), flush=True)
sid_a = str((ra.get("created") or [{}])[0].get("shift_id"))
sid_b = str((rb.get("created") or [{}])[0].get("shift_id"))
print("requesting swap", flush=True)
req = app.request_shift_swap(
    {
        "employee_key": a_key,
        "target_phone": phone_b,
        "shift_id": sid_a,
        "target_shift_id": sid_b,
        "date": day.isoformat(),
        "reason": "probe",
    },
    company_code=company,
    created_by_phone=phone_a,
)
print("request", req.get("ok"), req.get("error"), flush=True)
swap_id = str((req.get("swap") or {}).get("swap_id"))
print("self deny", flush=True)
self_d = app.approve_shift_swap({"swap_id": swap_id}, company_code=company, created_by_phone=phone_a)
print("self", self_d.get("error"), flush=True)
print("approve", flush=True)
appr = app.approve_shift_swap({"swap_id": swap_id}, company_code=company, created_by_phone=actor)
print("approve result", appr.get("ok"), appr.get("error"), flush=True)
print("replay", flush=True)
rep = app.approve_shift_swap({"swap_id": swap_id}, company_code=company, created_by_phone=actor)
print("replay", rep.get("ok"), rep.get("idempotent"), rep.get("error"), flush=True)
print("DONE", flush=True)
