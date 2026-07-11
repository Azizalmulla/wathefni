# Phase 7C.1 — Write-path reconciliation plan (plan only)

**Status:** Plan approved for review. **Do not implement writes** until separately approved.  
**Closed prerequisite:** Phase 7C read-only audit (`82ad185`).

**Keep OFF:**

- `WATHEFNI_EMPLOYEE_APP`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`

**Out of scope for 7C.1 / write-path v1:**

- Employee-app enablement
- Broad document upload expansion
- Production writes
- Deletes / destructive cleanup
- Silent alias merges (`residency_iqama`↔`residency`, `medical_check`↔`medical`)
- OCR expansion / template editor / onboarding seed activation

---

## 1. Exact type map

Canonical mapping for reconciliation. Keys that are not listed as compliance-relevant stay on the receipt/checklist spine only.

| Onboarding `item_id` | `employee_documents.document_type` | `compliance_documents.document_type` | Dual-write today? | Reconcile in v1? |
|----------------------|------------------------------------|--------------------------------------|-------------------|------------------|
| `civil_id` | `civil_id` | `civil_id` | yes | yes |
| `passport` | `passport` | `passport` | yes | yes |
| `work_permit` | `work_permit` | `work_permit` | no (upload allowlist omits) | checklist + optional compliance link only if ED exists |
| `residency_iqama` | `residency_iqama` | **no auto map** to `residency` | no | **flag only** — operator map later |
| `medical` *(if used as item)* | `medical` | `medical` | yes | yes |
| `medical_check` | `medical_check` *(if present)* | **no auto map** to `medical` | no | **flag only** |
| `education_cert` | `education_cert` | `education_cert` | yes | yes |
| `personal_photo` | `personal_photo` | — | no | checklist/receipt only |
| `employment_contract` | `employment_contract` | — | no | checklist/receipt only |
| `offer_letter` | `offer_letter` | — | no | checklist/receipt only |
| `bank_details` | `bank_details` | — | no | checklist/receipt only |

**Soft expiry tasks** (not compliance authority): `civil_id_expiry`, `passport_expiry`, `residency_expiry`, `work_permit_expiry`.  
v1 may mark these `done` only when the linked compliance row has a non-null `expiry_date` and operator policy says so; otherwise leave alone.

**Ambiguous families — never auto-merge in v1:**

| Family | Keys | v1 action |
|--------|------|-----------|
| residency | `residency`, `residency_iqama` | report `needs_operator_map` |
| medical | `medical`, `medical_check` | report `needs_operator_map` |
| education | `education_cert`, `education`, `certificate` | report `needs_operator_map` |

---

## 2. Rules for the 6 staging drift classes

Observed on staging `WATHEFNI` (6 events). Write-path v1 fixes **only** these classes under company scope + dry-run.

### A. Employee document exists, onboarding still pending (2)

**Examples:** `civil_id`, `bank_details` with ED `received` / present and OI `pending`.

| Step | Action |
|------|--------|
| Gate | Same company; ED row exists for matching `item_id` or exact `document_type`; OI status ∈ `{pending, missing, requested, awaiting, ''}` |
| Write | `UPDATE onboarding_items SET status='received', updated_at=now()` for that `(employee_key, item_id)` |
| Do not | Invent OI rows; change required/owner; copy file fields unless already empty and ED has storage pointer (defer file field copy to v1.1) |
| Log | `action=mark_onboarding_received`, before/after status |

### B. Compliance exists without employee document (2)

**Examples:** compliance `medical`=`received`, `passport`=`valid` with no ED of same type.

| Step | Action |
|------|--------|
| Gate | Compliance status ∈ received-like / `valid` / `expiring_soon` / `needs_review` OR non-null expiry |
| Prefer | If file_registry has matching `(subject_key, document_type)` → **create ED from file + compliance metadata** (upsert), then optionally sync OI |
| Else if | Compliance is seed/manual without file → **do not invent ED**; emit `action=skip_compliance_orphan_no_file` for operator review |
| Never | Delete the compliance row in v1 |
| Log | create ED plan or skip reason |

### C. Expiry mismatch (1)

**Example:** `civil_id` ED expiry ≠ compliance expiry.

| Step | Action |
|------|--------|
| Authority | See §3 — choose **newer non-null** expiry |
| Prefer order | (1) ED `expiry_date` if non-null and ≥ compliance, (2) else compliance if non-null and newer, (3) if equal keep both |
| Write | Set the lagging store to the winning date; recompute compliance `days_until_expiry` / renewal bucket fields from that date |
| Never | Write null over a non-null date; write an older date over a newer one |
| Log | `action=sync_expiry`, winner source, both before values |

### D. Received compliance with null expiry (1)

**Example:** compliance `medical` status `received`, `expiry_date` NULL.

| Step | Action |
|------|--------|
| If ED has non-null expiry | Copy ED → compliance (and refresh days_until_expiry) |
| Else if extraction/metadata on ED or compliance has parseable expiry | Promote into both ED + compliance if missing |
| Else | **No write** — set planned action `needs_review` / leave status as-is (or `needs_review` only if already in classifier vocabulary and approved) |
| Never | Fabricate an expiry date |
| Log | copy vs skip |

### Classes intentionally **not** auto-fixed in v1

From the closed audit, these were **0** on staging and stay **manual / later**:

- received without ED
- ED without file / orphan files
- company mismatch / orphan keys
- duplicates
- ambiguous type mappings

If any appear later, dry-run reports them as `manual_only`.

---

## 3. Field authority matrix

| Concern | Authoritative store | Notes |
|---------|---------------------|-------|
| File identity | `file_registry` | `file_id`, `content_sha256`, storage provider/object/url/status |
| Receipt / submission | `employee_documents` | Durable proof a document was accepted; links `item_id` + `document_type` |
| Checklist status | `onboarding_items.status` | Workflow UX; may be advanced from ED receipt, never invents files |
| Expiry date | **Newer non-null** across ED ↔ compliance | Soft OI expiry tasks are **not** authority |
| Compliance alert status | `compliance_documents` (derived) | Derived from receipt + expiry via existing classifier; do not invent “valid” without receipt or HR action |

**Derived write direction (v1):**

```
file_registry ──supports──► employee_documents ──may advance──► onboarding_items
                         └──may upsert/sync──► compliance_documents (mapped types only)
```

---

## 4. Dry-run first behavior

CLI shape (future implementation; not built yet):

```bash
python3 ops/staging-phase7c1-reconcile-docs.py \
  --company WATHEFNI \
  --mode dry-run \
  --json-out /tmp/p7c1-plan.json
```

Dry-run must:

1. Open **read-only** DB session (same proof as 7C).
2. Emit a full plan of intended writes: table, PK/natural key, column diffs, reason, drift class.
3. Write **zero** rows.
4. Exit non-zero only on tool/config errors, not on finding drift.
5. Require a second explicit invocation for apply:

```bash
... --mode apply --confirm-company WATHEFNI --i-understand-writes
```

`--mode apply` without both confirm flags must refuse.

---

## 5. Company-scoped execution only

- `--company` required (exact `company_code`).
- Refuse `ALL` / `*` (even with unsafe flags) in v1.
- Every SELECT/UPDATE filtered by `company_code` **and** employee membership in that company.
- Cross-tenant / null `company_code` rows → `manual_only`, never auto-heal across tenants.
- Protected production company (`WATHEFNI`) may be planned on staging freely; **production apply requires separate canary approval** (§10).

---

## 6. No deletes in v1

Forbidden:

- `DELETE` on any of the four stores
- Soft-delete / status=`void` as cleanup (unless already a product status and separately approved)
- Dropping duplicate rows (duplicates → report only)

Allowed:

- `UPDATE` existing rows
- `INSERT` missing `employee_documents` when justified by file_registry (+ optional compliance metadata)
- `INSERT` missing compliance row **only** when ED exists for a dual-write mapped type and compliance is absent (inverse of “compliance without ED”; rare if upload path worked)

---

## 7. Expiry overwrite guard

Pseudo-rule for every expiry write:

```
if new_expiry is None:
    skip  # never null-out
elif existing is None:
    set new_expiry
elif new_expiry >= existing:
    set new_expiry   # equal or newer
else:
    skip  # older loses; log conflict
```

Same guard applies when copying compliance → ED or ED → compliance.

---

## 8. Logging / audit of every planned write

Each planned or applied mutation emits one structured event (JSONL + optional DB audit table later):

| Field | Purpose |
|-------|---------|
| `event_id` | UUID |
| `ts` | UTC ISO |
| `mode` | `dry-run` \| `apply` |
| `company_code` | scope |
| `sample_id` | hashed employee key (no PII) |
| `drift_class` | e.g. `employee_doc_without_received_item` |
| `action` | e.g. `mark_onboarding_received` |
| `table` | target table |
| `natural_key` | e.g. `(employee_key_hash, item_id)` / `(…, document_type)` |
| `before` | column subset |
| `after` | column subset |
| `skipped` | bool + reason |
| `actor` | `phase7c1-reconcile` + operator / host |

Apply mode must write the same events **before** commit (or in the same transaction as an `audit_events` insert if that table is chosen later).  
Dry-run persists the plan file under `ops/reports/` for review.

---

## 9. Staging write-path test plan

Use throwaway company preferred (e.g. `P7C1STG01`), not only live staging `WATHEFNI`.

| # | Case | Setup | Expect |
|---|------|-------|--------|
| 1 | Dry-run no writes | Seed A–D drift on throwaway | Plan lists N writes; DB checksums unchanged; `transaction_read_only` on dry-run path |
| 2 | Refuse unscoped | `--company` missing / `ALL` | Exit refuse |
| 3 | Checklist catch-up | ED received + OI pending | Apply → OI `received`; re-audit class A = 0 for that row |
| 4 | Compliance orphan + file | Compliance received, no ED, file present | Apply → ED insert; no delete |
| 5 | Compliance orphan, no file | Compliance only | Apply → skip logged; no ED invented |
| 6 | Expiry newer wins | ED older, compliance newer | Both converge to newer; null never written |
| 7 | Expiry older rejected | Candidate older than existing | Skip; log conflict |
| 8 | Null expiry fill | Compliance received null; ED has date | Compliance filled from ED |
| 9 | Null expiry no source | Both null | Skip / needs_review; no fabricated date |
| 10 | Alias no-merge | `residency` + `residency_iqama` | Plan `needs_operator_map`; zero auto writes |
| 11 | Idempotency | Apply twice | Second apply empty plan |
| 12 | Re-audit | Run 7C audit after apply | Target drift classes reduced; file/orphan/tenant still 0 |
| 13 | Flag posture | After tests | `EMPLOYEE_APP` + `COMPANY_CHANNEL_ACCOUNTS` still off |

Only after throwaway green: optional **dry-run** against staging `WATHEFNI` (apply on `WATHEFNI` staging still needs explicit approval).

---

## 10. Production write canary — later?

**Yes — a production write canary is recommended before any broad prod reconcile**, but **not now**.

Recommended later sequence:

1. Implement 7C.1 tool behind explicit CLI (no cron, no flag that auto-runs).
2. Staging throwaway apply green (§9).
3. Staging `WATHEFNI` dry-run reviewed by operator.
4. Staging `WATHEFNI` apply (if still desired) with backup / snapshot note.
5. **Production:** dry-run only on one agreed company → human review of JSONL plan.
6. **Production canary apply:** one employee or one document type max, then re-run 7C audit.
7. Stop. No fleet-wide prod reconcile without a separate approval.

Until that approval:

- No production writes
- No employee-app enablement
- No broad upload expansion

---

## Implementation gate (when approved)

Ship order if/when write-path is approved:

1. Shared type-map module (single source for audit + reconcile)
2. `ops/staging-phase7c1-reconcile-docs.py` with dry-run default
3. Staging verifier with throwaway company
4. Runbook: `ops/PHASE7C1_RECONCILE_CANARY_RUNBOOK.md` (prod dry-run/canary — inactive until approved)

**This document is the plan only. No write-path code is authorized by Phase 7C.1 acceptance of the plan itself.**
