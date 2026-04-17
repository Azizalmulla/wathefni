declare module "openclaw/plugin-sdk/core" {
  export type OpenClawConfig = any;
  export type ChannelPlugin<ResolvedAccount = any, Probe = unknown, Audit = unknown> = any;
  export type OpenClawPluginApi = any;
  export function emptyPluginConfigSchema(): any;
}

declare module "node:fs" {
  export const promises: any;
}

declare module "node:path" {
  const path: any;
  export default path;
}
