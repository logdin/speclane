// Stub harness: runs a speclane workflow script with scripted agent() replies.
// The script body is evaluated as an async function of (args, agent, log, parallel),
// the same globals the Workflow runtime provides.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const AsyncFn = Object.getPrototypeOf(async () => {}).constructor

export function load(name) {
  const src = fs.readFileSync(path.join(ROOT, 'workflows', name), 'utf8')
  const meta = src.match(/export const meta = (\{[\s\S]*?\n\})/)
  const body = new AsyncFn('args', 'agent', 'log', 'parallel', src.replace('export const meta', 'const meta'))
  return { src, body, metaSrc: meta && meta[1] }
}

// replies: { [label]: value | (count, prompt, opts) => value }
export async function run(body, args, replies = {}) {
  const calls = [] // { label, prompt, opts, start, end }
  const counts = {}
  const logs = []
  let active = 0
  let maxActive = 0
  const agent = async (prompt, opts) => {
    const k = opts.label
    counts[k] = (counts[k] || 0) + 1
    const call = { label: k, prompt, opts }
    calls.push(call)
    active++
    maxActive = Math.max(maxActive, active)
    await new Promise((r) => setTimeout(r, 1))
    active--
    const r = replies[k]
    return typeof r === 'function' ? r(counts[k], prompt, opts) : r
  }
  const parallel = async (thunks) => Promise.all(thunks.map((t) => Promise.resolve().then(t).catch(() => null)))
  const out = await body(args, agent, (m) => logs.push(m), parallel)
  return { out, calls, labels: calls.map((c) => c.label), logs, maxActive }
}

let failed = 0
let passed = 0
export async function scenario(name, fn) {
  try {
    await fn()
    passed++
    console.log('PASS', name)
  } catch (e) {
    failed++
    console.log('FAIL', name, '-', e.message)
  }
}
export const assert = (c, m) => {
  if (!c) throw new Error(m)
}
export function summary(file) {
  console.log(`${file}: ${passed} passed, ${failed} failed`)
  if (failed) process.exitCode = 1
}

// Fixtures
export const crit = (status, text = 'c', introducedBy = null) => ({ text, status, ref: 'x:1', introducedBy })
export const pass = (id) => ({ specId: id, criteria: [crit('pass')], outOfScope: [] })
export const failG = (id, introducedBy = null) => ({ specId: id, criteria: [crit('fail', 'c', introducedBy)], outOfScope: [] })
export const worker = (lane, ids, extra = {}) => ({
  lane, completed: ids, commits: Object.fromEntries(ids.map((i) => [i, ['sha' + i]])), failedAt: null, failure: null, deviations: [], ...extra,
})
export const fixOk = (id, sha = 'fix') => ({ specId: id, ok: true, commits: [sha], failure: null, deviations: [] })
export const spec = (id, status = 'approved', commits = [], rounds = 0) => ({ specId: id, specPath: `specs/${id}.md`, files: ['f'], status, commits, rounds })
export const lane = (name, specs, dependsOn = [], workerKind = 'default') => ({ lane: name, worker: workerKind, dependsOn, specs })
