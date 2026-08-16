#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
print("boot", flush=True)
import app

app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}
app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
print("imported", flush=True)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT swap_id FROM shift_swap_requests WHERE company_code=%s AND status=%s ORDER BY requested_at DESC LIMIT 1",
            ("WATHEFNI", "requested"),
        )
        row = cur.fetchone()
print("row", dict(row) if row else None, flush=True)
if row:
    sid = str(dict(row)["swap_id"])
    print("calling approve", sid, flush=True)
    r = app.approve_shift_swap({"swap_id": sid}, company_code="WATHEFNI", created_by_phone="96588009911")
    print("done", r.get("ok"), r.get("error"), r.get("idempotent"), flush=True)
else:
    print("no swap", flush=True)
