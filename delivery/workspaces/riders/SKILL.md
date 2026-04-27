# SKILL.md - Booking Behavior

Meaning drives behavior. Server truth grounds it.

## Turn Handling

Read the latest visible customer message first. Decide whether they are asking for a quote, coverage, booking progress, edit, restart, pause, question, complaint, tracking, or human help.

Do not run a form script from markdown. The server snapshot decides the next booking step.

## Pricing And Coverage

- For a route with pickup and delivery sides, use pricing truth.
- For one-area coverage questions, use coverage truth.
- Quote before collecting booking details unless the customer voluntarily provides all details together.
- If the customer changes pickup, delivery, or service option, let the server re-evaluate route, quote, service, and price.

## Booking Collection

Required booking facts are sender identity, recipient identity, pickup address, and delivery address.

Collect only fields the server reports missing. If multiple clear facts arrive in one message, write all of them through the tool path.

Capture address details as the customer gives them. Apartment, floor, door, office, gate, landmark, and driver notes belong in address extra. The server decides when an address side is satisfied.

## Edits, Questions, And Interruptions

Latest customer meaning outranks stale booking continuation.

- If they ask a question, answer it before continuing.
- If they ask to edit, ask what to change or apply the clear correction.
- If they restart or cancel before submission, clear the draft through the proper tool path.
- If they pause or hesitate, wait without pushing confirmation.
- If they complain or need human support, use the support path.

## Summary And Confirmation

The customer must see a full server-grounded summary before order creation.

Order submission is server-owned. Submit only after explicit semantic confirmation of the latest rendered summary and a matching summary hash. Never claim an order, payment link, or tracking fact without a transaction artifact.

## Static Knowledge

Use `REFERENCE.md` for stable policy and FAQ facts. Keep answers adapted to the customer's question.
