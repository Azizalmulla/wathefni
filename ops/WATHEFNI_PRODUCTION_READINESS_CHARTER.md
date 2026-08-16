# Wathefni Production Readiness Charter

Status: ACTIVE
Created: 2026-08-12
Predecessor state: Waves 1–6 OWNER ACCEPTED / FROZEN
Current phase: R1 (Full Surface + Release Blocker Audit) — audit only

---

## 1. Purpose

Waves 1–6 proved **domain authority**: canonical truth, module boundaries, handoff contracts, historical
correctness, and modularity, verified by backend smoke tests and staging qualification scripts.

Production Readiness proves something different and strictly harder:

> Can a **real company** — with real employees, real documents, real attendance, real leave and real payroll —
> use Wathefni through its actual product surfaces, in EN and AR, on real devices, without a developer
> intervening?

A green domain test suite is **not** evidence of product readiness. This charter governs the work that closes
the gap between "the authority is correct" and "the product is usable and safe".

## 2. Scope

In scope for every readiness phase:

- HR Web (`apps/wathefni-dashboard`)
- HR Mobile (`apps/wathefni-hr-mobile`, plus the HR co-bundle inside `apps/wathefni-employee-mobile`)
- Employee App (`apps/wathefni-employee-mobile`)
- Setup Console (`apps/wathefni-dashboard/src/setup-console`)
- Assistant (all surfaces, read-only boundary)
- Backend orchestrator (`wathefni-orchestrator`) as it is reachable from those surfaces
- EN / AR / RTL on real journeys
- Permissions, tenant isolation, module composition
- Production infrastructure, data safety, performance, security

Out of scope unless a blocker forces it:

- New HCM domains or features
- Reopening frozen Wave 1–6 domain authority
- Redesign of infrastructure or UI

## 3. Standing rules

1. **No new HCM features.** Production Readiness ships correctness, safety and completeness of what exists.
2. **Frozen authority stays frozen.** Waves 1–6 may only be reopened by an explicit, written freeze amendment,
   and only for a genuine correctness or security blocker.
3. **No defect hiding.** A phase does not pass by narrowing its own definition. If a surface cannot be honestly
   proven, it is recorded as unproven, not as passing.
4. **No invented evidence.** Performance numbers must be measured. Physical-device behaviour must be observed on
   a physical device. Anything asserted without evidence is labelled *unverified*.
5. **Audit phases do not fix.** An audit phase records findings; it does not opportunistically refactor.
6. **Remediation phases are scoped.** Each R2+ phase fixes a named blocker set and re-proves it, then stops.
7. **Setup owns configuration.** Environment variables may act only as kill switches, allowlists and secrets —
   never as the only way to configure a customer-facing behaviour.
8. **Production surfaces never fall back to fake data.** A failed read renders an error state, never a fabricated
   or silently empty one.

## 4. Severity model

Every finding in every phase carries exactly one severity.

| Severity | Meaning | Examples |
|---|---|---|
| **P0** | Release blocker. Cannot go live with a real company. | Cross-tenant exposure, auth failure, forgeable credentials, data corruption, fake/inert production capability, broken core journey |
| **P1** | Must fix before a real paying customer. | Significant workflow or UX failure, broken module composition, missing critical state, important mobile/native defect, admin cannot self-configure |
| **P2** | Polish debt. Safe to ship with. | Visual inconsistency, microcopy, spacing, animation, non-critical convenience |
| **PHYSICAL** | Cannot be honestly proven in staging or a browser. Requires a real device. | Face ID, PIN, camera/uploads, push delivery and deep links, gestures, privacy cover, offline/reconnect, native RTL rendering, keyboard behaviour |

`PHYSICAL` is a *qualification requirement*, not a lower severity: a PHYSICAL item may also be P0 or P1 once
observed. Until observed it is recorded as unproven.

## 5. Phase model

| Phase | Name | Type | Exit condition |
|---|---|---|---|
| **R1** | Full Surface + Release Blocker Audit | Audit only | Honest, evidence-backed blocker list + recommended remediation order. Marker `PRODUCTION_READINESS_R1_AUDIT_COMPLETE`. |
| **R2…Rn** | Blocker remediation phases | Build + prove | Named blocker set fixed, re-proven, regression-clean against Waves 1–6, owner accepted |
| **RP** | Physical device qualification | Device QA | Physical matrix observed on real iOS + Android hardware, EN + AR |
| **RC** | Clean canary company | Live pilot | One real named company operating with zero fixture data and zero developer intervention |
| **RG** | Production rollout gate | Owner decision | Broad rollout authorised |

The exact R2–Rn sequence is an **output of R1**, not an input.

## 6. Evidence discipline

- Every phase writes to `ops/evidence/production-readiness-<phase>-<timestamp>/`.
- Findings cite `path:line` or a reproducible command. Claims without a citation are not findings.
- Subagent or tool output is treated as a lead, not a fact, until spot-verified against source.
- Where a claim could not be verified statically, the report says so explicitly.

## 7. Definition of production ready

All of the following, simultaneously:

1. Zero open P0 findings.
2. Zero open P1 findings, or each remaining P1 explicitly accepted in writing by the owner as known debt.
3. Physical-device matrix observed and passed on real iOS and Android hardware, EN and AR.
4. Every module that a company can enable in Setup delivers a real, reachable, usable product surface — or is
   removed from Setup until it does.
5. No production surface can render fabricated, fixture, or silently-empty-on-error data.
6. Tenant isolation re-proven at API level, not menu level.
7. A clean named company can be created, configured, and operated end-to-end without developer intervention.
8. Backup, restore, rollback and error visibility are proven, not merely present.

## 8. Rollout policy

`PRODUCTION_READY` is not granted by any audit or remediation phase. It requires the owner, after RC, with the
Definition of Production Ready satisfied. All Wave 4–6 capability remains global-OFF and company-gated until
then. Canary remains limited to named allowlisted companies.
