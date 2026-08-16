# Employee App P1 — Phase 3: Surface refinement

Stamp: `20260808T073000Z` · branch `authority-cutover`
Deployed `app.py` matches local (see `source-stamp.txt`).
Backup: `/opt/wathefni/backups/employee-app-p1-phase3-20260808T073000Z`

**Verdict: PASS** (internal wave step — not frozen; Phase 4 still owns Inbox/Settings completion polish + physical visual QA)

Owner review is **not** requested. Home/Schedule remain frozen.

## Per-surface changes

### Profile — PASS
- `/app/profile` now returns structured `personal` + `employment` over the same employee row `/app/me` uses (no second store).
- Employment includes start date when stored, and manager only when a manager phone is already on the employee profile (resolved to a roster name when present).
- Mobile Profile reads `/app/profile`; hierarchy is Personal → Employment → Bank → Account.
- Documents/Payslips shortcuts removed from Profile (owning destinations remain).
- Bank stays under Profile only.

### Documents — PASS
- Hierarchy: Needs attention → Current → History.
- Current file IDs are excluded from History (no unexplained duplicates).
- Upload/renew, HR review copy, legitimacy note, secure open/cancel, onboarding + Home invalidation preserved.
- OCR/extraction authority untouched.

### Payslips — PASS
- One unified list/detail experience for native + external released payslips.
- Period labeling, net-pay prominence, earnings/deductions grouping, source-neutral honesty, PDF share + cache cleanup preserved.
- No payment date invented.

### Inbox — PASS (presentation)
- Unread / earlier sections, VoiceOver labels, Phase 1 `openableHref` gating unchanged.
- Unknown/disabled destinations still alert calmly (`home.linkUnavailable`).
- Server EN/AR title/body handling unchanged; no workflow authority invented.

### Settings / security — PASS (presentation)
- Bank removed from Settings (Profile owns it).
- Device-security retry affordance added.
- Auth Wave 2 Phases 0–5 behavior preserved; production diagnostics remain build-gated.
- Auth Phase 6 not started.

### Global honesty / EN+AR+RTL / a11y baseline — PASS (touched surfaces)
- Profile error vs empty distinguished; Documents partial compliance noted without false empty facts.
- EN/AR key parity maintained.
- RTL direction shells, chevrons, and 44pt touch targets on refined controls.
- VoiceOver labels on Profile rows, Inbox cards, Payslip rows, Documents actions.

## Gates

| Host | Result |
|---|---|
| Local | 13 passed / 0 failed (DB classes skipped) — `local-gates.txt` |
| Production | 13 passed / 0 failed (mobile toolchain skipped) — `prod-gates.txt` |

Includes new: documents hierarchy (7), profile projection contract, Phase 0–2 regressions (home, workday, runtime access, payslips P0/P0.1).

Side fix: payslips P0 `create_period` collision now uses a savepoint so a unique-period miss no longer aborts the transaction (`ops/smoke-test-employee-payslips-p0.py`).

## Remaining functional / Phase 4 items

- Inbox: push taps still open Inbox rather than the deep-link target (safe; optional follow-through in Phase 4).
- Settings: further density/copy polish if needed after device review.
- Global FeatureUnavailable reason surfacing from `features[x].reason` still generic.
- Full Dynamic Type / VoiceOver / reduced-motion physical qualification.
- Physical visual QA on iPhone (EN+AR, RTL, Profile/Documents/Payslips/Inbox/Settings).
- OTA canary to Aziz/Talal for live device review of Phase 3 JS.

## Frozen foundations untouched

Auth Wave 2 · Payroll Authority / Payslip Wave 3 release rules · Bank ESS layers · Documents legitimacy (HR review ≠ government) · Home `/app/home` · Schedule `/app/workday` · Migration & Sync · Setup Console entitlements.

## Rollback

`ROLLBACK.sh` restores prior `app.py` from the Phase 3 backup. No schema migration. Mobile is JS-only (OTA revert).
