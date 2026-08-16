# BrowserStack App Automate + Maestro (real-device gate)

Credentials (**never commit**):

```bash
# Preferred: local secret files (chmod 600)
#   ~/.config/wathefni/e2e.env
#   ~/.config/wathefni/browserstack.env
#   ~/.config/wathefni/e2e-fixtures.env   # written by provision-leave-fixture.py
# Or export in the shell / ops/mobile-e2e/.env.local

export BROWSERSTACK_USERNAME='…'
export BROWSERSTACK_ACCESS_KEY='…'
# Prefer already-uploaded RC:
export BROWSERSTACK_APP_URL='bs://41149d60ef1f119af901722322179a92ed2c0b67'  # canary IPA 0.3.0 (23)
```

HR / Leave (loaded automatically from `~/.config/wathefni/e2e.env` + fixtures):

```bash
export MAESTRO_HR_COMPANY=WATHEFNI
export MAESTRO_HR_EMAIL='…'          # e2e-hr+mobile@wathefni.internal
export MAESTRO_HR_PASSWORD='…'
export MAESTRO_PIN=246810
# Leave IDs are provisioned — do not hardcode permanent IDs:
python3 ops/mobile-e2e/provision-leave-fixture.py
```

## Commands

```bash
# Publish canary OTA so IPA 23 relaunches into UnsignedEntry (not stale chooser)
(cd apps/wathefni-employee-mobile && bash scripts/publish-canary-ota.sh "BrowserStack E2E UnsignedEntry + leave testIDs")

# Provision disposable Leave fixtures + run real-device gate
python3 ops/mobile-e2e/provision-leave-fixture.py
export MOBILE_E2E_SUITE=bs-smoke
export MOBILE_E2E_RUNTIME=browserstack
python3 ops/mobile-e2e/run-release-gate.py
```

## RC under test

| Field | Value |
|---|---|
| App | `ai.wathefni.employee` unified |
| EAS build | `fa70005b-6eb4-4481-860f-9c4013d92a93` |
| Version | `0.3.0` (23) · channel `canary` |
| BrowserStack app | `bs://41149d60ef1f119af901722322179a92ed2c0b67` |
| Intended auth UI | Unified UnsignedEntry (`e2e.auth.methodSwitch`) — **not** principal chooser |
| OTA soak | `bs-smoke/_ota-to-unsigned.yaml` launch → wait → stopApp → launchApp |

### RC reconciliation (2026-08-11)

IPA 23 embeds the Aug 9 principal chooser ("Choose how to continue"). Workspace + canary OTA ship **UnsignedEntry** (Phone | Work email). BrowserStack flows must OTA-relaunch (or use a newer IPA) before asserting ship UI. Chooser Continue taps with `clickable=null` are **stale UI debt**, not the release definition of PASS.

Face ID / biometric unlock: **BLOCKED_NATIVE / PHYSICAL_DEBT** unless BrowserStack biometric injection is proven. Flows tap **Not now** on the opt-in sheet.

## Rule

**API PASS ≠ MOBILE PASS.** `MOBILE_PASS` only when BrowserStack reports passed real-device sessions that executed the UI.
