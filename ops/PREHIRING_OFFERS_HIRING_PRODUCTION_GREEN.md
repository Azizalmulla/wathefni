# Pre-Hiring Offers and Hiring — Production Green / Frozen

**Status:** production-green · **Offers/Hiring frozen**  
**Promoted artifact:** exact staging-green Offers/Hiring only  
**Artifact SHA:** `71dd4d10d51605968436885c5867a79ace73452e33849d64441ef23801f0ebf5`  
**Source:** staging tree at green pin (surgical promote)  
**Next:** wait for owner instruction — **do not begin another module**

---

## Verdict

Guarded production promotion of the Offers/Hiring staging-green artifact is **green**. Compensation redaction, expiry/stale-link privacy, durable send/resend, public XSS/CSP, one accepted offer, sole canonical hire authority, append-only versions/events, Arabic/English documents, hire-override confirmation/outcome, atomic hire, GCC/Kuwait metadata, frozen-module regressions, public-route guard, and zero synthetic residue all passed. **Stop.**

---

## Promoted identifiers

| Item | Value |
|---|---|
| Staging-green artifact SHA | `71dd4d10d51605968436885c5867a79ace73452e33849d64441ef23801f0ebf5` |
| Staging evidence | `ops/PREHIRING_OFFERS_HIRING_STAGING_GREEN.md` |
| Production pin file | `/opt/wathefni/production/offers-hiring-production-green.json` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator.service` · `127.0.0.1:8010` · health 200 |
| Database | `wathefni` · marker `wathefni-production-isolation-v1` |
| Dashboard | `/var/www/wathefni-dashboard` (from staging-green dist) |
| Delivery during quals | process-local `WATHEFNI_DELIVERY_MODE=dry_run` only |
| Service delivery pin | **unset** (not globally dry_run) |
| Explicit backup | `/opt/wathefni/backups/pre-offers-hiring-prod-20260724T230002Z` |
| DB dump sha256 | `d6227d8fc1e07ebe2b4404a6388b0754dcc5b474a39b47e645a433274b911592` |
| Daily backup | `/opt/wathefni/backups/daily/20260724T230007Z` |
| Matrix evidence | `ops/offers/offers-hiring-production-matrix-20260724T230202Z.json` |
| Owner search markers | **`OFFERPRO`** / **`OFFERPISO`** |

### Rollback command

```bash
snap=/opt/wathefni/backups/pre-offers-hiring-prod-20260724T230002Z
bash "$snap/ROLLBACK.sh"
# Or manually:
# tar -xzf "$snap/orchestrator.tgz" -C /opt/wathefni/orchestrator
# restore dashboard from "$snap/dashboard-public.tgz"
# systemctl disable --now wathefni-offer-lifecycle.timer 2>/dev/null || true
# rm -f /etc/systemd/system/wathefni-offer-lifecycle.service /etc/systemd/system/wathefni-offer-lifecycle.timer
# rm -f /etc/systemd/system/wathefni-orchestrator.service.d/offer-token.conf
# systemctl daemon-reload
# systemctl restart wathefni-orchestrator.service; systemctl reload caddy
# DB restore ONLY if required (destructive):
#   set -a; . /root/.openclaw/secrets/postgres.env; set +a
#   pg_restore --clean --if-exists -d "$DATABASE_URL" "$snap/wathefni.dump"
```

---

## Artifact identity

- Recomputed local/staging artifact SHA == `71dd4d10…`
- `/opt/wathefni/staging/last-green.sha256` == same
- Promote copied staging fingerprints exactly for Offers/Hiring remediation files
- Unrelated dirty worktree files were **not** deployed

### Per-file SHA256 (production == staging-green)

| File | SHA256 |
|---|---|
| `offer_lifecycle.py` | `6f817e23eeee14f39f035af6be382040a1e829688067dfacebcd8eebea9380c7` |
| `offer_service.py` | `a4f691dec596e2d688e17148be9a86c4f492d2c70a7cf8954884556d47ff5053` |
| `offer_routes.py` | `7f673cb0e336efff3d270ab79761115aed1bb2b09694e0aba9c5bd0e9867896f` |
| `offer-lifecycle-worker.py` | `bc27ac10d192eebd08c6ba3a284408f8ef06299f800f2b26971ccfc08ead46de` |
| `action_registry.py` | `75274646eb81a304ebaf9e8325c9cd462359d55abe3024fc0dd939bf3557b774` |
| `app.py` | `bd1c94eeb43e976e181ed63426dd6ca5558d310b360ba0946370834118f6ac8b` |

---

## Preflight (before deploy)

Read-only production scan:

| Check | Result |
|---|---|
| Duplicate `accepted` offers | **none** (0 groups) |
| Any existing offer rows | **none** (empty table) |
| Invalid statuses | **none** |
| Conflicting historical accepted agreements | **none — proceed** |

No genuine offer records were modified. No auto-withdraw was required or performed.

---

## Schema / config delta

| Change | Kind |
|---|---|
| Governance columns on `employment_offers` (country, legal entity, language, template id/version/approval, policy version, signatory, effective date) | additive via `ensure_schema` |
| Status `CHECK` for canonical offer statuses | additive |
| `employment_offers_accepted_app_uq` | additive unique partial index |
| Append-only triggers on versions/events | additive |
| `employment_offer_delivery_operations` | new durable send/resend table |
| `WATHEFNI_OFFER_TOKEN_SECRET` via production EnvironmentFile | staging-pattern secret; rotated once after deploy verification |
| `wathefni-offer-lifecycle.timer` | enabled (expiry worker) |
| Global `WATHEFNI_DELIVERY_MODE=dry_run` on production service | **not set** |

---

## Exact deployed fingerprints (pre → post)

| Path | Pre-promote | Post-promote (= staging-green) |
|---|---|---|
| `offer_lifecycle.py` | `efae44a8…` | `6f817e23…` |
| `offer_service.py` | `9686a108…` | `a4f691de…` |
| `offer_routes.py` | `914c5975…` | `7f673cb0…` |
| `offer-lifecycle-worker.py` | absent | `bc27ac10…` |
| `action_registry.py` | `04c58c9f…` | `75274646…` |
| `app.py` | `ba3f4a4a…` | `bd1c94ee…` |
| Dashboard public | prior | staging-green dist (`dashboard-Bsvmidao.js` et al.) |

Public routes: API JSON 401/404 (not SPA HTML); `/dashboard` shell has `#root`.

---

## Pass / fail matrix

| Gate | Result | Evidence |
|---|---|---|
| Artifact identity | **PASS** | `71dd4d10…` |
| Production backup verified | **PASS** | dump 5.7MB · tarballs readable · `ROLLBACK.sh` |
| Preflight no duplicate accepted | **PASS** | 0 conflicting groups |
| Schema constraints applied | **PASS** | accepted uq + delivery ops + append-only triggers |
| Public-route guard | **PASS** | auth/me, summary JSON; SPA `#root` |
| Offers/Hiring production matrix | **38/38 PASS** | `OFFERPRO`/`OFFERPISO` |
| Offer lifecycle smoke | **PASS** | |
| Offer hire-override smoke | **PASS** | |
| Candidates C3 production | **49/49 PASS** | |
| Ranking R0–R3 production | **55/55 PASS** | |
| Ranking presentation production | **219/219 PASS** | |
| Reports V1 production | **80/80 PASS** | |
| Assistant A0–A3 production | **79/79 PASS** | |
| Assessments ON/OFF production | **39/39 PASS** | |
| Interviews production | **45/45 PASS** | |
| Production health / binding | **PASS** | `/health` ok · env match |
| Offer expiry timer | **active** | |
| Delivery mode not globally dry_run | **PASS** | unset on service |
| Cleanup zero synthetic residue | **PASS** | all OFFERPRO/OFFERPISO counts 0 |

---

## Privacy / expiry / send / resend proof

- Compensation and PDF denied without `offer.compensation.read`; redacted bundles hide salary/terms/wording/document.
- Concurrent identical idempotency key → one provider call, one durable send operation, one delivery.
- Known provider failure retries the same operation; unknown post-provider DB outcome → `manual_review` with no automatic second send.
- Resend revokes prior tokens; stale/expired links do not disclose compensation.
- Raw response tokens are never persisted; API responses omit `raw_token`.
- Public `/offer/{token}` escapes dynamic HTML and sets restrictive CSP (`default-src 'none'`, `form-action 'self'`).

## Hire atomicity proof

- Accepted-offer gate allows hire without override; minted confirmation → atomic hire → application `hired`, exactly one employee, hire operation `completed`.
- Hire replay creates no second employee.
- Override requires explicit confirm + reason + grant; audit pending → completed with operation id and employee key.
- Source authority: no legacy direct hire bypass; Ranking/Assessments/Interviews remain isolated from offer mutation.

## Arabic / GCC proof

- Generated Arabic path rejected until confirmed uploaded PDF is attached.
- Uploaded Arabic PDF bytes retained (SHA `9fdee9d5…`).
- Draft persistence includes `KW`, production-fixture legal entity, `KWD`, `en`/`ar` language, template id/version `KW-OFFER-PRODUCTION` / `2026.7`, policy version, signatory, configuration effective date.

## Cleanup proof

Post-matrix residue for `OFFERPRO` / `OFFERPISO`:

| Entity | Count |
|---|---|
| offers / events / tokens / send ops | 0 |
| hire ops / employees / applications / companies | 0 |
| PDF files removed | 5 |

---

## Residuals

1. Ranking R0–R3 production matrix reports **55** gates (staging reported 57); both fully green with zero failures — matrix variant difference only.
2. Broader Kuwait/GCC country-pack employee/onboarding copy of offer governance fields remains deferred (documented in local remediation).
3. No supersede operation — second accept remains rejected by design.
4. Offer token secret was rotated once after deploy verification; production EnvironmentFile is configured (value not recorded here).

---

## Production health

- `wathefni-orchestrator.service`: **active**
- `http://127.0.0.1:8010/health`: **ok** / environment binding match
- `wathefni-offer-lifecycle.timer`: **active**
- Public edge routing: **PASS**
- Synthetic markers cleaned: **PASS**

---

## Final status

1. Offers/Hiring is **production-green**.
2. Offers/Hiring is **frozen**.
3. **Stop.**
4. **Do not begin another module** until the owner explicitly requests one.
