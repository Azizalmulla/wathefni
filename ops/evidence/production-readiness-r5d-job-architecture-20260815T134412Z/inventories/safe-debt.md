# R5D safe debt

- Backend `workspace_capability.py` now mirrors `nav.job-architecture` (no module key) and `nav.talent`. Composition fixtures still omit `job_architecture.read`, so matrix rows stay stable.
- `/app/job-architecture` remains listed on the readiness spec as a reserved namespace but is unimplemented and not fail-closed. Generic 404 is expected.
- JA authoring forms in HR Web are first-wave operational, not a polished design system pass.
- Comp Planning band attachment and WFP grade consumption remain future slices (R5I / R5J).
