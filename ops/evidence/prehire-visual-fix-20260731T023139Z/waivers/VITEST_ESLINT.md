# Vitest / ESLint classification (correction pass)

## Vitest — original 4 failures

### 1. `src/lib/candidateProfilePresentation.test.ts` › `shows No job assigned and non-technical stage for general candidates`
- **Evidence:** `expected '—' to be 'New'`
- **Classification:** **Unrelated pre-existing / product-contract drift** (not introduced by visual chrome). Held/general candidates intentionally use quiet Stage `—` (see `CandidatesTable.test.tsx` which already asserts this).
- **Waiver recommendation:** Update the presentation unit expectation to `—` in a candidates-list contract PR; do **not** block visual ship.

### 2–3. `src/components/PlatformIntegrationsPanel.test.tsx`
- `owner with settings.manage + calendar.sync sees Platform Integrations`
- `hr_admin with settings.manage but without calendar.sync does not see Platform Integrations`
- **Evidence:** Settings `EmailSendingCard` throws `Cannot read properties of undefined (reading 'map')` on `view.choices` while the Settings page mounts under these tests.
- **Classification:** **Unrelated pre-existing** (Settings / email-sending mock gap; hybrid-email track). Not caused by visual shell/pages work.
- **Waiver recommendation:** Fix Settings email mock/`choices` guard in the email/Settings track; waive for visual correction ship.

### 4. `src/EmployeeProfile.repro.test.tsx` › `opening an employee from the directory does not crash the dashboard`
- **Evidence (before fix):** waited for Overview copy that this fixture does not render (boots post-hire Employees).
- **Classification:** **Brittle fixture; fixed in this pass** by waiting for the Employees nav button instead of Overview greeting.
- **Status after correction:** **PASS** (included in `verify/vitest-visual-related.log`).

## Vitest — visual-related targeted after fixes
`App.test.tsx`, `JobsPage.test.tsx`, `EmployeeProfile.repro.test.tsx` → **18/18 PASS**.

## ESLint — changed files
Changed-file eslint still reports pre-existing `react-hooks/set-state-in-effect` / `react-refresh/only-export-components` on Jobs/Candidates/Reports patterns that predate this correction pass.
- **Introduced by this phase:** none identified beyond temporary unused-refresh leftovers (removed).
- **Waiver:** do not expand repo-wide eslint cleanup into the visual ship.
