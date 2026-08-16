See `matrices.md` — Permission matrix.

| Actor | Sees |
|---|---|
| Talent read + source read | Full pointer |
| Talent read without source read | Hidden, or existence-only if sensitive and explicitly allowed |
| No Talent read | Denied |
| Other tenant | Empty |

Alignment visibility: owner, manager scope, org-unit, or configured company-wide. Server enforced. Alignment is not a permission bypass.
