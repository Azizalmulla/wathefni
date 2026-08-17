#!/usr/bin/env python3
"""Frozen Employee/HR auth-shell state-machine regression contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, ok))
    print(("PASS" if ok else "FAIL"), name)


unified = read("src/principals/UnifiedSignInView.tsx")
activation = read("src/features/activation/ActivationView.tsx")
auth = read("src/auth/AuthProvider.tsx")
failure = read("src/auth/authFailure.ts")
root_layout = read("app/_layout.tsx")
principal_gate = read("src/principals/PrincipalGate.tsx")
mode = read("src/principals/mode.ts")
employee_session = read("src/auth/session.ts")
hr_session = read("src/hr/auth/session.ts")
hr_auth = read("src/hr/auth/AuthProvider.tsx")
hr_layout = read("app/hr/_layout.tsx")
switch_hr = read("src/principals/SwitchToHrControl.tsx")
hr_settings = read("app/hr/settings.tsx")
employee_lock_shell = read("src/features/pin/LocalUnlockShell.tsx")
hr_lock_shell = read("src/hr/features/local-lock/HRLocalUnlockShell.tsx")
principal_flow = read(".maestro/flows/hr-employee-mode-switch.yaml")
e2e_secrets = read("../../ops/mobile-e2e/load_secrets.py")
employee_flow = read(".maestro/smoke/03-employee-activation.yaml")
employee_tabs_flow = read(".maestro/smoke/04-employee-tabs.yaml")
hr_flow = read(".maestro/smoke/01-hr-login.yaml")
ar_flow = read(".maestro/locale/critical-ar.yaml")
en = json.loads(read("src/i18n/en.json"))
ar = json.loads(read("src/i18n/ar.json"))

# unsigned -> verified Employee session -> local security gate
for state in ("needsPinSetup", "needsBiometricOptIn", "locked", "signedIn"):
    check(f"unsigned handoff admits {state}", f"'{state}'" in unified.split("EMPLOYEE_SHELL_AUTH_STATES", 1)[1].split("])", 1)[0])
check(
    "post-auth state enters provider-owned Employee transition",
    "EMPLOYEE_SHELL_AUTH_STATES.has(status)" in unified
    and "selectMode('employee')" in unified
    and "savePrincipalModePreference('employee')" not in unified,
)
check(
    "activation is single-flight across button and keyboard",
    "activationInFlightRef.current" in unified
    and "if (activationInFlightRef.current) return" in unified
    and "valid && !busy ? onSignIn" in activation
    and "disabled={!valid || busy}" in activation,
)
check(
    "successful activation persists then loads canonical identity",
    "await persist(res.token, res.refresh_token)" in auth
    and "const loaded = await loadCurrentMe(current)" in auth
    and "await enterAfterIdentity(loaded.me, loaded.session)" in auth,
)

# PIN / biometric / returning-session state machine
check("first activation enters PIN setup", "setStatus('needsPinSetup')" in auth and "clearPinMaterial()" in auth)
check(
    "PIN setup reaches biometric opt-in or signed in",
    "await setPin(key, pin)" in auth
    and "setStatus('needsBiometricOptIn')" in auth
    and "applyMeSignedIn(me)" in auth,
)
check(
    "returning Employee with PIN seals session and locks",
    "const pin = await loadPinRecord()" in auth
    and "sealedSessionRef.current = stored" in auth
    and "setStatus('locked')" in auth,
)
check(
    "PIN and biometric unlock reuse the stored server session",
    "const result = await verifyPin(pin)" in auth
    and "await unlockSealedSession()" in auth
    and "promptBiometricUnlock" in auth
    and "loadCurrentMe(sealed)" in auth,
)
check(
    "logout clears Employee session and returns signed out",
    "await clearLocalAuthMaterial()" in auth.split("const signOut =", 1)[1]
    and "setStatus('signedOut')" in auth.split("const signOut =", 1)[1],
)
check(
    "revoked and expired sessions fail closed",
    all(code in failure for code in ("app_access_revoked", "stale_session_epoch", "app_auth_failed"))
    and "markRefreshFailed" in auth
    and "wipeLocalSession: true" in failure,
)

# HR authority and principal isolation/switching
check(
    "HR login enters provider-owned HR transition",
    "/dashboard/mobile/auth/login" in unified
    and "selectMode('hr')" in unified,
)
check(
    "HR and Employee session namespaces remain separate",
    "const ACCESS_KEY = 'wathefni.session.token'" in employee_session
    and "const SESSION_BLOB_KEY = 'wathefni.hr.session.v1'" in hr_session
    and "const ACCESS_KEY = 'wathefni.hr.access_token'" in hr_session,
)
check(
    "HR and Employee shell switching remains session-aware",
    "selectMode('hr', sealForPrincipalSwitch)" in switch_hr
    and "employeeSession" in hr_settings
    and "selectMode('employee')" in hr_settings
    and "resolveShell" in mode
    and "loadSession()" in principal_gate
    and "loadOperatorSession()" in principal_gate,
)
check(
    "principal transition is single-flight with mount acknowledgement, rollback, and error",
    "transitionPromiseRef" in principal_gate
    and "if (transitionPromiseRef.current) return transitionPromiseRef.current" in principal_gate
    and "savePendingPrincipalTransition(pending)" in principal_gate
    and "loadPendingPrincipalTransition()" in principal_gate
    and "acknowledgePrincipalMounted" in principal_gate
    and "principal_transition_mount_timeout" in principal_gate
    and "router.replace" not in principal_gate
    and "rollbackTransition" in principal_gate
    and "clearPrincipalModePreference" in principal_gate
    and "principal_transition_failed" in principal_gate
    and "catch {}" not in principal_gate,
)
check(
    "stable root navigator survives target provider topology changes",
    "function StableRootNavigator" in root_layout
    and "<StableRootNavigator />" in root_layout
    and "<PrincipalGateProvider>" in root_layout
    and "<AuthProvider>" in root_layout
    and "function EmployeePrincipalMountAck" in root_layout
    and "function HrPrincipalMountAck" in hr_layout
    and 'mode="employee"' in root_layout
    and 'mode="hr"' in hr_layout
    and "function ModeRedirect" not in root_layout,
)
check(
    "outgoing local locks suppress during principal transition",
    "principalTransitionRef.current" in employee_lock_shell
    and "principal_transition" in employee_lock_shell
    and "principalTransitionRef.current" in hr_lock_shell,
)
check(
    "runtime Maestro replaces the principal TODO with cross-PIN and logout isolation",
    "TODO" not in principal_flow
    and "MAESTRO_EMPLOYEE_PIN" in principal_flow
    and "MAESTRO_HR_PIN" in principal_flow
    and "e2e.auth.employee.locked" in principal_flow
    and "e2e.auth.hr.locked" in principal_flow
    and "e2e.pin.error" in principal_flow
    and "e2e.hr.signOut" in principal_flow
    and "e2e.employee.signOut" in principal_flow
    and 'MAESTRO_HR_PIN"] == os.environ["MAESTRO_EMPLOYEE_PIN' in e2e_secrets,
)
check(
    "HR local auth keeps its independent lock state machine",
    all(state in hr_auth for state in ("'needsPinSetup'", "'needsBiometricOptIn'", "'locked'"))
    and "/dashboard/mobile/me" in hr_auth,
)

# Cross-platform and bilingual release operators
check("Employee i18n has exact EN/AR key parity", set(en) == set(ar))
check("Arabic/RTL auth operator exists", "الهاتف" in ar_flow and "بريد العمل" in ar_flow)
check(
    "activation sends the native platform without changing auth authority",
    "Platform.OS === 'ios' ? 'ios'" in auth and "Platform.OS === 'android' ? 'android'" in auth,
)
check(
    "Employee Maestro covers activation, PIN, biometric choice, and authenticated home",
    all(marker in employee_flow for marker in ("MAESTRO_EMPLOYEE_CODE", "e2e.pin.root", "e2e.biometric.notNow", "e2e.tab.employee.home"))
    and "e2e.tab.employee.home" in employee_tabs_flow,
)
check(
    "HR Maestro covers login, PIN, biometric choice, and HR shell",
    all(marker in hr_flow for marker in ("e2e.auth.hr.signIn", "e2e.pin.root", "e2e.biometric.notNow", "e2e.tab.hr.home")),
)
check(
    "Employee AuthGate overlays local post-auth screens without replacing root navigator",
    "<StableRootNavigator />" in root_layout
    and "<AuthGate />" in root_layout
    and "status === 'needsPinSetup'" in root_layout
    and "principalOverlayStyle" in root_layout,
)

failed = [name for name, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
if failed:
    raise SystemExit(1)
print("employee-auth-state-machine: GREEN")
