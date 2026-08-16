# Staging channel canary — Luna qualification follow-up

**Status:** partial pass — live WhatsApp delivery blocked  
**Luna commit:** `a15fe3c72b0d401d73317049b4de9fccf457e594`  
**Artifact:** `f2d54ffde8cec2af3dae4f9a62f15a8e8a5c31ca2fe2ecba93c93679f492f25b`  
**Model / prompt / schema:** unchanged (`gpt-5.6-luna` / `candidate_intent_prompt_v1` / `candidate_intent_v1`)

## Process reload proof

OpenClaw gateway (`openclaw-gateway.service`, user unit) was restarted with a temporary drop-in:

`WATHEFNI_HR_ORCHESTRATOR_URL=http://127.0.0.1:8011/orchestrator/whatsapp-turn`

Then restored to default (no env override → production orchestrator URL default). Extension on disk contains provider-message-ID forwarding + fail-closed gates. Drop-in removed after canary.

## Canary authorization

- Recipient: Aziz Almulla (WATHEFNI staging owner/admin)
- Phone redacted: `965****8566`
- Phone SHA-256: `492c7b867e94619fab58426d4c938b86f06983f8c4d6ded0fd29bb16e854c437`
- Battery: `wathefni_ability_v1`
- Locale: `en`
- Expiry: 2 days

## Results

| Check | Result |
| --- | --- |
| OpenClaw reload to staging + restore | pass |
| Extension forwarding / fail-closed present | pass |
| Synthetic application + assessment attempt | pass |
| Secure link opens staging attempt (HTTP 200) | pass |
| Company / battery / expiry bound on attempt | pass |
| Inbound provider_message_id durable ledger (1 row) | pass |
| Replay same inbound ID (duplicate, no new mutation) | pass |
| Stage / employee / external-tenant unchanged | pass |
| Synthetic cleanup to zero | pass |
| Authoring off / production untouched | pass |
| Live WhatsApp invitation delivery | **blocked** |

## Remaining blocker

No active Octopus WhatsApp conversation for the authorized recipient. Probed conversation IDs (`1594`, `1606`, `1555`, …) all return `Invalid conversation_id provided`.

**Exact next step:** authorized recipient sends one WhatsApp message to the Wathefni business number to open a live conversation, then rerun the live invitation canary.

## Production recommendation

**NO-GO.** Do not promote. Staging channel plumbing is verified except live outbound delivery, which needs an active conversation.
