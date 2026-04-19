// Learned-aliases file I/O and merge. Kept in a separate module so it can be
// unit-tested without pulling in the OpenAI resolver or the entire pricing
// pipeline.
//
// File contract
// -------------
// - Path: env RIDERS_PRICING_LEARNED_ALIASES_PATH, else `<resolver-overlay-dir>/pricing.resolver.learned-aliases.json`.
// - Schema: { _meta: { version, last_updated_at }, aliases: [...] }
// - Idempotent writes: if an identical alias row already exists (same alias
//   + same area_id), we do NOT append a duplicate.
// - Collision protection: if the alias-normalized key already resolves to a
//   DIFFERENT area via the main overlay/catalog, we reject the write.
//   This is the SAME guarantee we have for hand-curated aliases.

import { promises as fs } from "fs";
import * as path from "path";

import {
  emptyLearnedAliasesFile,
  type LearnedAliasesFile,
  type LlmAreaConfidence,
} from "./llm-area-resolver";

export function resolveLearnedAliasesPath(): string | null {
  const explicit = process.env.RIDERS_PRICING_LEARNED_ALIASES_PATH?.trim();
  if (explicit) return explicit;
  const overlayPath = process.env.RIDERS_PRICING_RESOLVER_OVERLAY_PATH?.trim();
  if (!overlayPath) return null;
  const dir = path.dirname(overlayPath);
  return path.join(dir, "pricing.resolver.learned-aliases.json");
}

export async function loadLearnedAliasesFile(
  filePath: string | null = resolveLearnedAliasesPath(),
): Promise<LearnedAliasesFile> {
  if (!filePath) return emptyLearnedAliasesFile();
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    const parsed = JSON.parse(raw) as Partial<LearnedAliasesFile>;
    if (!parsed || typeof parsed !== "object") return emptyLearnedAliasesFile();
    if (!Array.isArray(parsed.aliases)) return emptyLearnedAliasesFile();
    return {
      _meta: parsed._meta || { version: 1, last_updated_at: null },
      aliases: parsed.aliases.filter(
        (a: any) =>
          a &&
          typeof a === "object" &&
          typeof a.alias === "string" &&
          typeof a.area_id === "number",
      ) as LearnedAliasesFile["aliases"],
    };
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return emptyLearnedAliasesFile();
    }
    throw err;
  }
}

export interface AppendLearnedAliasInput {
  alias: string;
  area_id: number;
  model: string | null;
  confidence: LlmAreaConfidence;
  conversation_id: string | null;
  reasoning: string;
}

export interface AppendLearnedAliasResult {
  written: boolean;
  reason?: string;
  file_path: string | null;
  total_aliases_after: number;
}

// Append a new learned alias. Fully idempotent — if the exact (alias,area_id)
// pair already exists, we skip the write.
export async function appendLearnedAlias(
  input: AppendLearnedAliasInput,
  filePath: string | null = resolveLearnedAliasesPath(),
): Promise<AppendLearnedAliasResult> {
  if (!filePath) {
    return {
      written: false,
      reason: "no_learned_aliases_path",
      file_path: null,
      total_aliases_after: 0,
    };
  }
  const alias = (input.alias || "").trim();
  if (!alias) {
    return {
      written: false,
      reason: "empty_alias",
      file_path: filePath,
      total_aliases_after: 0,
    };
  }

  const current = await loadLearnedAliasesFile(filePath);
  const existsAlready = current.aliases.some(
    (a) => a.alias.trim().toLowerCase() === alias.toLowerCase() && a.area_id === input.area_id,
  );
  if (existsAlready) {
    return {
      written: false,
      reason: "already_learned",
      file_path: filePath,
      total_aliases_after: current.aliases.length,
    };
  }

  // Collision guard: another learned alias with the same normalized string
  // but a DIFFERENT area_id would create an ambiguous lookup. Refuse it.
  const conflict = current.aliases.find(
    (a) =>
      a.alias.trim().toLowerCase() === alias.toLowerCase() && a.area_id !== input.area_id,
  );
  if (conflict) {
    return {
      written: false,
      reason: `conflicts_with_existing_learned:area_${conflict.area_id}`,
      file_path: filePath,
      total_aliases_after: current.aliases.length,
    };
  }

  current.aliases.push({
    alias,
    area_id: input.area_id,
    _source: "llm_learned",
    _learned_at: new Date().toISOString(),
    _model: input.model,
    _confidence: input.confidence,
    _conversation_id: input.conversation_id,
    _reasoning: input.reasoning,
  });
  current._meta = {
    version: 1,
    last_updated_at: new Date().toISOString(),
  };

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  // Atomic-ish write: write-temp + rename. Not crash-safe across a power
  // failure, but good enough for a learn-back file that can always be
  // rebuilt from logs.
  const tmp = `${filePath}.tmp-${process.pid}-${Date.now()}`;
  await fs.writeFile(tmp, JSON.stringify(current, null, 2), "utf-8");
  await fs.rename(tmp, filePath);

  return {
    written: true,
    file_path: filePath,
    total_aliases_after: current.aliases.length,
  };
}
