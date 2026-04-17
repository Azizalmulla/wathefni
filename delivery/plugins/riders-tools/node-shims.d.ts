declare module "node:fs/promises" {
  const fsPromises: {
    readFile: (path: string | URL, encoding: string) => Promise<string>;
    writeFile: (path: string | URL, data: string, encoding: string) => Promise<void>;
    stat: (path: string | URL) => Promise<unknown>;
    readdir: (path: string | URL, options?: { withFileTypes?: boolean }) => Promise<{ name: string; isDirectory: () => boolean; isFile: () => boolean }[]>;
    mkdir: (path: string | URL, options?: { recursive?: boolean }) => Promise<string | undefined>;
  };

  export default fsPromises;
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
