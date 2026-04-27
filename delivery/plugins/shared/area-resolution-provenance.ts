export type AreaResolutionStatus =
  | "canonical"
  | "exact_confirmed"
  | "suggested_unconfirmed"
  | "ambiguous"
  | "unresolved"
  | "missing"
  | "unknown";

export type AreaResolutionOption = {
  areaId: number | string | null;
  nameEn: string | null;
  nameAr: string | null;
};

export type AreaResolutionProvenance = {
  status: AreaResolutionStatus;
  areaId: number | string | null;
  nameEn: string | null;
  nameAr: string | null;
  ambiguityGroupId?: string | null;
  options?: AreaResolutionOption[];
  sourceText?: string | null;
  normalizedText?: string | null;
  resolverSource?: string | null;
  confirmedByUser?: boolean;
  quoteBuiltFromAreaIds?: boolean;
  promptEn?: string | null;
  promptAr?: string | null;
};

export function isCanonicalAreaResolutionStatus(
  status: AreaResolutionStatus | null | undefined,
): boolean {
  return status === "canonical" || status === "exact_confirmed";
}

export function normalizeAreaResolutionStatus(
  value: unknown,
): AreaResolutionStatus {
  const status = String(value || "").trim();
  if (
    status === "canonical" ||
    status === "exact_confirmed" ||
    status === "suggested_unconfirmed" ||
    status === "ambiguous" ||
    status === "unresolved" ||
    status === "missing" ||
    status === "unknown"
  ) {
    return status;
  }
  if (status === "suggested") return "suggested_unconfirmed";
  if (status === "not_found") return "unresolved";
  if (status === "resolved") return "canonical";
  return "unknown";
}

export function cloneAreaResolutionProvenance(
  provenance: AreaResolutionProvenance | null | undefined,
): AreaResolutionProvenance | null {
  if (!provenance) return null;
  return {
    ...provenance,
    status: normalizeAreaResolutionStatus(provenance.status),
    options: Array.isArray(provenance.options)
      ? provenance.options.map((option) => ({ ...option }))
      : undefined,
  };
}
