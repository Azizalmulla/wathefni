# R5G permission matrix

| Actor | Workspace / list | Case A if granted | Case B (no grant) | Sensitive evidence | Investigator notes | Finding / outcome | Export | Mobile queue |
|---|---|---|---|---|---|---|---|---|
| Owner / HR with `er.manage` + grant | grant-scoped | yes | no | if `er.sensitive` + grant | if investigate grant | if decide/manage + grant | if `er.export` | yes (if `er.read`) |
| HR `er.read` + grant | grant-scoped | header / permitted fields | no | no | no | no | no | yes |
| HR `er.investigate` + grant | grant-scoped | investigate | no | if `er.sensitive` | yes | no (unless decide) | no | yes |
| HR `er.decide` + grant | grant-scoped | decide | no | if `er.sensitive` | if investigate | yes | no | yes |
| HR admin / operator without `er.*` | 403 | 403 | 403 | 403 | 403 | 403 | 403 | no feature |
| Manager (default) | 403 | 403 | 403 | 403 | 403 | 403 | 403 | no feature |
| Manager with explicit contribution grant | no workspace | scoped contribution only | no | no | no | no | no | no |
| Empty assignment + `er.*` | empty / zeros | n/a | n/a | n/a | n/a | n/a | empty | empty |
| Unauthenticated | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 |
