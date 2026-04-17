// ---------------------------------------------------------------------------
// Wave 1b extraction: pure Google Sheets helpers used by the riders-tools
// admin sheet and pricing tool surfaces. No module-scope state, no I/O —
// only deterministic row/value shape utilities. The stateful `gog`-backed
// readers/writers still live in `plugins/riders-tools/index.ts` because they
// read module-scope Google Sheet configuration (spreadsheet id, sheet name,
// header row, admin allowlists); those move in a later wave 1b commit.
// ---------------------------------------------------------------------------

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function normalizeGoogleSheetCellValue(value: unknown) {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value === "string") {
    return value.trim();
  }
  return value;
}

export function isGoogleSheetCellEmpty(value: unknown) {
  return (
    value === null ||
    value === undefined ||
    (typeof value === "string" && !value.trim())
  );
}

export interface ParsedSheetRow {
  row_number: number;
  record: Record<string, unknown>;
  source_row: unknown[];
}

export interface GoogleSheetValueTable {
  headers: string[];
  rows: ParsedSheetRow[];
  input_row_count: number;
  skipped_row_count: number;
}

export function buildGoogleSheetValueTable(
  values: unknown[] | undefined,
  headerRow: number,
): GoogleSheetValueTable {
  const rows = Array.isArray(values) ? values : [];
  if (rows.length < headerRow) {
    throw new Error(`Google sheet does not contain header row ${headerRow}.`);
  }

  const headerSource = rows[headerRow - 1];
  if (!Array.isArray(headerSource)) {
    throw new Error(`Google sheet header row ${headerRow} is not a row array.`);
  }

  const typedHeaderSource = headerSource as unknown[];
  const headers = typedHeaderSource.map((value: unknown) =>
    value === null || value === undefined ? "" : String(value).trim(),
  );
  const populatedHeaders = headers.filter(Boolean);
  if (!populatedHeaders.length) {
    throw new Error(
      `Google sheet header row ${headerRow} does not contain any headers.`,
    );
  }

  const duplicateHeaders = populatedHeaders.filter(
    (header, index) => populatedHeaders.indexOf(header) !== index,
  );
  if (duplicateHeaders.length) {
    throw new Error(
      `Google sheet contains duplicate headers: ${duplicateHeaders.join(", ")}`,
    );
  }

  const parsedRows: ParsedSheetRow[] = [];
  let skippedRowCount = 0;
  for (let rowIndex = headerRow; rowIndex < rows.length; rowIndex += 1) {
    const sourceRow = (Array.isArray(rows[rowIndex])
      ? rows[rowIndex]
      : []) as unknown[];
    if (
      sourceRow.every((value: unknown) =>
        isGoogleSheetCellEmpty(normalizeGoogleSheetCellValue(value)),
      )
    ) {
      skippedRowCount += 1;
      continue;
    }

    const record: Record<string, unknown> = {};
    let hasValue = false;
    for (let columnIndex = 0; columnIndex < headers.length; columnIndex += 1) {
      const header = headers[columnIndex];
      if (!header) {
        continue;
      }
      const value = normalizeGoogleSheetCellValue(sourceRow[columnIndex]);
      if (!isGoogleSheetCellEmpty(value)) {
        hasValue = true;
      }
      record[header] = value;
    }

    if (!hasValue) {
      skippedRowCount += 1;
      continue;
    }

    parsedRows.push({
      row_number: rowIndex + 1,
      record,
      source_row: sourceRow,
    });
  }

  return {
    headers: populatedHeaders,
    rows: parsedRows,
    input_row_count: rows.length,
    skipped_row_count: skippedRowCount,
  };
}

export function convertGoogleSheetValuesToRows(
  values: unknown[] | undefined,
  headerRow: number,
) {
  return buildGoogleSheetValueTable(values, headerRow).rows.map(
    (item) => item.record,
  );
}

export function formatGoogleSheetA1SheetName(sheetName: string) {
  const escaped = sheetName.replace(/'/g, "''");
  return /[\s'!]/.test(sheetName) ? `'${escaped}'` : sheetName;
}

export function sheetColumnNumberToLetters(columnNumber: number) {
  let current = Math.trunc(columnNumber);
  let letters = "";
  while (current > 0) {
    const remainder = (current - 1) % 26;
    letters = String.fromCharCode(65 + remainder) + letters;
    current = Math.floor((current - 1) / 26);
  }
  if (!letters) {
    throw new Error(`Invalid Google Sheets column number: ${columnNumber}`);
  }
  return letters;
}

export function parseSheetAreaId(value: unknown) {
  const parsed = typeof value === "string" ? Number(value) : value;
  return typeof parsed === "number" &&
    Number.isInteger(parsed) &&
    parsed > 0
    ? parsed
    : null;
}
