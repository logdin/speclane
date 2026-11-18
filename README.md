# speclane

A Claude Code plugin for plan-driven work, split between a planner and workers. A strong planner in your main session writes thin, reviewable specs, one per commit. A pinned cross-model agent checks that each spec stands on its own, and you approve. Workers then implement the specs in **lanes**, one lane at a time, each commit carrying a `Spec: <item>/SPEC-NNN` trailer. Finally, an independent grader on a different model (`claude-opus-4-6`) checks every spec against its acceptance criteria. Failed specs get fix rounds, with a 3-round cap.

Git is the record: the `Spec:` trailers say what landed, and spec frontmatter is a cache that only the execute skill writes. Re-running is always the resume path.

Everything project-specific lives in one config file, `.claude/speclane.json`.

## Commands

| Command | What it does |
|---------|--------------|
| `/speclane:plan <feature \| --from doc.md>` | Write a structured plan to `{workDir}/plans/` (forked, high effort). User-invoked only |
| `/speclane:review-plan <plan.md>` | Fan reviewers out over a plan; consolidated report in `{workDir}/reviews/` |
| `/speclane:init <plan.md \| feature>` | Draft specs + lanes in `{workDir}/items/<slug>/`, then the `speclane:handoff-check` agent. User-invoked only |
| `/speclane:execute <slug> [SPEC-NNN] [--dry-run]` | Pre-flight, reconcile from git, run lanes serially, converge, record state, bookkeeping commit |
| `/speclane:finalize <slug>` | Gate on `done`, reviewers per group, cross-model verify for high-risk paths, one serial analyze/test pass, validation report |

Agents: `speclane:converge` (grader) and `speclane:handoff-check` (spec checker), both pinned to `claude-opus-4-6`. Workflows (called by the skills, not meant to be run by hand): `speclane:execute-lanes`, `speclane:finalize-agents`, `speclane:review-plan-agents`. Their names differ from the skills' on purpose: a plugin workflow is also a slash command, and one named like a skill shadows it.

The full flow, state machine and rules are in [`docs/runbook.md`](docs/runbook.md).

## Install

The repository is its own marketplace. From the project you want to use it in:

```bash
claude plugin marketplace add logdin/speclane --scope project
```

(or a local clone: `claude plugin marketplace add /path/to/speclane --scope project`)

```bash
claude plugin install speclane@speclane --scope project
```

`--scope project` writes both entries to the project's `.claude/settings.json`, so collaborators get the same setup. Use `--scope local` to keep it to yourself, or leave the scope out to install for your user. A GitHub marketplace is cached; run `claude plugin marketplace update speclane` to pick up new versions. A local-directory marketplace is read live, so edits apply from the next session.

Then add a project config (optional, but without one there are no test/analyze commands and every reviewer is `general-purpose`):

```bash
curl -fsSL https://raw.githubusercontent.com/logdin/speclane/main/examples/web-monorepo.speclane.json -o .claude/speclane.json   # pick the closest example, then edit
```

Open a **new** session after installing: skills, agents and workflows load when a session starts. `/speclane:init` also offers to draft a config from your build files if none exists.

## Configure

`.claude/speclane.json` (all keys optional; reference: [`docs/config.md`](docs/config.md); schema: [`schema/speclane.schema.json`](schema/speclane.schema.json)):

```json
{
  "workDir": ".claude/work",
  "contextFiles": ["AGENTS.md"],
  "commands": {
    "test": "pnpm exec vitest run {files}",
    "analyze": "pnpm typecheck",
    "fix": "pnpm exec eslint --fix {files}",
    "format": null,
    "codegen": { "run": "pnpm gen", "when": "a spec touches schema.graphql" },
    "gate": ["pnpm check"]
  },
  "derivedFiles": ["src/gen/**"],
  "reviewers": {
    "default": "general-purpose",
    "routes": [{ "paths": ["apps/server/"], "agent": "backend-reviewer" }]
  },
  "highRisk": ["apps/server/migrations/"]
}
```

Domain reviewer agents stay in your project's `.claude/agents/`. speclane routes to them by name.

Examples (fictional projects): [Flutter app](examples/mobile-app.speclane.json), [pnpm/TypeScript monorepo](examples/web-monorepo.speclane.json), [docs-only repo](examples/docs-only.speclane.json).

## Upgrading

From a v4 work item or an in-repo copy of the v5 skills: [`docs/upgrading-v4.md`](docs/upgrading-v4.md). Work items are format-compatible.

## Develop

```bash
tests/run.sh
```

```bash
claude plugin validate .
```

`tests/run.sh` runs:
- static checks;
- the stub workflow harness (scripted `agent()` replies against `workflows/*.js`);
- scratch-git-repo tests of every Python script embedded in the skills, extracted from the `SKILL.md` files themselves;
- schema validation of the examples.

Live runs have found bugs the stubs missed, so also smoke-test a change in a scratch project with the plugin installed (README → Install). Open a new session each time.

## Known limits

- **Workflow names must differ from skill names.** A plugin workflow is also a `/speclane:<meta.name>` slash command and shadows a skill of the same name. That's why the workflows are `execute-lanes`, `finalize-agents` and `review-plan-agents`. A static test guards it.
- **`.claude/` is a sensitive path.** `Write`/`Edit` calls under it ask for approval (headless runs refuse them). `init`, `plan` and `review-plan` write that way; set `workDir` outside `.claude/` to avoid the prompts. `execute` and `finalize` write through their scripts and aren't affected.
- **Project MCP tools aren't pre-approved.** A plugin skill can't list them in `allowed-tools`; allow them in your project's `.claude/settings.json` if you configure `mcpTools`.
- **Workers read the commit contract from the plugin folder** (an absolute path passed in the workflow input). If a sandbox blocks reads outside the project, that read fails; the worker prompt's summary of the contract still applies.
- **Live-verified**: init, execute (two lanes, converge pass) and finalize, with the `claude-opus-4-6` pins honoured. **Covered only by the offline tests**: fix rounds, the 3-round cap, block/unblock, single-spec mode, sonnet lanes and the high-risk verify pass.

## License

MIT. See [LICENSE](LICENSE).
