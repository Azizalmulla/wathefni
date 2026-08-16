# Employee Onboarding & Document Journey — Root-Cause Audit

**Stamp:** `20260805T035000Z`  
**Scope:** Implementation truth only. No card patches. No production deploy.  
**Canaries preserved:** Talal `WATHEFNI-96550252254`, Aziz QA `WATHEFNI-96599338566` (WATHEFNI).  
**Live proof (Aziz):** 36 Wave2 rows in DB; **4 required** surface on mobile; 3 JPEGs stored as civil_id / personal_photo / employment_contract with extraction `needs_review` / `storage_only` / `low_confidence`.

---

## 1. Verdict (one paragraph)

Mobile onboarding is a thin client over `GET /app/onboarding` + `POST /app/onboarding/documents`. Uploads share **storage + `file_registry` + `employee_documents` + optional OCR extract** with Document Hub, but **skip** WhatsApp’s classify/verify gates — so any PDF/image that passes MIME/size is accepted for the claimed `item_id`. Bank is intentionally **not** an upload: `authority=ess` / `collection_mode=ess_encrypted`, yet the app has **no `/app` bank API** and renders the card as a dead “HR-managed” task. The “four-item checklist” is the **required-only** slice of Kuwait Wave2 (36 items seeded for Aziz); optional nationality/role/company extensions exist only as light required-overrides, not full templates.

---

## 2. Complete mobile upload path (truth)

```
pick (camera|library|files)
  → uploadDocument.ts (resize JPEG ≤2048 / compress 0.78; PDF passthrough)
  → AuthProvider.uploadFile multipart
  → POST /app/onboarding/documents  { file, item_id }
  → gates: employee_app_context + feature onboarding/upload_document
  → reject bank_details (bank_via_ess_required)
  → ownership: onboarding_items row for this employee+company
  → ext ∈ {pdf,jpg,jpeg,png,webp,heic}; size ≤15MB; empty reject
  → validate_employee_app_upload_type (extension ∩ declared MIME ∩ puremagic bytes)
  → prepare_document_storage_operation → store_onboarding_document
  → UPDATE onboarding_items SET status='received' + storage cols
  → extract_compliance_document_metadata(channel=ess_onboarding)  [best-effort]
  → record_employee_document_receipt
        → upsert employee_documents
        → dual_write compliance (synced types)
        → upsert_file_registry (file_kind=onboarding_document)
        → register_upload_version → governed_document_versions (pending_hr_review)
  → recompute_employee_onboarding_counts
  → audit employee_document_uploaded
```

**Affected components**

| Layer | Path / symbol |
|---|---|
| Mobile route | `apps/wathefni-employee-mobile/app/onboarding.tsx` |
| UI | `…/features/onboarding/OnboardingView.tsx` (`ChecklistCard`, `ReviewedRow`) |
| Picker | `…/lib/uploadDocument.ts` |
| Upload transport | `…/auth/AuthProvider.tsx` `uploadFile` |
| API | `app_onboarding`, `app_onboarding_document_upload` |
| Storage | `store_onboarding_document`, `document_storage_operations` |
| Receipt | `record_employee_document_receipt`, `upsert_file_registry` |
| Extract | `extract_compliance_document_metadata` → `kuwait_gcc_document_intelligence.intake.shared_channel_extraction` |
| Tables | `onboarding_items`, `employee_documents`, `file_registry`, `document_storage_operations`, `governed_document_versions`, `governed_document_events`, `compliance_documents`, `action_results` (reject audit) |

**Documents tab path (separate):** `GET /app/documents` → `employee_documents_for`; open `GET /app/documents/{file_id}`; renew `POST /app/documents/renew` (no `onboarding_items` status flip; **no** puremagic MIME gate).

---

## 3. Shared pipeline? Exact answer

| Stage | `/app` onboarding upload | Dashboard Document Hub | WhatsApp onboarding |
|---|---|---|---|
| Store bytes | **Shared** `store_onboarding_document` | Shared | Shared (after accept) |
| Receipt / registry / versions | **Shared** `record_employee_document_receipt` | Shared | Shared |
| Extract OCR/structure | **Shared** `extract_compliance_document_metadata` (`mode=extract`) | Shared | Shared after verify |
| Classify media → item | **Not called** | Not called | `classify_onboarding_media_upload` |
| Verify media matches item | **Not called** | Not called | `verify_onboarding_media_item` + `validate_onboarding_item_receipt` |
| Identity name match | **Not called** | Not called | `validate_onboarding_document_identity` (civil_id/passport) |
| MIME byte gate | **Yes** (`validate_employee_app_upload_type` / puremagic) | No | Channel-dependent |

**Fallback when extract fails:** synthetic `{extraction_status: needs_review, extraction_error: shared_extract_unavailable}` — upload still succeeds. Parser stack: Kuwait/GCC document intelligence (identity delegate / structuring / `STORAGE_ONLY_TYPES` e.g. personal_photo). **Never GPT.**

---

## 4. Why wrong files submit without real validation

| Check | Mobile client | `/app/onboarding/documents` | Effect |
|---|---|---|---|
| Extension / size / empty | Soft picker only | Enforced | Blocks junk containers |
| MIME ↔ bytes | No | Enforced (puremagic) | Blocks extension spoof; **not** “is this a Civil ID” |
| Document type vs `item_id` | No | **Skipped** | Random JPEG as `employment_contract` accepted (live Aziz) |
| Image quality / blur / completeness | Resize only | None | No reject |
| Expiry / issued dates | None | OCR proposal only; non-authoritative | Does not block receipt |
| Completeness (front+back) | None | None | Single file marks item `received` |

Live Aziz evidence: `employment_contract` stored as `.jpg` with `extraction_status=low_confidence`; `civil_id` = `needs_review`; still `onboarding_items.status=received`.

---

## 5. Replace / remove / resubmit / versioning / rejection / approval

| Capability | Truth |
|---|---|
| Preview from onboarding checklist | **Absent** — `ReviewedRow` has no open; `file_id` decorated but unused |
| Preview from Documents | **Present** — `openDocument` → `/app/documents/{file_id}` (self-scoped) |
| Remove | **No** `/app` delete API |
| Replace before HR review | UI: received items leave pending list → actionless `ReviewedRow`. Re-upload same `item_id` is still allowed by API if user could reach it |
| Resubmit after HR reject | Checklist status stays `received`; compliance journey may show `rejected_reupload` + renew on Documents. Onboarding card does **not** flip to pending |
| Versioning | Append `governed_document_versions` (`pending_hr_review`). `employee_documents` updated **in place** (not append-only). New version does not displace current `hr_reviewed` until approve |
| HR approve/reject | `POST /dashboard/posthire/.../documents/{document_type}/review` → `approve_version` / `reject_version` / `correct_metadata`. Reject requires reason. Does **not** auto-reset `onboarding_items` |
| Meaning of “approved” | HR reviewed evidence only — **not** PACI/MOI/PAM |

---

## 6. Why Bank details is a dead card

1. Template: `bank_details` → `item_type=task`, `authority=ess`, `collection_mode=ess_encrypted`, `required=true`, `owner=employee`.
2. Mobile: `allowUpload` requires `item_type===document` or `document_type` → **false** → guidance “managed by HR”, **no button**, card not pressable.
3. API: upload of `bank_details` → `bank_via_ess_required`.
4. `find_next_required_onboarding_item` **skips** bank.
5. **No** `/app/*/bank` or ESS request routes on the employee app.
6. ESS bank lives only under dashboard: `/dashboard/posthire/employee-ess/requests` (`bank_detail_change`), apply, rotate.
7. Prod gates for Aziz QA: `WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY=on` requires **both** phone prefix `965549*` **and** name `W5C-SYNTH|`. Aziz has the name prefix but phone `96599338566` → **not** synthetic. `ESS_V5_REAL_ALLOWLIST` = Talal only. `ESS_V5_BANK_REAL_ALLOWLIST` = **empty**. So even dashboard ESS bank write would deny Aziz unless gates are adjusted for this synthetic QA identity.

---

## 7. Bank schema, encryption, masking, payroll authority

| Concern | Implementation |
|---|---|
| Table | `employee_ess_bank_profiles` (`bank_ciphertext` jsonb `ess_bank_v1`, fingerprint, version, soft-delete) |
| Encryption | Fernet (`WATHEFNI_ESS_BANK_SECRET_KEY` [+ previous]) or platform sensitive encrypt; plaintext store forbidden |
| Requests | `employee_ess_requests` type `bank_detail_change`; route **HR → payroll** |
| Apply | `_apply_bank` after approvals; audited |
| Masking | Employee self always masked; HR unmask needs `employees.ess.unmask` / `employees.manage` + `employee_ess_sensitive_access_log` |
| Payroll | Decide stage `pending_payroll` requires `employees.ess.approve.payroll` |
| Onboarding plaintext | Forbidden (`onboarding_plaintext_bank_forbidden`, WhatsApp + `/app`) |

---

## 8. Onboarding template authority & “only four tasks”

| Fact | Detail |
|---|---|
| Canonical | `onboarding_wave2.DEFAULT_KUWAIT_V2` — **36 items**, `default_kuwait` @ `2.0.0` |
| Required baseline | Exactly **4**: `civil_id`, `personal_photo`, `employment_contract`, `bank_details` |
| Aziz live | Full **36** rows seeded; mobile shows `pending`+`received` = **required-only** → appears as a 4-item journey |
| Optional docs (passport, residence, …) | In `items[]` but **not** in mobile `pending`/`received` lists |
| Seed authority | `start_onboarding` → `seed_wave2_items`; prod `WATHEFNI_ONBOARDING_SEED=off` with synthetic/HR_MUTATE canary path used for Aziz |
| Nationality / role | Only `onboarding_required_overrides` via `employee_identity.employee_category` (e.g. Article 18 → residence/work_permit required). **No** multi-template registry beyond `default_kuwait` |
| Company | `companies.metadata.onboarding_template` falls back to same default |
| FOUR_REALS freeze | Seed/mutate blocked for four production reals when SEED off — Talal checklist may remain historical short set; Aziz is synthetic-named and got Wave2 |

---

## 9. Exact gaps (mapped to live symptoms)

| Symptom | Root cause |
|---|---|
| Bank tap does nothing | Non-document ESS item + no `/app` bank UI/API |
| Cannot submit bank | No employee-app ESS bank surface; allowlists would also block Aziz QA today |
| No preview/replace/remove on submitted onboarding | `ReviewedRow` actionless; no remove API; replace not wired on received list |
| Random images accepted | `/app` skips classify/verify; status→`received` regardless of extraction |
| “Only four tasks” | Required-only mobile projection of 36-row Wave2 |

---

## 10. Proposed long-term model (coherent)

**Single checklist authority** (Wave2+) shared by HR console and employee app:

1. **Employee-facing work queue** derived from same `onboarding_items` + `authority`/`collection_mode`/`owner`, not required-only truncation — group by Employee / HR / Payroll / Compliance with clear “waiting on HR” vs “your action”.
2. **Document items:** draft → validate (shared classify+verify+MIME) → submit → `processing` → `accepted` \| `rejected` \| `replacement_required`; preview/remove while draft; replace/resubmit per status; append-only versions in `governed_document_versions` (+ stop in-place-only mental model for employee_documents).
3. **Bank item:** structured ESS form (IBAN validation) + optional supporting PDF/image; encrypt to `employee_ess_bank_profiles`; HR→payroll approve; masked everywhere except audited unmask; complete `bank_details` when applied.
4. **Templates:** Kuwait baseline + overlays (nationality, residency article, industry, role, company). One assignment pin (`employee_onboarding_assignments`) remains source of truth.
5. **States machine** shared: `pending | in_progress | submitted | processing | accepted | rejected | replacement_required | waived | blocked`.

---

## 11. Backend changes required (no deploy yet)

| Area | Change |
|---|---|
| `/app/onboarding` | Return actionable projection: collection_mode, authority, actions[], file preview meta, rejection_reason, version info; include optional employee-owned items |
| `/app/onboarding/documents` | Call shared verify/classify before commit; map fail → do not set `received`; status `processing`/`replacement_required` |
| New `/app/ess/bank` (or ESS requests under `/app`) | Create/submit `bank_detail_change`; read masked status; optional evidence upload |
| Checklist sync | On HR reject → flip item + notify; on ESS bank apply → complete `bank_details` |
| Versioning | Employee-visible history; forbid silent overwrite semantics in UX |
| Gates | Controlled QA allowlist for Aziz synthetic bank without expanding real bank GA |

**Migration risk:** Medium — existing `received` rows with weak extraction must not auto-fail; dual-write compliance versions already append; flipping statuses needs backfill policy for canaries; ESS bank empty allowlist means no plaintext migration. Preserve Talal/Aziz files in `file_registry`.

---

## 12. Phased plan

| Phase | Goal | Risk |
|---|---|---|
| **P0 — Truth & contracts** | Document states + API shapes; freeze WhatsApp vs `/app` parity matrix | Low |
| **P1 — Bank ESS on mobile** | Structured bank submit + masking + complete checklist item; QA allowlist only | Med (crypto/payroll) |
| **P2 — Document lifecycle UX** | Preview / draft remove / replace / rejection reasons on shared states | Med |
| **P3 — Validation parity** | Wire classify+verify into `/app` uploads; soft→hard gate behind flag | Med-High |
| **P4 — Template overlays** | Nationality/role/company extensions beyond required overrides | Med |
| **P5 — HR↔app state sync** | Reject/approve drives same employee-visible states | Med |

Do **not** expand `EMPLOYEE_APP` / ESS bank allowlists to GA in these phases.

---

## 13. Isolation confirmation

- All `/app` paths session-bound to `company_code` + `employee_key`.
- File download self-scopes `subject_key`.
- Aziz/Talal allowlists unchanged by this audit.
- No deploy performed.
