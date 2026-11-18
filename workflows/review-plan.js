// workflows/review-plan.js  (speclane plugin)
//
// Fan out specialist reviewers over a document and return structured findings.
// Generic reviewer fan-out: the calling skill selects WHICH reviewers to
// dispatch and what each one's brief says; this script owns HOW they run
// (parallel, schema-validated, attributed). Used by /speclane:review-plan;
// any skill may reuse it for a document or source file (`plan` is the content,
// `ref` carries file:line). Reviewer briefs come from the project's
// .claude/speclane.json (`planReviewers`).
//
// args: {
//   planFile: string,                       // path, shown to reviewers
//   plan:     string,                       // full plan content
//   reviewers: Array<{                      // selected by the skill
//     type:  string,                        // subagent_type (project agent name, or general-purpose)
//     brief: string,                        // that reviewer's checklist
//     model?: string,                       // OPTIONAL override; omit to use the agent's own frontmatter
//     effort?: string,
//   }>,
// }
//
// returns: Array<{ agent, verdict, findings[], questions[] }> — one per
// surviving reviewer, `agent` set deterministically by this script.

export const meta = {
  name: 'review-plan-agents',
  description: 'Fan out specialist reviewers over a document and return structured findings',
  whenToUse: 'Generic reviewer fan-out — invoked by the /speclane:review-plan skill after it selects reviewers',
  phases: [{ title: 'Review', detail: 'one agent per selected specialist, in parallel' }],
}

const FINDINGS = {
  type: 'object',
  required: ['verdict', 'findings'],
  properties: {
    verdict: { enum: ['APPROVE', 'APPROVE_WITH_CHANGES', 'REQUEST_CHANGES'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'title'],
        properties: {
          // → 🔴 / 🟡 / 🟢 in the consolidated report
          severity: { enum: ['critical', 'warning', 'suggestion'] },
          title: { type: 'string' },
          detail: { type: 'string' },
          ref: { type: 'string' }, // file:line or plan section, when applicable
        },
      },
    },
    questions: { type: 'array', items: { type: 'string' } },
  },
}

const reviewers = args?.reviewers ?? []
if (reviewers.length === 0) {
  log('No reviewers passed — nothing to review.')
  return []
}

log(`Reviewing ${args.planFile} with ${reviewers.length} specialists`)

// parallel() is the barrier: returns only once every reviewer has landed,
// each result already validated against FINDINGS. The reviewers' verbose
// analysis never enters the calling session's context — only these objects.
const reviews = await parallel(
  reviewers.map((r) => () =>
    agent(
      `${r.brief}\n\n## Under Review\nFile: ${args.planFile}\n\n${args.plan}`,
      {
        label: `review:${r.type}`,
        phase: 'Review',
        agentType: r.type,
        // Omit model/effort to inherit the agent's frontmatter — pass them
        // only when the skill deliberately overrides.
        ...(r.model ? { model: r.model } : {}),
        ...(r.effort ? { effort: r.effort } : {}),
        schema: FINDINGS,
      },
    ),
  ),
)

// Attribute results by position rather than trusting a model-reported field:
// parallel() preserves input order, so index i is reviewers[i].
const attributed = reviews
  .map((review, i) => (review ? { agent: reviewers[i].type, ...review } : null))
  .filter(Boolean)

const died = reviewers.filter((r, i) => !reviews[i]).map((r) => r.type)
if (died.length > 0) {
  log(`No result from: ${died.join(', ')} — consolidating the rest.`)
}

return attributed
