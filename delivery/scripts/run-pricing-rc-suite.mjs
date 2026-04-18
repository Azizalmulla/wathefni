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
    label: "Address completeness (Kuwaiti shapes) smoke",
    script: "smoke-test-address-completeness.mjs",
  },
  {
    label: "Reply hallucination guard smoke",
    script: "smoke-test-hallucination-guard.mjs",
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
