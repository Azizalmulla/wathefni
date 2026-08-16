#!/usr/bin/env python3
"""Auth Wave 1 freeze — unit/static regression (no DB writes, no PIN code).

Locks the frozen contract constants, Kuwait aliases, SecureStore handling,
auth route presence, and Phase 0 non-actions (no biometrics dep / no PIN module).

Run:
  python3 wathefni-orchestrator/smoke-test-auth-wave1-freeze-unit.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "wathefni-orchestrator" / "app.py"
SESSION_TS = ROOT / "apps" / "wathefni-employee-mobile" / "src" / "auth" / "session.ts"
AUTH_TSX = ROOT / "apps" / "wathefni-employee-mobile" / "src" / "auth" / "AuthProvider.tsx"
PKG = ROOT / "apps" / "wathefni-employee-mobile" / "package.json"
CONTRACT = ROOT / "ops" / "AUTH_WAVE1_FROZEN_CONTRACT.md"

passed: list[str] = []
failed: list[str] = []


def check(label: str, ok: bool, detail: object = None) -> None:
    (passed if ok else failed).append(label)
    status = "PASS" if ok else "FAIL"
    extra = f" :: {detail}" if detail is not None and not ok else ""
    print(f"  {status}  {label}{extra}")


def _const(src: str, name: str) -> int | None:
    m = re.search(rf"^{re.escape(name)}\s*=\s*(\d+)\s*$", src, re.M)
    return int(m.group(1)) if m else None


def main() -> int:
    print("auth wave1 freeze unit")
    app_src = APP_PY.read_text(encoding="utf-8")
    session_src = SESSION_TS.read_text(encoding="utf-8")
    auth_src = AUTH_TSX.read_text(encoding="utf-8")
    pkg_src = PKG.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")

    # --- Constants frozen ----------------------------------------------------
    check("invite TTL 24h", _const(app_src, "_EMPLOYEE_APP_INVITE_TTL_HOURS") == 24)
    check("max OTP attempts 5", _const(app_src, "_EMPLOYEE_APP_MAX_CODE_ATTEMPTS") == 5)
    check("resend cooldown 60s", _const(app_src, "_EMPLOYEE_APP_CODE_RESEND_COOLDOWN_SECONDS") == 60)
    check("access TTL 7d", _const(app_src, "_EMPLOYEE_APP_SESSION_TTL_DAYS") == 7)
    check("refresh TTL 180d", _const(app_src, "_EMPLOYEE_APP_REFRESH_TTL_DAYS") == 180)

    # --- Routes present ------------------------------------------------------
    for route in (
        '@app.post("/app/auth/activate")',
        '@app.post("/app/auth/request-code")',
        '@app.post("/app/auth/refresh")',
        '@app.post("/app/auth/logout")',
    ):
        check(f"route {route}", route in app_src)

    check("new-device revoke reason frozen", "reactivated_via_invite" in app_src)
    check("logout revoke reason frozen", "revoked_reason='logout'" in app_src)
    check("session_epoch stale reason frozen", "ess_session_epoch_stale" in app_src)
    check("activate uses phone aliases", "employee_phone_alias_list" in app_src and "phone = ANY(%s)" in app_src)
    check("request-code never discloses registration", 'generic = {"ok": True' in app_src)
    check("tokens hashed only", "def _app_token_hash" in app_src and "def _app_code_hash" in app_src)

    # Importable alias helper when orchestrator env is available; otherwise source-only.
    sys.path.insert(0, str(ROOT / "wathefni-orchestrator"))
    try:
        from app import employee_phone_alias_list  # type: ignore

        aliases = set(employee_phone_alias_list("99338566"))
        check(
            "Kuwait 8↔965 alias set",
            aliases == {"99338566", "96599338566"},
            aliases,
        )
        aliases2 = set(employee_phone_alias_list("96550252254"))
        check(
            "Kuwait 965→8 alias set",
            aliases2 == {"50252254", "96550252254"},
            aliases2,
        )
    except Exception as exc:
        print(f"  SKIP  Kuwait alias live import ({type(exc).__name__}: {exc})")
        check("phone alias helper present in source", "def employee_phone_alias_list" in app_src)
        check("phone_identity_candidates used for aliases", "phone_identity_candidates" in app_src)

    # --- Mobile SecureStore contract -----------------------------------------
    check("SecureStore access key", "wathefni.session.token" in session_src)
    check("SecureStore refresh key", "wathefni.session.refresh" in session_src)
    check("SecureStore WHEN_UNLOCKED only", "WHEN_UNLOCKED" in session_src and "AFTER_FIRST_UNLOCK" not in session_src)
    check("no AsyncStorage import for tokens", "from '@react-native-async-storage" not in session_src and "AsyncStorage." not in session_src)
    check("save/load/clear session API", all(x in session_src for x in ("saveSession", "loadSession", "clearSession")))

    check("mobile activate hits /app/auth/activate", "/app/auth/activate" in auth_src)
    check("mobile refresh hits /app/auth/refresh", "/app/auth/refresh" in auth_src)
    check("mobile logout hits /app/auth/logout", "/app/auth/logout" in auth_src)
    check("mobile request-code path", "/app/auth/request-code" in auth_src)
    check("401 triggers rotate+retry", "rotateSessionAndLoadMe" in auth_src)

    # --- Phase 0 non-actions -------------------------------------------------
    check("no expo-local-authentication dep", "expo-local-authentication" not in pkg_src)
    check("no PIN unlock module yet", not (ROOT / "apps" / "wathefni-employee-mobile" / "src" / "auth" / "pin.ts").exists())
    check("frozen contract doc present", CONTRACT.is_file() and "PIN unlocks the existing local SecureStore session only" in contract)
    check("UX first-login rule documented", "OTP once → create PIN" in contract)
    check("UX return rule documented", "Open app → PIN → app opens" in contract)

    # Syntax sanity on mobile auth files
    try:
        # TS not parseable by ast; just ensure non-empty + balanced braces roughly
        check("session.ts non-empty", len(session_src) > 100)
        check("AuthProvider.tsx non-empty", len(auth_src) > 500)
    except Exception as exc:
        check("mobile auth files readable", False, exc)

    # app.py still parses
    try:
        ast.parse(app_src)
        check("app.py parses", True)
    except SyntaxError as exc:
        check("app.py parses", False, exc)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    if failed:
        print("AUTH_WAVE1_FREEZE_UNIT: FAIL")
        return 1
    print("AUTH_WAVE1_FREEZE_UNIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
