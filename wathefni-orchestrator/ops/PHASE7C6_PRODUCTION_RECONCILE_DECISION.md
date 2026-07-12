# Phase 7C.6 — Production reconciliation decision plan (plan only)

**Status:** Option **B executed** — production dry-run only for `WATHEFNI` (no apply).  
**Report:** `ops/reports/phase7c6-prod-wathefni-option-b-report.json`  
**Runner:** `ops/staging-phase7c6-production-dryrun.py`  
**Prerequisites closed:** 7C audit · 7C.1–7C.3 plans · 7C.2 dry-run · 7C.4 throwaway apply · 7C.5 staging `WATHEFNI` W1 canary.

**Keep OFF:**

- `WATHEFNI_EMPLOYEE_APP`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`

**Hard non-goals for this phase document:**

- No production apply in this plan step  
- No employee-app enablement  
- No company channel accounts  
- No upload expansion  
- No broad / multi-row production reconcile  

---

## Context (what we already proved)

| Layer | Proof |
|-------|--------|
| Truth gap measured | Staging `WATHEFNI` had 6 checklist/compliance sync drifts; storage/tenant integrity was clean |
| Planner | Company-scoped dry-run, JSONL, skips, no writes |
| Apply gates | Env + confirms + plan-token/hash + canary caps + staging DSN |
| Throwaway apply | W1–W4 + blocked paths 36/36 |
| Staging live canary | One W1 `civil_id` write; sibling `sync_expiry` left alone; dashboard/health OK |

**Remaining staging drifts (intentionally not fixed in 7C.5):** bank_details W1, medical/passport compliance orphans, civil_id expiry sync, medical null expiry.

Production document graph has **not** been measured with the same canary-scoped dry-run in this series.

---

## Decision question

Do we need a **production one-write canary** before an employee-app pilot, or is staging proof enough to **stop / defer** production reconciliation?

Three options only.

---

## Option A — No production apply yet (stop / defer)

### What it means
- Leave production document stores untouched  
- Keep reconcile tools available for staging only  
- Defer production dry-run and apply to a later approved phase  

### Risk
- **Low operational risk** (no prod mutation)  
- **Residual unknown:** production may have different drift shape/volume than staging; first touch later could surprise operators  
- Employee-app pilot would still rely on **upload dual-write path**, not reconcile backfill — so unfixed historical prod drift remains until a later phase  

### Benefit
- Preserves production freeze posture  
- Avoids any prod checklist/compliance write risk  
- Lets product decide employee-app pilot on **feature flags + upload path**, independent of historical reconcile  

### Required approvals
- Explicit product/ops decision: “defer production reconcile”  
- No new unlock flags  

### Rollback / compensation
- N/A (no writes)  

### Needed before employee-app pilot?
**No — not strictly required** if the pilot:
- stays behind `WATHEFNI_EMPLOYEE_APP`  
- uses the existing receipt pipeline (`file_registry` + `employee_documents` + onboarding update)  
- does **not** depend on healing historical checklist/compliance mismatches  

**Recommended default if the next priority is employee-app readiness checklist (7E), not data healing.**

---

## Option B — One production dry-run only

### What it means
```text
staging tooling against production DSN in mode=dry-run only
--company <one agreed company>
optional canary filters
NO apply, NO WATHEFNI_RECONCILE_APPLY, NO production write unlock
```
Requires a **read-only** production allow path for dry-run (today CLI refuses production-looking DSN without `--allow-production-dsn`; apply must remain refused even with that flag).

### Risk
- **Low-medium:** read-only, but production credentials/DSN handling; mis-set env could be dangerous if apply unlocks were ever combined  
- Information risk: report must stay redacted (`sample_id` only)  
- Does **not** prove apply gates on prod data  

### Benefit
- Measures real production truth gap before any write  
- Informs whether a later one-write canary is even useful (0 vs N drifts)  
- Cheap insurance before employee-app pilot discussions about historical data quality  

### Required approvals
- Written approval to run **production dry-run** naming company scope  
- Confirm apply remains impossible (no `WATHEFNI_RECONCILE_APPLY`, no prod apply unlock)  
- Redacted report retention location agreed  

### Rollback / compensation
- N/A (no writes)  
- Abort if DSN/session is not read-only  

### Needed before employee-app pilot?
**Nice-to-have, not a hard gate** for a closed pilot.  
**Strongly recommended** before any production apply canary (Option C), and useful if stakeholders ask “how bad is prod drift?”

---

## Option C — One production apply canary

### What it means
Exactly one production write, mirroring 7C.5:

| Cap | Value |
|-----|--------|
| Companies | one agreed company |
| Employee | one `employee_sample_id` |
| Document type | one type |
| Writes | `--max-writes 1` |
| Preferred action | **W1 only** (checklist catch-up), same as staging canary |
| Unlock | new explicit flag e.g. `--allow-production-canary` (separate from staging flag) |
| Gates | all 7C.3/7C.4 gates + prod DSN allow + written approval |

**Do not** start with W2/W3/W4 on production.

### Risk
- **Highest of the three:** real prod mutation  
- Wrong employee/type selection could mark checklist received incorrectly  
- Compensation is restore-from-before-image (no DELETE), but still operator-visible  
- Broader blast radius if caps/flags are mishandled (mitigated by layered gates)  

### Benefit
- Proves production apply path end-to-end  
- Builds confidence for later limited prod healing  
- Does **not** by itself unblock employee-app (still a separate flag decision)  

### Required approvals
Must all be written before run:

1. Option C chosen over A/B  
2. Named company, sample_id, document_type, window, operator  
3. Fresh **Option B-style dry-run** for that exact canary showing exactly one W1 plan (or W1-only subset policy)  
4. DB snapshot / backup note  
5. Explicit `--allow-production-canary` implementation approved  
6. Rollback owner on-call  

### Rollback / compensation
| If wrong | Action |
|----------|--------|
| W1 | Restore `onboarding_items.status` to apply audit `before.status` |
| Never | DELETE rows |
| After | Re-dry-run canary scope; dashboard health check |

### Needed before employee-app pilot?
**No — not a prerequisite for a closed employee-app pilot.**  
Staging 7C.5 already proved the reconcile canary pattern. Employee-app pilot risk is dominated by **upload/write-path dual-write behavior and flag rollout**, not by healing one historical checklist row in production.

Only choose C if the goal is **production reconcile readiness**, not employee-app enablement.

---

## Comparison matrix

| Criterion | A Stop/defer | B Prod dry-run | C Prod one-write |
|-----------|--------------|----------------|------------------|
| Prod mutation | None | None | One row |
| Risk | Lowest | Low | Medium |
| Learns prod drift | No | Yes | Yes + apply proof |
| Needed for employee-app pilot | No | Optional | No |
| Needed before broader prod reconcile | Soft pause OK | **Yes, first** | After B |
| Approvals | Decision only | Read-only prod access | Full canary pack |

---

## Recommendation (advisory)

**Prefer Option A for the immediate product path** if the next milestone is Phase 7E employee-app readiness / closed pilot planning: production reconcile is not on the critical path, and staging canary already validated W1 apply mechanics.

**Insert Option B soon** (even while staying on A for writes) if you want production drift visibility before any future prod healing or before promising “docs are consistent” in a pilot narrative.

**Defer Option C** until:
1. Option B shows a clear, safe W1 candidate on an agreed prod company, and  
2. There is a concrete need to prove prod apply (not just employee-app upload).

---

## If Option B or C is later approved — minimal unlock rules

| Mode | Allowed | Forbidden |
|------|---------|-----------|
| B dry-run | `--allow-production-dsn` + read-only session proof | `WATHEFNI_RECONCILE_APPLY`, any apply mode |
| C apply | staging-proven CLI + `--allow-production-canary` + env apply gate + canary caps + max-writes 1 + W1-only | staging flag alone, company-wide, W2–W4 first, fleet runs |

Production canary must **not** reuse `--allow-staging-wathefni-canary`.

---

## Explicit ask for the next user decision

Choose one:

1. **A** — Stop production reconcile here; proceed elsewhere (e.g. 7D/7E)  
2. **B** — Approve production dry-run plan/execution next  
3. **C** — Approve designing/running a production one-write canary (only after B)  

**This document does not authorize production dry-run or apply.**
