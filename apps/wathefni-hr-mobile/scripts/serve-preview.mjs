import { createServer } from 'node:http'
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs'
import { isIP } from 'node:net'
import { extname, join, normalize } from 'node:path'

const root = new URL('../dist-preview/', import.meta.url).pathname
const port = Number(process.env.PORT || 4177)
const host = process.env.HOST || '127.0.0.1'
const build = JSON.parse(readFileSync(new URL('../dist-preview/preview-build.json', import.meta.url), 'utf8'))
const buildMarker = String(build.marker || '').trim()
const octets = host.split('.').map(Number)
const privateLan =
  isIP(host) === 4 &&
  (octets[0] === 10 ||
    (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
    (octets[0] === 192 && octets[1] === 168))
if (host !== '127.0.0.1' && !privateLan) {
  throw new Error('HOST must be 127.0.0.1 or one explicit RFC1918 IPv4 address')
}
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error('PORT must be an unprivileged TCP port')
}
if (!buildMarker) throw new Error('Preview build marker is missing; run preview:export first')
const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

createServer((request, response) => {
  const url = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`)
  let pathname = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.(\/|\\|$))+/, '')
  let file = join(root, pathname)
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html')
  if (!existsSync(file) && existsSync(`${file}.html`)) file = `${file}.html`
  if (!existsSync(file)) file = join(root, 'index.html')
  response.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
  response.setHeader('Pragma', 'no-cache')
  response.setHeader('Expires', '0')
  response.setHeader('Service-Worker-Allowed', 'none')
  response.setHeader('X-Preview-Build', buildMarker)
  response.setHeader('Content-Type', contentTypes[extname(file)] || 'application/octet-stream')
  createReadStream(file).pipe(response)
}).listen(port, host, () => {
  console.log(`HR_PREVIEW_READY http://${host}:${port}/design-preview build=${buildMarker}`)
})
