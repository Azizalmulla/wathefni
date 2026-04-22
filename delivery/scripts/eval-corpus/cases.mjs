// Phase C eval corpus — declarative cases (2026-04-21).
//
// Each case describes one conversation shape we want to measure, derived
// from a live blocker class in `BUG_CLASSES.md` or a happy-path regression
// anchor. The `turns` field drives the runner — per turn we supply the
// customer text and (optionally) per-turn contract assertions. `expected`
// records the target contract so the rollup can tell real progress from
// noise.
//
// Case `kind`:
//   - "live" — runs through the real webhook against prod; collects
//     drift / structured-output emits from the gateway between turns.
//   - "unit" — pure in-process check (schema validator round-trips, etc);
//     contributes its pass/fail signal to the corpus rollup without
//     hitting the network.
//
// Per-turn `assert` is ADVISORY — the corpus is a measurement tool, not
// a blocker. A failed assert is recorded in the report as `warn`, not as
// a runner exit. Only the schema-validator unit cases are hard-fail.
//
// Per-case conversation isolation (deferred — 2026-04-21)
// -------------------------------------------------------
// Ideally each live case would declare its own `reply_target` test phone
// so each case runs on a fresh Octopus conversation (no state bleed
// between cases). The runner already honours `caseDef.reply_target` via
// `resolveCaseConfig`, but the harness requires each phone to have a
// pre-bootstrapped active Octopus conversation before the first smoke
// run — phones that have never messaged the bot fail the resolve step
// with `Could not resolve an active live conversation_id for <phone>`.
//
// Until we add a bootstrap flow (or a conversation close/reopen API),
// all live cases share the default `RIDERS_LIVE_SMOKE_REPLY_TARGET`,
// which means the second+ case in a sweep sees state bleed from the
// prior case. Only the first live case in a run is truly clean.
//
// When bootstrap is wired up, restore the `reply_target` field on each
// live case (numbers must be dedicated test WhatsApp numbers, validated
// by `assertReplyTargetLooksLikeTestNumber` in the shared harness).

export const CASES = [
  // -------------------------------------------------------------------
  // Class 15 family — route_intent_turn_bypasses_get_price
  // -------------------------------------------------------------------
  {
    id: "C15-paired-ambiguous-city",
    kind: "live",
    class_ref: "class-15",
    description:
      "Paired turn: route intent with an ambiguous city (Kuwait City), followed by the clarification answer. Historically the turn-1 `get_price` bypass case.",
    turns: [
      {
        customer_text: "delivery salmiya to kuwait city pls",
        assert: {
          drift: {
            turn_kind: "initial_route",
            outcome_expected: ["tool_owned", "class15_repair"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
      {
        customer_text: "bnaid al qar",
        assert: {
          drift: {
            turn_kind_expected: ["post_clarify_continuation", "other"],
            outcome_expected: ["tool_owned"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
    ],
  },
  {
    id: "C15-single-full-route",
    kind: "live",
    class_ref: "class-15-happy",
    description:
      "Full route in one message (no ambiguity). Turn 1 must call get_price and produce a quote.",
    turns: [
      {
        customer_text: "dude salmiya to bnaid al qar",
        assert: {
          drift: {
            turn_kind: "initial_route",
            outcome_expected: ["tool_owned"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
    ],
  },

  // -------------------------------------------------------------------
  // Class 16 family — single_token_clarification_misattribution
  // -------------------------------------------------------------------
  {
    id: "C16-paired-doha-mina-doha",
    kind: "live",
    class_ref: "class-16",
    description:
      "Paired turn: Hawalli → Doha (ambiguous), clarified by single-token 'mina doha'. Historical blocker for the Class-16 symmetric-rebind guard.",
    turns: [
      {
        customer_text: "delivery hawalli to doha pls",
        assert: {
          drift: {
            turn_kind: "initial_route",
            outcome_expected: ["tool_owned", "class15_repair"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
      {
        customer_text: "mina doha",
        assert: {
          drift: {
            turn_kind_expected: ["post_clarify_continuation", "other"],
            outcome_expected: ["tool_owned"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
    ],
  },
  {
    id: "C16-paired-doha-mina-doha-reverse",
    kind: "live",
    class_ref: "class-16-mirror",
    description:
      "Mirror of C16: Doha (ambiguous) → Hawalli, clarified by 'mina doha'. Catches asymmetric bugs in the guard that would miss one direction.",
    turns: [
      {
        customer_text: "delivery doha to hawalli pls",
        assert: {
          drift: {
            turn_kind: "initial_route",
            outcome_expected: ["tool_owned", "class15_repair"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
      {
        customer_text: "mina doha",
        assert: {
          drift: {
            turn_kind_expected: ["post_clarify_continuation", "other"],
            outcome_expected: ["tool_owned"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
    ],
  },

  // -------------------------------------------------------------------
  // Happy-path / regression anchors
  // -------------------------------------------------------------------
  {
    id: "happy-direct-quote",
    kind: "live",
    class_ref: "happy-path",
    description:
      "Clean, fully-specified route with no ambiguity. Turn 1 must produce a quote. Regression anchor: if the prompt / structured-output changes ever break the plain happy path, this fires.",
    turns: [
      {
        customer_text: "delivery salmiya to dasman pls",
        assert: {
          drift: {
            turn_kind: "initial_route",
            outcome_expected: ["tool_owned"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned"],
          },
        },
      },
    ],
  },
  {
    id: "informational-only-idle",
    kind: "live",
    class_ref: "informational-guard",
    description:
      "Idle-conversation informational question. Must not advance to booking collection. Both `turn_kind=informational` + `pricing_action=informational_only` are the expected declarations.",
    turns: [
      {
        customer_text: "what is the cheapest option",
        assert: {
          drift: {
            turn_kind_expected: ["other", "informational"],
            outcome_expected: ["irrelevant"],
          },
          proposer: {
            present: true,
            schema_valid: true,
            plan_vs_fire: ["aligned", "n/a"],
          },
        },
      },
    ],
  },

  // -------------------------------------------------------------------
  // Unit (hybrid) — schema validator contract tests
  // -------------------------------------------------------------------
  {
    id: "unit-schema-validator-contract",
    kind: "unit",
    class_ref: "phase-a-schema",
    description:
      "In-process schema validator contract checks. Does NOT emit drift/proposer logs; contributes `validator_ok` signal to the corpus rollup.",
    unit_run: "schema_contract",
  },
];

export const LIVE_CASES = CASES.filter((c) => c.kind === "live");
export const UNIT_CASES = CASES.filter((c) => c.kind === "unit");
