# Phase 7E-R1 — Remediation plan only (no implementation)

**Status:** Plan only — awaiting review. Do **not** patch application code until this plan is approved.  
**Accepted E2 evidence:** `ops/reports/phase7e-e2-verifier-report.{json,md}` — **not staging-green**.  
**Phase posture:** Phase 7E remains open. Phase 8 must not begin. No production enablement authorized.

**In scope**

| Slice | Cases | Theme |
|-------|-------|-------|
| **7E-R1A** | C05e, C05g, C05h, C05i, C10c, C10d, C10d2, C10e, C10e2 | Identity binding, company lifecycle, module gate, repeated activation, session truth |
| **7E-R1B** | C07i | Server-side upload extension / declared MIME / content-signature consistency |

**Explicitly out of R1 (defer; keep as open 7E follow-ons)**

| Case | Why deferred |
|------|----------------|
| **C07k** | Post-storage DB failure orphan compensation — upload durability, not identity/MIME. Track as **7E-R2** candidate. |
| **C07l** | Rejection audit event — observability, not authorization/content gate. Track as **7E-R2** candidate. |
| Real-ladder delivery cases (C03e–C03h) | Already green; no remediation. |

Do **not** loosen any verifier assertion to make tests pass.

---

## Hard boundaries (unchanged)

Do not touch:

- production flags (`WATHEFNI_EMPLOYEE_APP`, `WATHEFNI_ONBOARDING_SEED`, `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`)
- production tenants or employees
- Phase 7D company channel routing / shared WhatsApp routing
- onboarding seed behavior
- dashboard/bootstrap unrelated to invite lifecycle gating
- push notifications
- public store work
- unrelated Document Hub architecture beyond the employee upload validation path needed for C07i

---

## 1. Exact files and services affected

### Primary (expected edits after approval)

| File / surface | Role in R1 |
|----------------|------------|
| `wathefni-orchestrator/app.py` | All R1A auth/session/invite gates; R1B upload validation before storage |
| `wathefni-orchestrator/ops/staging-phase7e-employee-app-verify.py` | Regression additions only after implementation approval; **do not weaken existing cases** |
| `wathefni-orchestrator/requirements.txt` | Add trusted content-type detector for R1B (see §R1B) |
| `wathefni-orchestrator/ops/deploy.sh` | Only if new module/file is split out or dependency install must be documented for staging/prod deploys |

### Optional small extraction (preferred if `app.py` churn is high)

| File | Purpose |
|------|---------|
| `wathefni-orchestrator/employee_app_auth_gates.py` (new, optional) | Pure helpers: invite identity match, lifecycle+module eligibility, “already activated” check — unit-smokeable without HTTP |
| `wathefni-orchestrator/employee_app_upload_validation.py` (new, optional) | Pure helper: extension + declared MIME + signature → allow/deny |

### Call sites (must enforce, not merely document)

| Function / route | Slice |
|------------------|-------|
| `dashboard_posthire_app_invite` | R1A lifecycle (+ existing module/flag) |
| `create_employee_app_invite` | Defense-in-depth lifecycle (or call only from gated paths) |
| `app_auth_activate` | R1A identity, lifecycle, module, repeated activation, invite non-consumption |
| `app_auth_request_code` | R1A lifecycle (same company must be active; keep response generic) |
| `employee_app_context` | R1A lifecycle + module (module already present; lifecycle missing) |
| `app_auth_refresh` / `rotate_employee_session` | R1A module + lifecycle **before** credential rotation |
| `app_onboarding_document_upload` | R1B content validation before `store_onboarding_document` / DB receipt |

### Reuse as-is (no redesign)

- `company_lifecycle_status` / `require_active_company` (dashboard already uses these)
- `company_has_module`
- `revoke_employee_app_access` (employee kill switch already proven green)
- Existing invite hash / attempt / lock / supersede mechanics

### Services / runtime

- Staging orchestrator process only for verification reruns
- No systemd flag flips
- No production DB writes from remediation or verifier

---

## 2. Current root cause for each failed case

### R1A

| Case | Observed | Root cause |
|------|----------|------------|
| **C05e** | Invite bound to `EMP_A` but stored with `PHONE_D`; activating as D returns **200** and issues a session for D | `app_auth_activate` loads invite by `(company_code, phone)` only, validates code hash, then creates a session for the **phone-resolved** employee. It never requires `invite.employee_key == resolved employee_key`. |
| **C05g / C05h** | HR invite and activate succeed while company is `disabled` / `archived` | Neither `dashboard_posthire_app_invite` nor `app_auth_activate` call `company_lifecycle_status` / `require_active_company`. Module + global flag checks alone are insufficient. |
| **C05i** | Second `/app/auth/activate` after an active session creates a **second** active session | `create_employee_session` always INSERTs; activate never checks for an existing `employee_sessions.status='active'` row for that employee. No conflict policy. |
| **C10c** | After `employee_app` module removal, refresh still returns new tokens | `app_auth_refresh` → `rotate_employee_session` rotates hashes on any active refresh row. **No** `company_has_module(..., "employee_app")` check. Bearer path already denies (C10b green); refresh path does not. |
| **C10d / C10d2** | Disabled company still serves bearer context and refresh | `employee_app_context` and refresh path never consult company lifecycle. |
| **C10e / C10e2** | Archived company same as disabled | Same omission as C10d/C10d2. |

### R1B

| Case | Observed | Root cause |
|------|----------|------------|
| **C07i** | `.pdf` filename + `image/png` Content-Type + PNG bytes accepted (200, stored) | `app_onboarding_document_upload` only allowlists **filename extension**. Declared `file.content_type` is trusted/stored; **no** byte-signature inspection; **no** consistency check across extension ↔ declared MIME ↔ detected type. |

---

## 3. Durable remediation design

### Phase 7E-R1A — identity, lifecycle, session enforcement

#### Shared eligibility helper (recommended)

Introduce one backend-owned predicate used by activate, refresh, and bearer context (and invite creation for lifecycle):

```
employee_app_access_allowed(company_code, employee) -> ok | deny_reason
```

Must evaluate **current DB state**, not claims embedded in tokens:

1. Global `employee_app_enabled()` (existing)
2. `company_lifecycle_status(company) == "active"`
3. `company_has_module(company, "employee_app")`
4. Employee exists in that company
5. `employment_status` in `("", "active")` (existing rule)

Deny reasons map to HTTP without leaking cross-tenant existence where the endpoint already uses generics (activate / request-code).

#### Rule 1 — Invite identity binding (`C05e`)

In `app_auth_activate`, **before** any invite status mutation or session insert:

1. Resolve phone → company → employee (existing).
2. Load candidate pending invite for `(company, phone)` (existing lookup is acceptable as the first filter).
3. Verify code hash (existing).
4. **New:** require `str(invite["employee_key"]) == str(employee["employee_key"])`.
5. **New:** require `str(invite["company_code"]).upper() == company`.
6. On mismatch: return the **same generic** `401 app_activation_failed` used for bad codes. Do **not** redeem, do **not** create a session, do **not** reveal that another employee owns the invite.

Optional hardening (same PR if cheap): when looking up the invite for redemption, also constrain `employee_key` once the phone-resolved employee is known (`AND employee_key=%s`), so a mismatched row is never selected.

#### Rule 2 — Company lifecycle (`C05g/h`, `C10d*`, `C10e*`)

| Gate | Required behavior |
|------|-------------------|
| Invite creation (`dashboard_posthire_app_invite`, and any path calling `create_employee_app_invite` for app activation) | Deny if company not `active` (403 with existing company lifecycle error shape used by dashboard is acceptable for HR). |
| Activation | Deny if company not `active` **before** redeem/session. Use generic 401 on the public activate path (no company-status disclosure). |
| Bearer (`employee_app_context`) | Deny if company not `active` (403 `company_disabled` / `company_archived` or reuse `require_active_company` shape). |
| Refresh | Deny if company not `active` **before** rotating credentials. |

Disabled and archived are both non-active; no special-case allowance.

#### Rule 3 — Effective module gate on refresh (`C10c`)

- Keep existing module check in `employee_app_context` (already green for bearer).
- Add the **same** `company_has_module(company, "employee_app")` check in `app_auth_refresh` **before** calling `rotate_employee_session`, or inside rotation only after a pre-check that performs **no write**.
- On deny: `401` or `403` consistent with bearer module denial; **no new token/refresh hashes written**.

#### Rule 4 — Repeated activation policy (`C05i`) — locked

If the employee already has ≥1 `employee_sessions` row with `status='active'` for that `(company_code, employee_key)`:

- **Reject** `/app/auth/activate`
- Deterministic response: prefer **`409`** with stable error code e.g. `already_activated` and message directing the client to normal login / recovery (not “ask HR for a new code” if that would confuse operators—wording may say they are already activated and should sign in again).
- Do **not** create a second session
- Do **not** atomically replace / revoke existing sessions from this endpoint
- Do **not** consume the new invite on this path (invite remains pending or is left unchanged; prefer **non-consumption**)

Out of scope: admin-controlled reactivation with atomic session replacement.

#### Rule 5 — Session truth

Bearer and refresh must re-read company status, module enablement, and employment status from the database on every request/rotation. Session row presence alone is never sufficient authorization.

#### Rule 6 — Invite safety on denial

Any failure of identity, lifecycle, module, employment, or already-activated checks must:

- leave invite `status` unchanged (still `pending` unless it was already locked/expired)
- issue no bearer/refresh credentials
- create no partial activation state
- leave active session count unchanged
- avoid leaking whether an unrelated employee exists (generic activate errors)

Wrong-code attempts may still increment `attempts` (existing abuse protection). Identity/lifecycle/already-activated denials must **not** be treated as wrong-code attempts if that would burn the invite toward lock; prefer zero mutation.

---

### Phase 7E-R1B — upload content validation (`C07i`)

#### Trusted detection mechanism

**Choice: `puremagic` (add to `requirements.txt`).**

| Criterion | Decision |
|-----------|----------|
| Why not filename alone | Filename is attacker-controlled; C07i proves this is insufficient. |
| Why not trust `UploadFile.content_type` alone | Client-declared; C07i uses a mismatched declaration. |
| Why `puremagic` | Pure Python magic-byte / container sniffing; **no** system `libmagic` package on the VPS; fits current thin `requirements.txt`. |
| Alternative rejected for R1 | Hand-rolled signature table only — easy to drift for WEBP/HEIC; acceptable as a **fallback** if `puremagic` returns empty, but not as the sole detector. |
| Alternative rejected for R1 | `python-magic` — requires OS `libmagic`; deploy friction and staging/prod drift risk. |

#### Allowed document set (employee app upload)

Keep the existing extension allowlist:

`{.pdf, .jpg, .jpeg, .png, .webp, .heic}`

Map to canonical MIME families:

| Extension | Allowed declared MIME | Allowed detected MIME / kind |
|-----------|----------------------|------------------------------|
| `.pdf` | `application/pdf` | PDF |
| `.jpg` / `.jpeg` | `image/jpeg` | JPEG |
| `.png` | `image/png` | PNG |
| `.webp` | `image/webp` | WEBP |
| `.heic` | `image/heic` / `image/heif` | HEIC/HEIF |

#### Validation order (fail closed)

Before `store_onboarding_document` and before any Document Hub / onboarding_items mutation:

1. Extension ∈ allowlist (existing) → else `400 unsupported_file_type`
2. Non-empty + size ≤ 15 MiB (existing)
3. Normalize declared MIME (`file.content_type`); if missing, **do not invent from filename as proof of type** — treat as unknown and require signature to establish type, or reject if signature cannot establish an allowed type
4. Run `puremagic.magic_stream` / equivalent on the **bytes already read**
5. Require **extension family ↔ declared MIME family ↔ detected family** all agree on one allowed type
6. On any mismatch, unknown detection, or ambiguous multi-match that does not resolve to one allowed family → `400` or `415` with stable error e.g. `mime_mismatch_or_invalid_content` (matcher already expects this class)
7. Only then write temp file / call storage / commit metadata

#### Failure behavior (locked)

| Detector outcome | Behavior |
|------------------|----------|
| Clear match to one allowed type, consistent with extension + declared MIME | Accept; store **detected** (or normalized canonical) MIME in metadata, not the raw attacker string if they differ only by alias |
| Clear match but disagrees with extension or declared MIME | Reject; no storage; no canonical rows; item stays pending |
| No match / empty / unrecognized | Reject (fail closed) |
| Detector exception | Reject (fail closed); log warning; do not store |
| Declared MIME spoof with correct bytes+extension | Reject if declared MIME is outside the extension’s allowed set (consistency required) |

Preserve existing orphan-safety for **failed storage** (C07j green). Do **not** claim C07k is fixed by R1B.

Do not treat mobile picker restrictions as enforcement.

HR twin upload (`dashboard_posthire_employee_document_upload`) is **out of R1** unless a one-line shared helper naturally covers both without expanding scope. Prefer sharing the pure validator if both call sites already share `_APP_DOC_*` constants; otherwise employee path only for R1B.

---

## 4. Transaction / order-of-check strategy

### Activate (`POST /app/auth/activate`)

Recommended order inside one DB transaction where possible:

1. Flag check (no DB write)
2. Resolve phone → company → employee (read)
3. Lifecycle + module + employment eligibility (read) — deny generic, **no invite mutate**
4. Load pending invite (read)
5. Attempt/lock / code hash verify (existing; wrong code may increment attempts)
6. Identity bind: invite.employee_key + company match (deny generic, **no redeem**)
7. Already-activated check: count active sessions (deny 409, **no redeem**, **no session insert**)
8. Redeem invite + insert session (**same transaction**)
9. Commit; return tokens

If redeem and session insert cannot share a transaction with session helper as written today, refactor `create_employee_session` to accept an open cursor **or** perform both writes in `app_auth_activate` before commit. Partial redeem-without-session is unacceptable.

### Refresh (`POST /app/auth/refresh`)

1. Flag check
2. Resolve session by refresh hash (**read only**)
3. Load employee + company lifecycle + module + employment (**read**)
4. On deny: return error; **do not UPDATE** token/refresh hashes
5. On allow: rotate hashes (existing write)

Today `rotate_employee_session` writes immediately after SELECT. R1 must split **lookup** from **rotate**, or add a preflight that returns without writing.

### Bearer (`employee_app_context`)

After session resolve + existing module/employment checks, add lifecycle check before returning context. Prefer deny without revoking all sessions automatically (operator may re-enable company); optional soft note in logs. Per-employee revoke remains the hard kill switch (already green).

### Invite create (HR)

After flag + module + employee found: require active company, then create invite + deliver (mocked in staging).

### Upload (R1B)

Validate extension → size → declared/detected consistency → **then** storage → DB. Reject path must not call `store_onboarding_document`.

---

## 5. Migration requirements

| Change | Migration? |
|--------|------------|
| Identity / lifecycle / module / already-activated gates | **None** — columns and tables already exist (`companies.status`, `company_modules`, `employee_app_invites.employee_key`, `employee_sessions`) |
| Upload MIME/signature validation | **None** — validation is request-time only |
| New dependency `puremagic` | Deploy/install via existing venv + `requirements.txt`; no schema migration |
| Optional unique constraint “one active session per employee” | **Not required for R1** — application reject is sufficient; DB unique partial index may be a later hardening, not blocking |

---

## 6. Compatibility risks

| Risk | Mitigation |
|------|------------|
| Clients that re-call `/app/auth/activate` after success currently get a second session; after R1 they get **409** | Document for mobile; treat as intentional. No silent replace. |
| HR invite while company disabled currently succeeds; after R1 it **403**s | Correct; Setup Console / dashboard should already treat non-active companies as restricted elsewhere. |
| Refresh after module removal currently renews access; after R1 it fails — existing bearer already fails | Mobile must fall through to login; expected kill-switch behavior. |
| Stricter upload validation may reject previously “accepted” spoofed files | Desired. Valid PDF/PNG/JPEG controls must pass. HEIC: verify `puremagic` detection on staging fixtures; if HEIC detection is weak, fail closed and document HEIC as staging-known until detector confirms (do not accept HEIC on extension alone). |
| Declared MIME required to match | Some clients send `application/octet-stream`; fail closed unless signature uniquely identifies an allowed type **and** extension matches — plan: allow missing/octet-stream **only when** signature+extension agree on one allowed type. |
| Generic activate errors | Keep; do not add distinct “wrong employee” messages. |

---

## 7. Exact verifier additions (after implementation approval)

Do **not** weaken C05e–C05i, C07i, or C10*. Rerun **all original E2 cases** (the locked 51-case matrix), then the strengthened extras if still present, plus:

### Invite non-consumption regressions

| New case | Assertion |
|----------|-----------|
| **C05e2** | After identity mismatch denial, invite row remains `pending` (not `redeemed`/`locked` solely due to mismatch) and session count unchanged |
| **C05g2 / C05h2** | After lifecycle denial on activate, invite not redeemed; if invite creation was denied, no new pending invite for that employee from the denied HR call |
| **C05i2** | Already-activated denial leaves prior active session count unchanged and does not redeem the new invite |

### Refresh denial does not mint credentials

| New case | Assertion |
|----------|-----------|
| **C10c2** | Module-off refresh denied; `token_hash` / `refresh_hash` for the session row unchanged vs preimage; no second session row |
| **C10d3 / C10e3** | Disabled/archived refresh denied; hashes unchanged (same proof pattern) |

### Upload controls (R1B)

| New case | Assertion |
|----------|-----------|
| **C07i_pdf** | Valid `%PDF` bytes + `.pdf` + `application/pdf` → 200 + canonical rows |
| **C07i_png** | Valid PNG signature + `.png` + `image/png` → 200 |
| **C07i_mismatch_ext** | PNG bytes + `.pdf` + `application/pdf` → deny |
| **C07i_mismatch_declared** | PNG bytes + `.png` + `application/pdf` → deny |
| **C07i_exec_spoof** | Non-image/PDF payload + `.pdf` → deny |

### Always retain

- Fixture cleanup (`C11e`)
- Production + staging protected snapshot checks (`C11a`–`C11d`)
- No production flag changes

---

## 8. Rollback approach

| Layer | Action |
|-------|--------|
| **Code** | Revert the R1 commit(s) on staging orchestrator; redeploy prior artifact via existing `ops/deploy.sh` path |
| **Dependency** | If `puremagic` must be removed, uninstall from venv on rollback of R1B |
| **Data** | No schema migration → no DB down-migration. Staging throwaways remain deletable by verifier cleanup |
| **Flags** | Remain OFF in production and staging systemd before/after R1; R1 does not flip flags |
| **Sessions** | R1 does not require mass revoke; if a bad deploy issued incorrect sessions in staging only, `revoke_employee_app_access` / verifier cleanup is sufficient |
| **Product posture** | Rollback returns to “E2 evidence accepted / not staging-green”; it does **not** authorize Phase 8 |

---

## Implementation sequence (when approved)

1. **R1A only** (identity + lifecycle + module-on-refresh + already-activated) → staging compile → verifier full matrix  
2. **R1B** (`puremagic` + upload consistency) → staging install dep → verifier full matrix + new upload controls  
3. Publish updated `phase7e-e2-verifier-report.*`  
4. Phase 7E remains open until **all in-scope R1 cases green** and deferred C07k/C07l disposition is decided (fix in R2 or accept as known non-blocking for a later gate — product call)

**Success for R1:** C05e, C05g, C05h, C05i, C07i, C10c, C10d, C10d2, C10e, C10e2 green on a full rerun; new regressions green; snapshots unchanged; no production enablement.

**Still not Phase 8.** Still not production employee-app enablement.

---

## Approval gate

No application patching until this R1 plan is explicitly approved. Verifier assertions must not be relaxed to obtain a green report.
