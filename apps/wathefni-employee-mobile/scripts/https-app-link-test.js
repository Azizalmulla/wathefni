#!/usr/bin/env node
'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'wathefni-applink-'))
let passed = 0
const failures = []

function check(name, ok, detail) {
  if (ok) {
    passed += 1
    console.log(`PASS  ${name}`)
  } else {
    failures.push(name)
    console.log(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`)
  }
}

function compile() {
  const tsconfig = path.join(OUT, 'tsconfig.json')
  fs.writeFileSync(
    tsconfig,
    JSON.stringify({
      compilerOptions: {
        target: 'es2019',
        module: 'commonjs',
        moduleResolution: 'node',
        rootDir: path.join(ROOT, 'src'),
        outDir: OUT,
        esModuleInterop: true,
        skipLibCheck: true,
        strict: false,
      },
      files: [path.join(ROOT, 'src/linking/httpsAppLink.ts')],
    }),
  )
  execFileSync(path.join(ROOT, 'node_modules/.bin/tsc'), ['-p', tsconfig], { stdio: 'pipe' })
  return require(path.join(OUT, 'linking/httpsAppLink.js'))
}

const { hrefFromHttpsAppLink } = compile()
check('canonical leave HTTPS maps to /leave', hrefFromHttpsAppLink('https://api.octo-hr.com/l/leave') === '/leave')
check('canonical HR people HTTPS maps to /hr/people', hrefFromHttpsAppLink('https://api.octo-hr.com/l/hr/people') === '/hr/people')
check('legacy leave HTTPS remains supported', hrefFromHttpsAppLink('https://api.wathefni.ai/l/leave') === '/leave')
check('custom scheme preserved', hrefFromHttpsAppLink('wathefni://leave') === '/leave')
check('unknown slug fails closed', hrefFromHttpsAppLink('https://api.octo-hr.com/l/not-a-surface') === null)
check('wrong host ignored', hrefFromHttpsAppLink('https://example.com/l/leave') === null)
check('home slug maps to /', hrefFromHttpsAppLink('https://api.octo-hr.com/l') === '/')

console.log(`HTTPS_APP_LINK_TEST_${failures.length ? 'FAIL' : 'PASS'}  ${passed} passed, ${failures.length} failed`)
process.exit(failures.length ? 1 : 0)
