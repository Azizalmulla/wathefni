# Legacy AI Recruiter prototype — exposure quarantine

**Status (HR-0):** Quarantined. Prefer retirement when no production dependency exists.

## What this is / is not

| This directory | Wathefni product |
| --- | --- |
| Standalone FastAPI prototype under `ai-recruiter/` | **Not** the in-product AI Recruiter |
| WhatsApp hiring experiment | Dashboard Assistant / orchestrator prehire flows |
| Unauthenticated `/internal/*` historically | Must never power Wathefni HR |

## Exposure evidence (before HR-0)

- `docker-compose.yml` published `8000:8000` (all interfaces) and Postgres `5432:5432`.
- `Dockerfile` ran uvicorn with `--host 0.0.0.0`.
- `app/routers/internal.py` had **no authentication** on company/HR/employee CRUD.
- Wathefni orchestrator systemd units under `wathefni-orchestrator/ops/` do **not** reference this service (no evidence it is part of Wathefni staging/production deploy).
- Local probe (2026-07-14): nothing listening on `:8000` / `:8001` in the developer workspace.

## Remediation (after HR-0)

- `/internal/*` is **not mounted** unless `LEGACY_AI_RECRUITER_INTERNAL_ENABLED=1`.
- When enabled, every `/internal` route requires `LEGACY_AI_RECRUITER_INTERNAL_TOKEN` via `Authorization: Bearer` or `X-Internal-Token`.
- Docker ports bind to `127.0.0.1` only.
- Uvicorn binds `127.0.0.1`.
- Disabled `/internal` paths return `404 legacy_internal_disabled`.

## Policy

- Do **not** reuse this auth model or these endpoints for Wathefni HR.
- Do **not** alter Wathefni dashboard AI Recruiter flows from this tree.
- Prefer full retirement once product confirms no active dependency.
