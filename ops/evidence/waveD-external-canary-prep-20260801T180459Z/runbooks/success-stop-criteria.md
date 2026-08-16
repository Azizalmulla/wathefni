# Canary success & stop criteria

## Success criteria (exit canary → consider next customer / longer window)

All must hold for **7 consecutive days** (stretch goal **14**):

1. ≥1 real external test CV and ≥5 production-like CVs processed to Held without silent loss  
2. Durable → Held materialization: every clean scanned CV yields Held app **or** auditable block/review  
3. Extraction: rich PDF/DOCX promote or soft-complete; **0** indefinite `pending`/`retrying` extraction jobs overnight  
4. Conflict/opaque CVs remain Held with warnings (not dropped)  
5. Message-ID duplicates idempotent (no double apps/docs)  
6. Dead-letter rate &lt; 5% of submissions / day (excluding intentional malware tests)  
7. Median intake validation→Held &lt; 2 minutes under normal load  
8. No cross-tenant leakage; allowlist remains exact two codes  
9. Customer HR completed ≥3 Held assign/admit actions successfully  
10. Kill switch drill completed once (on→verify waiting_budget→off) without data loss  
11. Mailbox sync remained **off** entire period  
12. No Sev-1 (orchestrator down, ClamAV down &gt;30m, allowlist misconfig)

## Stop / abort criteria (immediate kill switch + consider allowlist revoke)

Any one is enough:

| Trigger | Action |
|---|---|
| Cross-tenant data or wrong-company Held item | Kill + hard revoke |
| Allowlist accidentally opens `*` or extra companies | Hard revoke + incident |
| Mailbox sync flipped on | Turn off immediately; stop canary |
| Dead-letter &gt; 20% for 24h or backlog &gt; 50 open jobs | Kill switch; diagnose |
| Pending job age &gt; 1h systemic | Kill switch; pause worker only if global |
| Malware scanner outage &gt; 2h with growing quarantine | Kill switch; communicate |
| Customer requests stop / privacy concern | Soft disable + optional revoke |
| Identity/extraction regresses to silent completion without Held | Kill + engineering hold |

## Exit options after 7–14 days

| Outcome | Next step |
|---|---|
| Success | Keep canary tenant; optionally add 2nd company with same controls |
| Partial (ops friction only) | Extend 7 days; keep single tenant |
| Abort | Revoke allowlist; disable intakes; RCA |
| Never | Broader GA or connector enablement without new qualification |
