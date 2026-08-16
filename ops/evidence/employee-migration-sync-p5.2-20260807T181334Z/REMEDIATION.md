# Existing connector secret remediation (WATHEFNI)

| Metric | Value |
|---|---|
| Encryption available at remediate | `true` |
| Insecure secrets found | `2` |
| Resealed to Fernet | `2` |
| Require re-entry | `0` |

| connection_id | prior_alg | action | new_alg |
|---|---|---|---|
| `03187821-9921-4642-ab20-97dee98f36c9` | plainhex | resealed | fernet |
| `f0585b18-8d02-404a-a393-e7d367390ff1` | plainhex | resealed | fernet |

Secret values were never printed. Post-remediation scan: `alg=fernet` only for WATHEFNI.
