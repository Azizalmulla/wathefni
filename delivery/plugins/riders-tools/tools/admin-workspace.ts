// Admin workspace file management tools.
//
// Extracted from plugins/riders-tools/index.ts (originally lines 10163-10345)
// as part of Wave 1a of the surgical plugin split. Tool bodies are
// unchanged; only the local helpers (`workspaceRoots`,
// `ALLOWED_WORKSPACE_EXTENSIONS`, `resolveWorkspacePath`) moved in here
// with them.
//
// Dependencies used from the `deps` object:
//   - assertAdminAuthorized
//   - createTextResult
//   - errorPayload

import fs from "node:fs/promises";
import path from "node:path";

import type { ToolDeps } from "./deps";

const workspaceRoots: Record<string, URL> = {
  riders: new URL("../../../workspaces/riders", import.meta.url),
  "riders-admin": new URL("../../../workspaces/riders-admin", import.meta.url),
};

const ALLOWED_WORKSPACE_EXTENSIONS = new Set([
  ".md",
  ".json",
  ".txt",
  ".yaml",
  ".yml",
  ".csv",
  ".tsv",
]);

function resolveWorkspacePath(workspace: string, filePath: string): string {
  const root = workspaceRoots[workspace];
  if (!root) {
    throw new Error(
      `Unknown workspace: ${workspace}. Allowed: ${Object.keys(workspaceRoots).join(", ")}`,
    );
  }
  const rootDir = root.pathname.replace(/\/+$/, "");
  const resolved = path.resolve(rootDir, filePath);
  if (!resolved.startsWith(rootDir + "/") && resolved !== rootDir) {
    throw new Error("Path traversal outside workspace is not allowed.");
  }
  const ext = path.extname(resolved).toLowerCase();
  if (ext && !ALLOWED_WORKSPACE_EXTENSIONS.has(ext)) {
    throw new Error(
      `File extension ${ext} is not allowed. Allowed: ${[...ALLOWED_WORKSPACE_EXTENSIONS].join(", ")}`,
    );
  }
  return resolved;
}

export function registerAdminWorkspaceTools(api: any, deps: ToolDeps): void {
  const { assertAdminAuthorized, createTextResult, errorPayload } = deps;

  api.registerTool((ctx: any) => ({
    name: "admin_list_workspace_files",
    label: "Admin List Workspace Files",
    description:
      "List files in a Riders workspace directory. Use this to explore workspace structure before reading or editing files.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        workspace: {
          type: "string",
          description: 'Workspace name: "riders" or "riders-admin"',
        },
        subdirectory: {
          type: ["string", "null"],
          description:
            'Optional subdirectory relative to workspace root (e.g. "data")',
        },
      },
      required: ["workspace"],
    },

    async execute(
      _toolCallId: string,
      params: { workspace: string; subdirectory?: string | null },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const root = workspaceRoots[params.workspace];
        if (!root) {
          throw new Error(
            `Unknown workspace: ${params.workspace}. Allowed: ${Object.keys(workspaceRoots).join(", ")}`,
          );
        }
        const targetDir = params.subdirectory
          ? resolveWorkspacePath(params.workspace, params.subdirectory)
          : root.pathname.replace(/\/+$/, "");
        const entries = await fs.readdir(targetDir, { withFileTypes: true });
        const items = entries.map((entry) => ({
          name: entry.name,
          type: entry.isDirectory() ? "directory" : "file",
        }));
        return createTextResult(
          {
            status: "ok",
            workspace: params.workspace,
            path: params.subdirectory || "/",
            items,
          },
          { items },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_read_workspace_file",
    label: "Admin Read Workspace File",
    description:
      "Read the contents of a file in a Riders workspace. Use this to view SKILL.md, IDENTITY.md, TOOLS.md, MEMORY.md, data files, or any other workspace file.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        workspace: {
          type: "string",
          description: 'Workspace name: "riders" or "riders-admin"',
        },
        file_path: {
          type: "string",
          description:
            'File path relative to the workspace root (e.g. "SKILL.md", "data/pricing.published.json")',
        },
      },
      required: ["workspace", "file_path"],
    },

    async execute(
      _toolCallId: string,
      params: { workspace: string; file_path: string },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const resolved = resolveWorkspacePath(
          params.workspace,
          params.file_path,
        );
        const content = await fs.readFile(resolved, "utf-8");
        return createTextResult(
          {
            status: "ok",
            workspace: params.workspace,
            file_path: params.file_path,
            size_bytes: Buffer.byteLength(content, "utf-8"),
            content,
          },
          { content },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_write_workspace_file",
    label: "Admin Write Workspace File",
    description:
      "Write or update a file in a Riders workspace. Use this to edit SKILL.md, IDENTITY.md, TOOLS.md, MEMORY.md, or any workspace file. Provide the full new file content.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        workspace: {
          type: "string",
          description: 'Workspace name: "riders" or "riders-admin"',
        },
        file_path: {
          type: "string",
          description:
            'File path relative to the workspace root (e.g. "SKILL.md", "MEMORY.md")',
        },
        content: {
          type: "string",
          description: "Full new content of the file",
        },
        dry_run: {
          type: ["boolean", "null"],
          description: "If true, validate only without writing",
        },
      },
      required: ["workspace", "file_path", "content"],
    },

    async execute(
      _toolCallId: string,
      params: {
        workspace: string;
        file_path: string;
        content: string;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const resolved = resolveWorkspacePath(
          params.workspace,
          params.file_path,
        );
        let previousContent: string | null = null;
        try {
          previousContent = await fs.readFile(resolved, "utf-8");
        } catch {
          // file may not exist yet
        }
        if (!params.dry_run) {
          const dir = path.dirname(resolved);
          await fs.mkdir(dir, { recursive: true });
          await fs.writeFile(resolved, params.content, "utf-8");
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "File write validated."
              : "File updated successfully.",
            published: !params.dry_run,
            workspace: params.workspace,
            file_path: params.file_path,
            size_bytes: Buffer.byteLength(params.content, "utf-8"),
            was_new_file: previousContent === null,
          },
          {
            previous_size: previousContent
              ? Buffer.byteLength(previousContent, "utf-8")
              : null,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));
}
