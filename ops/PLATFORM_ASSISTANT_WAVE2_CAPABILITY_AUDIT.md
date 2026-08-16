# Platform Assistant Wave 2 — Capability Audit

**Mode:** research + architecture only — **no** code, deploy, mutation enablement, or user widening  
**Date:** 2026-08-03  
**Builds on:** `ops/PLATFORM_WIDE_AI_ASSISTANT_ARCHITECTURE_AUDIT.md` · `ops/PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md` (`PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE1_SPINE_GO`)  
**Constrained by:** Onboarding · Attendance · Leave · Shifts · Payroll · Analytics · Compliance freezes (and Action Inbox / Setup Wave A honesty)

---

## Verdict in one line

Do **not** connect every module. Recommended Wave 2 = **Safe Ops Queue Reads** for **Leave + Attendance** only (HR dashboard, WATHEFNI, mutations off, grounded envelopes). Analytics/Compliance remain Inbox-led; Onboarding/Compliance dark reads and all Payroll/Shifts/mutation work stay deferred.

---

## 1. Starting point (Wave 1 frozen)

| Already live | Gap for HR |
|---|---|
| Unified Action Inbox summarize (default post-hire entry) | Inbox composes Analytics + Compliance findings + E360 next actions — **not** full Leave/Attendance/Shifts queues |
| Employees 360 summarize | Per-person, not desk-wide queues |
| Setup Launch Readiness | Operator honesty, not daily ops |
| Mutations **off** · kill switches · citations/freshness/authority · audit | Module list tools exist in registry but are not first-class Wave 1 spine capabilities |

**Product rule (unchanged):** explain / summarize / investigate / prepare deep link. Frozen modules remain systems of action. Never bypass permissions, SOD, allowlists, freezes, money authority, or ingest-off.

---

## 2. Module evaluations

### 2.1 Onboarding

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | Who is still onboarding? Which checklist items are stuck? Whose ESS bank/docs block hire completion? |
| **Required data / permissions** | `onboarding.read` (+ company module on); checklist/status rows; no recruiter/`candidates.read` leakage (freeze) |
| **Read vs prepare** | **Read:** status lists, blockers. **Prepare:** deep link to Onboarding SoA / E360 next action. **Mutate:** start/mark/cancel/reschedule — **out** |
| **Source / freshness / authority** | Source=`onboarding` · as_of Kuwait · authority=`live_controlled` or `synthetic` per freeze · never claim SEED/employee-app breadth |
| **Privacy / SOD / scope** | ESS bank unmask paths forbidden; avoid civil ID in model context |
| **Useful?** | **Yes, but partial overlap** with E360 next actions + Inbox. Dedicated queue adds value for HR “onboarding desk” days. |
| **Registry truth** | `list_onboarding_status` exists but **dark** (`WATHEFNI_ASSISTANT_HR_READS` default off). Mutates exist — must stay killed. |

**Wave 2 fit:** Deferred (enable later via HR_READS under allowlist, not in first Wave 2 slice).

---

### 2.2 Attendance

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | Who was late / absent today? Which days need review? Who has open exceptions? |
| **Required data / permissions** | `attendance.read`; day projections / exceptions — **not** device punches as ingest product |
| **Read vs prepare** | **Read:** list/summarize exceptions. **Prepare:** deep link to Attendance ops. **Mutate:** correct/absent/check-in — **out**. **Never** enable CAPTURE_INGEST or invent punches |
| **Source / freshness / authority** | Source=`attendance` · as_of Kuwait · authority=`synthetic` / `live_controlled` honesty; label **ingest off** when relevant |
| **Privacy / SOD / scope** | Manager scope on lists; no biometric/GPS clocking claims |
| **Useful?** | **High** — daily Kuwait HR pain; weakly covered by Inbox (only via E360 next actions / analytics attention, not a full attendance desk) |
| **Registry truth** | `list_attendance` already ungated read; mutates confirm-gated and killed under Wave 1 |

**Wave 2 fit:** **In recommended scope** (grounded summarize wrapper + catalog chips; reuse `list_attendance`).

---

### 2.3 Leave

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | What leave is pending my decision? Who is out this week? Which requests are stale / dual-control? |
| **Required data / permissions** | `leave.read` (decide perms not required for read); pending queue; allowlist honesty for real decisions |
| **Read vs prepare** | **Read:** pending/approved queues. **Prepare:** deep link to Leave decision UI (+ proposed action package, **not** execute). **Mutate:** approve/reject/cancel — **out** (SOD / self-approval bans stay in SoA) |
| **Source / freshness / authority** | Source=`leave` · as_of · authority=`controlled` / allowlist-gated; `enforced=false` must not be oversold as statutory auto-enforcement |
| **Privacy / SOD / scope** | Manager scope; never let assistant approve; stale dual-control only via SoA |
| **Useful?** | **Highest** daily ops value; Inbox may show analytics “pending leave” attention but not a full decision queue with citations |
| **Registry truth** | `list_leave_requests` ungated read; decision tools confirm + killed |

**Wave 2 fit:** **In recommended scope** (grounded summarize + prepare deep links).

---

### 2.4 Shifts

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | What’s published this week? Open swaps? Coverage gaps? |
| **Required data / permissions** | `shifts.read`; L0 `shift_assignments`; HR allowlist reality |
| **Read vs prepare** | **Read:** list shifts/swaps/availability. **Prepare:** deep link to Shifts board. **Mutate:** create/cancel/replace/swap decide — **out**; manager scheduling allowlist empty |
| **Source / freshness / authority** | Source=`shifts` · published version immutability · authority=`hr_allowlist_controlled` |
| **Privacy / SOD / scope** | Easy to over-offer manager capabilities that freeze forbids |
| **Useful?** | **Medium** — valuable for multi-site later; today 1-HR controlled canary limits commercial story |
| **Registry truth** | `list_shifts` / swaps / availability already readable |

**Wave 2 fit:** Deferred (after Leave/Attendance prove spine widen pattern).

---

### 2.5 Payroll

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | Which timesheets need review? What’s policy mode? What does external package contain? |
| **Required data / permissions** | `payroll.read`; hours/policy/preview — **never** money posting |
| **Read vs prepare** | Soft **read** of hours/policy/preview with loud honesty. **Prepare:** deep link to Payroll external ops. **Mutate / money:** approve timesheet, export, policy set, WPS/bank — **hard NO-GO** |
| **Source / freshness / authority** | Authority must say `preview_non_authoritative` / `money_authority=external` / `payment_processing=disabled` |
| **Privacy / SOD / scope** | Highest hallucination risk (“pay salaries”); SOD approve≠export; Action Inbox excludes payroll stream by default for good reason |
| **Useful?** | Commercially tempting, **dangerous** if soft reads are phrased as pay authority. Better after Leave/Attendance discipline |
| **Registry truth** | Soft reads exist (`list_payroll_hours`, `show_payroll_policy`, `preview_payroll`); exports/approvals confirm + killed |

**Wave 2 fit:** **Out** of Wave 2 (explicit defer). Unnecessary for next slice; risk dominates value.

---

### 2.6 Analytics

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | What needs attention this month? Lateness concentration? Pending leave/swaps signal? |
| **Required data / permissions** | `analytics.read`; attention contract |
| **Read vs prepare** | **Read only.** Prepare = deep link into SoA modules. Product Analytics UI stays `ai:false` |
| **Source / freshness / authority** | Source=`analytics_attention` · as_of Kuwait · `money_authority=false` · no compliance metrics / cost analytics |
| **Privacy / SOD / scope** | Masked counts / synthetic markers where freeze requires |
| **Useful?** | **Already largely covered** by Action Inbox + existing `workforce_analytics` tool. Extra Wave 2 surface is **low incremental value** |
| **Registry truth** | `workforce_analytics` ungated read |

**Wave 2 fit:** Keep Inbox-led; optional tiny grounding polish later — **not** a Wave 2 module connection.

---

### 2.7 Compliance

| Dimension | Assessment |
|---|---|
| **Useful HR questions** | Which residences/IDs expire soon? What’s overdue? |
| **Required data / permissions** | `compliance.read`; findings / documents |
| **Read vs prepare** | **Read** findings/docs. **Prepare:** deep link to Compliance/E360. Reminder send / mark reviewed = mutate — **out**. Never claim government verification/filing |
| **Source / freshness / authority** | `evidence_status` · never `government_verified` · guidance_only |
| **Privacy / SOD / scope** | Civil ID scrub; legal holds |
| **Useful?** | **High**, but **already primary Inbox stream**. Dedicated list tool is dark behind `ASSISTANT_HR_READS` |
| **Registry truth** | `list_compliance_documents` dark; findings via Inbox |

**Wave 2 fit:** Deferred (Inbox remains the Compliance assistant entry; HR_READS flip is a later micro-wave).

---

## 3. Ranking

Scores: 1 (low) – 5 (high). **Readiness** = frozen contract + existing read tool + honesty clarity.

| Module | Customer value | Impl risk | Contract readiness | Differentiation | **Priority** |
|---|---|---|---|---|---|
| **Leave** | 5 | 2 | 5 | 4 | **1** |
| **Attendance** | 5 | 3 | 4 (ingest-off honesty) | 4 | **2** |
| **Compliance** | 4 | 2 | 5 (via Inbox) | 3 | 3 (Inbox covers) |
| **Analytics** | 3 | 1 | 5 (via Inbox) | 2 | 4 (Inbox covers) |
| **Onboarding** | 3 | 2 | 4 (HR_READS dark) | 3 | 5 |
| **Shifts** | 3 | 3 | 4 (allowlist narrow) | 3 | 6 |
| **Payroll** | 4 | 5 | 3 (money confusion) | 5* | 7 (defer) |

\*Payroll differentiates commercially only if honesty never slips — too early for Wave 2.

---

## 4. What is unnecessary right now

| Capability idea | Why skip |
|---|---|
| Connect all seven modules in one wave | Violates “small wave”; multiplies freeze/privacy surface |
| Flip `WATHEFNI_ASSISTANT_HR_READS` for everything | Couples Onboarding+Compliance; harder qualify; Inbox already covers Compliance attention |
| Dedicated Analytics assistant page/tool wave | Duplicate of Inbox + existing tool |
| Payroll hours/preview as Wave 2 headline | Money-authority confusion risk |
| Shifts desk summarize | Narrow canary; manager path NO-GO |
| Any prepare→execute / mutations on | Wave 1 freeze + this audit keep mutations off |
| WhatsApp / manager / employee / mobile | Explicit keep-out |

---

## 5. Exact recommended Assistant Wave 2 scope

### Name

**Platform Assistant Wave 2 — Safe Ops Queue Reads (Leave + Attendance)**

### In scope (small)

1. **Leave queue summarize** (read-only)  
   - Grounded envelope over existing `list_leave_requests` (or thin spine wrapper)  
   - Citations: request id, employee, state, as_of  
   - Authority: controlled / allowlist honesty  
   - Prepare-only deep links into Leave SoA (no approve/reject)

2. **Attendance exceptions summarize** (read-only)  
   - Grounded envelope over existing `list_attendance`  
   - Citations: employee/day/exception type, as_of  
   - Authority labels must state **CAPTURE_INGEST=off** / synthetic-controlled posture when applicable  
   - Prepare-only deep links into Attendance ops (no correct/absent/check-in)

3. **Catalog / empty-state chips** for these two behind Wave 1 spine flags (WATHEFNI · HR dashboard · mutations off)

4. **Reuse Wave 1 spine:** kill switches, audit events, EN/AR fallbacks, tenant isolation, WhatsApp hide, no new mutation tools

5. Staging qualify → prod synthetic qualify (Wave 2-B) before freeze

### Explicitly out of Wave 2

- Onboarding / Compliance `ASSISTANT_HR_READS` enablement  
- Shifts queue summarize  
- Payroll any reads or money paths  
- Analytics new product surface (Inbox remains)  
- Mutations / confirmation execute / SOD decisions  
- WhatsApp widening · manager/employee assistants · mobile · CK  
- Frozen-module contract changes · Attendance ingest · Payroll money  
- AI embedded inside Leave/Attendance product UIs  

### Success criteria (when implemented later)

- HR can ask pending leave / today’s attendance exceptions and get cited, fresh, authority-labeled answers  
- Deep links open SoA; assistant never decides leave or corrects attendance  
- Mutations remain off; sibling freezes green; residual 0 on synthetic canaries  

### Proposed gates (future)

- Staging: `STAGING_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO`  
- Prod synthetic: `PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO`

---

## 6. Suggested sequence after Wave 2 (not started)

| Later slice | Content |
|---|---|
| Wave 2.1 / 3a | Optional `ASSISTANT_HR_READS` for Onboarding **or** Compliance list (one at a time) |
| Wave 3 | Prepare-action UX cards (still SoA executes; mutations kill may lift only under separate owner GO) |
| Later | Shifts reads · soft Payroll honesty reads · manager-scoped assistant |

---

## 7. Risks and unresolved questions

| Risk / question | Note |
|---|---|
| Attendance answers sound like live clocking | Mandate ingest-off / synthetic labels in envelope |
| Leave summarize tempts “just approve it” | Mutations stay off; copy says prepare/deep-link only |
| Inbox vs Leave/Attendance overlap | Inbox = cross-module attention; Wave 2 = desk queues — complementary |
| Should Wave 2 add spine wrappers or only catalog-expose existing list tools? | Prefer **thin grounded wrappers** (Wave 1 pattern) so citations/authority are consistent |
| Manager-scoped lists | Wave 2 remains HR-dashboard roles that already pass entitlement; no manager assistant product |

---

## 8. Explicit NO-GO (this audit)

| Item | Verdict |
|---|---|
| Code / deploy / enable mutations / widen users | **NO-GO** |
| Connect all modules in one wave | **NO-GO** |
| Payroll money / Attendance ingest / WhatsApp-manager-employee-mobile | **NO-GO** |
| Starting Wave 2 implementation | **Not started** (await owner GO) |

---

## Bottom line

| Question | Answer |
|---|---|
| Most valuable next reads? | **Leave** then **Attendance** |
| Already covered by Inbox? | Analytics + Compliance (+ some E360) |
| Highest risk / defer? | **Payroll** (then Shifts / HR_READS bulk flip) |
| Exact Wave 2 scope? | **Safe Ops Queue Reads: Leave + Attendance only** |

**Architecture audit: GO**  
**Implementation: NO-GO until an owner-authorized Assistant Wave 2**
