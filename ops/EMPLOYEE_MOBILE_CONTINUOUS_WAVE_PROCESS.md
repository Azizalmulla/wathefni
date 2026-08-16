# Employee Mobile — Continuous Wave Process

**Effective:** `20260805T115900Z` (post Wave 2A cleanup)  
**App:** `apps/wathefni-employee-mobile` · API `https://api.wathefni.ai`  
**Canary:** Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254`  
**Log:** `ops/EMPLOYEE_MOBILE_CANARY_QUALIFICATION_LOG.md`

## Goal

Finish the full employee app faster by removing unnecessary waiting and reinstall cycles — **without** lowering quality or skipping production qualification.

## Working loop (default)

1. **Batch** related work into one major wave (see plan below).
2. **Implement** continuously on the rolling canary branch.
3. **Qualify** locally (dev client / simulator) + seeded QA employees + automated API/mobile E2E and contract tests.
4. **Fix** regressions immediately inside the wave.
5. **Ship internally:** canary deploy → smoke EN/AR → stamp evidence → keep rollback ready.
6. Prefer **OTA** for JS-only updates; **native build only** when native changes require it.
7. **Notify owner for live review only** when the major wave is polished (or a real product decision / pre-GA gate).

## Hard gates (never skip)

| Gate | Requirement |
|---|---|
| Locales | English + Arabic |
| Layout | LTR + RTL |
| Authz | Permissions + tenant isolation |
| UX states | Loading / error / empty |
| Continuity | Refresh / restart / deep links |
| Resilience | Offline / cache where relevant |
| Regressions | Existing employee-app features |
| Contracts | Mobile ↔ backend contract tests |
| Canary | Stamp + rollback path documented |

## Delivery channels

| Change type | Channel |
|---|---|
| JS / assets / copy / most screens | OTA when runtime supports it |
| Native module, permission, Expo config plugin, RN upgrade | New internal native build |
| Backend-only (`/app/*`) | Canary deploy + API smoke; OTA only if client needs matching JS |

## Owner touchpoints

| When | What owner does |
|---|---|
| End of major wave | Live review on canary devices |
| Product ambiguity | Decide; agent continues after |
| Pre-broad rollout | Explicit GO beyond Aziz/Talal |

**Not** an owner touchpoint: each small feature, each API fix, each copy/RTL tweak, each canary redeploy.

## Rolling canary hygiene

- Keep allowlists tight (Aziz + Talal unless owner expands).
- One qualification log entry per internal ship (stamp, scope, smokes, rollback).
- Do not widen bank ESS / payroll / hiring into employee app without an explicit wave.

---

## Major wave plan (upcoming)

Wave **2A lifecycle + cleanup** is **done** (stamp `20260805T114246Z`).  
**Document Validation Parity soft-gate** is **done** (stamp `20260805T142303Z`) — hard-gate deferred. Next batches:

### Wave 3 — Auth & session hardening (native build likely if deep-link / biometrics / secure-store changes)
- Activation reliability, session revoke/reissue, deep-link activate, logout/login RTL residual, access-state polish
- Contract tests for activate / refresh / revoke
- **Owner review:** when auth feels production-polished on canary devices
- **Do not start** until Document Validation live review + soft soak (or owner reorders)

### Wave 4 — Onboarding completion & document journey (partially landed via validation parity)
- Soft-gate live; hard-gate after false-rejection evidence
- Remaining lifecycle UX (preview/history clarity, HR↔employee sync edges)
- Optional-item assignment path (explicit assign → visible)
- Document download/preview parity; empty/error polish
- **No bank ESS yet** unless this wave is re-scoped by owner
- **Owner review:** full onboarding journey EN/AR on Aziz (validation + checklist)

### Wave 5 — Bank ESS (submit + auth) — product decision gate first
- Unlock ESS bank allowlist / synthetic gates only after owner GO
- `/app` bank submit API + encrypted ESS path + mobile form
- Isolation + regression vs informational Wave 2A card
- **Owner review:** required before any bank write on canary

### Wave 6 — Attendance / leave / shifts polish pack
- Leave request UX, cancel edge cases, shifts empty/error, attendance honesty (view-only unless product changes)
- PTR / offline banners / feature-flag empty states
- **Owner review:** after pack is cohesive

### Wave 7 — Notifications, push, settings & account
- Push registration (when EAS project + env allow), mark-read reliability, deletion flow, privacy/support
- Locale persistence + OTA-friendly RTL reload strategy
- **Owner review:** before enabling push for canary broadly

### Wave 8 — Pre-GA qualification
- Full EN/AR matrix, tenant isolation proof, store/privacy readiness checklist, Android internal if needed
- **Owner review:** mandatory before broad production rollout

Waves may merge or reorder when dependencies force it; the rule is **batch for review**, not **pause for install after every PR-sized change**.
