# Postmark Staging Isolation — Ownership & Rotation

## Ownership
- Staging Postmark server token: `/root/.openclaw/secrets/wathefni-postmark.staging.env`
- Staging inbound webhook secret: `/root/.openclaw/secrets/wathefni-intake.staging.env` (`WATHEFNI_POSTMARK_INBOUND_SECRET`)
- Postmark Account token (server create/edit only): `/root/.openclaw/secrets/wathefni-postmark-account.staging.env` (mode 0600, root-only)
- Production Postmark server token: `/root/.openclaw/secrets/postgres.env` only

## Separation rules
- Never store production server token in staging secret files.
- Never PUT/PATCH Postmark server ID `19430066` (production) from staging scripts.
- Staging webhook URL must use `/webhook/postmark-staging/...` → `:8011` only.
- Production webhook URL must remain `/webhook/postmark/inbound` → `:8010`.

## Rotation
1. Generate new staging inbound webhook secret; update `wathefni-intake.staging.env`; restart `wathefni-orchestrator-staging.service`.
2. Update staging Postmark server `InboundHookUrl` query token / basic auth to match (staging server only).
3. Rotate staging server API token in Postmark UI; update `wathefni-postmark.staging.env`.
4. Rotate Account token in Postmark Account → API Tokens; update `wathefni-postmark-account.staging.env`.
5. Do not rotate production tokens as part of staging maintenance.

## Least privilege
- Day-to-day staging ops: Server Token for the staging server only.
- Account Token: create/edit servers and inbound domains only; not used by the orchestrator runtime.
