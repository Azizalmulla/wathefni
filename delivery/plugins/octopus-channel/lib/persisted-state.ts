// ---------------------------------------------------------------------------
// Wave 3 extraction: generic JSON state store factory.
// The octopus-channel plugin keeps four tiny `Record<string, ...>` state files
// on disk (inactivity, closed-conversation alerts, conversation controller,
// plus anything else in the future). All four use exactly the same
// "best-effort read-or-empty" / "best-effort write-or-ignore" pattern, so we
// factor that duplication into a single `createJsonStateStore` factory.
//
// Extracted from `plugins/octopus-channel/index.ts`. `index.ts` now calls
// `createJsonStateStore<T>(path)` once per state file and reuses the returned
// `{ load, save }` pair. Behavior is byte-identical to the previous inline
// helpers: missing/unreadable files yield `{}`, parse errors yield `{}`,
// write failures are swallowed.
// ---------------------------------------------------------------------------

import fs from "node:fs/promises";
import path from "node:path";

export type JsonStateStore<T extends Record<string, unknown>> = {
  load(): Promise<T>;
  save(state: T): Promise<void>;
};

export function createJsonStateStore<T extends Record<string, unknown>>(
  filePath: string,
): JsonStateStore<T> {
  async function load(): Promise<T> {
    try {
      const raw = await fs.readFile(filePath, "utf-8");
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? (parsed as T) : ({} as T);
    } catch {
      return {} as T;
    }
  }

  async function save(state: T): Promise<void> {
    try {
      await fs.mkdir(path.dirname(filePath), { recursive: true });
      await fs.writeFile(filePath, JSON.stringify(state), "utf-8");
    } catch {
      // best-effort persistence
    }
  }

  return { load, save };
}
