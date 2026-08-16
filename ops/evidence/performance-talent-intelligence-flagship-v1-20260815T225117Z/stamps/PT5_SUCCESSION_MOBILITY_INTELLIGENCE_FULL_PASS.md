# PT5 — Succession Intelligence + Internal Mobility

**Status:** `PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS`  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**Prior freeze:** `PT4_DYNAMIC_TALENT_MAP_FULL_PASS`  
**Paused:** Production Readiness R7  
**Do not begin:** PT8, R7  
**Next (serial, no owner gate):** PT6 Trajectory + Organizational Capability Intelligence

---

## 0. What shipped

PT5 deepens frozen C6 succession without replacing it, and adds advisory internal-mobility discovery.

Shipped:

- Derived facts: uncovered critical roles, zero ready-now, single-successor dependency, honest bench counts, concentration (default N=3)
- Current holder from employment/JA profile — no second holder record
- Successor comparison via WHY graphs (role-fit + human readiness); no opaque master rank
- Advisory mobility matches over JA career edges + C5 interest facts + PT3 fit
- Explicit Recruiting handoff only; Recruiting OFF → no candidate
- Talent continues with Recruiting OFF
- What-if remains PT8+

Did **not** ship:

- 0–100 bench score
- Silent candidate creation
- Silent transfer / employment mutation
- Cascading what-if simulation
- Replacement of C6 nominations / readiness

---

## 1. Binding authorities preserved

| Authority | PT5 rule |
|---|---|
| C6 succession | Remains SoT for critical roles, plans, nominations, human readiness |
| Employment / JA holder | Canonical; PT never writes a holder row |
| Recruiting | Optional explicit handoff only |
| PT3 role fit | Informs mobility / comparison WHY; never writes JA |
| Wave 4 C1–C6 | Not reopened |
| R7 | Stays paused |

---

## 2. Qualification

Run: `ops/qualify-pt5-succession-mobility.sh`  
Evidence: `ops/evidence/pt5-succession-mobility-20260815T224503Z/`

Proved:

- Dashboard 89/481 + mobile composition
- PT5 unit 18/0 + PT4 predecessor 23/0 + R5C + Wave 4
- Staging DB: empty role uncovered; single-successor risk; no invented candidates; bench_score is None; mobility advisory; no employment mutate; no silent application
- Live intel/map routes not public
- EN/AR single-successor labels

---

## 3. Safe debt

- Holder lookup is employment `profile` jsonb + optional JA assignment peek; not a full org graph
- Mobility seed without JA edges uses the first declared interest as a lateral destination
- Concentration threshold is company setting default 3; no UI editor yet

---

## 4. Next

PT5 frozen. Continue serially to **PT6**. Do not resume R7. Do not start PT8.
