# Candidate WhatsApp GPT-5.6 Luna Semantic Router (Staging)

**Status:** staging complete — stop before production / live canary  
**Generated:** 2026-07-19T20:13:35Z  
**Model ID:** `gpt-5.6-luna`  
**Prompt version:** `candidate_intent_prompt_v1`  
**Schema version:** `candidate_intent_v1`  
**Catalog version:** `candidate_flow_v1`  
**Confidence gate:** `0.80`

## Architecture

1. Deterministic first: APPLY codes, attachments/media, pending withdrawal confirmations, secure tokens, screening answers (bound to company/conversation/application).
2. GPT-5.6 Luna only after deterministic routing does not resolve natural-language messages.
3. Strict structured JSON schema (`candidate_intent_v1`).
4. Backend validation remains authoritative; model never mutates lifecycle directly.
5. Below 0.80 confidence (or unknown / multi-intent conflict) → short clarification + durable clarification state.
6. Telemetry: prompt/schema version, confidence, tokens, estimated cost, latency via `llm_call_logs` metadata.

## Evaluation (200 balanced messages)

| Metric | Result | Target |
| --- | --- | --- |
| Overall intent accuracy | **92.5%** | ≥90% |
| EN | 92.0% | ≥85% |
| MSA | 96.0% | ≥85% |
| Gulf | 92.0% | ≥85% |
| Arabizi/mixed | **90.0%** | ≥80% |
| Entity extraction (apply code/role) | **100%** | ≥95% |
| False mutation attempts | **0** | 0 |
| Ambiguous/adversarial safe | **100%** | 100% |

### Latency / tokens / cost (192 Luna calls)

- p50 latency: **1398 ms** (avg 1543, p95 2716, max 3981)
- Tokens: 98,499 in / 19,309 out
- Estimated cost: **$0.214** total (~$0.00112 / call)

### Failed examples (primary cluster)

Bare confirm/cancel tokens without pending withdrawal context (`CONFIRM`, `تأكيد`, `CANCEL`, `keep it`, …) were classified as unknown/clarification. In production these are handled by the **deterministic pending-confirmation path** before Luna; Luna correctly refuses to guess without pending state.

## Provider message-ID / dedupe

`PROVIDER_DEDUPE_PROOF.json`: **pass**

- Top-level `provider_message_id` / `wamid` forwarding: pass
- Nested `provider_payload.messages[0].id` fallback: pass
- Concurrent single claim: pass
- Missing ID → dedupe unavailable: pass
- Generic-agent fallback bypass: **no bypass** (authoritative empty reply returns; missing ID returns; orchestrator null fail-closed)

## Remaining blockers (pre-production)

1. Authorized staging link canary for assessment/interview/offer secure links (not run).
2. Confirm/cancel NL accuracy outside pending context remains weak by design; keep deterministic pending gate.
3. OpenClaw process reload on staging may be required if the channel extension is cached in a long-lived Node process (file deployed to `/root/.openclaw/extensions/octopus-channel.ts`).
4. No Terra fallback (intentionally omitted).
5. Production remaining OFF until explicit go/no-go.

## Artifact

- Artifact SHA-256: `f2d54ffde8cec2af3dae4f9a62f15a8e8a5c31ca2fe2ecba93c93679f492f25b`

## Production recommendation

**NO-GO for production / live canary.** Staging targets met for Luna routing + provider dedupe + fail-closed bypass. Promote only after authorized link canary and operator sign-off.
