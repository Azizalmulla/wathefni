// Minimal Node.js built-in type declarations for `plugins/shared/`.
//
// The project does NOT depend on `@types/node`; each plugin that
// touches Node built-ins declares a narrow shim that covers exactly
// what its sources need. `plugins/octopus-channel/` and
// `plugins/riders-tools/` already have their own shims; this file is
// the equivalent for `plugins/shared/` so shared modules that touch
// `fs` / `path` / `url` type-check standalone (e.g. from smoke tests
// that invoke `tsc` on a single source file).
//
// Keep this narrow — only add declarations that the shared modules
// actually use. If you find yourself adding broad `any` shapes, stop
// and reach for the existing octopus-channel or riders-tools shim
// instead.

declare module "node:fs" {
  export const promises: {
    readFile: (path: string | URL, encoding: string) => Promise<string>;
    writeFile: (path: string | URL, data: string, encoding: string) => Promise<void>;
    appendFile: (path: string | URL, data: string, encoding: string) => Promise<void>;
    stat: (path: string | URL) => Promise<unknown>;
    mkdir: (
      path: string | URL,
      options?: { recursive?: boolean },
    ) => Promise<string | undefined>;
  };
}

declare module "node:path" {
  const pathModule: {
    resolve: (...segments: string[]) => string;
    dirname: (p: string) => string;
    extname: (p: string) => string;
    join: (...segments: string[]) => string;
    basename: (p: string, ext?: string) => string;
  };
  export default pathModule;
}

declare module "node:url" {
  const urlModule: {
    fileURLToPath: (url: string | URL) => string;
    pathToFileURL: (path: string) => URL;
  };
  export default urlModule;
  export const fileURLToPath: (url: string | URL) => string;
  export const pathToFileURL: (path: string) => URL;
}
