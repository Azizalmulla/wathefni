// ---------------------------------------------------------------------------
// Wave 3 extraction: customer profile read/sanitize helpers.
// Splits into:
//   - pure helpers (`looksLikeSavedPhoneValue`, `hasSavedAddressEvidence`,
//     `isSuspiciousSavedOrder`, `sanitizeCustomerProfile`,
//     `formatCustomerMemoryValue`) that depend only on the already-extracted
//     normalize helpers, and
//   - a small `createCustomerProfileStore({ memoryDir })` factory that owns
//     the path join + filesystem read, so the caller in `index.ts` no longer
//     has to weave `RIDERS_CUSTOMER_MEMORY_DIR` through every caller.
// Extracted from `plugins/octopus-channel/index.ts`.
// ---------------------------------------------------------------------------

import fs from "node:fs/promises";
import path from "node:path";
import { asTrimmedString, normalizePhone } from "./normalize";
import { safeJsonParse } from "./session-helpers";
import {
  formatSanitizerDrops,
  sanitizeSavedOrder,
  type SanitizationDrop,
} from "../../shared/persisted-state-sanitizer.js";
import type {
  CustomerProfile,
  SavedAddress,
  SavedCustomerOrder,
} from "./types";

export function looksLikeSavedPhoneValue(value: string | null | undefined): boolean {
  if (typeof value !== "string") {
    return false;
  }
  const normalized = value.replace(/[^\d+]/g, "").replace(/^\+/, "");
  return /^\d{7,20}$/.test(normalized);
}

export function hasSavedAddressEvidence(address: SavedAddress | null | undefined): boolean {
  return Boolean(
    asTrimmedString(address?.house) ||
      asTrimmedString(address?.avenue) ||
      (typeof address?.notes === "string" && address.notes.trim()),
  );
}

export function isSuspiciousSavedOrder(
  order: SavedCustomerOrder | null | undefined,
  customerWhatsapp: string | null | undefined,
): boolean {
  if (!order) {
    return false;
  }
  const senderName = asTrimmedString(order.sender?.name);
  const recipientName = asTrimmedString(order.recipient?.name);
  const senderPhone = normalizePhone(order.sender?.phone);
  const recipientPhone = normalizePhone(order.recipient?.phone);
  const customerPhone = normalizePhone(customerWhatsapp);
  const bothNamesLookWrong =
    !senderName ||
    !recipientName ||
    looksLikeSavedPhoneValue(senderName) ||
    looksLikeSavedPhoneValue(recipientName);
  const bothPhonesMatchCustomer =
    Boolean(customerPhone) &&
    senderPhone === customerPhone &&
    recipientPhone === customerPhone;
  const missingAddressEvidence =
    !hasSavedAddressEvidence(order.pickup) ||
    !hasSavedAddressEvidence(order.delivery);
  return bothNamesLookWrong && bothPhonesMatchCustomer && missingAddressEvidence;
}

export function sanitizeCustomerProfile(profile: CustomerProfile | null): CustomerProfile | null {
  if (!profile) {
    return null;
  }
  if (!isSuspiciousSavedOrder(profile.last_successful_order, profile.customer_whatsapp)) {
    return profile;
  }
  return {
    ...profile,
    last_successful_order: null,
  };
}

export function formatCustomerMemoryValue(value: unknown): string {
  return asTrimmedString(typeof value === "string" ? value : value == null ? "" : String(value)) || "-";
}

export type CustomerProfileStoreOptions = {
  memoryDir: string;
};

export type CustomerProfileStore = {
  getPath(replyTarget: string | null): string | null;
  load(replyTarget: string | null): Promise<CustomerProfile | null>;
};

export function createCustomerProfileStore(
  options: CustomerProfileStoreOptions,
): CustomerProfileStore {
  const { memoryDir } = options;

  function getPath(replyTarget: string | null): string | null {
    const normalizedReplyTarget = normalizePhone(replyTarget);
    if (!normalizedReplyTarget) {
      return null;
    }
    return path.join(memoryDir, `${normalizedReplyTarget.replace(/^\+/, "")}.json`);
  }

  async function load(replyTarget: string | null): Promise<CustomerProfile | null> {
    const profilePath = getPath(replyTarget);
    if (!profilePath) {
      return null;
    }
    // Hashed phone id for metric correlation without leaking raw numbers
    // into logs. Last 4 digits of the normalized reply target — enough to
    // spot "same customer hitting repeatedly" without PII exposure.
    const phoneTail = (replyTarget || "").replace(/[^\d]/g, "").slice(-4) || "unknown";
    try {
      const raw = await fs.readFile(profilePath, "utf-8");
      const parsed = safeJsonParse(raw);
      if (!parsed || typeof parsed !== "object") {
        try {
          console.log(`[metric] memory.profile_load hit=false reason=unparseable phone_tail=${phoneTail}`);
        } catch {}
        return null;
      }
      const profile = parsed as CustomerProfile;
      try {
        const hasLastOrder = profile.last_successful_order ? "true" : "false";
        console.log(`[metric] memory.profile_load hit=true has_last_order=${hasLastOrder} phone_tail=${phoneTail}`);
      } catch {}
      // (1) Coarse legacy sanitizer — wipes the WHOLE saved order when it's
      // structurally junk (both names look like phones, etc.). Kept for
      // backwards compatibility.
      const coarse = sanitizeCustomerProfile(profile);
      const coarseDroppedOrder =
        coarse &&
        profile.last_successful_order &&
        !coarse.last_successful_order;
      // (2) Per-field sanitizer — catches the common case where the
      // saved order is MOSTLY valid but one field (e.g.
      // `sender.name = "Is this the cheapest option"`) was written by
      // pre-fix code. These corrupt-in-place fields don't trip the
      // coarse check. Runs the same validators as the write path.
      const fieldResult = sanitizeSavedOrder(coarse?.last_successful_order ?? null);
      const fieldDrops: SanitizationDrop[] = fieldResult.drops;
      const sanitized: CustomerProfile | null = coarse
        ? { ...coarse, last_successful_order: fieldResult.value ?? null }
        : coarse;
      if (fieldDrops.length > 0) {
        // One structured line per load so ops can grep for it and
        // measure historical corruption in the wild.
        try {
          console.warn(
            `[sanitizer] customer_profile path=${profilePath} drops=${fieldDrops.length} ${formatSanitizerDrops(fieldDrops)}`,
          );
        } catch {}
      }
      // Persist the cleaned profile back if EITHER sanitizer path changed
      // anything — so the next read is clean even without the fix in place,
      // and so telemetry doesn't spam the same drops turn after turn.
      if (coarseDroppedOrder || fieldDrops.length > 0) {
        await fs.writeFile(profilePath, `${JSON.stringify(sanitized, null, 2)}\n`, "utf-8");
      }
      return sanitized;
    } catch (error) {
      const code =
        error && typeof error === "object" && "code" in error
          ? String((error as { code?: unknown }).code || "")
          : "";
      if (code === "ENOENT") {
        try {
          console.log(`[metric] memory.profile_load hit=false reason=no_file phone_tail=${phoneTail}`);
        } catch {}
        return null;
      }
      throw error;
    }
  }

  return {
    getPath,
    load,
  };
}
