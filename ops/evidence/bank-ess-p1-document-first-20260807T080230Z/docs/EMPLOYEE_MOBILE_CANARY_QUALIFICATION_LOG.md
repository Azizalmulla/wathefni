# Employee Mobile — Rolling Canary Qualification Log

**Canary employees:** Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254`  
**Process:** `ops/EMPLOYEE_MOBILE_CONTINUOUS_WAVE_PROCESS.md`  
**Rule:** `.cursor/rules/employee-mobile-continuous-waves.mdc`

Append one row (or section) per internal ship. Do not wait for owner review between rows.

---

## 20260807T080230Z — Bank ESS P1 document-first KW certificate OCR (PASS)

| Field | Value |
|---|---|
| Scope | P1 only: document-first upload · Kuwait/GCC Mistral extraction · confirm/correct · manual fallback · evidence link · HR extraction summary · authority preserved |
| Backend | `employee_bank_ess.py` · `app.py` · `kuwait_gcc_document_intelligence/{schemas,intake,extraction}.py` |
| Flags | `WATHEFNI_BANK_ESS_OCR_V1=on` · companies `WATHEFNI` |
| Contract | `ops/BANK_ESS_AND_ONBOARDING_COMPLETION_CONTRACT.md` (`bank_ess_v1_p1_document_first`) |
| Dashboard | BankReviewPanel extraction status EN+AR |
| Mobile OTA | canary `95d11ede-9516-4d85-bc73-936167b83fa3` |
| Prove | P1 focused **8/8 + 12/12** · Qual Bank ESS **51/51** · onboarding **31/31** · Aziz FP unchanged `0f349ce848ab5e4b` |
| Migrations | Additive `employee_bank_evidence.extraction_*` only |
| Verdict | **`PASS`** (residual: real IBAN-letter OCR field richness not live-proven on synthetic PDF) |
| Stamp | `ops/evidence/bank-ess-p1-document-first-20260807T080230Z/` |
| Next | Optional physical Aziz/Talal certificate walk. **Do not start P2. Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T074024Z — Bank ESS P0 verified-at-HR (PASS)

| Field | Value |
|---|---|
| Scope | P0 only: HR approve=verified · Apply=effective · state/copy · withdraw onboarding sync · needs_review recovery · KW IBAN at submit · Profile/Settings Bank entry · dual-control preserved |
| Backend | `employee_bank_ess.py` · `employee_selfservice_wave5.py` · `app.py` |
| Contract | `ops/BANK_ESS_AND_ONBOARDING_COMPLETION_CONTRACT.md` |
| Dashboard | Bank review labels/copy EN+AR |
| Mobile OTA | canary `d73cd3c7-703e-4d66-a865-90d90b925125` |
| Prove | Qual Bank ESS **47/47** · onboarding **31/31** · Aziz effective FP unchanged `0f349ce848ab5e4b` |
| Migrations | None |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/bank-ess-p0-verified-at-hr-20260807T074024Z/` |
| Next | P1 / document OCR not started. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T063432Z — Invitation/delivery physical acceptance (PASS w/ residuals)

| Field | Value |
|---|---|
| Scope | HR EN+AR needles · states · Resend/Re-invite · code exception gating · Aziz emailed-code activate → session reopen · HR activated · no pending duplicates |
| Prove | `canary-prod-employee-app-invitation-physical.py` PASS · live activate/refresh PASS · copy vitest 4/4 · PIN crypto PASS |
| Residuals | On-device PIN/Face ID UI (no USB) · headless profile-card screenshot incomplete (bundle+API cover copy) |
| Verdict | **`PASS`** (with residuals) |
| Stamp | `ops/evidence/employee-app-invitation-physical-20260807T063432Z/` |
| Next | Optional owner glance at Aziz App access EN/AR. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T061923Z — Employee app invitation + delivery (PASS canary)

| Field | Value |
|---|---|
| Scope | Long-term invitation/delivery (separate from Auth Wave 2): auto-invite · email/WhatsApp deliver · HR status · Resend/Re-invite without code · exception code handoff only |
| Contract | `ops/EMPLOYEE_APP_INVITATION_DELIVERY_CONTRACT.md` |
| Backend | `employee_app_invitation.py` · create/onboarding hooks · dashboard `/app-invitation*` · outbound `company_code` fix on WhatsApp session |
| Flags | `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE=on` · `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES=WATHEFNI` |
| Dashboard | App access invitation status + Resend/Re-invite (no normal code) |
| Prove | Smoke PASS · Aziz live reinvite **delivered via email** · no code disclosure · Phase 6 not started |
| Verdict | **`PASS`** (canary) — optional physical HR EN/AR UI walk |
| Stamp | `ops/evidence/employee-app-invitation-delivery-20260807T061923Z/` |
| Next | Continue continuous wave. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260806T230823Z — Auth Wave 2 Phase 2 Face ID gating fix (PARTIAL)

| Field | Value |
|---|---|
| Finding | Opt-in skipped after PIN · reopen PIN-only |
| Fix | Relax usable (hardware+enrolled) · one-time boot recovery offer · OTA `aec3862c-70b5-47d3-9a2e-d7f07eade52b` |
| Verdict | **`partially proven`** — confirm Face ID offer + unlock on device |
| Stamp | `ops/evidence/auth-wave2-phase2-biometric-fix-20260806T230823Z/` |

---

## 20260806T230037Z — Auth Wave 2 Phase 2 Face ID / Touch ID (PARTIAL)

| Field | Value |
|---|---|
| Scope | Optional Face ID/Touch ID after PIN · auto prompt on reopen · PIN fallback · Settings toggle · canary Aziz/Talal |
| Native | iOS `24c71b0a-6b09-4bb3-8d0d-c1e5dcbdc076` (build 10) · Android `e7eefb47-abfb-4b0e-8387-bf02b75805cc` (vc 3) |
| Channel | Canary OTA `02919c30-f663-4471-a8a6-058dbdf37054` · PIN=1 · BIOMETRIC=1 |
| Prove | Bio unit 34/34 · PIN 38/38 · hardening 28/28 · live preserve 10/10 |
| Restore | Aziz code **321898** · phone `99338566` |
| Verdict | **`partially proven`** — install native → OTA → physical Face ID matrix |
| Stamp | `ops/evidence/auth-wave2-phase2-biometric-20260806T230037Z/` |
| Next | Owner device qualify. **Stop — no Phase 3.** |

---

## 20260806T225101Z — Auth Wave 2 Phase 1 session-hardening (PARTIAL)

| Field | Value |
|---|---|
| Scope | Stop random “Session expired” · central `classifyAuthFailure` · wipe only after definitive refresh reject / stale epoch / inactive / logout · soft keep on network/5xx/language |
| Channel | Canary OTA `41239180-9b5a-4cc1-88f7-7a2f8d2ad7f8` · PIN=1 · biometric=0 |
| Prove | Hardening unit 28/28 · PIN unit 38/38 · Wave1 live 30/30 |
| Verdict | **`partially proven`** — owner device matrix (force-quit / offline / EN↔AR / PIN / logout / revoke) |
| Stamp | `ops/evidence/auth-wave2-phase1-session-hardening-20260806T225101Z/` |
| Next | Force-quit → pull OTA → confirm no spurious OTP. Biometrics stay off until this closes. |

---

## 20260806T223109Z — Auth Wave 2 Phase 1 seamless EN↔AR (PARTIAL)

| Field | Value |
|---|---|
| Scope | Remove language restart Alert · silent RTL reload · cover to avoid flash · keep session/PIN preserve |
| Channel | Canary OTA `7a0d99fc-0e0e-44be-8b9f-5cc4ad9c8b20` |
| Prove | Unit 37/37 · Wave1/Bank 30/30 |
| Verdict | **`partially proven`** — owner EN→AR→EN once, then fully proven |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T223109Z/` |
| Next | Force-quit → OTA → Settings EN↔AR (no dialog). No Phase 2. |

---

## 20260806T222232Z — Auth Wave 2 Phase 1 locale restart session wipe fix (PARTIAL)

| Field | Value |
|---|---|
| Finding | After RTL restart Alert, `/me` failure → `clearLocalAuthMaterial` → Session expired → OTP |
| Fix | Preserve marker · never wipe on locale restart · fall back to PIN lock not activation |
| Channel | Canary OTA `9dc373a9-b9ce-4a7a-9877-5023454ecdc3` |
| Restore | Aziz activation code **692269** issued |
| Prove | Unit 37/37 · Wave1/Bank live 30/30 |
| Verdict | **`partially proven`** — physical EN↔AR/AR↔EN after restore |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T222232Z/` |

---

## 20260806T221706Z — Auth Wave 2 Phase 1 RTL language restart fix (PARTIAL)

| Field | Value |
|---|---|
| Finding | EN→AR used silent `DevSettings.reload` after `forceRTL` — looked like a crash |
| Fix | Confirm Alert · `Updates.reloadAsync` · one-shot unlocked session resume (no OTP/PIN) |
| Channel | Canary OTA `173506a4-e2ea-4a66-9d1e-d5b2860c426c` · no native build |
| Prove | Unit 34/34 · Wave1+Bank live 30/30 · Bank/onboarding unchanged |
| Verdict | **`partially proven`** — confirm Alert + resume once on device |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T221706Z/` |
| Next | Force-quit → OTA → Settings EN↔AR · no biometrics |

---

## 20260806T215837Z — Auth Wave 2 Phase 1 local PIN (PARTIAL)

| Field | Value |
|---|---|
| Scope | Local 6-digit PIN create/unlock/change · 5-fail → OTP · Aziz/Talal canary · flag `EXPO_PUBLIC_LOCAL_PIN_UNLOCK` |
| Channel | Canary OTA group `b41cdbcf-9338-4073-a0be-af8ea9773c71` · runtime 0.1.0 · **no native build** |
| Prove | Unit 29/29 · crypto PASS · capability GREEN · Wave 1 live 30/30 · Bank/onboarding unchanged |
| Verdict | **`partially proven`** — physical force-quit/PIN soak pending on Aziz/Talal devices |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T215837Z/` |
| Next | Owner: force-quit → OTA → OTP→PIN→unlock→5-fail→Change PIN · EN/AR. Do **not** start biometrics. |

---

## 20260806T214259Z — Auth Wave 2 Phase 0 Wave 1 freeze (READY_FOR_PHASE_1)

| Field | Value |
|---|---|
| Scope | Freeze OTP activate / request-code / refresh / logout / new-device revoke / Kuwait aliases / session_epoch / SecureStore — no PIN |
| Tests | Unit **35/35** · live Aziz+Talal **30/30** · bank/onboarding snapshots unchanged |
| Verdict | **`ready_for_phase_1`** — Phase 1 not started |
| Stamp | `ops/evidence/auth-wave1-freeze-20260806T214259Z/` · contract `ops/AUTH_WAVE1_FROZEN_CONTRACT.md` |
| Next | Wait for explicit Phase 1 authorization |

---

## 20260806T213600Z — Auth Wave 2 readiness reassessment (READY)

| Field | Value |
|---|---|
| Scope | Reassess Auth Wave 2 after real-bank acceptance; no auth code |
| Gates | Bank ESS + onboarding fully proven · withdrawn cannot resurface · EN/AR/mobile · permissions/tenant/idempotency/migration/payroll green |
| Verdict | **`ready`** — Phase 1 = local PIN unlock only (biometrics / idle / recovery / device trust deferred) |
| Stamp | `ops/AUTH_WAVE2_READINESS_DECISION.md` · evidence `ops/evidence/aziz-real-bank-acceptance-20260806T212710Z/` |
| Next | Owner may authorize Phase 1 implementation; do not start Phase 2+ |

---

## 20260806T212710Z — Aziz real bank acceptance (PASS)

| Field | Value |
|---|---|
| Scope | Read-only acceptance after real submit → HR → payroll → Apply |
| Live truth | Verified Gulf bank / ABDULAZIZ HAMAD RASHED ALMULLA / last4 **9548** · onboarding **completed** 4/4 · absent from queue · surfaces agree · reconcile `changed: false` |
| Defect found | Stale walkthrough `withdrawn` still projected as Bank submission; fixed with bank-of-record cutoff |
| Channel | Backend projection only (no mobile OTA) |
| Verdict | **`ACCEPTANCE_PASS`** 19/19 |
| Stamp | `ops/evidence/aziz-real-bank-acceptance-20260806T212710Z/` |
| Next | Auth Wave 2 remains blocked |

---

## 20260806T193736Z — Correction resubmit 409 + field-error UX (DEPLOYED)

| Field | Value |
|---|---|
| Live finding | Physical resubmit POST `/app/bank/requests` → **409** `bank_request_already_active` on request `d65628a4…` (`needs_information`); IBAN fixture valid; mobile showed generic error |
| Fix | Replace sealed proposal on `needs_information`/`draft` and return to `pending_hr` · field-level validation errors · preserve form · busy/idempotency lock |
| Channel | Backend + canary OTA group `e3d3ffae-14a8-42f9-bc87-301763b0b0cd` · iOS `019fd894-c5e9-7601-bbd2-edaf8618f7d9` · Android `019fd894-c5e9-7d94-88d5-7a7b36f3aff5` |
| Prove | `RESUBMIT_REPLACE_PROOF_PASS` — same request_id, `needs_information → pending_hr`, display IBAN last4 `0000` |
| Verdict | **`deployed`** — continue Phase 2 HR review of Aziz’s corrected request |
| Stamp | `ops/evidence/bank-ess-phase2-resubmit-ux-20260806T193628Z/` |
| Next | Aziz force-quit/reopen → Bank shows under review; HR Approve → Payroll → Apply. Auth Wave 2 blocked. |

---

## 20260806T192823Z — Returned-state submitted date patch (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Returned/resubmitted Bank screen: compose `Submitted on` + real date in code; strip leftover `{date}`/`{{date}}` from `bank.submittedAt` |
| Channel | Canary OTA group `f4f7a2d6-da32-45b6-a08c-4669e66701d4` · iOS `019fd88c-567c-7be3-af0f-c8e5a4db24fc` · Android `019fd88c-567c-7ef6-b58a-491a29ecb163` · full rebuild (iOS 1303 modules) |
| Verdict | **`deployed`** — force-quit/reopen then confirm date; use synthetic IBAN `KW30TEST0000000000000000000000` for resubmit |
| Stamp | `ops/evidence/bank-ess-phase2-approval-date-validation-20260806T191329Z/mobile/` |

---

## 20260806T191329Z — Bank approval stages + date + validation correction (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Distinguish HR approval → payroll approval → apply · concurrency guard + in-memory duplicate lock · render submitted date without placeholder interpolation · enforce registry-based IBAN/account format + checksum validation |
| Audit finding | First click succeeded `pending_hr → pending_payroll`; second click succeeded `pending_payroll → approved`; neither click applied |
| Remediation | Invalid approved Aziz request `d65628a4…` returned through audited `approved → needs_information`; no invalid value became payroll-effective |
| Channel | Backend enforcement + dashboard `PostHire-BOf-Lh9g.js` + canary OTA group `f77228cd-af7d-4235-9c08-4392f019addc` · iOS `019fd880-8f4f-77d3-9934-5674e5c217b3` · Android `019fd880-8f4f-7580-b129-c6f251eac274` |
| Qualification | Dashboard Vitest 24/24 + build PASS · mobile typecheck + capability GREEN · malformed KW/generic identifiers rejected · health 200 · remediation audit verified |
| Verdict | **`deployed`** — continue the same Phase 2 with Aziz correcting/resubmitting a valid IBAN |
| Stamp | `ops/evidence/bank-ess-phase2-approval-date-validation-20260806T191329Z/` |
| Next | Aziz force-quit/reopen, verify real submitted date + correction reason, resubmit valid IBAN; HR verifies distinct HR/payroll/apply stages. Auth Wave 2 remains blocked. |

---

## 20260806T185624Z — HR onboarding drawer visual correction (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Remove always-expanded Bank panel · compact Bank row under Needs HR · open canonical review only from **Review bank** · drawer-safe single-column values |
| Channel | Dashboard-only `PostHire-C_o12y1w.js` · no backend/OTA change |
| Qualification | Focused Vitest 21/21 · build PASS · 1,134 controls / 0 dead · live asset 200 |
| Verdict | **`deployed`** — continue the same Phase 2 review |
| Stamp | `ops/evidence/bank-ess-hr-drawer-cleanup-20260806T185624Z/` |
| Next | Hard-refresh dashboard; open Aziz → Needs HR action → Review bank |

---

## 20260806T184542Z — HR onboarding drawer Bank review + clarity (DEPLOYED · continue Phase 2)

| Field | Value |
|---|---|
| Scope | Wire `BankReviewPanel` into onboarding drawer · ownership groups (Needs HR / Waiting on employee / payroll-other / Completed) · compact rows + View details · bank checklist sync from ESS · fix mobile `Submitted on {{date}}` |
| Channel | Dashboard `PostHire-CUJvv77p.js` · backend reconcile/sync · OTA `59ec9dc5-2ffb-4018-b64c-788f3bb94b31` |
| Prove | Aziz bank `processing` + `being_reviewed` + `review_bank` · completion `waiting_on_hr` |
| Verdict | **`deployed`** — continue Phase 2 HR Approve/Reject/Apply walk |
| Stamp | `ops/evidence/bank-ess-hr-drawer-phase2-20260806T184542Z/` |
| Next | Hard-refresh dashboard + mobile OTA · Auth Wave 2 still blocked |

---

## 20260806T182313Z — Temporary Aziz Bank ESS allowlist for physical form test (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Add Aziz `WATHEFNI-96599338566` to Bank ESS + ESS bank real allowlists via temporary systemd drop-in (normal eligibility — no UI hardcode) |
| Channel | Backend env only · **no OTA** (tip remains `388e8cf5…`) |
| Prove | `/app/me` bank enabled · onboarding `open_bank` · `/app/bank` 200 · EN/AR OK |
| Cleanup | `ops/evidence/bank-ess-aziz-temp-allowlist-20260806T182313Z/cleanup/REMOVE_AZIZ_AFTER_PHASE2.sh` **after Phase 2** |
| Verdict | **`deployed`** — awaiting Aziz physical Bank form walk |
| Stamp | `ops/evidence/bank-ess-aziz-temp-allowlist-20260806T182313Z/` |
| Next | Aziz force-quit → Open bank → submit real form · Auth Wave 2 still blocked |

---

## 20260806T181405Z — Bank ESS eligibility align me/onboarding/bank (DEPLOYED · physical walk pending)

| Field | Value |
|---|---|
| Scope | Same canonical Bank ESS eligibility for `/app/me`, `/app/onboarding` (`open_bank` only when eligible), `/app/bank`; mobile CTA + route gated; Aziz stays allowlist-disabled (no hardcode) |
| Channel | Backend production + JS OTA `canary` `0.1.0` group `388e8cf5-1d6b-4140-9c84-bfff55504928` · iOS `019fd849-26c1-72ec-94b8-500e667e3bc0` |
| Prove | Live matrix PASS: Aziz ineligible (no `open_bank`, bank 403) · synthetic `7001` eligible (open_bank + bank 200) · EN/AR onboarding 200 |
| Capability | GREEN · export fingerprint includes syncLayoutLocale guard + bank gates |
| Verdict | **`deployed`** — physical force-quit/reopen walk still needed on canary iPhone |
| Stamp | `ops/evidence/bank-ess-eligibility-align-20260806T173727Z/` |
| Rollback | OTA → prior tip `85f648c9-73a0-4b14-9d8e-838913496a4d` · backend `app.py.bak-bank-elig*` |
| Next | Owner physical: no Open bank CTA for Aziz · no fresh-start crash · then continue Phase 1 soak (Auth Wave 2 still blocked) |

---

## 20260806T154352Z — Phase 1 clean Bank/completion UI deploy (BLOCKED)

| Field | Value |
|---|---|
| Scope | Clean deploy of Bank ESS + onboarding-completion UI only (no full lifecycle qual, no Auth Wave 2) |
| Attempt | Release branch `release/bank-ess-ui-20260806T154352Z` · worktree from HEAD · VPS apps overlay · contract check OK |
| Blocker | Live PostHire source not recoverable without OCR regression **or** shipping dirty WIP (`MigrationSyncShell` / Leave / Shifts / soft-keep not in live bundle) |
| Prod change | **None** — dashboard SHA unchanged `PostHire-6LCFY5pA` · health 200 · no OTA |
| Verdict | **`blocked`** |
| Stamp | `ops/evidence/bank-ess-ui-clean-deploy-20260806T154352Z/` |
| Next | Freeze PostHire source matching live OCR bundle, then surgical bank/completion patch + deploy |

---

## 20260806T153212Z — Bank ESS + onboarding completion UI (DONE · Auth Wave 2 still blocked)

| Field | Value |
|---|---|
| Scope | Employee `/bank` screen · canonical completion on checklist · HR `BankReviewPanel` + `OnboardingCompletionStrip` · sealed proposals / three-layer authority already live on backend |
| Channel | Backend already canary-deployed · UI locally built + contract-qualified · **no** production dashboard rsync / OTA this stamp (tree has unrelated WIP) |
| Backend matrix | Bank ESS **43/43** · Onboarding **27/27** (`qual-20260806T052441Z`) |
| UI quals | Mobile capability foundation GREEN · dashboard Vitest 451 PASS · build PASS |
| Verdicts | Bank ESS **partially proven** · Onboarding completion **partially proven** · Auth Wave 2 **blocked** |
| Residual | Clean UI deploy + Aziz/Talal EN/AR live walk required before `fully proven` / Auth unblock |
| Stamp | `ops/evidence/bank-ess-onboarding-completion-20260806T052304Z/` · readiness `ops/AUTH_WAVE2_READINESS_DECISION.md` |
| Next | Clean deploy of bank/completion UI only → live canary walk → re-stamp |

---

## 20260806T035255Z — HR OCR summary UI + docs wave close (DONE · Bank ESS next)

| Field | Value |
|---|---|
| Scope | Shared `DocumentExtractionSummary` on Compliance + Onboarding · mask document numbers · extracted vs verified · Civil ID F/B + pair · no auto-overwrite · six-type live HTTP re-qual |
| Channel | Dashboard dist `/var/www/wathefni-dashboard` + orchestrator journey/OCR enrich · canary DocVal/lifecycle unchanged · HARD off |
| Verdicts | All six document types **fully proven** incl. `hr_ocr_summary_ui` · civil SHA unchanged · canaries cleaned |
| Residual | Real-world OCR accuracy needs continued sampling · Bank ESS still open · Auth Wave 2 blocked until Bank ESS + onboarding complete |
| Stamp | `ops/evidence/hr-ocr-summary-ui-20260806T035255Z/` |
| Next | Bank ESS |

---

## 20260806T033827Z — Kuwait docs live-HTTP qualification matrix (DONE · Bank ESS still open)

| Field | Value |
|---|---|
| Scope | Full disposable-canary matrix: Civil ID F+B, passport, residence, work permit, employment contract, personal photo · HR projection + approve/reject/replace · OCR schemas · never touch real Civil ID |
| Channel | Live uvicorn HTTP only (no TestClient) · minted Aziz session · per-type subprocess isolation · timeouts/retries/partials |
| Verdicts | All six **partially proven** (shared: HR OCR summary UI hidden; Civil ID also identity_matching partial). None missing/broken after WP/contract fixture rerun |
| Civil ID | SHA `fe98f7d9…` accepted unchanged · canary leftovers 0 |
| Smokes | `smoke-test-onboarding-civil-id-dual-side.py` OK · uvicorn `/docs`+`/openapi.json` 200 |
| Stamp | `ops/evidence/kuwait-docs-qual-matrix-20260806T033827Z/` |
| Residual | Bank ESS separate · HR OCR UI not shown · do not claim mobile onboarding complete |

---

## 20260806T20260806T020012Z — Dual-side Front upload 500 fix (READY for phone retest)

| Field | Value |
|---|---|
| Root cause | OCR `date`/`datetime` not JSON-serializable on `attach_part` / lifecycle meta |
| Fix | `_json_ready` + lifecycle meta sanitize · deployed |
| Prove | Front upload smoke HTTP 200 · canary reset pending · civil_id SHA unchanged |
| Stamp | `ops/evidence/civil-id-dual-side-front-500-fix-20260806T020012Z/` |

---

## 20260806T015133Z — Civil ID dual-side disposable canary LIVE (READY for mobile front/back test)

| Field | Value |
|---|---|
| Scope | Prod deploy dual-side · flags Aziz-only · create `civil_id_dual_side_canary` · real Civil ID untouched · canary OTA Front/Back UX |
| Channel | Backend + JS OTA `canary` `0.1.0` group `968adf2a-135f-4cae-b4cc-7136f74628de` |
| Proven | Canary in `your_actions` with `upload_front`/`upload_back` · civil_id accepted sha `fe98f7d9…` unchanged · legacy_single |
| Stamp | `ops/evidence/civil-id-dual-side-canary-live-20260806T015133Z/READY.md` |
| Owner | Force-close app → Onboarding → CANARY front then back live test |

---

## 20260806T014717Z — Civil ID front+back dual-side (IMPLEMENTED · canary prove pending deploy)

| Field | Value |
|---|---|
| Scope | One `civil_id` item · Front/Back parts on one draft attempt · pair gate · same-version HR promote · disposable `civil_id_dual_side_canary` · Aziz accepted Civil ID untouched · DocVal soft · HARD=off · no native scanner |
| Channel | Backend flags + employee mobile OTA + HR web dual preview |
| Smokes | `smoke-test-onboarding-civil-id-dual-side.py` PASS |
| Stamp / evidence | `ops/evidence/civil-id-dual-side-20260806T014717Z/` · `ops/CIVIL_ID_DUAL_SIDE.md` |
| Owner review | After live disposable-canary prove; do not enable real Civil ID replacement demand until soak |

### Residual update
- Pre-GA residual #2 (Proper Civil ID front-and-back) → **in progress / behind flags** (prove on disposable canary first)

---

## 20260806T004945Z — Kuwait onboarding wave CLOSE + DocVal canary cleanup (DONE)

| Field | Value |
|---|---|
| Scope | Close current Kuwait onboarding wave · stamp baseline · remove disposable `civil_id_canary_test` only · preserve real Civil ID · keep lifecycle+DocVal soft canary Aziz/Talal · HARD off · no GA · native scanner deferred · Auth Wave 2 audit/plan only |
| Channel | Backend-only cleanup + docs stamp |
| Smokes | `ops-aziz-docval-canary-item.py cleanup` · real `civil_id` accepted sha `fe98f7d9…` unchanged · flags SOFT=on HARD=off LIFECYCLE=on |
| Stamp / evidence | `ops/evidence/kuwait-onboarding-wave-close-20260806T004945Z/` · Auth plan `ops/AUTHENTICATION_WAVE2_AUDIT_AND_PLAN.md` |
| Owner review | Onboarding wave closed; Auth Wave 2 awaits approval before code |

### DocVal canary close outcomes
- Clear frame-filling Civil ID accepted (crop FP fixed)
- Random non-document rejected with correct wrong-document copy
- No raw errors
- Disposable canary item removed

### Pre-GA residuals (recorded)
1. Bank-details submission in employee app
2. Proper Civil ID front-and-back handling
3. Qualify passport / residence / work permit / employment contract / personal-photo DocVal flows
4. Controlled rollout beyond canary
5. Native document scanner — deferred until end

---

## 20260805T231332Z — DocVal Try again reopens picker (DONE — ready for owner smoke)

| Field | Value |
|---|---|
| Scope | Blocked upload Try again → new file picker · never resend rejected file · calm EN/AR preserved |
| Channel | JS-only OTA canary `0.1.0` · group `18b27224-09d0-4fcf-b6da-cd91e28c21bf` · iOS `019fd434-8846-742c-9f4d-066d8beb4359` |
| Smokes | Typecheck PASS · no same-file retry static check · Aziz canary item reset + VERIFY PASS |
| Stamp / evidence | `ops/evidence/docval-try-again-picker-ota-20260805T231332Z/` |
| Owner review | Force-close/reopen → mismatch → Try again → choose different file |

---

## 20260805T230300Z — Aziz disposable Civil ID canary item (READY FOR LIVE DOCVAL TEST)

| Field | Value |
|---|---|
| Scope | Optional `civil_id_canary_test` for Aziz only · real civil_id accepted preserved · soft-gate aliased to Civil ID · reset/cleanup scripts |
| Channel | Backend only (no OTA/native) |
| Smokes | `ops-aziz-docval-canary-item.py verify` PASS · visible `your_actions` + upload · civil_id hash unchanged |
| Stamp / evidence | `ops/evidence/aziz-docval-canary-item-*/` |
| Cleanup | `ops-aziz-docval-canary-item.py cleanup` |
| Owner review | Pull-to-refresh Onboarding; test mismatch → uncertain → reset → correct |

---

## 20260805T224917Z — Document Validation Parity mobile UX OTA (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | EN/AR mismatch + unclear correction alerts · uncertain→HR advisory · no raw 422/codes · Wave 2A preview/history/resubmit preserved |
| Channel | JS-only OTA `canary` runtime `0.1.0` · group `b6bccf66-d7a2-4b95-b5dd-73543f9faa86` · iOS update `019fd41e-4220-751f-b5d5-72f427cc48c5` |
| Smokes | Typecheck PASS · OTA published current · calm UX smoke PASS · soft allowlist Aziz+Talal · prod doc-validation smoke OK |
| Stamp / evidence | `ops/evidence/onboarding-doc-validation-parity-ota-20260805T224917Z/` |
| Rollback | `eas update:rollback b6bccf66-d7a2-4b95-b5dd-73543f9faa86` |
| Owner review | **Requested** — force-close/reopen; three upload scenarios below |

---

## 20260805T224005Z — Interaction assurance program open (P0/P1 closed)

| Field | Value |
|---|---|
| Scope | Close confirmed interaction-audit P0/P1 · retain residual register · synthetic IAX fixture env for 495 unproven · Vitest 13 drift fixes · calendar calm-error wave start · release gate fails only on confirmed P0/P1 |
| Channel | Docs + harness + dashboard test contracts; production IAX batch-0 fixture create/cleanup; no employee OTA required |
| Smokes | Release gate GO (0 confirmed P0/P1 blockers; 495 unproven tracked) · 7/7 previously red Vitest files green (44 tests) · calendar calm envelope unit check · production IAX canary 11/11 |
| Stamp / evidence | `ops/INTERACTION_ASSURANCE_PROGRAM/` · `ops/evidence/interaction-assurance-20260805T224005Z/` · audit `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/` |
| Rollback | Prior audit `deploy/ROLLBACK.sh` unchanged; IAX canary is disposable-fixture only |
| Owner review | Not required; residual 495 is a tracked assurance program, not a product latch |

---

## 20260805T220256Z — Interaction authority late closure (DONE)

| Field | Value |
|---|---|
| Scope | Onboarding upload capability gate · account-deletion capability/idempotency · notification/leave repeat locks and feedback · Documents/Settings back controls |
| Channel | JS-only OTA to internal `canary` + production backend/dashboard authority fixes; no native build required |
| Smokes | Typecheck + capability foundation GREEN · iOS export pass · Talal `/app/me` capability proof pass · production account-deletion replay reused one task · 3-role attendance read/manage probe 6/6 |
| Stamp / evidence | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/` · late deployment `20260805T220256Z` · OTA group `34a288bc-36c6-40fb-80e3-a38fe5449320` |
| Rollback | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/deploy/ROLLBACK.sh` (backend/dashboard/gateway + OTA-to-embedded) |
| Owner review | Not required; bundled into the completed major interaction-audit wave |

---

## 20260805T195406Z — Full interaction and dead-control audit (DONE)

| Field | Value |
|---|---|
| Scope | Employee app static controls · capability/deep-link gates · session refresh · self-scope reads · notification/leave/push/sign-out repeat safety |
| Channel | Production-connected WATHEFNI canary · backend/dashboard deploy · no native dependency change |
| Smokes | 1,101 source controls / 0 dead · 240 dashboard role/locale/viewport pages + 24 final targeted pages · 191 mutation probes / 0 server failures · 17/17 employee API controls pass · P0/P1 confirmed broken = 0 |
| Stamp / evidence | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/` |
| Rollback | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/deploy/ROLLBACK.sh` |
| Owner review | Not required; no new native build or employee-app UX wave |

---

## 20260805T150828Z — EMF manager resolution fix (DONE)

| Field | Value |
|---|---|
| Scope | `manager_phone` parse/resolve · unresolved non-blocking warning · exception CSV · commit manager_employee_key · preview ID/manager detail |
| Channel | Backend canary WATHEFNI |
| Smokes | Manager smoke OK · exact fixture preview OK · user batch `5f09ba60` left previewed |
| Stamp / evidence | `ops/evidence/employee-migration-foundation-manager-20260805T150828Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-emf-manager-20260805T150828Z/ROLLBACK.sh` |
| Owner review | Re-preview test file; do not confirm `5f09ba60` until Unknown Manager shows warning |

---

## 20260805T144609Z — Employee Migration Foundation P0–P2 (DONE)

| Field | Value |
|---|---|
| Scope | Roster import batch ledger · row results · exception CSV · idempotent replay · source_mappings · Wave4 manager_phone fix · create-only/no-message |
| Channel | Backend canary (`WATHEFNI`) + dashboard import UX totals/exceptions |
| Smokes | `OK employee migration foundation local smoke` on prod |
| Stamp / evidence | `ops/evidence/employee-migration-foundation-p0p2-20260805T144609Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-foundation-20260805T144609Z/ROLLBACK.sh` |
| Owner review | Not required for P0–P2; import stays create-only |

---

## 20260805T142303Z — Document Validation Parity soft-gate (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | `/app` upload classify/verify/quality/identity/expiry · soft block clear mismatches · uncertain→HR · Wave 2A untouched |
| Channel | Backend canary + mobile JS correction UX (OTA/next build) |
| Smokes | Doc-validation parity OK · Wave 2A OK · health active |
| Stamp / evidence | `ops/evidence/onboarding-doc-validation-parity-20260805T142303Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-onboarding-doc-validation-20260805T142303Z/ROLLBACK.sh` |
| Owner review | **Requested** — Civil ID / passport / contract / certs / photo on Aziz+Talal; hard-gate still off |

---

## 20260805T134124Z — HR Onboarding Web canary correction (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | HR projection + lifecycle writers · manage gates · drawer/portal menu · primary action consistency |
| Channel | Backend + dashboard web deploy |
| Smokes | `CANARY_QUAL_OK` · Wave 2A local smoke on prod · owner mutate + viewer 403 |
| Stamp / evidence | `ops/evidence/hr-onboarding-web-canary-20260805T134124Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-hr-onboarding-web-canary-20260805T134124Z/ROLLBACK.sh` |
| Owner review | **Requested** — live review Onboarding page (owner + restricted HR) |

---

## 20260805T114246Z — Wave 2A final cleanup (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | Global RTL/LTR · hide Expo headers · hide dormant optionals · rejection reason once · lifecycle states preserved |
| Backend | `onboarding_lifecycle_wave2a.py` canary deploy |
| Backup | `/opt/wathefni/backups/production-pre-onboarding-wave2a-cleanup-20260805T114246Z` |
| Smokes | `AZIZ_SMOKE_OK` · `EN_AR_API_SMOKE_OK` |
| Native build | iOS #7 internal — https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/78a25dd7-0731-4e27-95fe-f7f44b532c51 |
| Activation | phone `99338566` · code `356216` |
| Rollback | flag off · restore bak · prior IPA build 6 |
| Evidence | `ops/evidence/employee-onboarding-wave2a-cleanup-20260805T114246Z/` |
| Owner review | **Requested** — Wave 2A complete; next work continues as Wave 3+ without per-feature installs |

---

## Template (copy for next ship)

```
## YYYYMMDDTHHMMSSZ — <wave> / <short title>

| Field | Value |
|---|---|
| Scope | |
| Channel | OTA \| native build \| backend-only |
| Smokes | |
| Stamp / evidence | |
| Rollback | |
| Owner review | not yet \| requested \| passed |
```

| 2026-08-06 | DocVal decision-order | Soft canary Aziz/Talal | Non-doc message wins over capture copy; blurry+high OCR blocks; idempotent bypass after reset closed | Stamp `ops/evidence/docval-decision-order-20260806T001109Z/` · canary reset pending |

| 2026-08-06 | DocVal crop FP fix | Soft canary Aziz/Talal | crop_hot_sides demoted to weak signal; frame-fill clear ID allows; rejection audit keeps capture_quality | Stamp `ops/evidence/docval-crop-false-positive-fix-20260806T003126Z/` · canary reset pending |

## 20260806T155845Z — Phase 1A Bank ESS UI source recovery (no deploy)

- **Verdict:** `ready_to_deploy`
- **Evidence:** `ops/evidence/bank-ess-ui-source-recovery-20260806T155845Z/`
- **Recovered baseline:** `4f435beda3ee36dfebcf28afd06f58f027268f1f` (artifact-proven vs live `PostHire-6LCFY5pA`, norm-byte-identical)
- **Release tip:** `6547a25883609cbe84ca2f25bb8b2ea24afedce6` on `release/bank-ess-ui-clean-20260806T155845Z`
- **Included:** BankReviewPanel, OnboardingCompletionStrip, employee bank/completion mobile surfaces + EN/AR
- **Excluded:** Migration Sync / Leave / Shifts / soft-keep WIP (not in baseline→release diff)
- **Build/tests:** dashboard vite build PASS; posthire Vitest 162/162; mobile capability GREEN; EN/AR bank keys PASS
- **Production:** unchanged (`PostHire-6LCFY5pA` SHA `406b9dca…`, health 200)
- **Auth Wave 2:** not started

## 20260806T170025Z — Phase 1B Bank ESS UI clean deploy (live)

- **Verdict:** `deployed`
- **Evidence:** `ops/evidence/bank-ess-ui-clean-deploy-live-20260806T170025Z/`
- **Dashboard:** `PostHire-BRA7Ln_S.js` SHA `e833ce5c…` (prev `PostHire-6LCFY5pA` backed up)
- **Mobile OTA:** canary group `326e2040-6603-4c34-a6db-1022ff8095a6` runtime `0.1.0` · iOS `019fd80f-3cc8-7905-8863-2c4cefed9e4b` · Android `019fd80f-3cc8-75bd-8b6e-d7cfed86c919`
- **Smokes:** live API 21/21 · OCR asset needles PASS · EN/AR bank+completion API PASS · device force-close pull pending owner
- **Phase 2 / Auth Wave 2:** not started

## 20260806T172002Z — Bank ESS OTA crash fix (syncLayoutLocale)

- **Verdict:** `deployed` (republished; physical force-close verify pending owner — no USB device on agent)
- **Evidence:** `ops/evidence/bank-ess-ota-crash-fix-20260806T172002Z/`
- **Rolled back:** `326e2040-6603-4c34-a6db-1022ff8095a6` → republish group `cb2655a4-6451-4724-b321-0d20929aa838` (prior cf26d59)
- **Root cause:** `_layout` called `syncLayoutLocale()` but stale recovered `i18n/index.tsx` lacked it → AppErrorBoundary “fresh start”
- **Fix OTA tip:** group `85f648c9-73a0-4b14-9d8e-838913496a4d` runtime `0.1.0` · iOS `019fd81a-629a-7289-82ce-6207924ecc10` · Android `019fd81a-629a-7922-95b0-f9a502cf1c4e`
- **Ignore:** intermediate `f65e46d0…` (stale Metro cache)
- **Smokes:** iOS/Android export PASS · startup contract PASS · capability GREEN · published fingerprint PASS
- **Owner:** force-quit + reopen → launch / Bank / Onboarding
- **Phase 2 / Auth Wave 2:** not started

## 20260806T200247Z — Onboarding: one canonical state + next action per surface

- **Verdict:** `deployed` · live Aziz/Talal walkthrough GREEN (physical device pull pending owner)
- **Evidence:** `ops/evidence/onboarding-completion-reconcile-20260806T200247Z/`
  (`prove/consistency-matrix.md`, `prove/live-walkthrough.txt`,
  `prove/reconcile-authority-smoke.txt`, `deploy/backend-shipped.diff`)
- **Root cause 1 — stale bank history outranked the bank of record:**
  `reconcile_onboarding_bank_item` ordered requests by recency only, so an older
  `rejected` request beat a newer `applied` one and every HR read reverted the
  bank item. Fixed by `desired_onboarding_bank_state` authority order:
  open request → live `employee_bank_effective` → terminal history. Idempotent.
- **Root cause 2 — each surface picked its own "next" item:** the queue and the
  drawer/app/profile ran separate selection loops over different item sets.
  Replaced by `select_next_item()` in the contract (required + open, class
  priority, unblocked-then-due tiebreak).
- **Root cause 3 — `reopened` hardcoded owner `employee`:** a bank change under
  review showed queue `hr` vs drawer/app/profile `employee`. `next_action()` now
  takes the owner from `current_actor()` (the snapshot's own buckets).
- **Root cause 4 — mobile preferred a local state→copy table** over the
  contract's message, so client copy could contradict the backend owner. Server
  message now wins; the per-state string is an offline fallback only.
- **Live matrix:** T0 applied → T1 submitted → T2 returned → T3 resubmitted →
  T4 HR approved → T5 payroll approved → T6 applied. All four surfaces identical
  at every step; one Apply satisfies bank and completes onboarding; drawer
  re-reads are stable. 46/46 walkthrough checks, 15/15 authority smoke, 0 HTTP
  errors (Talal's bank `403` is the expected ineligibility).
- **Backend:** `app.py` + `onboarding_completion_contract.py` — shipped diff is
  5 hunks, all next-item/next-action (`deploy/backend-shipped.diff`).
- **Dashboard:** `PostHire-Bcu7y5zK.js` live in `/var/www/wathefni-dashboard`
  (backup `/opt/wathefni/backups/dashboard-onboarding-ux-20260806T200247Z`).
- **Mobile OTA:** canary group `b540423a-de1a-44c9-afa5-caa9504d2957` runtime
  `0.1.0` · iOS `019fd8d1-10b2-745c-a768-3be2eddac34e` · Android
  `019fd8d1-10b2-771b-a7b6-547b5d99ca79` · prior group
  `e3d3ffae-14a8-42f9-bc87-301763b0b0cd` for republish rollback.
- **Rollback:** `ops/evidence/onboarding-completion-reconcile-20260806T200247Z/ROLLBACK.sh`
- **Owner:** force-quit + reopen the app → Onboarding (bank item under Completed,
  no HR/payroll clutter) and Bank.
- **Auth Wave 2:** still blocked.

## 20260806T205803Z — Controlled broad rollout (Bank ESS + onboarding completion)

- **Verdict:** `broad_rollout_go`
- **Evidence:** `ops/evidence/bank-ess-onboarding-broad-rollout-20260806T205803Z/`
- **Pre:** Aziz synthetic payroll bank cleared (no invented IBAN — `bank_details=pending` for real submit) · Talal `/app/bank` 403 · rollback artifacts usable · prior OTA group `e3d3ffae…` intact
- **Stage 1:** 6 real + 3 synthetic bank-enabled (Aziz/Fouad/Noura/Mariam/Fahad/Dana) · Talal denied · `ELIGIBILITY_OK`
- **Stage 2:** 13 real + 3 synthetic bank-enabled · employee app 17 keys (Talal app-only) · `ELIGIBILITY_OK`
- **Smoke:** consistency `SMOKE_OK` 7/7 · authority `RECONCILE_AUTHORITY_OK` 15/15
- **Monitor:** journal errors 0 · edge 200/200/200 · reconcile idempotent · expected 403s only
- **Preserved:** Auth Wave 2 blocked · Settings/setup WIP untouched · `pending_payroll→hr` ownership
- **Rollback:** `ops/evidence/bank-ess-onboarding-broad-rollout-20260806T205803Z/ROLLBACK.sh`
- **Owner:** Aziz should submit real bank details via Bank ESS (synthetic cleared)

## 20260806T211805Z — Aziz synthetic bank ghost cleared (API)

- **Verdict:** `fixed`
- **Evidence:** `ops/evidence/aziz-synthetic-bank-clear-20260806T211805Z/`
- **Root cause:** prior cleanup superseded effective + soft-deleted profile but left `employee_bank_verified`; `/app/bank` still projected Walkthrough as verified/approved
- **Fix:** `revoked_at` on verified · current reads ignore revoked · no bank-of-record ⇒ no terminal history projected · revoke 4 synthetic verified rows (audit retained)
- **Live API:** `has_verified_bank=false` · verified/payroll/submission null · `can_submit_new=true` · next step “Add your bank details…”
- **Owner:** force-quit → Bank → empty form → submit real details (no TEST IBAN)

## 20260806T232633Z — Auth Wave 2 Phase 3: Smart Auto-Lock

- **Verdict:** `partially_proven` (OTA + unit PASS; iOS/Android natives FINISHED; physical matrix open)
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-20260806T232633Z/`
- **Scope:** background timeout · device-lock probe · Face ID/PIN unlock · Settings timeouts · EN/AR RTL · canary Aziz/Talal only
- **Policy:** default 30s · Immediate / 30s / 1m / 5m / Never · Never may be company-disabled · device-lock always locks when native probe works · never clears SecureStore/PIN · no Wave 1/OTP touch
- **OTA:** group `fda08e77-f7a1-464c-8596-00cc4e4c6461` runtime `0.1.0` · env PIN=1 BIOMETRIC=1 AUTO_LOCK=1 · prior rollback `3d4d10ca-…`
- **Native:** iOS `7b3dc831-…` build 11 · Android `92869701-…` vc 5 (vendored `modules/wathefni-screen-detector` after Expo 51 gradle fix)
- **Unit:** 39/39 `smoke-test-auth-wave2-phase3-autolock-unit.py`
- **Owner matrix:** bg&lt;30s no lock · bg≥30s Face ID/PIN · screen lock · Face ID cancel→PIN · success opens · no OTP · Bank/onboarding OK · EN/AR RTL
- **Phase 4:** not started

## 20260807T001856Z — Auth Wave 2 Phase 3 timeout fix (not proven)

- **Verdict:** `not_proven` — physical bg≥40s returned unlocked on `fda08e77-…`; fix republished
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-timeout-fix-20260807T001808Z/`
- **Root causes addressed:** unstable AppState effect deps · async-before-seal · no background timer · weak diagnostics
- **OTA:** group `6cffdfd1-a7d9-4b1e-9d9e-5bb731fc2e5f` · env PIN=1 BIOMETRIC=1 AUTO_LOCK=1 · rollback `fda08e77-…`
- **Owner retest:** force-quit/reopen → confirm Auto-lock=30s → bg≥40s must Face ID/PIN; check logs `[autolock]` for updateId + SEALED
- **Phase 4:** not started · Phase 3 not marked proven

## 20260807T002604Z — Auth Wave 2 Phase 3 false-positive lock fix

- **Verdict:** `not_proven` — every leave/return locked on prior OTA; inactive + screen-probe false positives
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-false-positive-fix-20260807T002520Z/`
- **Fix:** arm only on `background` · probe only while background · resume reasons `timeout|confirmed_device_lock|none` · cancel timers · no duplicate seal
- **OTA:** `0ac5d3b9-442e-422d-8bcc-39d0b1027346` · rollback `6cffdfd1-…`
- **Retest:** 5–15s away no prompt · ≥40s Face ID/PIN · phone lock Face ID/PIN · Control Center no false lock
- **Phase 4:** not started

## 20260807T003218Z — Auth Wave 2 Phase 3 FAILED (resume crash) + fix

- **Verdict:** `failed` on `0ac5d3b9-…` (leave → return hard crash after Face ID unlock)
- **Rollback:** republished `fda08e77-…` as live `83fe64f6-…`
- **Cause (code):** `setStatus('locked')` from background timer/probe + Face ID during AppState transition
- **Fix OTA:** `fdb4002c-d014-4cd1-aa12-0ff2f76aaa76` — resume-only seal · intent refs in background · delayed Face ID · single coordinator
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-crash-fix-20260807T003131Z/`
- **Re-prove:** 10s no lock/crash · 40s one prompt · phone lock one prompt · Control Center clean · rapid ×10 no crash
- **Phase 4:** not started

## 20260807T054506Z — Phase 5: Re-invite one-time code modal fix

- **Finding:** After HR revoke, Re-invite hit a **pending** invite (`pending_activation_invite_exists`); canceling supersede exited silently — no new invite, no code modal
- **Fix:** Re-invite auto-supersedes pending · always success notice + one-time code modal · revoke supersedes pending invites
- **Evidence:** `ops/evidence/auth-wave2-phase5-reinvite-modal-fix-20260807T054506Z/`
- **Verdict:** Phase 5 still **fully proven** · **Phase 6 not started**

## 20260807T053517Z — Auth Wave 2 Phase 5: access-reset copy (close)

- **Finding:** HR revoke showed Session expired because `hr_revoked` → generic `app_auth_failed` → `session_expired`
- **Fix:** server `app_access_revoked` · client `access_reset` copy — **Your app access was reset** / Sign in again with a new activation code. Soft failures unchanged
- **OTA:** `7f1731ad-d482-4b7a-a2fc-502fa1a987c8`
- **Prove:** unit 38/38 · live revoke→`app_access_revoked`→refresh dead→re-invite activate
- **Evidence:** `ops/evidence/auth-wave2-phase5-access-reset-copy-20260807T053517Z/`
- **Verdict:** Phase 5 **fully proven** · **Phase 6 not started**

## 20260807T045603Z — Auth Wave 2 Phase 5: Basic device security

- **Scope:** Settings Device security · Sign out this device · new-device notice once · HR App access revoke/re-invite · one-device rule preserved
- **OTA:** `4cb17ad8-2fea-4f19-954d-95a418ec265d`
- **Backend:** `GET /app/device-security` · HR `.../app-access` + revoke · activate `replaced_previous_device` + platform
- **Prove:** Phase 5 unit 31/31 · public routes 401 (not 404) · dashboard dist shipped
- **Evidence:** `ops/evidence/auth-wave2-phase5-device-security-20260807T045603Z/`
- **Owner:** device details · sign-out · HR revoke kills session · old PIN/Face ID dead · new-phone notice once · offline/5xx no revoke
- **Verdict:** **partially proven** · **Phase 6 not started**

## 20260807T042705Z — Auth Wave 2 Phase 4: Forgot PIN confirm copy

- **Scope:** Confirm before reset — title **Reset your PIN?** · body activation-code + new PIN · **Cancel** / **Continue** · clear only after Continue
- **OTA:** `1f0fcfdb-0d27-4d21-97e6-d657bc7a589b`
- **Prove:** Phase 4 unit 29/29 · tsc PASS
- **Evidence:** `ops/evidence/auth-wave2-phase4-forgot-confirm-copy-20260807T042705Z/`
- **Verdict:** copy ship · recovery path unchanged · **Phase 5 not started**

## 20260807T041404Z — Auth Wave 2 Phase 4: Simple PIN recovery

- **Scope:** Forgot PIN? · confirm → clear PIN + biometric pref + session → activation · 5-fail same path · EN/AR
- **OTA:** `af0c0998-d41b-4f68-a2a2-3fabc06537c0`
- **Prove:** Phase 4 unit 24/24 · Phase 3 unit 61/61 · tsc PASS
- **Evidence:** `ops/evidence/auth-wave2-phase4-pin-recovery-20260807T041404Z/`
- **Owner:** Forgot PIN · old PIN/Face ID dead · activate + new PIN · wrong×5 same reset · no network false reset
- **Verdict:** **partially proven** · **Phase 5 not started**

## 20260807T035603Z — Auth Wave 2 Phase 3B nav preserve (under review)

- **Finding:** Face ID unlock may have restored a different screen; code path does **not** remount AuthGate / call router — likely RN Modal vs native-stack
- **Fix:** iOS unlock host → `FullWindowOverlay` · skip privacy cover + foreground refetch while overlay up · timeout/Face ID unchanged
- **OTA:** `9a9a11be-dc9a-4e01-a1ec-f6f98bc5e2de`
- **Prove:** unit 60/60
- **Evidence:** `ops/evidence/auth-wave2-phase3b-nav-preserve-20260807T035603Z/`
- **Owner:** leave on Settings/Bank → ≥40s → Face ID (and cancel→PIN) must return to **same screen**
- **Verdict:** Phase 3B **under review** · **Phase 4 not started**

## 20260807T030944Z — Auth Wave 2 Phase 3B Face ID arm fix

- **Finding:** `68f5d59c-…` overlay after 40s OK · no crash/OTP · **PIN only** (Face ID never prompted)
- **Cause:** `attempted=true` before authenticate + no AppState retry → single attempt consumed on resume settle
- **Fix:** rising-edge reset · commit only before prompt · AppState retry · Modal `overFullScreen` + onShow fallback · Settings bio gate reason · no preference wipe on transient !usable
- **OTA:** `9aa012bf-dec5-4c54-9bf0-db525484eeca`
- **Prove:** unit 56/56
- **Evidence:** `ops/evidence/auth-wave2-phase3b-faceid-arm-fix-20260807T030944Z/`
- **Verdict:** **partially proven** — retest Face ID prompt · **Phase 4 not started**

## 20260807T025428Z — Auth Wave 2 Phase 3B: Face ID on proven overlay

- **Scope:** Reuse cold-start `UnlockWithBiometricGate` inside Modal overlay · arm after `onShow` + stable active · success dismisses overlay only · cancel/fail → PIN same overlay
- **Unchanged:** timeout logic · no remount · no Wave 1 / SecureStore session / device-lock
- **OTA:** group `68f5d59c-c243-4f50-8361-6f49d7a7c5db` · AUTO_LOCK=1 · AUTO_LOCK_BIOMETRIC=1
- **Prove:** unit 48/48
- **Evidence:** `ops/evidence/auth-wave2-phase3b-overlay-faceid-20260807T025428Z/`
- **Owner:** &lt;30s none · ≥40s overlay→Face ID · success dismiss · cancel→PIN · wrong/correct PIN · CC clean · ×25 no crash · no OTP/logout/nav reset
- **Verdict:** **partially proven** — physical pending · **Phase 4 not started**

## 20260807T024253Z — Auth Wave 2 Phase 3 overlay Modal + Settings diagnostics

- **Finding:** `b9c90b4f` physical test — &lt;30s OK · ≥30s also no PIN overlay (activation failure / likely native-stack covering absolute View; console stripped)
- **Fix:** PIN overlay hosted in RN `Modal` · Settings canary panel (update ID, marker `al-overlay-v3:1`, enabled, timeout, last away/elapsed/decision) · Face ID still off
- **OTA:** group `f6364b3b-5b9f-4ec9-8c97-3ec22f560a89` · AUTO_LOCK=1 · AUTO_LOCK_BIOMETRIC=0
- **Prove:** unit 39/39
- **Evidence:** `ops/evidence/auth-wave2-phase3-overlay-diag-20260807T024253Z/`
- **Owner:** force-quit → confirm Settings diagnostics (marker `al-overlay-v3:1`, enabled yes, timeout 30000) → 5–15s none · ≥40s PIN Modal · CC clean · ×25 no crash. Stop if crash; no Face ID; no Phase 4
- **Verdict:** **not proven** — awaiting device

## 20260807T022920Z — Auth Wave 2 Phase 3 overlay rebuild (PIN-only)

- **Verdict:** prior Phase 3 `failed` (resume crashes). Rebuilt as `needsLocalUnlock` overlay; AuthGate stays mounted
- **Disable OTA:** `3c51b707-…` (AUTO_LOCK=0)
- **PIN-only prove OTA:** `b9c90b4f-83c7-42fe-8145-d2c991324417` (AUTO_LOCK=1, BIOMETRIC overlay=0) — **physical PIN overlay did not appear** (superseded by `f6364b3b-…`)
- **Evidence:** `ops/evidence/auth-wave2-phase3-overlay-rebuild-20260807T022817Z/`
- **Owner:** force-quit → 30s setting → 5–15s no overlay · 40s PIN overlay · CC clean · rapid ×25 no crash. Stop if crash; do not enable Face ID yet
- **Phase 4:** not started
