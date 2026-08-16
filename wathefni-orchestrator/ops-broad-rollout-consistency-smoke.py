#!/usr/bin/env python3
"""Read-only consistency smoke across representative employees.

For each employee, reads HR queue, HR drawer, employee app, and employee
profile (when an app session can be minted) and asserts the same
completion state / progress / next-action owner.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

for line in Path("/tmp/orch-environ.env").read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k, v)

import app as A  # noqa: E402

COMPANY = "WATHEFNI"
AZIZ = "WATHEFNI-96599338566"
TALAL = "WATHEFNI-96550252254"
OUT = Path(os.environ.get("OUT_PATH") or "/tmp/broad-consistency-smoke.json")
RESULTS: dict[str, Any] = {"employees": [], "checks": [], "failed": 0}


def check(name: str, ok: bool, detail: Any = None) -> bool:
    RESULTS["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        RESULTS["failed"] += 1
    print(("PASS" if ok else "FAIL"), name, "::", json.dumps(detail, default=str)[:500])
    return bool(ok)


def http(method: str, path: str, *, token: str | None = None, hr_token: str | None = None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if hr_token:
        headers["X-Dashboard-Token"] = hr_token
        headers["Authorization"] = f"Bearer {hr_token}"
    req = urllib.request.Request(
        f"http://127.0.0.1:8010{path}", method=method, headers=headers, data=None
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        return e.code, detail


def mint_employee(key: str) -> str | None:
    try:
        emp = A.find_employee_by_key(key, company_code=COMPANY)
        if not emp:
            return None
        return str(A.create_employee_session(COMPANY, key, str(emp.get("phone")))["token"])
    except Exception as e:
        RESULTS.setdefault("mint_errors", []).append({"key": key, "error": str(e)})
        return None


def mint_hr() -> str:
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s
                  AND lower(coalesce(role,'')) IN ('owner','admin','hr_admin','hr')
                ORDER BY created_at LIMIT 1
                """,
                (COMPANY,),
            )
            hr_user = dict(cur.fetchone() or {})
        conn.commit()
    return str(A.create_dashboard_session(hr_user)[0]), hr_user


def _owner(payload: dict[str, Any], *, from_queue: bool = False) -> str | None:
    if from_queue:
        if payload.get("next_owner"):
            return str(payload.get("next_owner"))
        return str((payload.get("completion_next_action") or {}).get("owner") or "") or None
    action = payload.get("next_action") or (payload.get("completion") or {}).get("next_action") or {}
    return str(action.get("owner") or "") or None


def surface_tuple(state, satisfied, required, owner) -> dict[str, Any]:
    return {
        "state": str(state or "") or None,
        "satisfied": int(satisfied or 0) if satisfied is not None else None,
        "required": int(required or 0) if required is not None else None,
        "owner": str(owner or "") or None,
    }


def read_surfaces(key: str, *, hr_token: str, emp_token: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"employee_key": key}
    code_q, queue = http("GET", "/dashboard/posthire/onboarding?limit=500", hr_token=hr_token)
    row = None
    if isinstance(queue, dict):
        for bucket in ("in_progress", "completed", "not_started", "employees", "items"):
            for r in queue.get(bucket) or []:
                if r.get("employee_key") == key:
                    row = r
                    break
            if row:
                break
        if row is None:
            # Some payloads nest under data
            for r in (queue.get("data") or []) if isinstance(queue.get("data"), list) else []:
                if r.get("employee_key") == key:
                    row = r
                    break
    if row is None:
        out["hr_queue"] = {
            "http": code_q,
            "absent_from_queue": True,
            **surface_tuple("completed_or_absent", 0, 0, None),
        }
    else:
        out["hr_queue"] = {
            "http": code_q,
            "absent_from_queue": False,
            **surface_tuple(
                row.get("completion_state"),
                row.get("satisfied_count"),
                row.get("required_total") or row.get("open_count"),
                _owner(row, from_queue=True),
            ),
            "next_item_label": row.get("next_item_label"),
            "completion_next_action": row.get("completion_next_action"),
        }

    code_d, drawer = http("GET", f"/dashboard/posthire/onboarding/{key}", hr_token=hr_token)
    completion = (drawer.get("completion") or {}) if isinstance(drawer, dict) else {}
    out["hr_drawer"] = {
        "http": code_d,
        **surface_tuple(
            completion.get("state"),
            completion.get("satisfied_count"),
            completion.get("required_total"),
            _owner({"completion": completion, "next_action": completion.get("next_action")}),
        ),
        "next_action": completion.get("next_action"),
    }

    if emp_token:
        code_a, app_body = http("GET", "/app/onboarding", token=emp_token)
        c = (app_body.get("completion") or {}) if isinstance(app_body, dict) else {}
        out["employee_app"] = {
            "http": code_a,
            **surface_tuple(
                c.get("state"),
                c.get("satisfied_count"),
                c.get("required_total"),
                _owner({"completion": c, "next_action": c.get("next_action") or app_body.get("next_action")}),
            ),
            "next_action": c.get("next_action") or (app_body.get("next_action") if isinstance(app_body, dict) else None),
        }
        code_p, profile = http("GET", "/app/profile", token=emp_token)
        onb = (profile.get("onboarding") or {}) if isinstance(profile, dict) else {}
        pc = onb.get("completion") or {}
        out["employee_profile"] = {
            "http": code_p,
            **surface_tuple(
                pc.get("state") or onb.get("completion_state"),
                pc.get("satisfied_count"),
                pc.get("required_total"),
                _owner({"completion": pc, "next_action": onb.get("next_action") or pc.get("next_action")}),
            ),
        }
        code_b, bank = http("GET", "/app/bank", token=emp_token)
        out["bank"] = {"http": code_b, "detail": bank if code_b >= 400 else {"ok": True}}
    else:
        out["employee_app"] = None
        out["employee_profile"] = None
        out["bank"] = None
    return out


def agree(surfaces: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Compare state/owner across available surfaces. Progress uses drawer as authority for required_total."""
    drawer = surfaces.get("hr_drawer") or {}
    app = surfaces.get("employee_app") or {}
    profile = surfaces.get("employee_profile") or {}
    queue = surfaces.get("hr_queue") or {}

    cores = []
    for name, s in (("drawer", drawer), ("app", app), ("profile", profile)):
        if not s:
            continue
        cores.append((name, s.get("state"), s.get("satisfied"), s.get("required"), s.get("owner")))

    if len(cores) < 2:
        return False, {"reason": "not_enough_surfaces", "cores": cores}

    base = cores[0][1:]
    mismatches = []
    for name, state, sat, req, owner in cores[1:]:
        if (state, sat, req, owner) != base:
            mismatches.append({"name": name, "got": (state, sat, req, owner), "want": base})

    # Queue: when present and enriched, state + owner must match. An unenriched
    # queue row (null completion_state) is a listing artifact for employees who
    # are not yet on the still-onboarding contract path — drawer/app/profile are
    # the authority in that case.
    if queue and not queue.get("absent_from_queue") and queue.get("state") is not None:
        if queue.get("state") != drawer.get("state") or queue.get("owner") != drawer.get("owner"):
            mismatches.append(
                {
                    "name": "queue",
                    "got": (queue.get("state"), queue.get("owner")),
                    "want": (drawer.get("state"), drawer.get("owner")),
                }
            )
        if (
            queue.get("satisfied") not in (None, drawer.get("satisfied"))
            and drawer.get("state") != "completed"
            and queue.get("satisfied") != drawer.get("satisfied")
        ):
            mismatches.append(
                {
                    "name": "queue_satisfied",
                    "got": queue.get("satisfied"),
                    "want": drawer.get("satisfied"),
                }
            )

    return len(mismatches) == 0, {
        "cores": cores,
        "mismatches": mismatches,
        "queue": queue,
        "queue_unenriched": bool(queue and not queue.get("absent_from_queue") and queue.get("state") is None),
    }


def pick_representatives() -> list[str]:
    keys = [AZIZ, TALAL]
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.employee_key, c.state
                FROM employee_onboarding_completion c
                WHERE c.company_code=%s
                ORDER BY c.state, c.employee_key
                """,
                (COMPANY,),
            )
            by_state: dict[str, list[str]] = {}
            for r in cur.fetchall() or []:
                by_state.setdefault(str(r["state"]), []).append(str(r["employee_key"]))
        conn.commit()
    for state in (
        "completed",
        "waiting_on_employee",
        "waiting_on_hr",
        "reopened",
        "in_progress",
        "not_started",
    ):
        for key in by_state.get(state, [])[:2]:
            if key not in keys:
                keys.append(key)
    # Always include Fouad if present (real HR-adjacent employee).
    if "WATHEFNI-96566363363" not in keys:
        keys.append("WATHEFNI-96566363363")
    return keys[:12]


def main() -> int:
    RESULTS["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    hr_token, hr_user = mint_hr()
    RESULTS["hr"] = {"email": hr_user.get("email"), "role": hr_user.get("role")}
    keys = pick_representatives()
    RESULTS["keys"] = keys

    for key in keys:
        token = mint_employee(key)
        surfaces = read_surfaces(key, hr_token=hr_token, emp_token=token)
        RESULTS["employees"].append(surfaces)
        ok, detail = agree(surfaces)
        check(f"{key}: surfaces agree", ok, detail)
        if key == TALAL:
            bank = surfaces.get("bank") or {}
            check(
                "Talal bank still 403 after rollout",
                bank.get("http") == 403,
                bank,
            )
        if key == AZIZ:
            bank = surfaces.get("bank") or {}
            check("Aziz bank still reachable", bank.get("http") == 200, {"http": bank.get("http")})

    OUT.write_text(json.dumps(RESULTS, indent=2, default=str))
    print("SMOKE_OK" if RESULTS["failed"] == 0 else "SMOKE_FAILED")
    print("wrote", OUT)
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
