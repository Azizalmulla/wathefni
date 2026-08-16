#!/usr/bin/env python3
"""Seed disposable Bank ESS visual fixtures for Employee App QA.

Targets (canary fixtures only — Aziz/Talal never touched):
  WATHEFNI-96550010001  Noura — applied/effective + pending_hr change
  WATHEFNI-9655497001   synth — pending_payroll
  WATHEFNI-9655497002   synth — needs_correction
  WATHEFNI-9655497003   synth — clean applied/effective

Uses the live sealed Bank ESS HTTP path (employee submit + HR decide/apply).
All fixture display values carry TAG so cleanup can revoke/supersede safely
without touching non-fixture production bank facts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request as urlrequest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _pds  # noqa: E402

_pds.activate_fixture_tooling_from_argv()
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")
# Mirror production allowlists so in-process session minting matches the live service.
os.environ.setdefault(
    "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST",
    ",".join(
        [
            "WATHEFNI-96550010001",
            "WATHEFNI-96550010002",
            "WATHEFNI-96550010003",
            "WATHEFNI-96550010004",
            "WATHEFNI-96550010005",
            "WATHEFNI-96550010006",
            "WATHEFNI-96550010009",
            "WATHEFNI-96550010010",
            "WATHEFNI-96550252254",
            "WATHEFNI-9655497001",
            "WATHEFNI-9655497002",
            "WATHEFNI-9655497003",
            "WATHEFNI-96566363363",
            "WATHEFNI-96588721142",
            "WATHEFNI-96597727743",
            "WATHEFNI-96599338566",
            "WATHEFNI-96599411617",
        ]
    ),
)
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST", "on")
os.environ.setdefault("WATHEFNI_BANK_ESS_V1", "on")
os.environ.setdefault("WATHEFNI_BANK_ESS_V1_COMPANIES", "WATHEFNI")
os.environ.setdefault(
    "WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST",
    os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST")
    or "",
)

import app as legacy  # noqa: E402
import employee_bank_ess as bank  # noqa: E402

COMPANY = os.environ["WATHEFNI_COMPANY_CODE"]
TAG = "bank-visual-fixture"
STAMP = os.environ.get("BANK_VISUAL_STAMP") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
BASE = os.environ.get("WATHEFNI_QUAL_BASE", "http://127.0.0.1:8010")
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}

# Distinct valid KW IBANs (mod-97 checked) — never reuse across employees in one seed.
IBANS = {
    "noura_applied": "KW81CBKU0000000000001234560101",
    "noura_change": "KW16NBOK0000000000001234560101",
    "7001_applied": "KW70CBKU0000000000001234560202",
    "7001_change": "KW20CBKU0000000000009876540101",
    "7002_change": "KW94CBKU0000000000001111222233",
    "7003_applied": "KW66GULB0000000000001234560101",
}

FIXTURE_BANK = "Visual Fixture Bank"
HOLDER_PREFIX = "Visual Fixture"
SYNTH_NAME_PREFIX = "W5C-SYNTH|"

SCENARIOS: dict[str, dict[str, Any]] = {
    "WATHEFNI-96550010001": {
        "role": "noura_effective_plus_pending_hr",
        "phone": "96550010001",
        "create_if_missing": False,
        "name": None,
    },
    "WATHEFNI-9655497001": {
        "role": "pending_payroll",
        "phone": "9655497001",
        "create_if_missing": True,
        "name": f"{SYNTH_NAME_PREFIX} Bank Visual 7001",
    },
    "WATHEFNI-9655497002": {
        "role": "needs_correction",
        "phone": "9655497002",
        "create_if_missing": True,
        "name": f"{SYNTH_NAME_PREFIX} Bank Visual 7002",
    },
    "WATHEFNI-9655497003": {
        "role": "applied_clean",
        "phone": "9655497003",
        "create_if_missing": True,
        "name": f"{SYNTH_NAME_PREFIX} Bank Visual 7003",
    },
}


def _guard_keys(keys: list[str]) -> None:
    for key in keys:
        if key in PROTECTED:
            raise SystemExit(f"refusing protected canary key {key}")


def _is_fixture_display(display: Any) -> bool:
    d = display if isinstance(display, dict) else {}
    holder = str(d.get("account_holder") or "")
    bank_name = str(d.get("bank_name") or "")
    return TAG in holder or TAG in bank_name or HOLDER_PREFIX in holder or bank_name == FIXTURE_BANK


def _http(
    method: str,
    path: str,
    *,
    token: str | None = None,
    dashboard_token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if dashboard_token:
        headers["Authorization"] = f"Bearer {dashboard_token}"
    req = urlrequest.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlrequest.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw[:400]}
        return int(exc.code), parsed


def _employee_token(key: str) -> str:
    emp = legacy.find_employee_by_key(key, company_code=COMPANY)
    if not emp:
        raise RuntimeError(f"missing employee {key}")
    phone = str(emp.get("phone") or "")
    return str(legacy.create_employee_session(COMPANY, key, phone)["token"])


def _hr_token() -> str:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s
                  AND lower(coalesce(role,'')) IN ('owner','admin','hr_admin','hr')
                ORDER BY created_at
                LIMIT 1
                """,
                (COMPANY,),
            )
            row = dict(cur.fetchone() or {})
        conn.commit()
    if not row:
        raise SystemExit("no HR dashboard user available")
    return str(legacy.create_dashboard_session(row)[0])


def _ensure_synth_employee(key: str, phone: str, name: str) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (
                  company_code, employee_key, phone, name,
                  onboarding_status, employment_status, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,'not_started','active',now(),now())
                ON CONFLICT (employee_key) DO UPDATE
                SET phone=EXCLUDED.phone,
                    name=EXCLUDED.name,
                    updated_at=now()
                """,
                (COMPANY, key, phone, name),
            )
        conn.commit()
    emp = legacy.find_employee_by_key(key, company_code=COMPANY) or {}
    if not emp.get("app_access_enabled"):
        import employee_app_access as access

        access.set_employee_app_access(
            legacy,
            {
                "company_code": COMPANY,
                "user_id": TAG,
                "actor_user_id": TAG,
                "email": f"{TAG}@wathefni.ai",
                "permissions": ["employees.manage", "onboarding.manage"],
            },
            employee_key=key,
            enabled=True,
            reason=TAG,
            deliver_invite=False,
        )
        emp = legacy.find_employee_by_key(key, company_code=COMPANY) or emp
    return emp


def _withdraw_active(token: str) -> dict[str, Any]:
    code, body = _http("GET", "/app/bank", token=token)
    if code != 200:
        return {"ok": False, "http": code}
    sub = body.get("submission") or {}
    rid = sub.get("request_id")
    state = str(body.get("submission_state") or "")
    if not rid or state in {"", "none", "applied", "rejected", "withdrawn"}:
        return {"ok": True, "cleared": False, "state": state}
    # Only withdraw fixture-shaped submissions.
    display = ((sub.get("proposed") or {}).get("display")) or {}
    if not _is_fixture_display(display) and HOLDER_PREFIX not in json.dumps(body, default=str):
        return {"ok": True, "cleared": False, "state": state, "skipped_non_fixture": True}
    wcode, _ = _http("POST", f"/app/bank/requests/{rid}/withdraw", token=token)
    return {"ok": wcode == 200, "cleared": wcode == 200, "state": state, "request_id": rid}


def _submit(
    token: str,
    *,
    iban: str,
    holder: str,
    bank_name: str = FIXTURE_BANK,
) -> tuple[str | None, dict[str, Any]]:
    code, body = _http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={
            "iban": iban,
            "bank_name": bank_name,
            "account_holder": holder,
            "idempotency_key": f"{TAG}-{uuid.uuid4().hex[:10]}",
        },
    )
    bank_body = body.get("bank") if isinstance(body, dict) else None
    rid = (((bank_body or {}).get("submission") or {}) or {}).get("request_id")
    return (str(rid) if rid else None), {"http": code, "state": (bank_body or {}).get("submission_state"), "body": body}


def _concurrency(rid: str) -> int:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT concurrency_version FROM employee_ess_requests WHERE request_id=%s",
                (rid,),
            )
            row = dict(cur.fetchone() or {})
        conn.commit()
    return int(row.get("concurrency_version") or 0)


def _hr_decide(hr: str, rid: str, action: str, comment: str) -> tuple[int, Any]:
    return _http(
        "POST",
        f"/dashboard/posthire/employee-ess/requests/{rid}/decide",
        dashboard_token=hr,
        body={
            "action": action,
            "comment": comment,
            "expected_concurrency_version": _concurrency(rid),
        },
    )


def _hr_apply(hr: str, rid: str) -> tuple[int, Any]:
    return _http(
        "POST",
        f"/dashboard/posthire/employee-ess/requests/{rid}/apply",
        dashboard_token=hr,
        body={"idempotency_key": f"{TAG}-apply-{rid}"},
    )


def _approve_through_apply(hr: str, rid: str, comment: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    code, body = _hr_decide(hr, rid, "approve", comment)
    steps.append({"decide_hr": code, "state": (body.get("request") or body).get("state") if isinstance(body, dict) else None})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM employee_ess_requests WHERE request_id=%s", (rid,))
            state = str(dict(cur.fetchone() or {}).get("state") or "")
        conn.commit()
    if state == "pending_payroll":
        code2, body2 = _hr_decide(hr, rid, "approve", f"{comment} · payroll")
        steps.append({"decide_payroll": code2})
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM employee_ess_requests WHERE request_id=%s", (rid,))
                state = str(dict(cur.fetchone() or {}).get("state") or "")
            conn.commit()
    if state == "approved":
        code3, body3 = _hr_apply(hr, rid)
        steps.append({"apply": code3, "body": body3})
    return {"final_state": state, "steps": steps}


def cleanup(keys: list[str] | None = None) -> dict[str, Any]:
    targets = list(keys or SCENARIOS.keys())
    _guard_keys(targets)
    removed: dict[str, Any] = {"keys": targets, "actions": []}
    try:
        purge = legacy.purge_bank_evidence_bytes(company_code=COMPANY, employee_keys=targets)
        removed["evidence_files"] = purge
    except Exception as exc:
        removed["evidence_files_error"] = str(exc)[:200]

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            bank.ensure_bank_ess_schema(cur)
            for key in targets:
                # Withdraw/close active fixture requests via state update is unsafe;
                # mark rejected only when display is fixture-tagged.
                cur.execute(
                    """
                    SELECT request_id::text, state, proposed_values
                    FROM employee_ess_requests
                    WHERE company_code=%s AND employee_key=%s
                      AND request_type='bank_detail_change'
                      AND state = ANY(%s)
                    """,
                    (COMPANY, key, list(bank.ACTIVE_REQUEST_STATES)),
                )
                for row in cur.fetchall() or []:
                    r = dict(row)
                    # proposed_values is sealed — rely on verified/effective display + holder TAG
                    # via a soft withdraw using employee session below if needed.
                    removed["actions"].append({"active_seen": r.get("request_id"), "state": r.get("state"), "key": key})

                cur.execute(
                    """
                    UPDATE employee_bank_effective
                    SET superseded_at=COALESCE(superseded_at, now())
                    WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
                      AND (
                        COALESCE(display->>'bank_name','') = %s
                        OR COALESCE(display->>'account_holder','') LIKE %s
                        OR COALESCE(display->>'account_holder','') LIKE %s
                      )
                    RETURNING request_id::text
                    """,
                    (COMPANY, key, FIXTURE_BANK, f"%{HOLDER_PREFIX}%", f"%{TAG}%"),
                )
                removed["actions"].append(
                    {"supersede_effective": [dict(x) for x in cur.fetchall() or []], "key": key}
                )
                cur.execute(
                    """
                    UPDATE employee_bank_verified
                    SET revoked_at=COALESCE(revoked_at, now()),
                        revocation_reason=COALESCE(revocation_reason, %s)
                    WHERE company_code=%s AND employee_key=%s AND revoked_at IS NULL
                      AND (
                        COALESCE(display->>'bank_name','') = %s
                        OR COALESCE(display->>'account_holder','') LIKE %s
                        OR COALESCE(display->>'account_holder','') LIKE %s
                      )
                    RETURNING request_id::text
                    """,
                    (TAG, COMPANY, key, FIXTURE_BANK, f"%{HOLDER_PREFIX}%", f"%{TAG}%"),
                )
                removed["actions"].append(
                    {"revoke_verified": [dict(x) for x in cur.fetchall() or []], "key": key}
                )
                # Soft-delete bank profiles only for disposable synth hosts.
                if key.startswith("WATHEFNI-965549700"):
                    cur.execute(
                        """
                        UPDATE employee_ess_bank_profiles
                        SET deleted_at=COALESCE(deleted_at, now()),
                            deletion_reason=COALESCE(deletion_reason, %s)
                        WHERE company_code=%s AND employee_key=%s AND deleted_at IS NULL
                        RETURNING version
                        """,
                        (TAG, COMPANY, key),
                    )
                    removed["actions"].append(
                        {"delete_profile": [dict(x) for x in cur.fetchall() or []], "key": key}
                    )
        conn.commit()

    # Withdraw active submissions via employee sessions when fixture-shaped.
    for key in targets:
        try:
            token = _employee_token(key)
            removed["actions"].append({"withdraw": _withdraw_active(token), "key": key})
        except Exception as exc:
            removed["actions"].append({"withdraw_error": str(exc)[:160], "key": key})
    return removed


def _seed_applied(token: str, hr: str, *, iban: str, holder: str) -> dict[str, Any]:
    rid, submit = _submit(token, iban=iban, holder=holder)
    if not rid:
        return {"ok": False, "submit": submit}
    apply = _approve_through_apply(hr, rid, f"{TAG} apply {STAMP}")
    return {"ok": apply.get("final_state") in {"applied", "approved"}, "request_id": rid, "submit": submit, "apply": apply}


def seed() -> dict[str, Any]:
    keys = list(SCENARIOS.keys())
    _guard_keys(keys)
    # Ensure synth hosts exist before cleanup tries to withdraw.
    for key, spec in SCENARIOS.items():
        if spec["create_if_missing"]:
            _ensure_synth_employee(key, spec["phone"], str(spec["name"]))
    cleanup(keys)
    hr = _hr_token()
    out: dict[str, Any] = {"stamp": STAMP, "tag": TAG, "scenarios": {}, "ok": True}

    # —— Noura: applied + pending HR change ——
    noura = "WATHEFNI-96550010001"
    ntoken = _employee_token(noura)
    applied = _seed_applied(
        ntoken,
        hr,
        iban=IBANS["noura_applied"],
        holder=f"{HOLDER_PREFIX} Noura Applied · {TAG}",
    )
    change_rid, change_submit = _submit(
        ntoken,
        iban=IBANS["noura_change"],
        holder=f"{HOLDER_PREFIX} Noura Pending HR · {TAG}",
    )
    out["scenarios"]["noura"] = {
        "employee_key": noura,
        "role": "applied_plus_pending_hr",
        "applied": applied,
        "pending_hr": {"request_id": change_rid, "submit": change_submit},
    }
    if not (applied.get("ok") and change_rid):
        out["ok"] = False

    # —— 7001: seed applied then pending_payroll change ——
    k1 = "WATHEFNI-9655497001"
    t1 = _employee_token(k1)
    a1 = _seed_applied(t1, hr, iban=IBANS["7001_applied"], holder=f"{HOLDER_PREFIX} 7001 Applied · {TAG}")
    rid1, sub1 = _submit(t1, iban=IBANS["7001_change"], holder=f"{HOLDER_PREFIX} 7001 Payroll · {TAG}")
    payroll_step = None
    if rid1:
        code, body = _hr_decide(hr, rid1, "approve", f"{TAG} hr→payroll {STAMP}")
        payroll_step = {"http": code, "body": body}
    out["scenarios"]["7001"] = {
        "employee_key": k1,
        "role": "pending_payroll",
        "applied": a1,
        "pending_payroll": {"request_id": rid1, "submit": sub1, "hr_approve": payroll_step},
    }
    if not rid1:
        out["ok"] = False

    # —— 7002: needs_correction ——
    k2 = "WATHEFNI-9655497002"
    t2 = _employee_token(k2)
    rid2, sub2 = _submit(t2, iban=IBANS["7002_change"], holder=f"{HOLDER_PREFIX} 7002 Correction · {TAG}")
    ret = None
    if rid2:
        code, body = _hr_decide(
            hr,
            rid2,
            "return_for_information",
            f"{TAG}: please re-check the IBAN on your certificate and resubmit.",
        )
        ret = {"http": code, "body": body}
    out["scenarios"]["7002"] = {
        "employee_key": k2,
        "role": "needs_correction",
        "request_id": rid2,
        "submit": sub2,
        "return": ret,
    }
    if not rid2:
        out["ok"] = False

    # —— 7003: clean applied ——
    k3 = "WATHEFNI-9655497003"
    t3 = _employee_token(k3)
    a3 = _seed_applied(t3, hr, iban=IBANS["7003_applied"], holder=f"{HOLDER_PREFIX} 7003 Applied · {TAG}")
    out["scenarios"]["7003"] = {"employee_key": k3, "role": "applied_clean", "applied": a3}
    if not a3.get("ok"):
        out["ok"] = False

    # Activation codes for device login
    activations: dict[str, Any] = {}
    for key, spec in SCENARIOS.items():
        emp = legacy.find_employee_by_key(key, company_code=COMPANY) or {}
        if not emp.get("app_access_enabled"):
            import employee_app_access as access

            access.set_employee_app_access(
                legacy,
                {
                    "company_code": COMPANY,
                    "user_id": TAG,
                    "actor_user_id": TAG,
                    "email": f"{TAG}@wathefni.ai",
                    "permissions": ["employees.manage", "onboarding.manage"],
                },
                employee_key=key,
                enabled=True,
                reason=TAG,
                deliver_invite=False,
            )
            emp = legacy.find_employee_by_key(key, company_code=COMPANY) or emp
        invite, code = legacy.create_employee_app_invite(COMPANY, emp, created_by_user_id=TAG)
        # Prove /app/bank shape
        token = _employee_token(key)
        http_code, bank_body = _http("GET", "/app/bank", token=token)
        activations[key] = {
            "phone": legacy.digits(emp.get("phone") or spec["phone"]),
            "activation_code": code,
            "invite_expires_at": str(invite.get("expires_at") or ""),
            "bank_http": http_code,
            "submission_state": bank_body.get("submission_state") if isinstance(bank_body, dict) else None,
            "has_verified_bank": bank_body.get("has_verified_bank") if isinstance(bank_body, dict) else None,
            "has_payroll_effective_bank": bank_body.get("has_payroll_effective_bank")
            if isinstance(bank_body, dict)
            else None,
            "next_step": ((bank_body.get("next_step") or {}).get("message") if isinstance(bank_body, dict) else None),
        }
    out["activations"] = activations

    # Shape checks
    expected = {
        noura: {"submission_state": "pending_hr", "has_effective": True},
        k1: {"submission_state": "pending_payroll", "has_effective": True},
        k2: {"submission_state": {"needs_correction", "rejected"}, "has_effective": False},
        k3: {"submission_state": {"applied", "none", "approved"}, "has_effective": True},
    }
    shape_ok = True
    for key, want in expected.items():
        got = activations.get(key) or {}
        state = got.get("submission_state")
        want_state = want["submission_state"]
        if isinstance(want_state, set):
            state_ok = state in want_state
        else:
            state_ok = state == want_state
        eff_ok = bool(got.get("has_payroll_effective_bank")) == bool(want["has_effective"])
        # applied_clean may show submission_state applied OR none with effective
        if key == k3:
            eff_ok = bool(got.get("has_payroll_effective_bank") or got.get("has_verified_bank"))
            state_ok = True
        if not (state_ok and eff_ok and got.get("bank_http") == 200):
            shape_ok = False
    out["shape_ok"] = shape_ok
    out["ok"] = bool(out["ok"] and shape_ok)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        result = cleanup()
        print(json.dumps(result, indent=2, default=str))
        print("CLEANUP_OK")
        return 0
    result = seed()
    print(json.dumps(result, indent=2, default=str))
    print("SEED_OK" if result.get("ok") else "SEED_FAILED")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
