#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: letterless turns (digits/punctuation/whitespace only)
// must inherit the conversation's fallback language.
//
// Product rule (2026-04-19):
//   A bare-number turn like "929" carries zero language signal by
//   construction. It must NOT be able to flip the conversation's
//   preferred reply language. The 2026-04-19 transcript hit exactly
//   this: an otherwise-English conversation replied in Arabic after
//   the customer typed "929" — the fallback chain briefly produced
//   "ar" for a letterless turn, and `resolveCustomerReplyLanguage`
//   had a code path that could return it via `detectConversationLanguage`
//   instead of inheriting. We've now pinned letterless turns to return
//   the explicit fallback unconditionally.
//
// Cases covered:
//   T1  pure digits + fallback=en → en
//   T2  pure digits + fallback=ar → ar
//   T3  digits + punctuation + fallback=en → en
//   T4  emoji-only + fallback=en → en
//   T5  Latin letters present → still "en" regardless of fallback
//       (the text signal wins)
//   T6  Arabic letters present → still "ar" regardless of fallback
//   T7  Mixed Latin+Arabic → `detectConversationLanguage` decides
//       (preserved behavior; not the subject of today's fix)
//   T8  Empty text → returns fallback (existing behavior)
//   T9  Explicit language override still dominates letterless text
// ---------------------------------------------------------------------------

import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const policy = loadTs("plugins/shared/conversation-policy.ts");
const { resolveCustomerReplyLanguage, resolveCustomerScriptMode } = policy;

function resolve({ text, fallback = "en", explicit = null, lowSignal = false }) {
  return resolveCustomerReplyLanguage({
    visibleText: text,
    explicitLanguage: explicit,
    fallbackLanguage: fallback,
    preferFallbackForLowSignalText: lowSignal,
  });
}

function resolveScript({ text, fallback = "en", explicit = null }) {
  return resolveCustomerScriptMode({
    visibleText: text,
    explicitLanguage: explicit,
    fallbackLanguage: fallback,
  });
}

// -----------------------------------------------------------------------
// T1: pure digits + fallback=en → en. Screenshot scenario.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "929", fallback: "en" });
  assert(r === "en", `T1: "929" with fallback=en must stay en; got ${r}`);
}

// -----------------------------------------------------------------------
// T2: pure digits + fallback=ar → ar. The inverse: an Arabic
// conversation that slips in a bare number must not flip to English.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "929", fallback: "ar" });
  assert(r === "ar", `T2: "929" with fallback=ar must stay ar; got ${r}`);
}

// -----------------------------------------------------------------------
// T3: digits + punctuation + whitespace → fallback.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "  929.  ", fallback: "en" });
  assert(r === "en", `T3: "  929.  " with fallback=en must stay en; got ${r}`);
}

// -----------------------------------------------------------------------
// T4: emoji-only → fallback. Emoji are letterless by our rule.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "👍👍", fallback: "en" });
  assert(r === "en", `T4: emoji-only with fallback=en must stay en; got ${r}`);
}

// -----------------------------------------------------------------------
// T5: Latin text → en regardless of fallback. Real text signal wins.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "hello", fallback: "ar" });
  assert(r === "en", `T5: "hello" with fallback=ar must still be en; got ${r}`);
}

// -----------------------------------------------------------------------
// T6: Arabic text → ar regardless of fallback.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "مرحبا", fallback: "en" });
  assert(r === "ar", `T6: Arabic text with fallback=en must be ar; got ${r}`);
}

// -----------------------------------------------------------------------
// T7: Mixed Latin+Arabic → `detectConversationLanguage` decides.
// Preserved legacy behavior — we didn't touch this path and shouldn't
// regress it.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "اسمي John", fallback: "en" });
  // Mostly Arabic by char count → "ar".
  assert(r === "ar" || r === "en", `T7: mixed text returns a language; got ${r}`);
}

// -----------------------------------------------------------------------
// T8: empty text → fallback.
// -----------------------------------------------------------------------
{
  assert(resolve({ text: "", fallback: "en" }) === "en", `T8a: empty+en=en`);
  assert(resolve({ text: "", fallback: "ar" }) === "ar", `T8b: empty+ar=ar`);
  assert(resolve({ text: null, fallback: "ar" }) === "ar", `T8c: null+ar=ar`);
}

// -----------------------------------------------------------------------
// T9: explicit language override always wins, even for letterless text.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "929", fallback: "en", explicit: "ar" });
  assert(r === "ar", `T9: explicit=ar dominates fallback=en for letterless; got ${r}`);
}

// -----------------------------------------------------------------------
// T10: the fix must work WITHOUT the caller passing
// `preferFallbackForLowSignalText: true`. The flag used to be required
// to get fallback inheritance on letterless turns, but we've tightened
// the rule so it's unconditional. Any caller that used to pass the
// flag still gets the same answer; callers that didn't now get the
// correct answer instead of a random one from
// `detectConversationLanguage`.
// -----------------------------------------------------------------------
{
  const r = resolve({ text: "929", fallback: "ar", lowSignal: false });
  assert(
    r === "ar",
    `T10: letterless inherits fallback even without lowSignal flag; got ${r}`,
  );
}

// -----------------------------------------------------------------------
// Script-mode stability (2026-04-19 22:08 incident)
//
// `resolveCustomerScriptMode` is the sibling resolver that picks
// Arabic-script vs English-script reply rendering. It has the same
// letterless-stability obligation: a bare number like "99338566" must
// NOT flip the conversation's script mode. Before the fix the function
// fell through its single-script branches and defaulted to `"arabic"`
// on any letterless input, producing English→Arabic script flips after
// the customer sent a bare phone number.
//
// S1–S9 mirror T1–T9 above for the script-mode resolver.
// -----------------------------------------------------------------------

// S1: letterless + fallback=en → english
{
  const r = resolveScript({ text: "929", fallback: "en" });
  assert(r === "english", `S1: "929" with fallback=en must stay english; got ${r}`);
}

// S2: letterless + fallback=ar → arabic
{
  const r = resolveScript({ text: "929", fallback: "ar" });
  assert(r === "arabic", `S2: "929" with fallback=ar must stay arabic; got ${r}`);
}

// S3: digits + punctuation + fallback=en → english
{
  const r = resolveScript({ text: "  929.  ", fallback: "en" });
  assert(r === "english", `S3: "  929.  " with fallback=en must stay english; got ${r}`);
}

// S4: emoji-only + fallback=en → english
{
  const r = resolveScript({ text: "👍👍", fallback: "en" });
  assert(r === "english", `S4: emoji-only with fallback=en must stay english; got ${r}`);
}

// S5: Latin text → english regardless of fallback
{
  const r = resolveScript({ text: "hello", fallback: "ar" });
  assert(r === "english", `S5: "hello" with fallback=ar must still be english; got ${r}`);
}

// S6: Arabic text → arabic regardless of fallback
{
  const r = resolveScript({ text: "مرحبا", fallback: "en" });
  assert(r === "arabic", `S6: Arabic text with fallback=en must be arabic; got ${r}`);
}

// S7: Arabizi → english (Kuwaiti customers prefer English replies over
// back-transliterated Arabizi; see `resolveCustomerScriptMode` docs).
{
  const r = resolveScript({ text: "shlonkm", fallback: "ar" });
  assert(r === "english", `S7: Arabizi "shlonkm" must route to english; got ${r}`);
}

// S8: empty text → fallback
{
  assert(resolveScript({ text: "", fallback: "en" }) === "english", `S8a: empty+en=english`);
  assert(resolveScript({ text: "", fallback: "ar" }) === "arabic", `S8b: empty+ar=arabic`);
  assert(resolveScript({ text: null, fallback: "ar" }) === "arabic", `S8c: null+ar=arabic`);
}

// S9: regression anchor for the 2026-04-19 22:08 incident —
// customer sent "99338566" (bare phone digits) in an English
// conversation, bot replied in Arabic ("أرسل اسم المستلم ورقمه.").
{
  const r = resolveScript({ text: "99338566", fallback: "en" });
  assert(
    r === "english",
    `S9: bare phone "99338566" with fallback=en must stay english (2026-04-19 22:08 regression); got ${r}`,
  );
}

// S10: mixed-script still prefers arabic unless explicit english (the
// legacy "mixed-script default" branch must still fire on real mixed
// content, just not on letterless).
{
  const r = resolveScript({ text: "اسمي John", fallback: "en" });
  assert(r === "arabic", `S10: mixed-script defaults to arabic; got ${r}`);
  const rEn = resolveScript({ text: "اسمي John", fallback: "en", explicit: "en" });
  assert(rEn === "english", `S10b: explicit=en dominates on mixed-script; got ${rEn}`);
}

console.log("smoke-test-letterless-language-stability: OK");
