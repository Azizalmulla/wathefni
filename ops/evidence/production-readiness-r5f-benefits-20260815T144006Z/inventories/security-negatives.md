# R5F security negatives

Direct API proves on staging:

- Unauthenticated dashboard / employee Benefits not public (401/403/503)
- Tenant B cannot see tenant A enrollments
- Manager 403 on workspace and enrollments (“Managers do not have a Benefits workspace.”)
- HR without `benefits.read` 403
- HR `benefits.read` only cannot write plans; cannot read contributions
- Employee workspace is self-keyed; IDOR override does not return the other employee's enrollments
- Employee cannot confirm coverage via dashboard confirm route
- Remaining Wave 6 namespaces (ER / Comp Planning / WFP) stay `capability_not_released` on the live staging service
