# R5E E2E journeys A–F

Proved on staging tenant `R5EC348CC` (`R5E_LEARNING_SURFACE_DB_PASS`, 74/0).

| Journey | Result |
|---|---|
| A Assignment | HR catalog item → assign employee → employee workspace and HR list converge; assigned is not enrolled or completed |
| B Employee request | request created (`is_enrollment=false`) → reject without reason refused → approve creates enrollment, not completion; request ≠ approval ≠ enrollment |
| C Session | offering capacity 1 → enroll EMP2 → overflow EMP refused (`session_capacity_exceeded`) → attendance metadata → completion only via evidence |
| D Certification | evidence-backed completion → cert issued with approaching expiry → renewal issued → prior certificate remains (≥2 rows); expiry does not erase history |
| E Performance | fulfillment link attached; `silently_closed_c3=false`; C3 remains sole development authority; C3 row unchanged or absent |
| F Optional dependencies | Learning workspace ready with Performance OFF + Talent OFF + JA OFF; no auto-HiPo; no learning Talent score |

Also proved: mandatory first generate + idempotent replay; employee mandatory self-complete forbidden; overdue ≠ failure.
