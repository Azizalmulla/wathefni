# Setup Console Phase 4 — Roles, Permissions & Integrations UX

**Status:** PASS (canary qualified) · **Frozen**  
**Depends on:** Setup Console Phases 1–3B (frozen)  
**Do not auto-start:** Adaptive Employee App · Employee App P1 · HR App · Auth Wave 2 Phase 6

## Verdict

**PASS** — canary live smoke **34/0**

Evidence: `ops/evidence/setup-console-phase4-20260808T033934Z`  
Canary: `/opt/wathefni/ops/evidence/setup-console-phase4-20260808T033934Z`

Smoke: `wathefni-orchestrator/smoke-test-setup-console-phase4.py`  
Evidence pattern: `ops/evidence/setup-console-phase4-*`

## Product answers

| Question | Surface |
|---|---|
| Who administers this company? | Setup **Team & access** + Settings → Team |
| What can they manage? | Human access summaries from role presets |
| What external systems are connected? | Setup **Integrations** catalog |

## Roles / Permissions ownership map

| Concern | Owner | Canonical authority |
|---|---|---|
| First Company Admin seed | **Setup Console** (`#classic-owner`) | `POST .../setup/companies/{c}/owner` → `dashboard_users` + invites |
| Day-to-day invite / role / status | **Settings → Team** (single writer) | `POST/PATCH /dashboard/team*` |
| Role presets | Platform (`ROLE_PERMISSIONS` / `ROLE_LABELS`) | Not UI-editable matrices |
| Grant-only extras | Ops/CLI audited path | `dashboard_user_permission_grants` |
| Setup team view | Setup `#classic-team-access` | Read summary only |
| Last-owner protection | Team PATCH API | `last_owner_protected` |
| Privilege escalation | Team invite/update + grant CLI | Target role/permission ⊆ actor |

## Integrations ownership map

| Concern | Owner | Notes |
|---|---|---|
| Integrations catalog | **Setup Console** `#classic-integrations` | Status + Configure / Manage sync links |
| Connected Systems sync ops | **Migration & Sync** | Runs, exceptions, mappings, history |
| Company messaging / channel policy | **Setup** `#classic-channels` | No provider secrets stored |
| Personal HR WhatsApp | **Settings → Account** | Not merged with company channel |
| Calendar OAuth (Google / M365) | **Settings → Integrations** | Sealed credentials |
| Recruitment mailbox | **Settings → Communications** | Sealed credentials |
| Email admin (outbound) | Setup Control | Already present |
| Secrets | Canonical sealed stores | Never returned to browser |

## Retired / clarified duplicate writers

| Item | Decision |
|---|---|
| Setup full invite workflow | Not duplicated — Manage team deep link |
| Setup connector admin / SFTP forms | Not duplicated — Migration & Sync |
| Control raw `provider_key` list | Softened to friendly labels + catalog deep link |
| IMAP / SMS / api_stub as products | Not advertised |

## Safety

- Last active Company Admin cannot be demoted/disabled
- Role assignment cannot exceed actor’s effective permissions
- Grant CLI cannot grant a permission the actor does not hold
- Disable user revokes sessions; does not delete audit/history
- Module entitlement still gates APIs independently of role presets

## Gaps

- Arabic role labels still mirror English `ROLE_LABELS` (access summaries are localized)
- SFTP credential form still thin in Migration UI (API real; Setup does not fork it)
- Custom roles (`tc_tenant_roles`) remain deferred
- Grant-only permission matrix remains ops/CLI (by design)

## API

- `GET .../setup/companies/{code}/team-access`
- `GET .../setup/companies/{code}/integrations-catalog`
