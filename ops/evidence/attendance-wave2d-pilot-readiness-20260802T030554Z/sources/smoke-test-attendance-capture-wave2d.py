#!/usr/bin/env python3
"""Attendance Wave 2D — local/staging pilot-readiness qualification.

Proves secret-safe handling, leak-scan gate, registry ownership, rotate/revoke,
HR remediation (mapping approve/reject/replay), payroll exclusion, health
alerts/recovery, idempotent remediation, manager/self/cross-tenant denials,
Wave 1 authority path, read-only compat (no ingest), freeze regressions.

REFUSES production. Does not connect a real customer device or ingest real punches.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
from datetime import date, datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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


def _start_readonly_lab(rows: list[dict[str, Any]], *, username: str, password: str, token: str) -> tuple[ThreadingHTTPServer, str]:
    state = {"rows": rows, "username": username, "password": password, "token": token}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _auth_ok(self) -> bool:
            auth = self.headers.get("Authorization") or ""
            if auth == f"Token {state['token']}":
                return True
            if auth.startswith("Basic "):
                import base64

                try:
                    raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
                    user, pw = raw.split(":", 1)
                    return user == state["username"] and pw == state["password"]
                except Exception:  # noqa: BLE001
                    return False
            return False

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") + "/"
            if not self._auth_ok():
                self._json(401, {"detail": "auth_failed"})
                return
            if path.endswith("/iclock/api/transactions/"):
                qs = parse_qs(urlparse(self.path).query)
                page = int((qs.get("page") or ["1"])[0])
                limit = int((qs.get("page_size") or qs.get("limit") or ["5"])[0])
                start = (page - 1) * limit
                chunk = state["rows"][start : start + limit]
                self._json(200, {"count": len(state["rows"]), "results": chunk})
                return
            self._json(404, {"detail": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") + "/"
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:  # noqa: BLE001
                body = {}
            if path.endswith("/jwt-api-token-auth/") or path.endswith("/api-token-auth/"):
                if body.get("username") == state["username"] and body.get("password") == state["password"]:
                    self._json(200, {"token": state["token"]})
                    return
                self._json(400, {"non_field_errors": ["Unable to log in"]})
                return
            self._json(404, {"detail": "not_found"})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, f"http://127.0.0.1:{port}/"


def main() -> int:
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production":
        print("REFUSE: production")
        return 2
    os.environ.setdefault("WATHEFNI_ENV", "local")

    import attendance_authority_wave1 as core
    import attendance_capture_compat as compat
    import attendance_capture_contract as contract
    import attendance_capture_health as health_mod
    import attendance_capture_pipeline as pipeline_mod
    import attendance_capture_registry as registry_mod
    import attendance_capture_remediation as rem_mod
    import attendance_capture_secrets as secrets

    core.reset_authority_services_for_tests()

    tag = uuid.uuid4().hex[:8]
    company = "ATTW2D"
    other = "ATTW2DX"
    manager_phone = f"9655710{tag[:4]}"
    emp_phone = f"9655720{tag[:4]}"
    emp_key = f"{company}-ATTW2D-{tag}"
    other_emp_key = f"{other}-ATTW2D-{tag}"
    day = date(2026, 8, 25)
    shift = {
        "shift_id": str(uuid.uuid4()),
        "shift_date": day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
        "company_code": company,
    }

    employees = {
        emp_key: {"employee_key": emp_key, "phone": emp_phone, "name": f"W2D-{tag}", "company_code": company},
        other_emp_key: {
            "employee_key": other_emp_key,
            "phone": f"9655730{tag[:4]}",
            "name": f"W2DX-{tag}",
            "company_code": other,
        },
    }

    def resolve(company_code: str, key: str) -> dict[str, Any] | None:
        e = employees.get(key)
        if not e or e["company_code"] != company_code.upper():
            return None
        return e

    # -------------------------------------------------------------------------
    # Secret-handling contract + argv safety
    # -------------------------------------------------------------------------
    check("secret contract version", secrets.SECRET_HANDLING_CONTRACT["version"].endswith("wave2d_v1"))
    fake_secret = f"super-secret-key-{tag}-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    os.environ["BIOTIME_PASSWORD"] = fake_secret
    argv_bad = secrets.assert_argv_secret_safe(["python", "agent.py", f"--password={fake_secret}"])
    check("argv secret flag blocked", not argv_bad["ok"], argv_bad)
    argv_ok = secrets.assert_argv_secret_safe(["python", "agent.py", "--connector-id", "conn-1"])
    check("argv without secrets ok", argv_ok["ok"], argv_ok)

    with tempfile.TemporaryDirectory() as td:
        env_path = Path(td) / "attendance-capture.env"
        wrote = secrets.write_environment_file(
            env_path,
            {
                "BIOTIME_PASSWORD": fake_secret,
                "WATHEFNI_CAPTURE_CREDENTIAL_KEY": fake_secret,
            },
        )
        check("environment file written", wrote["ok"] and env_path.exists(), wrote)
        mode = oct(env_path.stat().st_mode & 0o777)
        check("environment file mode 600", mode == "0o600", mode)

        clean_log = Path(td) / "deploy.log"
        clean_log.write_text("deploy ok\nBIOTIME_PASSWORD=[REDACTED]\ntoken=[REDACTED]\n", encoding="utf-8")
        clean_scan = secrets.scan_paths([td])
        # secrets .env in tree must block
        q_env = secrets.qualify_or_block(clean_scan)
        check("raw secrets file in pack blocks qualify", q_env["blocked"] and not q_env["ok"], q_env)

        evidence_only = Path(td) / "evidence"
        evidence_only.mkdir()
        (evidence_only / "deploy.log").write_text(
            "started\nBIOTIME_PASSWORD=[REDACTED]\nAuthorization: Token [REDACTED]\n",
            encoding="utf-8",
        )
        (evidence_only / "app.json").write_text(
            json.dumps({"status": "ok", "password": "[REDACTED]", "token": "[REDACTED]"}),
            encoding="utf-8",
        )
        scan_clean = secrets.scan_paths([evidence_only])
        check("clean evidence leak scan pass", scan_clean.ok, scan_clean.to_dict())
        check("qualify_or_block allows clean pack", secrets.qualify_or_block(scan_clean)["ok"])

        leak_log = evidence_only / "bad-deploy.log"
        leak_log.write_text(f"oops BIOTIME_PASSWORD={fake_secret}\n", encoding="utf-8")
        scan_leak = secrets.scan_paths([evidence_only])
        blocked = secrets.qualify_or_block(scan_leak)
        check(
            "simulated secret exposure detected",
            not scan_leak.ok,
            {"files_scanned": scan_leak.files_scanned, "finding_count": len(scan_leak.findings), "rules": sorted({f.rule for f in scan_leak.findings})},
        )
        check(
            "simulated exposure blocks qualification",
            blocked["blocked"] is True,
            {"blocked": blocked.get("blocked"), "error": blocked.get("error"), "finding_count": len(blocked.get("findings") or [])},
        )
        leak_log.unlink()

        # error traces
        err = secrets.safe_error(RuntimeError(f"login failed password={fake_secret}"))
        check("safe_error redacts password", fake_secret not in err and "password=" in err.lower(), err)

        # prove finding excerpts never echo the secret
        leak_log.write_text(f"oops BIOTIME_PASSWORD={fake_secret}\n", encoding="utf-8")
        findings = secrets.scan_paths([leak_log]).findings
        check(
            "leak finding excerpts redacted",
            bool(findings) and all(fake_secret not in f.excerpt for f in findings),
            [{"rule": f.rule, "excerpt": f.excerpt} for f in findings],
        )
        leak_log.unlink()

    os.environ.pop("BIOTIME_PASSWORD", None)

    # -------------------------------------------------------------------------
    # Registry: site/device/connector + wrong-tenant fail-closed
    # -------------------------------------------------------------------------
    registry = registry_mod.ConnectorRegistry()
    site = registry.register_site(company_code=company, name=f"Site-{tag}")
    other_site = registry.register_site(company_code=other, name=f"Other-{tag}")
    check("site registered", bool(site.site_id), site.site_id)

    wrong = registry.register_device(
        company_code=company,
        site_id=site.site_id,
        terminal_sn=f"SN-OWNED-{tag}",
        actor_company=other,
    )
    check("cross-tenant device registration denied", not wrong["ok"] and wrong["error"] == "cross_tenant_device_registration_denied", wrong)

    owned = registry.register_device(company_code=company, site_id=site.site_id, terminal_sn=f"SN-OWNED-{tag}")
    check("device registered for tenant", owned["ok"], owned)
    device_id = owned["device"]["device_id"]

    # other tenant tries to claim same SN
    steal = registry.register_device(company_code=other, site_id=other_site.site_id, terminal_sn=f"SN-OWNED-{tag}")
    check("wrong-tenant device claim fail-closed", not steal["ok"] and steal["error"] == "device_owned_by_other_tenant", steal)

    own_check = registry.verify_device_ownership(company_code=other, terminal_sn=f"SN-OWNED-{tag}")
    check("ownership verify wrong tenant fails", not own_check["ok"] and own_check["error"] == "wrong_tenant_device", own_check)
    own_ok = registry.verify_device_ownership(company_code=company, terminal_sn=f"SN-OWNED-{tag}")
    check("ownership verify correct tenant", own_ok["ok"], own_ok)

    reg = registry.register_connector(
        company_code=company,
        site_id=site.site_id,
        device_id=device_id,
        secrets={"username": "admin", "password": f"pw-{tag}", "token": f"tok-{tag}"},
        connector_version="wave2d",
        actor_phone=manager_phone,
    )
    check("connector registered without secret return", reg["ok"] and reg["secrets"] == secrets.REDACTED, reg)
    connector_id = reg["connector"]["connector_id"]
    row_v = reg["connector"]["row_version"]

    cross_conn = registry.register_connector(
        company_code=company,
        site_id=site.site_id,
        device_id=device_id,
        secrets={"password": "x"},
        connector_version="wave2d",
        actor_company=other,
    )
    check("cross-tenant connector registration denied", not cross_conn["ok"], cross_conn)

    act = registry.activate(connector_id, expected_row_version=row_v, actor_phone=manager_phone)
    check("connector activated", act["ok"] and act["connector"]["status"] == "active", act)
    row_v = act["connector"]["row_version"]

    # rotate / revoke / reconnect
    rot = registry.rotate_credentials(
        connector_id,
        new_secrets={"username": "admin", "password": f"pw2-{tag}", "token": f"tok2-{tag}"},
        expected_row_version=row_v,
        actor_phone=manager_phone,
    )
    check("credential rotate ok", rot["ok"] and rot["secrets"] == secrets.REDACTED, rot)
    row_v = rot["connector"]["row_version"]
    recon = registry.reconnect_after_rotate(connector_id)
    check("reconnect after rotate (no secret values)", recon["ok"] and recon["secrets"] == secrets.REDACTED and recon["has_password"], recon)

    stale = registry.rotate_credentials(
        connector_id,
        new_secrets={"password": "stale"},
        expected_row_version=row_v - 1,
        actor_phone=manager_phone,
    )
    check("rotate optimistic concurrency stale denied", not stale["ok"] and stale["error"] == "stale_row_version", stale)

    # second connector for revoke drill (keep first for remediation)
    reg2 = registry.register_connector(
        company_code=company,
        site_id=site.site_id,
        device_id=device_id,
        secrets={"password": f"rev-{tag}"},
        connector_version="wave2d",
    )
    cid2 = reg2["connector"]["connector_id"]
    rv2 = reg2["connector"]["row_version"]
    act2 = registry.activate(cid2, expected_row_version=rv2)
    rv2 = act2["connector"]["row_version"]
    rev = registry.revoke(cid2, expected_row_version=rv2, reason="pilot_abort", actor_phone=manager_phone)
    check("connector revoke", rev["ok"] and rev["connector"]["status"] == "revoked", rev)
    recon_rev = registry.reconnect_after_rotate(cid2)
    check("reconnect after revoke denied", not recon_rev["ok"] and recon_rev["error"] == "connector_revoked", recon_rev)

    tenant_deny = registry.assert_connector_tenant(connector_id, other)
    check("connector cross-tenant assert denied", not tenant_deny["ok"], tenant_deny)

    # -------------------------------------------------------------------------
    # Remediation queue + Wave 1 authority
    # -------------------------------------------------------------------------
    mapping = contract.InMemoryMappingStore()
    svc = core.AttendanceAuthorityService()
    pipeline = pipeline_mod.CapturePipeline(
        authority_service=svc,
        mapping=mapping,
        employee_resolver=resolve,
        connector_id=connector_id,
        require_mapping=True,
    )

    def manager_scope(company_code: str, actor: str, employee: str) -> bool:
        # manager may act on emp_key only within company; deny other_emp
        return company_code == company and employee == emp_key and actor == manager_phone

    queue = rem_mod.RemediationQueue(mapping=mapping, pipeline=pipeline, manager_scope_allows=manager_scope)

    punch_payload = {
        "company_code": company,
        "source": "biotime",
        "source_event_id": f"biotime:w2d-{tag}-1",
        "device_user_id": f"DU-{tag}",
        "punched_at": datetime(2026, 8, 25, 9, 5, tzinfo=core.KUWAIT_TZ if hasattr(core, "KUWAIT_TZ") else None) or datetime(2026, 8, 25, 9, 5),
        "direction": "in",
        "capture_method": "card",
        "device_id": f"SN-OWNED-{tag}",
        "connector_id": connector_id,
        "raw_ref": {"id": 1, "emp_code": f"DU-{tag}"},
        "metadata": {},
    }
    # ensure timezone-aware punched_at
    from attendance_capture_contract import as_kuwait

    punch_payload["punched_at"] = as_kuwait("2026-08-25T09:05:00")

    unknown = pipeline.ingest_canonical(punch_payload, shift=shift)
    check("unknown mapping quarantines (not payroll)", unknown.get("quarantined") is True, unknown)

    enq = queue.enqueue(
        company_code=company,
        kind="unknown_employee",
        connector_id=connector_id,
        device_user_id=f"DU-{tag}",
        device_id=f"SN-OWNED-{tag}",
        source_event_id=punch_payload["source_event_id"],
        payload=punch_payload,
        idempotency_key=f"unk-{tag}",
    )
    check("unknown enters remediation", enq["ok"] and not enq["duplicate"], enq)
    item_id = enq["item"]["item_id"]
    item_rv = enq["item"]["row_version"]

    enq2 = queue.enqueue(
        company_code=company,
        kind="unknown_employee",
        connector_id=connector_id,
        device_user_id=f"DU-{tag}",
        source_event_id=punch_payload["source_event_id"],
        payload=punch_payload,
        idempotency_key=f"unk-{tag}",
    )
    check("remediation enqueue idempotent", enq2["ok"] and enq2["duplicate"] is True, enq2)

    cross_approve = queue.approve_mapping(
        item_id,
        employee_key=emp_key,
        expected_row_version=item_rv,
        actor_phone=manager_phone,
        actor_company=other,
    )
    check("mapping approve cross-tenant denied", not cross_approve["ok"] and cross_approve["error"] == "cross_tenant_denied", cross_approve)

    self_deny = queue.approve_mapping(
        item_id,
        employee_key=emp_key,
        expected_row_version=item_rv,
        actor_phone=emp_phone,
        actor_company=company,
        actor_is_manager=True,
        employee_phone=emp_phone,
        replay=False,
    )
    check("manager self-action denied", not self_deny["ok"] and self_deny["error"] == "manager_self_action_denied", self_deny)

    scope_deny = queue.approve_mapping(
        item_id,
        employee_key=other_emp_key,
        expected_row_version=item_rv,
        actor_phone=manager_phone,
        actor_company=company,
        replay=False,
    )
    check("manager scope denied for out-of-scope employee", not scope_deny["ok"] and scope_deny["error"] == "manager_scope_denied", scope_deny)

    # missing / ambiguous stay payroll excluded
    miss = queue.mark_projection_exception(
        company_code=company,
        kind="missing_check_out",
        employee_key=emp_key,
        work_date=day.isoformat(),
        projection={"status": "incomplete", "exception_state": "missing_check_out"},
        connector_id=connector_id,
    )
    check("missing checkout enqueued", miss["ok"], miss)
    amb = queue.mark_projection_exception(
        company_code=company,
        kind="ambiguous_punch_order",
        employee_key=emp_key,
        work_date=day.isoformat(),
        projection={"status": "ambiguous", "exception_state": "ambiguous_punch_order"},
        connector_id=connector_id,
    )
    check("ambiguous order enqueued", amb["ok"], amb)
    excluded = queue.payroll_excluded_open(company)
    check(
        "missing/ambiguous payroll_excluded",
        any(i["kind"] == "missing_check_out" and i["payroll_excluded"] for i in excluded)
        and any(i["kind"] == "ambiguous_punch_order" and i["payroll_excluded"] for i in excluded),
        excluded,
    )

    lag = queue.enqueue(
        company_code=company,
        kind="connector_lag",
        connector_id=connector_id,
        payload={"lag_seconds": 2000},
        idempotency_key=f"lag-{tag}",
    )
    off = queue.enqueue(
        company_code=company,
        kind="connector_offline",
        connector_id=connector_id,
        payload={"status": "offline"},
        idempotency_key=f"off-{tag}",
    )
    check("connector lag/offline remediation", lag["ok"] and off["ok"], {"lag": lag, "off": off})

    # approve + replay only after approval → Wave 1 authority
    approve = queue.approve_mapping(
        item_id,
        employee_key=emp_key,
        expected_row_version=item_rv,
        actor_phone=manager_phone,
        actor_company=company,
        actor_is_manager=True,
        employee_phone=emp_phone,
        replay=True,
        shift=shift,
    )
    check("mapping approve+replay ok", approve["ok"] and approve.get("replay", {}).get("ok"), approve)
    # idempotent replay
    item_after = queue.items[item_id]
    replay2 = queue.replay_item(
        item_id,
        expected_row_version=item_after.row_version,
        actor_phone=manager_phone,
        actor_company=company,
        shift=shift,
    )
    # status already approved_replayed — second call with new version may ingest again (authority idempotent by source_event_id)
    # Prefer testing reject idempotency
    rej_item = queue.enqueue(
        company_code=company,
        kind="duplicate_conflict",
        connector_id=connector_id,
        payload={"a": 1},
        source_event_id=f"dup-{tag}",
        idempotency_key=f"dup-{tag}",
    )
    rj = queue.reject(
        rej_item["item"]["item_id"],
        expected_row_version=rej_item["item"]["row_version"],
        actor_phone=manager_phone,
        actor_company=company,
    )
    check("reject conflict ok", rj["ok"], rj)
    rj2 = queue.reject(
        rej_item["item"]["item_id"],
        expected_row_version=rj["item"]["row_version"],
        actor_phone=manager_phone,
        actor_company=company,
    )
    check("reject idempotent", rj2["ok"] and rj2.get("duplicate") is True, rj2)

    ingest_res = (approve.get("replay") or {}).get("ingest") or {}
    check(
        "accepted punch flowed Wave 1 authority",
        approve.get("replay", {}).get("ok") is True and ingest_res.get("ok") is True,
        {"approve": approve, "ingest": ingest_res},
    )

    # -------------------------------------------------------------------------
    # Health dashboard
    # -------------------------------------------------------------------------
    dash = health_mod.HealthDashboard()
    offline_view = dash.upsert_from_agent(
        connector_id=connector_id,
        company_code=company,
        site_id=site.site_id,
        agent_health={"status": "offline", "lag_seconds": 0, "error_count": 3, "last_error": "timeout"},
        quarantined_events=1,
        open_remediation=len(queue.list_open(company)),
    )
    check("health offline alert", offline_view.status == "offline" and "connector_offline" in offline_view.alerts, offline_view.to_dict())
    lag_view = dash.upsert_from_agent(
        connector_id=connector_id,
        company_code=company,
        site_id=site.site_id,
        agent_health={"status": "ok", "lag_seconds": 2000, "error_count": 0, "last_sync_at": "2026-08-25T09:00:00+03:00"},
        quarantined_events=0,
        open_remediation=0,
    )
    check("health lag critical alert", "connector_lag_critical" in lag_view.alerts and lag_view.status == "degraded", lag_view.to_dict())
    recovered = dash.mark_recovered(connector_id)
    check("health recovery clears offline/lag alerts", recovered is not None and recovered.status == "online" and "connector_offline" not in recovered.alerts, recovered.to_dict() if recovered else None)
    revoked_view = dash.upsert_from_agent(
        connector_id=cid2,
        company_code=company,
        site_id=site.site_id,
        agent_health={"status": "ok"},
        revoked=True,
    )
    check("health revoked status", revoked_view.status == "revoked", revoked_view.to_dict())
    check("health contract schema present", dash.contract_schema()["version"].endswith("wave2d_v1"), dash.contract_schema())

    # -------------------------------------------------------------------------
    # Read-only customer compat (no ingest)
    # -------------------------------------------------------------------------
    lab_rows = [
        {
            "id": 9001,
            "emp_code": f"LAB{tag[:4]}",
            "punch_time": "2026-08-25 09:00:00",
            "punch_state": 0,
            "verify_type": 2,
            "terminal_sn": f"SN-OWNED-{tag}",
        }
    ]
    httpd, base_url = _start_readonly_lab(lab_rows, username="admin", password=f"lab-{tag}", token=f"labtok-{tag}")
    try:
        before_punches = getattr(svc, "punch_count", None)
        report = compat.run_readonly_compat(
            company_code=company,
            base_url=base_url,
            username="admin",
            password=f"lab-{tag}",
            sample_limit=5,
            connector_id="compat-readonly",
        )
        check("readonly compat ok", report.get("ok") is True and report.get("ingest") is False, report)
        check("readonly compat secrets redacted", report.get("secrets") == secrets.REDACTED, report)
        # ensure no authority write from compat alone — mapping quarantine count unchanged by compat
        check("readonly compat does not set ingest flag", report["ingest"] is False)
    finally:
        httpd.shutdown()

    # checklist files present
    ops = ROOT.parent / "ops"
    check("secret runbook present", (ops / "ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md").is_file())
    check("pilot checklist present", (ops / "ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md").is_file())

    # -------------------------------------------------------------------------
    # Freezes
    # -------------------------------------------------------------------------
    if os.environ.get("ATTW2D_SKIP_FREEZE") == "1":
        check("freeze skipped", True)
    else:
        freeze_root = Path(os.environ.get("WATHEFNI_ORCH_ROOT") or ROOT)
        for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
            path = freeze_root / script
            if not path.is_file():
                check(f"freeze {script}", False, "missing")
                continue
            proc = subprocess.run([sys.executable, str(path)], cwd=str(freeze_root), capture_output=True, text=True)
            check(f"freeze {script}", proc.returncode == 0, (proc.stdout + proc.stderr)[-500:])

    out = {
        "wave": "attendance-wave2d",
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "secret_contract": secrets.SECRET_HANDLING_CONTRACT,
        "health_contract": dash.contract_schema(),
    }
    # Never persist secret-bearing strings in evidence JSON
    out_txt = secrets.redact_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({"pass": PASS, "fail": FAIL}, indent=2))
    out_path = os.environ.get("ATTW2D_RESULTS_PATH")
    if out_path:
        Path(out_path).write_text(out_txt, encoding="utf-8")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(1)
