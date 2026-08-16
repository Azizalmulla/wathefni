# Analytics Wave 1-B — production synthetic Attention Contract

**Stamp:** `20260803T160118Z`  
**Evidence:** `ops/evidence/analytics-wave1b-prod-canary-20260803T160118Z/`  
**Staging prerequisite:** `ops/evidence/analytics-wave1-20260803T155142Z` (`STAGING_ANALYTICS_WAVE1_ATTENTION_GO`)  
**Freeze doc:** `ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Analytics Wave 1 Attention Contract | **GO** |
| Freeze Analytics Wave 1 | **GO** |
| Analytics Wave 2 | **NO-GO** (not started) |
| AI / Compliance metrics / payroll money analytics | **NO-GO** |

## Proof

| Check | Result |
|---|---|
| Canary before rollback | **49/0**, residual **0** |
| Rollback | **ROLLBACK_VERIFIED** (drop-in cleared) |
| Redeploy + canary | **49/0**, residual **0** |
| Analytics freeze regression | **34/0** |
| Sibling freezes | E360 57 · Onboarding 54 · Attendance 22 · Leave 34 · Shifts 96 — all **0 failed** |
| SYNTHETIC_ONLY | enforced (`WATHEFNI_ANALYTICS_WAVE1_SYNTHETIC_ONLY=1`) |
| UI EN/AR + mobile web | Attention copy present · Headcount gone · responsive grid OK |

## Flags

`WATHEFNI_ANALYTICS_WAVE1=1` · `SYNTHETIC_ONLY=1` · markers `ANW1` · phones `965540*` · company `WATHEFNI`

## Residual

Canary-tagged ACK rows cleaned to **0**. Durable migrate ACK retained for audit.

## Rollback

`/opt/wathefni/backups/production-pre-analytics-wave1b-*` + `ROLLBACK.sh`
