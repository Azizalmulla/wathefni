// ---------------------------------------------------------------------------
// Wave 3 extraction: ingress ledger factory.
// Owns the on-disk dedupe/replay ledger for WhatsApp ingress events. The
// factory encapsulates:
//   - the serialized mutation queue (previously a module-scoped `let` binding)
//   - the persistence path + retention/cap policy (constants)
//   - the load / save / mutate / upsert / update / persist-accepted pipeline
//
// Extracted from `plugins/octopus-channel/index.ts`. `index.ts` now builds a
// single ledger instance at boot and uses its methods; no caller elsewhere has
// direct access to the mutation queue or to the raw load/save helpers, which
// eliminates the risk of parallel mutators racing on the state file.
// ---------------------------------------------------------------------------

import fs from "node:fs/promises";
import path from "node:path";
import type {
  IngressLedgerState,
  IngressLedgerStatus,
  PersistedIngressLedgerEntry,
} from "./types";
import { isTerminalIngressStatus } from "./webhook";

export type IngressLedgerOptions = {
  ledgerPath: string;
  retentionMs: number;
  maxEntries: number;
};

export type IngressLedger = {
  load(): Promise<IngressLedgerState>;
  mutate<T>(
    mutator: (state: IngressLedgerState) => Promise<T> | T,
  ): Promise<T>;
  upsert(entry: PersistedIngressLedgerEntry): Promise<void>;
  update(
    ingressIds: string[] | null | undefined,
    updater: (entry: PersistedIngressLedgerEntry) => PersistedIngressLedgerEntry,
  ): Promise<void>;
  persistAccepted(entry: PersistedIngressLedgerEntry): Promise<{
    duplicate: boolean;
    existingStatus: IngressLedgerStatus | null;
  }>;
};

export function createIngressLedger(options: IngressLedgerOptions): IngressLedger {
  const { ledgerPath, retentionMs, maxEntries } = options;

  async function load(): Promise<IngressLedgerState> {
    try {
      const raw = await fs.readFile(ledgerPath, "utf-8");
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? (parsed as IngressLedgerState) : {};
    } catch {
      return {};
    }
  }

  function prune(state: IngressLedgerState): void {
    const now = Date.now();
    for (const [key, entry] of Object.entries(state)) {
      const updatedAt = Date.parse(entry.lastUpdatedAt || entry.receivedAt || "");
      if (Number.isFinite(updatedAt) && (now - updatedAt) > retentionMs) {
        delete state[key];
      }
    }
    const keys = Object.keys(state);
    if (keys.length <= maxEntries) {
      return;
    }
    const keep = keys
      .map((key) => ({
        key,
        updatedAt: Date.parse(state[key]?.lastUpdatedAt || state[key]?.receivedAt || "") || 0,
      }))
      .sort((left, right) => right.updatedAt - left.updatedAt)
      .slice(0, maxEntries);
    const keepSet = new Set(keep.map((entry) => entry.key));
    for (const key of keys) {
      if (!keepSet.has(key)) {
        delete state[key];
      }
    }
  }

  async function save(state: IngressLedgerState): Promise<void> {
    try {
      prune(state);
      await fs.mkdir(path.dirname(ledgerPath), { recursive: true });
      await fs.writeFile(ledgerPath, JSON.stringify(state), "utf-8");
    } catch {
      // best-effort persistence
    }
  }

  let mutationQueue: Promise<void> = Promise.resolve();

  async function mutate<T>(
    mutator: (state: IngressLedgerState) => Promise<T> | T,
  ): Promise<T> {
    const previous = mutationQueue.catch(() => {});
    let releaseQueue: (() => void) | null = null;
    mutationQueue = new Promise<void>((resolve) => {
      releaseQueue = resolve;
    });
    await previous;
    try {
      const state = await load();
      const result = await mutator(state);
      await save(state);
      releaseQueue?.();
      return result;
    } catch (error) {
      releaseQueue?.();
      throw error;
    }
  }

  async function upsert(entry: PersistedIngressLedgerEntry): Promise<void> {
    await mutate(async (state) => {
      state[entry.ingressId] = entry;
    });
  }

  async function update(
    ingressIds: string[] | null | undefined,
    updater: (entry: PersistedIngressLedgerEntry) => PersistedIngressLedgerEntry,
  ): Promise<void> {
    const uniqueIds = Array.from(
      new Set((ingressIds || []).map((value) => String(value || "").trim()).filter(Boolean)),
    );
    if (uniqueIds.length === 0) {
      return;
    }
    await mutate(async (state) => {
      for (const ingressId of uniqueIds) {
        const existing = state[ingressId];
        if (!existing) {
          continue;
        }
        state[ingressId] = updater(existing);
      }
    });
  }

  async function persistAccepted(entry: PersistedIngressLedgerEntry): Promise<{
    duplicate: boolean;
    existingStatus: IngressLedgerStatus | null;
  }> {
    return await mutate(async (state) => {
      const existing = state[entry.ingressId];
      if (existing && isTerminalIngressStatus(existing.status)) {
        return {
          duplicate: true,
          existingStatus: existing.status,
        };
      }
      state[entry.ingressId] = entry;
      return {
        duplicate: false,
        existingStatus: existing?.status || null,
      };
    });
  }

  return {
    load,
    mutate,
    upsert,
    update,
    persistAccepted,
  };
}
