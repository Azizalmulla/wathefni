# Employees 360 Wave 3 — Production-readiness counsel pack

**Stamp:** `20260801T205321Z`  
**Audience:** Kuwaiti employment counsel + Wathefni product owners  
**Mode:** Review / decision only — **no code changes, no deploy**  
**Scope:** WATHEFNI-only Wave 3 lifecycle (authority Wave 2 + safety Wave 3C)  
**Disclaimer:** This pack is **not legal advice**. The product records operator and counsel answers; it never decides lawfulness, EOSB, pay-in-lieu, or termination validity.

**Baselines:**  
- Wave 3B policy: `ops/evidence/employees360-wave3b-lifecycle-policy-20260801T204059Z/`  
- Wave 3C implementation PASS (staging): `ops/evidence/employees360-wave3c-lifecycle-safety-local-20260801T204413Z/`

---

## Final GO / NO-GO (now)

**NO-GO** for WATHEFNI production deployment of Wave 3 lifecycle until **blocking counsel items** below are answered and the post-counsel GO checklist is signed.

Staging qualification remains PASS. Production flags must stay off.

---

## Hard confirmation — what Employees 360 does **not** do

| Calculation / decision | Employees 360 |
|---|---|
| End-of-service benefit (EOSB / indemnity) amounts | **Never** |
| Pay-in-lieu of notice amounts | **Never** |
| Garden-leave wage math | **Never** |
| Whether a termination is legally valid | **Never** |
| Whether notice length meets statutory floors | **Never enforces**; may show **non-binding hints** only |
| Leave encashment / final settlement pay | **Never**; emits **input packet** to Payroll only |
| Auto-approval of irreversible offboarding | **Never**; two-person approval required |

Settlement handoff contains IDs, dates, types, impact snapshot refs, and a disclaimer. It must **not** contain an `amounts` field.

---

## Proposed WATHEFNI lifecycle policy values

| Config key | Proposed WATHEFNI value | Notes |
|---|---|---|
| `tier` | `small` | SMB-safe; can raise later |
| `timezone` | `Asia/Kuwait` | All effective/revoke clocks |
| `notice_hint_monthly_days` | `90` | **Hint only** (research summary for monthly-paid KW) |
| `notice_hint_other_days` | `30` | **Hint only** |
| `revoke_mode` | `end_of_last_working_day` | 23:59:59 Kuwait on LWD |
| `effective_time_mode` | `start_of_effective_date` | 00:00 Kuwait on effective date |
| `downstream_mode` | `warn_first` | No hard blocks on open shifts/leave/payroll |
| `require_impact_ack` | `true` | Mandatory before irreversible requests |
| `require_counsel_gate` | `true` | Checklist must be recorded before live mutations in prod |
| `allow_self_approval` | `false` | Hard policy |
| `rehire_same_employee_key` | `true` | When phone identity unchanged |
| `scheduler_cadence` | `hourly` | Staging timer already hourly |
| `lag_alert_seconds` | `7200` | Alert if due terminations lag > 2h |

---

## CQ1–CQ10 counsel review

### CQ1 — Kuwait notice floors by contract type

| Field | Content |
|---|---|
| **Proposed default** | UI/policy **hints** 90 calendar days (monthly) / 30 days (other). Operators enter effective date + LWD. System does **not** block shorter dates (SMB). |
| **Product behavior affected** | Notice suggestions; optional future hard-block if enterprise mode; audit of `termination_effective_on` / `last_working_day`. |
| **Legal decision required** | Confirm Law 6/2010 (and any amendments) floors for Wathefni’s actual contracts: monthly vs other; unlimited vs fixed-term; probation; any contract-longer-than-statute rules. |
| **Safest temporary fallback** | Keep hints **off in production UI copy** or label “illustrative / not legal advice”; require dual approval + approval_reference for any termination; no auto-suggested dates in prod until answered. |
| **Blocks production?** | **Yes — Blocker (P0)** for live employee terminations. Synthetic canary only until answered. |

### CQ2 — Representation risk of suggested notice if shorter dates approved

| Field | Content |
|---|---|
| **Proposed default** | Show hint with explicit “not legal advice” disclaimer; allow override with reason + dual approval. |
| **Product behavior affected** | Termination request UX; override reason fields; counsel-facing audit trail. |
| **Legal decision required** | Does displaying a statutory-style hint create reliance / misrepresentation risk if HR approves a shorter period? Preferred disclaimer language? |
| **Safest temporary fallback** | **Hide numeric notice hints** in production; require free-text effective date only + disclaimer banner. |
| **Blocks production?** | **Yes — Blocker (P0)** if hints remain visible. **Configurable (non-blocking)** if hints disabled and disclaimer retained. |

### CQ3 — Pay-in-lieu / garden leave must stay outside Employees 360

| Field | Content |
|---|---|
| **Proposed default** | Employees 360 never computes pay-in-lieu or garden-leave amounts. Settlement packet is inputs-only. |
| **Product behavior affected** | Settlement handoff shape; payroll integration boundary; scheduler (no money steps). |
| **Legal decision required** | Confirm this boundary is acceptable and that Payroll (or external counsel process) is sole calculator. |
| **Safest temporary fallback** | Already implemented — keep. Add counsel sign-off only. |
| **Blocks production?** | **Yes — Blocker (P0)** until counsel **confirms** the boundary in writing (product already compliant). |

### CQ4 — EOSB / leave encashment ownership in Payroll

| Field | Content |
|---|---|
| **Proposed default** | Packet fields: person/employment IDs, LWD, effective date, term type/reason, impact snapshot refs. Payroll computes and closes packet. |
| **Product behavior affected** | `employee_lifecycle_settlement_packets`; handoff status `handed_to_payroll`. |
| **Legal decision required** | Confirm Payroll is system of record for EOSB and leave encashment; list required input fields (if any missing). |
| **Safest temporary fallback** | Ship inputs-only packet; manual payroll spreadsheet until field list confirmed. |
| **Blocks production?** | **Yes — Blocker (P0)** for **paid** offboarding. **Synthetic lifecycle canary** (no money) can proceed after CQ1–CQ3. |

### CQ5 — Summary dismissal without notice — evidence standard

| Field | Content |
|---|---|
| **Proposed default** | Termination type `dismissal` still requires effective date + dual approval + reason + approval_reference. No “instant legal waive” button. Revoke mode `immediate_on_summary` exists but **not** default for WATHEFNI. |
| **Product behavior affected** | Termination types; optional revoke mode; document retention expectations. |
| **Legal decision required** | When (if ever) summary dismissal without notice is lawful; what evidence must be retained in Wathefni. |
| **Safest temporary fallback** | **Disable** `immediate_on_summary` revoke for WATHEFNI; treat all dismissals like dated terminations with dual approval. |
| **Blocks production?** | **No — Configurable (P1)**. Default path already conservative. |

### CQ6 — Reinstate after effective date (continuous vs broken service)

| Field | Content |
|---|---|
| **Proposed default** | `reinstate` restores **same** `employment_id`; does **not** silently restore sessions/shifts/leave. Dual approval + approval_reference. |
| **Product behavior affected** | Reinstate workflow; indemnity/visa continuity assumptions outside the app. |
| **Legal decision required** | Does reinstate mean continuous service for EOSB/visa, or broken service requiring rehire semantics? |
| **Safest temporary fallback** | **Disable reinstate in production** until answered; require true rehire (new employment) for any return. |
| **Blocks production?** | **Yes — Blocker (P0)** if reinstate remains enabled for live cases. **Non-blocking** if reinstate is flag-disabled and only rehire allowed. |

### CQ7 — Job-search day during employer notice

| Field | Content |
|---|---|
| **Proposed default** | Not tracked as a legal entitlement in v1. Attendance/leave remain normal operational modules during `notice_period`. |
| **Product behavior affected** | Notice-period attendance; future leave policy. |
| **Legal decision required** | Must Wathefni track the ~1 day / 8h per week job-search entitlement (KW research summaries)? |
| **Safest temporary fallback** | No product tracking; HR handles manually; document in runbook. |
| **Blocks production?** | **No — Configurable (P2)**. |

### CQ8 — Document retention / legal hold after termination

| Field | Content |
|---|---|
| **Proposed default** | Documents retained; recommended action `retain_per_policy`; no auto-delete. |
| **Product behavior affected** | Impact preview documents domain; no Wave 3 deletion jobs. |
| **Legal decision required** | Retention periods for Civil ID / residency / contracts; legal-hold process owner. |
| **Safest temporary fallback** | Keep retain-only; no purge tools in Wave 3. |
| **Blocks production?** | **No — Configurable (P1)**. Already safe default. |

### CQ9 — Cross-border / remote workers — which notice regime

| Field | Content |
|---|---|
| **Proposed default** | WATHEFNI policy assumes Kuwait (`Asia/Kuwait`). No multi-country packs in Wave 3. |
| **Product behavior affected** | Timezone; notice hints; counsel gate. |
| **Legal decision required** | Does Wathefni employ anyone whose notice regime is not Kuwait private-sector? |
| **Safest temporary fallback** | Confirm “Kuwait-only employees” in writing; if any non-KW, exclude them from Wave 3 flag until country pack exists. |
| **Blocks production?** | **Conditional P0**: blocks only if non-KW employees exist on WATHEFNI roster. Owner must confirm roster is KW-only. |

### CQ10 — Auto-decline leave / auto-cancel shifts on effective date

| Field | Content |
|---|---|
| **Proposed default** | **Warn-first**. Cancel/decline only via **explicit** two-person downstream actions (reversible). Scheduler does **not** auto-mutate shifts/leave. |
| **Product behavior affected** | Downstream action APIs; scheduler scope (terminate + access revoke only). |
| **Legal decision required** | Is auto-cancel/decline on effective date acceptable under local practice, or must actions stay explicit? |
| **Safest temporary fallback** | Keep warn-first + explicit actions (current). |
| **Blocks production?** | **No — Configurable (P2)**. Current default is safest. |

---

## Owner decision matrix (summary)

| ID | Owner focus | Prod block if unanswered? | Temporary fallback |
|---|---|---|---|
| CQ1 | Notice floors | **P0 Yes** | No live terms; synthetic only / hide hints |
| CQ2 | Hint representation | **P0 Yes** (if hints on) | Hide hints + disclaimer |
| CQ3 | No pay-in-lieu in E360 | **P0 Yes** (sign-off) | Already compliant |
| CQ4 | EOSB in Payroll | **P0 Yes** (for paid offboarding) | Inputs-only + manual payroll |
| CQ5 | Summary dismissal | P1 No | Keep dated dual-approval path |
| CQ6 | Reinstate continuity | **P0 Yes** (if reinstate on) | Disable reinstate; rehire only |
| CQ7 | Job-search day | P2 No | Manual HR |
| CQ8 | Retention | P1 No | Retain-only |
| CQ9 | Cross-border | **P0 if non-KW staff** | KW-only attestation |
| CQ10 | Auto leave/shift | P2 No | Keep explicit actions |

---

## Unresolved blockers by severity

### P0 — block live WATHEFNI production terminations

1. **CQ1** — statutory notice floors for Wathefni contracts  
2. **CQ2** — production stance on notice hints (disable or counsel-approved copy)  
3. **CQ3** — written confirmation: no pay-in-lieu math in Employees 360  
4. **CQ4** — written confirmation: EOSB/encashment only in Payroll + required inputs  
5. **CQ6** — reinstate enabled vs disabled until continuity clarified  
6. **CQ9** — written attestation that WATHEFNI roster is Kuwait-governed only (or exclusions listed)

### P1 — do not block synthetic canary; resolve before broad use

- CQ5 summary-dismissal evidence matrix  
- CQ8 retention schedule documentation  

### P2 — backlog / configurable later

- CQ7 job-search entitlement tracking  
- CQ10 optional auto downstream mutations (default remains off)

---

## Scheduler ownership and support runbook

### Ownership

| Role | Duty |
|---|---|
| **Platform Ops** | Own `wathefni-lifecycle-effective` timer/service; on-call for failed ticks / lag alerts |
| **HR Ops (WATHEFNI)** | Create/approve lifecycle requests; review impact ack; hand settlement to payroll |
| **Payroll Ops** | Compute amounts; close settlement packets |
| **Engineering** | Idempotent executor, audit events, metrics — **no legal discretion** |

### Staging (already)

- Unit: `wathefni-lifecycle-effective-staging.timer` (hourly)  
- Worker: `lifecycle-effective-worker.py` → terminations due + access revokes  
- Kill switch: `WATHEFNI_EMPLOYEE_LIFECYCLE_V3=off`

### Production runbook (when GO)

1. Confirm flags: Wave 2 + Wave 3 on, companies=`WATHEFNI` only, counsel gate on  
2. Install **prod** timer only after canary section passes (not done now)  
3. On failure: check `employee_lifecycle_scheduler_runs` for `failed`; fix DB/env; next tick retries  
4. Lag alert if due `notice_period` rows remain > `lag_alert_seconds` (7200)  
5. Emergency: set lifecycle flag off; does **not** rewind history  
6. Scoped rollback tool exists for **synthetic** keys only in drills — never silent-delete real history

Scheduler **may** set employment `terminated` and revoke app access when due. It **must not** calculate money or waive notice.

---

## Production canary plan (synthetic first)

**Do not run against real employees until P0 counsel answers are recorded.**

| Phase | Action | Pass criteria |
|---|---|---|
| C0 | Deploy code+flags to prod **off** or allowlist empty | No lifecycle mutations |
| C1 | Enable WATHEFNI + create **synthetic** employee (non-human phone) | Create OK; integrity scan clean |
| C2 | Future-dated termination → scheduler → terminated | Same as staging proofs |
| C3 | Access remains until LWD end; revoked after | Session evidence |
| C4 | cancel_scheduled + reinstate (if enabled) / rehire same key | History immutable |
| C5 | Settlement packet has inputs, no amounts | Packet audit |
| C6 | Downstream cancel shifts + reverse | Explicit only |
| C7 | Rollback drill on **synthetic keys only** | Pre-wave3 overlays cleared; Wave 2 optional restore |
| C8 | Only then: one real dual-control case with counsel-aware HR | Owner + counsel observe |

---

## Exact GO checklist after counsel answers

All boxes required for **GO** (WATHEFNI-only):

- [ ] CQ1 answered; notice hint policy set (values or “hints disabled”)  
- [ ] CQ2 answered; production copy/disclaimer approved  
- [ ] CQ3 signed: Employees 360 performs no pay-in-lieu / garden-leave math  
- [ ] CQ4 signed: EOSB/encashment only in Payroll; input field list accepted  
- [ ] CQ6 answered; reinstate enabled **or** explicitly disabled in WATHEFNI policy  
- [ ] CQ9 KW-only roster attestation (or named exclusions outside Wave 3)  
- [ ] Counsel checklist recorded for prod schema version with `require_counsel_gate=true`  
- [ ] Staging Wave 3 + 3C suites still green  
- [ ] Synthetic canary C1–C7 PASS on production DB  
- [ ] Platform Ops on-call named for scheduler  
- [ ] Kill switch + rollback drill documented for WATHEFNI  
- [ ] Explicit owner sign-off: **no Wave 4 / no redesign / no pre-hire changes** in this deploy  

Until then: **NO-GO**.

---

## Sign-off block (for counsel / owners)

| Role | Name | Date | Signature / reference |
|---|---|---|---|
| Kuwait employment counsel | | | |
| Wathefni product owner | | | |
| HR Ops owner | | | |
| Payroll owner | | | |
| Platform Ops (scheduler) | | | |

Interactive summary: Cursor canvas `employees360-wave3-counsel-pack.canvas.tsx`.
