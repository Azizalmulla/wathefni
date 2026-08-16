# R5G security negatives

Direct API proves on staging:

- Unauthenticated ER workspace / mobile not public (401/403/503)
- Tenant B cannot read tenant A case (direct-object IDOR blocked)
- Manager 403 on workspace and case detail (“Managers do not have an Employee Relations workspace.”)
- HR without `er.*` 403; 403 payload is not empty-cases copy
- Investigator A cannot list or read Case B
- Unauthorized evidence retrieve 403; raw provider URL never returned
- Export without `er.export` is 403
- Unauthorized mobile queue/summary fail-closed
- Assistant unauthorized denied; Assistant mutation forbidden
- Wave 5 rejects allegation/narrative free text
- Remaining Wave 6 namespaces (Engagement / Comp Planning / WFP) stay `capability_not_released` on the live staging service
