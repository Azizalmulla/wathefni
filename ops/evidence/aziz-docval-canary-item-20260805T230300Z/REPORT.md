# Aziz disposable Civil ID canary item — Document Validation Parity

**Stamp:** see folder name  
**Employee:** Aziz `WATHEFNI-96599338566`  
**Item:** `civil_id_canary_test`  
**Label:** `CANARY ONLY — Civil ID upload test (disposable)`

## Safety

| Guard | Status |
|---|---|
| Real `civil_id` | Untouched (`accepted`) |
| `document_type` | `civil_id_canary_test` (isolated version lane) |
| Required / progress | `required=false` — does not move checklist counts |
| Soft-gate validation | Aliased to Civil ID via `CANARY_VALIDATION_ALIASES` |
| Native / OTA | Not required |

## Verify (live)

```
visible_in_employee_app: true
group: your_actions
actions: ["upload"]
upload_enabled: true
real_civil_id_status: accepted
VERIFY PASS
```

## Test order (three attempts)

1. **Clear mismatch** — upload passport / wrong file as this canary item → blocked with calm EN/AR message; item stays pending (retry OK).  
2. **Blurry / uncertain** — soft unclear upload → submits; alert that HR will double-check. Then run **reset** before attempt 3.  
3. **Correct Civil ID** — clear Civil ID photo/PDF → accepts into processing.

After any successful/uncertain upload the canary moves out of pending (no Upload). Re-open upload without deleting canary history:

```bash
# on prod orchestrator
WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py reset
```

## Cleanup / restore

```bash
WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py cleanup
WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py verify
# expect canary_present false; civil_id still accepted
```

Deletes only canary-scoped rows (`civil_id_canary_test`). Asserts real Civil ID status/hash unchanged.

## Ops script

`wathefni-orchestrator/ops-aziz-docval-canary-item.py` — `create` | `verify` | `reset` | `cleanup`
