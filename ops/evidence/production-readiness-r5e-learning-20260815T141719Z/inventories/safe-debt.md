# R5E safe debt

- HR Mobile Learning admin is intentionally absent (`mobile_ready=false`, not required).
- Attendance is assignment metadata, not a separate C2 table. Capacity is enforced in surfaces, not by reopening C2.
- Rejection reason is enforced in surfaces; C2 still accepts an empty reject reason if called directly.
- Employee catalog request currently posts the first published item as a first-wave action, not a full item picker.
- HR Web authoring forms are first-wave operational, not a polished design-system pass.
- Optional Talent skill-gap read is best-effort (`talent_skills` missing is swallowed).
- Backend owner permission fixture still omits `learning.read` the same way it omitted `talent.read`, so composition matrix rows stay stable. Frontend owner fixture includes `learning.read`.
- Benefits / ER / Engagement / Comp Planning / Workforce Planning remain unreleased.
