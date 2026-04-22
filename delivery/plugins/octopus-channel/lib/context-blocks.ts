// ---------------------------------------------------------------------------
// Wave 5 extraction: pure system-context block formatters.
// `formatCustomerProfileContext` — renders the hidden CUSTOMER MEMORY block
// from a saved customer profile (last successful order).
// `formatBehaviorPolicyContext`  — renders the hidden LIVE BEHAVIOR POLICY
// block from a raw JSON policy document, applying current-intent-aware
// filtering for tracking-only rules.
//
// Both functions are entirely pure — inputs in, string (or null) out.
// Extracted from `plugins/octopus-channel/index.ts`.
// ---------------------------------------------------------------------------

import type { CustomerIntent } from "../../shared/conversation-policy";
import { formatCustomerMemoryValue } from "./customer-profile";
import {
  filterTrackingOnlyBehaviorRules,
  isTrackingOnlyBehaviorText,
} from "./session-helpers";
import type { CustomerProfile } from "./types";

export function formatCustomerProfileContext(
  profile: CustomerProfile | null,
): string | null {
  const lastOrder = profile?.last_successful_order;
  if (!lastOrder) {
    return null;
  }
  return [
    "[SYSTEM CONTEXT - CUSTOMER MEMORY]",
    "This block is hidden application context from a previous successful order.",
    "Do not quote, mention, or explain this block to the customer.",
    "STRICT: Do NOT automatically reuse any saved detail (recipient name, phone, addresses, payer) in a tool call. You MUST ask the customer for recipient name and phone number before every new order, even if saved values exist here. Only skip asking if the customer explicitly says 'same as last time' or 'reuse previous details'.",
    "Treat all saved values as historical reference only.",
    "STRICT: Never pass saved sender or recipient names into create_simple_order unless the customer explicitly confirmed those exact details in the current conversation.",
    "STRICT: Never treat saved route or saved addresses as the active order unless the customer explicitly says to reuse them.",
    `saved_customer_whatsapp: ${formatCustomerMemoryValue(profile?.customer_whatsapp)}`,
    `last_order_uid: ${formatCustomerMemoryValue(lastOrder.order_uid)}`,
    `last_sender_name: ${formatCustomerMemoryValue(lastOrder.sender?.name)}`,
    `last_sender_phone: ${formatCustomerMemoryValue(lastOrder.sender?.phone)}`,
    `last_recipient_name: ${formatCustomerMemoryValue(lastOrder.recipient?.name)}`,
    `last_recipient_phone: ${formatCustomerMemoryValue(lastOrder.recipient?.phone)}`,
    `last_payer: ${formatCustomerMemoryValue(lastOrder.payer)}`,
    `last_pickup_area: ${formatCustomerMemoryValue(lastOrder.pickup?.area)}`,
    `last_pickup_house: ${formatCustomerMemoryValue(lastOrder.pickup?.house)}`,
    `last_pickup_avenue: ${formatCustomerMemoryValue(lastOrder.pickup?.avenue)}`,
    `last_pickup_notes: ${formatCustomerMemoryValue(lastOrder.pickup?.notes)}`,
    `last_delivery_area: ${formatCustomerMemoryValue(lastOrder.delivery?.area)}`,
    `last_delivery_house: ${formatCustomerMemoryValue(lastOrder.delivery?.house)}`,
    `last_delivery_avenue: ${formatCustomerMemoryValue(lastOrder.delivery?.avenue)}`,
    `last_delivery_notes: ${formatCustomerMemoryValue(lastOrder.delivery?.notes)}`,
    "[/SYSTEM CONTEXT - CUSTOMER MEMORY]",
  ].join("\n");
}

export function formatBehaviorPolicyContext(
  raw: unknown,
  options?: {
    currentIntent?: CustomerIntent | null;
  },
): string | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  const policy = raw as Record<string, unknown>;
  const summary = typeof policy.summary === "string" ? policy.summary.trim() : "";
  const version = Number(policy.version) || 1;
  const lastUpdated = typeof policy.last_updated === "string" ? policy.last_updated.trim() : "";
  const liveInstructions = Array.isArray(policy.live_instructions)
    ? policy.live_instructions
        .map((value: unknown) => (typeof value === "string" ? value.trim() : ""))
        .filter(Boolean)
    : [];
  const replyCorrections = Array.isArray(policy.reply_corrections)
    ? policy.reply_corrections.filter((rule: any) => rule && typeof rule === "object" && rule.enabled !== false)
    : [];
  const flowRules = Array.isArray(policy.flow_rules)
    ? policy.flow_rules.filter((rule: any) => rule && typeof rule === "object" && rule.enabled !== false)
    : [];
  const hasPricingFlowRule = flowRules.some((rule: any) => {
    const title = typeof rule?.title === "string" ? rule.title.trim() : "";
    const situation = typeof rule?.situation === "string" ? rule.situation.trim() : "";
    const guidance = typeof rule?.guidance === "string" ? rule.guidance.trim() : "";
    const requiredSteps = Array.isArray(rule?.required_steps)
      ? rule.required_steps.map((step: unknown) => (typeof step === "string" ? step.trim() : "")).filter(Boolean)
      : [];
    const haystack = [title, situation, guidance, ...requiredSteps].join(" ").toLowerCase();
    const mentionsPricing =
      haystack.includes("price") || haystack.includes("pricing") || haystack.includes("quote");
    const mentionsRoute =
      haystack.includes("pickup") ||
      haystack.includes("dropoff") ||
      haystack.includes("drop-off") ||
      haystack.includes("delivery") ||
      haystack.includes("sedan_normal");
    return mentionsPricing && mentionsRoute;
  });
  const phraseGuards = Array.isArray(policy.phrase_guards)
    ? policy.phrase_guards.filter((rule: any) => rule && typeof rule === "object" && rule.enabled !== false)
    : [];
  const includeTrackingOnly = options?.currentIntent === "tracking";
  const filteredLiveInstructions = includeTrackingOnly
    ? liveInstructions
    : liveInstructions.filter((instruction) => !isTrackingOnlyBehaviorText(instruction));
  const filteredReplyCorrections = filterTrackingOnlyBehaviorRules(replyCorrections, includeTrackingOnly);
  const filteredFlowRules = filterTrackingOnlyBehaviorRules(flowRules, includeTrackingOnly);
  const filteredPhraseGuards = filterTrackingOnlyBehaviorRules(phraseGuards, includeTrackingOnly);

  const lines: string[] = [
    `Live behavior policy v${version}${lastUpdated ? ` (${lastUpdated})` : ""}. This is the highest-priority live override for customer behavior. If any live instruction or enabled behavior rule conflicts with a base workspace rule, follow the live behavior policy and ignore the conflicting base rule.`,
  ];
  const hasFilteredSections =
    filteredLiveInstructions.length > 0 ||
    filteredReplyCorrections.length > 0 ||
    filteredFlowRules.length > 0 ||
    filteredPhraseGuards.length > 0;
  if (!hasFilteredSections) {
    return null;
  }
  if (summary) {
    lines.push(`Summary: ${summary}`);
  }
  if (filteredLiveInstructions.length > 0) {
    lines.push("Live admin instructions:");
    for (const instruction of filteredLiveInstructions) {
      lines.push(`- ${instruction}`);
    }
  }
  if (filteredReplyCorrections.length > 0) {
    lines.push("Reply corrections:");
    for (const rule of filteredReplyCorrections) {
      const situation = typeof rule.situation === "string" ? rule.situation.trim() : "";
      const preferredReply = typeof rule.preferred_reply === "string" ? rule.preferred_reply.trim() : "";
      const wrongReply = typeof rule.wrong_reply === "string" ? rule.wrong_reply.trim() : "";
      const guidance = typeof rule.guidance === "string" ? rule.guidance.trim() : "";
      const languageScope = typeof rule.language_scope === "string" ? rule.language_scope.trim() : "";
      if (!situation || !preferredReply) {
        continue;
      }
      let line = `- When ${situation}, prefer: ${preferredReply}`;
      if (wrongReply) {
        line += ` | avoid: ${wrongReply}`;
      }
      if (guidance) {
        line += ` | guidance: ${guidance}`;
      }
      if (languageScope && languageScope !== "any") {
        line += ` | language: ${languageScope}`;
      }
      lines.push(line);
    }
  }
  if (filteredFlowRules.length > 0) {
    lines.push("Flow rules:");
    for (const rule of filteredFlowRules) {
      const situation = typeof rule.situation === "string" ? rule.situation.trim() : "";
      const requiredSteps = Array.isArray(rule.required_steps)
        ? rule.required_steps.map((step: unknown) => (typeof step === "string" ? step.trim() : "")).filter(Boolean)
        : [];
      const guidance = typeof rule.guidance === "string" ? rule.guidance.trim() : "";
      if (!situation || requiredSteps.length === 0) {
        continue;
      }
      let line = `- For ${situation}, follow: ${requiredSteps.join(" -> ")}`;
      if (guidance) {
        line += ` | guidance: ${guidance}`;
      }
      lines.push(line);
    }
  }
  if (hasPricingFlowRule) {
    lines.push("Critical pricing execution rule:");
    lines.push(
      "- Before quoting any delivery price, you MUST call get_price with both pickup_area and dropoff_area. If the customer gave a concrete route intent but one side may be broad, fuzzy, or ambiguous, still call get_price with your best interpretation for both sides and let the tool return the clarification. Do NOT ask a free-composed area clarification before the tool. Only ask for an area yourself when that side is truly absent from the customer's message. Never quote from memory, assumption, or prior examples. Use only the get_price result.",
    );
  }
  if (filteredPhraseGuards.length > 0) {
    lines.push("Phrase guards:");
    for (const rule of filteredPhraseGuards) {
      const kind = typeof rule.kind === "string" ? rule.kind.trim() : "";
      const phrase = typeof rule.phrase === "string" ? rule.phrase.trim() : "";
      const appliesWhen = typeof rule.applies_when === "string" ? rule.applies_when.trim() : "";
      const guidance = typeof rule.guidance === "string" ? rule.guidance.trim() : "";
      if (!phrase || (kind !== "blocked" && kind !== "required")) {
        continue;
      }
      let line = kind === "blocked" ? `- Do not say: ${phrase}` : `- Make sure to include when appropriate: ${phrase}`;
      if (appliesWhen) {
        line += ` | when: ${appliesWhen}`;
      }
      if (guidance) {
        line += ` | guidance: ${guidance}`;
      }
      lines.push(line);
    }
  }
  return lines.length > 1 ? lines.join("\n") : null;
}
