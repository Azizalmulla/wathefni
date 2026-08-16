# Privacy & retention notice (canary)

## What Wathefni processes
- Email envelope metadata (From/To/Subject/Message-ID/received time)
- CV attachments forwarded to the Wathefni intake address
- Extracted identity fields (name/email/phone when readable) for Held review
- Malware scan results and quarantine object references

## What Wathefni does **not** do in this canary
- Does **not** connect to or sync the customer’s Gmail/M365 mailbox (`WATHEFNI_MAILBOX_SYNC=off`)
- Does **not** auto-admit candidates into active hiring without HR action
- Does **not** start post-hiring workflows

## Retention posture (current production)
- Quarantine storage is encrypted/isolated per production inbound design
- `WATHEFNI_INTAKE_RETENTION_EXECUTE=off` — automated destructive retention cleanup is **not** executing
- Retention dry-run tooling exists for platform ops; customer-facing deletion follows support process
- Customer may request disable of intake address / kill switch / allowlist removal at any time

## Customer obligations
- Forward only recruitment-related mail
- Ensure candidates are informed under the customer’s own privacy notice that applications may be processed in Wathefni
- Restrict Wathefni admin access to HR owners who need settings + Held review

## Data residency / access
- Processing occurs in Wathefni production environment (current host posture)
- Access is tenant-scoped; platform ops alerts are not shown to normal HR users
