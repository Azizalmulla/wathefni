# Civil ID dual-side Front upload 500 — root cause fix

**Stamp:** 20260806T020012Z

## Audit (Aziz live Front upload ~01:56Z)

| Check | Result |
|---|---|
| Request | `POST /app/onboarding/documents` from mobile IP |
| HTTP | **500** (twice) |
| Mobile copy | Generic “file could not be uploaded” — client maps non-structured 500 to `upload.failed` / `error.generic` (no JSON `detail`) |
| Backend error | `TypeError: Object of type date is not JSON serializable` in `attach_part` → jsonb insert of OCR `expiry_date`/`issue_date` |
| Follow-on | Same class of bug for `datetime` in `lifecycle_meta` via `parts_projection.uploaded_at` |
| `governed_document_version_parts` | Present / ensure OK |
| Dual-side flags on worker | on · WATHEFNI · Aziz |
| Canary document_type lane | `civil_id_dual_side_canary` (isolated) |
| Real Civil ID | Untouched throughout · SHA `fe98f7d9…0bb7` |

## Fix

1. `_json_ready` before jsonb writes in dual-side module (date/datetime/UUID).
2. Serialize `uploaded_at` in `parts_projection`.
3. Sanitize `set_item_lifecycle` meta_patch with `json.dumps(..., default=str)`.

## Prove

- In-process Front upload with OCR dates → **HTTP 200**, `draft_parts`, front present, back missing, expiry serialized `2028-06-01`.
- Canary hard-reset to pending with empty parts.
- Real Civil ID accepted + SHA unchanged.

## Phone retest

Force-close / reopen app → Onboarding → **CANARY ONLY — Civil ID front & back** → Upload Front then Back.
