#!/usr/bin/env node

const fs = require('node:fs')
const Module = require('node:module')
const path = require('node:path')
const ts = require('typescript')

const sourcePath = path.resolve(__dirname, '../src/branding/CompanyBrand.tsx')
const output = ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
  compilerOptions: {
    esModuleInterop: true,
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
  fileName: sourcePath,
}).outputText

const loaded = new Module(sourcePath)
loaded.filename = sourcePath
loaded.paths = Module._nodeModulePaths(path.dirname(sourcePath))
loaded._compile(output, sourcePath)

const { resolveCompanyBrand } = loaded.exports
let checks = 0

function check(label, condition) {
  checks += 1
  if (!condition) throw new Error(`COMPANY_BRAND_RUNTIME_FAILED: ${label}`)
}

const unresolved = resolveCompanyBrand(null, 'en')
check('unresolved tenant name', unresolved.name === 'OctoHR')
check('unresolved tenant has no logo', unresolved.logoUrl === null)
check('unresolved tenant is platform identity', unresolved.isTenantBrand === false)

const tenant = {
  company_code: 'ACME',
  display_name: 'Acme Global',
  display_name_en: 'Acme Company',
  display_name_ar: 'شركة أكمي',
  logo_url: 'https://cdn.example.com/acme.png',
}
const english = resolveCompanyBrand(tenant, 'en')
check('English uses English company name', english.name === 'Acme Company')
check('English keeps safe company logo', english.logoUrl === tenant.logo_url)
check('English identifies tenant branding', english.isTenantBrand === true)

const arabic = resolveCompanyBrand(tenant, 'ar')
check('Arabic uses Arabic company name', arabic.name === 'شركة أكمي')
check('Arabic keeps safe company logo', arabic.logoUrl === tenant.logo_url)
check('Arabic identifies tenant branding', arabic.isTenantBrand === true)

const legacy = resolveCompanyBrand({
  company_code: 'LEGACY',
  display_name: 'Wathefni',
  display_name_en: 'WATHEFNI',
  display_name_ar: 'وظفني',
  logo_url: 'http://cdn.example.com/legacy.png',
}, 'ar')
check('legacy tenant name falls back to OctoHR', legacy.name === 'OctoHR')
check('legacy tenant does not expose an unsafe logo', legacy.logoUrl === null)
check('legacy tenant is not presented as tenant branding', legacy.isTenantBrand === false)

const credentialedLogo = resolveCompanyBrand({
  company_code: 'ACME',
  display_name_en: 'Acme Company',
  logo_url: 'https://user:secret@cdn.example.com/acme.png',
}, 'en')
check('credentialed logo URL fails closed', credentialedLogo.logoUrl === null)

console.log(`COMPANY_BRAND_RUNTIME_CHECKS=${checks}`)
console.log('COMPANY_BRAND_RUNTIME_PASS')
