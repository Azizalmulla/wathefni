# Employees 360 Wave 5B — Self-service production safety qualification

**Stamp:** `20260801T223945Z`  
**Evidence:** `ops/evidence/employees360-wave5b-safety-local-20260801T223945Z/`  
**Schema:** `employees360-wave5b-selfservice-v1`  
**Mode:** Local implementation + **staging** qualification  
**Production deploy:** **NOT DONE**  
**Real lifecycle / Wave 6 / pre-hiring / Wave D:** **UNTOUCHED**

---

## Verdict

| Gate | Result |
|---|---|
| Wave 5B staging safety smoke | **31/31 PASS** |
| Wave 5 regression smoke | **41/41 PASS** |
| Prod untouched | **PASS** (no ESS module / no ESS flags) |
| Staging technical readiness | **GO** |
| **WATHEFNI-only production synthetic canary** | **NO-GO** until authorized deploy pack (backup + rollback + phone/key allowlist + ESS bank key provisioning) — **no remaining product/safety code blockers** |

---

## Exact fixes (Wave 5 → 5B)

1. **Mandatory bank encryption**
   - Removed all `plaintext_dev_only` write paths.
   - Writes require Fernet ciphertext under schema `ess_bank_v1` (`WATHEFNI_ESS_BANK_SECRET_KEY` [+ `_PREVIOUS`]).
   - Create/apply reject `store_plaintext` / `plaintext_dev_only` with `plaintext_bank_forbidden`.
   - Stored blobs without ciphertext / with plaintext are rejected on read (`plaintext_bank_rejected`).

2. **Key rotation / masking / audit / safe deletion**
   - `rotate_bank_encryption` re-wraps under current primary (MultiFernet decrypts previous).
   - Masked reads by default; unmask requires `employees.ess.unmask` / manage and is logged to `employee_ess_sensitive_access_log`.
   - `safe_delete_bank_profile` wipes ciphertext, retains fingerprint tombstone, audits.

3. **Employee-app identity binding**
   - Table `employee_ess_identity_bindings`: one active binding per `(company, employee_key)`, unique active `phone_fingerprint` / `email_fingerprint`.
   - Binds `person_id` + `employment_id` from Wave 2 map.
   - `session_epoch` bump revokes stale sessions (`stale_session_epoch`).
   - Terminated: `session_not_allowed`.

4. **Eligibility access policy**
   - Explicit policies for `active`, `future_start`, `suspended`, `notice_period`, `terminated` via `access_policy_for`.

5. **Overlay reconciliation**
   - `reconcile_ess_overlays` detects hub↔overlay drift and plaintext bank residue.
   - Opens `employee_ess_overlay_conflicts`; **never silent overwrite**.
   - Stale overlay version on apply → `409 overlay_conflict` and request state `needs_review`.

6. **Wave 4 assignment**
   - Still applied only via `apply_assignment_change`; smoke proves history growth + prior `effective_to` close (reversible corrective slice).

---

## Identity model

```
tenant (company_code)
  └── employee_key (hub)
        └── person_id (Wave 2)
        └── employment_id (active/eligible)
        └── phone_fingerprint  ── unique while status=active
        └── email_fingerprint  ── unique while status=active
        └── session_epoch      ── must match client; bump = revoke
```

Cross-tenant: ESS disabled outside allowlisted companies. Phone/email reuse across employees → `phone_already_bound` / `email_already_bound`.

---

## Encryption contract

| Item | Contract |
|---|---|
| Schema | `ess_bank_v1` |
| Alg | Fernet (MultiFernet primary + previous) |
| Env | `WATHEFNI_ESS_BANK_SECRET_KEY`, optional `WATHEFNI_ESS_BANK_SECRET_KEY_PREVIOUS` |
| Plaintext writes | **Rejected** |
| Rotation | Decrypt with multi → encrypt with primary → bump version + audit |
| Deletion | Ciphertext cleared; fingerprint retained; audited |
| Access audit | `employee_ess_sensitive_access_log` |

Staging keys live only in `/opt/wathefni/staging/var/employees360-wave5.env` (mode 600).

---

## Reconciliation behavior

1. Compare overlay personal fields (`email`/`phone`/`legal_name`) to hub.  
2. Flag plaintext bank residue.  
3. Insert `employee_ess_overlay_conflicts` rows (`status=open`).  
4. Apply-time version mismatch → request `needs_review` (not overwrite).

---

## Staging proofs (31/31)

Encrypted bank write/read/mask · unauthorized path · plaintext rejected · identity bind · duplicate phone denied · session revoke/stale · terminated/suspended policy · reconcile drift · overlay conflict → `needs_review` · apply idempotent · docs intact · self-approve / manager-scope / cross-tenant deny · Wave 4 reversible history · safe delete · `SYNTHETIC_ONLY` on.

Regression: Wave 5 ESS smoke **41/41**.

---

## Risks (residual for canary)

| Risk | Notes |
|---|---|
| Deploy not done | Intentional; needs Wave 5C-style prod pack |
| ESS bank key ops | Prod must provision `WATHEFNI_ESS_BANK_SECRET_KEY` before enable |
| Employee-app session wiring | Binding helpers exist; full `/app` token→epoch coupling still a rollout step |
| Letter PDF fulfillment | Still stub orders |
| Overlay vs hub drift | Detected; human review required to resolve |

---

## GO / NO-GO — production synthetic canary

**NO-GO** for immediate production canary execution (deploy forbidden in this wave).

**Technical readiness: GO** — Wave 5B closed the listed safety blockers in staging.

Next authorized step (out of scope here): Wave 5C WATHEFNI-only synthetic canary with backup/rollback, allowlist (`965549*` or dedicated), and production ESS bank key drop-in — without enabling real lifecycle.
