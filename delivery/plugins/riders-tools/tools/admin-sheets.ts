// Generic gog-backed Google Sheets admin tools.
//
// Extracted from plugins/riders-tools/index.ts (originally lines 9611-10038)
// as part of Wave 1a of the surgical plugin split. Tool bodies are
// unchanged. All external state is passed through the shared `deps`
// object built inside register().
//
// Tools registered:
//   - admin_fetch_google_sheet_rows
//   - admin_fetch_google_sheet_metadata
//   - admin_update_google_sheet_values
//   - admin_batch_update_google_sheet
//   - admin_clear_google_sheet_values
//   - admin_append_google_sheet_rows
//   - admin_delete_google_sheet_rows

import type { ToolDeps } from "./deps";

export function registerAdminSheetsTools(api: any, deps: ToolDeps): void {
  const {
    assertPricingAdminAuthorized,
    createTextResult,
    errorPayload,
    isRecord,
    runGogJsonCommand,
    getPricingGoogleSheetSpreadsheetId,
    getPricingGoogleSheetName,
  } = deps;

  api.registerTool((ctx: any) => ({
    name: "admin_fetch_google_sheet_rows",
    label: "Admin Fetch Google Sheet Rows",
    description:
      "Fetch rows from any Google Sheet range using gog. Defaults to the Riders pricing spreadsheet and tab when omitted. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        range: {
          type: ["string", "null"],
          description:
            "A1 range notation (e.g. 'Sheet1!A1:K50'). Defaults to the full pricing tab.",
        },
      },
    },

    async execute(
      _toolCallId: string,
      params: { spreadsheet_id?: string | null; range?: string | null },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        const range =
          params.range?.trim() || getPricingGoogleSheetName().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");
        if (!range) throw new Error("range is required.");

        const payload = await runGogJsonCommand(
          ["sheets", "get", spreadsheetId, range, "--json"],
          "gog sheets get",
        );
        const root = isRecord(payload) ? payload : {};
        const values = Array.isArray(root.values) ? root.values : [];
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            range,
            row_count: values.length,
            values,
          },
          { raw: root },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_fetch_google_sheet_metadata",
    label: "Admin Fetch Google Sheet Metadata",
    description:
      "Fetch header row and row count from a Google Sheet tab using gog. Defaults to the Riders pricing spreadsheet and tab. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        sheet_name: {
          type: ["string", "null"],
          description: "Tab name. Defaults to the Riders pricing tab.",
        },
      },
    },

    async execute(
      _toolCallId: string,
      params: { spreadsheet_id?: string | null; sheet_name?: string | null },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        const sheetName =
          params.sheet_name?.trim() || getPricingGoogleSheetName().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");
        if (!sheetName) throw new Error("sheet_name is required.");

        const payload = await runGogJsonCommand(
          ["sheets", "get", spreadsheetId, sheetName, "--json"],
          "gog sheets get (metadata)",
        );
        const root = isRecord(payload) ? payload : {};
        const values = Array.isArray(root.values) ? root.values : [];
        const headers =
          values.length > 0 && Array.isArray(values[0]) ? values[0] : [];
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            sheet_name: sheetName,
            total_rows: values.length,
            data_rows: Math.max(0, values.length - 1),
            headers,
            header_count: headers.length,
          },
          { raw: root },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_update_google_sheet_values",
    label: "Admin Update Google Sheet Values",
    description:
      "Update a range in a Google Sheet with new values using gog. Defaults to the Riders pricing spreadsheet. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        range: {
          type: "string",
          description: "A1 range notation (e.g. 'Sheet1!A2:K2').",
        },
        values: {
          type: "array",
          description: "2D array of cell values.",
          items: { type: "array", items: {} },
        },
      },
      required: ["range", "values"],
    },

    async execute(
      _toolCallId: string,
      params: {
        spreadsheet_id?: string | null;
        range: string;
        values: unknown[][];
      },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");

        const payload = await runGogJsonCommand(
          [
            "sheets",
            "update",
            spreadsheetId,
            params.range,
            "--values-json",
            JSON.stringify(params.values),
            "--input",
            "USER_ENTERED",
            "--json",
          ],
          "gog sheets update",
        );
        const root = isRecord(payload) ? payload : {};
        const updates = isRecord(root.updates) ? root.updates : root;
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            range: params.range,
            updatedRange: updates.updatedRange ?? root.updatedRange ?? null,
            updatedRows: updates.updatedRows ?? root.updatedRows ?? null,
            updatedCells: updates.updatedCells ?? root.updatedCells ?? null,
          },
          { raw: root },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_batch_update_google_sheet",
    label: "Admin Batch Update Google Sheet",
    description:
      "Apply multiple range updates to a Google Sheet in sequence using gog. Each item has a range and a 2D values array. Defaults to the Riders pricing spreadsheet. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        updates: {
          type: "array",
          description: "Array of {range, values} objects to apply in order.",
          items: {
            type: "object",
            additionalProperties: false,
            properties: {
              range: { type: "string" },
              values: {
                type: "array",
                items: { type: "array", items: {} },
              },
            },
            required: ["range", "values"],
          },
        },
      },
      required: ["updates"],
    },

    async execute(
      _toolCallId: string,
      params: {
        spreadsheet_id?: string | null;
        updates: Array<{ range: string; values: unknown[][] }>;
      },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");
        if (!params.updates?.length)
          throw new Error("updates array must not be empty.");

        const results: Array<{ range: string; updatedCells: unknown }> = [];
        for (const item of params.updates) {
          const payload = await runGogJsonCommand(
            [
              "sheets",
              "update",
              spreadsheetId,
              item.range,
              "--values-json",
              JSON.stringify(item.values),
              "--input",
              "USER_ENTERED",
              "--json",
            ],
            "gog sheets update (batch)",
          );
          const root = isRecord(payload) ? payload : {};
          const updates = isRecord(root.updates) ? root.updates : root;
          results.push({
            range: item.range,
            updatedCells: updates.updatedCells ?? root.updatedCells ?? null,
          });
        }
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            batch_size: results.length,
            results,
          },
          { results },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_clear_google_sheet_values",
    label: "Admin Clear Google Sheet Values",
    description:
      "Clear a range of cells in a Google Sheet using gog (values removed, cells remain). Defaults to the Riders pricing spreadsheet. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        range: {
          type: "string",
          description: "A1 range notation (e.g. 'Sheet1!A5:K5').",
        },
      },
      required: ["range"],
    },

    async execute(
      _toolCallId: string,
      params: { spreadsheet_id?: string | null; range: string },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");

        const payload = await runGogJsonCommand(
          ["sheets", "clear", spreadsheetId, params.range, "--json"],
          "gog sheets clear",
        );
        const root = isRecord(payload) ? payload : {};
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            range: params.range,
            clearedRange: root.clearedRange ?? root.range ?? params.range,
          },
          { raw: root },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_append_google_sheet_rows",
    label: "Admin Append Google Sheet Rows",
    description:
      "Append rows to the end of a Google Sheet table using gog. Defaults to the Riders pricing spreadsheet and tab. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        range: {
          type: ["string", "null"],
          description:
            "A1 range notation for the table. Defaults to the pricing tab.",
        },
        values: {
          type: "array",
          description: "2D array of row values to append.",
          items: { type: "array", items: {} },
        },
      },
      required: ["values"],
    },

    async execute(
      _toolCallId: string,
      params: {
        spreadsheet_id?: string | null;
        range?: string | null;
        values: unknown[][];
      },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        const range =
          params.range?.trim() || getPricingGoogleSheetName().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");
        if (!range) throw new Error("range is required.");

        const payload = await runGogJsonCommand(
          [
            "sheets",
            "append",
            spreadsheetId,
            range,
            "--values-json",
            JSON.stringify(params.values),
            "--input",
            "USER_ENTERED",
            "--json",
          ],
          "gog sheets append",
        );
        const root = isRecord(payload) ? payload : {};
        const updates = isRecord(root.updates) ? root.updates : root;
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            range,
            updatedRange: updates.updatedRange ?? root.updatedRange ?? null,
            updatedRows: updates.updatedRows ?? root.updatedRows ?? null,
            updatedCells: updates.updatedCells ?? root.updatedCells ?? null,
          },
          { raw: root },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_delete_google_sheet_rows",
    label: "Admin Delete Google Sheet Rows",
    description:
      "Delete (clear) one or more rows in a Google Sheet using gog. This clears the cell values but does not remove the row from the sheet. Use the range parameter to target specific rows. Defaults to the Riders pricing spreadsheet. Only for allowlisted admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        spreadsheet_id: {
          type: ["string", "null"],
          description:
            "Google Sheets spreadsheet ID. Defaults to the Riders pricing spreadsheet.",
        },
        sheet_name: {
          type: ["string", "null"],
          description: "Tab name. Defaults to the pricing tab.",
        },
        start_row: {
          type: "integer",
          description: "1-indexed first row number to delete.",
        },
        end_row: {
          type: ["integer", "null"],
          description:
            "1-indexed last row number to delete (inclusive). Defaults to start_row.",
        },
      },
      required: ["start_row"],
    },

    async execute(
      _toolCallId: string,
      params: {
        spreadsheet_id?: string | null;
        sheet_name?: string | null;
        start_row: number;
        end_row?: number | null;
      },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const spreadsheetId =
          params.spreadsheet_id?.trim() ||
          getPricingGoogleSheetSpreadsheetId().trim();
        const sheetName =
          params.sheet_name?.trim() || getPricingGoogleSheetName().trim();
        if (!spreadsheetId) throw new Error("spreadsheet_id is required.");
        if (!sheetName) throw new Error("sheet_name is required.");
        const startRow = params.start_row;
        const endRow = params.end_row ?? startRow;
        if (startRow < 1 || endRow < startRow)
          throw new Error("Invalid row range.");

        const cleared: string[] = [];
        for (let row = startRow; row <= endRow; row++) {
          const range = `${sheetName}!A${row}:ZZ${row}`;
          await runGogJsonCommand(
            ["sheets", "clear", spreadsheetId, range, "--json"],
            `gog sheets clear row ${row}`,
          );
          cleared.push(range);
        }
        return createTextResult(
          {
            status: "ok",
            spreadsheet_id: spreadsheetId,
            sheet_name: sheetName,
            rows_cleared: cleared.length,
            cleared_ranges: cleared,
          },
          { cleared },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));
}
