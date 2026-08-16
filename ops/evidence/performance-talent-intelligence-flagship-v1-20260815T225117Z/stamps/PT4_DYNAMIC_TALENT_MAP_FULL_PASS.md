# PT4 — Dynamic Talent Map + Explainability

**Status:** `PT4_DYNAMIC_TALENT_MAP_FULL_PASS`  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**Prior freeze:** `PT3_ROLE_FIT_READINESS_FULL_PASS`  
**Paused:** Production Readiness R7  
**Do not begin:** PT8, R7  
**Next (serial, no owner gate):** PT5 Succession Intelligence + Internal Mobility

---

## 0. What shipped

PT4 is the flagship Talent exploration surface over frozen C5/C6 + PT2/PT3 facts. It is **not** a 9-box product. 9-box remains one derived lens via C6 `project_nine_box()`.

Shipped:

- Governed lenses: Performance × Potential, Potential × Readiness, Role Fit × Readiness, Growth × Contribution (honestly unknown until PT6 trajectory exists)
- One lens selector; progressive org filters from employee profile jsonb
- Unknown stays unknown — never forced into a middle bucket
- Same `canonical_employee_facts()` across lens switches; only the projection changes
- WHY drawer: lens, consumed/missing evidence, classification WHY id, role-fit WHY
- Drill into Talent Profile remains the existing workspace
- HR Web Map tab (EN/AR/RTL) on the existing Talent workspace

Did **not** ship:

- Permanent 20-filter wall
- Excel-first grid
- Dashboard card spam
- Unexplained colored dots
- Decorative AI
- Frontend Talent math
- Universal Talent score
- Automatic HiPo

---

## 1. Binding authorities preserved

| Authority | PT4 rule |
|---|---|
| C5 human Potential | Read only. Map never writes it. |
| C6 designated HiPo | Read only. Lens switch does not rewrite HiPo. |
| C6 9-box | Existing derived projection; one available lens. |
| PT2 classifications / WHY | Consumed as evidence pointers. |
| PT3 role fit | Consumed as evidence pointers. |
| Wave 4 C1–C6 | Not reopened. |
| Wave 5 | No second analytics engine. |
| R7 | Stays paused. |

---

## 2. Qualification

Run: `ops/qualify-pt4-dynamic-talent-map.sh`  
Evidence: `ops/evidence/pt4-talent-map-20260815T224352Z/`

Proved:

- Dashboard 89 files / 481 tests + mobile composition
- PT4 unit 23/0 + PT3 predecessor 43/0 + R5C + Wave 4
- Staging DB: missing performance stays unknown; not stuffed in middle; same potential/HiPo across lenses; WHY present
- Live `/map` and `/models` are not public
- EN/AR/RTL Map tab

---

## 3. Safe debt

- Growth × Contribution is honestly unlabeled until PT6 publishes trajectory
- Org filters read `employees.profile` jsonb only (no invented department columns)
- Map list is a simple people + WHY drawer, not a visual 2D canvas

---

## 4. Next

PT4 frozen. Continue serially to **PT5**. Do not resume R7. Do not start PT8.
