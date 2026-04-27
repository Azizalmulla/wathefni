# TOOLS.md - Customer Tool Contracts

Tools are silent fact, state, or transaction operations. Never mention tool names or internal effects to the customer.

Use only values grounded in the customer's visible latest message or live server state. Do not claim a tool result until the tool/server confirms it.

## `propose_turn_decision`

Structured observation for the orchestrator. Use when required by runtime instructions. It is not a state write and must not be mentioned to the customer.

## `get_price`

Route pricing and route-specific service options.

- Use when the customer provides or changes pickup and delivery sides.
- Pass the customer's area wording when unsure; the resolver owns clarification.
- Use returned quote/options only. Do not invent, round, or reuse stale prices.

## `check_area_coverage`

Read-only coverage lookup for one area, place, or landmark.

- Use for "do you deliver to X?" style questions.
- Do not use it for full route pricing.
- Reply only from returned coverage, mapping, ambiguity, or nearby suggestions.

## `apply_booking_field`

Validated booking writes for customer-provided or corrected facts.

- Sender name, sender phone, recipient name, recipient phone.
- Pickup and delivery address parts.
- `address_extra` is for apartment, floor, door, office, gate, landmark, or driver note.
- `address_house` is only for building-level house, villa, tower, or building identifier.
- If role or value is unclear, ask a short clarification instead of guessing.

## `propose_option_interpretation`

Proposal-only service option interpretation. Use when the latest message names or implies a quoted service option. The server reconciles the proposal with the quote catalog before committing selection.

## `set_pending_order_edits`

Use before asking the customer to provide multiple edit values later. Include only the fields you are about to ask for.

## `create_simple_order`

Order creation is server-owned. In the single-lifecycle flow, the server submits from `bookingTruthSnapshot` only after explicit semantic confirmation and matching summary hash.

Never claim the order was placed unless the server returns a real order artifact, such as order ID, tracking/payment artifact, or payment link.

## `track_order`

Use for tracking/status questions when a valid order ID or submitted order UID is available. If no valid ID is visible or stored, ask for the order number.

## `complains`

Use after the customer gives complaint details. Do not promise compensation, refunds, or a specific resolution unless another tool/server result confirms it.

## `request_handoff` / `assign_agent`

Use only when the customer needs human handling, unsupported operational help, refund action, payment/system-error support, unavailable/manual-confirmation service handling, or placed-order changes that cannot be safely handled in chat.

Do not say a handoff happened unless the tool/server confirms it.

## `carry_over_from_last_order`

Use only when the customer clearly asks to reuse saved details. Only claim reused values that the tool result confirms.

## Cancellation Tools

- `cancel_booking`: clear a pre-submission draft when the customer clearly cancels or restarts.
- `cancel_order`: cancel a placed order by UID when a post-order flow requires it.
