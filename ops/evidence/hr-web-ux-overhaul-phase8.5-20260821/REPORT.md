# OctoHR HR Web Product UX Overhaul — Phase 8.5

**Migration Completeness Closure**  
As of 2026-08-21 · last structural UX cleanup before the final visual/palette phase · no palette freeze · no production deploy · no already-migrated workflow redesign

Phase 8 checkpoint: `6c17f82d` on `authority-cutover`.

---

## Verdict

The Surface Registry no longer overloads `canonical`. Every registered surface now carries `inventory_status`, `ux_migration_status`, and `ux_phase`, and the census/contracts show **0 partial** and **0 missed** rows.

Compliance (the only previously missed product page) is fully migrated onto shared chrome. Remaining primary-chrome leftovers on Organization, Employee 360, Onboarding, Attendance, Payroll inner tabs, Assistant, and Jobs form were closed without redesigning those workflows. Confirm overlays are one shared `ConfirmDialog`. AnalyticsPage stays as required C6/entitlement resilience, not a second production path. Selected Job position is URL-backed via `position_code`.

Backend remains authoritative for permissions, modules, `allowed_actions`, tenant isolation, compliance review/reminders, payroll money, ranking, and audit. Palette is not locked. Stop here — do not start the final palette phase.

---

## Registry semantics

| Field | Meaning |
| --- | --- |
| `inventory_status` | `live` · `alias` · `adjacent_setup` · `preauth` · `excluded` |
| `ux_migration_status` | `migrated` · `preserved_specialist` · `preserved_overlay` · `partial` · `missed` · `n_a` |
| `ux_phase` | `3`–`8.5`, or `null` for non-product inventory |
| `migration_status` | Legacy compatibility only (`canonical` / `preserve` / `consolidate` / …). Do not treat `canonical` as the UX truth. |

---

## Completeness counts (exact)

Census: `HR_WEB_SURFACE_CENSUS_PASS  34 pages, 34 nav items`

| Class | Count |
| --- | --- |
| Registered surfaces | **209** |
| `ux_migration_status=migrated` | **188** |
| `ux_migration_status=preserved_overlay` | **15** |
| `ux_migration_status=preserved_specialist` | **0** |
| `ux_migration_status=n_a` | **6** |
| `ux_migration_status=partial` | **0** |
| `ux_migration_status=missed` | **0** |
| `inventory_status=live` | **203** |
| `inventory_status=alias` | **1** (`legacy.migration-sync`) |
| `inventory_status=adjacent_setup` | **3** (Setup Console modules / policies / classic) |
| `inventory_status=preauth` | **2** (`auth.sign-in`, `auth.invite`) |
| `inventory_status=excluded` (in registry) | **0** (`employee_app` remains an exclusion row, not a registry surface) |

### Intentionally preserved overlays (15)

`drawer.calendar.event`, `drawer.onboarding.detail`, `drawer.leave.detail`, `modal.employees.approver-pick`, `modal.leave.file`, `modal.interviews.action`, `modal.employees.add`, `modal.employees.edit`, `modal.employees.import`, `modal.employees.activation`, `modal.candidates.add-to-job`, `modal.shared.confirm`, `modal.payroll.export-detail`, `modal.attendance.import`, `fallback.analytics.legacy`

These are local mutation/detail overlays (or the C6-off analytics fallback). They are not leftover product pages.

### n_a inventory (6)

- Alias: `legacy.migration-sync` → `?page=employees&view=migration`
- Adjacent Setup Console (not HR Web chrome): modules, policies, classic
- Pre-auth: sign-in, invite

`settings.advanced` remains a **live migrated** Settings section whose legacy `migration_status=consolidate` records the naming drift (`settings.platform` vs `advanced`). It is not unfinished UX.

---

## What changed

### Compliance (only missed page)

- Shell owns `HrPageHeader` (People spine / Post-Hire eyebrow).
- Findings / All documents on `HrSurfaceTabs`, URL-backed via `?tab=`.
- Bucket filters URL-backed via `?status=` (`needs_review` default omitted from the URL).
- Nested registry rows: `tab.compliance.findings`, `tab.compliance.register`, `tab.compliance.filter.*`.
- `ResourceState` for loading / error / empty. Semantic tokens. EN/AR/RTL unchanged.
- `getPosthireCompliance`, `compliance_send_reminder`, `compliance.read` / `compliance.manage`, and Setup Console document-requirements ownership are unchanged.

### Partial chrome closed (no workflow redesign)

- Organization advanced rail uses `HrSurfaceTabs`; overview chips tokenized.
- Employee 360 chrome (approval strip, empty, quiet stats, profile cards) tokenized.
- Onboarding queue/item/drawer cream hex tokenized; queue tabs were already `HrSurfaceTabs`.
- Attendance capture + operations inner tabs use `HrSurfaceTabs`; capture remains local on purpose.
- Payroll payslip / external / close / statutory inner tabs use `HrSurfaceTabs`; policy panels use `text-end` + semantic tokens.
- Assistant: physical `ml-auto` / `border-l` → logical `ms-auto` / `border-s`; leftover hover-translate removed.
- Jobs form drawer: same RTL logical properties; cream canvas → `semantic-canvas`.

### ConfirmDialog

PostHire-local `ConfirmDialog` removed. Backend confirmation steps and caller-supplied confirms now use the shared `ConfirmProvider` / `useConfirm`. Server confirmation text is still shown; mutations still re-submit through `runPosthireAction`.

### AnalyticsPage fallback — kept

Governed HR Intelligence is the qualified production path. `AnalyticsPage` is still mounted when `gateOff` is true (C6 / `intelligence_surfaces` / company entitlement off). Removing it would collapse that fail-closed case to an empty “not enabled” panel and drop the remaining analytics experience for tenants without governed surfaces. Registered as `fallback.analytics.legacy` (`preserved_overlay`). Not a second KPI authority.

### Jobs selected position

`?position_code=` is written for the selected opening, distinct from Jobs search `q`. Refresh/back/deep-link restore the workspace after the list hydrates. Ranking still uses `position_code` on its own page.

---

## Evidence

- Census: `node ops/full-web-e2e/run-hr-web-surface-census.cjs` → `HR_WEB_SURFACE_CENSUS_PASS  34 pages, 34 nav items`
- Dashboard vitest: Phase 4–8 + 8.5 contracts, Surface Registry coverage, Compliance Wave 1, Analytics Wave 1, Payroll Wave 1, Organization Wave 1, chrome, interaction perf — pass
- Completeness snapshot pinned in `WorkspacePhase85Contract.test.ts`

---

## Explicitly not done (stop)

- Final palette / launch qualification
- Shared `Button` / `Card` / form focus still cream hex + hover-translate by design
- Calendar event drawer and other preserved overlays stay local (documented)
- Activity actor / category / action_type stay local (Phase 8)
- No production deploy
