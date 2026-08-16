# R5G web / app / mobile convergence

- HR Web and HR Mobile read the same C4 tables through `employee_relations_surfaces`.
- HR Web is the sealed investigation/evidence authoring workspace.
- HR Mobile is a thin operational adapter: privacy-safe queue, scoped summary, acknowledge. It does not clone investigation notes, findings, witnesses, or evidence bodies.
- There is no Employee App ER case-management surface and no `/app/employee-relations` namespace.
- Manager dashboard routes 403. Scoped contribution is a separate grant, not a Manager workspace.
- Home/Inbox/priority items for authorized ER actors use generic copy and entitlement composition (`employee_relations_actions`). Managers never receive that feature.
