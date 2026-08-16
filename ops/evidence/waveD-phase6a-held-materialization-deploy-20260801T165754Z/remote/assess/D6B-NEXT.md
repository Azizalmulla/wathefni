# D6B — Next focused investigation (NOT fixed in D6A)

## Finding
Local/prod smoke after Held materialization still fails later on **canonical `cv_extraction` promotion**
(`smoke-test-inbound-email.py`: "canonical extraction promotes first governed CV").

## Evidence
- Local: `ops/evidence/waveD-phase6a-held-materialization-20260801T164408Z/verify/local-inbound-email-smoke-with-pdftotext.log`
- Prod pending `cv_extraction` jobs (WATHEFNI): see `d6b-cv-extraction-pending-count.txt`

## Scope for D6B
Investigate worker handoff / promotion from Held+governed identity → `cv_extraction` completion
and current-CV supersede. Do **not** regress D6A durable→Held materialization.

## Explicitly out of scope for D6A deploy
No cv_extraction promotion fix shipped in Wave D6A.
