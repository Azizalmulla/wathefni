#!/usr/bin/env node

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");

const contextBlocks = readFileSync(
  join(ROOT, "plugins/octopus-channel/lib/context-blocks.ts"),
  "utf8",
);
const liveChannelContext = readFileSync(
  join(ROOT, "plugins/octopus-channel/lib/live-channel-context.ts"),
  "utf8",
);
const toolsMd = readFileSync(join(ROOT, "workspaces/riders/TOOLS.md"), "utf8");
const skillMd = readFileSync(join(ROOT, "workspaces/riders/SKILL.md"), "utf8");

// C1: remove the contradictory hidden-context rule that explicitly told the
// model to clarify ambiguous areas before the pricing tool.
assert.ok(
  !contextBlocks.includes("If either area is missing or ambiguous, clarify it first."),
  "C1: hidden context must not tell the model to clarify ambiguous route sides before get_price.",
);

// C2: hidden context must explicitly encode the new invariant.
assert.match(
  contextBlocks,
  /concrete route intent[\s\S]*still call get_price[\s\S]*Do NOT ask a free-composed area clarification before the tool/i,
  "C2: context-blocks must force tool-owned clarification for concrete route intents.",
);

// C3: the live channel context seen every turn must repeat the same invariant.
assert.match(
  liveChannelContext,
  /MUST call get_price in this turn[\s\S]*broad, fuzzy, or ambiguous[\s\S]*let the tool return clarification_required[\s\S]*Do NOT ask a free-composed area clarification before the tool/i,
  "C3: live-channel context must force tool-owned clarification for ambiguous route intents.",
);

// C4: Riders TOOLS.md must no longer say "Do NOT call until BOTH..." because
// that instruction directly caused the blocker transcript to bypass get_price.
assert.ok(
  !toolsMd.includes("Do NOT call until BOTH `pickup_area` and `dropoff_area` are confirmed."),
  "C4: Riders TOOLS.md must not require perfect confirmation before get_price.",
);

// C5: Riders TOOLS.md must explicitly tell the model to call get_price first
// on broad/parent area mentions like Kuwait City.
assert.match(
  toolsMd,
  /Do NOT wait for both areas to be perfectly confirmed[\s\S]*still call `get_price`[\s\S]*If the customer's route mentions a broad or parent area name like `Kuwait City`[\s\S]*first clarification must still come from `get_price`/i,
  "C5: Riders TOOLS.md must define tool-owned clarification for parent/broad area route intents.",
);

// C6: Riders SKILL.md must route ambiguous concrete routes into Step C rather
// than letting Step B short-circuit into a free-composed clarification.
assert.match(
  skillMd,
  /If the customer already gave a concrete route with both sides mentioned[\s\S]*Move to Step C and let `get_price` produce the clarification/i,
  "C6: SKILL.md Step B must not short-circuit concrete ambiguous routes.",
);
assert.match(
  skillMd,
  /The tool owns the clarification[\s\S]*Do NOT ask a free-composed \"which part\?\" question before the tool/i,
  "C7: SKILL.md Step C must explicitly force tool-owned clarification.",
);

console.log("smoke-test-route-intent-tool-owned-clarification: OK");
