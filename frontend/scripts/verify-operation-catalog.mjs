import { execFile } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { promisify } from 'node:util'

const source = await readFile(new URL('../src/api/operation-catalog.ts', import.meta.url), 'utf8')
const execFileAsync = promisify(execFile)
const requiredGroups = ['auth', 'crm', 'profile', 'chat', 'student', 'reports', 'reportData']

for (const group of requiredGroups) {
  if (!source.includes(`group: '${group}'`)) {
    throw new Error(`missing API operation group: ${group}`)
  }
}

const catalogEntries = [...source.matchAll(/operation\(\{\s*operationId:[\s\S]*?method: '(GET|POST|PUT|PATCH|DELETE)', path: '([^']+)'/g)]
  .map(([, method, path]) => `${method} ${path}`)
const operationCount = catalogEntries.length

if (!source.includes("operationId: 'profile-upload'") || !source.includes("requestKind: 'multipart'")) {
  throw new Error('profile upload must be mapped as a multipart operation')
}

if (!source.includes("operationId: 'daily-summary'") || !source.includes('defaultQuery: { report_date:')) {
  throw new Error('daily report summary must provide its required report_date query field')
}

const { stdout } = await execFileAsync('python', ['-c', `
from main import app
import json
excluded = ('/api/v1/dify/', '/api/v1/chat/', '/api/v1/courses', '/api/v1/events')
items = []
for path, methods in app.openapi()['paths'].items():
    if path.startswith(excluded):
        continue
    for method in methods:
        clean_path = path.removeprefix('/api/v1')
        items.append(f"{method.upper()} {clean_path}")
print(json.dumps(sorted(items)))
`], { cwd: new URL('../..', import.meta.url) })
const expectedEntries = JSON.parse(stdout)
const missing = expectedEntries.filter((item) => !catalogEntries.includes(item))
const unexpected = catalogEntries.filter((item) => !expectedEntries.includes(item))

if (missing.length || unexpected.length) {
  throw new Error(`OpenAPI mapping mismatch. missing=${missing.join(', ') || 'none'}; unexpected=${unexpected.join(', ') || 'none'}`)
}

console.log(`operation catalog verified: ${operationCount} operations`)
