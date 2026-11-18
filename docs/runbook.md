# speclane runbook

For plan-driven, multi-spec work. The main session plans; workers implement one commit per spec; an independent grader on a different model checks each one.

## The flow

```
0. .claude/speclane.json                  — project config (docs/config.md); optional
1. /speclane:plan <feature | --from doc>  — optional: write {workDir}/plans/<slug>.md
2. /speclane:review-plan <plan-file>      — optional: multi-agent review of the plan
3. /speclane:init <plan-file>             — draft specs + lanes in {workDir}/items/<slug>/,
                                            then the cross-model speclane:handoff-check (reports/handoff-check.md)
4. Approve                                — you set `status: approved` in each spec you accept; only approved specs run
5. /speclane:execute <slug> --dry-run     — pre-flight + reconcile + guard; prints the serial run order
6. /speclane:execute <slug>               — lanes run one at a time; each worker makes one commit per spec
                                            (`Spec: <slug>/SPEC-NNN` trailer), then speclane:converge grades the lane
                                            (pinned claude-opus-4-6, 3-round cap)
7. /speclane:finalize <slug>              — gates on reconciled state, reviewers, cross-model verify for
                                            highRisk paths, one serial analyze/test pass, validation report
8. Merge                                  — see "Merging spec branches"
```

`/speclane:init` and `/speclane:plan` are `disable-model-invocation: true`: only you can start them.

## State

- **Authority**: the `Spec:` commit trailers in git. Spec frontmatter (`status`, `commits`, `converge`) is a cache that `/speclane:execute` reconciles forward and is its only writer. Workers write code and commits only.
- **Statuses**: `draft` → `approved` (you) → `committed` (a trailer commit exists) → `done` (converge pass, or `manual`). `blocked` (3 failed converge rounds, or the worker failed before committing) and `skipped` (behind a blocked spec) are set by the skill.
- **Held**: a spec is held while any `depends_on` spec or earlier lane-mate is `blocked`, or is itself held (holding is transitive). Held specs never reach the workflow, not even `committed` ones.
- **Reconcile is forward-only**: it fills `commits` from exact `<slug>/SPEC-NNN` trailer values, moves `approved` → `committed`, returns `skipped` → `approved` once no longer held, and never touches `done`, `blocked` or `committed`.
- **Resume** is just re-running `/speclane:execute <slug>` after a crash, block or unblock.
- **Untestable is not a pass.** A converge of `untestable (n/m)` keeps the spec `committed`, runs no fix round, and skips lanes that depend on it. Either check the criterion yourself and set `status: done`, `converge: manual`, or rewrite it so it can be checked and re-run.
- **Unblock**: fix the cause, then set `status: approved`, `rounds: 0` and clear `blocked_reason`.
- **Single spec**: `/speclane:execute <slug> SPEC-NNN` runs one spec as a one-spec lane; it refuses unless every dependency and earlier lane-mate is `done`.
- **README**: the work-item README's Specifications Status column is rewritten from frontmatter after every run. Frontmatter stays the source.

## Lanes

A lane is the specs one worker implements in sequence, keeping its context. Lanes are named with single capital letters (`A`–`Z`). Lanes run **one at a time**: every worker edits the session's working tree, so parallel lanes would see each other's half-written files. `/speclane:init` derives lanes from `depends_on`; pre-flight re-checks the rules:

1. Within a lane, specs are ordered so each `depends_on` comes first.
2. A lane depends on every lane holding a dependency of one of its specs.
3. A spec that another lane depends on is the **last** spec in its lane.
4. The lane graph is acyclic.
5. `worker: sonnet` only when every spec in the lane is mechanical.

## Workers

- One commit per spec: `git commit --only -F <msgfile> -- <paths>`, message file outside the repo, exactly one `Spec: <slug>/SPEC-NNN` trailer, `Refs: #N` when the README names an issue. Never `fixes`/`closes` in a spec commit.
- Never edit `{workDir}/items/`, except a path the spec's `## Files` lists explicitly (e.g. moving another item into `archive/`). Even then, never this item's spec frontmatter, README or `reports/`.
- On failure, stop and leave partial edits in place. The skill prints both recovery commands (commit, or `git restore --source=HEAD --staged --worktree -- <paths>`). Never use `git stash`: the stash is shared across worktrees and sessions.

## Merging spec branches

- Merge a work item's branch with `git merge --no-ff <branch>`. **Never squash or rebase-merge**: that rewrites or erases the per-spec commits and their `Spec:` trailers, which are the record of what's done.
- Spec commits reference the issue with `Refs: #N`. The closing keyword goes only in the `--no-ff` merge commit (or PR body), once the whole item is done:

```bash
git merge --no-ff <branch> -m "Merge <branch>: <work item title>, fixes #N"
```

## Model routing

Each agent's frontmatter owns its model. Dispatch without a `model` argument.

| Agent | Model | Why |
|-------|-------|-----|
| `speclane:handoff-check` | `claude-opus-4-6` (pinned) | Cross-model check of the planner's specs before approval (generator/verifier split) |
| `speclane:converge` | `claude-opus-4-6` (pinned), effort `high` | Grades each spec independently of the model that wrote it |
| finalize verifier (`highRisk` only) | `claude-opus-4-6`, set by the workflow | Strict completeness pass |
| lane worker / fix worker | session model; `sonnet` on a sonnet lane | — |
| `/speclane:plan` skill | `opus`, effort `xhigh`, forked context (skill frontmatter) | Planning is the most consequential step; needs Opus access |
| `/speclane:finalize` skill | `sonnet` (skill frontmatter) | It orchestrates and writes reports; the reviewers and verifier do the judging |
| `/speclane:init`, `:execute`, `:review-plan` | session model | init plans in your main session on purpose |
| project reviewers | their own frontmatter | — |

The pin is deliberate and does not track "latest opus". If a run's journal ever shows converge on another model, pass `model: 'claude-opus-4-6'` in that `agent()` call in `workflows/execute.js` and record why in its header.

Plugin agents ignore `permissionMode`, `hooks` and `mcpServers` in their frontmatter. speclane's agents use none of them.

## Acceptance criteria that work

- Commands run in the session's shell: zsh on macOS, usually bash on Linux. Write POSIX-compatible commands, and on macOS remember BSD tools (`sed -i ''`, no GNU-only flags).
- **Greps**: `.claude/worktrees/` holds other sessions' untracked checkouts. Every recursive grep over `.` or `.claude` needs `--exclude-dir=worktrees`, or use `git grep` (tracked files only). `converge` marks a grep whose only extra hits are under worktrees `untestable`, not `fail`.
- Criteria must still hold after later lane-mates land: converge grades at the lane's final HEAD.

## Testing changes to speclane itself

- **Where tooling loads from**: Claude Code loads skills, agents and named workflows when a session starts, from the folder the session was **opened on** plus installed plugins. A session opened on a main checkout that works in `.claude/worktrees/<name>/` still runs the main checkout's tooling. To test a change live, install the plugin (or the branch's copy of it) and open a **new** session.
- **Offline**: `tests/run.sh` runs the stub workflow harness (scripted `agent()` replies) and the scratch-repo tests of every Python script embedded in the skills. Live runs have found bugs the stubs missed, so do both before a release.
