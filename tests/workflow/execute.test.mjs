// Stub-harness tests for workflows/execute.js.
// Ports the v5 checks: SPEC-004 (serial scheduler), SPEC-006 (converge + fix rounds),
// the post-merge follow-up (untestable is not a pass, ITEMS_RULE), plus speclane's settings plumbing.
import { load, run, scenario, assert, summary, crit, pass, failG, worker, fixOk, spec, lane } from './harness.mjs'

const { body, metaSrc } = load('execute.js')
const all = (ids) => Object.fromEntries(ids.map((id) => [`converge:${id}`, pass(id)]))

// ---------------------------------------------------------------- meta
await scenario('meta: name is execute-lanes (must not collide with the execute skill), phases present', async () => {
  assert(/name: 'execute-lanes'/.test(metaSrc), 'meta.name')
  assert(/title: 'Converge'/.test(metaSrc) && /title: 'Implement'/.test(metaSrc) && /title: 'Fix'/.test(metaSrc), 'phases')
})

// ---------------------------------------------------------------- SPEC-004 serial scheduler
await scenario('SPEC-004/1: topological order T->A->B->C, max concurrency 1', async () => {
  const lanes = [lane('C', [spec('S-C')], ['B']), lane('B', [spec('S-B')], ['A']), lane('A', [spec('S-A')], ['T']), lane('T', [spec('S-T')])]
  const replies = { ...all(['S-A', 'S-B', 'S-C', 'S-T']) }
  for (const n of ['A', 'B', 'C', 'T']) replies[`lane:${n}`] = worker(n, [`S-${n}`])
  const { out, labels, maxActive } = await run(body, { workItem: 'w', lanes }, replies)
  const order = labels.filter((l) => l.startsWith('lane:')).join()
  assert(order === 'lane:T,lane:A,lane:B,lane:C', 'order ' + order)
  assert(maxActive === 1, 'concurrency ' + maxActive)
  assert(out.lanes.every((l) => l.finished), 'not all finished')
})

await scenario('SPEC-004/2: B fails -> C and D skipped, A and E run', async () => {
  const lanes = [lane('A', [spec('S-A')]), lane('B', [spec('S-B')], ['A']), lane('C', [spec('S-C')], ['B']), lane('D', [spec('S-D')], ['C']), lane('E', [spec('S-E')])]
  const replies = {
    ...all(['S-A', 'S-E']),
    'lane:A': worker('A', ['S-A']), 'lane:E': worker('E', ['S-E']),
    'lane:B': { lane: 'B', completed: [], commits: {}, failedAt: 'S-B', failure: 'tests failed', deviations: [] },
  }
  const { out, labels } = await run(body, { workItem: 'w', lanes }, replies)
  assert(!labels.includes('lane:C') && !labels.includes('lane:D'), 'C/D ran')
  assert(labels.includes('lane:A') && labels.includes('lane:E'), 'A/E did not run')
  assert(out.skipped.map((s) => s.lane).sort().join() === 'C,D', 'skipped ' + JSON.stringify(out.skipped))
  const B = out.lanes.find((l) => l.lane === 'B')
  assert(B.failedAt === 'S-B' && !B.finished, 'B state')
})

await scenario('SPEC-004/3: a cycle runs nothing and names the cycle', async () => {
  const lanes = [lane('A', [spec('S-A')], ['B']), lane('B', [spec('S-B')], ['A']), lane('C', [spec('S-C')])]
  const { out, calls } = await run(body, { workItem: 'w', lanes }, {})
  assert(calls.length === 0, 'agents ran')
  assert(out.skipped.length === 3 && out.skipped.every((s) => /lane cycle: A -> B -> A/.test(s.reason)), JSON.stringify(out.skipped))
})

await scenario('SPEC-004/4: absent dependency lane skips only that lane and its dependents', async () => {
  const lanes = [lane('A', [spec('S-A')], ['Z']), lane('B', [spec('S-B')], ['A']), lane('C', [spec('S-C')])]
  const { out, labels } = await run(body, { workItem: 'w', lanes }, { ...all(['S-C']), 'lane:C': worker('C', ['S-C']) })
  assert(labels.join() === 'lane:C,converge:S-C', 'calls ' + labels)
  assert(out.skipped.find((s) => s.lane === 'A').reason.includes('not runnable: Z'), 'A reason')
  assert(out.skipped.find((s) => s.lane === 'B').reason.includes('A did not finish'), 'B reason')
})

await scenario('SPEC-004/5: sonnet lane passes model sonnet to worker and fix; default lane passes none', async () => {
  const lanes = [lane('A', [spec('S-A')], [], 'sonnet'), lane('B', [spec('S-B')])]
  const replies = {
    'lane:A': worker('A', ['S-A']), 'lane:B': worker('B', ['S-B']),
    'converge:S-A': (n) => (n === 1 ? failG('S-A') : pass('S-A')), 'fix:S-A:1': fixOk('S-A'), ...all(['S-B']),
  }
  const { calls } = await run(body, { workItem: 'w', lanes }, replies)
  const by = (l) => calls.find((c) => c.label === l).opts
  assert(by('lane:A').model === 'sonnet' && by('fix:S-A:1').model === 'sonnet', 'sonnet lane model')
  assert(!('model' in by('lane:B')), 'default lane model')
})

await scenario('SPEC-004/6: worker prompt rules (skip committed, exact trailer, stop at first failure, contract)', async () => {
  const { calls } = await run(body, { workItem: 'demo', lanes: [lane('A', [spec('S-1')])] }, { 'lane:A': worker('A', ['S-1']), ...all(['S-1']) })
  const p = calls.find((c) => c.label === 'lane:A').prompt
  for (const w of ['SKIP it if it already has a commit', 'exactly "demo/<specId>"', 'STOP at the first spec you cannot make pass', 'Worker contract', 'never discard or stash work'])
    assert(p.includes(w), 'missing: ' + w)
})

// ---------------------------------------------------------------- SPEC-006 converge
await scenario('SPEC-006/1: all pass -> lane finished, dependent lane runs', async () => {
  const lanes = [lane('A', [spec('A1'), spec('A2')]), lane('B', [spec('B1')], ['A'])]
  const { out, labels } = await run(body, { workItem: 'w', lanes }, { 'lane:A': worker('A', ['A1', 'A2']), 'lane:B': worker('B', ['B1']), ...all(['A1', 'A2', 'B1']) })
  assert(out.lanes[0].finished && labels.includes('lane:B'), 'B did not run')
})

await scenario('SPEC-006/2: A1 fails once -> fix:A1, commits +1, A1 and A2 re-converged, rounds 1', async () => {
  const replies = { 'lane:A': worker('A', ['A1', 'A2']), 'converge:A1': (n) => (n === 1 ? failG('A1') : pass('A1')), 'converge:A2': pass('A2'), 'fix:A1:1': fixOk('A1', 'fix3') }
  const { out, labels } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1'), spec('A2')])] }, replies)
  assert(labels.join() === 'lane:A,converge:A1,fix:A1:1,converge:A1,converge:A2', labels.join())
  const A = out.lanes[0]
  assert(A.commits.A1.join() === 'shaA1,fix3' && A.converge.A1.rounds === 1 && A.finished, JSON.stringify(A.converge))
})

await scenario('SPEC-006/3: introducedBy A2 -> fix goes to A2, round counts on A2', async () => {
  const replies = { 'lane:A': worker('A', ['A1', 'A2']), 'converge:A1': (n) => (n === 1 ? failG('A1', 'A2') : pass('A1')), 'converge:A2': pass('A2'), 'fix:A2:1': fixOk('A2') }
  const { out, labels } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1'), spec('A2')])] }, replies)
  assert(labels.includes('fix:A2:1') && !labels.some((l) => l.startsWith('fix:A1')), labels.join())
  assert(out.lanes[0].converge.A1.rounds === 0 && out.lanes[0].converge.A2.rounds === 1, JSON.stringify(out.lanes[0].converge))
})

await scenario('SPEC-006/4: always failing -> 3 converges, 2 fixes, blocked; A2 ungraded; C skipped; B runs', async () => {
  const lanes = [lane('A', [spec('A1'), spec('A2')]), lane('B', [spec('B1')]), lane('C', [spec('C1')], ['A'])]
  const replies = { 'lane:A': worker('A', ['A1', 'A2']), 'converge:A1': failG('A1'), 'fix:A1:1': fixOk('A1'), 'fix:A1:2': fixOk('A1'), 'lane:B': worker('B', ['B1']), ...all(['B1']) }
  const { out, labels } = await run(body, { workItem: 'w', lanes }, replies)
  assert(labels.filter((l) => l === 'converge:A1').length === 3 && labels.filter((l) => l.startsWith('fix:A1')).length === 2, labels.join())
  const A = out.lanes.find((l) => l.lane === 'A')
  assert(A.blocked[0].specId === 'A1' && A.blocked[0].reason.startsWith('converge failed 3 rounds'), JSON.stringify(A.blocked))
  assert(!labels.includes('converge:A2'), 'A2 graded')
  assert(out.skipped.some((s) => s.lane === 'C') && labels.includes('lane:B'), 'C/B')
})

await scenario('SPEC-006/5: committed A1 is converged before the worker; worker prompt omits A1', async () => {
  const replies = { 'lane:A': worker('A', ['A2']), ...all(['A1', 'A2']) }
  const { labels, calls } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1', 'committed', ['c1']), spec('A2')])] }, replies)
  assert(labels.join() === 'converge:A1,lane:A,converge:A2', labels.join())
  assert(!calls.find((c) => c.label === 'lane:A').prompt.includes('A1:'), 'prompt lists A1')
})

await scenario('SPEC-006/6: cap hit before the worker -> worker never called, A2 notRun', async () => {
  const { out, labels } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1', 'committed', ['c1'], 2), spec('A2')])] }, { 'converge:A1': failG('A1') })
  assert(!labels.includes('lane:A'), 'worker ran')
  assert(out.lanes[0].notRun.join() === 'A2' && out.lanes[0].blocked[0].specId === 'A1', JSON.stringify(out.lanes[0]))
})

await scenario('SPEC-006/7: an out-of-scope path fails the spec and triggers a fix', async () => {
  const replies = { 'lane:A': worker('A', ['A1']), 'converge:A1': (n) => ({ specId: 'A1', criteria: [crit('pass')], outOfScope: n === 1 ? ['x.ts'] : [] }), 'fix:A1:1': fixOk('A1') }
  const { out, labels, calls } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1')])] }, replies)
  assert(labels.includes('fix:A1:1') && out.lanes[0].finished, labels.join())
  assert(calls.find((c) => c.label === 'fix:A1:1').prompt.includes('OUT OF SCOPE: x.ts'), 'fix prompt')
})

await scenario('SPEC-006/8: dispatch shape (converge speclane:converge / no model / high; workers general-purpose / medium)', async () => {
  const replies = { 'lane:A': worker('A', ['A1']), 'converge:A1': (n) => (n === 1 ? failG('A1') : pass('A1')), 'fix:A1:1': fixOk('A1') }
  const { calls } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1')], [], 'sonnet')] }, replies)
  const c = calls.find((x) => x.label === 'converge:A1').opts
  assert(c.agentType === 'speclane:converge' && !('model' in c) && c.effort === 'high' && c.phase === 'Converge', JSON.stringify(c))
  for (const l of ['lane:A', 'fix:A1:1']) {
    const o = calls.find((x) => x.label === l).opts
    assert(o.agentType === 'general-purpose' && o.effort === 'medium' && o.model === 'sonnet', l + ' ' + JSON.stringify(o))
  }
})

await scenario('SPEC-006/9: worker failure mid-lane -> committed specs still converged, lane unfinished', async () => {
  const replies = { 'lane:A': { ...worker('A', ['A1']), failedAt: 'A2', failure: 'analyze errors' }, ...all(['A1']) }
  const { out, labels } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1'), spec('A2'), spec('A3')])] }, replies)
  assert(labels.includes('converge:A1') && !out.lanes[0].finished && out.lanes[0].failedAt === 'A2', labels.join())
})

await scenario('dead worker: failure says re-run /speclane:execute', async () => {
  const { out } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('A1')])] }, {})
  assert(out.lanes[0].failure.startsWith('worker returned no result') && out.lanes[0].failure.includes('/speclane:execute'), out.lanes[0].failure)
})

await scenario('no lanes -> nothing dispatched', async () => {
  const { out, calls } = await run(body, { workItem: 'w', lanes: [] }, {})
  assert(calls.length === 0 && out.lanes.length === 0, 'ran')
})

// ---------------------------------------------------------------- post-merge follow-up (untestable is not a pass, ITEMS_RULE)
await scenario('follow-up/1: untestable-only: no fix round, lane not finished, dependents skipped', async () => {
  const lanes = [lane('A', [spec('SPEC-001', 'committed', ['s1']), spec('SPEC-002')]), lane('B', [spec('SPEC-003')], ['A']), lane('C', [spec('SPEC-004')])]
  const replies = {
    'converge:SPEC-001': { specId: 'SPEC-001', criteria: [crit('pass'), crit('untestable'), crit('pass')], outOfScope: [] },
    'lane:A': worker('A', ['SPEC-002']), 'lane:C': worker('C', ['SPEC-004']), ...all(['SPEC-002', 'SPEC-004']),
  }
  const { out, labels } = await run(body, { workItem: 'w', lanes }, replies)
  const A = out.lanes.find((l) => l.lane === 'A')
  assert(A.converge['SPEC-001'].result === 'untestable (1/3)' && A.converge['SPEC-001'].rounds === 0, A.converge['SPEC-001'].result)
  assert(!labels.some((c) => c.startsWith('fix:')), 'fix round dispatched')
  assert(labels.includes('lane:A') && A.converge['SPEC-002'].result === 'pass', 'lane did not carry on')
  assert(JSON.stringify(A.untestable) === '["SPEC-001"]' && A.finished === false, 'state')
  assert(out.skipped.some((s) => s.lane === 'B' && s.reason.includes('A did not finish')), 'B not skipped')
  assert(out.lanes.find((l) => l.lane === 'C').finished === true, 'independent lane C')
})

await scenario('follow-up/2: fail+untestable: fix round, then untestable', async () => {
  const replies = {
    'lane:A': worker('A', ['SPEC-001']),
    'converge:SPEC-001': (n) => ({ specId: 'SPEC-001', criteria: [n === 1 ? crit('fail') : crit('pass'), crit('untestable')], outOfScope: [] }),
    'fix:SPEC-001:1': fixOk('SPEC-001', 'fix1'),
  }
  const { out, labels } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('SPEC-001')])] }, replies)
  const A = out.lanes[0]
  assert(labels.includes('fix:SPEC-001:1') && A.converge['SPEC-001'].result === 'untestable (1/2)' && A.converge['SPEC-001'].rounds === 1, A.converge['SPEC-001'].result)
  assert(A.untestable.includes('SPEC-001') && !A.finished, 'state')
})

await scenario('follow-up/3: untestable survives a later mate fix round', async () => {
  const replies = {
    'lane:A': worker('A', ['SPEC-001', 'SPEC-002']),
    'converge:SPEC-001': (n) => ({ specId: 'SPEC-001', criteria: [n === 1 ? crit('untestable') : crit('pass')], outOfScope: [] }),
    'converge:SPEC-002': (n) => ({ specId: 'SPEC-002', criteria: [n === 1 ? crit('fail') : crit('pass')], outOfScope: [] }),
    'fix:SPEC-002:1': fixOk('SPEC-002', 'fix2'),
  }
  const { out } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('SPEC-001'), spec('SPEC-002')])] }, replies)
  assert(out.lanes[0].converge['SPEC-002'].result === 'pass' && out.lanes[0].untestable.join() === 'SPEC-001', out.lanes[0].untestable.join())
})

await scenario('follow-up/4: untestable+outOfScope: fix round', async () => {
  const replies = {
    'lane:A': worker('A', ['SPEC-001']),
    'converge:SPEC-001': (n) => ({ specId: 'SPEC-001', criteria: [crit('untestable')], outOfScope: n === 1 ? ['x.ts'] : [] }),
    'fix:SPEC-001:1': fixOk('SPEC-001', 'fix1'),
  }
  const { out, labels } = await run(body, { workItem: 'w', lanes: [lane('A', [spec('SPEC-001')])] }, replies)
  assert(labels.includes('fix:SPEC-001:1') && out.lanes[0].converge['SPEC-001'].result === 'untestable (1/1)', 'result')
})

await scenario('follow-up/5: skip reasons chain through untestable', async () => {
  const lanes = [lane('A', [spec('SPEC-001')]), lane('B', [spec('SPEC-002')], ['A']), lane('D', [spec('SPEC-003')], ['B'])]
  const replies = { 'lane:A': worker('A', ['SPEC-001']), 'converge:SPEC-001': { specId: 'SPEC-001', criteria: [crit('untestable')], outOfScope: [] } }
  const { out } = await run(body, { workItem: 'w', lanes }, replies)
  assert(out.skipped.map((s) => s.lane).join() === 'B,D', JSON.stringify(out.skipped))
})

await scenario('follow-up/6: worker + fix prompts carry ITEMS_RULE with the running item (default workDir)', async () => {
  const replies = { 'lane:A': worker('A', ['SPEC-001']), 'converge:SPEC-001': (n) => (n === 1 ? failG('SPEC-001') : pass('SPEC-001')), 'fix:SPEC-001:1': fixOk('SPEC-001') }
  const { calls } = await run(body, { workItem: 'demo-item', lanes: [lane('A', [spec('SPEC-001')])] }, replies)
  const want = ["except a path that the spec's ## Files lists explicitly", 'README.md or reports/ of .claude/work/items/demo-item/', 'Never edit anything under .claude/work/items/']
  for (const l of ['lane:A', 'fix:SPEC-001:1']) for (const w of want) assert(calls.find((c) => c.label === l).prompt.includes(w), `${l}: ${w}`)
})

// ---------------------------------------------------------------- speclane settings plumbing
const SETTINGS = {
  workDir: 'docs/work/',
  contractFile: '/plug/skills/execute/SKILL.md',
  commands: {
    test: 'pnpm vitest run {files}', analyze: 'pnpm tsc --noEmit', fix: 'pnpm eslint --fix {files}', format: null,
    codegen: { run: 'pnpm gen', when: 'a spec touches schema.graphql' },
  },
  derivedFiles: ['src/gen/**'],
  contextFiles: ['AGENTS.md', 'docs/rules.md'],
  mcpTools: ['mcp__x__analyze'],
}
await scenario('settings: worker prompt carries commands, codegen condition, derived files, context, MCP tools, contract path, workDir', async () => {
  const replies = { 'lane:A': worker('A', ['S1']), 'converge:S1': (n) => (n === 1 ? failG('S1') : pass('S1')), 'fix:S1:1': fixOk('S1') }
  const { calls } = await run(body, { workItem: 'it', settings: SETTINGS, lanes: [lane('A', [spec('S1')])] }, replies)
  const w = calls.find((c) => c.label === 'lane:A').prompt
  for (const s of ['`pnpm eslint --fix {files}`', 'analyze: `pnpm tsc --noEmit`', '`pnpm vitest run {files}`', '`pnpm gen` (only when a spec touches schema.graphql)',
    'src/gen/**', 'test files for the changed code', 'Read these project files first: AGENTS.md, docs/rules.md', 'mcp__x__analyze',
    '/plug/skills/execute/SKILL.md', 'Never edit anything under docs/work/items/', 'reports/ of docs/work/items/it/'])
    assert(w.includes(s), 'worker prompt missing: ' + s)
  assert(!w.includes('format:'), 'null format command rendered')
  const f = calls.find((c) => c.label === 'fix:S1:1').prompt
  assert(f.includes('/plug/skills/execute/SKILL.md') && f.includes('docs/work/items/it/'), 'fix prompt')
  const c = calls.find((x) => x.label === 'converge:S1').prompt
  for (const s of ['src/gen/**', 'test `pnpm vitest run {files}`', 'analyze `pnpm tsc --noEmit`', 'Never run: `pnpm eslint --fix {files}`, `pnpm gen`', 'AGENTS.md'])
    assert(c.includes(s), 'converge prompt missing: ' + s)
})

await scenario('settings absent: no project-specific text, neutral fallbacks', async () => {
  const { calls } = await run(body, { workItem: 'it', lanes: [lane('A', [spec('S1')])] }, { 'lane:A': worker('A', ['S1']), ...all(['S1']) })
  const w = calls.find((c) => c.label === 'lane:A').prompt + calls.find((c) => c.label === 'converge:S1').prompt
  for (const bad of ['fvm', 'dart', 'build_runner', 'flutter', '.freezed', 'undefined', '[object Object]'])
    assert(!w.includes(bad), 'leaked: ' + bad)
  assert(w.includes("if it has any") && w.includes('(none configured)'), 'fallback text')
})

summary('execute.test.mjs')
