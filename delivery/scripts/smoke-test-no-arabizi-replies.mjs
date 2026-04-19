#!/usr/bin/env node
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const mod = await loadTsModule("plugins/shared/conversation-policy.ts");
const { resolveCustomerScriptMode, resolveCustomerReplyLanguage } = mod;

const cases = [
  { label: "pure English",    text: "salmiya to hawalli please", expectScript: "english",  expectLang: "en" },
  { label: "pure Arabic",     text: "بكم التوصيل من حولي الى سلوى", expectScript: "arabic", expectLang: "ar" },
  { label: "Arabizi digits",  text: "slam 3laikm bkm il tws6eel", expectScript: "english", expectLang: "en" },
  { label: "Arabizi words",   text: "hala shlonkm",               expectScript: "english", expectLang: "en" },
  { label: "Arabizi Jlai3a",  text: "Jlai3a to wafra",            expectScript: "english", expectLang: "en" },
  { label: "plain Latin",     text: "salmiya to hawalli",         expectScript: "english", expectLang: "en" },
  { label: "empty fallback",  text: "",                           expectScript: "english", expectLang: "en" },
];

let failed = 0;
for (const c of cases) {
  const scriptMode = resolveCustomerScriptMode({ visibleText: c.text, explicitLanguage: null, fallbackLanguage: "en" });
  const replyLang = resolveCustomerReplyLanguage({ visibleText: c.text, explicitLanguage: null, fallbackLanguage: "en" });
  const scriptOk = scriptMode === c.expectScript;
  const langOk = replyLang === c.expectLang;
  const pass = scriptOk && langOk;
  if (!pass) failed++;
  console.log(
    `${pass ? "PASS" : "FAIL"}: ${c.label.padEnd(22)} scriptMode=${scriptMode} (expected ${c.expectScript})  replyLang=${replyLang} (expected ${c.expectLang})`,
  );
  if (scriptMode === "arabizi") {
    console.log("  ^^ scriptMode should NEVER be 'arabizi' after this change");
    failed++;
  }
}
console.log(failed === 0 ? "\nAll assertions passed." : `\n${failed} failure(s).`);
process.exit(failed === 0 ? 0 : 1);
