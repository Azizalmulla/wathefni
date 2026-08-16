# Setup Console Phase 5 — Adaptive Employee App Composition + Final Qualification

**Status:** PASS  
**Freeze Setup Console (Phases 1–5):** YES  
**Evidence:** `ops/evidence/setup-console-phase5-20260808T035116Z` (25/0, FREEZE=YES)  
**Depends on:** Setup Console Phases 1–4 (frozen)  
**Do not auto-start:** Employee App P1 · HR App · Auth Wave 2 Phase 6

## Verdict

| Gate | Result |
|---|---|
| Composition matrix A–F | PASS |
| Mobile capability verify | PASS (GREEN) |
| Setup Console regression Phases 1–5 | PASS |
| Canary smoke | **25/0** |

Smoke: `wathefni-orchestrator/smoke-test-setup-console-phase5.py`  
Mobile verify: `apps/wathefni-employee-mobile/scripts/verify-capability-foundation.py`  
Server twin: `wathefni-orchestrator/setup_console_employee_app_phase5.py`

## Final Setup Console architecture map

```
Setup Console (company administration SoT)
├── Phase 1  Ownership / company seed
├── Phase 2  Company modules + Employee App access modes
├── Phase 3A Payroll Setup (calendar SoT)
├── Phase 3B Module company policies (Leave/Attendance/Shifts/Documents/Onboarding)
├── Phase 4  Team access summary + integrations catalog
└── Phase 5  Employee App composition consumer contract  ← this phase
         │
         ▼
   /app/me features (+ app_access + employment + journey state)
         │
         ▼
   employeeAppComposition.ts  (single client derivation — no parallel registry)
         │
         ├── Core: Home · Inbox · Profile · Settings
         ├── Modules: Leave · Shifts · Attendance · Documents · Payslips · Bank · Onboarding
         ├── Home tiles / wide layout / task feed
         └── Deep-link gates (canOpenPath) + soft refresh on foreground/unlock
```

Setup Console remains the only company configuration surface. Employee App consumes entitlements; it does not expose competing admin switches.

## Final Employee App composition contract

**Inputs (canonical):**
1. Company Employee App enabled
2. Employee `app_access_enabled` + active employment
3. `/app/me` feature contract (Setup Console module entitlements)
4. Temporary onboarding journey state (where applicable)

**No parallel frontend feature registry.**

| Surface | Kind | Rule |
|---|---|---|
| Home, Inbox, Profile, Settings | **Core platform** | Always when signed in |
| Leave, Shifts tabs | Entitlement | Hidden when off (no empty slots) |
| Attendance, Documents, Payslips | Entitlement | Home tiles / stack routes |
| Bank | Entitlement | Under Profile (not primary tab) |
| Onboarding | Temporary journey | Shown while incomplete; demoted when complete |
| Compliance | **Not a tab** | Documents + Home tasks |
| Inbox/Notifications | Core | Never counted as purchased module |

**Home density:** `wideHomeTiles` when ≤1 entitlement tile. Inbox is a platform strip, not a module card. No filler tiles.

**Tasks:** `homeTasksFromState` — only entitled modules contribute; deep-link to owning surface.

**Deep links:** `canOpenPath(me, path)` — disabled entitlements fail safe to Home.

**Refresh:** `ForegroundQueryRefresh` + unlock soft-refresh re-fetch `/app/me` (no reinstall).

## Configurations qualified

| ID | Shape | Result |
|---|---|---|
| A | Documents only | Wide Documents tile; no Leave/Shifts tabs |
| B | Leave + Documents | Two tiles; Leave tab on |
| C | Leave + Documents + Attendance + Payslips | Multi-tile grid |
| D | Full suite | All tiles/tabs |
| E | Onboarding employee | Journey visible |
| F | Onboarding complete | Journey demoted |

Also proven in smoke/verify: disabled modules absent from tab/card/task; Inbox not purchased; no separate Compliance tab; `moduleCount` filler removed from Home.

## Launch blockers vs deferred

**Launch blockers:** none for Setup Console freeze.

**Deferred (Employee App / later tracks — not Setup Console blockers):**
- Broad Home/Profile/Attendance/Documents P1 UX polish
- Live device visual QA of A–D layouts on physical canaries (composition contract proven; visual polish is P1)
- SFTP / custom roles / Arabic role-title localization polish from Phase 4 deferrals
- Auth Wave 2 Phase 6

## Freeze recommendation

**YES — freeze Setup Console track (Phases 1–5)** as the company-administration layer.

Do not start Employee App P1, HR App, or Auth Wave 2 Phase 6 from this phase.

## Key files

- `apps/wathefni-employee-mobile/src/composition/employeeAppComposition.ts`
- `apps/wathefni-employee-mobile/src/features/home/HomeView.tsx`
- `apps/wathefni-employee-mobile/app/(tabs)/index.tsx`
- `wathefni-orchestrator/setup_console_employee_app_phase5.py`
- `wathefni-orchestrator/smoke-test-setup-console-phase5.py`
