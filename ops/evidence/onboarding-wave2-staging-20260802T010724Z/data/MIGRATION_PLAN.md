# Four-real migration / backfill plan (read-only)

**Template:** `default_kuwait@2.0.0`  
**Applied:** `False` — **must not apply to production**

## Policy

- `preserve_received_and_reminders`: True
- `obsolete_only_via_audit`: True
- `brian_explicit`: True
- `production_apply`: False
- `staging_synthetic_only_until_canary_go`: True

## Employees

### Talal Fadhli (`WATHEFNI-96550252254`)

- Live items: **6**
- Brian partial: **False**
- Missing to add on backfill: **31**
- Obsolete to retire (audited): **2** → medical, education_cert
- Bank: keep bank_details row; set collection_mode=ess_encrypted; never plaintext
- Apply to production: **False**

### Fouad Burhamad (`WATHEFNI-96566363363`)

- Live items: **6**
- Brian partial: **False**
- Missing to add on backfill: **31**
- Obsolete to retire (audited): **2** → medical, education_cert
- Bank: keep bank_details row; set collection_mode=ess_encrypted; never plaintext
- Apply to production: **False**

### mohammad alqattan (`WATHEFNI-96597727743`)

- Live items: **6**
- Brian partial: **False**
- Missing to add on backfill: **31**
- Obsolete to retire (audited): **2** → medical, education_cert
- Bank: keep bank_details row; set collection_mode=ess_encrypted; never plaintext
- Apply to production: **False**

### unknown (`WATHEFNI-96599411617`)

- Live items: **0**
- Brian partial: **True**
- Missing to add on backfill: **36**
- Obsolete to retire (audited): **0** → none
- Bank: keep bank_details row; set collection_mode=ess_encrypted; never plaintext
- Apply to production: **False**

## Explicit Brian handling

Brian (`…411617`) has a partial/legacy checklist. Backfill must insert missing canonical items as `pending`, preserve any received history, and record an audit event `onboarding_migration_brian_partial` before touching rows. Do not wipe `personal_photo`.

