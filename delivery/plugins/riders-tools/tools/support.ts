// Customer support tools.
//
// Extracted from plugins/riders-tools/index.ts as part of Wave 1a of the
// surgical plugin split. Tool bodies are unchanged. Helpers come from
// deps.intentGates and deps.createTextResult / deps.errorPayload; the
// shared conversation-policy helpers are imported directly because they
// already live as a sibling module.
//
// Tools registered:
//   - complains
//   - assign_agent

import {
  extractTrackingOrderId,
  isBookingStartIntent,
  normalizeIntentText,
} from "../../shared/conversation-policy";

import {
  appendComplaint,
  COMPLAINT_CATEGORIES,
  type ComplaintCategory,
} from "../lib/complaint-store";

import type { ToolDeps } from "./deps";

export function registerCustomerSupportTools(api: any, deps: ToolDeps): void {
  const { intentGates } = deps;
  const {
    isCustomerOctopusContext,
    getVisibleCustomerText,
    getCustomerTurnActionHint,
    getNormalizedBookingAuthority,
    isActiveBookingFlow,
    customerExplicitlyRequestsHuman,
    assignAgentReasonLooksLegitimate,
    hasStrictTrackingOrderId,
  } = intentGates;

  // =========================================================================
  // TOOL: complains — persisted record (AI Octopus handoff still pending)
  //
  // Before 2026-04-24 this was a pure stub: logged "complaint received"
  // to the customer and threw the text away. That meant every admin
  // query of the form "customers who complained about X", "top complaint
  // categories this week", etc. was unanswerable for structural
  // reasons — not because we lacked a query engine, but because there
  // was nothing to query. This version closes that gap by writing a
  // structured record to disk via `complaint-store.ts` (daily JSONL
  // files under $HOME/.openclaw-${OPENCLAW_PROFILE}/complaints/). The
  // customer-facing message is unchanged; this is backend-only work.
  //
  // Handoff to a human is still a stub — `handoff_available: false`
  // and `escalation_status: "pending_integration"` stay true until the
  // AI Octopus `/client/conversation/toagent` integration lands. Do
  // not re-introduce any "forwarded to management" / "transferred to
  // support" phrasing in the message until that integration actually
  // routes to a human.
  // =========================================================================
  api.registerTool({
    name: "complains",
    label: "Record Complaint",
    description:
      "Persist a customer complaint to the admin-readable complaint log. Always include the customer's own words verbatim as `complaint_text`. Classify the complaint into the most specific `category` that fits (late_delivery, wrong_item, pricing, rude_driver, coverage, service_quality, damaged_item, order_not_received, other). The customer is told their complaint has been recorded — do not promise human follow-up.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        complaint_text: {
          type: "string",
          description: "The customer's complaint details as described by them (verbatim).",
        },
        order_id: {
          type: "string",
          description: "Related order ID if applicable.",
        },
        category: {
          type: "string",
          enum: [...COMPLAINT_CATEGORIES],
          description:
            "Best-fit category for this complaint. Pick 'other' only if nothing else applies.",
        },
      },
      required: ["complaint_text"],
    },

    async execute(
      _toolCallId: string,
      params: { complaint_text: string; order_id?: string; category?: string },
      ctx?: any,
    ) {
      const timestamp = new Date().toISOString();
      // Best-effort extract phone + conversation identifiers from the
      // customer-turn ctx. Fall back to nulls — we still want the
      // complaint text persisted even if we can't attribute it.
      const phone =
        (ctx?.replyTarget as string | undefined) ??
        (ctx?.ReplyTarget as string | undefined) ??
        (ctx?.SenderId as string | undefined) ??
        (ctx?.senderId as string | undefined) ??
        (ctx?.current_customer_whatsapp as string | undefined) ??
        null;
      const conversationId =
        (ctx?.conversationId as string | undefined) ??
        (ctx?.ConversationId as string | undefined) ??
        (ctx?.ConversationID as string | undefined) ??
        null;
      const accountId =
        (ctx?.accountId as string | undefined) ??
        (ctx?.AccountId as string | undefined) ??
        null;
      const category = (params.category || "other") as ComplaintCategory;

      let complaintId: string | null = null;
      try {
        const record = await appendComplaint({
          phone,
          conversation_id: conversationId,
          account_id: accountId,
          complaint_text: params.complaint_text,
          order_id: params.order_id || null,
          category,
        });
        complaintId = record.complaint_id;
        try {
          const tail = record.phone_tail;
          console.log(
            `[metric] complaint.recorded id=${record.complaint_id} category=${record.category} phone_tail=${tail} lang=${record.language} at=${record.recorded_at}`,
          );
        } catch {}
      } catch (err) {
        // Persistence failed (disk full, permission issue, etc.). Do
        // NOT fail the tool call — the customer still gets a truthful
        // acknowledgement. Log the failure so ops can notice.
        try {
          const message = err instanceof Error ? err.message : String(err);
          console.log(
            `[metric] complaint.persist_failed category=${category} error="${message.slice(0, 120).replace(/"/g, "'")}"`,
          );
        } catch {}
      }

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              status: "recorded",
              complaint_id: complaintId,
              complaint_text: params.complaint_text,
              order_id: params.order_id || null,
              category,
              recorded_at: timestamp,
              message: "تم تسجيل شكواك. سأحاول مساعدتك هنا، وسنراجعها.",
              handoff_available: false,
              escalation_status: "pending_integration",
            }),
          },
        ],
      };
    },
  });

  // =========================================================================
  // TOOL: assign_agent — STUB (AI Octopus escalation pending)
  // =========================================================================
  api.registerTool({
    name: "assign_agent",
    label: "Assign to Human Agent",
    description:
      "Transfer the current conversation to a human support agent. Use this for refunds, data modifications, system errors, job applications, or any case requiring human intervention.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        reason: {
          type: "string",
          description:
            "Brief reason for the handover (e.g. refund request, system error, job application)",
        },
      },
      required: ["reason"],
    },

    async execute(_toolCallId: string, params: { reason: string }, ctx?: any) {
      if (ctx && isCustomerOctopusContext(ctx)) {
        const visibleText = getVisibleCustomerText(ctx);
        const actionHint = getCustomerTurnActionHint(ctx);
        const bookingAuthority = getNormalizedBookingAuthority(ctx);
        const stageHint = bookingAuthority.stage;
        const bookingStepHint = bookingAuthority.bookingStep;
        const reason = String(params.reason || "");
        const explicitHumanRequest = customerExplicitlyRequestsHuman(visibleText);
        const interpreterWantsHandoff = actionHint === "handoff";
        const quotedBookingFollowup =
          stageHint === "quoted" &&
          (actionHint === "start booking" || isBookingStartIntent(visibleText));
        const activeBookingCollection = isActiveBookingFlow(stageHint, bookingStepHint);
        const trackingFallbackReason =
          normalizeIntentText(reason).includes("tracking") ||
          normalizeIntentText(reason).includes("order id") ||
          normalizeIntentText(reason).includes("order number");
        const hasVisibleTrackingId = hasStrictTrackingOrderId(
          extractTrackingOrderId(visibleText) || "",
        );
        if (
          (activeBookingCollection && !explicitHumanRequest && !interpreterWantsHandoff) ||
          (quotedBookingFollowup &&
            !explicitHumanRequest &&
            !assignAgentReasonLooksLegitimate(reason) &&
            !interpreterWantsHandoff) ||
          (actionHint === "tracking missing id" && !explicitHumanRequest) ||
          (actionHint === "booking step input" && !explicitHumanRequest) ||
          (trackingFallbackReason && !hasVisibleTrackingId && !explicitHumanRequest)
        ) {
          console.log(
            `[intent-gate-exec] blocked assign_agent intent=${actionHint} stage=${stageHint || "unknown"} bookingStep=${bookingStepHint || "unknown"}`,
          );
          try {
            console.log(
              `[metric] handoff.escalation outcome=blocked reason_kind=${actionHint || "unknown"} stage=${stageHint || "unknown"} booking_step=${bookingStepHint || "unknown"}`,
            );
          } catch {}
          throw new Error(
            "Do not escalate to a human here. Continue the current booking flow unless the customer explicitly asked for human support or there is a real unsupported/manual-confirmation/system-error case.",
          );
        }
      }

      const timestamp = new Date().toISOString();
      // NOTE: This is still the STUB escalation path — no real human is
      // assigned yet. The `[metric] handoff.escalation outcome=noted_stub`
      // line lets ops count how often the bot WOULD escalate today so
      // when the AI Octopus assign-to-agent integration lands, we have
      // baseline volume and can spot routing regressions.
      try {
        console.log(
          `[metric] handoff.escalation outcome=noted_stub reason="${(params.reason || "").slice(0, 80).replace(/"/g, "'")}" at=${timestamp}`,
        );
      } catch {}
      // Honest stub response (2026-04-24): previously returned
      // status=escalated + message "تم تحويل المحادثة لموظف الدعم" which
      // is a lie — no human receives the conversation until the AI
      // Octopus `/client/conversation/toagent` integration is wired.
      // Current shape is semantically accurate:
      //   - status: "noted" (not "escalated")
      //   - handoff_available: false (machine-readable truth for the LLM)
      //   - message: no transfer/wait claim, just acknowledgement
      // The LLM hard rules already tell it to answer the customer's
      // likely intent and offer one helpful next step, so it will
      // continue the conversation rather than telling the customer to
      // wait for a human that isn't coming.
      //
      // DO NOT re-introduce status=escalated or any "transferred to
      // support" / "please wait" phrasing in this message until the
      // integration actually routes to a human. Protect this at
      // launch-gate time (go-live checklist).
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              status: "noted",
              reason: params.reason,
              noted_at: timestamp,
              message:
                "سجلت ملاحظتك. سأحاول مساعدتك هنا.",
              handoff_available: false,
              escalation_status: "pending_integration",
            }),
          },
        ],
      };
    },
  });
}
