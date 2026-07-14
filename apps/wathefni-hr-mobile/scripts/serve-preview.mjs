import { createServer } from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'

const root = new URL('../dist-preview/', import.meta.url).pathname
const port = Number(process.env.PORT || 4177)
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
  response.setHeader('Content-Type', contentTypes[extname(file)] || 'application/octet-stream')
  createReadStream(file).pipe(response)
}).listen(port, '127.0.0.1', () => {
  console.log(`HR_PREVIEW_READY http://127.0.0.1:${port}/design-preview`)
})
