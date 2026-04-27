// Smoke test for Riders domain-scope boundary.
//
// Run from `delivery/` with:
//   node scripts/smoke-test-riders-scope-boundary.mjs
//
// Locks the "is Donald Trump president?" regression: Riders must not behave
// like a generic public-world Q&A bot, and must not emit external citations
// for unrelated general-knowledge questions.

import { readFileSync } from "node:fs";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");

const failures = [];
function assert(name, cond, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    console.log(`FAIL  ${name} -- ${detail || ""}`);
    failures.push(name);
  }
}

function read(rel) {
  return readFileSync(path.join(DELIVERY_ROOT, rel), "utf8");
}

const oneBrain = read("plugins/octopus-channel/lib/one-brain-context.ts");
const identity = read("workspaces/riders/IDENTITY.md");
const agents = read("workspaces/riders/AGENTS.md");
const skill = read("workspaces/riders/SKILL.md");
const combinedWorkspace = `${identity}\n${agents}\n${skill}`;

assert(
  "one-brain hard rule has Riders scope boundary",
  /Riders-scope boundary/.test(oneBrain) &&
    /NOT a general chatbot/.test(oneBrain) &&
    /unrelated public-world\/general-knowledge/.test(oneBrain),
  "missing hard runtime boundary",
);

assert(
  "one-brain bans unrelated politics/current-events answers",
  /politics/.test(oneBrain) &&
    /news/.test(oneBrain) &&
    /web\/current-events facts/.test(oneBrain) &&
    /do not answer the factual question/.test(oneBrain),
  "missing public-world refusal language",
);

assert(
  "one-brain bans unrelated citations and external links",
  /do not cite sources or external links/.test(oneBrain) &&
    /External links are allowed only when they are official Riders links/.test(
      oneBrain,
    ),
  "missing external citation/link boundary",
);

assert(
  "workspace identity bans generic assistant answers",
  /NEVER answer unrelated public-world\/general-knowledge questions/.test(
    identity,
  ) && /generic assistant/.test(identity),
  "IDENTITY.md missing generic assistant ban",
);

assert(
  "workspace docs route unrelated topics back to Riders",
  /Unrelated public-world\/general-knowledge questions/.test(agents) &&
    /Stay inside Riders scope/.test(skill) &&
    /Riders deliveries, prices, coverage, tracking, complaints, and order support/.test(
      combinedWorkspace,
    ),
  "workspace docs missing Riders redirect",
);

assert(
  "workspace bans non-Riders external citations",
  /NEVER include external citations or non-Riders links/.test(identity) &&
    /do not cite sources/.test(agents) &&
    /do not cite sources/.test(skill),
  "workspace docs missing citation ban",
);

console.log(`\n${failures.length === 0 ? "ALL PASS" : "FAILURES: " + failures.length}`);
if (failures.length > 0) process.exit(1);
