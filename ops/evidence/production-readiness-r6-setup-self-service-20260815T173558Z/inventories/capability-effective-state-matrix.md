# R6 capability / effective-state matrix

Resolver: `setup_console_effective_state.resolve_effective_state`.

R5A `customer_facing_state` is the public vocabulary. `effective_state` is the R6 discriminator.

| Situation | effective_state | customer_facing_state | usable | Proved |
|---|---|---|---|---|
| Released + deployable + stored on | `enabled_usable` | `enabled` | true | R5A unit + R6 unit |
| Released + deployable + stored off | `available_disabled` | `disabled` | false | R6 unit |
| Stored on + analytics kill | `unavailable_deployment` | `unavailable` | false | Staging B |
| Stored on + C1 off | `unavailable_deployment` | `unavailable` | false | Unit (kill still wins) |
| Comp/WFP without company JA | `dependency_unmet` | `dependency_unmet` | false | Staging C + HTTP 409 |
| Ordinary HR Setup | `not_permitted` | `not_permitted` | false | Staging G 403 |
| Unreleased capability | `not_released` | `not_released` | false | None remain after R5J |

Honesty flags:

- `one_effective_state=true`
- `consumes_capability_readiness=true`
- `no_second_availability_system=true`
- `stored_enabled_does_not_imply_usable=true`
- `enabled_never_shown_when_runtime_unavailable=true`
- `env_names_never_exposed=true`

R5A after R6: `customer_facing_state enabled` still passes when performance is released and stored enabled. `UNRELEASED_CAPABILITY_KEYS=()`.
