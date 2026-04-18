#!/usr/bin/env node
/**
 * Smoke test: full-text n-gram evidence binding.
 *
 * Regression fix for the "Ok lets book slwa to slmya" false-positive smuggle
 * rejection. The old guard only inspected the narrow substring left of the
 * "to"/"من" separator ("Ok lets book slwa"), which no resolver can match.
 *
 * The new `collectAreaEvidenceFromText` tokenizes the full customer message
 * into 1–3 word n-grams and resolves each through the same matcher the LLM
 * uses, building a set of area IDs the customer plausibly referenced. The
 * guard then demotes reject/needs_clarification decisions whenever the
 * model's claimed area is in that evidence set — no regex whack-a-mole for
 * conversational prefixes, no language/phrasing gating.
 */
import assert from "node:assert/strict";
import {
  defaultPublishedPricingPath,
  loadRidersToolsModule,
} from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const mod = await loadRidersToolsModule(import.meta.url);
  const hooks = mod.__resolverTestHooks;
  assert(hooks?.collectAreaEvidenceFromText, "missing collectAreaEvidenceFromText hook");
  const { collectAreaEvidenceFromText, buildPublishedPricingData } = hooks;

  const fs = await import("node:fs");
  const pricingSource = JSON.parse(fs.readFileSync(defaultPublishedPricingPath, "utf8"));
  const data = buildPublishedPricingData(pricingSource, pricingSource);
  assert(Array.isArray(data.areas) && data.areas.length > 0, "pricing areas empty");

  const idByName = new Map(
    data.areas.map((a) => [a.name_en.toLowerCase(), a.id]),
  );
  const idFor = (name) => {
    const id = idByName.get(name.toLowerCase());
    assert(typeof id === "number", `fixture area missing: ${name}`);
    return id;
  };

  const salwa = idFor("Salwa");
  const salmiya = idFor("Salmiya");
  const hawalli = idFor("Hawalli");
  const jahra = idFor("Jahra");

  const run = (label, text, expected) => {
    const got = collectAreaEvidenceFromText(text, data);
    for (const id of expected) {
      assert(
        got.has(id),
        `${label}: expected area id ${id} in evidence set; got [${[...got].join(",")}]`,
      );
    }
    console.log(`ok - ${label}`);
  };

  run(
    "conversational English prefix is ignored",
    "Ok lets book slwa to slmya",
    [salwa, salmiya],
  );
  run(
    "polite prefix + typos",
    "please quote me salwa to salmyia",
    [salwa, salmiya],
  );
  run(
    "verb + filler prefix",
    "i want delivery from salwa to hawalli please",
    [salwa, hawalli],
  );
  run(
    "trailing filler",
    "salwa to salmiya for my cousin",
    [salwa, salmiya],
  );
  run(
    "Arabic prefix (abi ahjiz)",
    "أبي أحجز من السالمية إلى حولي",
    [salmiya, hawalli],
  );
  run(
    "Arabizi + English mix",
    "abi ahjiz slwa to hawally",
    [salwa, hawalli],
  );
  run(
    "punctuation-only split",
    "salwa, salmiya",
    [salwa, salmiya],
  );
  run(
    "question phrasing",
    "how much is jahra to salwa?",
    [jahra, salwa],
  );

  // Negative case: pure garbage returns empty evidence.
  const garbage = collectAreaEvidenceFromText("xxxxx yyyy zzzz", data);
  assert.equal(garbage.size, 0, `expected empty evidence for garbage, got [${[...garbage].join(",")}]`);
  console.log("ok - pure garbage returns no evidence");

  // Negative case: adversarial claim with no corroborating token → guard
  // would NOT be suppressed (evidence set does not contain the claim).
  const adversarial = collectAreaEvidenceFromText("atlantis to moon", data);
  assert(
    !adversarial.has(salwa) && !adversarial.has(salmiya),
    `adversarial text should not surface real areas; got [${[...adversarial].join(",")}]`,
  );
  console.log("ok - adversarial unrelated text does not manufacture evidence");

  console.log("\nArea-evidence n-gram suite passed.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
