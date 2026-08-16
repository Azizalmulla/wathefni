#!/usr/bin/env python3
"""Attendance Wave 2E — production dark canary (synthetic/lab only).

Proves capture-ops APIs: seed, rotate/revoke/reconnect, wrong-tenant denial,
remediation approve/reject idempotency, payroll exclusion, health lag/offline,
manager self/cross-tenant denial, ingest still off. No real devices.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

PASS = 0
FAIL = 0
RESULTS: list[dict[str, Any]] = []


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL
    RESULTS.append({"label": label, "ok": bool(cond), "detail": detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    if (os.environ.get("WATHEFNI_ENV") or "").lower() != "production":
        print("REFUSE: WATHEFNI_ENV must be production for this canary")
        return 2

    import app
    import attendance_capture_ops as ops
    from attendance_capture_secrets import REDACTED, scan_paths, qualify_or_block

    ops.reset_capture_ops_for_tests()

    check("capture ops enabled", app.attendance_capture_ops_enabled() is True)
    check("capture ingest off", app.attendance_capture_ingest_enabled() is False)
    check("import off", app.attendance_import_enabled() is False)
    check("authority synthetic only", app.attendance_authority_synthetic_only() is True)

    tag = uuid.uuid4().hex[:8]
    company = "WATHEFNI"
    other = "OTHERCO"
    manager = f"96552410{tag[:4]}"
    self_phone = f"96552420{tag[:4]}"

    reg = ops.get_registry()
    site = reg.register_site(company_code=company, name=f"W2E Lab {tag}")
    other_site = reg.register_site(company_code=other, name=f"Other {tag}")
    check("site registered", bool(site.site_id))

    steal = reg.register_device(
        company_code=company, site_id=site.site_id, terminal_sn=f"LAB-SN-{tag}", actor_company=other
    )
    check("wrong-tenant device denied", not steal["ok"], steal)

    owned = reg.register_device(company_code=company, site_id=site.site_id, terminal_sn=f"LAB-SN-{tag}")
    check("device registered", owned["ok"], owned)
    device_id = owned["device"]["device_id"]

    claim = reg.register_device(company_code=other, site_id=other_site.site_id, terminal_sn=f"LAB-SN-{tag}")
    check("wrong-tenant claim denied", not claim["ok"] and claim.get("error") == "device_owned_by_other_tenant", claim)

    conn = reg.register_connector(
        company_code=company,
        site_id=site.site_id,
        device_id=device_id,
        secrets={"username": "lab", "password": f"pw-{tag}", "token": f"tok-{tag}"},
        connector_version="wave2e",
        actor_phone=manager,
    )
    check("connector registered secrets redacted", conn["ok"] and conn["secrets"] == REDACTED, conn)
    cid = conn["connector"]["connector_id"]
    rv = conn["connector"]["row_version"]
    act = reg.activate(cid, expected_row_version=rv, actor_phone=manager)
    check("connector activated", act["ok"], act)
    rv = act["connector"]["row_version"]

    rot = reg.rotate_credentials(
        cid,
        new_secrets={"username": "lab", "password": f"pw2-{tag}", "token": f"tok2-{tag}"},
        expected_row_version=rv,
        actor_phone=manager,
    )
    check("rotate ok", rot["ok"] and rot["secrets"] == REDACTED, rot)
    rv = rot["connector"]["row_version"]
    recon = reg.reconnect_after_rotate(cid)
    check("reconnect after rotate", recon["ok"] and recon["secrets"] == REDACTED and recon["has_password"], recon)

    cross = reg.assert_connector_tenant(cid, other)
    check("cross-tenant connector denied", not cross["ok"], cross)

    # second connector for revoke
    conn2 = reg.register_connector(
        company_code=company,
        site_id=site.site_id,
        device_id=device_id,
        secrets={"password": f"rev-{tag}"},
        connector_version="wave2e",
    )
    cid2 = conn2["connector"]["connector_id"]
    rv2 = conn2["connector"]["row_version"]
    act2 = reg.activate(cid2, expected_row_version=rv2)
    rv2 = act2["connector"]["row_version"]
    rev = reg.revoke(cid2, expected_row_version=rv2, reason="canary", actor_phone=manager)
    check("revoke ok", rev["ok"], rev)
    check("reconnect after revoke denied", not reg.reconnect_after_rotate(cid2)["ok"])

    q = ops.get_queue()
    enq = q.enqueue(
        company_code=company,
        kind="unknown_employee",
        connector_id=cid,
        device_user_id=f"LABDU-{tag}",
        payload={
            "company_code": company,
            "source": "biotime",
            "source_event_id": f"biotime:w2e-{tag}",
            "device_user_id": f"LABDU-{tag}",
            "punched_at": "2026-08-25T09:05:00+03:00",
            "direction": "in",
            "capture_method": "card",
        },
        idempotency_key=f"w2e-unk-{tag}",
    )
    check("unknown remediation", enq["ok"] and not enq["duplicate"], enq)
    item_id = enq["item"]["item_id"]
    item_rv = enq["item"]["row_version"]
    enq2 = q.enqueue(
        company_code=company,
        kind="unknown_employee",
        connector_id=cid,
        device_user_id=f"LABDU-{tag}",
        payload={},
        idempotency_key=f"w2e-unk-{tag}",
    )
    check("enqueue idempotent", enq2["ok"] and enq2["duplicate"], enq2)

    cross_approve = q.approve_mapping(
        item_id,
        employee_key=f"{company}-ATTW2E-{tag}",
        expected_row_version=item_rv,
        actor_phone=manager,
        actor_company=other,
        replay=False,
    )
    check("approve cross-tenant denied", not cross_approve["ok"], cross_approve)

    self_deny = q.approve_mapping(
        item_id,
        employee_key=f"{company}-ATTW2E-{tag}",
        expected_row_version=item_rv,
        actor_phone=self_phone,
        actor_company=company,
        actor_is_manager=True,
        employee_phone=self_phone,
        replay=False,
    )
    check("manager self-action denied", not self_deny["ok"], self_deny)

    approve = q.approve_mapping(
        item_id,
        employee_key=f"{company}-ATTW2E-{tag}",
        expected_row_version=item_rv,
        actor_phone=manager,
        actor_company=company,
        actor_is_manager=True,
        employee_phone=self_phone,
        replay=False,
    )
    check("approve mapping without ingest replay", approve["ok"], approve)
    check("ingest remains off so no authority punch from dark approve", app.attendance_capture_ingest_enabled() is False)

    miss = q.mark_projection_exception(
        company_code=company,
        kind="missing_check_out",
        employee_key=f"{company}-ATTW2E-{tag}",
        work_date="2026-08-25",
        projection={"status": "incomplete"},
        connector_id=cid,
    )
    amb = q.mark_projection_exception(
        company_code=company,
        kind="ambiguous_punch_order",
        employee_key=f"{company}-ATTW2E-{tag}",
        work_date="2026-08-25",
        projection={"status": "ambiguous"},
        connector_id=cid,
    )
    check("missing/ambiguous enqueued", miss["ok"] and amb["ok"])
    excluded = q.payroll_excluded_open(company)
    check(
        "missing/ambiguous payroll excluded",
        any(i["kind"] == "missing_check_out" and i["payroll_excluded"] for i in excluded)
        and any(i["kind"] == "ambiguous_punch_order" and i["payroll_excluded"] for i in excluded),
        excluded,
    )

    health = ops.upsert_health_from_agent(
        connector_id=cid,
        company_code=company,
        agent_health={"status": "offline", "error_count": 2, "last_error": "lab_timeout"},
    )
    check("offline health", health["ok"] and health["health"]["status"] == "offline", health)
    lag = ops.upsert_health_from_agent(
        connector_id=cid,
        company_code=company,
        agent_health={"status": "ok", "lag_seconds": 2000, "last_sync_at": "2026-08-25T09:00:00+03:00"},
    )
    check("lag alert", "connector_lag_critical" in (lag.get("health") or {}).get("alerts", []), lag)
    recovered = ops.get_health().mark_recovered(cid)
    check("health recovery", recovered is not None and recovered.status == "online", recovered.to_dict() if recovered else None)

    rej = q.enqueue(
        company_code=company,
        kind="duplicate_conflict",
        connector_id=cid,
        payload={"x": 1},
        idempotency_key=f"w2e-dup-{tag}",
    )
    r1 = q.reject(rej["item"]["item_id"], expected_row_version=rej["item"]["row_version"], actor_phone=manager, actor_company=company)
    r2 = q.reject(rej["item"]["item_id"], expected_row_version=r1["item"]["row_version"], actor_phone=manager, actor_company=company)
    check("reject idempotent", r1["ok"] and r2["ok"] and r2.get("duplicate") is True, {"r1": r1, "r2": r2})

    overview = ops.overview(company)
    check("overview lists connectors", overview["ok"] and len(overview["connectors"]) >= 1, overview["counts"])

    # demo rows untouched
    with app.db_connect() as conn_db:
        with conn_db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            n = int(cur.fetchone()["n"])
    check("attendance demo rows untouched", n == 42, n)

    evid = os.environ.get("ATTW2E_EVID")
    if evid:
        scan = scan_paths([evid])
        qgate = qualify_or_block(scan)
        check("evidence leak scan pass", qgate.get("ok") is True, qgate)

    out = {"pass": PASS, "fail": FAIL, "results": RESULTS}
    print(json.dumps({"pass": PASS, "fail": FAIL}, indent=2))
    out_path = os.environ.get("ATTW2E_RESULTS")
    if out_path:
        from attendance_capture_secrets import redact_text

        open(out_path, "w", encoding="utf-8").write(redact_text(json.dumps(out, indent=2, default=str)))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
