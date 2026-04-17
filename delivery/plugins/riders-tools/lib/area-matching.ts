// ---------------------------------------------------------------------------
// Wave 1b extraction: pure Arabic/English area-matching primitives used by the
// pricing resolver and admin pricing tools. These are deterministic string
// transformations and edit-distance helpers with no I/O and no module-scope
// state. The higher-level `findArea*` matchers and the resolver-layer fuzzy
// pipeline still live in `plugins/riders-tools/index.ts` for now because they
// consume the shared pricing cache; they move in a follow-up wave 1b commit.
// ---------------------------------------------------------------------------

export function normalizeArabic(text: string): string {
  return text
    .replace(/^ال/, "")
    .replace(/ة$/, "ه")
    .replace(/[أإآ]/g, "ا")
    .replace(/ى$/, "ي")
    .trim();
}

/** Aggressive Arabic normalization for fuzzy/prefix matching (applies globally). */
export function normalizeForFuzzyMatch(text: string): string {
  return text
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي")
    .replace(/\s+/g, " ")
    .trim();
}

/** Strip the Arabic definite article ال from each token. */
export function stripArDefiniteArticle(text: string): string {
  return text
    .split(/\s+/)
    .map((t) => t.replace(/^ال/, ""))
    .filter((t) => t.length > 0)
    .join(" ")
    .trim();
}

/** Common Arabic area prefixes that don't help distinguish areas. */
export const AREA_PREFIX_RE = /^(?:ضاحية|منطقة|جزيرة|محافظة)\s+/;
export const AREA_DIRECTION_PREFIX_RE = /^(?:جنوب|شرق|شمال|غرب)\s+/;

/** Strip common prefixes for canonical comparison. Keeps directional prefixes since they distinguish areas. */
export function canonicalizeAreaName(text: string): string {
  const s = text.trim().replace(AREA_PREFIX_RE, "").trim();
  return normalizeForFuzzyMatch(s);
}

/** Tokenize Arabic/English text for overlap analysis. */
export function areaTokens(text: string): Set<string> {
  return new Set(
    normalizeForFuzzyMatch(text)
      .split(/\s+/)
      .filter((t) => t.length > 0),
  );
}

export const NON_DISTINGUISHING_AREA_TOKENS = new Set([
  "ضاحيه",
  "ضاحية",
  "منطقه",
  "منطقة",
  "جزيره",
  "جزيرة",
  "محافظه",
  "محافظة",
  "ال",
]);

export const NON_DISTINGUISHING_EN_TOKENS = new Set([
  "al",
  "el",
  "area",
  "block",
  "district",
  "zone",
  "suburb",
  "neighbourhood",
  "neighborhood",
]);

/**
 * Normalize English area name for substring comparison.
 * Strips "al"/"el" prefixes/articles and hyphens so that
 * "Abdullah Al-Mubarak" and "Abdullah Mubarak" both normalize to
 * "abdullah mubarak".
 */
export function normalizeEnSubstring(text: string): string {
  return text
    .toLowerCase()
    .replace(/[-''`]/g, " ")
    .replace(/[^a-z0-9\s]/g, "")
    .split(/\s+/)
    .filter((t) => t.length > 0 && t !== "al" && t !== "el")
    .join(" ")
    .trim();
}

export function isNumericAreaSuffixToken(token: string): boolean {
  return /^\d+$/.test(token.trim());
}

export function diffMeaningfulAreaTokens(
  inputText: string,
  matchLabel: string,
) {
  const inputToks = areaTokens(inputText);
  const matchToks = areaTokens(matchLabel);
  const inputOnly: string[] = [];
  const matchOnly: string[] = [];

  for (const token of inputToks) {
    if (
      !matchToks.has(token) &&
      !NON_DISTINGUISHING_AREA_TOKENS.has(token) &&
      token.length > 1
    ) {
      inputOnly.push(token);
    }
  }

  for (const token of matchToks) {
    if (
      !inputToks.has(token) &&
      !NON_DISTINGUISHING_AREA_TOKENS.has(token) &&
      token.length > 1
    ) {
      matchOnly.push(token);
    }
  }

  return { inputOnly, matchOnly };
}

export function diffMeaningfulEnTokens(
  inputText: string,
  matchLabel: string,
) {
  const normalize = (s: string) =>
    new Set(
      normalizeEn(s)
        .split(/\s+/)
        .filter((t) => t.length > 0),
    );
  const inputToks = normalize(inputText);
  const matchToks = normalize(matchLabel);
  const inputOnly: string[] = [];
  const matchOnly: string[] = [];

  for (const token of inputToks) {
    if (!matchToks.has(token) && !NON_DISTINGUISHING_EN_TOKENS.has(token)) {
      inputOnly.push(token);
    }
  }

  for (const token of matchToks) {
    if (!inputToks.has(token) && !NON_DISTINGUISHING_EN_TOKENS.has(token)) {
      matchOnly.push(token);
    }
  }

  return { inputOnly, matchOnly };
}

export function stripTrailingNumericAreaSuffix(text: string): string {
  return text.replace(/\s+\d+$/, "").trim();
}

export function extractTrailingNumericAreaSuffix(text: string): number | null {
  const match = text.trim().match(/(?:^|\s)(\d+)$/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
}

export function stripFlexibleTrailingNumericAreaSuffix(text: string): string {
  return text.replace(/(?:\s+|[-_/])\d+$/, "").trim();
}

export function hasTokenConflict(
  inputText: string,
  matchLabel: string,
): boolean {
  const { inputOnly, matchOnly } = diffMeaningfulAreaTokens(
    inputText,
    matchLabel,
  );
  if (inputOnly.length > 0 && matchOnly.length > 0) {
    console.log(
      `[voyage-guard] Token conflict detected: input-only=[${inputOnly.join(", ")}] match-only=[${matchOnly.join(", ")}]`,
    );
    return true;
  }
  return false;
}

export function normalizeEn(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .trim();
}

export function normalizeLatinAreaToken(token: string): string {
  return token
    .replace(/^el(?=[a-z])/g, "al")
    .replace(/ph/g, "f")
    .replace(/ou/g, "u")
    .replace(/oo+/g, "u")
    .replace(/ee+/g, "i")
    .replace(/ii+/g, "i")
    .replace(/yy+/g, "i")
    .replace(/y/g, "i")
    .replace(/aa+/g, "a")
    .replace(/ei/g, "ai")
    .replace(/q/g, "g")
    .replace(/([a-z])\1+/g, "$1")
    .replace(/ah$/g, "a")
    .replace(/iya$/g, "ia")
    .replace(/ieh$/g, "ia")
    .replace(/^(?:al|el)$/g, "");
}

export function normalizeLatinAreaKey(text: string): string {
  return text
    .toLowerCase()
    .replace(/['’`]/g, "")
    .replace(/5/g, "kh")
    .replace(/7/g, "ha")
    .replace(/8/g, "gh")
    .replace(/6/g, "t")
    .replace(/9/g, "s")
    .replace(/[23]/g, "a")
    .replace(/[^a-z\s]/g, " ")
    .split(/\s+/)
    .map((token) => normalizeLatinAreaToken(token))
    .filter(Boolean)
    .join(" ")
    .trim();
}

export function containsArabicScript(text: string): boolean {
  return /[\u0600-\u06FF]/u.test(text || "");
}

export function compactLookupKey(text: string): string {
  return text.replace(/\s+/g, "");
}

export function damerauLevenshteinDistance(a: string, b: string): number {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const dp = Array.from({ length: rows }, () => Array<number>(cols).fill(0));

  for (let i = 0; i < rows; i += 1) dp[i][0] = i;
  for (let j = 0; j < cols; j += 1) dp[0][j] = j;

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + cost,
      );
      if (
        i > 1 &&
        j > 1 &&
        a[i - 1] === b[j - 2] &&
        a[i - 2] === b[j - 1]
      ) {
        dp[i][j] = Math.min(dp[i][j], dp[i - 2][j - 2] + cost);
      }
    }
  }

  return dp[a.length][b.length];
}

export function normalizeGovernorateName(text: string): string {
  return normalizeEn(text.replace(/governorate/gi, ""));
}

export function buildSheetHeaderFingerprints(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return [];

  const compact = trimmed.toLowerCase().replace(/[\s_\-()\/\\]+/g, "");
  const normalizedAr = normalizeArabic(trimmed).replace(/[\s_\-()\/\\]+/g, "");
  const normalizedEn = normalizeEn(trimmed).replace(/\s+/g, "");
  return Array.from(
    new Set([compact, normalizedAr, normalizedEn].filter(Boolean)),
  );
}
