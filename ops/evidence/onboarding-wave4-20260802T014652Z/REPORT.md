# Onboarding Wave 4 — Controlled HR operation, UX refinement & final qualification

**Stamp:** `20260802T014652Z`  
**Evidence:** `ops/evidence/onboarding-wave4-20260802T014652Z/`  
**Template:** `default_kuwait@2.0.0` (four reals unchanged at 150 rows)  
**Freeze:** Closed — see `ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` and `ops/evidence/onboarding-freeze-closure-20260802T015200Z/`

---

## Separate verdicts

| Gate | Verdict |
|---|---|
| **HR production use (WATHEFNI)** | **GO** — `HR_MUTATE=on` + `COMPANIES=WATHEFNI`; mark/waive/remind/reschedule/cancel audited & concurrency-safe; four reals operable in scope |
| **Manager production use** | **GO (scoped)** — list/detail keep manager scope gates; managers with `onboarding.manage` can operate in-scope employees only; cross-scope returns not-found / outside-scope |
| **Talal employee-app onboarding** | **GO (unchanged allowlist)** — `WATHEFNI-96550252254` only; bank via encrypted ESS only |
| **Broad employee-app rollout** | **NO-GO** — allowlist not broadened |
| **General automatic onboarding seed** | **NO-GO** — `ONBOARDING_SEED=off` |
| **Overall Onboarding completion** | **GO for WATHEFNI HR customer-ready operation** — migrated checklists + HR mutate + UX; not a broad employee/SEED rollout |

---

## Implemented UX changes

Dashboard (`PostHire.tsx` → `/var/www` `PostHire-BrW2GlcR.js`):

- Onboarding **queue** with employee, planned start, progress, overdue, next owner
- Checklist grouped by **Employee / HR / IT / Payroll / Compliance**
- Required vs optional labels; dependency / blocked reasons
- States: not started, delayed, in progress, completed, cancelled, abandoned
- Safe actions: mark complete, waive, remind, reschedule, cancel
- ESS bank copy (no plaintext); EN/AR + RTL via `useEmployees360Locale`
- Loading / empty / error / stale (row_version) / permission-denied messaging
- Cream board language aligned with Employees 360 / pre-hiring chrome (no giant card dump)

Backend enrichments: `owner_group`, queue enrichment, `hr_mutate_enabled` company-scoped, `expected_row_version` on mark, `cancel_onboarding` / `reschedule_onboarding` actions.

---

## Production flags & SHAs

| Flag | Value |
|---|---|
| `WATHEFNI_ONBOARDING_SEED` | **off** |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | **on** |
| `WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES` | **WATHEFNI** |
| `WATHEFNI_ONBOARDING_SYNTHETIC_CANARY` | on (synthetic only) |
| Employee-app allowlist | `WATHEFNI-96550252254` only |

| Artifact | SHA256 |
|---|---|
| `app.py` | `e6b670f958f18d32a572a2ae47e80f17e4e397c1b907eadea1f0e3e94cdc6222` |
| `action_registry.py` | `b55c79d3fb1840ba8de4f616a0aeb1c43e621da29bb022de9b87c396452371d3` |
| Dashboard `PostHire-BrW2GlcR.js` | `0f13238daf5431b087da549c57abf17e3eb890453302af21ce409c7d64c349aa` |
| Dashboard `index.html` | `42aa780ec3869e810ad4749dc4f2208681cbd09bd3ab6239fd312f30ccb44882` |

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave4-hr-mutate.conf`  
Backup / rollback: `/opt/wathefni/backups/production-pre-onboarding-wave4-20260802T014652Z/ROLLBACK.sh`

---

## Proofs

| Proof | Result |
|---|---|
| Wave 4 canary | **68/68** (`canary/canary-evidence.json`) |
| Wave 1 read authority | **38/38** |
| E360 freeze | **54/54** |
| Four-real fingerprint | **unchanged** (150 rows) |
| Bank plaintext | **blocked** (`bank_via_ess_required`) |
| Cross-tenant mutate | **denied** |
| Kill switch (drop-in remove/restore) | **PASS** (`verify/kill-switch-execute.txt`) |
| Synthetic lifecycle + cleanup | **PASS** (zero residue) |
| Manager scope wiring | list `_employee_scope_where` + detail `context_manager_allows_employee` |

---

## Screenshots / UX evidence

- `screenshots/queue-en.png` — queue evidence (EN)
- `screenshots/queue-ar.png` — queue evidence (AR/RTL)
- `screenshots/ux-queue-evidence.html` / `ux-queue-ar.html`
- `ux/talal-summary.json`, `ux/queue-enrichment.json`, `ux/bundle-markers.txt`

Live UI: PostHire Onboarding page on production dashboard (cream board, grouped checklist).

---

## Remaining blockers

1. **WhatsApp remind delivery** for synthetic phones can raise `company_code_required` in the outbound recorder — HR remind action is registered; live HR reminders should use real employees with company context (Talal/Fouad/…).
2. **ESS bank allowlist** still gates real encrypted bank collection end-to-end (onboarding tracks ESS authority; plaintext remains impossible).
3. **Broad employee-app** and **general SEED** intentionally remain **NO-GO**.
4. Interactive HR soak in the browser (manual click-through) recommended for first week; automated canary covers API/action paths.

---

## Frozen boundaries

Employees 360 / pre-hiring / Wave D: **no regression** (freeze **54/54**). Four-real checklist history fingerprint restored after reversible prove; SEED remains off; employee-app allowlist unchanged.
