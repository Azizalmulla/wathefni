# Shifts Wave 5B — production synthetic publish, open-shift & coverage canary

**Stamp:** `20260803T005831Z`  
**Evidence:** `ops/evidence/shifts-wave5b-20260803T005831Z/`  
**Staging gate:** `ops/evidence/shifts-wave5-20260803T004110Z` (**GO**)  
**Module:** `shifts_publish_wave5.py` **v5.0.0** · cleanup contract **1.2.0**  
**Prior attempt:** `ops/evidence/shifts-wave5b-20260803T005415Z` (**NO-GO** — W4B `cleanup_contract_1_1` vs 1.2.0; dashboard build skipped → Publish tab asset missing)

## Scope
Production WATHEFNI synthetic-only canary for draft → review → approve → publish, open shifts, and coverage.  
Markers: **SHW5B** / **965535***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**. Integrity jobs **0**. CAPTURE_INGEST **off**.

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 5 (publish/open/coverage) | **GO** |
| Controlled real draft creation | **NO-GO** |
| Controlled real publishing | **NO-GO** |
| Controlled real open shifts | **NO-GO** |
| HR/manager production scheduling | **NO-GO** (allowlists empty) |
| Wave 6 readiness | **NO-GO** (rotations/remote hitches/PAM not built) |
| Broad employee-app access | **NO-GO** |

## Gate result
`PROD_SYNTHETIC_WAVE5_PUBLISH_GO`

---

## Production SHAs and flags

### SHAs (preflight → after redeploy #2)
| Path | SHA |
|---|---|
| `app.py` | `53b6e4553a5f95ab156e24ecce82b66569fcc0924b5f9a442516c9c2ff9f40c6` |
| `shifts_publish_wave5.py` | `d6172b85d6aa071813018df60d85a4a1dc3520bb188419ee102b4563b43db336` |
| `shifts_templates_wave4.py` | `2ff2e89d3be656069297253e9c7e8bb3c10dd2a74268487fef6c3878a811997f` |
| `shifts_synthetic_cleanup.py` | `aee228f34711b434ad81ab0a86480690108845f1db641a9f72344361846cef03` |

Full preflight/verify dumps: `remote/preflight/before-deploy.txt`, `remote/verify/after-deploy.txt`.

### Active Wave 5 drop-in (`remote/flags/shifts-wave5b-synthetic.conf`)
- `WATHEFNI_SHIFTS_WAVE5=1` · companies `WATHEFNI` · `SYNTHETIC_ONLY=1`
- Markers `SHW5B,SHW5B-SYNTH|` · phones `965535`
- `WATHEFNI_SHIFTS_HR_ALLOWLIST=` · `WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=`
- `WATHEFNI_SHIFTS_REAL_MUTATION_GATE=1` · `WATHEFNI_SHIFTS_REAL_REMINDERS=0`
- `WATHEFNI_SHIFTS_INTEGRITY_JOBS=0` · `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off`
- Wave 1–4 marker lists include SHW5B coexistence phones/markers

### Schema
`shift_schedule_periods`, `shift_schedule_versions`, `shift_schedule_draft_rows`, `shift_open_shifts`, `shift_open_shift_claims`, `shift_coverage_rules`  
L0 columns: `schedule_period_id`, `schedule_version_id`, `schedule_source`

---

## Backup and rollback

| Item | Evidence |
|---|---|
| Backup path | `/opt/wathefni/backups/production-pre-shifts-wave5b-20260803T005831Z` (`rollback/backup/BACKUP_PATH.txt`) |
| Rollback script | `rollback/backup/ROLLBACK.sh` |
| Rollback exercise | **YES** — `tests/rollback.out` → `ROLLBACK_OK` |
| Redeploy after rollback | `tests/deploy2.out` → `DEPLOY_SHIFTS_W5B_OK` + `DASHBOARD_DIST_DEPLOYED` |
| Dashboard build | **YES** — `ui/dashboard-build-status.txt` → `DASHBOARD_BUILD_OK` |
| UI probe | **YES** — `publish_tab_asset True` (`PostHire-DHjOpc8q.js`), `UI_PROBE_OK` |

---

## Test counts (before / after redeploy)

| Suite | Canary #1 (deploy1) | Canary #2 (after rollback+redeploy) |
|---|---|---|
| Wave 5B prod canary | **83 passed, 0 failed** (tag `CA4D3A84`) | **83 passed, 0 failed** (tag `479454D0`) |
| Wave 4B coexist | — | **75 passed, 0 failed** |
| Wave 3B / 2B / 1B | — | 31 / 108 / 57 passed, 0 failed |
| Wave 1 / 2 / 3 UX smokes | — | 90 / 82 / 43 passed, 0 failed |
| Freezes (E360/ONB/ATT/LEAVE) | local preflight green | all rc=0 |

Artifacts: `tests/canary1.out`, `tests/canary2.out`, `tests/coexistence.out`, `remote/canary/{canary1,canary2}/`.

---

## Synthetic IDs (canary #2 — post-redeploy proof)

| Kind | ID |
|---|---|
| Period | `fabb8edf-46ed-43e9-b1e9-a75b21638d48` |
| Versions | `0ff52dd3-f955-424e-8612-33f60771b136`, `14a0cc7b-61d7-4731-8cab-8e98e99cf11f` |
| Day / night templates | `1cf9e6c4-0479-4466-9de3-d2bdbabfb672`, `e1ec5406-cca2-4208-be7d-13da2cfa8e56` |
| Weekly recurrence (Wave 4 → draft) | `ddce0680-8b02-40a6-9822-58bdc64dbdf6` |
| Open shifts | `70a1202d-…`, `f740843c-…`, `b5b93931-…`, `610997b4-…` |
| Coverage rules | `SHW5B Warn 479454D0`, `SHW5B Block 479454D0`, `SHW5B OvernightCov 479454D0` |
| Employees | `WATHEFNI-SHW5B-479454D0`, `WATHEFNI-SHW5B-B-479454D0` |

Canary #1 IDs (pre-rollback): period `e7997812-ee6e-45b7-9545-f4e3517acd41`, tag `CA4D3A84` — see `remote/canary/canary1/ids.json`.

---

## Publish / rollback evidence (synthetic)

Proven on both canaries (`remote/canary/*/results.json`):

- Draft from Wave 4 recurrence → `draft_rows_gt_0` · **`L0_unchanged_after_draft`**
- Review: `transition_in_review` → `return_to_draft_with_note` → approve
- Coverage **warn** allows publish; **block** prevents publish (`publish_blocked_by_coverage`)
- `publish_ok` · `published_L0_provenance` · `republish_idempotent`
- Concurrent publish: `concurrent_publish_lock_held` · `concurrent_worker_finished`
- Edit via new draft/version: `create_draft_from_published` · `publish_second_version`
- Audited rollback: `rollback_to_version`
- Overnight template / open shift / coverage overnight windows
- Optional period: `optional_require_publish_period` · `manual_L0_optional_period` (`require_publish=false`)
- Wave 4 honesty remains `publishing: false` (`w4_honesty_publishing_false`)

---

## Open-shift race evidence

- Dual claims: `claim_by_A` · `claim_by_B`
- One winner: `approve_A_wins` · `second_approve_B_rejected`
- `self_approval_denied`
- Direct HR assign: `direct_assign_open_shift`
- Overnight open shift created and exercised
- Real open-shift fingerprints unchanged after cleanup

---

## Coverage evidence

- Classes exercised: understaffed warning, unresolved open shift, overnight coverage
- Modes: warn (`warn_blocks_publish_false`) · block (`block_blocks_publish_true` → publish blocked)
- Snapshot tied to published version path in publish success after block rule cleared/adjusted in flow
- No monetary calculations (honesty + module gates)
- Real coverage fingerprints unchanged

---

## Cleanup and fingerprint proof

| Check | Result |
|---|---|
| Real assignment fps unchanged (canary#2) | **PASS** — 73 real assignments; before≡after |
| Real open-shift / coverage fps | **PASS** |
| Events count | **103** unchanged |
| Cleanup contract | **1.2.0** |
| Residual after cleanup | **total 0** across periods, versions, drafts, opens, claims, coverage, L0 synth rows (`residual-final.json`) |
| SHW2 seasonal hygiene | run in deploy preflight before coexistence |

---

## Remaining blockers (intentional)

1. Real HR/manager allowlists remain **empty** — no controlled real draft, publish, or open-shift claims.
2. Real reminders / integrity jobs / CAPTURE_INGEST remain **off**.
3. Rotations, remote hitches, PAM export, Payroll money, broad employee-app access — **not built / not enabled** (Wave 6+).
4. Wave 4 honesty still reports `publishing: false` by design (Wave 5 owns publish honesty).

---

## Coexistence / regressions

- Wave 1B · 2B · 3B · 4B: **YES**
- Wave 1 / 2 / 3 UX smokes: **YES**
- Frozen modules (E360 / ONB / ATT / LEAVE): **YES**
- Details: `tests/coexistence.out`

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · Draft/publish/open/coverage true for Wave 5 · Rotations/PAM false · Wave 4 honesty still publishing false.

## Fixes applied between NO-GO attempt and this GO
1. `canary-prod-shifts-wave4b.py`: accept cleanup contract **1.2.x** (was hard-coded `startswith("1.1")`).
2. Removed unused `AlertTriangle` import so dashboard `npm run build` succeeds and Publish & coverage assets deploy.
3. Qualify gates now require `DASHBOARD_BUILD_OK` + `publish_tab_asset True`.
