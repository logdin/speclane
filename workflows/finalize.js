// workflows/finalize.js  (speclane plugin)
//
// Fan out a work item's finalize agents (one reviewer per `agents.review`
// group) in parallel and return structured, attributed results. When the item
// touched a high-risk path (`highRisk` in .claude/speclane.json), also run one
// strict cross-model verifier (pinned claude-opus-4-6).
// Invoked by the /speclane:finalize skill, which builds each agent's prompt (it
// holds the context: changed files, spec contents, report expectations) and
// consumes the returns for report writing; this script owns HOW they run.
//
// Replaces the old Agent(run_in_background: true) + TaskOutput-polling dispatch,
// which breaks under agent teams (teammate sessions keep findings in their own
// transcripts) and needed a hand-run 5-minute-timeout wait loop.
//
// Agents run in the session's working tree. A test-writing agent may WRITE test
// files there deliberately (no worktree isolation; reviewers only read, so the
// sets don't collide). No model args for reviewers: each agent's frontmatter
// owns its model. Reviewer agent names come from the project's config
// (`reviewers`); domain reviewers live in the project's own .claude/agents/.
//
// Where `agents[]` comes from (built by the skill, not here): the skill's gate
// script reads the item's spec frontmatter and its `Spec: <item>/SPEC-NNN`
// trailer commits. Specs are grouped by their frontmatter `agents.review`
// reviewer; each group becomes ONE entry whose `scope` is its spec IDs and
// whose prompt is the skill's `per-spec-agent` template, filled with those
// specs' IDs, their `## Acceptance` sections, and the union of the files
// their trailer commits changed (deleted paths dropped). This script never
// reads spec files or git itself.
//
// args: {
//   workItem: string,
//   agents: Array<{
//     type: string,                         // normalized subagent_type
//     scope: string,                        // the group's spec IDs, e.g. 'SPEC-001,SPEC-004' (attribution only)
//     prompt: string,                       // full prompt built by the skill
//     label?: string,
//   }>,
//   verify?: {                              // only when the item touched a highRisk path
//     brief: string,                        // item, spec IDs, commits, high-risk files, spec dir
//     agentType?: string,                   // default 'general-purpose'
//     model?: string,                       // default 'claude-opus-4-6' (the pin is the point)
//   },
// }
//
// returns: {
//   reviews: Array<{ agent, scope, summary, score?, findings[], filesChanged[] }>,
//            one per surviving agent, `agent`/`scope` set positionally by this script;
//   verify: { verdict, findings[] } | null, // null when not requested or no result
// }

export const meta = {
  name: 'finalize-agents',
  description: "Parallel dispatch of a work item's finalize agents with structured returns",
  whenToUse: 'Finalize-agent fan-out — invoked by the /speclane:finalize skill after its done-gate passes',
  phases: [
    { title: 'Finalize', detail: 'specialist reviews, in parallel' },
    { title: 'Verify', detail: 'strict cross-model completeness pass, high-risk items only', model: 'claude-opus-4-6' },
  ],
}

const RESULT = {
  type: 'object',
  required: ['summary'],
  properties: {
    summary: { type: 'string' }, // 2-3 sentences: what was reviewed/generated, headline outcome
    score: { type: 'number' }, // quality reviewers: 0-100
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'title'],
        properties: {
          severity: { enum: ['critical', 'warning', 'suggestion'] },
          title: { type: 'string' },
          detail: { type: 'string' },
          ref: { type: 'string' }, // file:line
        },
      },
    },
    filesChanged: { type: 'array', items: { type: 'string' } }, // agents that wrote files (e.g. tests)
  },
}

const VERIFY_MODEL = 'claude-opus-4-6'
const VERDICT = {
  type: 'object',
  required: ['verdict', 'findings'],
  properties: {
    verdict: { enum: ['APPROVE', 'APPROVE_WITH_CHANGES', 'REQUEST_CHANGES'] },
    findings: RESULT.properties.findings,
  },
}
const PREAMBLE = [
  'You are performing a STRICT completeness-focused review of implemented,',
  'committed work. Your mandate is to catch what was MISSED: omitted',
  'requirements, unhandled states, stale references or doc comments, and',
  'gaps between what the tests assert and what the code actually does.',
  'Verify claims against the real code rather than trusting the summary.',
  'Be pedantic; a finding you can prove beats three you suspect.',
  'Read-only: never edit, stage or commit anything.',
  '',
].join('\n')

const agents = args?.agents ?? []
const verify = args?.verify?.brief ? args.verify : null
if (agents.length === 0 && !verify) {
  log('No agents passed — nothing to dispatch.')
  return { reviews: [], verify: null }
}

log(`Finalizing ${args.workItem} with ${agents.length} agent(s)${verify ? ' + cross-model verify' : ''}`)

const verifyRun = verify
  ? agent(`${PREAMBLE}${verify.brief}`, {
      label: `verify:${verify.model ?? VERIFY_MODEL}`,
      phase: 'Verify',
      agentType: verify.agentType ?? 'general-purpose',
      model: verify.model ?? VERIFY_MODEL,
      schema: VERDICT,
    })
  : Promise.resolve(null)

const results = await parallel(
  agents.map((a) => () =>
    agent(a.prompt, {
      label: a.label ?? `${a.type}:${a.scope}`,
      phase: 'Finalize',
      agentType: a.type,
      schema: RESULT,
    }),
  ),
)

// Attribute by position — parallel() preserves input order.
const attributed = results
  .map((r, i) => (r ? { agent: agents[i].type, scope: agents[i].scope, ...r } : null))
  .filter(Boolean)

const died = agents.filter((a, i) => !results[i]).map((a) => `${a.type}:${a.scope}`)
if (died.length > 0) {
  log(`No result from: ${died.join(', ')} — consolidating the rest.`)
}

return { reviews: attributed, verify: (await verifyRun) ?? null }
