# Pre-Hiring Assessments — Production Green / Frozen

**Status:** production-green · **Assessments module-boundary + optionality remediation frozen**  
**Promoted artifact:** exact staging-green Assessments only  
**Artifact SHA:** `240416fe3d1abfb48beff9a10f0f1a7eff8868dd0d5af83d75aaaf2e1f83190d`  
**Source tree:** `/tmp/wathefni-c3-local`  
**Next:** wait for owner instruction — **do not begin Interviews or another module**

---

## Verdict

Guarded production promotion of the Assessments staging-green artifact is **green**. Tenant ON/OFF, Ranking independence, module-off invisibility, EN/AR Begin flow, delivery-state truthfulness, frozen-module regressions, public-route guard, and zero-residue cleanup all passed. Documented residuals were **not** implemented. **Stop.**

---

## Promoted identifiers

| Item | Value |
|---|---|
| Staging-green artifact SHA | `240416fe3d1abfb48beff9a10f0f1a7eff8868dd0d5af83d75aaaf2e1f83190d` |
| Staging evidence | `ops/PREHIRING_ASSESSMENTS_STAGING_GREEN.md` · ON/OFF `…20260724T020012Z.json` |
| Production pin file | `/opt/wathefni/production/assessments-production-green.json` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator.service` · `127.0.0.1:8010` · health 200 |
| Database | `wathefni` · marker `wathefni-production-isolation-v1` |
| Dashboard | `/var/www/wathefni-dashboard` |
| Delivery during quals | process-local `WATHEFNI_DELIVERY_MODE=dry_run` only |
| Service delivery pin | **unset** (Luna/outbound unchanged; not globally dry_run) |
| AI authoring | `WATHEFNI_ASSESSMENT_AUTHORING=false` |
| Explicit DB backup | `/opt/wathefni/backups/pre-assessments-prod-20260724T093940Z` |
| DB dump sha256 | `c9403c3de63f52434d1ad9987289d04fc22e8033c8a46fa0524b16fc719d063b` |
| Deploy snapshot | `/opt/wathefni/backups/predeploy-20260724T094221Z` |
| Daily backup stamp | `/opt/wathefni/backups/daily/20260724T094211Z` (`db.dump` sha `26900b1f…`) |
| ON/OFF evidence | `/opt/wathefni/orchestrator/ops/assessments/assessments-on-off-production-matrix-20260724T095051Z.json` |
| Owner search markers | **`ASSESONP`** / **`ASSESSOFFP`** |

### Rollback command (tested path)

```bash
# Preferred: restore the Assessments pre-promote snapshot
snap=/opt/wathefni/backups/pre-assessments-prod-20260724T093940Z
# Or: bash ops/deploy.sh rollback  (uses /opt/wathefni/backups/.last-predeploy → predeploy-20260724T094221Z)
# Or: bash ops/ROLLBACK_ASSESSMENTS_PRODUCTION.sh "$snap"

tar -xzf "$snap/orchestrator.tgz" -C /opt/wathefni/orchestrator
rm -rf /var/www/wathefni-dashboard.rb
mkdir -p /var/www/wathefni-dashboard.rb
tar -xzf "$snap/dashboard-public.tgz" -C /var/www/wathefni-dashboard.rb
rsync -a --delete /var/www/wathefni-dashboard.rb/ /var/www/wathefni-dashboard/
rm -rf /var/www/wathefni-dashboard.rb
systemctl restart wathefni-orchestrator.service
sleep 3
systemctl reload caddy
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health

# DB restore ONLY if required (destructive):
#   set -a; . /root/.openclaw/secrets/postgres.env; set +a
#   pg_restore --clean --if-exists -d "$WATHEFNI_DATABASE_URL" "$snap/wathefni.dump"
```

---

## Schema / config proof

| Change | Kind |
|---|---|
| `assessment_attempts.delivery_status` CHECK includes `send_accepted` / `intentionally_skipped` | additive (`NOT VALID` widen) — matches staging |
| `WATHEFNI_ASSESSMENT_AUTHORING=false` | preserved |
| No global `WATHEFNI_DELIVERY_MODE=dry_run` on production service | preserved |
| Assistant / Ranking retrieval pins | unchanged |
| Product-2 live authoring | **not** enabled |

---

## Exact deployed fingerprints (pre → post)

| Path | Pre-promote | Post-promote (= staging) |
|---|---|---|
| `app.py` | `52fe37c3…037e9` | `30d8fd13…147cb5` |
| `prehire_overview.py` | `7e7a7e32…435819` | `9a99959c…74c8380` |
| `candidate_ranking.py` | `f288c917…57c4f9` | `9b8a54f1…efd8c8` |
| `ranking_result_presentation.py` | `0c8297a8…902c2bbe` | `8d2f3c9f…953be64b` |
| `assessment_lifecycle.py` | `2e2f9bff…c99c2e3` | `d531133b…842ec7b` |
| `assessment_service.py` | `75343310…e54644` | **SAME** |
| `reports_v1.py` | `15e3f9ca…e25692` | `d7f52f2a…c147a41` |
| `module_catalog.py` | (pre) | `74e09aa5…cc0a9b4` |

Staging `app.py` == production `app.py` after promote.

---

## Pass / fail matrix

| Gate | Result | Evidence |
|---|---|---|
| Artifact SHA == staging-green | **PASS** | `240416fe…83190d` |
| `ops/deploy.sh production` + public-route guard | **PASS** | deploy log; edge JSON 401/404; SPA `#root` |
| Assessments ON/OFF production (`ASSESONP`/`ASSESSOFFP`) | **39/39 PASS** | `…production-matrix-20260724T095051Z.json` |
| Assessments cleanup1 | **29/29 PASS** (staging-only harness by design) | reconfirmed on staging; refuses production DB |
| Candidates C3 production | **49/49 PASS** | `ops/reports/candidates-c3-production-matrix.json` |
| Ranking R0–R3 production | **55/55 PASS** | `ranking-r0r3-production-matrix-20260724T094833Z.json` |
| Ranking presentation production | **219/219 PASS** | hash pin updated to promoted `candidate_ranking` |
| Reports V1 production | **80/80 PASS** | matrix JSON |
| Assistant A0–A3 production | **79/79 PASS** | `assistant-a0a3-production-matrix.json` |
| Tenant read hardening | **PASS** | smoke |
| Toolcall orchestrator | **PASS** | smoke |
| Prehire overview unit | **PASS** | smoke |
| Dashboard test/build (preflight) | **70 tests PASS** + build | deploy preflight |
| Prod health / bind | **PASS** | production binding match |
| Service not globally dry_run | **PASS** | `DELIVERY_MODE` unset on service |
| Synthetic cleanup zero residue | **PASS** | ON/OFF `cleanup_zero_residue` |

### Assessments production proofs (synthetic only)

| Proof | Result |
|---|---|
| Module-on: assigned pending; unassigned no attempt | PASS |
| Terminal send fail-closed | PASS |
| Link open does not start; Begin starts once; Begin idempotent | PASS |
| Arabic locale + `dir=rtl` on dedicated attempt | PASS |
| Default Ranking unused without approved selection | PASS |
| Module-off: overview/Reports/Ranking/mobile/Assistant/public fail closed | PASS |
| Historical attempts/scores/reports preserved after disable | PASS |
| Cross-tenant token blocked | PASS |
| `sent`/`send_accepted` labels = “Send accepted” (not delivered) | PASS |
| Dry-run send → `intentionally_skipped` | PASS |
| Full marker cleanup | PASS |

---

## Documented residuals (not implemented)

| Residual | Classification |
|---|---|
| Legacy WhatsApp reminder still writes `delivery_status='sent'` | documented; never treated as delivery proof |
| No invitation-recovery worker | documented |
| Background expiry sweep | documented; durable expiry on access still enforced |
| Application assessment projection non-authoritative | documented |

---

## Frozen boundary

Do **not** reopen or redesign:

- Jobs Phase 1–2 · Candidates C0–C3 · Ranking R0–R3 · Ranking presentation · Reports V1 · Assistant A0–A3  
- Deterministic assessment scoring/runtime core  
- Production AI authoring kill switch  

Assessments module-boundary + optionality remediation is **frozen** at this production-green pin.

**Stop. Do not begin Interviews or another module.**
