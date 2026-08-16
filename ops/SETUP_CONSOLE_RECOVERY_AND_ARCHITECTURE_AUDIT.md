# Setup Console Recovery + Architecture Audit (P0)

**Date:** 20260808  
**Scope:** White-screen P0 fix + architecture audit only — **no broad redesign**  
**Paused:** Employee App P1 · Auth Wave 2 Phase 6 · Payroll Authority reopen · Migration & Sync  

---

## White-screen P0 — PASS

### Exact root cause

`/setup-console` HTML is served by the orchestrator from `WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist`.

Browser then loads hashed JS/CSS from `/dashboard/assets/*`, which **Caddy** was serving from a **different tree**: `/var/www/wathefni-dashboard/assets`.

Proven skew before fix:

| Asset referenced by live HTML | In `/opt/wathefni/dashboard-dist` | In `/var/www/wathefni-dashboard` |
|---|---|---|
| `setupConsole-Xtk-tD4a.js` | present | **missing → public 404** |
| `src-CkK3DIwh.js` | present | missing |
| `src-SO970dzC.css` | present | missing |

Public proof before fix: `GET /setup-console` → 200 HTML · `GET /dashboard/assets/setupConsole-Xtk-tD4a.js` → **404**.  
Empty `#root` with no ErrorBoundary → **complete white screen**.

Not caused by: auth ConnectScreen, Suspense/lazy, or API bootstrap alone.

### Fixes deployed

1. **Single asset root:** Caddy `handle_path /dashboard/assets/*` and dashboard shell now use `/opt/wathefni/dashboard-dist` (same as orchestrator).
2. **Synced** rebuilt dashboard dist to both `/opt/wathefni/dashboard-dist` and `/var/www/wathefni-dashboard` (compat).
3. **Resilient boot shell** in `setup-console.html`: cream background, loading card, script-error listener, 12s timeout recovery (never silent blank).
4. **`SetupConsoleErrorBoundary`** in `src/setup-console/main.tsx` (mirrors dashboard).
5. **Null-safe Classic workspace** (`available_modules`, `channel_policy`, readiness).
6. **Scroll override** for `html.setup-console-boot` so dashboard `overflow:hidden` cannot clip Setup Console.

### Prove (WATHEFNI / api.wathefni.ai)

- `/setup-console` → 200 + boot shell markers (`Loading Setup Console`)
- All HTML-referenced `/dashboard/assets/*` → **200** with non-zero bytes
- Caddy root = `/opt/wathefni/dashboard-dist`
- Uvicorn `:8010/setup-console` → 200

---

## Audit matrix

| Area | Current owner/state | Status | Long-term owner | Gap |
|---|---|---|---|---|
| Company identity/basic setup | Setup Classic create + profile | **PASS** | Setup Console | No CR/legal-entity; no company default locale field in classic |
| Company module entitlements | Classic ModulesCard → `company_modules` | **PASS** / purchased≠live **PARTIAL** | Setup (configured) + freezes (live) | Wizard dual model; full-replace save blast radius |
| Employee App enable/disable | `employee_app` module + platform flag | **PASS** | Setup + platform kill switch | Platform-off still allows selecting module (preview warns) |
| Employee App access mode | Backend `all`\|`selected`+departments | **PARTIAL** | HR PostHire policy + Setup module on/off | **No Setup UI**; no company-level HR policy UI (per-employee only) |
| Employee-facing module entitlements | `/app/me` feature contract | **PASS** | Orchestrator contract | Payroll has no V1 app surface in catalog |
| HR module entitlements | `moduleWorkspace` / `workspaceCapability` / App nav | **PASS** | HR shell | Some Settings subsections not module-scoped |
| Payroll configuration | Setup toggle only; P6 schema contract unused | **PARTIAL** | Setup readiness forms + Payroll ops screens | No P6 required/optional/advanced UI in Setup |
| Attendance / Shifts configuration | Setup entitlement; ops in domain UIs | **PARTIAL** | Domain UIs + Setup readiness | No connector/template forms in Setup |
| Leave configuration | Setup entitlement; packs in Leave | **PARTIAL** | Leave module | No Kuwait pack bind in Setup |
| Documents / Compliance | Setup entitlement; HR Compliance | **PARTIAL** | Compliance domain | No policy-pack/doc-type Setup forms |
| Onboarding configuration | Setup entitlement; template pinned elsewhere | **PARTIAL** | Onboarding domain | No template picker in Setup |
| Channels / notifications | Setup channel policy + WhatsApp | **PARTIAL** | Setup (ownership) + Alerts (runtime) | Company WhatsApp often env-gated |
| Integrations / Connected Systems | Control page + HR Settings | **PARTIAL** | Split intentionally | Duplicate surfaces / unclear authority |
| Roles / permissions / admin ownership | Owner invite only; roles stub | **PARTIAL** | Setup seed → HR Team | No multi-admin Setup UX |
| Localization / timezone / calendar | TZ/currency in Setup; locale Wave A checked | **PARTIAL** | Company settings + Calendar module | Classic Setup does not set `default_locale` |
| Duplicated settings elsewhere | Classic / wizard / control / HR Settings | **BROKEN** (clarity) | Unify under Setup + deep-links | Conflicting “ready” meanings |

---

## Entitlement map (summary)

| Module | Enables | HR respects | App respects | API fail-closed | Home/tasks/deeplinks | Stale UI risk |
|---|---|---|---|---|---|---|
| payroll | `company_modules` + freezes | Yes | Payslips feature only | Yes | HR gated; app payslips gated | Until bootstrap/`/app/me` refresh |
| leave | module row | Yes | Yes | Yes | Tab+Home gated | Same |
| attendance | module row | Yes | Yes | Yes | Home card; stack route | Same |
| shifts | module row | Yes | Yes | Yes | Tab+Home gated | Same |
| onboarding | module row | Yes | Yes | Yes | Home attention | Same |
| compliance | module row | Yes | via documents | Yes | Quick action | Same |
| employee_app | module + platform flag (+ allowlist) | Excluded from HR nav | Hard gate | Yes | App off = no surfaces | Disable revokes sessions/invites |
| pre_hiring / recruiting | module + deps | Yes | N/A (candidate/hr) | Yes | HR Overview adaptive | Same |

**Rule preserved:** Employee App OFF → no app access/invites/surfaces. ON → eligibility + selected employee modules compose the app.

**Disablement safety (recommended policy):** hide/stop future activity; retain history; revoke app sessions when `employee_app` turns off (already implemented); do not mutate payroll authority/history or auto-start onboarding/invites unless the setting explicitly requires it.

---

## Payroll Setup Console mapping (P6)

Contract: `ops/payroll_authority_p6_setup_console_schema_v1.json`

| Group | Maps to future Setup | Today |
|---|---|---|
| Wathefni-owned statutory/engine/provenance | Read-only readiness panel | Not in Setup (correct) |
| Required company fields (mode, frequency, cutoff, attendance payroll mode, components, SOD, Mode A opt-in) | SME-first Setup Payroll section | **Missing** — only module toggle |
| Optional (calendar, lateness, OT, classifications, PIFSS, variance) | Progressive disclosure | Missing in Setup; some in PostHire |
| Advanced (enterprise SOD, allowlist, overrides, Mode B shadow) | Hidden until needed | Missing in Setup; P6 APIs exist |

Do **not** ask companies for Kuwait OT%/statutory percentages Wathefni owns.

---

## Adaptive Employee App findings

| Finding | Severity |
|---|---|
| Notifications Home tile always rendered (+1 in `moduleCount`) — breaks true 1-module wide layout | **Hardcoded surface** |
| Core tabs Home/Inbox/Profile always on; only Shifts/Leave hide | Acceptable baseline; document |
| Attendance/onboarding/documents/payslips are cards/stack routes, not tabs | OK if gated |
| EN/AR RTL: direction + rowReverse on Home; tabs rely on RN direction | Mostly OK |
| Fixed grid holes when modules off | Partially mitigated by gating; notifications always-on still densifies sparse configs |

**Do not resume Employee App P1 in this wave** — findings only.

---

## Recommended implementation phases (not started)

1. **P0 complete** — white-screen + boot resilience + Caddy single root *(this wave)*  
2. **Phase 1 — Authority clarity:** one config owner map in UI copy; deep-links from Setup readiness to domain screens; kill classic/wizard dual-write confusion  
3. **Phase 2 — Access mode:** company-level `all` / `selected` (+ departments) in Setup or HR with fail-closed APIs already present  
4. **Phase 3 — Payroll Setup forms:** P6 required SME defaults → optional → advanced; Mode A entitlement opt-in  
5. **Phase 4 — Adaptive Employee App:** compose Home/tabs from feature contract; remove always-on notifications hole math  
6. **Phase 5 — Locale + packs:** company default_locale; leave/E360/onboarding pack bind from Setup  

---

## Evidence

Local/canary evidence directory: `ops/evidence/setup-console-white-screen-p0-*`  
Backups on host: `/opt/wathefni/backups/dashboard-dist-setup-console-p0-*`, `Caddyfile.bak-setup-console-p0-*`
