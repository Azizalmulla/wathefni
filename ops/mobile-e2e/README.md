# Wathefni permanent mobile E2E release harness

**App under test:** `apps/wathefni-employee-mobile` (`ai.wathefni.employee`) — unified Employee + HR (`/hr/*`).  
**Retired:** standalone `wathefni-hr-mobile` is not a ship target.  
**Rule:** **API PASS ≠ MOBILE PASS.** A feature only gets `MOBILE_PASS` when Maestro (or another real UI driver) opens the app, performs the interaction, and the visible result matches backend truth.

## Audit snapshot (this machine)

| Capability | Status |
|---|---|
| Maestro / Detox / Appium in repo (before this harness) | None |
| EAS Workflows / mobile GitHub Actions | None |
| BrowserStack / Sauce / Maestro Cloud account | None |
| Xcode.app | Present (26) |
| `xcode-select` | Often points at CommandLineTools — use `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` |
| Java (required by Maestro) | Install Temurin/OpenJDK 17+ |
| iOS Simulator **runtime** | Missing until ~8 GB free + `xcodebuild -downloadPlatform iOS` |
| Android SDK / adb | Missing |
| API spine + static verify scripts | Strong (existing) |
| Latest full qual (`20260810T194000Z`) | `MOBILE_PASS=0` · HR+Employee **NO-SHIP** |

## What can be automated today

- Host readiness probe (honest BLOCKED reasons)
- Maestro flow authoring + `testID` anchors
- API/DB reconcile spine for HR + Employee canaries (credentials required)
- Static verify / contract scripts already in `apps/wathefni-employee-mobile/scripts/`
- SHIP/NO-SHIP gate that **refuses** to invent `MOBILE_PASS`

## What needs new infrastructure / cost

| Gap | Need | Cost |
|---|---|---|
| iOS Simulator runtime | Free ~9+ GB disk + download platform | Disk space (no $) |
| Install release candidate on sim | EAS build artifact or local `expo run:ios` / install `.app` | EAS minutes (existing) |
| USB iPhone | Registered device + internal build | Existing Apple/EAS |
| True-device cloud (BrowserStack etc.) | New account — **only if** local sim/USB cannot cover | Paid — deferred |
| Multi-tenant module-off fixtures | BOOT*/TENANTISO* companies on env | Engineering time |
| Biometrics | Sim Face ID enrolled or skip as DEBT | Local setup |

**Decision:** BrowserStack App Automate + Maestro is the real-device gate (`ops/mobile-e2e/BROWSERSTACK.md`). Local sim remains optional when disk/JDK allow.

## Fastest path to first real HR + Employee smoke

1. Free ≥9 GB disk → `DEVELOPER_DIR=… xcodebuild -downloadPlatform iOS`
2. Install JDK 17+ without sudo pkg if needed: `brew install openjdk@17` then export `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`
3. Install Maestro: unzip GitHub `cli-*.zip` into `~/.maestro` (or `curl -Ls 'https://get.maestro.mobile.dev' | bash`)
4. Install canary/production RC binary on simulator (`eas build` artifact or existing internal build)
5. Export HR + employee fixture credentials (see `config.example.env`)
6. `python3 ops/mobile-e2e/run-release-gate.py`
7. Read `ops/evidence/mobile-e2e-gate-<stamp>/VERDICT.md`

## Effort estimate

| Slice | Effort |
|---|---|
| This harness (flows + gate + testIDs) | Done (smallest useful) |
| Free disk + install iOS runtime + Maestro | 0.5–2 h (mostly download) |
| First unsigned smoke `MOBILE_PASS` | 1–2 h after sim+app install |
| HR login + tabs + Employee activation smoke | 0.5–1 day with fresh OTP fixtures |
| Full matrix (mutations, RTL, module-off, deep links) | Multi-day wave; expand `.maestro/flows/` |

## Commands

```bash
# Always safe — never invents PASS
bash ops/mobile-e2e/host-readiness.sh

# API spine only (credentials optional; missing → BLOCKED rows)
python3 ops/mobile-e2e/run-api-reconcile.py

# Full gate: readiness → Maestro (if ready) → API reconcile → VERDICT
python3 ops/mobile-e2e/run-release-gate.py

# From the app package
cd apps/wathefni-employee-mobile
npm run e2e:host
npm run e2e:gate
```

## Evidence contract

Each gate writes `ops/evidence/mobile-e2e-gate-<stamp>/`:

- `host-readiness.json`
- `ui/*.log` (+ Maestro debug output when UI ran)
- `api-reconcile.json`
- `VERDICT.json` / `VERDICT.md`

`MOBILE_PASS` count must stay **0** when `ui_runtime_ready=false`.
