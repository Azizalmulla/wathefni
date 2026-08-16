# Employees 360 Wave 0 — Production truth and risk inventory

**Stamp:** `20260801T184148Z`  
**Mode:** Read-only production inventory. **No code, schema, config, permission, data, or behavior changes.**  
**Mutations performed:** none  
**Frozen baselines preserved:** pre-hiring + Wave D (inbound allowlist `WATHEFNI`, `INBOUND_EMAIL=on`, `MAILBOX_SYNC=off`, `INTAKE_RETENTION_EXECUTE=off`)

**Evidence path:** `ops/evidence/employees360-wave0-prod-truth-20260801T184148Z/`

| Artifact | Path |
|---|---|
| This report | `REPORT.md` |
| Read-only inventory script | `verify/wave0_readonly_inventory.py` |
| Production inventory JSON | `raw/prod-run3/wave0-inventory.json` |
| Production summary JSON | `raw/prod-run3/wave0-summary.json` |
| Live process flags (secrets redacted) | `raw/prod-extra2/live-flags-filtered.txt` |
| Extra SQL / orphans / grants | `raw/prod-extra/`, `raw/prod-extra2/` |
| Backup listings | `raw/prod-run3/backups-ls.txt`, `raw/prod-extra2/daily-backups.txt`, `raw/prod-extra2/offsite-backups.txt` |

---

## Verdict

| Question | Result |
|---|---|
| Wave 0 inventory complete? | **PASS** |
| Production data mutated? | **No** |
| Active external-customer employee data at immediate duplicate/collision risk? | **No** — only `WATHEFNI` has employees today |
| Latent architectural P0 risks still open? | **Yes** |
| Wave 1 local containment engineering | **GO** |
| Wave 1 production deploy / repair / constrain / merge | **NO-GO** without separate owner approval after local evidence |

---

## Executive snapshot

Production employee footprint is small and currently internal-only:

| Metric | Value |
|---|---|
| Database | `wathefni` (production marker confirmed) |
| Companies in DB | 12 |
| Companies with employees | **1 (`WATHEFNI`)** |
| Employee rows | **4** |
| Employment status | `active` = 2, `NULL/blank` = 2, `left` = 0 |
| Phone formats stored | all `965…` (11 digits) |
| Local-vs-965 duplicate groups | **0** |
| Exact phone duplicate groups | **0** |
| Email duplicate groups | **0** |
| Keys whose suffix ≠ stored phone | **0** |
| Orphan employee-linked rows | **3** (`employee_messages` → synthetic `WATHEFNI-P0-DUP-1`) |
| Active manager scopes | **0** |
| Users with both `employees.manage` + `employees.status.approve` | **1** (WATHEFNI owner) |
| `self_approved_internal_canary` rows | **1** (WATHEFNI only) |
| `UNIQUE (company_code, phone)` | **Absent** |

**Immediate active-customer data risk:** Low for external tenants (no employee rows). Residual internal risks are real: null employment statuses, synthetic orphans, unrestricted canary approval mode in code, and phone-canonicalization split still present in creation/lookup paths even though no live collision exists yet.

---

## 1. Employee schema / indexes / constraints (production)

### `employees`

Primary key: `employee_key` only (not composite with `company_code`).

Notable columns observed:

- `employee_key`, `phone` (NOT NULL), `company_code` (NOT NULL)
- `app_key`, `name`, `email`, `position_title`
- `hire_date`, `start_date`
- `onboarding_status`, `documents_pending`, `documents_complete`, `compliance_status`
- `profile` jsonb, `raw_json` jsonb
- `employment_status` (**nullable**, no CHECK for `active|left`)
- `device_user_id`
- timestamps

Indexes:

| Index | Meaning |
|---|---|
| `employees_pkey` | UNIQUE(`employee_key`) |
| `employees_company_app_key_uq` | UNIQUE(`company_code`,`app_key`) where app_key set |
| `idx_employees_device_user_id` | UNIQUE(`company_code`,`device_user_id`) where set |
| `idx_employees_company` | btree company |
| `idx_employees_phone` | btree phone (**not unique**) |
| `idx_employees_onboarding` | btree onboarding_status |

**Missing and material:**

- No `UNIQUE (company_code, phone)`
- No CHECK constraint on `employment_status`
- No immutable `person_id` / `employment_id`
- Soft-hub children mostly lack composite tenant FKs

### Soft-hub FK reality

- `onboarding_items` FK → `employees(employee_key)` only — **no `company_code` column** on onboarding_items
- `compliance_documents` FK → `employees(employee_key)`; `company_code` nullable/additive
- `employee_documents` FK → `employees(employee_key)`
- App integrity scan covers only a subset of child tables and still misses `employee_messages`, sessions, invites, status changes, org assignments, file_registry, onboarding in its declared list

---

## 2. Feature flags and enabled post-hire capabilities

### Live orchestrator process environment (authoritative for runtime)

| Flag | Production value | Effect on Employees 360 |
|---|---|---|
| `WATHEFNI_ENV` | `production` | Production identity |
| `WATHEFNI_EXPECTED_DATABASE_NAME` | `wathefni` | DB pin |
| `WATHEFNI_DATABASE_ENVIRONMENT_MARKER` | `wathefni-production-isolation-v1` | Isolation marker |
| `WATHEFNI_DOC_UPLOAD` | **on** | HR document upload enabled |
| `WATHEFNI_EMPLOYEE_NEXT_ACTIONS` | **on** | Ranked next-actions panel enabled |
| `WATHEFNI_LEAVE_BALANCES` | **on** | Leave balances observe path enabled |
| `WATHEFNI_ONBOARDING_SEED` | **off** | Checklist seed on create/hire inert |
| `WATHEFNI_EMPLOYEE_APP` | **off** | Employee app / activation commercially dark |
| `WATHEFNI_ORG_HIERARCHY` | **UNSET → default off** | Org admin APIs dark |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | **UNSET → default off** | Mark/waive from 360 inert |
| `WATHEFNI_INBOUND_EMAIL` | on | Frozen pre-hire inbound |
| `WATHEFNI_INBOUND_ALLOWED_COMPANIES` | `WATHEFNI` | External inbound still disabled |
| `WATHEFNI_MAILBOX_SYNC` | off | Frozen |
| `WATHEFNI_INTAKE_RETENTION_EXECUTE` | off | Frozen |

Note: older handoff text said `DOC_UPLOAD=off`. Live process now has **`DOC_UPLOAD=on`**. Wave 0 records current truth.

### Company modules (post-hire)

Only **`WATHEFNI`** has post-hire people modules enabled:

- onboarding, compliance, attendance, shifts, leave, payroll, analytics

`employee_app` module is not enabled. Other companies in `companies` have **no** post-hire people modules enabled in this inventory.

---

## 3. Employee creation / lookup path inventory (code + production data)

| Path | Phone normalization | Key minting | Dedup / lookup | Prod evidence |
|---|---|---|---|---|
| Manual create `create_company_employee` | `canonical_employee_phone` (8 → `965…`) | `{COMPANY}-{canonical}` | `ON CONFLICT (employee_key)`; phone existence via exact lookup | 1 row with `source=dashboard_roster` |
| CSV/XLSX import | Uses canonical phone before create | Same as manual | Exact phone existence + in-file dups | No separate import batch table for employees |
| Recruiting hire `hire_operations._employee_transaction` | `digits()` only (no 8→965) | `{COMPANY}-{digits}` | Match by `app_key` or exact `employee_key`; does **not** set/clear `employment_status` | `hire_operations` table empty (0 rows) |
| Employee phone lookup `find_employee_by_phone` | Exact `phone=` match only | n/a | Does **not** use `phone_identity_candidates` | Current rows all already `965…`, so latent |
| Employee app auth | Depends on stored phone / active status | n/a | Left employees ineligible | App flag OFF |
| Integrations | No live HRIS/SCIM employee create path found in this inventory | — | — | None observed |

**Creation-path conclusion:** the hire-vs-roster canonicalization split remains a live code defect. Production currently has **no materialized local-vs-965 collision**, because all four stored phones are already `965…` and hire_operations is empty.

---

## 4. Duplicate classification

### Exact duplicate classes

| Class | Groups | Employees involved | Tenants | Severity now |
|---|---|---|---|---|
| `exact_phone_duplicate` | 0 | 0 | — | None live |
| `local_vs_965` canonical collision | 0 | 0 | — | None live; **latent P0 in code** |
| `repeated_email` | 0 | 0 | — | None live |
| `key_suffix_ne_stored_phone` (phone edited after key mint) | 0 | 0 | — | None live |
| `key_uses_local_8_not_canonical_965` | 0 | 0 | — | None live |

### Affected tenant / employee counts

| Scope | Tenants with employees | Employee rows | Duplicate-affected employees |
|---|---|---|---|
| All production | 1 (`WATHEFNI`) | 4 | 0 |
| External / non-WATHEFNI | 0 with employees | 0 | 0 |

### Classification detail for Wave 1 planning

Even with zero live collisions, classify the residual risk as:

1. **Latent split-key defect** — hire path can still mint non-canonical keys if an 8-digit candidate phone is hired.
2. **No DB uniqueness** — application checks alone cannot prevent races or non-canonical forms.
3. **Exact-only lookup** — WhatsApp/ops lookups can miss the sibling form if one appears later.

---

## 5. Orphan classification

| Table | Orphans | Sample key | Classification | Notes |
|---|---|---|---|---|
| `employee_messages` | **3** | `WATHEFNI-P0-DUP-1` | `orphan_employee_key` / **synthetic test residue** | Not a live person row |
| attendance / leave / shifts / payroll | 0 | — | clean | |
| compliance_documents | 0 | — | clean | FK to employee_key only |
| onboarding_items | 0 | — | clean | No company_code column; FK employee_key only |
| file_registry (employee subjects) | 0 | — | clean | |
| employee_sessions / push / invites / status / org | 0 | — | clean | |
| employee_documents | 0 | — | clean | |
| manager_scope_members | 0 | — | clean | table empty |

**Coverage gap:** `workspace_integrity_scan` does not include `employee_messages` (or several other employee-linked tables). A green app scan can miss the residue found here.

**Operational tables with data (non-orphan):** attendance 42, shifts 20, onboarding 19, compliance 18, file_registry 82, leave 3, payroll timesheets 2, employee_messages 37 total.

---

## 6. Permission and manager-scope risk matrix

### Grants (WATHEFNI only; active)

| Permission | Active grants | Notes |
|---|---|---|
| `employees.read` | 4 | 2 owners + 2 viewers |
| `employees.manage` | 4 | 2 owners + **2 viewers** |
| `employees.status.approve` | 1 | 1 owner |

### Risk matrix

| Risk | Present in prod data? | Code gap? | Exploitability now | Severity |
|---|---|---|---|---|
| Nav soft-gate shows Employees without `employees.read` | **No** among active WATHEFNI users | Yes (soft-gate vs grant-only) | Low today | P2 latent |
| Viewer holding `employees.manage` | **Yes** (2 viewers) | Grant hygiene | Can mutate roster if they use API/UI | P1 hygiene |
| Dual `manage` + `status.approve` enabling canary self-approval | **Yes** (1 owner) | Server does not tenant-restrict canary | Confirmed used once on WATHEFNI | P0 control gap |
| Scoped manager with `employees.manage` mutating out-of-scope employee | **No scoped managers exist** | Mutation endpoints skip manager target scope | Latent until scopes used | P0 latent |
| External tenant canary usage | **0 rows outside WATHEFNI** | Mode accepted for any tenant | Latent until external tenants get dual grants | P0 latent |

### Manager scopes

- `manager_scopes` active rows: **0**
- `manager_scope_members`: **0**
- `employee_org_assignments`: **0**
- Org hierarchy flag: default off

Therefore: **no live out-of-scope mutation victim set**, but the missing mutation guard remains a Wave 1 containment item before any org/manager rollout.

---

## 7. `self_approved_internal_canary`

| Check | Result |
|---|---|
| Rows with `approval_mode='self_approved_internal_canary'` | **1** |
| Outside `WATHEFNI` | **0** |
| Server-side tenant/env allowlist | **Absent** |
| Dashboard always sends canary mode | **Yes** (code) |

Observed row (WATHEFNI, 2026-07-12): `previous_status=active` → `requested_status=active`, `verification_status=verified`.

**Conclusion:** No external-tenant canary abuse in current data. Control remains unsafe for future external enablement.

---

## 8. Former employees linked by recruiting while still `left`

| Check | Result |
|---|---|
| Employees with `employment_status='left'` | **0** |
| Left employees with `app_key` | **0** |
| `hire_operations` rows | **0** |
| Hire ops pointing at left employees | **0** |

**Conclusion:** No live rehire-left linkage in production data. Code defect remains: hire transaction does not reactivate / create a new employment relationship.

---

## 9. Employee status distribution / invalid states

| Status | Count | Classification |
|---|---|---|
| `active` | 2 | Valid |
| `left` | 0 | Valid |
| `NULL` / blank | **2** | **Invalid / unknown** — treated as active by many code paths via canonicalization helpers |

Both null-status employees are hire-linked (`has_app_key=true`) and still `onboarding_status=in_progress`.

This is the clearest **live internal data-quality defect** found in Wave 0.

Production employee inventory (redacted):

| employee_key | phone | status | onboarding | source |
|---|---|---|---|---|
| `WATHEFNI-96550252254` | ***2254 | `<null>` | in_progress | hire-linked |
| `WATHEFNI-96566363363` | ***3363 | active | in_progress | hire-linked |
| `WATHEFNI-96597727743` | ***7743 | `<null>` | in_progress | hire-linked |
| `WATHEFNI-96599411617` | ***1617 | active | in_progress | `dashboard_roster` |

---

## 10. Backup and rollback readiness

| Layer | Status |
|---|---|
| Daily backups | Present through `20260801T023033Z` |
| Offsite encrypted dailies | Present (latest `offsite-daily-20260801T023033Z.tar.zst.gpg`) |
| Weekly offsite | Present (`20260726…`) |
| Recent deploy backups | Multiple Wave D / Wave C production-pre backups from 2026-08-01 |
| Example rollback script | `/opt/wathefni/backups/production-pre-waveD-phase6b-cv-extraction-20260801T174712Z/ROLLBACK.sh` exists |

**Assessment:** Backup/rollback posture is adequate to support a future Wave 1 deploy **after** local qualification and explicit owner approval. Wave 0 did not execute restore rehearsal.

---

## 11. Is any active customer data at immediate risk?

### External / paying customers

**No employee rows exist outside `WATHEFNI`.**  
No live local-vs-965 duplicates, no left/rehire collisions, no scoped-manager mutation victims.

### Internal `WATHEFNI` workforce data

Immediate issues:

1. **2 employees with null `employment_status`** — lifecycle gates may behave inconsistently.
2. **3 orphan `employee_messages`** for synthetic `WATHEFNI-P0-DUP-1` — low blast radius; integrity-scan blind spot.
3. **Dual-grant owner can self-approve status changes via canary mode** — control gap, currently internal-only.
4. **Two viewer accounts hold `employees.manage`** — over-privileged relative to role name.

### Latent risks that become immediate on expansion

- Enabling external tenants or org scopes before Wave 1 containment.
- Hiring a candidate with an 8-digit phone while a roster row exists under `965…`.
- Granting `employees.manage` + `employees.status.approve` outside WATHEFNI while canary remains unrestricted.

---

## 12. Recommended safe remediation order

Do **not** merge, delete, backfill, constrain, or deploy yet.

### Wave 1 — containment only (local first)

1. **Server-side restrict** `self_approved_internal_canary` to an explicit internal allowlist (tenant + env); fail closed elsewhere.
2. **Unify phone canonicalization** across hire, roster create/import, and `find_employee_by_phone` (alias-aware lookup using `phone_identity_candidates` / canonical form).
3. **Enforce manager scope on all employee mutations** (PATCH, status, create-target assumptions, document orphans).
4. **Add optimistic concurrency** to employee PATCH (parity with status path).
5. **Expand integrity scan** to include `employee_messages`, sessions, invites, status changes, org assignments, file_registry, and onboarding.
6. **Tests:** hire-vs-roster phone matrix, canary allowlist matrix, scoped-manager mutation deny, null-status handling.

### Explicitly defer from Wave 1

- Adding `UNIQUE (company_code, phone)` before alias lookup + full historical scan across environments.
- Merging/deleting any employee rows.
- Backfilling null `employment_status` in production without a dedicated approved repair wave.
- True rehire / offboarding orchestration (Wave 3).
- Person/employment UUID cutover (Wave 2).
- Visual redesign / EN-AR polish (Wave 6).
- Any frozen pre-hire / Wave D changes.

### Suggested later repair for null statuses / synthetic orphans

- Separate approved data-repair wave after Wave 1 code containment.
- Quarantine/delete only synthetic keys such as `WATHEFNI-P0-DUP-1` with evidence.
- Normalize null → `active` only with row-level proof and rollback.

---

## 13. Wave 1 GO / NO-GO

| Decision | Gate |
|---|---|
| **GO — start Wave 1 local containment engineering** | Wave 0 complete; backups exist; no live external duplicate casualties; P0 control gaps are code-side and should be closed before expansion |
| **NO-GO — production Wave 1 deploy / data repair / constraints** | Requires local tests + evidence pack + explicit owner approval |
| **NO-GO — external tenant employee enablement** | Until Wave 1 containment is deployed and re-inventoried |
| **NO-GO — merge/delete/backfill/constrain now** | Wave 0 forbids it; still correct |

### Wave 1 exit criteria (for a future deploy decision)

- Canary mode cannot succeed outside allowlisted internal tenant/env.
- Hire and roster mint identical canonical keys for Kuwait 8-digit phones.
- `find_employee_by_phone` resolves both forms.
- Scoped manager mutation matrix fails closed.
- Integrity scan covers all employee-linked tables inventoried here.
- Re-run of this Wave 0 inventory remains clean for duplicates and shows expected control posture.
- No frozen pre-hire / Wave D regression.

---

## 14. What Wave 0 did **not** do

- No INSERT/UPDATE/DELETE/DDL
- No permission grant changes
- No flag flips
- No merges, deletes, backfills, constraints, replays, or repairs
- No production deploy
- No restore drill execution
- No change to frozen pre-hiring or Wave D posture

---

## Bottom line

Wave 0 **PASS**.

Production employee data is currently a small internal `WATHEFNI` set with **no live local-vs-965 duplicates**, but the **authority and approval control gaps remain open**. Start Wave 1 as **local containment only**. Do not deploy, repair data, or enable external employee tenants until Wave 1 evidence is approved.
