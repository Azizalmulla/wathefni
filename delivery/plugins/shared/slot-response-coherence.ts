/**
 * Slot-response coherence — does this customer message actually answer
 * the slot we asked for?
 *
 * Background
 * ----------
 * Before this module existed, both write paths (the pre-LLM fast-path
 * extractor and the post-LLM apply-boundary validator) decided whether
 * to write a value to a booking slot using only **shape** rules: "does
 * the string look like a name / phone / address part?" That's the wrong
 * question. A real customer name and a real customer question can both
 * be pure letters+spaces of length 2–60, so shape rules cannot tell
 * them apart. Result: on 2026-04-19 13:42 (live) the customer's
 * follow-up question "Is this the cheapest option" was silently written
 * to `sender_name` and corrupted the rest of the booking flow.
 *
 * The right question is: **given that we just asked for slot X, is the
 * customer's reply a coherent answer to X — or a question, a topic
 * change, or noise?** Two cheap signals do most of the work:
 *
 *   1. Question detection — interrogative prefixes + question marks are
 *      almost never an answer to a slot we asked for.
 *   2. Topic mismatch — vocabulary belonging to *other* domains (price,
 *      vehicle type, time, area names, cancellation, etc.) signals the
 *      customer changed topic instead of answering.
 *
 * Layered with a per-slot shape check, these signals classify each
 * utterance into one of: `answer`, `question`, `topic_change`,
 * `ambiguous`, or `empty`. The two write paths consult this classifier
 * before persisting; only `answer` is unconditionally accepted.
 *
 * Design principles
 * -----------------
 * 1. **Single source of truth.** Both write paths import the same
 *    `classifyResponseForSlot`. They cannot drift.
 *
 * 2. **Asymmetric error budget.** Saying "answer" when it isn't is
 *    catastrophic (silent corruption). Saying "not answer" when it is
 *    is cheap (the LLM re-asks once). The decision rule is biased
 *    accordingly: we only return `answer` when shape passes AND no
 *    negative signal fires.
 *
 * 3. **Positive evidence only.** We never return `question` or
 *    `topic_change` on weak evidence. Without a positive signal the
 *    verdict is `ambiguous`, and the caller decides per-slot policy
 *    (high-risk slots reject ambiguous, low-risk slots accept it).
 *
 * 4. **Slot-aware, not slot-coupled.** The signals are generic; only
 *    the per-slot vocabulary lookup is specialized. Adding a new slot
 *    means adding one row to `SLOT_VOCABULARY`, not changing logic.
 *
 * 5. **Telemetry first.** Every decision returns the ordered list of
 *    signals that contributed, so production logs let us tune the
 *    rules with real data instead of guessing.
 */

import type { SlotName } from "./dialog-state";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type CoherenceKind =
  | "answer"
  | "question"
  | "topic_change"
  | "greeting"
  | "acknowledgment"
  | "ambiguous"
  | "empty";

export type CoherenceConfidence = "high" | "medium" | "low";

export type SlotCoherenceDecision = {
  kind: CoherenceKind;
  /** Short snake_case label for the dominant reason (used in telemetry / op rejection reasons). */
  reason: string;
  /** Every signal that fired, in the order it fired. Useful for debugging surprising decisions. */
  signals: string[];
  confidence: CoherenceConfidence;
};

// ---------------------------------------------------------------------------
// Question signals
//
// Same patterns the legacy `validateName` used, promoted here so they
// can be applied uniformly to ANY slot, not just names. These are
// matched on the trimmed text. We use an explicit non-letter lookahead
// instead of `\b` because JS word boundaries don't handle Arabic letters
// reliably across engines.
// ---------------------------------------------------------------------------

const INTERROGATIVE_PREFIXES: RegExp[] = [
  /^(is|are|am|do|does|did|can|could|will|would|should|may|might|have|has|had|was|were)(?=$|[^\p{L}])/iu,
  /^(what|when|where|why|who|whom|whose|which|how)(?=$|[^\p{L}])/iu,
  /^(هل|شو|شنو|متى|وين|كيف|كم|ليش|منو|اي|ايش)(?=$|[^\p{L}])/u,
  /^(shlon|shlonk|shloon|shloo|shku|shnu|shno|wain|win|kam|kef|kaif|laish|leysh|menu|mno|aysh|esh)(?=$|[^\p{L}])/iu,
];

function hasQuestionMark(text: string): boolean {
  return /[?؟]/.test(text);
}

function startsWithInterrogative(text: string): boolean {
  return INTERROGATIVE_PREFIXES.some((rx) => rx.test(text));
}

// ---------------------------------------------------------------------------
// Greeting signals
//
// Pure greetings ("hi", "hello", "hala", "السلام عليكم") shouldn't be
// considered slot answers under any circumstances — they pass name
// shape (pure letters, short) and carry no foreign-domain vocabulary,
// so without a dedicated greeting detector they'd fall through to
// `answer` for name slots and corrupt the draft. The 2026-04-19 live
// incident is the canonical case: "hello" got shape-matched into
// `sender_name` on a complete draft, creating a slot conflict against
// the already-poisoned stored name.
//
// We match:
//   - English greetings (hi, hello, hey, howdy, greetings).
//   - Kuwaiti / Arabic Gulf greetings in Arabizi transliteration
//     (hala, halla, hala wallah, marhaba, sabah el kheir, etc).
//   - Arabic script greetings (السلام عليكم, مرحبا, أهلا, اهلا, صباح الخير).
//
// Matches are whole-message (optional trailing punctuation / emoji /
// exclamation mark) so that "hi, I'm Aziz" is NOT classified as a
// greeting — it's a greeting PLUS content, which is still a
// legitimate answer for name slots.
// ---------------------------------------------------------------------------

const GREETING_PATTERNS: RegExp[] = [
  // English
  /^(?:hi|hello|hey|heya|hiya|howdy|greetings|yo|sup|good\s+(?:morning|afternoon|evening|day))[\s.!?؟،,]*$/iu,
  // Arabizi / Kuwaiti gulf
  /^(?:hala|halla|hala\s+wallah|halla\s+wallah|hala\s+w\s+allah|marhaba|marhabtain|sabah\s+(?:el\s+|al\s+)?kheir|sabah\s+(?:el\s+|al\s+)?khair|masa\s+(?:el\s+|al\s+)?kheir|masa\s+(?:el\s+|al\s+)?khair|salam|salaam|salamu?\s*alaikum|assalamu?\s*alaikum|3alaikum\s+(?:es\s*)?salam)[\s.!?؟،,]*$/iu,
  // Arabic script
  /^(?:السلام\s+عليكم|و?عليكم\s+السلام|مرحبا|مرحباً|أهلا|اهلا|أهلاً|اهلاً|أهلين|اهلين|صباح\s+(?:ال)?خير|مساء\s+(?:ال)?خير|يا\s*هلا|هلا|هلا\s+والله)[\s.!?؟،,]*$/u,
];

function looksLikeGreeting(text: string): boolean {
  return GREETING_PATTERNS.some((rx) => rx.test(text));
}

// ---------------------------------------------------------------------------
// Acknowledgment signals
//
// Bare acknowledgments ("ok", "alright", "sure", "yes", "تمام", "زين") pass
// the name-shape predicate (letters-only, short, 2–60 chars) but are NOT
// slot answers — they're the customer signalling they received the previous
// bot message and are ready for the next step. Without a dedicated detector
// they'd fall through to `answer` for name slots and corrupt the draft.
//
// The 2026-04-19 22:08 live transcript is the canonical case: the customer
// said "alright" after the bot delivered a price quote, the fast-path
// extractor shape-matched it into `sender_name`, the draft advanced to
// `ASK_SENDER_PHONE`, and the bot silently skipped the real sender-name
// step.
//
// This list is intentionally narrow. Patterns are anchored whole-message
// (optional trailing punctuation / emoji / exclamation mark) so that
// "alright, I'm Aziz" is NOT classified as an acknowledgment — it's an
// acknowledgment PLUS content, which is still a legitimate answer for
// name slots. We match:
//   - English acks (ok, okay, alright, sure, yes, yeah, yep, fine, cool,
//     great, perfect, got it, sounds good, noted, done).
//   - Kuwaiti / Arabizi (tamam, zain, zein, maashi, mashi, ok, okay,
//     okii, okeey, inshallah/isa as affirmation, yalla).
//   - Arabic script (تمام, طيب, زين, ماشي, اوكي, أوكي, اوك, تمت, تم,
//     عدل, إنشاء الله / إن شاء الله as soft affirmation, يلا, يلله, يالله).
// ---------------------------------------------------------------------------

// NOTE on trailing punctuation: we deliberately accept `.`, `!`, `,` but
// NOT `?` / `؟`. A question mark turns an acknowledgment into a question
// ("ok?", "sure?", "تمام؟" read as "are we good? / are you sure?"), and
// the downstream classifier is expected to route those through the
// question path — not through acknowledgment. This differs from the
// greeting patterns, which DO accept trailing `?` ("hello?") because a
// greeting-with-question is still handled as a greeting.
//
// 2026-04-22 — multi-word acks added. Live transcript (conv 19399)
// showed "أوكي تم" reaching the name-slot fast-path because the
// single-token patterns below never fired. Rather than add a second
// list of hand-rolled two-word Arabic pairs, we split the lexicons
// into alternation fragments and build a fourth regex that matches
// any two stacked ack tokens (EN/Arabizi/Arabic, in any order). That
// closes "ok done", "yes noted", "تمام ماشي", "أوكي تم", "ok tamam",
// etc. without enumerating pairs. Both tokens must be in the lexicon,
// so legitimate "alright, I'm Aziz" / "ok Ali" are still NOT acks.
const EN_ACK_ALT =
  "ok|okay|okey|oki|okie|okies|alright|alrighty|aight|sure|fine|cool|nice|great|perfect|awesome|excellent|yes|yea|yeah|yep|yup|yess+|yass+|yh|y|mhm|mmhm|mhmm|done|noted|got\\s+it|sounds\\s+good|go\\s+ahead|go|do\\s+it|proceed|roger|copy|ack";
const ARABIZI_ACK_ALT =
  "tamam|tmam|tamaam|mashi|maashi|maashy|mashy|zain|zein|zen|yalla|yala|yallah|inshallah|inshalla|isa|akeed|akid|tab|tayeb|6ayeb";
const AR_ACK_ALT =
  "تمام|تم|تمت|طيب|ماشي|زين|زينو|اوكي|أوكي|اوكيه|أوكيه|اوك|أوك|عدل|نعم|ايه|أيه|ايوه|إي|اي|يلا|يلله|يالله|اكيد|أكيد|ان\\s*شاء\\s*الله|إن\\s*شاء\\s*الله|انشاء\\s*الله|إنشاء\\s*الله|حسنا|حسناً";

const ANY_ACK_ALT = `${EN_ACK_ALT}|${ARABIZI_ACK_ALT}|${AR_ACK_ALT}`;

const ACKNOWLEDGMENT_PATTERNS: RegExp[] = [
  // Single-token EN / Latin
  new RegExp(`^(?:${EN_ACK_ALT})[\\s.!،,]*$`, "iu"),
  // Single-token Arabizi — Kuwaiti affirmations that are letters-only
  // (digit-embedded Arabizi like "9ah" is rare and we prefer a false
  // negative to a false positive here).
  new RegExp(`^(?:${ARABIZI_ACK_ALT})[\\s.!،,]*$`, "iu"),
  // Single-token Arabic script
  new RegExp(`^(?:${AR_ACK_ALT})[\\s.!،,]*$`, "u"),
  // Two-token stacked ack in any script combination. Each token must be
  // a known ack — this is the guarantee that "ok Ali" / "tamam Ahmad"
  // don't get swallowed as acks just because the first token is one.
  new RegExp(
    `^(?:${ANY_ACK_ALT})\\s+(?:${ANY_ACK_ALT})[\\s.!،,]*$`,
    "iu",
  ),
];

function looksLikeAcknowledgment(text: string): boolean {
  return ACKNOWLEDGMENT_PATTERNS.some((rx) => rx.test(text));
}

// ---------------------------------------------------------------------------
// Topic-vocabulary signals
//
// Each domain is a small set of high-signal tokens drawn from the live
// transcripts. We detect them with whole-word boundaries (Unicode-safe)
// so substrings inside legitimate values don't false-positive (e.g.
// "Mansouriya" doesn't match "ya").
// ---------------------------------------------------------------------------

type DomainName =
  | "price"
  | "vehicle"
  | "time"
  | "cancel_or_change"
  | "tracking"
  | "payment"
  | "options"
  | "areas";

// We use explicit Unicode boundary lookarounds instead of `\b` because
// JavaScript's `\b` is ASCII-only and mis-fires on Arabic letters. The
// leading `(?<![\p{L}\p{N}])` rejects matches where the previous char
// is alphanumeric; the trailing `(?![\p{L}\p{N}])` rejects matches
// where the next char is alphanumeric. This gives us proper
// "whole-word" matching across scripts.
const LB = "(?<![\\p{L}\\p{N}])";
const RB = "(?![\\p{L}\\p{N}])";
const wb = (alternation: string) => new RegExp(`${LB}(?:${alternation})${RB}`, "iu");

const DOMAIN_VOCABULARY: Record<DomainName, RegExp[]> = {
  price: [
    wb(
      "price|prices|pricing|cost|costs|cheap|cheaper|cheapest|expensive|fee|fees|kwd|kd|دينار|سعر|اسعار|الاسعار|تكلفه|تكلفة|رخيص|اوفر|akhass|akkhass|arkhas|arkhass|s3er|si3r|si3ir|awfar",
    ),
  ],
  vehicle: [
    wb(
      "sedan|car|van|truck|express|fast|standard|cooled|helper|bike|moto|motorcycle|سياره|سيارة|شاحنه|فان|عاديه|عادية|سريع|سريعه|سريعة|مبرد|مساعد",
    ),
  ],
  time: [
    wb(
      "when|how\\s+long|eta|hours?|minutes?|today|tomorrow|tonight|asap|now|متى|اليوم|باچر|ساعه|ساعة|دقيقه|دقيقة|الحين|بسرعه",
    ),
  ],
  cancel_or_change: [
    wb(
      "cancel|cancell|cancelled|cancelation|stop|abort|nevermind|change|edit|modify|الغاء|اوقف|توقف|غير|عدل|بدل",
    ),
  ],
  tracking: [
    wb(
      "track|tracking|where\\s+is|status|order\\s+id|order\\s+number|تتبع|وين\\s+الطلب|وصل|الحال",
    ),
  ],
  payment: [
    wb(
      "pay|paid|payment|cash|knet|k-net|visa|mastercard|invoice|receipt|دفع|دفعت|كاش|نقدا|كي\\s*نت|فاتوره|فاتورة|ايصال",
    ),
  ],
  options: [
    wb(
      "option|options|alternatives?|other(?:s)?|different|else|اخر|اخرى|ثانيه|ثانية|بديل|بدائل|خيار|خيارات",
    ),
  ],
  // Common Kuwait area names that often appear in price re-quote
  // questions ("how much to Salmiya?"). Intentionally EXCLUDES
  // governorate names that double as common Kuwaiti first names
  // ("Mubarak", "Ahmadi") — including them would cause false
  // topic_change verdicts on legitimate name answers. The area
  // resolver has its full vocabulary; this list is only for spotting
  // obvious topic drift in non-area slots.
  areas: [
    wb(
      "salmiya|salwa|jabriya|hawalli|hawally|farwaniya|fahaheel|jahra|kuwait\\s+city|airport|wafra|jlai3a|jlea|julaia|الجابريه|الجابرية|السالميه|السالمية|سلوى|حولي|الفروانيه|الفروانية|الفحيحيل|الجهراء|الكويت|المطار|الوفره|الوفرة|الجليعه|الجليعة",
    ),
  ],
};

function detectForeignDomains(text: string, allowedDomains: ReadonlySet<DomainName>): DomainName[] {
  const hits: DomainName[] = [];
  for (const [domain, patterns] of Object.entries(DOMAIN_VOCABULARY) as Array<[DomainName, RegExp[]]>) {
    if (allowedDomains.has(domain)) continue;
    if (patterns.some((rx) => rx.test(text))) {
      hits.push(domain);
    }
  }
  return hits;
}

// ---------------------------------------------------------------------------
// Per-slot policy: which domains are NATIVE to the slot (so foreign-
// vocabulary detection skips them), what the shape predicate is, and
// how strict to be about ambiguous cases.
//
// "Strict" slots reject `ambiguous`. They are the slots where a wrong
// write corrupts the booking in ways the customer can't easily see —
// names and addresses, primarily. "Lenient" slots accept `ambiguous`
// (they have stronger downstream validation: phones must be all digits,
// areas are re-resolved by the resolver).
// ---------------------------------------------------------------------------

type SlotPolicy = {
  /** Domains that are native to this slot — vocabulary from these
   *  domains does NOT count as topic change. */
  nativeDomains: ReadonlySet<DomainName>;
  /** Hard shape predicate for the value as an answer. */
  passesShape: (text: string) => boolean;
  /** Maximum word count that's plausible for this slot (0 = no cap). */
  maxWords: number;
  /** Treat "ambiguous" as `answer` (false) or as not-answer (true). */
  rejectAmbiguous: boolean;
};

// Shape predicates — these are intentionally loose; tight shape
// checking still happens at the apply-boundary's `validateName` /
// `validatePhone`. The job here is "could this PLAUSIBLY be an answer
// to this slot?", not "is it a perfect value?".
const NAME_SHAPE = /^[\p{L}][\p{L}\s'\-.]*$/u;
const PHONE_SHAPE = /\d/;
const ADDRESS_PART_SHAPE = /[\p{L}\p{N}]/u;
const AREA_SHAPE = /[\p{L}]/u;

const PERSON_NAME_NATIVE = new Set<DomainName>([]);
const PHONE_NATIVE = new Set<DomainName>([]);
const ADDRESS_NATIVE = new Set<DomainName>([]);
const AREA_NATIVE = new Set<DomainName>(["areas"]);

const SLOT_POLICY: Record<SlotName, SlotPolicy> = {
  sender_name: {
    nativeDomains: PERSON_NAME_NATIVE,
    passesShape: (t) => NAME_SHAPE.test(t),
    maxWords: 4,
    rejectAmbiguous: true,
  },
  recipient_name: {
    nativeDomains: PERSON_NAME_NATIVE,
    passesShape: (t) => NAME_SHAPE.test(t),
    maxWords: 4,
    rejectAmbiguous: true,
  },
  sender_phone: {
    nativeDomains: PHONE_NATIVE,
    passesShape: (t) => PHONE_SHAPE.test(t),
    maxWords: 0,
    rejectAmbiguous: false,
  },
  recipient_phone: {
    nativeDomains: PHONE_NATIVE,
    passesShape: (t) => PHONE_SHAPE.test(t),
    maxWords: 0,
    rejectAmbiguous: false,
  },
  pickup_area: {
    nativeDomains: AREA_NATIVE,
    passesShape: (t) => AREA_SHAPE.test(t),
    maxWords: 8,
    rejectAmbiguous: false,
  },
  dropoff_area: {
    nativeDomains: AREA_NATIVE,
    passesShape: (t) => AREA_SHAPE.test(t),
    maxWords: 8,
    rejectAmbiguous: false,
  },
  pickup_block: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  pickup_street: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  pickup_house: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  pickup_avenue: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  pickup_extra: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 30,
    rejectAmbiguous: false,
  },
  delivery_block: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  delivery_street: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  delivery_house: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  delivery_avenue: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 6,
    rejectAmbiguous: true,
  },
  delivery_extra: {
    nativeDomains: ADDRESS_NATIVE,
    passesShape: (t) => ADDRESS_PART_SHAPE.test(t),
    maxWords: 30,
    rejectAmbiguous: false,
  },
};

function countWords(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/u).filter(Boolean).length;
}

// ---------------------------------------------------------------------------
// Public predicate
// ---------------------------------------------------------------------------

/**
 * Classify a customer utterance against the slot the assistant just
 * requested. Returns `kind: "answer"` only when shape passes AND no
 * question / topic-change signal fires. See module docstring for the
 * full contract.
 *
 * If `slot` is null (no slot was requested this turn — e.g. the
 * customer is in `idle` or `quoted` and just sent a fresh message),
 * the classifier returns `ambiguous` with reason `no_slot_requested`.
 * Callers should NOT use this as a write gate when no slot is requested
 * — it's only meaningful in slot-collection contexts.
 */
export function classifyResponseForSlot(params: {
  text: string;
  slot: SlotName | null;
}): SlotCoherenceDecision {
  const text = (params.text ?? "").trim();
  const signals: string[] = [];

  if (!text) {
    return {
      kind: "empty",
      reason: "empty_text",
      signals: ["empty"],
      confidence: "high",
    };
  }

  if (!params.slot) {
    return {
      kind: "ambiguous",
      reason: "no_slot_requested",
      signals: ["no_slot_requested"],
      confidence: "low",
    };
  }

  const policy = SLOT_POLICY[params.slot];
  if (!policy) {
    return {
      kind: "ambiguous",
      reason: "unknown_slot",
      signals: ["unknown_slot"],
      confidence: "low",
    };
  }

  // --- Negative signals (positive evidence that this is NOT an answer)

  // Greeting — bare "hi", "hello", "hala", "مرحبا", etc. These should
  // never be treated as a slot answer, even though they pass the name
  // shape check. We test BEFORE the question check so that greetings
  // with trailing "?" ("hello?") are classified as greetings, not
  // questions — that's the 2026-04-19 case where the customer said
  // "hello?" after waiting for confirmation, and the existing question
  // path was acceptable but greeting is more specific and lets callers
  // render a "we're still here" response deterministically.
  if (looksLikeGreeting(text)) {
    signals.push("greeting");
    return {
      kind: "greeting",
      reason: "greeting",
      signals,
      confidence: "high",
    };
  }

  // Acknowledgment — bare "ok", "alright", "sure", "yes", "تمام", "زين",
  // etc. These pass name-shape but are not slot answers. Detected here,
  // before the question/topic checks, so the verdict is the most specific
  // one available and callers can log/route acknowledgments explicitly
  // (e.g. "we heard you, here's the next ask"). Whole-message anchor
  // keeps "alright, I'm Aziz" on the answer path.
  if (looksLikeAcknowledgment(text)) {
    signals.push("acknowledgment");
    return {
      kind: "acknowledgment",
      reason: "acknowledgment",
      signals,
      confidence: "high",
    };
  }

  let isQuestion = false;
  if (hasQuestionMark(text)) {
    signals.push("question_mark");
    isQuestion = true;
  }
  if (startsWithInterrogative(text)) {
    signals.push("interrogative_prefix");
    isQuestion = true;
  }

  if (isQuestion) {
    return {
      kind: "question",
      reason: signals.includes("question_mark") ? "question_mark" : "interrogative_prefix",
      signals,
      confidence: "high",
    };
  }

  const foreignDomains = detectForeignDomains(text, policy.nativeDomains);
  for (const domain of foreignDomains) {
    signals.push(`foreign_domain:${domain}`);
  }

  const wordCount = countWords(text);
  const shapePasses = policy.passesShape(text);
  if (shapePasses) signals.push("slot_shape_match");
  const overWordCap = policy.maxWords > 0 && wordCount > policy.maxWords;
  if (overWordCap) signals.push("over_word_cap");

  // Topic-change verdict: any foreign-domain vocabulary is strong
  // evidence the customer is talking about a different topic rather
  // than answering the requested slot. We treat this as topic-change
  // regardless of whether the string happens to pass the slot's loose
  // shape check — shape can be noise (e.g. "cheapest option please"
  // passes name shape but is obviously not a name).
  //
  // Confidence is high when either (a) shape also fails or (b) the
  // message exceeds the slot's word cap. When shape passes AND the
  // message is short, confidence is medium — these cases are the
  // hardest (customer could have legitimately included a foreign-
  // domain word as context, e.g. "Aziz cash"), so we still call it
  // topic-change but leave room for callers to be lenient.
  if (foreignDomains.length > 0) {
    const strong = !shapePasses || overWordCap;
    return {
      kind: "topic_change",
      reason: strong
        ? `foreign_domain:${foreignDomains[0]}`
        : `foreign_domain_with_shape_match:${foreignDomains[0]}`,
      signals,
      confidence: strong ? "high" : "medium",
    };
  }

  // Word-cap-only (no foreign vocab): treat as ambiguous, not as a
  // hard reject. Lets edge cases like "Abdulaziz Mohammed Al Sabah Al
  // Mubarak" (5 tokens) survive into the apply-boundary, where stricter
  // rules can still reject it. The apply-boundary's name validator caps
  // at the same 4 words for sender/recipient names, so this stays
  // consistent end-to-end.
  if (overWordCap) {
    return {
      kind: "ambiguous",
      reason: "over_word_cap",
      signals,
      confidence: "medium",
    };
  }

  if (!shapePasses) {
    return {
      kind: "ambiguous",
      reason: "shape_mismatch",
      signals,
      confidence: "medium",
    };
  }

  // No negative signals + shape passes → confident answer.
  return {
    kind: "answer",
    reason: "shape_match_no_negatives",
    signals,
    confidence: "high",
  };
}

/**
 * Convenience wrapper for write-path gates. Returns true iff the
 * decision is `answer` (always) OR `ambiguous` for slots whose policy
 * accepts ambiguous. Callers that need richer telemetry should call
 * `classifyResponseForSlot` directly and inspect the decision.
 */
export function isAcceptableSlotResponse(params: {
  text: string;
  slot: SlotName | null;
}): { acceptable: boolean; decision: SlotCoherenceDecision } {
  const decision = classifyResponseForSlot(params);
  if (decision.kind === "answer") {
    return { acceptable: true, decision };
  }
  if (decision.kind === "ambiguous" && params.slot && !SLOT_POLICY[params.slot]?.rejectAmbiguous) {
    return { acceptable: true, decision };
  }
  return { acceptable: false, decision };
}

// Re-exported for tests + telemetry tooling. NOT part of the recommended
// public API — production code should use `classifyResponseForSlot` /
// `isAcceptableSlotResponse`.
export const __coherenceTestHooks = {
  INTERROGATIVE_PREFIXES,
  GREETING_PATTERNS,
  ACKNOWLEDGMENT_PATTERNS,
  DOMAIN_VOCABULARY,
  SLOT_POLICY,
};
