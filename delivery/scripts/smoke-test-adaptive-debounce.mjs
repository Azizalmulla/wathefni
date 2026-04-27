// Smoke test for Riders adaptive WhatsApp debounce.
//
// Run from repo root:
//   node delivery/scripts/smoke-test-adaptive-debounce.mjs

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");
const SOURCE_FILE = path.join(
  DELIVERY_ROOT,
  "plugins/octopus-channel/lib/inbound-debounce.ts",
);

const outDir = mkdtempSync(path.join(tmpdir(), "adaptive-debounce-"));
const tscBin = path.join(DELIVERY_ROOT, "node_modules/.bin/tsc");

const config = {
  defaultTextMs: 1000,
  mediaMs: 2500,
  explicitActionMs: 0,
  clearRouteMs: 500,
  shortFragmentMs: 1500,
  maxTextMs: 2000,
};

function msg(text, extras = {}) {
  return {
    messageText: text,
    audioMessage: null,
    imageMessage: null,
    locationMessage: null,
    ...extras,
  };
}

try {
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

  const mod = await import(
    url.pathToFileURL(path.join(outDir, "inbound-debounce.js")).href
  );
  const { resolveAdaptiveInboundDebounce } = mod;

  {
    const d = resolveAdaptiveInboundDebounce([msg("confirm")], config, 0);
    assert.equal(d.delayMs, 0);
    assert.equal(d.reason, "explicit_action");
  }

  {
    const d = resolveAdaptiveInboundDebounce([msg("delivery")], config, 0);
    assert.equal(d.delayMs, 0);
    assert.equal(d.reason, "explicit_action");
  }

  {
    const d = resolveAdaptiveInboundDebounce([msg("توصلون لي افنيوز؟")], config, 0);
    assert.equal(d.delayMs, 1000);
    assert.equal(d.reason, "normal_text");
  }

  {
    const d = resolveAdaptiveInboundDebounce([msg("salmiya")], config, 0);
    assert.equal(d.delayMs, 1500);
    assert.equal(d.reason, "short_fragment");
  }

  {
    const d = resolveAdaptiveInboundDebounce(
      [msg("from salmiya to hawalli")],
      config,
      0,
    );
    assert.equal(d.delayMs, 500);
    assert.equal(d.reason, "clear_full_route");
  }

  {
    const d = resolveAdaptiveInboundDebounce(
      [msg("salmiya"), msg("hawalli")],
      config,
      900,
    );
    assert.equal(d.delayMs, 1100);
    assert.equal(d.reason, "max_wait_cap");
    assert.equal(d.uncappedDelayMs, 1500);
  }

  {
    const d = resolveAdaptiveInboundDebounce(
      [msg("photo", { imageMessage: { id: "img-1" } })],
      config,
      0,
    );
    assert.equal(d.delayMs, 2500);
    assert.equal(d.reason, "media");
  }

  console.log("ALL PASS smoke-test-adaptive-debounce.mjs");
} finally {
  rmSync(outDir, { recursive: true, force: true });
}
