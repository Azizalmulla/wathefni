// Smoke test for Z1-P0 `get_price` cold-start symmetric-area validator.
//
// Run from `delivery/` with:
//   node scripts/smoke-test-get-price-validator.mjs
//
// The test compiles `plugins/riders-tools/lib/get-price-validator.ts` on
// the fly via a one-shot tsc invocation so we can exercise the pure
// decision function without touching the full tool execute path.
//
// Coverage (maps to the acceptance tests the user listed):
//   - Acceptance 3 (fake symmetric tool call on cold start): rejected.
//   - Acceptance 4 (legit quote): passes.
//   - Acceptance 5 (mid-flow clarification with pending opposite side):
//       NOT rejected — preserves existing mid-flow rebind behaviour.
//   - Missing leg: passes (no symmetry).
//   - Case-variant ("khaldiya" vs "Khaldiya"): rejected.

import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");
const SOURCE_FILE = path.join(
  DELIVERY_ROOT,
  "plugins/riders-tools/lib/get-price-validator.ts",
);

const tscBin = path.join(DELIVERY_ROOT, "node_modules/.bin/tsc");
const outDir = mkdtempSync(path.join(tmpdir(), "z1p0-validator-"));

try {
  // Pass `--ignoreConfig` so tsc ignores delivery's tsconfig (which
  // would otherwise interpret the single-file invocation as
  // "files specified on commandline" and refuse to run).
  const tsc = spawnSync(
    tscBin,
    [
      SOURCE_FILE,
      "--target",
      "ES2020",
      "--module",
      "ES2022",
      "--moduleResolution",
      "bundler",
      "--esModuleInterop",
      "--skipLibCheck",
      "--ignoreConfig",
      "--outDir",
      outDir,
    ],
    { stdio: "pipe", encoding: "utf-8" },
  );
  if (tsc.status !== 0) {
    console.error("tsc failed:\n" + (tsc.stdout || "") + (tsc.stderr || ""));
    process.exit(1);
  }

  const compiledUrl = url.pathToFileURL(
    path.join(outDir, "get-price-validator.js"),
  ).href;
  const mod = await import(compiledUrl);
  const { evaluateSymmetricAreaGuard, formatRejectMetric } = mod;

  const failures = [];
  function assert(name, cond, detail) {
    if (cond) {
      console.log(`PASS  ${name}`);
    } else {
      console.log(`FAIL  ${name} -- ${detail || ""}`);
      failures.push(name);
    }
  }

  // Case A: env flag missing no longer disables the invariant.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Khaldiya",
      dropoffArea: "Khaldiya",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: undefined,
    });
    assert(
      "env unset → symmetric cold-start still rejects",
      d.action === "reject" && d.reason === "symmetric_cold_start",
      JSON.stringify(d),
    );
  }

  // Case B (Acceptance 3): cold-start symmetric with flag on → reject.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Khaldiya",
      dropoffArea: "Khaldiya",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "on",
    });
    assert(
      "acceptance 3 — cold-start symmetric Khaldiya/Khaldiya → reject",
      d.action === "reject" &&
        d.reason === "symmetric_cold_start" &&
        d.normalizedArea === "Khaldiya" &&
        typeof d.message === "string" &&
        d.message.includes("same area (Khaldiya)"),
      JSON.stringify(d),
    );
  }

  // Case B2: case-insensitive symmetry still catches it.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "KHALDIYA",
      dropoffArea: "khaldiya",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "true",
    });
    assert(
      "case-variant symmetric → reject",
      d.action === "reject" && d.reason === "symmetric_cold_start",
      JSON.stringify(d),
    );
  }

  // Case C (Acceptance 4): legitimate asymmetric route → pass.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Khaldiya",
      dropoffArea: "Salmiya",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "on",
    });
    assert(
      "acceptance 4 — Khaldiya → Salmiya passes validator",
      d.action === "pass" && d.reason === "not_symmetric",
      JSON.stringify(d),
    );
  }

  // Case D (Acceptance 5a): mid-flow clarification with pending pickup
  // pinned and requestedSlot=dropoff_area — the existing mid-flow rebind
  // would have a target, so we must NOT reject here. Guard passes.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Mirqab",
      dropoffArea: "Mirqab",
      requestedSlotName: "dropoff_area",
      pendingPickupAreaNameEn: "Hawalli",
      pendingDropoffAreaNameEn: null,
      envValue: "on",
    });
    assert(
      "acceptance 5a — mid-flow pending pickup + requestedSlot=dropoff → pass",
      d.action === "pass" && d.reason === "mid_flow_rebind_target_present",
      JSON.stringify(d),
    );
  }

  // Case D2 (Acceptance 5b): mid-flow with pending dropoff pinned and
  // requestedSlot=pickup_area.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Salmiya",
      dropoffArea: "Salmiya",
      requestedSlotName: "pickup_area",
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: "Jabriya",
      envValue: "on",
    });
    assert(
      "acceptance 5b — mid-flow pending dropoff + requestedSlot=pickup → pass",
      d.action === "pass" && d.reason === "mid_flow_rebind_target_present",
      JSON.stringify(d),
    );
  }

  // Case D3: mid-flow WITHOUT a pending opposite side — even with a
  // requestedSlot pinned, this is cold-start-shaped and should reject.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Salmiya",
      dropoffArea: "Salmiya",
      requestedSlotName: "dropoff_area",
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "on",
    });
    assert(
      "mid-flow with no pending opposite → reject (still cold-start shape)",
      d.action === "reject",
      JSON.stringify(d),
    );
  }

  // Case E: flag set to 'off' no longer disables the invariant.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Khaldiya",
      dropoffArea: "Khaldiya",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "off",
    });
    assert(
      "env=off → symmetric cold-start still rejects",
      d.action === "reject" && d.reason === "symmetric_cold_start",
      JSON.stringify(d),
    );
  }

  // Case F: missing leg (only pickup) → pass, not symmetric.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Khaldiya",
      dropoffArea: "",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "on",
    });
    assert(
      "missing dropoff → pass(not_symmetric)",
      d.action === "pass" && d.reason === "not_symmetric",
      JSON.stringify(d),
    );
  }

  // Case G: metric formatter shape.
  {
    const d = evaluateSymmetricAreaGuard({
      pickupArea: "Khaldiya",
      dropoffArea: "Khaldiya",
      requestedSlotName: null,
      pendingPickupAreaNameEn: null,
      pendingDropoffAreaNameEn: null,
      envValue: "on",
    });
    if (d.action !== "reject") throw new Error("setup failure for case G");
    const line = formatRejectMetric(d, {
      requestedSlotName: null,
      pendingPickupPresent: false,
      pendingDropoffPresent: false,
      stage: "idle",
    });
    assert(
      "metric formatter includes reason + area + stage",
      line.startsWith("[metric] get_price.validator_reject") &&
        line.includes("reason=symmetric_cold_start") &&
        line.includes('pickup="Khaldiya"') &&
        line.includes('dropoff="Khaldiya"') &&
        line.includes("requestedSlot=null") &&
        line.includes("pendingPickup=null") &&
        line.includes("pendingDropoff=null") &&
        line.includes("stage=idle"),
      line,
    );
  }

  if (failures.length) {
    console.error(
      `\n${failures.length} smoke-test assertion(s) failed:\n  - ` +
        failures.join("\n  - "),
    );
    process.exit(1);
  }
  console.log("\nAll Z1-P0 validator smoke assertions passed.");
} finally {
  try {
    rmSync(outDir, { recursive: true, force: true });
  } catch {}
}
