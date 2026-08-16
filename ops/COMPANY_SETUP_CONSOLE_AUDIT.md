# Company Setup Console Audit

**Mode:** research + product architecture only — **no** code or deploy  
**Date:** 2026-08-03  
**Builds on:** `ops/SUPER_ADMIN_COMPANY_ONBOARDING_AND_TENANT_CONTROL_AUDIT.md` (2026-07-27) · Wave 4 final qual (`ops/SUPER_ADMIN_TENANT_CONTROL_WAVE4_ONBOARDING_ACTIVATION_AND_FINAL_QUALIFICATION.md`)  
**Also constrained by:** Attendance / Shifts / Payroll / Leave / E360 / Onboarding freezes (Aug 2026)

---

## Verdict in one line

Setup Console is a **real operator bootstrap + partial control plane**, not a self-serve Kuwait launch product. A real GCC company **cannot** launch Wathefni without engineering. First wave = **unify readiness + config authority for operators (WATHEFNI-scoped)** — not a giant rebuild and **not** external-tenant go-live.

---

## 1. Current setup truth

### What exists

| Surface | Audience | What it actually does |
|---|---|---|
| Setup Console V2 (`/setup-console`) | Platform operators only | Create/select company, profile, modules, Owner seed, WhatsApp link, channel policy, lifecycle, email admin, control page |
| Onboarding wizard (Wave 4) | Operators | 10-step EN/AR shell; **purchased ≠ live**; hard-codes `WATHEFNI`; many steps are copy/stubs |
| Company control page | Operators | Overview, pause/resume, integrations, policies JSON, readiness retest; roles/data largely stubs |
| HR soft readiness | Owner/HR session | Tips (first job/employee/docs) — **not** provisioning |
| Domain UIs | HR | Employee import, leave/E360/onboarding, payroll external setup, shifts board, attendance ops — **outside** Setup Console |

### How companies are created today

1. **Product path:** operator credentials → `POST .../setup/companies` → `companies` + `company_settings`.  
2. **Production truth:** **one** live tenant = `WATHEFNI`. Wave 4 = **NO-GO** for first real external `companies` row.  
3. **Synthetic control-plane tenants** are not externally usable and do not replace `companies`.  
4. **Legacy** `provision-company.sh` / workspace files are not the canonical launch path.

### Product goal vs reality

| Desired step | Today |
|---|---|
| Create tenant | Operator API yes; customer self-serve **no**; external **blocked** |
| Choose modules | Classic writes `company_modules` immediately; wizard purchased/live **incomplete** |
| Configure policies & roles | Channel policy + Owner seed only; leave/E360 packs, custom roles, manager scope **elsewhere / missing** |
| Import employees | **HR dashboard**, not Setup; control page = dry-run only |
| Connect channels/integrations | Partial (WhatsApp policy; company account flag often off; many providers eng/env) |
| Validate readiness | Multiple conflicting “ready” meanings |
| Launch safely | Env allowlists + freezes dominate; Setup “ready” ≠ commercially live |

**Answer:** A real Kuwait/GCC company **cannot** launch without engineering help.

---

## 2. Setup dependency map

```
[Platform flags] Setup Console ON · platform admins · operator credentials
        ↓
[Company row] code + name + country + TZ + currency
        ↓
[Module entitlement] company_modules (+ hard deps: recruiting children → pre_hiring; payroll → currency)
        ↓
[Owner invite] dashboard_users / invite
        ↓
[Channel policy reviewed] → optional company WhatsApp account (flag)
        ↓
─── Setup Console “ready” ends here; commercial launch does not ───
        ↓
[Eng / freeze gates] *_COMPANIES · SYNTHETIC_ONLY · allowlists · CAPTURE_INGEST=off · payroll money off
        ↓
[Domain config] leave pack · E360 pack · onboarding template · payroll mode · shifts templates
        ↓
[People] employee import/hire · manager scopes (mostly empty) · consent rows
        ↓
[Integrations secrets] BioTime/agent · Postmark · providers · SSH/env
        ↓
[Controlled GO] per-module freeze evidence — not Setup activate alone
```

**Soft product couplings (guidance, not enforced in Setup):** onboarding↔compliance↔employee_app · shifts↔attendance · leave↔payroll · payroll↔attendance/leave.

---

## 3. Permission and configuration authority map

| Concern | Belongs at | Today |
|---|---|---|
| Tenant existence / lifecycle | **Company** | Exists; WATHEFNI protected from disable |
| Purchased vs live modules | **Company + commercial entitlement** | Split: classic vs Wave 4 vocabulary |
| Country / TZ / currency | **Company** (legal-entity later) | Company settings |
| CR / PAM file / multi-entity | **Legal entity** | Schema foundation; **not** in Setup |
| Branch / site / team | **Org structure** | Schema thin; Shifts manager scope **NO-GO** in prod |
| Fixed roles (owner/hr/manager) | **Company roles** | Fixed; custom roles canary-only |
| Manager who-sees-whom | **Role + scope (branch/team)** | Fail-closed; production scopes empty for Shifts |
| Leave / E360 policy packs | **Company (module settings)** | Bound by scripts/canaries, not Setup forms |
| Onboarding checklist template | **Company module** | Pinned `default_kuwait@2.0.0` in code/DB |
| Payroll mode / payment_processing | **Company payroll settings** | HR PostHire + wave env; money disabled |
| Attendance connector / ingest | **Site + device + module** | Capture ops dark; ingest **off** |
| Shifts HR/notify allowlists | **Module rollout (subject)** | Env + code pins; not Setup |
| Notification preset / consent | **Company + subject** | Preset default; consent per canary |
| EN/AR default | **Company (+ user override)** | UI locale only; **no** company default language field |
| Kill switches | **Platform + module** | Env-dominant |

**Unsafe / sharp edges**

- Classic “save modules” = full replace (high blast; mitigations exist).  
- Empty onboarding HR-mutate company allowlist while mutate ON = all tenants (freeze hard-ban).  
- Notification preset default `frontline` can be chatty.  
- Company disable ≠ full worker/webhook/timer pause.  
- `admin` → `owner` alias over-privilege risk.  
- Setup “ready” can imply launch while freezes still block real use.  
- Orphan `company_settings` (historical debt) = weak lifecycle integrity.

---

## 4. Engineering-only steps that must become product UX

**Must become Setup (or linked setup tasks) for any honest launch story:**

1. **Module live ≠ env wave allowlist** — show blockers (`SYNTHETIC_ONLY`, empty allowlists, `CAPTURE_INGEST=off`) in readiness.  
2. **Leave / E360 / onboarding policy pack bind** — choose Kuwait pack without scripts.  
3. **Payroll mode + external-run honesty** — link/setup from console; keep money disabled.  
4. **Default locale EN/AR + RTL** at company level.  
5. **Employee import** as an explicit setup step (or deep-link with status), not only HR afterthought.  
6. **Channel ownership** — company WhatsApp vs shared Octopus made explicit.  
7. **Owner + HR admins** beyond single Owner seed (invite list with roles).  
8. **Kill / pause impact** — what actually stops when a module or company is paused.  
9. **Legal entity basics** (name, country, CR) when multi-entity matters — even if single-entity v1.  

**Remain eng/change-control for now (do not fake in Setup):**

- Flipping Attendance ingest / connecting BioTime  
- Payroll money / bank / WPS  
- Shifts manager allowlist / broad notify / timers  
- Broad employee-app rollout  
- AI, iOS/Android  
- New external tenant in production without owner authorization  

---

## 5. Table-stakes vs differentiation

### Table-stakes (ZenHR / Bayzat class)

- Self-serve or assisted company create  
- Module toggles that mean “usable”  
- Org structure + roles + manager scopes  
- Bulk employee import  
- Policy templates (leave, docs)  
- Locale EN/AR  
- Guided go-live checklist  

### Wathefni differentiation (keep)

1. **Honesty of controlled rollout** — purchased ≠ live ≠ freeze-GO.  
2. **Systems of action freezes** — Attendance/Leave/Shifts/Payroll authority not casually toggled.  
3. **Kuwait-first packs** (onboarding, leave, E360) when surfaced as product choices.  
4. **Fail-closed pause / kill vocabulary** when made real (not marketing toggles).  
5. **External payroll as money authority** setup honesty vs “we run payroll” claims.  

Do **not** differentiate by hiding eng gates behind a green “Ready” badge.

---

## 6. Recommended Setup Console architecture (focused)

```
Operator Control Plane (platform admins)
  ├── Tenant registry (create / lifecycle)     [exists; external still gated]
  ├── Entitlement: purchased → configured → ready → live → paused
  ├── Company profile (+ locale, later legal entity)
  ├── Role seeds + invites (fixed roles first)
  ├── Setup task graph (deep-links into domain UIs)
  ├── Readiness = product checks + freeze/env blockers
  └── Audit + pause impact preview

Domain systems of action (HR UIs) — unchanged freezes
  └── Leave / Attendance / Shifts / Payroll / Onboarding / E360
```

**Principles**

- One readiness authority for “can this company operate module X safely?”  
- Setup configures **entitlement + defaults**; freezes remain **change-control**.  
- No giant rewrite of PostHire. Deep-link and report status.  
- Classic destructive module save → retire behind purchased/live model.  
- External tenant creation stays **owner-gated** until platform ops (pause workers, orphans, channel ownership) are honest.

---

## 7. Exact first implementation wave

### **Setup Console Wave A — Launch Readiness Authority (operator-only, WATHEFNI-scoped)**

**In scope**

1. Single **Launch readiness** model: profile, modules, owner, channel policy, **plus** freeze/env blockers per module (read-only truth from flags).  
2. Enforce **purchased → configured → ready → live** for console-driven changes; stop implying classic enablement = commercial live.  
3. Company **default locale** EN/AR.  
4. Setup **task list** with deep-links: employee import, leave pack status, payroll mode/setup status, shifts allowlist status, attendance ingest = off (explicit).  
5. Pause/live copy that states what is *not* stopped (workers/timers) until those gates exist.  
6. Evidence pack + freeze regressions; no external tenant; no module freeze reopen.

**Out of scope**

- External company go-live  
- Legal-entity multi-site / manager scope product  
- Attendance ingest, payroll money, AI, native apps  
- Broad user rollout / Shifts manager widening  
- Rebuilding PostHire or inventing a second HR console  

**Success:** An operator can answer “why isn’t payroll/shifts/attendance commercially live?” from Setup without SSH — without weakening freezes.

**Follow-on (not this wave):** Wave B = first external tenant foundation (owner-authorized); Wave C = policy-pack + structure forms; only after A.

---

## 8. Risks and unresolved questions

| Risk / question | Note |
|---|---|
| Green “Ready” vs freeze NO-GO | Highest buyer-trust risk; Wave A must fix honesty |
| Orphan `company_settings` | Lifecycle integrity before external tenants |
| Classic vs wizard dual model | Confuses operators; unify in Wave A |
| When is first external `companies` row allowed? | Still product authorization (Wave 4 NO-GO stands) |
| Who owns channel WhatsApp — company or shared? | Commercial + ops decision |
| Legal entity vs company for Kuwait CR/PAM | Architecture open; single-entity OK for Wave A |
| Custom roles vs fixed roles | Fixed roles enough for Wave A |
| Notification preset default | Confirm conservative default for new tenants |
| Module pause vs systemd timers | Incomplete suspension boundary |

---

## 9. Keep frozen / unchanged

All current module freezes · no AI · no iOS/Android · no Payroll money · no Attendance ingest · no broad user rollout · no Shifts manager widening · Setup remains operator-gated (not customer self-serve yet).

---

## Sources

- `apps/wathefni-dashboard/src/setup-console/*`  
- `wathefni-orchestrator/company_setup.py`, `module_catalog.py`, `tenant_control_*.py`, `app.py` setup routes  
- `ops/SUPER_ADMIN_COMPANY_ONBOARDING_AND_TENANT_CONTROL_AUDIT.md`  
- `ops/SUPER_ADMIN_TENANT_CONTROL_WAVE4_ONBOARDING_ACTIVATION_AND_FINAL_QUALIFICATION.md`  
- Module freezes: Attendance, Shifts, Payroll, Leave, E360, Onboarding  
- Market: ZenHR / Bayzat setup & roles table-stakes
