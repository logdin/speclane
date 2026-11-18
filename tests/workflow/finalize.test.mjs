// Stub-harness tests for workflows/finalize.js and workflows/review-plan.js.
import { load, run, scenario, assert, summary } from './harness.mjs'

const fin = load('finalize.js')
const rp = load('review-plan.js')
const R = (s) => ({ summary: s, findings: [] })

await scenario('finalize meta: name finalize-agents, Verify phase pinned', async () => {
  assert(/name: 'finalize-agents'/.test(fin.metaSrc) && /model: 'claude-opus-4-6'/.test(fin.metaSrc), fin.metaSrc)
})

await scenario('finalize: reviewers in parallel, attributed by position, dead one dropped, no verify', async () => {
  const args = { workItem: 'w', agents: [{ type: 'a', scope: 'SPEC-001', prompt: 'p1' }, { type: 'b', scope: 'SPEC-002', prompt: 'p2' }, { type: 'c', scope: 'SPEC-003', prompt: 'p3' }] }
  const { out, calls, maxActive, logs } = await run(fin.body, args, { 'a:SPEC-001': R('A'), 'b:SPEC-002': undefined, 'c:SPEC-003': R('C') })
  assert(maxActive === 3, 'not parallel: ' + maxActive)
  assert(out.reviews.map((r) => `${r.agent}/${r.scope}/${r.summary}`).join() === 'a/SPEC-001/A,c/SPEC-003/C', JSON.stringify(out))
  assert(out.verify === null && !calls.some((c) => c.label.startsWith('verify')), 'verify ran')
  assert(calls.every((c) => !('model' in c.opts) && c.opts.agentType === c.label.split(':')[0]), 'reviewer opts')
  assert(logs.some((l) => l.includes('No result from: b:SPEC-002')), 'dead not logged')
})

await scenario('finalize: verify runs pinned claude-opus-4-6 on general-purpose with the strict preamble', async () => {
  const args = { workItem: 'w', agents: [{ type: 'a', scope: 'S', prompt: 'p' }], verify: { brief: 'BRIEF-X' } }
  const { out, calls } = await run(fin.body, args, { 'a:S': R('A'), 'verify:claude-opus-4-6': { verdict: 'APPROVE', findings: [] } })
  const v = calls.find((c) => c.label === 'verify:claude-opus-4-6')
  assert(v && v.opts.model === 'claude-opus-4-6' && v.opts.agentType === 'general-purpose' && v.opts.phase === 'Verify', JSON.stringify(v && v.opts))
  assert(v.prompt.includes('STRICT completeness') && v.prompt.endsWith('BRIEF-X'), 'prompt')
  assert(out.verify.verdict === 'APPROVE' && out.reviews.length === 1, JSON.stringify(out))
})

await scenario('finalize: verify only (no reviewers) still runs; verifier with no result -> null', async () => {
  const { out, calls } = await run(fin.body, { workItem: 'w', agents: [], verify: { brief: 'b' } }, {})
  assert(calls.length === 1 && out.verify === null && out.reviews.length === 0, JSON.stringify(out))
})

await scenario('finalize: nothing passed -> { reviews: [], verify: null }, no calls', async () => {
  const { out, calls } = await run(fin.body, { workItem: 'w' }, {})
  assert(calls.length === 0 && JSON.stringify(out) === '{"reviews":[],"verify":null}', JSON.stringify(out))
})

await scenario('review-plan: meta name, parallel, model only when passed, attributed', async () => {
  assert(/name: 'review-plan-agents'/.test(rp.metaSrc), 'meta')
  const args = { planFile: 'p.md', plan: 'PLAN', reviewers: [{ type: 'x', brief: 'BX' }, { type: 'y', brief: 'BY', model: 'opus', effort: 'high' }] }
  const F = (v) => ({ verdict: v, findings: [], questions: [] })
  const { out, calls, maxActive } = await run(rp.body, args, { 'review:x': F('APPROVE'), 'review:y': F('REQUEST_CHANGES') })
  assert(maxActive === 2, 'parallel')
  const x = calls.find((c) => c.label === 'review:x'), y = calls.find((c) => c.label === 'review:y')
  assert(!('model' in x.opts) && y.opts.model === 'opus' && y.opts.effort === 'high', 'model opts')
  assert(x.prompt.startsWith('BX') && x.prompt.includes('File: p.md') && x.prompt.endsWith('PLAN'), 'prompt')
  assert(out.map((r) => r.agent + ':' + r.verdict).join() === 'x:APPROVE,y:REQUEST_CHANGES', JSON.stringify(out))
})

await scenario('review-plan: no reviewers -> []', async () => {
  const { out, calls } = await run(rp.body, { planFile: 'p', plan: '' }, {})
  assert(calls.length === 0 && Array.isArray(out) && out.length === 0, 'out')
})

summary('finalize.test.mjs')
