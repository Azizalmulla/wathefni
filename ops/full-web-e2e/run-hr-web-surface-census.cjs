/**
 * HR Web Surface Census — build-time coverage gate.
 * Fails if Page union / nav / PostHire / ?page= destinations drift from the registry.
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..', '..')
const DASH = path.join(ROOT, 'apps/wathefni-dashboard/src')
const REGISTRY = path.join(DASH, 'lib/hrWebSurfaceRegistry.ts')

function read(file) {
  return fs.readFileSync(file, 'utf8')
}

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    if (['node_modules', 'dist', 'coverage'].includes(name)) continue
    const full = path.join(dir, name)
    if (fs.statSync(full).isDirectory()) walk(full, out)
    else if (/\.(tsx?|jsx?)$/.test(name) && !/\.(test|spec)\./.test(name)) out.push(full)
  }
  return out
}

function pageUnion() {
  const text = read(path.join(DASH, 'types.ts'))
  const block = text.slice(text.indexOf('export type Page ='), text.indexOf('export type ChatMessage'))
  return [...block.matchAll(/'([a-z0-9-]+)'/g)].map((m) => m[1])
}

function navIds() {
  const text = read(path.join(DASH, 'lib/hrWebNavCatalog.ts'))
  const block = text.slice(text.indexOf('const PAGE_ICONS'), text.indexOf('export const DASHBOARD_NAV_CATALOG'))
  return [...block.matchAll(/^\s+'?([a-z0-9-]+)'?: /gm)].map((m) => m[1])
}

function postHireCases() {
  const text = read(path.join(DASH, 'posthire/PostHireDispatcher.tsx'))
  const start = text.indexOf('switch (page)')
  return [...text.slice(start, start + 8000).matchAll(/case '([a-z0-9-]+)':/g)].map((m) => m[1])
}

function queryPages() {
  const found = new Set()
  for (const file of walk(DASH)) {
    const text = read(file)
    for (const match of text.matchAll(/[?&]page=([a-z0-9-]+)/g)) found.add(match[1])
    for (const match of text.matchAll(/opsHref: '\/dashboard\?page=([a-z0-9-]+)/g)) found.add(match[1])
  }
  return [...found]
}

function fail(message) {
  console.error(`HR_WEB_SURFACE_CENSUS_FAIL  ${message}`)
  process.exit(1)
}

if (!fs.existsSync(REGISTRY)) fail('hrWebSurfaceRegistry.ts missing')
const registry = read(REGISTRY)
function covered(id) {
  return registry.includes(`page.${id}`) || registry.includes(`page: '${id}'`) || registry.includes(`page=${id}`)
}

const missing = []
for (const page of pageUnion()) {
  if (!covered(page)) missing.push(`page:${page}`)
}
for (const nav of navIds()) {
  if (!covered(nav)) missing.push(`nav:${nav}`)
}
for (const page of postHireCases()) {
  if (!covered(page)) missing.push(`posthire:${page}`)
}
for (const dest of queryPages()) {
  if (!covered(dest) && !registry.includes(`'${dest}'`)) missing.push(`query:${dest}`)
}

if (missing.length) fail(`unregistered destinations: ${missing.join(', ')}`)
if (!registry.includes('HR_WEB_SURFACE_EXCLUSIONS')) fail('exclusions list missing')
if (!registry.includes('employee_app')) fail('employee_app exclusion missing')

console.log(`HR_WEB_SURFACE_CENSUS_PASS  ${pageUnion().length} pages, ${navIds().length} nav items`)
