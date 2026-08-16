# Employees 360 Wave 7 — Production qualification & controlled rollout readiness

**Stamp:** `20260801T232347Z`  
**Evidence:** `ops/evidence/employees360-wave7-prod-qual-20260801T232347Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave7-prod-qual/20260801T232347Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave7-20260801T232347Z/`  
**Company:** WATHEFNI only

**Boundary honored:** Wave 6 UI deployed to production · Wave 3/4/5 safety flags preserved · real lifecycle remains `SYNTHETIC_ONLY=on` · real ESS remains `ESS_V5_SYNTHETIC_ONLY=on` · `WATHEFNI_EMPLOYEE_APP=off` · four reals untouched · no broad real-employee onboarding · no synthetic-gate lift · pre-hire / Wave D frozen.

---

## Overall verdict

### Employees 360 production readiness: **PASS (qualified / controlled)**

Wave 6 UX is live on production with thin read APIs, synthetic end-to-end canary **33/33**, backup/rollback ready, and all Wave 3–5 authority gates still fail-closed for real users.

**Not a green light for broad real-user onboarding.** Real employee-app, real ESS, and real lifecycle remain **NO-GO** until classification, gate lifts, and an explicit controlled plan.

---

## Separate GO / NO-GO verdicts

| Track | Verdict | Notes / blocker |
|---|---|---|
| **HR production use** | **GO** (controlled) | Directory, profile surfaces, Workforce hub (org / lifecycle queue / remediation read / migration / requests) live under owner auth. Mutations still hit Wave 3–5 APIs; approve ≠ apply; remediation read-only. Real lifecycle execution stays synthetic-only. |
| **Manager production use** | **GO** (controlled) | Manager-scoped ESS paths proven fail-closed when out of scope; transfer apply via Wave 4 on synthetic only. No broad manager real-report ESS until synthetic-only lifts. |
| **Controlled real employee-app rollout** | **NO-GO** | `WATHEFNI_EMPLOYEE_APP=off` · `ESS_V5_SYNTHETIC_ONLY=on` · four reals still unclassified in remediation · no employee-app onboarding executed. |
| **Normal real lifecycle operations** | **NO-GO** | `LIFECYCLE_V3_SYNTHETIC_ONLY=on` · reals lack jurisdiction pack fields · remediation UI explicitly blocks lifecycle execution. |
| **Exceptional / high-risk lifecycle cases** | **NO-GO** | Counsel / high-risk paths not opened for reals; synthetic-only + classification dual-control still required. |

---

## Production SHAs (after)

| Artifact | SHA256 |
|---|---|
| `app.py` | `915467b126f42203d16b07c98c1407258b76e99c9add984585a22f5541a7752e` |
| `employee_org_wave4.py` | `8c7a00567596299945dc60502ca3aa0fbb332e2f18186f4ec919fa46382acccf` |
| `employee_selfservice_wave5.py` | `942a440a404284cbac0bd7e3193db205150e878ee63a35ab87d135b2157fc7ca` |
| `PostHire-S7v-8p_F.js` | `a42a8689c00449a366aa9d5a83d5a9b1eb869642fb858458a1bdcf079fb2f135` |
| `dashboard-Dxz4Ghhp.js` | `1a5fb63464f3f075fb72b13053e7931b07976fe825263c9b7441f8aa08011146` |

Artifacts: `preflight/after-deploy.txt`, `verify/final-prod-state.txt`, `verify/ui-markers.txt`.

---

## Flags (live — preserved)

```
WATHEFNI_EMPLOYEE_ESS_V5=on
WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES=WATHEFNI
WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY=on
WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_PHONE_PREFIXES=965549
WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_NAME_PREFIX=W5C-SYNTH|

WATHEFNI_EMPLOYEE_ORG_V4=on (+ ACTIVATE_DUE=on)
WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on + SYNTHETIC_ONLY=on (965522 / W3D-SYNTH|)
WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on
WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
WATHEFNI_EMPLOYEE_APP=off
```

`safety_flags_preserved=true` (`verify/safety-flags.txt`).  
Lifecycle timer: **enabled/active**.

---

## Deployed surface

1. **Wave 6 dashboard dist** → `/var/www/wathefni-dashboard/` (Workforce nav + Employees 360 sections).
2. **Thin production APIs** (already required for hub):
   - `GET /dashboard/posthire/employee-lifecycle/remediation` — **PRESENT**
   - `GET|POST /dashboard/posthire/employee-org/migration-batches` — present
3. No real lifecycle / real ESS gate changes.

---

## Backup + rollback

- Backup: `/opt/wathefni/backups/production-pre-employees360-wave7-20260801T232347Z/`
- Includes pre-deploy orchestrator files, dashboard dist, `ROLLBACK.sh`
- Validated: syntax OK, executable, restores app + dashboard (`verify/rollback-tested.txt`, `verify/rollback-proof.txt`)
- Full rollback **not executed** post-GO (would remove live Wave 6 UI)

---

## Staging remediation 10 vs production 4

| Env | Count | Interpretation |
|---|---|---|
| Staging (Wave 6) | 10 | Staging residue / synthetic mix |
| Production | **12 open** = **4 reals** (unclassified) + **8** quarantined synthetic | Environment data only |

`logic_mismatch=false` — same remediation read path; different queued rows (`verify/remediation-env-diff.txt`). UI shows OPEN **12** with four real keys visible and dual-control / no lifecycle execution copy.

---

## Synthetic E2E canary (production)

**Script:** `tests/canary-prod-wave7-qual.py`  
**Result:** **33 passed, 0 failed** (`canary/canary-rc.txt` = `0`)  
**Tag:** `8e201f5d`  
**IDs (cleaned):** `WATHEFNI-96554919853/54/55`  
**Allowlist used for canary run:** phones `965549*`, names `W7-SYNTH|` (live drop-in remains `W5C-SYNTH|`)

Proved:

| Area | Result |
|---|---|
| Org units + migration batches list | PASS |
| Assignment history + future-effective + `activate_due` | PASS |
| Identity bind + session live + revoke | PASS |
| Personal apply; bank HR→payroll; approve ≠ apply; apply + idempotent; mask default | PASS |
| ESS transfer apply via Wave 4 | PASS |
| Stale overlay → `needs_review` | PASS |
| Self-approval / cross-tenant / real ESS / manager-scope deny | PASS |
| ESS reconcile | PASS |
| Four reals untouched | PASS |
| Synthetic cleanup zero | PASS |

---

## Production UI qualification

Against `https://api.wathefni.ai/dashboard/` with short-lived owner session.

| Check | Result |
|---|---|
| Employees directory (EN desktop/mobile) | PASS |
| Workforce Organization / Lifecycle / Remediation / Migration / Requests | PASS |
| AR desktop + mobile RTL (`main[dir=rtl]`) | PASS |
| Deep link `?page=workforce&workforce=remediation` + browser refresh | PASS |
| Light a11y (main/nav/h1 present) | PASS |
| Perf (median ~4.1s cold load incl. wait; max ~7.7s AR mobile) | ACCEPTABLE for qual pack |
| Employee `?employee=` deep-link auto-click | SKIPPED (no `data-employee-key` in DOM); directory + workforce refresh covered |

Screenshots: `screenshots/{en,ar}-{desktop,mobile}/` · probes: `screenshots/prod-ui-probes.json`.

Authority copy visible in UI: “authority stays on Waves 3–5”; remediation “Read-only… No lifecycle execution.”

---

## Final production state

- Synthetic employees remaining: **0**
- Synthetic ESS requests remaining: **0**
- Four reals still `active`; `updated_at` unchanged by canary (pre-existing timestamps)
- Employee app remains **off**

---

## Remaining blockers (before real-user tracks)

1. Classify / remediate the four real employees (dual-control) — still open in remediation.
2. Explicit plan to lift `ESS_V5_SYNTHETIC_ONLY` for a named allowlist only (not broad).
3. Explicit plan to lift `LIFECYCLE_V3_SYNTHETIC_ONLY` for normal real lifecycle (separate from exceptional counsel paths).
4. Turn on `WATHEFNI_EMPLOYEE_APP` only after identity binding + session revoke proofs on real devices.
5. Clear or archive leftover quarantined synthetic remediation rows (8) when ops ready — does not block HR UI GO.
6. Optional: add stable `data-employee-key` for profile deep-link automation.

---

## Explicit non-goals (honored)

- No broad real-employee onboarding  
- No disable of synthetic-only gates  
- No normal / exceptional real lifecycle enablement  
- No pre-hire or Wave D changes  

---

## Evidence index

| Path | Content |
|---|---|
| `ops/deploy-wave7-prod-qual.sh` | Deploy |
| `tests/canary-prod-wave7-qual.py` | Synthetic canary |
| `canary/canary-run.log` / `canary-evidence.json` | 33/33 |
| `preflight/after-deploy.txt` | SHAs + flags + routes |
| `verify/remediation-env-diff.txt` | 10 vs 4/12 explained |
| `verify/final-prod-state.txt` | Reals + cleanup |
| `screenshots/` | EN/AR desktop/mobile + probes |
| `capture-prod.mjs` | UI harness |
