# Phase 7D — Company channel accounts readiness pack

**Status:** Implementation (staging/design only). Plan accepted.  
**Prerequisites closed:** Phase 7C document reconciliation series (audit → staging canary → production dry-run). Option C production write canary **deferred**.

**Keep OFF in production (and default everywhere until staging validation is approved):**

- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_EMPLOYEE_APP=off`

**Hard non-goals for Phase 7D:**

- Do not enable employee app  
- Do not provision live WhatsApp / provider accounts  
- Do not change production routing  
- Do not flip production `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS` on  
- Do not send real customer/employee messages through company-owned numbers as part of this phase  

**Implementation artifacts:**

- `channel_account_routing.py` — pure outbound/inbound resolve helpers  
- `app.resolve_company_outbound_whatsapp_route` / `resolve_inbound_company_from_whatsapp_account`  
- `send_octopus_whatsapp(..., company_code=, audience=)` — optional; omitted ⇒ shared path unchanged  
- `ops/staging-phase7d-channel-accounts-verify.py` — 10-case throwaway matrix (`P7DSTG01`/`P7DSTG02`)  
- `smoke-test-channel-account-routing.py` — pure unit smoke  
- `.env.example` — flag documentation  

---

## Goal

Ship a **readiness pack** that makes company-owned channel accounts a safe, fail-closed, tenant-isolated capability — first as design + staging validation — without regressing today’s **shared WATHEFNI WhatsApp** routing.

Today’s truth (important):

| Layer | Current state |
|-------|----------------|
| Registry | `company_channel_accounts` table + Setup Console card exist |
| Flag | `company_channel_accounts_enabled()` — default **off**; mutations return `404 not_found` |
| Runtime | `setup_console_channel_policy().runtime_routing_changed == False` — registry does **not** drive send/receive yet |
| Production messaging | One platform-owned WhatsApp sender; company resolved from **phone actor context**, not from inbound account id |

Phase 7D designs and stages the missing **routing contract**, isolation proofs, and rollback — it does not go live on production.

---

## 1. Per-company channel account model

### Existing spine (keep)

Table `company_channel_accounts` (already in orchestrator schema):

| Field | Role |
|-------|------|
| `company_code` | Tenant owner (FK → `companies`) |
| `channel_key` | Default `whatsapp_business` |
| `provider` | Normalized allowlist (today: `octopus`) |
| `provider_account_id` | Provider-side account identity |
| `sender_phone` | Display / matching aid (not a secret store) |
| `audiences` | jsonb subset of `{candidate, employee}` |
| `status` | `pending_verification` \| `active` \| `disabled` |
| Uniques | `(company_code, channel_key)`, `(provider, provider_account_id)` |

Setup Console APIs (flag-gated mutations):

- `PUT /dashboard/superadmin/setup/companies/{company_code}/channel-account`
- `DELETE …/channel-account` (soft-disable)
- Company detail includes `channel_account` + `channel_policy`

### Phase 7D model rules (design)

1. **One active WhatsApp business account per company** for v1 (matches unique `(company_code, channel_key)`).  
2. **Provider account cannot be shared across companies** (existing unique on `(provider, provider_account_id)`).  
3. **Activation requires verification evidence** (today: non-empty verification reference → `active`; 7D should document this as operator-asserted, not provider-callback-verified, until a later phase).  
4. **Disabled / missing / unverified ⇒ fall back to shared platform routing** (see §3) — never “black hole” messages silently without policy.  
5. **Secrets stay out of this table** — tokens/API keys remain in host/config secret stores; registry holds identity + status only.  
6. **Audit every mutation** (already via `record_admin_audit` / `target_type=company_channel_account`).

### Deliverables (when coding approved)

- Short model doc in this file + optional `ops/PHASE7D_CHANNEL_ACCOUNT_MODEL.md` excerpt  
- Staging seed of **throwaway** company registry rows (fake provider ids) — no live WhatsApp  
- Extend `.env.example` / ops flag inventory to document `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`

---

## 2. Candidate vs employee audience separation

### Current

- `audiences` stores `candidate` and/or `employee`  
- Setup Console policy surfaces pre-hire vs post-hire WhatsApp readiness separately  
- **Not enforced** on send/receive paths today  

### Phase 7D policy (design)

| Audience | Meaning | Routing implication (when flag ON + account active) |
|----------|---------|------------------------------------------------------|
| `candidate` | Pre-hire / applicant messaging | Outbound candidate templates/notifications may use company account **only if** `candidate ∈ audiences` |
| `employee` | Post-hire employee messaging | Employee notifications may use company account **only if** `employee ∈ audiences` |
| Neither / empty | Misconfiguration | Treat as **not ready** — fail closed to shared default or block company-owned send (choose in staging; recommend **fallback to shared** for v1 to avoid dropouts) |
| HR operator chat | Platform HR console | Remains on **shared WATHEFNI** account unless explicitly designed later (out of 7D v1) |

**Fail-closed audience rule (staging target):**

- If company account is `active` but requested audience not listed → **do not** send via company account; use shared default (and log `audience_not_permitted`).  
- Never send a candidate message through an employee-only account (and vice versa).

Actor classification already exists (`candidate` / `employee` / `hr` via phone context). 7D wires **audience check after actor class is known**.

---

## 3. Shared default routing vs company-owned routing

### Shared default (production today — must not regress)

```text
Inbound WhatsApp → single platform account
  → resolve actor by phone
  → resolve company_code from employee/HR/candidate context (default WATHEFNI)
  → handle in that company scope

Outbound → openclaw/octopus account_id from platform config (default)
```

### Company-owned routing (flag ON, staged design)

```text
Inbound:
  preferred: map receiving provider_account_id / to-number → company_channel_accounts
  fallback: if no mapping → shared default resolver (phone → company)

Outbound:
  if flag OFF → always shared default
  if flag ON and company has status=active account
       and audience permits
       → select that provider_account_id for send
  else → shared default
```

### Explicit invariants

1. **`runtime_routing_changed` becomes meaningful only behind the flag** and only after staging proofs.  
2. Production with flag OFF must behave **byte-for-byte** like today’s shared path.  
3. Registering an account while flag OFF must **never** alter routing (already true; keep it).  
4. Company-owned routing is **opt-in per company** via active verified registry row — not a global cutover.

---

## 4. Fail-closed behavior

| Condition | Behavior |
|-----------|----------|
| Flag OFF | Mutations `404 not_found`; UI read-only banner; readiness ignores channel step; routing = shared only |
| Flag ON, no row | Shared default routing |
| Flag ON, `pending_verification` / `disabled` | Shared default routing; do not send as company |
| Flag ON, `active`, audience mismatch | Shared default (v1) + structured log; never cross-audience |
| Flag ON, `active`, provider id unknown to sender config | **Fail closed:** do not invent credentials; refuse company send; fallback shared **or** hard-fail outbound with operator-visible error (staging must pick one; recommend fallback + alert for v1) |
| Cross-tenant provider id collision | Blocked by DB unique; API must surface conflict clearly |
| Missing company_code on send context | Refuse company-owned send; shared path only if actor resolves |

No silent cross-tenant delivery. No “best effort” account reuse.

---

## 5. Setup Console visibility while flag is OFF

Keep current UX posture (do not hide the card entirely):

- **Visible** channel account card + policy summary for superadmins  
- Banner: feature not available on this environment; existing status read-only; **live delivery unchanged**  
- Inputs disabled; save/disable return `404`  
- Readiness must **not** block on channel account while flag OFF  

Phase 7D staging checklist:

- [ ] Flag OFF: card visible, mutations 404, routing unchanged  
- [ ] Flag OFF: existing row (if any) still readable  
- [ ] Flag OFF: company readiness can still complete other steps  

---

## 6. Staging validation with flag ON

Throwaway company only (e.g. `P7DSTG01`) — **never** flip production flag.

### Staging matrix (design)

| # | Case | Expect |
|---|------|--------|
| 1 | Flag OFF baseline | Shared routing; mutations 404 |
| 2 | Flag ON, no account | Shared routing; readiness shows channel not configured |
| 3 | Upsert pending account | Row stored; still shared routing |
| 4 | Activate with verification ref | Status `active`; policy shows verified |
| 5 | Audience candidate-only | Employee-targeted company send blocked/fallback; candidate permitted (simulated) |
| 6 | Audience employee-only | Inverse of #5 |
| 7 | Disable account | Soft-disable; routing returns to shared |
| 8 | Second company cannot steal provider id | Unique conflict |
| 9 | Flag rollback OFF mid-flight | Mutations 404 again; routing shared even if row remains `active` |
| 10 | Production WATHEFNI shared path smoke | Unchanged (see §8) |

Simulated sends only (dry harness / mocked octopus) — **no live WhatsApp provisioning**.

### Staging enablement procedure (when approved)

1. Staging unit drop-in only: `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=on`  
2. Run staging verifier  
3. Leave production off  
4. Document rollback (§9)

---

## 7. Proof no messages can cross tenants

Required isolation proofs (staging harness):

1. **Provider account uniqueness** — account registered to `P7DSTG01` cannot be attached to `P7DSTG02`.  
2. **Outbound selection** — mocked send for company A never selects company B’s `provider_account_id`.  
3. **Inbound mapping** — webhook fixture with account id A resolves `company_code=A` even if phone exists in company B (design target; may be new code behind flag).  
4. **Phone-only fallback** — when inbound account unknown, phone resolver must not leak B’s employee into A’s session without existing multi-tenant rules (document current behavior; tighten if needed).  
5. **Audit log** — every registry mutation company-scoped; no cross-tenant reads in Setup Console detail API.

Acceptance: automated staging test file (future) `ops/staging-phase7d-channel-accounts-verify.py` with PASS/FAIL matrix.

---

## 8. Proof production shared WATHEFNI routing does not regress

Even while designing company-owned routing:

| Check | Method |
|-------|--------|
| Production flag remains OFF | systemd environ assert (same as 7C verifiers) |
| Shared send path unchanged | Code review: send helpers ignore registry when flag OFF |
| Inbound company resolution unchanged | Golden tests / smoke on phone→company for WATHEFNI |
| Setup Console prod | Card read-only; no accidental enable |
| Health / bootstrap | Staging+prod health 200 after any staging-only deploy |

**Regression gate:** no production PR that sets `runtime_routing_changed=True` or queries `company_channel_accounts` on the send path without flag guard.

---

## 9. Rollback / disable behavior

| Action | Effect |
|--------|--------|
| Set flag OFF (staging or prod) | Immediate: mutations gone; routing forced shared; rows retained |
| Soft-disable account (`DELETE` API / status `disabled`) | Company-owned send stops; shared fallback |
| Hard delete row | **Not required in v1**; prefer soft-disable for audit trail |
| Remove staging drop-in + restart | Returns to default OFF |

Rollback drill is part of staging validation (#9 in §6).

Compensation for mis-routed staging test messages: N/A if no live provider; if a mocked ledger exists, assert no cross-tenant entries.

---

## 10. Why this is not required before a single employee-app pilot

A **single-tenant employee-app pilot** on shared Wathefni WhatsApp (or app-only push/API) does **not** need company-owned WhatsApp numbers when:

- Pilot company is content to use the **platform sender**  
- Employee identity is app session / phone already bound to one company  
- No requirement for branded WhatsApp business number per client  

Company channel accounts become required when:

- A client demands **their** WhatsApp Business number for candidates and/or employees  
- Multiple concurrent clients must be isolated at the **telephony/account** layer (not only phone→company DB lookup)  
- Compliance/branding requires separate sender identity  

Therefore: **7D can proceed in parallel with 7E employee-app readiness**, but **7D production enablement is not a gate** for a closed employee-app pilot on shared routing.

Order suggestion:

1. Keep `COMPANY_CHANNEL_ACCOUNTS` off in production  
2. Optionally implement 7D staging pack when multi-tenant WhatsApp is on the roadmap  
3. Employee-app pilot (7E) can advance independently if it uses shared WhatsApp + app APIs  

---

## Suggested Phase 7D workstreams (when coding approved)

| Stream | Output |
|--------|--------|
| D0 | This plan accepted; flag inventory / `.env.example` note |
| D1 | Routing design ADR: inbound account map + outbound selector + fallback |
| D2 | Audience enforcement rules + structured logs |
| D3 | Staging verifier `P7DSTG01` (matrix §6) with flag ON |
| D4 | Regression suite proving flag OFF = shared-only |
| D5 | Runbook: staging enable/rollback; production enable **explicitly deferred** |

Stop before any production flag ON or live provider provisioning.

---

## Explicit decision ask (later)

After this plan is accepted, choose when to authorize **D1–D4 coding**:

- **Now (parallel):** build staging readiness while 7E is planned  
- **Later:** defer until a client requires company-owned WhatsApp  

**This document does not authorize enabling `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS` in production, provisioning WhatsApp accounts, or changing production routing.**
