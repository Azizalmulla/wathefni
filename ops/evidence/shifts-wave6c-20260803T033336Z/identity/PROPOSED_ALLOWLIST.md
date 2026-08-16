# Shifts Wave 6C — Step 1: proposed controlled-rollout subjects (OWNER APPROVAL REQUIRED)

**Stamp:** `20260803T022802Z`  
**Evidence:** `ops/evidence/shifts-wave6c-20260803T022802Z/identity/`  
**Method:** read-only production SELECTs (`ops/sql/shifts_wave6c_subject_inventory.sql`, `..._probe2.sql`, `..._probe3.sql`). No mutation, no flag change, no deploy has been performed.

**Status: BLOCKED pending owner approval.** Nothing real has been enabled. Production posture is unchanged and still fully synthetic (`HR_ALLOWLIST=` empty, `MANAGER_ALLOWLIST=` empty, `REAL_MUTATION_GATE=1`, `NOTIFICATIONS_REAL_DELIVERY=0`, `INTEGRITY_JOBS=0`, `REAL_REMINDERS=0`).

---

## 1. Canonical identities found in production (WATHEFNI)

### Dashboard operators — the only 4 that exist

| user_id | name | email | phone (as stored) | role | status | last active |
|---|---|---|---|---|---|---|
| `88b17ca9-aff4-4721-a553-c1b5514ef95f` | Aziz Almulla | azizalmulla16@gmail.com | `96599338566` | **owner** | active | 2026-08-03 |
| `b69f4cad-589d-4029-8a2d-cfa85399966c` | Fouad | f.burhama@disruptv.tech | `66363363` | **owner** | active | 2026-07-27 |
| `201d0b3b-6a6f-483f-914a-7a2356fd0a2e` | Faisal Almulla | fslalmulla@gmail.com | *(none)* | viewer | active | 2026-07-27 |
| `90b78a42-9eb2-43b6-9eeb-c9c134a964b6` | hamad almulla | h.almulla@almulla-media.com | *(none)* | viewer | active | 2026-05-29 |

WhatsApp identities linked: Aziz `96599338566` + `99338566`; Fouad `66363363`.

### Real employees — the only 4 real people

| employee_key | name | phone | email | position | employment | lifecycle | branch/team |
|---|---|---|---|---|---|---|---|
| `WATHEFNI-96550252254` | Talal Fadhli | 96550252254 | talalabdalla89@gmail.com | Social Media Manager | active | active | none |
| `WATHEFNI-96566363363` | Fouad Burhamad | 96566363363 | fb-urhama@gmail.com | IT Maintenance | active | active | none |
| `WATHEFNI-96597727743` | mohammad alqattan | 96597727743 | *(none)* | Marketing Specialist | active | active | none |
| `WATHEFNI-96599411617` | Brian Saleh | 96599411617 | briansaleh92@gmail.com | *(none)* | active | active | none |

Talal has 11 employee-app sessions (last 2026-08-01) and is already the sole entry in `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST`.

---

## 2. Proposed allowlist (nothing applied yet)

| Purpose | Env var | Proposed value | Justification |
|---|---|---|---|
| HR operator (real Shifts mutations) | `WATHEFNI_SHIFTS_HR_ALLOWLIST` | `96599338566` (Aziz Almulla) | Only active operator with a verified linked phone, owner role, `shifts.manage`, active today. Matches the phone already trusted by the Leave controlled rollout. |
| HR operator #2 (optional) | same, appended | `96566363363` (Fouad) — **only after phone normalization**, see B1 | Second owner; stored dashboard phone is currently 8-digit local, which will not match. |
| Scoped manager | `WATHEFNI_SHIFTS_MANAGER_ALLOWLIST` | **(cannot be proposed)** | See B2 — no manager user, no scope, no org structure exists. |
| Employee-app canary | `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` | `WATHEFNI-96550252254` (Talal, unchanged) | Already the approved canary in the Employees 360 and Leave freezes. |
| Notification canary recipient | new `WATHEFNI_SHIFTS_NOTIFY_REAL_ALLOWLIST` | `WATHEFNI-96550252254` (Talal only) | Single approved recipient; every other employee fails closed. |

---

## 3. Blockers — owner decisions required before Wave 6C can proceed

### B1. Fouad's dashboard phone will not match the allowlist
`dashboard_users.phone = 66363363` (8-digit local) but his employee record is `96566363363`. The allowlist compares normalized digits of the acting user's phone, so `66363363` would never match `96566363363`. Options: use Aziz only, or update Fouad's dashboard phone to `96566363363` first (that is a real mutation and needs explicit approval).

### B2. No scoped manager exists — step 3 cannot be qualified on real data
Production has **zero** `manager_scopes` rows, **zero** `manager_scope_members`, **zero** `company_branches`, **zero** `company_teams`, and **no dashboard user with role `manager` or `hr`** (only 2 owners + 2 viewers). Scoped manager qualification would require creating an org structure and a new manager user — a structural change to a live tenant. Recommendation: **NO-GO for real scoped manager rollout**; qualify manager scope on synthetic subjects only, unless you name a real manager and their branch/team.

### B3. Real notification delivery is not implementable by Wave 6B code
`shifts_notifications_wave6b.py` only has a mock adapter and hard-returns `real_delivery_not_allowed_in_wave6b` even when the flag is on. A real canary needs new Wave 6C code binding the canonical outbox to the existing production sender (`deliver_employee_notification(flow="shift")` → Octopus WhatsApp / Postmark-Gmail email). This is a build item, not a flag flip.

### B4. No verified notification destination or consent
Production has **zero** `employee_push_tokens`, **zero** `shift_channel_preferences`, **zero** `person_consent_records` for WATHEFNI. The in-app inbox (`/app/notifications` over `employee_messages`) is a **read** surface with no standalone app-only sender, so "app/web as canonical delivery" means an inbox row written by the outbound ladder, not an independent channel. Practically, the first real external channel must be **WhatsApp to 96550252254** (Octopus session message, requires an existing conversation) or **email to talalabdalla89@gmail.com**. Owner must confirm Talal consents and pick the channel.

Note: `WATHEFNI_DELIVERY_MODE` is unset in production, which means **live**, and `WATHEFNI_OUTBOUND_FLOWS` already includes `shift`. Any real Shifts send would therefore go out for real the moment the code path is reachable — this is exactly why the recipient allowlist must be enforced in code, not by convention.

### B5. Pre-existing "real-looking" rows that are not real people
`shift_assignments` has 31 non-`SHW` rows, but they break down as: Talal 5, Fouad 8, mohammad 7 (all historical, June 16 and earlier, **zero future rows**), plus 3 keys not present in `employees` (`WATHEFNI-96552202357`, `-96552263564`, `-96596552203`) and 8 `WATHEFNI-ORPHAN-*` keys — all cancelled, and all paired with `WATHEFNI-SHW1-*` hex suffixes in `shift_orphan_quarantine` (21 rows), so they are synthetic residue that the current markers/prefixes do **not** classify as synthetic. They will be treated as real by the gate. Recommendation: leave untouched, exclude explicitly, and do not let cleanup or reconciliation act on them.

Also present: `WATHEFNI-REALBLOCK-0F290BF7` (phone 96599998877), the deliberate real-denial probe employee. Not a rollout subject; leave in place.

### B6. Legal/policy items still unresolved (unchanged from Wave 6B)
Sector Ramadan hour caps and midday outdoor windows; weekly rest weekday convention (`shift_authority_settings.rest_weekdays = {4}` today, i.e. Friday only); official PAM form field mapping vs `pam-export@1.0.0`; hitch travel-day vs Payroll allowance ownership. Compliance profiles must stay **warn**, never **block**, until these are verified.

---

## 4. What is unchanged and will stay unchanged without approval

No allowlist populated · no flag changed · no deploy · no real mutation · no real message sent · no timer enabled · no PAM submission · no Payroll money · Attendance capture ingest still `off` · Employees 360 / Onboarding / Attendance / Leave freezes untouched.

---

## 5. Recommended scope if you approve

1. **HR real scheduling:** Aziz only (`96599338566`), future dates only, on real employees Talal / Fouad Burhamad / mohammad alqattan / Brian Saleh, with audit reason + concurrency token required.
2. **Scoped manager:** synthetic-only qualification, real rollout **NO-GO** (B2).
3. **Talal employee-app:** read + acknowledge only, no writes.
4. **Real notification canary:** Wave 6C adapter, recipient allowlist of exactly one employee key, one external channel (your choice of WhatsApp or email), kill switch tested first.
5. **Timers:** stay disabled; qualify the jobs by manual invocation only.
