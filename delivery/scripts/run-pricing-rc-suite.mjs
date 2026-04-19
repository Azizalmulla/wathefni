#!/usr/bin/env node
import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scriptsDir = path.dirname(fileURLToPath(import.meta.url));

const steps = [
  {
    label: "Pricing config alignment audit",
    script: "check-pricing-config-alignment.mjs",
  },
  {
    label: "Pricing overlay status smoke",
    script: "smoke-test-local-pricing-overlay-status.mjs",
  },
  {
    label: "Published pricing resolver smoke",
    script: "smoke-test-published-pricing-resolver.mjs",
  },
  {
    label: "Local area resolver smoke",
    script: "smoke-test-local-area-resolver.mjs",
  },
  {
    label: "Local pricing admin resolver smoke",
    script: "smoke-test-local-pricing-admin-resolver.mjs",
  },
  {
    label: "Local geo ordering resolver smoke",
    script: "smoke-test-local-geo-ordering-resolver.mjs",
  },
  {
    label: "Area pre-resolution regression smoke",
    script: "smoke-test-area-preresolution.mjs",
  },
  {
    label: "Area graduated-response smoke",
    script: "smoke-test-area-graduated-response.mjs",
  },
  {
    label: "Area n-gram evidence smoke",
    script: "smoke-test-area-evidence-ngram.mjs",
  },
  {
    label: "Area alias coverage smoke (Jlai3a regression net)",
    script: "smoke-test-area-alias-coverage.mjs",
  },
  {
    label: "LLM area resolver fallback smoke (Option B)",
    script: "smoke-test-llm-area-resolver.mjs",
  },
  {
    label: "Pending area preservation across turns (Bug A + B regression)",
    script: "smoke-test-pending-area-preservation.mjs",
  },
  {
    label: "Effective pickup/delivery area (pin-resolved area counts as area slot)",
    script: "smoke-test-effective-area.mjs",
  },
  {
    label: "Carry-over source-precedence (fresh customer tuple beats carried-over identity)",
    script: "smoke-test-carryover-source-precedence.mjs",
  },
  {
    label: "Area-before-identity (missing route area gates sender/recipient asks)",
    script: "smoke-test-area-before-identity.mjs",
  },
  {
    label: "Letterless language stability (bare-number turn can't flip reply language)",
    script: "smoke-test-letterless-language-stability.mjs",
  },
  {
    label: "Arabizi input → English reply routing",
    script: "smoke-test-no-arabizi-replies.mjs",
  },
  {
    label: "Address completeness (Kuwaiti shapes) smoke",
    script: "smoke-test-address-completeness.mjs",
  },
  {
    label: "Reply hallucination guard smoke",
    script: "smoke-test-hallucination-guard.mjs",
  },
  {
    label: "Canonical-overwrite gate (Bug 1 + Bug 3 regression)",
    script: "smoke-test-canonical-overwrite-gate.mjs",
  },
  {
    label: "Name-shape validation (sender/recipient question rejection)",
    script: "smoke-test-name-shape-validation.mjs",
  },
  {
    label: "Slot-response coherence (intent classification + write-path gates)",
    script: "smoke-test-slot-response-coherence.mjs",
  },
  {
    label: "Slot-response coherence — greeting intent (2026-04-19 regression)",
    script: "smoke-test-coherence-greeting.mjs",
  },
  {
    label:
      "Slot-response coherence — acknowledgment intent (2026-04-19 22:08 'alright→sender_name' regression)",
    script: "smoke-test-coherence-acknowledgment.mjs",
  },
  {
    label:
      "Apply boundary — one pipeline for every proposal (evidence contract + source tagging)",
    script: "smoke-test-apply-boundary.mjs",
  },
  {
    label: "Outbound clarifying-question preservation (2026-04-19 regression)",
    script: "smoke-test-outbound-clarifying-question.mjs",
  },
  {
    label:
      "Outbound guards factual-only policy (Step-3: free phrasing, strict on facts)",
    script: "smoke-test-outbound-guards-factual-only.mjs",
  },
  {
    label:
      "Outbound decision contract (Step-4: 5-kind / 10-reason unified vocabulary)",
    script: "smoke-test-outbound-decision-contract.mjs",
  },
  {
    label:
      "Compact factual drift detector (Step-5: log-only phone/name claim drift)",
    script: "smoke-test-compact-factual-drift.mjs",
  },
  {
    label:
      "Ambiguous pair guard (reject silent recipient-attribution when sender unresolved)",
    script: "smoke-test-ambiguous-pair-guard.mjs",
  },
  {
    label:
      "Fast-path address extra (accept block+street+substantive-extra, matches completeness gate)",
    script: "smoke-test-fast-path-address-extra.mjs",
  },
  {
    label: "Persisted-state sanitizer (read-time validation at load boundaries)",
    script: "smoke-test-persisted-state-sanitizer.mjs",
  },
  {
    label: "Carry-over from last order (provenance + stale-skip + reset partition)",
    script: "smoke-test-carry-over-from-last-order.mjs",
  },
  {
    label: "Carry-over live drain (applyCarryOverOp — the path one-brain actually runs)",
    script: "smoke-test-carry-over-live-drain.mjs",
  },
  {
    label:
      "One-brain drain branches (anchors surviving op handlers after step-2 dead-code sweep)",
    script: "smoke-test-one-brain-drain-branches.mjs",
  },
  {
    label: "Summary fact verifier smoke",
    script: "smoke-test-summary-fact-verifier.mjs",
  },
  {
    label: "FSM state gate smoke",
    script: "smoke-test-fsm-state-gate.mjs",
  },
  {
    label: "Dialog state (DST) core smoke",
    script: "smoke-test-dialog-state.mjs",
  },
  {
    label: "DST-aware slot conflict guard smoke",
    script: "smoke-test-slot-conflict-guard.mjs",
  },
  {
    label: "2026-04-20 post-deploy bugfix regression anchors",
    script: "smoke-test-post-deploy-bugfixes.mjs",
  },
  {
    label: "Published pricing summary smoke",
    script: "smoke-test-published-pricing-summary.mjs",
  },
  {
    label: "Published pricing transcript smoke",
    script: "smoke-test-published-pricing.mjs",
  },
];

async function runStep(step) {
  const scriptPath = path.join(scriptsDir, step.script);
  const { stdout, stderr } = await execFileAsync(process.execPath, [scriptPath], {
    cwd: path.resolve(scriptsDir, ".."),
    env: process.env,
    maxBuffer: 20 * 1024 * 1024,
  });
  if (stdout) {
    process.stdout.write(stdout);
  }
  if (stderr) {
    process.stderr.write(stderr);
  }
}

async function main() {
  for (const step of steps) {
    process.stdout.write(`\n=== ${step.label} ===\n`);
    try {
      await runStep(step);
    } catch (error) {
      const stdout = error && typeof error === "object" && "stdout" in error ? error.stdout : "";
      const stderr = error && typeof error === "object" && "stderr" in error ? error.stderr : "";
      if (stdout) {
        process.stdout.write(String(stdout));
      }
      if (stderr) {
        process.stderr.write(String(stderr));
      }
      throw new Error(`Release-candidate suite failed during: ${step.label}`);
    }
  }

  process.stdout.write("\nPricing release-candidate suite passed.\n");
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
