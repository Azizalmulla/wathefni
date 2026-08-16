# Module-Aware Product Shell Audit

**Mode:** research + implementation truth only · **no code · no deploy**  
**Date:** 2026-08-03  
**Product rule:** A company with one module must feel like it bought a complete focused product — not a mostly empty HR suite.

---

## Verdict (one sentence)

Wathefni already has a real entitlement spine and reshapes **nav, Overview (pre-hire), E360 sections, Assistant tool execution, Setup Launch Readiness, and API 403s** by module — but **post-hire single-module Home is still a suite-shaped shell** (Employees → Workforce → Inbox → module page), and a few surfaces still leak “empty suite” signals (Action Inbox always-partial, Alerts delivery rows, Assistant catalog `pre_hiring` always-on / E360 gated to `onboarding`).

**Code changes are required** — but only a **small shell-composition wave**, not a dashboard rebuild.

---

## 1. Current implementation truth

### 1.1 Entitlement spine (authoritative)

| Layer | Where | Behavior |
|---|---|---|
| Storage | `company_modules` (`app.py`) | Per-company `module_key` + `enabled` |
| Catalog | `module_catalog.py` | Canonical keys, suites, `people_surface`, deps |
| Configured | `configured_company_modules` | Registry authoritative once any row exists |
| Effective | `effective_company_modules` | Configured ∩ catalog ∩ platform available |
| Check | `company_has_module` / `require_entitlement` | Hard API deny → `403 module_disabled` |
| Bootstrap | `/dashboard/bootstrap` | Exposes `configured_modules`, `effective_modules`, `enabled_modules` (= effective) |

**Important:** There is **no purchasable `employees` module**. Employees / Workforce are **people surfaces** unlocked by any `people_surface` post-hire module (onboarding, compliance, attendance, shifts, leave, payroll).

Role packs grant **permissions**; modules grant **entitlements**. Surfaces need both. Permissions do not shrink when a module is off (correct AND-gate; easy to misread as “role implies module”).

### 1.2 Shell authority (already built)

| Piece | Path |
|---|---|
| Frontend helpers | `apps/wathefni-dashboard/src/lib/moduleWorkspace.ts` |
| Frontend authority | `apps/wathefni-dashboard/src/lib/workspaceCapability.ts` |
| Backend mirror + matrix | `wathefni-orchestrator/workspace_capability.py` |
| Composition fixtures | `COMPOSITION_MATRIX` (pre-hire-heavy + one `posthire_only` row) |
| Deploy/tests | `ops/deploy-workspace-composition.sh`, `test_workspace_composition_matrix.py` |

Disabled modules normally **disappear from nav** (not locked cards). Deep links to disabled pages remap to `defaultWorkspacePage`. Setup Console still shows purchased vs `not_purchased` / platform-unavailable states (correct place for subtle “explore”).

### 1.3 What already correctly reshapes (not mere hide)

| Surface | Reshape behavior |
|---|---|
| Sidebar groups | Entire prehire group gone without `pre_hiring`; Assistant moves to posthire group |
| Default landing | Pre-hire → Overview; payroll-operator-like → Payroll; else first offerable posthire page |
| Overview cards | Card count / assessment / calendar driven by entitlement; posthire-only → **no Overview** |
| Optional pre-hire modules | Interviews / Video Interviews / Assessments independently ON/OFF — **production-green** (`ops/PREHIRING_OPTIONAL_MODULE_BOUNDARY_PRODUCTION_GREEN.md`) |
| E360 profile | Sections **omitted** when module off or `*.read` missing (`employee_profile_accessible_modules`) |
| Assistant execution | `tool_call_orchestrator._require_tool_entitlements` → `module_disabled` |
| Action Inbox sources | Analytics / Compliance streams gated; unavailable keys listed; payroll stream excluded by default |
| Setup Launch Readiness | Per-module `not_purchased` … `live_controlled` (Wave A freeze) |
| Employee mobile | Capability contract module-aware; home tiles widen when few modules |
| EN/AR | Locale-aware labels / inbox notes / assistant chips; gating is locale-independent |

### 1.4 What mostly hides (or half-hides)

| Surface | Truth |
|---|---|
| Alerts & Delivery nav | Shown if pre_hiring **or** any post-hire |
| Alerts groups | Onboarding / pre_hiring / completions filtered by module |
| Delivery issue rows | `moduleScopedNotificationRows` returns **[] when `pre_hiring` is off** — posthire-only page can look empty |
| Action Inbox nav | Module-eligible **and** bootstrap `action_inbox.offerable` (viewer allowlist fail-closed) — not pure entitlement |
| Future modules strip | `futureModuleItems` empty — no Explore Modules HR surface yet |

---

## 2. What was already completed

1. **Canonical module catalog** + company registry authority  
2. **Workspace composition spine** (nav + Overview layout matrix; tests)  
3. **Pre-hiring optional module boundary** — production green / frozen  
4. **Post-hire SoA freezes** (Employees 360, Onboarding, Attendance, Leave, Shifts, Payroll foundation) with module gates on APIs  
5. **Unified Action Inbox** — compose-only, source gates, partial/unavailable honesty  
6. **Analytics / Compliance** — unavailable sources not presented as zero (banner + keys)  
7. **Setup Console Launch Readiness** — purchased vs live states (WATHEFNI Wave A)  
8. **Platform Assistant Wave 1–2** — spine + Leave/Attendance queue reads with `company_has_module`  
9. **Employee mobile capability contract** — module-aware tiles  

These prove the platform knows how to disappear disabled modules. They do **not** yet prove every single-module SKU feels like a focused product Home.

---

## 3. Combination matrix (requested SKUs)

Legend: **Good** = focused / calm · **Partial** = usable but suite-shaped · **Gap** = product-rule miss · **N/A** = not a real SKU

### 3.1 “Employees only”

**N/A as a purchasable SKU.** Employees is unlocked only via a people-surface module. A company cannot enable “Employees” alone in `company_modules`.

Closest truth: any single people module (e.g. Leave) unlocks Employees + Workforce + that module.

### 3.2 Leave only (`leave`)

| Surface | Behavior | Verdict |
|---|---|---|
| Nav | posthire: Employees, Workforce, Leave, Assistant; (+ Inbox if allowlisted); Alerts; Settings. No Overview/Jobs | **Good hide** |
| Default Home | First posthire nav id → typically **Employees**, not Leave | **Gap** (suite-shaped landing) |
| Action Inbox | E360 leave next-actions can populate; analytics+compliance marked unavailable; `partial` always true | **Partial** (honest unavailable, noisy “partial”) |
| Assistant | Leave tools gated on; pre_hiring caps can still appear **offerable in catalog** if role has prehire perms (execution still blocked) | **Gap** (offer leak) |
| E360 | Only Leave section (if `leave.read`) | **Good** |
| Setup | Leave purchased; others `not_purchased` | **Good** |
| Alerts | Page may show; delivery rows emptied without pre_hiring | **Gap** |
| Metrics from disabled modules | APIs 403 / streams unavailable | **Good** |

### 3.3 Shifts only (`shifts`)

Same pattern as Leave: nav correctly thin; default landing **Employees**; Inbox partial banner; Alerts delivery thin; Assistant catalog pre_hire leak risk; E360 shifts-only section **Good**.

### 3.4 Payroll only (`payroll`)

| Surface | Behavior | Verdict |
|---|---|---|
| Nav | Employees, Workforce, Payroll, Assistant (± Inbox), Alerts, Settings | **Good hide** |
| Default Home | Special-case: `payroll.read` without `prehire.read` → **Payroll** | **Good** (best single-module Home today) |
| Money / mutations | Payroll foundation freeze; assistant mutations off; money off | **Good** (unchanged constraints) |
| Inbox | Payroll stream excluded by default; E360 payroll next-actions may appear | **Partial** |
| Alerts | Same posthire delivery-row gap | **Gap** |

### 3.5 Employees + Onboarding + Compliance

| Surface | Behavior | Verdict |
|---|---|---|
| Nav | Employees, Workforce, Onboarding, Compliance, Assistant (± Inbox), Alerts | **Good** |
| Home | Default first posthire → Employees (not Onboarding queue) | **Partial** |
| Inbox | Compliance stream live; Analytics unavailable → partial banner; E360 onboarding/compliance actions | **Partial** (usable) |
| E360 | Onboarding + Compliance sections only | **Good** |
| Assistant | `posthire_employees_360` catalog entry keyed to module **`onboarding`** — present here; would be wrong for leave-only | **Partial** |
| Full calm Home | No dedicated “hire-to-ready” Home composition | **Partial** |

### 3.6 Shifts + Attendance + Leave

| Surface | Behavior | Verdict |
|---|---|---|
| Nav | Employees, Workforce, Attendance, Leave, Shifts, Assistant (± Inbox) | **Good** |
| Home | Lands Employees; ops queues are separate pages | **Partial** |
| Inbox | E360 ops next-actions; analytics/compliance unavailable → always partial | **Partial** |
| Assistant Wave 2 | Leave queue + Attendance exceptions when Wave 2 on; Shifts summarize via existing tools if module on | **Good** (reads) |
| Focused “ops desk” Home | Not composed — user must know which page | **Gap** vs focused-product rule |

### 3.7 Full suite

| Surface | Behavior | Verdict |
|---|---|---|
| Prehire Overview | Full card grid when entitlements allow | **Good / unchanged** |
| Posthire | All module pages + Inbox sources complete when entitled | **Good** |
| Assistant | Full catalog (subject to Wave kills / mutations off) | **Good** |
| Composition matrix | `mixed` / `full_prehiring` fixtures cover this path | **Good** |

Full-suite behavior should remain the control case for any future shell wave — do not regress Overview.

---

## 4. Exact module-aware shell architecture (as implemented)

```text
company_modules (registry)
        │
        ├─ configured_company_modules
        └─ effective_company_modules ──► bootstrap.enabled_modules
                    │
                    ▼
        resolveWorkspaceAuthority (TS)  ≈  workspace_capability.py (mirror)
                    │
        ┌───────────┼───────────────┬────────────────┬──────────────┐
        ▼           ▼               ▼                ▼              ▼
   Nav groups   Overview       Action Inbox     Assistant      Setup / E360
   + default    layout         source gates     tools+caps     sections
   landing      (prehire)      + allowlist      + kills        + readiness
```

**AND-gate everywhere that matters:** `module entitlement` ∧ `permission` ∧ (sometimes) `provider/flag/allowlist`.

**People surface rule:** any people module → Employees + Workforce nav (permission permitting).

**Disabled module rule (current):** remove from nav; remap deep links; API `module_disabled`; Setup shows `not_purchased`. Do **not** show locked product cards in the main shell (aligned with product rule). Explore remains Setup / Launch Readiness, not HR nav.

---

## 5. Gaps vs product rule (prioritized)

### P0 — Proven product-feel gaps (not theoretical)

1. **Post-hire default Home is suite-shaped**  
   Single Leave/Shifts/Attendance companies land on **Employees** first (nav order), not the purchased module’s queue. Payroll is the exception (special-cased). Violates “complete focused product.”

2. **Action Inbox `partial` means “missing disabled sources”**  
   `partial = (not analytics) or (not compliance)` even when those modules were never purchased. Single-module tenants always look “incomplete.” Unavailable keys are honest; the **partial framing** is not.

3. **Assistant capability catalog leaks / mis-keys**  
   - `_module_on("pre_hiring")` always True → jobs/candidates/overview can stay **offerable** for owners without `pre_hiring` (execution still denied — empty chips / promises lie).  
   - `posthire_employees_360` keyed to module **`onboarding`** → Leave-only loses E360 assistant surface incorrectly.  
   - `posthire_setup_readiness` keyed to `pre_hiring` (always-on path).

4. **Alerts & Delivery delivery rows require `pre_hiring`**  
   Posthire-only tenants open Alerts and get an emptied delivery list — feels broken, not focused.

### P1 — Incomplete reshaping (acceptable short-term)

5. **No post-hire Overview / composed Home** — posthire-only correctly hides Overview, but does not replace it with a calm module-aware Home (inbox-as-home or module desk).  
6. **Action Inbox allowlist** — entitlement alone does not offer Inbox; canaries fail closed (intentional Phase 0; still not “product SKU complete”).  
7. **`configured` vs `effective`** used inconsistently (catalog often uses configured).  
8. **Backend `WORKSPACE_SURFACES` lags frontend** (Inbox / Workforce richer on TS).  
9. **No HR “Explore Modules” area** — Setup covers purchase state; fine if kept there.

### P2 — Explicit non-goals / already OK

- Full-suite Overview rebuild — **not required**  
- Locked cards for disabled modules in main nav — **already avoided**  
- Metrics-as-zero for disabled modules on Analytics/Compliance/Inbox streams — **largely honest**  
- Frozen SoA modules as systems of action — **keep**  
- WhatsApp / manager / employee / mobile assistant widen — **out of scope**

---

## 6. Are code changes required?

**Yes — small, proven gaps exist.** Not a broad dashboard rebuild.

Do **not** start a “new Home framework.” Reuse `resolveWorkspaceAuthority` / `defaultWorkspacePage` / inbox source meta / assistant catalog.

---

## 7. Smallest next wave (only if authorized)

### Wave name (proposed): **Module-Aware Shell Wave 0 — Focused Post-Hire Landing + Honesty**

**Scope (tight):**

1. **Default landing by primary purchased module**  
   When `pre_hiring` is off, prefer the single (or primary) post-hire ops page over Employees:
   - one people module → that module’s page (Leave / Shifts / Attendance / Onboarding / Compliance / Payroll)
   - multi post-hire → keep Employees **or** Action Inbox when offerable (document rule; pick one)
   - preserve payroll-operator special case and full-suite Overview when `pre_hiring` on

2. **Action Inbox source honesty**  
   Treat disabled/not-purchased analytics/compliance as **omitted**, not `partial`. Reserve `partial` for entitled-but-errored sources. Keep `unavailable_source_keys` only when the UI needs an explicit note — prefer silence for never-purchased modules so one-module tenants don’t feel incomplete.

3. **Assistant catalog module truth**  
   - Gate `pre_hiring` like every other module (remove always-True).  
   - Retarget `posthire_employees_360` to people-surface entitlement (any people module + `employees.read`), not `onboarding` alone.  
   - Keep execution gates unchanged (already correct).

4. **Alerts delivery scoping**  
   Stop blanking all delivery issue rows when `pre_hiring` is off; scope by relevant modules / kinds instead.

**Out of scope for Wave 0:** new Overview widgets, Explore Modules marketplace, role-pack redesign, WhatsApp, mutations, money, Attendance ingest, Assistant Wave 3, changing frozen SoA UIs.

**Prove:** Leave-only, Shifts-only, Payroll-only, Onboarding+Compliance, Shifts+Attendance+Leave, full suite — nav + default landing + inbox honesty + assistant chips + alerts + E360 sections; EN/AR; sibling freezes green.

**Estimated shape:** mostly `App.tsx` default landing + `action_inbox` sources_meta + `assistant_capability_catalog.py` + `NotificationsPage.tsx` row filter — hours/days, not a rebuild.

---

## 8. Recommendation

| Question | Answer |
|---|---|
| Is the shell already module-aware? | **Partially — entitlement + nav reshape yes; focused-product Home no** |
| Hide-only vs reshape? | **Nav/API/E360/Setup reshape; post-hire Home & Alerts still suite-shaped** |
| Full suite safe? | **Yes — leave Overview path alone** |
| Next work? | **Module-Aware Shell Wave 0 only** (above) — after explicit authorize |
| Assistant Wave 3 / broad rebuild? | **NO-GO / not proposed** |

---

## 9. Source anchors

- `wathefni-orchestrator/module_catalog.py`  
- `wathefni-orchestrator/workspace_capability.py` + `apps/wathefni-dashboard/src/lib/workspaceCapability.ts`  
- `apps/wathefni-dashboard/src/lib/moduleWorkspace.ts`  
- `apps/wathefni-dashboard/src/App.tsx` (`defaultWorkspacePage`, nav filter)  
- `wathefni-orchestrator/app.py` (`company_has_module`, `employee_profile_accessible_modules`, `dashboard_action_inbox_payload`)  
- `wathefni-orchestrator/assistant_capability_catalog.py`  
- `apps/wathefni-dashboard/src/pages/NotificationsPage.tsx` (`moduleScopedNotificationRows`)  
- `ops/PREHIRING_OPTIONAL_MODULE_BOUNDARY_PRODUCTION_GREEN.md`  
- `ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md`  
- `ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md`
