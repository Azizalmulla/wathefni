# Three release blockers — fix stamp

**Stamp:** `20260810T185200Z`  
**OTA:** `7c52c216-8534-4e16-a141-ab177495dea5` · iOS `019fed03-d990-7cdf-8b79-8ae7f9376b79` · runtime 0.3.0 · canary  
**Backend:** prod orchestrator restarted with `app.py` + `operator_mobile_data.py` queue fixes

## Blocker results

| # | Blocker | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | Leave Confirm silent failure | **PASS (fix + HTTP)** · **owner Confirm smoke remaining** | Sheet moved outside ScrollView; inline `confirmError`; missing pending throws visible error; post-success refresh non-blocking. HTTP prepare→confirm approve+reject completed. No USB/sim on build host — owner must pull OTA and tap Confirm on seeded Fouad leaves. |
| 2 | Onboarding queue reachability | **PASS** | Canonical `list_onboarding_hr_actionable_page` SQL; queue total **2** (includes W2B-SYNTH visual); Home/Inbox priorities total **2**. |
| 3 | Document Reviews queue truth | **PASS** | `renewal_status` selected; `pending_hr_review`→`needs_review`; stored-valid without renewal not re-queued. Mobile needs_review **12**; HTTP mark reviewed from queue **200 completed**; priorities aligned. |

## Owner physical checklist (Leave Confirm only)

1. Force-quit HR app → reopen → wait for OTA `7c52c216-…`
2. Home/Inbox → Fouad annual (seeded, tag `hr-blocker-fix-owner`) → Approve → **Confirm** must succeed (success state, not silent)
3. Fouad sick → Reject with reason → **Confirm** must succeed
4. Onboarding queue → open W2B-SYNTH → Accept/Waive → back to Home counts refresh
5. Documents queue → Mark reviewed → back to Home counts refresh
6. Spot EN/AR on confirm error + sheet labels

## Frozen UX

Leave cream/SOD preserved; onboarding Accept/Waive/bank handoff unchanged; documents mark-reviewed + expected_status unchanged. No Face ID/auth work started.
