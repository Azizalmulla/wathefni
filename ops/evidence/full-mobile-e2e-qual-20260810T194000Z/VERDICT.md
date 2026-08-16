# Full mobile E2E product qualification — VERDICT

**Stamp:** `20260810T194000Z`  
**Host:** build machine + prod `root@76.13.63.68`  
**Canary:** Aziz (HR) · Talal (Employee) · company `WATHEFNI`

## Rule applied

**API PASS ≠ MOBILE PASS.** A row is `MOBILE_PASS` only when the real app UI path was exercised and the visible result matched backend/DB truth.

## Counts (merged matrix)

| Verdict | Count |
| --- | ---: |
| MOBILE_PASS | **0** |
| API_SPINE | 37 |
| BLOCKED | 21 |
| DEBT | 4 |
| FAIL (product) | **0** (after schedule/bank harness reclassification) |

## SHIP / NO-SHIP

| Product | Verdict | Why |
| --- | --- | --- |
| **HR mobile** | **NO-SHIP** | Zero MOBILE_PASS. Leave Confirm owner-device smoke still open. Face ID / auto-lock / Forgot PIN / EN·AR·RTL / deep-link UI unproven. Multi-tenant module-off tenants (BOOT*) absent on this prod workspace. |
| **Employee mobile** | **NO-SHIP** | Zero MOBILE_PASS. Schedule/leave/payslips/docs/onboarding API spines green for Talal; bank ESS correctly fail-closed. Physical PIN/Face ID/locale/navigation unproven. |

Canary-only continued internal use of existing OTA builds remains acceptable under continuous-wave process; **broad release is NO-SHIP**.

## API spines proven (not ship)

- Priorities totals ↔ Leave / Onboarding / Documents / Tasks / Attendance / Shift swaps
- Leave approve prepare→confirm→DB `approved`
- Onboarding HR-actionable queue reachable; waive confirm
- Documents `needs_review` queue + mark reviewed
- HR task mark done
- Candidate CV authenticated preview
- Cross-tenant leave detail denied
- Assistant capabilities catalog
- Destination list clean (no `/ranking` / soft-dead filtered candidates)
- Talal `/app/me` · home · leave · payslips · documents · onboarding · notifications · `/app/workday` · schedule history · shifts today/upcoming · attendance
- Bank `/app/bank` → 403 `bank_ess_not_allowlisted` when feature disabled
- Manager-role leave list HTTP reachable on WATHEFNI fixtures

## Release blockers

1. **No physical device/sim on qual host** → cannot stamp MOBILE_PASS for any UI path.
2. **Leave Confirm sheet** — HTTP SOD green; owner Confirm tap smoke still required post-OTA `7c52c216-…`.
3. **Auth/local-lock physical** — Face ID, auto-lock, Forgot PIN, mode switch, sign-out.
4. **Multi-tenant module matrix incomplete** — only 2 companies with `company_modules` on prod; BOOTPRE01/BOOTPOST01/BOOTMIX01 / TENANTISO* absent this run.

## Safe post-launch debt (non-blocking)

- Static harness drift (`verify-capability-foundation` documents back string; `verify-hr-deep-nav-blockers` exact `"/candidates"`).
- Navigation ergonomics Candidates/Interviews `onBack`.
- Colour-system untokenised literals; Inbox density cream ledger.
- RTL single-source manual `textAlign` / `row-reverse` — clear with physical AR pass.

## Evidence

- `matrix-merged.json` / `matrix-compact.json`
- `api/full-mobile-e2e-qual-out/` · `api/full-mobile-e2e-qual-b-out/`
- `static/` verify batch
- Canvas: `full-mobile-e2e-product-qual.canvas.tsx`
