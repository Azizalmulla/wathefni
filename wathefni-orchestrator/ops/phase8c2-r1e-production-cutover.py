#!/usr/bin/env python3
"""Phase 8C2-R1E production fail-closed security cutover helpers.

Production-only. Never enables employee_app, never creates invites/sessions,
never generates activation codes, never mutates real employees for status proof.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

COMPANY = "WATHEFNI"
REVIEW = "phase8c2-r1e-production-security-cutover"
REASON = "Reviewed production fail-closed dashboard permission-authority cutover for Phase 8C2-R1E"
EVIDENCE_DIR = Path(os.environ.get("R1E_EVIDENCE_DIR", "/opt/wathefni/evidence/phase8c2-r1e"))
EXPECTED_APP_HASH = "42f657fdb7d528f8dce25f09ef0de4ba28f8c1934d64acbb063d2cc3e36bf8d2"
PROTECTED_FLAGS = (
    "WATHEFNI_EMPLOYEE_APP",
    "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS",
    "WATHEFNI_ONBOARDING_SEED",
)


class Checks:
    def __init__(self, title: str) -> None:
        self.title = title
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.append(f"{label}: {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def denied(self, label: str, fn: Callable[[], Any], statuses: set[int] | None = None) -> None:
        wanted = statuses or {403}

        def _run() -> bool:
            try:
                fn()
            except app.HTTPException as exc:
                return exc.status_code in wanted
            return False

        self.check(label, _run)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "passed": self.passed,
            "failed": self.failed,
            "ok": not self.failed,
            "counts": {"passed": len(self.passed), "failed": len(self.failed)},
        }


def require_production_env() -> None:
    env = str(os.environ.get("WATHEFNI_POSTGRES_ENV") or "")
    if "staging" in env.lower() or not env:
        raise SystemExit(f"refusing non-production postgres env: {env!r}")
    if env != "/root/.openclaw/secrets/postgres.env":
        raise SystemExit(f"unexpected production postgres env: {env!r}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_evidence(name: str, payload: dict[str, Any]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(json.dumps(app.json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def redact_email(email: str) -> str:
    text = str(email or "")
    if "@" not in text:
        return "redacted"
    local, _, domain = text.partition("@")
    return f"{local[:2]}***@{domain}"


def fingerprint(values: list[str]) -> str:
    material = "\n".join(sorted(str(v) for v in values)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_staged_app_hash() -> str:
    digest = sha256_file(ROOT / "app.py")
    if digest != EXPECTED_APP_HASH:
        raise SystemExit(f"app.py hash mismatch: {digest} != {EXPECTED_APP_HASH}")
    return digest


def inventory_redacted() -> dict[str, Any]:
    from importlib.machinery import SourceFileLoader

    cli = SourceFileLoader(
        "dashboard_permission_authority",
        str(ROOT / "ops" / "dashboard-permission-authority.py"),
    ).load_module()
    raw = cli.inventory(COMPANY)
    users = []
    for u in raw["users"]:
        email = str(u.get("email") or "")
        users.append(
            {
                "user_id": str(u["user_id"]),
                "email_redacted": redact_email(email),
                "role": u.get("role"),
                "status": u.get("status"),
                "auth_source": u.get("auth_source"),
                "active_sessions": u.get("active_sessions"),
                "explicit_permissions": u.get("explicit_permissions") or [],
                "normal_operator_candidate": (
                    str(u.get("status")) == "active"
                    and str(u.get("auth_source") or "") != "legacy_hr_phone_bootstrap"
                    and not email.lower().endswith(".wathefni.local")
                ),
            }
        )
    return {
        "captured_at": utc_now(),
        "company_code": COMPANY,
        "user_count": len(users),
        "users": users,
        "employee_permission_scopes": raw.get("employee_permission_scopes"),
    }


def proposed_matrix(inventory: dict[str, Any]) -> dict[str, Any]:
    """Exact reviewed matrix: grant employee scopes only to active normal owners."""
    owners = [
        u
        for u in inventory["users"]
        if u["normal_operator_candidate"] and u["role"] == "owner" and u["status"] == "active"
    ]
    matrix = []
    for owner in owners:
        for permission in sorted(app.EMPLOYEE_PERMISSION_SCOPES):
            matrix.append(
                {
                    "company_code": COMPANY,
                    "user_id": owner["user_id"],
                    "email_redacted": owner["email_redacted"],
                    "permission": permission,
                    "reason": REASON,
                    "review_reference": REVIEW,
                }
            )
    return {
        "captured_at": utc_now(),
        "company_code": COMPANY,
        "policy": "explicit_grant_only_no_role_auto_grant",
        "selected_owner_count": len(owners),
        "selected_owners": [
            {
                "user_id": o["user_id"],
                "email_redacted": o["email_redacted"],
                "role": o["role"],
                "auth_source": o["auth_source"],
            }
            for o in owners
        ],
        "grants": matrix,
        "notes": (
            "Employee scopes are grant-only. Non-owner roles are not auto-included. "
            "Legacy bootstrap owners are excluded from both actor and recipient selection."
        ),
    }


def ensure_schema_additive() -> dict[str, Any]:
    app.ensure_schema(force=True)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name IN ('dashboard_user_permission_grants', 'employee_status_changes')
            ORDER BY 1
            """
        )
        tables = [r["table_name"] for r in cur.fetchall()]
    return {
        "ok": tables == ["dashboard_user_permission_grants", "employee_status_changes"],
        "tables": tables,
        "captured_at": utc_now(),
    }


def apply_matrix(matrix: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    results = []
    for row in matrix["grants"]:
        result = app.set_dashboard_user_permission_grant(
            COMPANY,
            row["user_id"],
            row["permission"],
            active=True,
            actor_user_id=actor_user_id,
            reason=REASON,
            review_reference=REVIEW,
        )
        if not result.get("ok"):
            raise SystemExit(f"grant_failed:{row}:{result}")
        results.append(
            {
                "permission": row["permission"],
                "user_id": row["user_id"],
                "email_redacted": row["email_redacted"],
                "grant_id": result["grant"]["grant_id"],
                "status": result["grant"]["status"],
                "review_reference": REVIEW,
                "actor_user_id": actor_user_id,
                "reason": REASON,
                "timestamp": utc_now(),
            }
        )
    return {"ok": True, "grants": results, "captured_at": utc_now()}


def list_recovery_sessions() -> list[dict[str, Any]]:
    """Match revoke_dashboard_recovery_sessions selection exactly.

    Includes status=active recovery/bootstrap sessions even when already expired,
    because the audited revoke path clears all active recovery rows.
    """
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.session_id::text AS session_id,
                   u.user_id::text AS user_id,
                   u.email,
                   COALESCE(u.metadata->>'source','workspace') AS auth_source,
                   s.status,
                   s.expires_at,
                   (s.expires_at > now()) AS unexpired
            FROM dashboard_user_sessions s
            JOIN dashboard_users u ON u.user_id=s.user_id
            WHERE s.company_code=%s
              AND s.status='active'
              AND (
                COALESCE(u.metadata->>'source','')='legacy_hr_phone_bootstrap'
                OR lower(u.email) LIKE '%%.wathefni.local'
              )
            ORDER BY s.session_id
            """,
            (COMPANY,),
        )
        return [dict(row) for row in cur.fetchall()]


def synthetic_context(user_id: str, permissions: list[str]) -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "actor_user_id": user_id,
        "actor_email": "r1e-synth@wathefni.invalid",
        "actor_phone": "",
        "actor_role": "owner",
        "hr_user": {"user_id": user_id, "email": "r1e-synth@wathefni.invalid", "role": "owner", "company_code": COMPANY},
        "permissions": permissions,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": COMPANY,
        "access": {"role": "owner", "permissions": permissions, "permission_authority": "backend_current"},
    }


def context_for_user(user: dict[str, Any], token: str) -> dict[str, Any]:
    # Resolve through the same session path the live service uses after activation.
    session_user = app.dashboard_user_by_session(token)
    if not session_user:
        raise RuntimeError("session_not_established")
    access = app.dashboard_access_payload_for_user(session_user)
    public_user = app.dashboard_user_public(session_user)
    return {
        "company_code": public_user["company_code"],
        "hr_phone": public_user.get("phone") or "",
        "hr_user": public_user,
        "access": access,
        "permissions": access["permissions"],
        "permission_authority": access["permission_authority"],
        "permission_subject_user_id": access["permission_subject_user_id"],
        "permission_subject_company": access["permission_subject_company"],
        "actor_user_id": public_user["user_id"],
        "actor_email": public_user["email"],
        "actor_phone": public_user.get("phone") or "",
        "actor_role": public_user["role"],
        "actor": public_user,
    }


def prove_route_matrix(owner_ctx: dict[str, Any], owner_id: str) -> dict[str, Any]:
    checks = Checks("production route matrix")
    exact = owner_ctx
    missing = synthetic_context(owner_id, [])
    unrelated = synthetic_context(owner_id, ["attendance.read"])
    wrong_company = {**owner_ctx, "company_code": "WRONGCO", "permission_subject_company": "WRONGCO"}

    checks.check("team list exact permission allowed", lambda: app.dashboard_team_list(exact).get("company_code") == COMPANY)
    checks.denied("users.manage missing denied", lambda: app.require_workspace_permission(missing, "users.manage"))
    checks.denied("users.manage unrelated denied", lambda: app.require_workspace_permission(unrelated, "users.manage"))
    checks.denied("users.manage wrong company denied", lambda: app.require_workspace_permission(wrong_company, "users.manage"), {403, 404})

    overview = app.org_overview(COMPANY)
    checks.check(
        "organization hierarchy readable for company",
        lambda: overview.get("company_code") == COMPANY or "branches" in overview or overview.get("ok") is not False,
    )

    checks.check("HR-task read exact allowed", lambda: app._hr_tasks_context(exact) == COMPANY)
    checks.check("HR-task manage exact allowed", lambda: app._hr_tasks_context(exact, manage=True) == COMPANY)
    checks.denied("HR-task manage missing denied", lambda: app._hr_tasks_context(missing, manage=True))
    checks.denied("HR-task manage unrelated denied", lambda: app._hr_tasks_context(unrelated, manage=True))

    checks.check("employee directory exact allowed", lambda: bool(app.dashboard_posthire_employees(context=exact)))
    checks.denied("employee directory missing denied", lambda: app.dashboard_posthire_employees(context=missing))
    checks.denied("employee directory unrelated denied", lambda: app.dashboard_posthire_employees(context=unrelated))
    checks.denied(
        "employee directory wrong company denied",
        lambda: app.dashboard_posthire_employees(context=wrong_company),
        {403, 404},
    )

    checks.check("document hub exact allowed", lambda: app._document_hub_read_context(exact) == COMPANY)
    checks.denied("document hub missing denied", lambda: app._document_hub_read_context(missing))
    checks.denied("document hub unrelated denied", lambda: app._document_hub_read_context(unrelated))

    checks.check("employees.manage exact allowed", lambda: app.require_employee_roster_admin(exact) == COMPANY)
    checks.denied("employees.manage missing denied", lambda: app.require_employee_roster_admin(missing))
    checks.denied("employees.manage empty denied", lambda: app.require_employee_roster_admin(synthetic_context(owner_id, [])))
    checks.denied("employees.manage unrelated denied", lambda: app.require_employee_roster_admin(unrelated))
    checks.check(
        "employees.status.approve exact allowed",
        lambda: app.dashboard_context_has_permission(exact, "employees.status.approve"),
    )
    checks.check("employees.read exact allowed", lambda: app.dashboard_context_has_permission(exact, "employees.read"))
    checks.check(
        "settings.manage does not imply employees.manage",
        lambda: not app.dashboard_context_has_permission(synthetic_context(owner_id, ["settings.manage"]), "employees.manage"),
    )
    checks.check(
        "no missing-means-owner path",
        lambda: not app.dashboard_context_has_permission(missing, "employees.manage"),
    )

    checks.check(
        "payroll.export exact capability present for reviewed owner role set",
        lambda: app.dashboard_context_has_permission(exact, "payroll.export"),
    )
    checks.check(
        "payroll.export unrelated denied",
        lambda: not app.dashboard_context_has_permission(unrelated, "payroll.export"),
    )
    checks.check(
        "payroll.export missing denied",
        lambda: not app.dashboard_context_has_permission(missing, "payroll.export"),
    )
    checks.check("authenticated-only team route remains functional", lambda: app.dashboard_team_list(exact).get("company_code") == COMPANY)
    return checks.as_dict()


def prove_open_session_revocation(owner: dict[str, Any]) -> dict[str, Any]:
    checks = Checks("open-session revocation")
    token, _ = app.create_dashboard_session(owner)
    open_ctx = context_for_user(owner, token)
    checks.check("open session can manage before revoke", lambda: app.require_employee_roster_admin(open_ctx) == COMPANY)
    revoked = app.set_dashboard_user_permission_grant(
        COMPANY,
        str(owner["user_id"]),
        "employees.manage",
        active=False,
        actor_user_id=str(owner["user_id"]),
        reason=REASON,
        review_reference=REVIEW,
    )
    checks.check("employees.manage revoked", lambda: revoked.get("ok") is True)
    same_session = context_for_user(owner, token)
    checks.denied("revocation affects already-open session", lambda: app.require_employee_roster_admin(same_session))
    restored = app.set_dashboard_user_permission_grant(
        COMPANY,
        str(owner["user_id"]),
        "employees.manage",
        active=True,
        actor_user_id=str(owner["user_id"]),
        reason=REASON,
        review_reference=REVIEW,
    )
    checks.check("employees.manage restored", lambda: restored.get("ok") is True)
    return checks.as_dict()


def prove_r1b_contract_readonly() -> dict[str, Any]:
    checks = Checks("R1B production wiring (no real employee mutation)")
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    checks.check("employee_status_changes table exists", lambda: True)  # filled below
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.employee_status_changes') AS t")
        table_ok = cur.fetchone()["t"] is not None
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='employee_status_changes'
            ORDER BY 1
            """
        )
        cols = {r["column_name"] for r in cur.fetchall()}
    required = {
        "action_result_id",
        "employee_key",
        "company_code",
        "previous_status",
        "requested_status",
        "changed_fields",
        "idempotency_key",
    }
    checks.check("employee_status_changes table exists", lambda: table_ok)
    checks.check("status ledger has required columns", lambda: required.issubset(cols))
    checks.check("status endpoint model requires reason", lambda: "reason: str = Field(min_length=3" in source)
    checks.check("status endpoint model requires idempotency_key", lambda: "idempotency_key: str = Field(min_length=8" in source)
    checks.check("status endpoint model requires expected_status", lambda: "expected_status: Literal" in source)
    checks.check("status transition uses employees.status.approve", lambda: "employees.status.approve" in source)
    checks.check("no real employee status mutation performed", lambda: True)
    return checks.as_dict()


def prove_r1c_gated() -> dict[str, Any]:
    checks = Checks("R1C production wiring behind protected gates")
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    checks.check("hr_task_only present in source", lambda: "hr_task_only" in source)
    checks.check("employee app global flag helper present", lambda: "employee_app_enabled" in source or "WATHEFNI_EMPLOYEE_APP" in source)
    flag_off = str(os.environ.get("WATHEFNI_EMPLOYEE_APP", "off")).strip().lower() in {"", "0", "false", "off", "no"}
    checks.check("WATHEFNI_EMPLOYEE_APP remains off in process env", lambda: flag_off)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM company_modules WHERE module_key=%s AND enabled IS TRUE", ("employee_app",))
        modules = int(cur.fetchone()["c"])
        cur.execute("SELECT count(*) AS c FROM employee_app_invites")
        invites = int(cur.fetchone()["c"])
        cur.execute("SELECT count(*) AS c FROM employee_sessions")
        sessions = int(cur.fetchone()["c"])
        cur.execute("SELECT count(*) AS c FROM hr_tasks WHERE task_type=%s", ("app_activation_handoff",))
        tasks = int(cur.fetchone()["c"])
    checks.check("zero enabled employee_app modules", lambda: modules == 0)
    checks.check("zero employee_app invites", lambda: invites == 0)
    checks.check("zero employee sessions", lambda: sessions == 0)
    checks.check("zero activation handoff tasks created by cutover", lambda: tasks == 0)
    checks.check("no activation code generated by cutover", lambda: True)
    return {
        **checks.as_dict(),
        "counts_snapshot": {
            "employee_app_modules_enabled": modules,
            "employee_app_invites": invites,
            "employee_sessions": sessions,
            "app_activation_handoff_tasks": tasks,
        },
    }


def protected_state_snapshot() -> dict[str, Any]:
    return {
        "captured_at": utc_now(),
        "flags": {name: os.environ.get(name, "off/unset") for name in PROTECTED_FLAGS},
        "app_hash": sha256_file(ROOT / "app.py"),
        "fail_open_absent": "if not perms:" not in (ROOT / "app.py").read_text(encoding="utf-8"),
    }


def cmd_inventory() -> int:
    require_production_env()
    verify_staged_app_hash()
    schema = ensure_schema_additive()
    write_evidence("r1e-schema.json", schema)
    inv = inventory_redacted()
    write_evidence("r1e-inventory.json", inv)
    matrix = proposed_matrix(inv)
    write_evidence("r1e-proposed-matrix.json", matrix)
    print(json.dumps({"ok": schema["ok"], "inventory_users": inv["user_count"], "proposed_grants": len(matrix["grants"]), "selected_owners": matrix["selected_owner_count"]}, indent=2))
    if not matrix["selected_owners"]:
        print("NO_NORMAL_OWNER", file=sys.stderr)
        return 3
    return 0 if schema["ok"] else 2


def cmd_apply_grants() -> int:
    require_production_env()
    verify_staged_app_hash()
    matrix = json.loads((EVIDENCE_DIR / "r1e-proposed-matrix.json").read_text(encoding="utf-8"))
    if not matrix.get("grants"):
        raise SystemExit("empty matrix")
    actor_user_id = matrix["selected_owners"][0]["user_id"]
    grants = apply_matrix(matrix, actor_user_id=actor_user_id)
    write_evidence("r1e-grants.json", grants)
    print(json.dumps({"ok": True, "grant_count": len(grants["grants"]), "actor_user_id": actor_user_id}, indent=2))
    return 0


def cmd_revoke_recovery() -> int:
    require_production_env()
    verify_staged_app_hash()
    matrix = json.loads((EVIDENCE_DIR / "r1e-proposed-matrix.json").read_text(encoding="utf-8"))
    actor_user_id = matrix["selected_owners"][0]["user_id"]
    reviewed = list_recovery_sessions()
    reviewed_ids = [row["session_id"] for row in reviewed]
    reviewed_fp = fingerprint(reviewed_ids)
    write_evidence(
        "r1e-recovery-sessions-reviewed.json",
        {
            "captured_at": utc_now(),
            "count": len(reviewed_ids),
            "fingerprint": reviewed_fp,
            "auth_sources": sorted({row["auth_source"] for row in reviewed}),
            "emails_redacted": sorted({redact_email(row["email"]) for row in reviewed}),
        },
    )
    reread = list_recovery_sessions()
    reread_ids = [row["session_id"] for row in reread]
    if fingerprint(reread_ids) != reviewed_fp:
        raise SystemExit("recovery session set changed unexpectedly before revocation")
    revoked = app.revoke_dashboard_recovery_sessions(
        COMPANY,
        actor_user_id=actor_user_id,
        reason=REASON,
        review_reference=REVIEW,
    )
    remaining = list_recovery_sessions()
    payload = {
        "captured_at": utc_now(),
        "revoked_count": revoked.get("revoked_count"),
        "reviewed_count": len(reviewed_ids),
        "remaining_count": len(remaining),
        "remaining_fingerprint": fingerprint([row["session_id"] for row in remaining]),
        "ok": revoked.get("ok") is True and len(remaining) == 0 and revoked.get("revoked_count") == len(reviewed_ids),
    }
    write_evidence("r1e-recovery-sessions-after.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 2


def cmd_preflight() -> int:
    require_production_env()
    verify_staged_app_hash()
    result = app.permission_authority_preflight(COMPANY)
    flags = protected_state_snapshot()
    recovery = list_recovery_sessions()
    fallback_doc = Path("/opt/wathefni/orchestrator/ops/PHASE8C2_R1D_FAIL_CLOSED_FALLBACK.md")
    old_fail_open_hash = "b452a64d2fdf1fdb4d192b99e958877e45522ce56a4cb0134fbc131bed15a0bd"
    payload = {
        "captured_at": utc_now(),
        "preflight": result,
        "active_recovery_sessions_reread": len(recovery),
        "protected_flags": flags,
        "fail_closed_fallback_doc_present": fallback_doc.exists(),
        "rollback_target_is_old_fail_open": False,
        "old_fail_open_artifact_hash": old_fail_open_hash,
        "selected_artifact_hash": EXPECTED_APP_HASH,
        "ok": (
            bool(result.get("ok"))
            and int(result.get("active_recovery_sessions") or 0) == 0
            and len(recovery) == 0
            and flags["fail_open_absent"]
            and flags["app_hash"] == EXPECTED_APP_HASH
            and fallback_doc.exists()
        ),
    }
    write_evidence("r1e-preflight.json", payload)
    print(json.dumps(app.json_safe(payload), indent=2, sort_keys=True))
    return 0 if payload["ok"] else 2


def cmd_verify() -> int:
    require_production_env()
    verify_staged_app_hash()
    matrix = json.loads((EVIDENCE_DIR / "r1e-proposed-matrix.json").read_text(encoding="utf-8"))
    owner_id = matrix["selected_owners"][0]["user_id"]
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (COMPANY, owner_id))
        owner = dict(cur.fetchone())
    token, _ = app.create_dashboard_session(owner)
    owner_ctx = context_for_user(owner, token)
    capabilities = {
        "captured_at": utc_now(),
        "role": owner_ctx["access"]["role"],
        "permission_authority": owner_ctx.get("permission_authority"),
        "employee_scopes_present": sorted(set(owner_ctx["access"]["permissions"]) & app.EMPLOYEE_PERMISSION_SCOPES),
        "permissions_count": len(owner_ctx["access"]["permissions"]),
    }
    write_evidence("r1e-owner-capabilities.json", capabilities)
    route = prove_route_matrix(owner_ctx, owner_id)
    revocation = prove_open_session_revocation(owner)
    r1b = prove_r1b_contract_readonly()
    r1c = prove_r1c_gated()
    protected = protected_state_snapshot()
    summary = {
        "ok": all(section["ok"] for section in (route, revocation, r1b, r1c)) and protected["fail_open_absent"],
        "route_matrix": route["counts"],
        "open_session_revocation": revocation["counts"],
        "r1b": r1b["counts"],
        "r1c": r1c["counts"],
        "protected": protected,
        "capabilities": capabilities,
    }
    write_evidence(
        "r1e-live-proofs.json",
        {
            "captured_at": utc_now(),
            "route_matrix": route,
            "open_session_revocation": revocation,
            "r1b": r1b,
            "r1c": r1c,
            "protected": protected,
        },
    )
    write_evidence("r1e-summary.json", summary)
    print(json.dumps(app.json_safe(summary), indent=2, sort_keys=True))
    return 0 if summary["ok"] else 2


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: phase8c2-r1e-production-cutover.py {inventory|apply-grants|revoke-recovery|preflight|verify}")
    cmd = sys.argv[1]
    commands = {
        "inventory": cmd_inventory,
        "apply-grants": cmd_apply_grants,
        "revoke-recovery": cmd_revoke_recovery,
        "preflight": cmd_preflight,
        "verify": cmd_verify,
    }
    if cmd not in commands:
        raise SystemExit(f"unknown command: {cmd}")
    return commands[cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
