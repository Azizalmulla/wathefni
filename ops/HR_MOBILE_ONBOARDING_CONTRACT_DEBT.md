# HR mobile Onboarding — backend contract debt

**Status:** HR-actionable review wave shipped (Accept + Waive + preview + bank handoff).  
**Boundary:** Explicit mobile review wave within onboarding freeze — not a broader OS redesign.

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| List filter cost | Page of in_progress then **N+1** `dashboard_posthire_onboarding_detail` to keep `being_reviewed` | Batch HR-actionable projection / enrichment count on queue cards |
| Total counts | Mobile `total` ≈ filtered page length (not workforce-wide HR-actionable total) | Authoritative workforce HR-actionable count matching web |
| Remind | Intentionally omitted on mobile | Remains web-first |
| Bank decide | Read-only handoff copy; no ESS deep-link URL on mobile yet | Optional “Open on web” deep link when product provides one |
| Dual-side Civil ID preview | Mobile preview uses single file_id path | Surface `preview_front` / `preview_back` when present |
| Documents fan-out | Onboarding-sourced docs expose **preview only**; decisions route to Onboarding | Keep — avoid second decision queue |

## Explicitly out of mobile scope (web-first)

Reminders · start/restart · ownership rails · completion governance · bank ESS approve · HR uploads · bulk ops · full administration.
