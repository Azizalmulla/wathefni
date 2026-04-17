// ---------------------------------------------------------------------------
// Wave 1b extraction: pure behavior-policy normalization helpers.
// Extracted from `plugins/riders-tools/index.ts`. The state-backed loaders
// (`loadBehaviorPolicy`, `writePublishedBehaviorPolicy`, `clearBehaviorPolicyCache`,
// `getBehaviorPolicyStatus`) remain in `index.ts` for now because they
// touch module-scope cache + path-override bindings; those will move in a
// follow-up wave 1b commit once a small `createBehaviorPolicyStore()` factory
// is introduced. The helpers below are deterministic transformations only.
// ---------------------------------------------------------------------------

import { createHash } from "node:crypto";
import { isRecord } from "./google-sheets";
import type {
  BehaviorFlowRule,
  BehaviorLanguageScope,
  BehaviorPhraseGuard,
  BehaviorPolicy,
  BehaviorReplyCorrection,
} from "./types";

export function asOptionalTrimmedString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function parseJsonInput(label: string, raw: string) {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error(`${label} must not be empty.`);
  }

  try {
    return JSON.parse(trimmed) as unknown;
  } catch (err) {
    throw new Error(
      `Invalid JSON in ${label}: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

export function createEmptyBehaviorPolicy(): BehaviorPolicy {
  return {
    version: 1,
    last_updated: "",
    updated_by: null,
    summary: "",
    live_instructions: [],
    reply_corrections: [],
    flow_rules: [],
    phrase_guards: [],
  };
}

export function normalizeBehaviorPriority(value: unknown, fallback = 100) {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return Math.max(1, Math.trunc(numeric));
}

export function getNextBehaviorPriority<T extends { priority: number }>(
  rules: T[],
) {
  if (rules.length === 0) {
    return 100;
  }
  const currentMin = rules.reduce(
    (min, rule) => Math.min(min, normalizeBehaviorPriority(rule.priority)),
    100,
  );
  return Math.max(1, currentMin - 1);
}

export function normalizeBehaviorLanguageScope(
  value: unknown,
): BehaviorLanguageScope {
  return value === "arabic" || value === "english" ? value : "any";
}

export function createBehaviorRuleId(prefix: string, seed: unknown) {
  return `${prefix}_${createHash("sha1")
    .update(JSON.stringify([prefix, seed, Date.now()]))
    .digest("hex")
    .slice(0, 12)}`;
}

export function normalizeBehaviorEnabled(value: unknown) {
  return typeof value === "boolean" ? value : true;
}

export function normalizeBehaviorStringArray(
  value: unknown,
  fieldName: string,
) {
  if (!Array.isArray(value)) {
    throw new Error(`${fieldName} must be an array.`);
  }
  const values = value
    .map((entry) => asOptionalTrimmedString(entry))
    .filter((entry): entry is string => Boolean(entry));
  if (values.length === 0) {
    throw new Error(`${fieldName} must contain at least one non-empty string.`);
  }
  return values;
}

export function normalizeBehaviorReplyCorrection(
  value: unknown,
  seed: unknown,
): BehaviorReplyCorrection {
  if (!isRecord(value)) {
    throw new Error("Each reply correction must be an object.");
  }
  const title =
    asOptionalTrimmedString(value.title) ||
    asOptionalTrimmedString(value.situation);
  const situation = asOptionalTrimmedString(value.situation);
  const preferredReply = asOptionalTrimmedString(value.preferred_reply);
  if (!title) {
    throw new Error("Behavior reply correction title is required.");
  }
  if (!situation) {
    throw new Error("Behavior reply correction situation is required.");
  }
  if (!preferredReply) {
    throw new Error("Behavior reply correction preferred_reply is required.");
  }
  return {
    id:
      asOptionalTrimmedString(value.id) ||
      createBehaviorRuleId("reply", [seed, title, situation, preferredReply]),
    title,
    situation,
    preferred_reply: preferredReply,
    wrong_reply: asOptionalTrimmedString(value.wrong_reply),
    guidance: asOptionalTrimmedString(value.guidance),
    language_scope: normalizeBehaviorLanguageScope(value.language_scope),
    priority: normalizeBehaviorPriority(value.priority),
    enabled: normalizeBehaviorEnabled(value.enabled),
  };
}

export function normalizeBehaviorFlowRule(
  value: unknown,
  seed: unknown,
): BehaviorFlowRule {
  if (!isRecord(value)) {
    throw new Error("Each flow rule must be an object.");
  }
  const title =
    asOptionalTrimmedString(value.title) ||
    asOptionalTrimmedString(value.situation);
  const situation = asOptionalTrimmedString(value.situation);
  const requiredSteps = normalizeBehaviorStringArray(
    value.required_steps,
    "required_steps",
  );
  if (!title) {
    throw new Error("Behavior flow rule title is required.");
  }
  if (!situation) {
    throw new Error("Behavior flow rule situation is required.");
  }
  return {
    id:
      asOptionalTrimmedString(value.id) ||
      createBehaviorRuleId("flow", [seed, title, situation, requiredSteps]),
    title,
    situation,
    required_steps: requiredSteps,
    guidance: asOptionalTrimmedString(value.guidance),
    priority: normalizeBehaviorPriority(value.priority),
    enabled: normalizeBehaviorEnabled(value.enabled),
  };
}

export function normalizeBehaviorPhraseGuard(
  value: unknown,
  seed: unknown,
): BehaviorPhraseGuard {
  if (!isRecord(value)) {
    throw new Error("Each phrase guard must be an object.");
  }
  const rawKind = asOptionalTrimmedString(value.kind);
  if (rawKind !== "blocked" && rawKind !== "required") {
    throw new Error(
      "Behavior phrase guard kind must be either blocked or required.",
    );
  }
  const phrase = asOptionalTrimmedString(value.phrase);
  if (!phrase) {
    throw new Error("Behavior phrase guard phrase is required.");
  }
  return {
    id:
      asOptionalTrimmedString(value.id) ||
      createBehaviorRuleId("phrase", [seed, rawKind, phrase, value.applies_when]),
    kind: rawKind,
    phrase,
    applies_when: asOptionalTrimmedString(value.applies_when),
    guidance: asOptionalTrimmedString(value.guidance),
    priority: normalizeBehaviorPriority(value.priority),
    enabled: normalizeBehaviorEnabled(value.enabled),
  };
}

export function sortBehaviorRules<
  T extends { priority: number; id: string },
>(rules: T[]) {
  return [...rules].sort(
    (left, right) =>
      left.priority - right.priority || left.id.localeCompare(right.id),
  );
}

export function normalizeBehaviorPolicyDocument(
  raw: unknown,
  basePolicy?: BehaviorPolicy,
): BehaviorPolicy {
  const base = basePolicy || createEmptyBehaviorPolicy();
  if (raw === null || raw === undefined) {
    return {
      ...base,
      live_instructions: base.live_instructions,
      reply_corrections: sortBehaviorRules(base.reply_corrections),
      flow_rules: sortBehaviorRules(base.flow_rules),
      phrase_guards: sortBehaviorRules(base.phrase_guards),
    };
  }
  if (!isRecord(raw)) {
    throw new Error("Behavior policy must be an object.");
  }
  const liveInstructionsRaw = raw.live_instructions;
  const replyCorrectionsRaw = raw.reply_corrections;
  const flowRulesRaw = raw.flow_rules;
  const phraseGuardsRaw = raw.phrase_guards;
  if (liveInstructionsRaw !== undefined && !Array.isArray(liveInstructionsRaw)) {
    throw new Error("live_instructions must be an array when provided.");
  }
  if (replyCorrectionsRaw !== undefined && !Array.isArray(replyCorrectionsRaw)) {
    throw new Error("reply_corrections must be an array when provided.");
  }
  if (flowRulesRaw !== undefined && !Array.isArray(flowRulesRaw)) {
    throw new Error("flow_rules must be an array when provided.");
  }
  if (phraseGuardsRaw !== undefined && !Array.isArray(phraseGuardsRaw)) {
    throw new Error("phrase_guards must be an array when provided.");
  }
  const liveInstructions = (liveInstructionsRaw ?? base.live_instructions)
    .map((instruction) => asOptionalTrimmedString(instruction))
    .filter((instruction): instruction is string => Boolean(instruction));
  const replyCorrections = (replyCorrectionsRaw ?? base.reply_corrections).map(
    (rule, index) => normalizeBehaviorReplyCorrection(rule, index),
  );
  const flowRules = (flowRulesRaw ?? base.flow_rules).map((rule, index) =>
    normalizeBehaviorFlowRule(rule, index),
  );
  const phraseGuards = (phraseGuardsRaw ?? base.phrase_guards).map(
    (rule, index) => normalizeBehaviorPhraseGuard(rule, index),
  );
  return {
    version: Math.max(
      1,
      Math.trunc(Number(raw.version ?? base.version) || base.version || 1),
    ),
    last_updated:
      asOptionalTrimmedString(raw.last_updated) || base.last_updated,
    updated_by: asOptionalTrimmedString(raw.updated_by) || base.updated_by,
    summary: asOptionalTrimmedString(raw.summary) || base.summary,
    live_instructions: liveInstructions,
    reply_corrections: sortBehaviorRules(replyCorrections),
    flow_rules: sortBehaviorRules(flowRules),
    phrase_guards: sortBehaviorRules(phraseGuards),
  };
}

export function buildNextBehaviorPolicy(
  policy: BehaviorPolicy,
  currentPolicy: BehaviorPolicy,
  senderId: string | null | undefined,
  normalizeAdminSenderId: (value: string | null | undefined) => string,
) {
  const hasCurrentContent =
    Boolean(currentPolicy.last_updated) ||
    currentPolicy.live_instructions.length > 0 ||
    currentPolicy.reply_corrections.length > 0 ||
    currentPolicy.flow_rules.length > 0 ||
    currentPolicy.phrase_guards.length > 0 ||
    Boolean(currentPolicy.summary);
  return {
    ...policy,
    version: hasCurrentContent
      ? Math.max(1, currentPolicy.version) + 1
      : 1,
    last_updated: new Date().toISOString(),
    updated_by: normalizeAdminSenderId(senderId) || null,
    summary: policy.summary.trim(),
    live_instructions: policy.live_instructions
      .map((instruction) => instruction.trim())
      .filter(Boolean),
    reply_corrections: sortBehaviorRules(policy.reply_corrections),
    flow_rules: sortBehaviorRules(policy.flow_rules),
    phrase_guards: sortBehaviorRules(policy.phrase_guards),
  };
}

export function resolveBehaviorPolicyInput(params: {
  policy?: unknown;
  policy_json?: string | null;
}) {
  if (isRecord(params.policy)) {
    return params.policy;
  }
  if (typeof params.policy_json === "string" && params.policy_json.trim()) {
    const parsed = parseJsonInput("policy_json", params.policy_json);
    if (!isRecord(parsed)) {
      throw new Error("policy_json must decode to an object.");
    }
    return parsed;
  }
  throw new Error("Either policy or policy_json must be provided.");
}

export function resolveBehaviorRequiredStepsInput(params: {
  required_steps?: unknown;
  required_steps_json?: string | null;
}) {
  if (Array.isArray(params.required_steps)) {
    return normalizeBehaviorStringArray(params.required_steps, "required_steps");
  }
  if (
    typeof params.required_steps_json === "string" &&
    params.required_steps_json.trim()
  ) {
    const parsed = parseJsonInput(
      "required_steps_json",
      params.required_steps_json,
    );
    return normalizeBehaviorStringArray(parsed, "required_steps_json");
  }
  throw new Error(
    "Either required_steps or required_steps_json must be provided.",
  );
}

export function resolveBehaviorLiveInstructionsInput(params: {
  live_instructions?: unknown;
  live_instructions_json?: string | null;
  clear?: boolean | null;
}) {
  if (params.clear) {
    return [] as string[];
  }
  if (Array.isArray(params.live_instructions)) {
    return params.live_instructions
      .map((entry) => asOptionalTrimmedString(entry))
      .filter((entry): entry is string => Boolean(entry));
  }
  if (
    typeof params.live_instructions_json === "string" &&
    params.live_instructions_json.trim()
  ) {
    const parsed = parseJsonInput(
      "live_instructions_json",
      params.live_instructions_json,
    );
    if (!Array.isArray(parsed)) {
      throw new Error("live_instructions_json must decode to an array.");
    }
    return parsed
      .map((entry) => asOptionalTrimmedString(entry))
      .filter((entry): entry is string => Boolean(entry));
  }
  throw new Error(
    "Either live_instructions/live_instructions_json must be provided, or clear=true.",
  );
}

export function findBehaviorRuleLocation(policy: BehaviorPolicy, ruleId: string) {
  const normalizedRuleId = ruleId.trim();
  const replyCorrectionIndex = policy.reply_corrections.findIndex(
    (rule) => rule.id === normalizedRuleId,
  );
  if (replyCorrectionIndex >= 0) {
    return {
      collection: "reply_corrections" as const,
      index: replyCorrectionIndex,
    };
  }
  const flowRuleIndex = policy.flow_rules.findIndex(
    (rule) => rule.id === normalizedRuleId,
  );
  if (flowRuleIndex >= 0) {
    return { collection: "flow_rules" as const, index: flowRuleIndex };
  }
  const phraseGuardIndex = policy.phrase_guards.findIndex(
    (rule) => rule.id === normalizedRuleId,
  );
  if (phraseGuardIndex >= 0) {
    return { collection: "phrase_guards" as const, index: phraseGuardIndex };
  }
  return null;
}
