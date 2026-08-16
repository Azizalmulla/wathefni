# Employee App P1 — Phase 4: Final Functional Qualification

Stamp: `20260808T074820Z` · branch `authority-cutover` · base commit `cf26d59` (working tree dirty with Phases 0–4 + unrelated WIP)

**Verdict: PASS**

`FUNCTIONAL_READY_FOR_PHYSICAL_VISUAL_QA = YES`

Employee App is **not frozen**. Visual redesign, HR App, and Auth Wave 2 Phase 6 were **not** started.
Owner visual judgment belongs to the next dedicated Physical Visual QA phase.

## What shipped

### 1. Push / deep-link follow-through — PASS
- Mobile `resolvePushDestination` extracts `deep_link` / `path` / `payslip_id` / flow defaults.
- Follow-through always goes through Phase 1 `openableHref` registry + current entitlements.
- Unknown / external / malformed / unentitled → calm Inbox, then Home.
- Tap handling runs whenever signed in (independent of push-registration flag).
- Does **not** bypass LocalUnlockShell / auth.
- Backend `build_employee_push_data` enriches Expo push `data` with flow-default path hints (still client-authoritative).

### 2. FeatureUnavailable reason copy — PASS
- Reads canonical `me.features[x].reason` only (no frontend entitlement invention).
- Customer i18n for module-disabled / no-access / temporarily-unavailable.
- Raw backend enums never shown.

### 3. Global state honesty — PASS (static + prior Phase 0–3 discipline)
- Loading / error / empty / partial authority patterns preserved on Home, Schedule, module screens.
- Network/read failures continue to use ErrorState / `home.dataUnavailable` — not business empty facts.
- Session refresh contract re-proven statically (foreground, unlock, PTR, feature-disabled → refreshMe).

### 4. EN / AR / RTL — PASS (static/contract)
- Full EN/AR key parity.
- Feature unavailable + surface prefixes scanned.
- Inbox still presents server title/body (HR free text not fake-translated).

### 5. Accessibility (code-level) — PASS
- Labels, 44pt targets on refined controls, reduced-motion wiring, header roles.
- **Physical VoiceOver / Dynamic Type / reduced-motion judgment deferred** to Physical Visual QA.

### 6. OTA canary (Aziz/Talal only) — PASS
| Field | Value |
|---|---|
| Branch | `canary` |
| Runtime | `0.1.0` |
| Update group | `f9fc3c25-f535-40e0-b273-ef3214da93c2` |
| iOS update ID | `019fe05a-a586-7410-8198-b0b9f79b6167` |
| Android update ID | `019fe05a-a586-714c-aa34-38fc5c0b0151` |
| Rollback group | `905477b6-1db1-4b6b-b0c8-bcc72bb32c3a` (prior canary: Payslips P0.1) |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/f9fc3c25-f535-40e0-b273-ef3214da93c2 |
| Installed update ID | Verifiable on device after force-quit → reopen (Settings diagnostics when build-gated) |

### 7. Regression gates — PASS (combined hosts)
| Host | Result |
|---|---|
| Local | 16 passed / 0 failed / 10 DB skips (`ALLOW_DB_SKIP=1`) — `local-gates.txt` |
| Production | 13 passed / 0 failed / 13 mobile-toolchain skips — `prod-gates.txt` |

Includes: typecheck · composition · push follow-through · feature-unavailable copy · session-refresh static · capability foundation · Auth Wave 2 phases 0–5 units · runtime access · home · workday · profile · documents hierarchy · payslips P0+P0.1 · Bank ESS contracts (via capability) · Inbox/deep links · HR sync · tenant/self-scope.

### 8. Remaining functional defects
None blocking functional readiness. Device-only items deferred:
- Physical push-tap with a live payload (registration currently off in production env; follow-through wired for when data is present / cold-start response).
- Physical VoiceOver / Dynamic Type / large-text overflow.
- Visual density / polish (explicitly out of scope for Phase 4).

## Frozen foundations untouched
Auth Wave 2 (0–5) · Payroll Authority / Payslip Wave 3 · Bank ESS layers · Documents legitimacy · Home `/app/home` · Schedule `/app/workday` · Migration & Sync · Setup Console entitlements · no Auth Phase 6.

## Next phase
**Employee App Physical Visual QA & Responsiveness** — owner review on the real iPhone using `PHYSICAL_QA_CHECKLIST.md`. Do not freeze yet. Do not start visual redesign automatically.
