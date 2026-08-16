# Shifts Commercial Loop Audit

**Mode:** research + product architecture only — **no** code, deploy, manager widening, real-reminder enablement, or freeze reopen  
**Date:** 2026-08-03  
**Authority freeze:** `ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` (`PROD_CONTROLLED_WAVE6C_SHIFTS_GO`)  
**Prior research:** Wave 0 prod truth · Wave 0B Kuwait rostering (`ops/evidence/shifts-wave0b-kuwait-rostering-research-20260802T180006Z/`)  
**Evidence tip:** Wave 6C `ops/evidence/shifts-wave6c-20260803T033336Z/REPORT.md`

---

## Verdict in one line

The **publish → notify → acknowledge → coverage → PAM-export** loop exists end-to-end in product. A real Kuwait **multi-site** HR team **cannot** run it commercially without engineering/allowlist change: production is a **one-HR / one-employee canary**, not an operated workforce loop.

---

## 1. Current product truth (journey)

| Step | Product reality | Who can do it in prod today |
|---|---|---|
| **Create schedule** | Board L0 create/reschedule/cancel; Wave 4 templates→draft; Wave 6 rotations→draft. Overnight/split/lifecycle/leave/availability gates. Concurrency + audit reason. | **Aziz only** (`96599338566`) for real subjects |
| **Publish** | Wave 5: draft → review → approve → publish → immutable L0 version + provenance. Coverage warn/block. Concurrent publish lock. | Same HR allowlist |
| **Notify** | Outbox: events → per-channel deliveries → ack-once. Seven fail-closed real-delivery guards. | **Real:** Talal only, channels `app` + `email`, consent required. WhatsApp/Teams/Telegram/SMS = mock/preference ladder only |
| **Acknowledge** | Wathefni-owned ack-once (`shift_notification_acks`). Employee app today/upcoming read. | **Talal** read + ack. No employee write / swap / claim |
| **Swaps & availability** | Schema + UI + self-decision bans proven synthetically. | Real decide = HR only. Talal cannot swap/claim. Organic use historically idle (Wave 0) |
| **Coverage gaps** | Min staff by role/site/branch/team/window; open shifts as unresolved findings; warn vs block at publish | HR configures/rules on Publish tab |
| **Leave conflicts** | Leave owns leave; Shifts gates (`require_ack` / `block` / `cancel_shift`). No balance mutation. | Create-time / leave-approve surfaces. **Integrity jobs OFF** → no auto recon drain |
| **Escalation** | Delivery retry → `terminal_failed`; integrity flags on Reconciliation tab; coverage block at publish | **No** manager/branch/SLA escalation chain (manager identity/scope absent) |
| **PAM-ready evidence** | `pam-export@1.0.0` EN/AR CSV + printable + fingerprint; status always `manual_submission_required` | Export **GO**. Submit **NO-GO**. Official form field mapping **unresolved** |

**Live commercial shape today**

```
Aziz creates/publishes → outbox notifies Talal (app+email) → Talal reads+acks
→ coverage/leave gates at publish/create → PAM export pack → human PAM portal
→ everyone else: still Excel / WhatsApp / manual chase
```

---

## 2. Can a real Kuwait multi-site HR team operate without engineering?

**No — not in the current freeze posture.**

| Buyer expectation | Current truth |
|---|---|
| Multiple HR / site leads schedule their sites | One HR operator; manager allowlist **empty**; no production manager identity/scope/branch/team |
| Whole workforce sees published roster | Employee-app allowlist = **Talal only** |
| Publish fans out notifications | Real notify allowlist = **one recipient**; timers/reminders **off** |
| Missed ack escalates to site manager | No scoped-manager chain; terminal delivery flags only |
| PAM pack → portal without ops help | Export exists; form mapping + submission stay human/legal |
| Add a second employee to the loop | Requires owner change-control + consent + allowlist wave — not self-serve |

**Without engineering** means: cannot expand HR operators, cannot enable managers, cannot broaden notify/app, cannot turn on reminder jobs. Those are freeze hard bans, not missing buttons.

---

## 3. Operator / buyer friction

### Still Excel / WhatsApp / manual

1. **Non-Talal employees** learn the roster outside Wathefni (Excel share / WhatsApp group) — Wave 0B market baseline still true for the unfrozen majority.
2. **Call-outs / open-shift fills** for the real workforce still land on WhatsApp; open-shift product is HR-mediated and employee claim is off.
3. **Reminders off** → “did you see tomorrow’s shift?” is manual.
4. **Integrity jobs off** → leave clash after the fact is not auto-surfaced; HR must catch at create or run recon manually.
5. **PAM** → print/export then type/upload into Ashal/PAM; mapping to official fields unresolved.
6. **Compliance profiles warn-only** → statutory risk may still be tracked in spreadsheets until legal clears block profiles.

### HR-only model friction

- All real mutation collapses to **one person** → multi-site buyers will bounce or keep Excel per site.
- Swaps/availability UI exists but **cannot decentralize** without manager scope + employee write (both frozen).
- Publish feels “done” in the UI while **commercial communication** to the workforce is incomplete — biggest honesty gap for demos vs production.

### Loop clarity (commercial)

| Segment | Clear? |
|---|---|
| Create → publish (authority) | **Yes** — L0 + version immutability is sharp |
| Publish → notify → ack | **Clear in product; incomplete in production scale** |
| Coverage at publish | **Yes** |
| Leave conflict honesty | **Yes** (Leave owns leave) |
| Evidence / PAM | **Clear as export-not-submit** — must stay that way in sales copy |
| Escalation | **Weak** — not a buyer-visible management loop |

---

## 4. Table-stakes vs differentiation

### Table-stakes (competitors already claim — Bayzat, ZenHR, AiTIME, Qandle class)

- Drag/create roster, multi-site/branch language  
- Publish + employee mobile view  
- Shift swap with manager approval  
- Coverage / understaffed views  
- Leave conflict awareness  
- Attendance/payroll sync stories (often the real purchase reason)  
- Bilingual EN/AR  

Wathefni **partially** matches create/publish/coverage/leave-gate/ack **in code**, but **not** at competitor commercial breadth (MSS + ESS + notify + timers).

### Genuinely differentiated (keep and sell carefully)

1. **Canonical L0 + immutable publish versions** — audit-grade “what was the official roster,” not a mutable spreadsheet cell.
2. **Ack-once notification authority owned by Wathefni** — channel is delivery, not source of truth (fits Kuwait WhatsApp chaos).
3. **Leave-aware scheduling without stealing Leave authority** — system-of-action honesty across freezes.
4. **PAM export pack with explicit non-submission** — Kuwait-local evidence posture vs generic “compliance” claims.
5. **Fail-closed controlled rollout** — allowlists, consent, kill switch, exclusions (trust for regulated buyers; friction for growth).

### Do not claim (competitors lean here; we must not)

- Full multi-manager MSS at production scale  
- Broad WhatsApp workforce messaging as contracted  
- Automated PAM/Ashal submission or legal-compliance guarantee  
- Attendance ingest or payroll money from Shifts  
- AI scheduling / auto-fill

---

## 5. Strongest positioning

**Not:** “Replace Bayzat/ZenHR shift module for every site manager.”

**Yes:**  
> Wathefni Shifts is the **authority layer** for Kuwait private-sector rosters: publish an immutable schedule, prove who was notified and who acknowledged, catch coverage and leave conflicts before go-live, and produce a **PAM-ready evidence pack** — without pretending Shifts is payroll, attendance, or the government portal.

**Buyer that fits now:** owner-led / small HR team, controlled pilot, high audit sensitivity, already on Wathefni Employees 360 + Leave.  
**Buyer that does not fit yet:** multi-site ops with site managers chasing WhatsApp call-outs all day.

---

## 6. Exact missing commercial loop

Not “rebuild Shifts.” The **missing middle** after publish:

```
[publish OK]
    ↓
[notify ALL affected employees on contracted channels]  ← blocked (1 recipient)
    ↓
[ack visibility + chase for missing acks]               ← timers/reminders OFF
    ↓
[site/manager handles exceptions / swaps]               ← manager scope NO-GO
    ↓
[coverage remains true through the week]                ← jobs OFF; WhatsApp fills gaps
    ↓
[PAM evidence from published truth]                     ← export OK; mapping/submit human
```

That middle is **policy + identity + channel contract**, mostly already built behind allowlists — not a greenfield module gap.

---

## 7. What must remain frozen

From the freeze — do not reopen for commercial pressure:

- Manager allowlist / `APPROVED_HR_OPERATORS` widening without owner wave  
- Real reminders / integrity / operator timers  
- Broad employee-app write or notify recipients/channels  
- PAM automated submission / legal-compliance claim  
- Payroll money · Attendance ingest · Leave balance mutation · AI  
- L0 authority, version immutability, self-decision bans, ack-once, notify fail-closed guards  

Unresolved legal items stay **out of code waves**: Ramadan/midday windows, rest-weekday convention, PAM form field mapping, hitch travel ownership, contracted second channels.

---

## 8. Recommended changes (focused — no broad rebuild)

**Product / GTM (no wave required)**

1. Sales and UI honesty: label production as **controlled HR pilot**, not multi-site MSS.  
2. Demo script = create → publish → notify (Talal) → ack → coverage warn → PAM export — then explicitly say what stays manual.  
3. One-pager: Excel/WhatsApp replacement **path**, not claim of completed replacement.  
4. Keep PAM copy as **export evidence / manual submission required**.

**Ops / research (no feature wave)**

5. Customer interview pack (multi-site retail / hospitality / security) validating which missing-middle step kills the deal first: notify breadth vs manager scope vs PAM mapping.  
6. Contract checklist before any second real channel (WhatsApp provider, consent, kill switch still on).

**Do not do now**

- Rebuild board/UI  
- Invent escalation SLA product  
- Wire Attendance or Payroll money  
- Enable timers “just for demo”

---

## 9. Exact next wave?

**None for implementation.**

There is **no proven code gap** in the commercial loop modules themselves (create/publish/notify/ack/coverage/leave-gate/PAM export all exist and are freeze-qualified). The blocker for multi-site commercial operation is the **controlled freeze posture** (identity, allowlists, channels, timers) plus **unresolved legal/mapping** items.

Any future work is **owner change-control**, not an engineering discovery wave:

| If owner prioritizes… | Then the *only* coherent next wave shape |
|---|---|
| Prove loop with 2–3 real employees | Controlled **notify+ack expansion** (named subjects, consent, same channels) — still no managers, no timers, no PAM submit |
| Multi-site ops | **Manager identity/scope foundation** research → then a scoped manager wave — large; do not start casually |
| PAM sales story | Legal **form-mapping** research only — still no auto-submit |

Until that owner decision: **Shifts stays frozen; commercial loop audit closes as research.**

---

## Sources (primary)

- `ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`  
- `ops/evidence/shifts-wave6c-20260803T033336Z/REPORT.md`  
- `ops/evidence/shifts-wave6b-20260803T021530Z/REPORT.md`  
- `ops/evidence/shifts-wave5b-20260803T005831Z/REPORT.md`  
- `ops/evidence/shifts-wave0b-kuwait-rostering-research-20260802T180006Z/REPORT.md`  
- `ops/evidence/shifts-wave0-prod-truth-20260802T174657Z/REPORT.md`  
- Market: Bayzat / ZenHR / AiTIME / Qandle shift claims; PAM/Ashal working-hours declaration context (Res. 15/2025 family)
