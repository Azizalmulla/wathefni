# Pre-Hiring Interviews — Production Green / Frozen

**Status:** production-green · **Interviews remediation frozen**  
**Promoted artifact:** exact staging-green Interviews only  
**Artifact SHA:** `c434d4b2076ccf22e4808b3f8739d48ba9b11f22ee05628915e8026e5f902cb9`  
**Source:** staging tree at green pin (surgical promote)  
**Next:** wait for owner instruction — **do not begin Offers/Hiring**

---

## Verdict

Guarded production promotion of the Interviews staging-green artifact is **green**. Live Google create → reschedule → cancel, Wathefni-only scheduling, conflicts, feedback, async-video reclaim/purge, Ranking isolation, frozen-module regressions, public-route guard, and zero synthetic residue all passed. **Stop.**

---

## Promoted identifiers

| Item | Value |
|---|---|
| Staging-green artifact SHA | `c434d4b2076ccf22e4808b3f8739d48ba9b11f22ee05628915e8026e5f902cb9` |
| Staging evidence | `ops/PREHIRING_INTERVIEWS_STAGING_GREEN.md` |
| Production pin file | `/opt/wathefni/production/interviews-production-green.json` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator.service` · `127.0.0.1:8010` · health 200 |
| Database | `wathefni` · marker `wathefni-production-isolation-v1` |
| Dashboard | `/var/www/wathefni-dashboard` (from staging-green dist) |
| Delivery during quals | process-local `WATHEFNI_DELIVERY_MODE=dry_run` only |
| Service delivery pin | **unset** (not globally dry_run) |
| Google account | `azizalmulla16@gmail.com` |
| Explicit backup | `/opt/wathefni/backups/pre-interviews-prod-20260724T213117Z` |
| DB dump sha256 | `efa33920f85f2de0e699dc6f438830c5f8efb2fdb626fe8147ae677029a1281a` |
| Daily backup | `/opt/wathefni/backups/daily/20260724T213117Z` (`db.dump` sha `6cd1dcc1…`) |
| Live soak evidence | `ops/interviews/interviews-live-gcal-soak-20260724T213219Z.json` |
| Matrix evidence | `ops/interviews/interviews-production-matrix-20260724T213237Z.json` |
| Owner search markers | **`INTVLIVEP`** / **`INTVVIDP`** / **`INTVGCALP`** |

### Rollback command

```bash
snap=/opt/wathefni/backups/pre-interviews-prod-20260724T213117Z
bash "$snap/ROLLBACK.sh"
# Or manually:
# tar -xzf "$snap/orchestrator.tgz" -C /opt/wathefni/orchestrator
# restore dashboard from "$snap/dashboard-public.tgz"
# systemctl restart wathefni-orchestrator.service; systemctl reload caddy
# DB restore ONLY if required (destructive):
#   set -a; . /root/.openclaw/secrets/postgres.env; set +a
#   pg_restore --clean --if-exists -d "$DATABASE_URL" "$snap/wathefni.dump"
```

---

## Artifact identity

- Recomputed staging artifact SHA == `c434d4b2…`
- `/opt/wathefni/staging/last-green.sha256` == same
- Promote copied staging fingerprints exactly for Interviews delta files

---

## Schema / config delta

| Change | Kind |
|---|---|
| Interview lifecycle/service tables & columns (assignments, schedule ops, feedback versions, retention ops, provider sync fields, etc.) | additive via `ensure_schema` / `ensure_interview_schema` |
| Optional Google via `gog` / `GOG_ACCOUNT` | unchanged ops config |
| `_google_update` omits `--with-meet`; `_google_delete` uses `--force` | CLI compatibility with gog v0.12.0 |
| No global `WATHEFNI_DELIVERY_MODE=dry_run` on production service | preserved |
| Ranking / Reports / Assistant / Assessments pins | unchanged |

---

## Exact deployed fingerprints (pre → post)

| Path | Pre-promote | Post-promote (= staging) |
|---|---|---|
| `interview_service.py` | **absent** | `8f10e8f7…0b01b6` |
| `interview_lifecycle.py` | **absent** | `09a6a91b…beab3784` |
| `app.py` | `30d8fd13…147cb5` | `ba3f4a4a…92a6ef` |
| `action_registry.py` | `da56619c…a4d2c0` | `04c58c9f…fbce2631` |
| `tool_call_orchestrator.py` | `82cc7fc0…8f2a48` | `a968142a…06fbff52` |
| `candidate_ranking.py` | unchanged | **SAME** |
| `reports_v1.py` | unchanged | **SAME** |

Dashboard published from staging-green dist. Public routes: JSON 401/404 (not SPA HTML); `/dashboard` shell has `#root`.

---

## Pass / fail matrix

| Gate | Result | Evidence |
|---|---|---|
| Artifact identity | **PASS** | `c434d4b2…` |
| Production backup verified | **PASS** | dump 5.2MB · tgz readable · `ROLLBACK.sh` |
| Public-route guard | **PASS** | auth/me, summary, interviews JSON; SPA `#root` |
| Live GCal soak (`INTVGCALP`) | **19/19 PASS** | create/reschedule same event / cancel cancelled / zero residue |
| Interviews production matrix | **45/45 PASS** | phone/physical/manual/Google, conflicts, feedback, async video, Ranking unused |
| Focused gcal CLI unit | **5/5 PASS** | |
| Candidates C3 production | **49/49 PASS** | |
| Ranking R0–R3 production | **55/55 PASS** | |
| Ranking presentation production | **219/219 PASS** | |
| Reports V1 production | **80/80 PASS** | |
| Assistant A0–A3 production | **79/79 PASS** | |
| Assessments ON/OFF production | **39/39 PASS** | |
| Service not globally dry_run | **PASS** | |
| Synthetic cleanup zero residue | **PASS** | `INTVLIVEP`/`INTVVIDP`/`INTVGCALP` + `+9658841*` = 0 |

### Interviews production proofs (synthetic only)

| Proof | Result |
|---|---|
| Schedule without Google (phone) | PASS |
| Physical / manual-link | PASS |
| Google-connected create one event | PASS |
| Duplicate / concurrent → one interview | PASS |
| Candidate + panel conflicts fail closed | PASS |
| Reschedule updates same Google event | PASS |
| Cancel removes/cancels Google event | PASS |
| No stale Meet/event | PASS |
| Feedback versioning + immutable finalize | PASS |
| Video/AI do not complete human feedback | PASS |
| No interview score in Ranking | PASS (`interview=unused`) |
| Stale transcription reclaim + retention purge | PASS |
| Delivery / RSVP / sync states distinct | PASS |
| Arabic/RTL + a11y copy in dashboard | PASS |
| Assistant schedule/cancel/reschedule confirmation | PASS |
| Tenant isolation on panel filter | PASS |

---

## Freeze

Interviews is **production-green and frozen**.

Do **not**:
- reopen Interviews scope without a new assessment
- begin Offers or Hiring work
- change Ranking / Reports / Assistant / Assessments frozen contracts as part of this promote
