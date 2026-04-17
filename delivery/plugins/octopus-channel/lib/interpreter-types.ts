// ---------------------------------------------------------------------------
// Wave 5 extraction: shared interpreter types.
// Pure type aliases moved out of `plugins/octopus-channel/index.ts` so both
// the interpreter pipeline and the live-channel-context formatter can import
// them without pulling on module-scoped state.
// ---------------------------------------------------------------------------

export type InterpretedCustomerTurnAction =
  | "greeting"
  | "language_switch"
  | "service_overview"
  | "pricing_request"
  | "same_route_quote_option"
  | "same_route_show_other_options"
  | "start_booking"
  | "booking_step_input"
  | "correct_booking_field"
  | "confirm_summary"
  | "cancel_booking"
  | "tracking_request"
  | "tracking_missing_id"
  | "passenger_transport_request"
  | "handoff"
  | "clarify"
  | "general_support";

export type InterpretedBookingFields = {
  sender_name: string | null;
  sender_phone: string | null;
  phone_decision: "use_whatsapp" | "different" | "none" | null;
  recipient_name: string | null;
  recipient_phone: string | null;
  address_block: string | null;
  address_street: string | null;
  address_house: string | null;
};

export type InterpretedCustomerTurn = {
  action: InterpretedCustomerTurnAction;
  selected_delivery_type: string | null;
  should_use_active_quote: boolean;
  route_changed: boolean;
  order_id: string | null;
  requested_language: "ar" | "en" | null;
  confidence: "low" | "medium" | "high";
  reason: string;
  booking_fields: InterpretedBookingFields | null;
  location_role_hint: "pickup" | "delivery" | null;
};
