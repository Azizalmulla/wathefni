# Kuwait Onboarding Wave — Close Stamp

**Stamp:** `20260806T004945Z`  
**Evidence:** `ops/evidence/kuwait-onboarding-wave-close-20260806T004945Z/`  
**Decision:** **CLOSE** the current Kuwait onboarding feature wave. Operate under freeze + soft canary only. No HARD DocVal. No broad GA.

---

## 1. Audited baseline (live today)

### HR web (WATHEFNI) — production GO / frozen
- Template `default_kuwait@2.0.0`
- Checklist inspector, mark/waive, HR document upload
- Wave 2A approve / reject → `replacement_required` (canary employees)
- Bank ESS-owned · plaintext forbidden
- Broad auto-SEED off

### Employee app — Aziz + Talal canary only
| Capability | Status |
|---|---|
| Wave 2A lifecycle (preview / versions / replace / resubmit) | **Live soft canary** |
| DocVal soft-gate (`SOFT=on` · `HARD=off`) | **Live soft canary** |
| Capture quality (blur/glare/resolution hard; crop weak+supported) | **Live soft canary** |
| Calm EN/AR correction copy · no raw API codes | **Live soft canary** |
| Bank details submit | **Not live** (item visible only) |
| Native document scanner | **Deferred** (prep stubs only) |

### Checklist items (v2)
Employee upload: `civil_id`, `personal_photo`, `employment_contract`, optional `passport` / `residence` / `work_permit`  
HR: `offer_letter` + readiness tasks  
ESS: `bank_details`  
System: expiry mirrors  

---

## 2. Civil ID DocVal canary — CLOSED

| Outcome | Result |
|---|---|
| Clear frame-filling Civil ID | **Accepted** (crop false-positive fixed) |
| Random non-document | **Rejected** with wrong-document copy (not blur/crop) |
| Crop false-positive | **Fixed** — `crop_hot_sides` weak signal only |
| Raw errors | **None** — calm EN/AR DocVal messages |
| Disposable item | **`civil_id_canary_test` removed** |

### Cleanup proof (`audit/canary-cleanup.json`)
- Deleted only canary-scoped rows (versions/events/files/item)
- Real Aziz `civil_id` remains **`accepted`** · sha `fe98f7d9…0bb7`
- Real versions / audit history for non-canary docs **untouched**

### Related evidence stamps (DocVal soak)
- `docval-decision-order-20260806T001109Z`
- `docval-crop-false-positive-fix-20260806T003126Z`
- `docval-capture-quality-layer-20260806T000158Z`
- prior parity / try-again / identity-alias stamps in canary log

---

## 3. What stays on (explicit)

```
WATHEFNI_ONBOARDING_LIFECYCLE_V2A=on
WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES=WATHEFNI
WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566,WATHEFNI-96550252254

WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT=on
WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD=off
WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES=WATHEFNI
WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566,WATHEFNI-96550252254
```

**Do not** enable HARD DocVal or broaden allowlists without owner change-control.

---

## 4. Remaining pre-GA work (recorded residuals)

1. **Bank-details submission** in the employee app (Wave 2B ESS encrypted path)
2. **Proper Civil ID front-and-back** handling (UX + validation contract beyond single-file / missing_side signals)
3. **Qualify remaining DocVal flows** on soft canary: passport, residence, work permit, employment contract, personal photo
4. **Controlled rollout** beyond Aziz/Talal (still not GA)
5. **Native document scanner** — VisionKit / ML Kit — **deferred until the end** (`docs/NATIVE_DOCUMENT_SCANNER_PREP.md`)

---

## 5. Freeze relationship

Supersedes open DocVal canary testing on disposable item.  
Does **not** reopen `ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` HR freeze.  
Does **not** authorize broad employee-app onboarding GA.

**Next product wave:** Authentication Wave 2 — audit & plan only (`ops/AUTHENTICATION_WAVE2_AUDIT_AND_PLAN.md`). No auth code until approved.
