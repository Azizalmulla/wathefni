# Setup Console Phase 2C — Employee App Access Enterprise Hardening

**Status:** PASS (canary qualified) · **Frozen**  
**Depends on:** Phase 2B access-mode semantics (unchanged) · Wave 4 org-unit IDs  
**Do not auto-start:** next Setup Console phase · Employee App P1 · Auth Wave 2 Phase 6

## Verdict

**PASS** — canary live smoke **35/0**

Evidence: `ops/evidence/setup-console-phase2c-20260808T023702Z`  
Canary: `/opt/wathefni/ops/evidence/setup-console-phase2c-20260808T023702Z`

Smoke: `wathefni-orchestrator/smoke-test-setup-console-phase2c.py`

## Canonical org-unit migration result

| Before (2B) | After (2C) |
|---|---|
| `selected_departments: ["Sales"]` name strings | `selected_department_org_unit_ids: [<uuid>]` |
| Match via `profile.department` | Match via current `department_unit_id` (assignment history) |
| Rename breaks membership | Rename is display-only — IDs unchanged |
| Duplicate names ambiguous | IDs disambiguate |

**Backfill:** On policy GET, name-only policies run `migrate_selected_department_names_to_ids`:

- Unique name → ID (persisted)  
- Multiple matches → **Needs Attention** (never guess)  
- Unmatched name → Needs Attention  

Historical names/labels retained in settings + admin audit. Archived/missing selected IDs surface Needs Attention; HR removes/replaces explicitly (`resolve-attention`). No silent remap by name.

## Picker / preview architecture

```
Departments picker
  → list org units (id, name, status, active count)
  → store/select org_unit_id[]

Employees picker (10k+)
  → server search + filters (department_org_unit_id, status)
  → page size ≤ 100 (UI default 40)
  → select/deselect page; selection Set persists across pages/search
  → never load full roster client-side

Preview
  → counts first (gain / lose / unchanged)
  → optional POST …/preview/details bucket drill-down (paged + searchable)
  → reason codes (selected department / no longer in scope / …)

Apply
  → batch UPDATE flags + existing invite/revoke (unchanged 2B semantics)
```

## Scale measurements

| Metric | Result |
|---|---|
| Live search page (50 rows / 98 total) | **24.8 ms** |
| Live preview everyone (98 active) | **43.9 ms** |
| Synthetic matcher 100 | **0.06–0.11 ms** |
| Synthetic matcher 1,000 | **0.66–5.1 ms** |
| Synthetic matcher 10,000 | **6.0–10.4 ms** |
| Client full-roster load | **Never** (page ≤100) |

See evidence `results.json` → `scale`.
## Reconciliation (re-proven)

| Event | Behavior |
|---|---|
| Department rename | Membership unchanged (ID) |
| Employee dept move | Reconcile vs current `department_unit_id` |
| Archive/delete selected unit | Needs Attention; HR chooses remove/replace |
| Termination / reactivation | Existing employment + reconcile gates |
| Migration org update | `allow_invite=False` preserved |
| Future hires | 2B semantics unchanged (Everyone/Dept/Selected) |

## Remaining Setup Console gaps (later)

1. Cross-company access policy templates  
2. Adaptive Employee App shell composition (Phase 5)  
3. Optional virtualized windowing library (current paging is sufficient for 10k)  
4. Auto-suggest replacements for archived units (still explicit HR choice)

## Key files

- `wathefni-orchestrator/employee_app_access.py`  
- Setup routes in `app.py` (preview/details, resolve-attention, scale, employees filters)  
- `EmployeeAppAccessPolicyCard.tsx` · `setup-console/api.ts`  
