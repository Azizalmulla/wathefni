# Battery-1 Larger Validation Pilot Protocol

**Status:** prepared — do not recruit yet  
**Battery:** Wathefni General Ability & Workplace Judgment v1 (`pilot_v2`)  
**Source curated manifest:** `238481b1659aa80a592b6633fa08cd67f4cf43092c954afbbd05f6b6adee74bd`  
**Revised manifest:** `035a12a2e35c487d3588f2d3be8952cd3350f30f2b030cdf3d863c5490e39c62`  
**Environment:** staging / non-consequential only  
**Approved-for-use:** false  
**Production live bank:** not inserted  

---

## 1. Purpose

Run a real, non-consequential validation study with **100–200 consenting participants** to decide whether Battery-1 is ready for controlled operational use later. This study measures psychometric quality, EN/AR equivalence, fairness signals, and operational take-path stability. It does **not** create hiring decisions, offers, or employees.

## 2. Study design

| Element | Spec |
|---|---|
| Design | Single-form bilingual battery; participants assigned EN or AR |
| Content version | Frozen `pilot_v2` EN/AR assessment versions only |
| Scoring | Deterministic answer-key scoring only; no AI scoring |
| Consequences | None — explicit non-consequential consent |
| Tenant isolation | Dedicated validation company (not `WATHEFNI` recruiting analytics) |
| Duration target | ~35–45 minutes; hard stop optional at 60 minutes |

### Staging battery pins

| Locale | Battery key | Assessment version ID |
|---|---|---|
| EN | `b1_gawj_v1_en_pilot_v2` | `8b079f30-6c58-4753-81a7-1945d4c6424b` |
| AR | `b1_gawj_v1_ar_pilot_v2` | `90d6ebd8-bbdb-4de2-82a3-e5c6efe764e6` |

Item #7 is the only content change since the internal pilot. Items #8 and #22 are unchanged and flagged for monitoring.

## 3. Consent and privacy

Required before link issuance:

1. Written consent that participation is voluntary, unpaid or separately compensated if offered, and **non-consequential**.
2. Privacy notice covering: identity handling, retention, no hiring use in this study, right to withdraw.
3. Explicit acknowledgement that scores are for battery validation only.
4. Optional demographic fields collected only with separate consent and used solely for fairness checks.
5. No WhatsApp answer advancement; browser take path only.
6. Data stored under an isolated validation company code; excluded from recruiting analytics and norm tables used for live hiring.

Withdrawal: participant may stop anytime; partial attempts retained as dropout data unless deletion is requested under the privacy notice.

## 4. Participant segmentation

Target **N = 100–200 completers** (invite more to absorb dropout).

| Segment | Target share | Notes |
|---|---|---|
| English | 45–55% | Balanced with Arabic |
| Arabic | 45–55% | MSA professional register |
| Device desktop | ≥40% | Chrome/Safari/Firefox |
| Device mobile | ≥30% | Must include Mobile Safari cohort (≥15 attempts) |
| Role-relevant experience | ≥50% | Supervisor / team-lead / coordinator exposure |
| Early-career / student | ≤30% | For difficulty calibration only |

Randomize locale assignment within language-capable consenters. Do not let participants self-select after seeing item content.

## 5. Exclusion criteria

Exclude from primary psychometric sample (may still be logged separately):

- Incomplete consent
- Duplicate identity / repeated attempt from same person
- Attempt not pinned to `pilot_v2` version IDs above
- Completion time &lt; 8 minutes (speeded / non-effort)
- Completion time &gt; 90 minutes without pause justification
- &gt;20% items unanswered after start (abandoned)
- Known prior exposure to Battery-1 item text (authors, prior pilot completers)
- Assistive-tool misuse that bypasses item content (if detectable)
- Non-consenting demographic fields must not block inclusion in core sample

## 6. Minimum sample requirements

| Analysis | Minimum |
|---|---|
| Overall keep/revise screen | 100 completers |
| EN and AR separate item stats | ≥40 completers per locale |
| Distractor analysis | ≥30 responses per item per locale |
| Reliability (α / ω) | ≥100 completers overall |
| Fairness exploratory checks | ≥30 per compared subgroup cell, else descriptive only |
| Mobile Safari stability | ≥15 Mobile Safari completed attempts |

If minima are not met, decision defaults to **collect more data**, not retire.

## 7. Metrics to capture

### Operational

- Invite → start → complete funnel
- Completion rate, dropout rate, dropout item index
- Total completion time; time per item (`response_time_ms` + event timestamps)
- Browser/device/user-agent; error events; refresh recoveries
- EN vs AR timing differences

### Psychometric

- Item difficulty \(p\) (proportion correct)
- Item-total / item-rest correlation (discrimination)
- Distractor selection frequencies and non-key endorsement rates
- Internal consistency (Cronbach α; McDonald’s ω if feasible)
- Score distribution (mean, SD, skew, floor/ceiling)
- Section / construct subscores (numerical, verbal, logical, SJT, prioritization)

### Equivalence / fairness

- EN vs AR difficulty delta per item and overall
- EN vs AR score mean difference with CI
- DIF exploratory screen (Mantel-Haenszel or logistic) when cell sizes allow
- Fairness by consented subgroups (gender, education band, language dominance) — exploratory, not gate for hiring use

### Feedback

- Structured ratings: clarity, length, language quality, fairness perception
- Free-text confusing items / answer-key challenges
- Device issues checklist (including Mobile Safari)

## 8. Statistical decision rules (keep / revise / retire)

Apply after minima are met. Recommendations only — **no in-study content mutation**.

| Decision | Rule (primary sample) |
|---|---|
| **Keep** | \(0.30 \le p \le 0.90\); discrimination ≥ 0.20; no unresolved key challenge; distractors each &lt; keyed option; EN−AR \(p\) delta within ±0.15 |
| **Revise** | \(p &lt; 0.30\) or \(p &gt; 0.90\); discrimination &lt; 0.15; ≥2 independent wording/key complaints; dominant distractor ≈ keyed option; EN−AR delta &gt; 0.20 without translation defect explanation |
| **Retire** | Discrimination ≤ 0; two keyed options defensible after human adjudication; critical fairness/DIF flag with content cause; or repeated key invalidity |
| **Collect more data** | Any minimum sample cell unmet; unstable SE; Mobile Safari defect rate unresolved; borderline metrics within 0.02 of cutoffs |

### Monitored items (pre-declared)

- **#8 numerical** — difficulty monitoring (internal pilot \(p=0.50\)). Prefer keep unless discrimination collapses or \(p&lt;0.25\) at N≥100.
- **#22 verbal** — ceiling-effect monitoring (internal pilot \(p=1.00\)). Prefer keep/collect more data unless still \(p≥0.95\) with discrimination &lt;0.10 at N≥100, then revise.
- **#7 prioritization** — revised; treat as new item for decisioning (no carry-over of prior confusing-feedback flag unless it reappears).

Battery-level gate for “ready for limited operational validation” (still not approved-for-use):

- Completion rate ≥ 75%
- Reliability α ≥ 0.70
- ≤3 items in revise; 0 retire without replacement plan
- No critical EN/AR inequivalence on &gt;2 items
- Mobile Safari blank-render defect rate &lt; 2% of item transitions
- Zero answer-key invalidations after adjudication

## 9. Later linkage to interview and probation outcomes

Out of scope for this study’s administration, but the protocol must preserve linkage readiness:

1. Store stable `participant_study_id` separate from future application IDs.
2. Retain frozen `assessment_version_id`, score vector, and completion timestamp.
3. Only after a **later explicit ethics/legal approval**, and only for consenting participants who later become candidates/employees, allow keyed linkage to:
   - structured interview ratings
   - probation / 90-day performance indicators
4. Linkage analysis is predictive validation (concurrent/predictive), never reverse-scored into this study’s item keys.
5. Default retention: study dataset remains isolated; linkage is opt-in and auditable.

No offers, hiring stage mutations, or employee creation occur in this validation pilot.

## 10. Execution checklist (when recruitment is authorized)

1. Confirm revised manifest SHA and frozen version IDs.
2. Activate only `pilot_v2` batteries in the isolated validation company.
3. Issue consent + browser links; prohibit production tenant use.
4. Monitor Safari/mobile defect dashboard daily.
5. Freeze recruitment at 200 completers or calendar stop.
6. Lock dataset; run analysis notebook against pinned versions only.
7. Publish keep/revise/retire recommendations; do not mutate items during analysis.
8. Rollback rehearsal: deactivate validation batteries; confirm production/`GLOBAL` unchanged.

## 11. Explicit non-goals

- Not production deployment
- Not approved-for-use
- Not live recruiting analytics inclusion
- Not AI scoring / AI hiring decisions
- Not item editing during the study
- Not participant recruitment in this preparation step
