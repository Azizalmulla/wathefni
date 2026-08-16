# Wave D6A — Production deploy (durable → Held materialization repair)

**Stamp:** `20260801T165754Z`  
**Mode:** Production deploy of local-qualified D6A only  
**Local qualifier:** `ops/evidence/waveD-phase6a-held-materialization-20260801T164408Z/` (PASS)  
**Host:** `root@76.13.63.68`  
**Remote evidence:** `/opt/wathefni/production-evidence/waveD-phase6a-held/20260801T165754Z`  
**Backup / rollback:** `/opt/wathefni/backups/production-pre-waveD-phase6a-held-20260801T165754Z`

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Health orch + dashboard 200 | **PASS** |
| Short valid CV → accepted Held | **PASS** (3×3 shorts) |
| Opaque / OCR-failed → Held identity-review + terminal | **PASS** (×3) |
| Conflict → separate checksum-scoped warned Held | **PASS** (×3) |
| Message-ID duplicates idempotent | **PASS** |
| No silent identity completion without Held / auditable block | **PASS** |
| Tenant isolation (allowlist WATHEFNI; unknown recipient ignored) | **PASS** |
| Mailbox sync off | **PASS** |
| Quarantine / ClamAV clean path exercised | **PASS** |
| Explicit admit unchanged (no auto-admit on held-review) | **PASS** |
| Synthetic materialization gate ×3 | **PASS** |
| Cleanup (proof intakes disabled; 1 continuous active) | **PASS** |
| Rollback verified + D6A restored | **PASS** |
| External tenants / post-hiring | **Not enabled / not started** |
| `cv_extraction` promotion | **Deferred to D6B** (not fixed) |

---

## Production SHAs (final)

| Artifact | SHA-256 |
|---|---|
| `orchestrator/app.py` | `661dd600f83d97f5b78cd88928f1edf1ed549c5d4700e8c601db621650863070` |
| `orchestrator/durable_email_ingress.py` | `5807b200bd1f22e3e4d6512be485b73595b1e4b5c89915e14dc2d0177fa59a16` |

Pre-deploy (rollback target):

| Artifact | SHA-256 |
|---|---|
| `app.py` | `e4c2001736e18dc5e9352d45e44e519f61a242df660c0ee36d78ed391ff8a032` |
| `durable_email_ingress.py` | `48701edb8cffffd07d15348594ff0f60c37876595b8a3c57c9268e8160e1bada` |

Source: `verify/sha-final.txt`, `verify/sha-before.txt`, `rollback/`

---

## Kept canary posture (live)

- `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`
- `WATHEFNI_MAILBOX_SYNC=off`
- Continuous active intake left: Postmark default `2493b577-09e3-45c2-b923-b0c382c251df` only  
  (`cleanup/final-intakes.txt`)

---

## Timing results (prod gate ×3)

Worker drain (timer paused during gate for determinism; restored after):  
`intake_validation` → `file_safety_scan` → `cv_identity_resolution` → `accepted_intake_preparation` → `held_intake_materialization`

Representative (gate 1):

| Path | Result | Notes |
|---|---|---|
| Short CV | accepted Held | identity ~96–655 ms; accepted prepare ~69–308 ms |
| Opaque | held_identity_review | `held_intake_materialization` processed=1 (~53 ms); terminal `low_quality_text`; warned=true |
| Conflict | separate app_key | warned=true; outcome=`conflict` |
| Duplicate Message-ID | idempotent | asserted every short run |

Full matrix: `verify/prod-d6a-timing-summary.json`  
Gate JSON: `verify/prod-d6a-gate-run{1,2,3}.json`  
Post-rollback restore re-gate: `verify/prod-d6a-gate-post-restore.json` (**PASS**)

---

## Rollback verification

1. Executed `rollback/ROLLBACK.sh` → restored pre-D6A SHAs; D6A symbols absent  
2. Orch briefly unreachable during cutover (`rollback_orch=000`); dashboard stayed 200  
3. Re-deployed D6A files; orch/dash **200**; post-restore gate **PASS**

---

## D6B (next — not fixed here)

Canonical **`cv_extraction` promotion** after Held still fails in the broader inbound-email smoke and leaves pending `cv_extraction` jobs on prod (**32** at deploy close).

Recorded in `assess/D6B-NEXT.md`. **No cv_extraction fix in this deployment.**

---

## Evidence path

Local: `ops/evidence/waveD-phase6a-held-materialization-deploy-20260801T165754Z/`  
Remote: `/opt/wathefni/production-evidence/waveD-phase6a-held/20260801T165754Z/`
