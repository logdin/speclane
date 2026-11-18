# Project config: `.claude/speclane.json`

speclane keeps everything project-specific in one file at the repo root: `.claude/speclane.json`. Every key is optional. With no file at all, the defaults below apply and the skills say so once.

Schema: [`schema/speclane.schema.json`](../schema/speclane.schema.json). For editor completion, add `"$schema": "https://raw.githubusercontent.com/logdin/speclane/main/schema/speclane.schema.json"` (or a path to a local copy). Use a tagged URL (`…/speclane/v0.1.0/schema/…`) to stay on one version. Examples: [`examples/`](../examples/).

## Who reads it

Workflow scripts can't read files, so the skills read the config and pass what's needed on:

| Reader | Keys | How |
|--------|------|-----|
| `/speclane:execute` state script and single-spec script | `workDir`, `commands`, `derivedFiles`, `contextFiles`, `mcpTools` | Read from `<repo root>/.claude/speclane.json` and embedded in the workflow input as `settings`. The workflow puts them in worker, fix and converge prompts |
| `/speclane:finalize` gate script | `reviewers.default`, `reviewers.aliases`, `highRisk` | Read by the script itself |
| `/speclane:finalize` skill | `workDir`, `commands`, `contextFiles`, `mcpTools` | Read at the start (fix/format, gate, reviewer prompts, verifier brief) |
| `/speclane:init` | `workDir`, `contextFiles`, `commands`, `reviewers.routes`, `derivedFiles` | Read at the start; routes each spec's `agents.review` |
| `/speclane:plan`, `/speclane:review-plan` | `workDir`, `contextFiles`, `planReviewers`, `reviewers` | Read at the start |

The scripts look for the file at `git rev-parse --show-toplevel`. Run the skills from the repo root (the normal case).

## Keys

### `workDir` (default `.claude/work`)

Holds `plans/`, `items/<slug>/` and `reviews/`. Every item path in the skills is `{workDir}/items/{item}`, and the workers' "never edit the item folder" rule uses it.

Claude Code treats files under `.claude/` as sensitive: a `Write`/`Edit` tool call there asks for approval every time, and a headless (`claude -p`) run refuses it. `/speclane:execute` writes all its state through its Python scripts and git (Bash), so it isn't affected. `/speclane:init`, `/speclane:plan`, `/speclane:review-plan` and `/speclane:finalize` (its `reports/`) write files with the `Write` tool, so expect approval prompts with the default `workDir`. To avoid them, set `workDir` to a folder outside `.claude/`, e.g. `docs/work`.

### `contextFiles` (default `[]`)

Files read before anything else: by the planner (`init`, `plan`), by every worker and fix worker, by `converge` and `handoff-check` when a criterion depends on a project rule, and by finalize reviewers. Keep the list short: each file costs every agent tokens.

### `commands` (default `{}`)

| Key | Used by | `{files}` |
|-----|---------|-----------|
| `test` | workers (spec TEST rows), `init` (Acceptance lines), finalize gate | changed/test paths; removed for the gate |
| `analyze` | workers, `init`, finalize gate | changed paths; removed for the gate |
| `fix` | workers, finalize step 3 | changed paths |
| `format` | workers, finalize step 3 | changed paths |
| `codegen` | workers only. `converge` is told never to run it | not used |
| `gate` | finalize serial gate: a list run in order. Default: `analyze` then `test` | not used |

A command is a string, `null`, or `{ "run": "...", "when": "..." }`. `when` is shown to workers as a condition ("only when a spec touches @freezed models"). With no gate commands, finalize records the gate as **not run**, never as a pass.

Commands run in zsh. Write them for macOS (BSD) tools if anyone runs speclane on a Mac.

### `mcpTools` (default `[]`)

MCP tool names workers should prefer for fix/format/analyze/test when they're available, e.g. the Dart MCP server's `mcp__dart__analyze_files`. Plugin skills can't pre-approve project-specific MCP tools in `allowed-tools`, so expect a permission prompt the first time, or add them to your project's `.claude/settings.json` allow list.

### `derivedFiles` (default `[]`)

Generated files a spec's commit may include without listing them in `## Files`: e.g. `**/*.g.dart`, `**/*.freezed.dart`. Test files for the changed code are always derived. Entries are shown verbatim to workers and to `converge`'s out-of-scope check, so a short description ("barrel exports (index files that only re-export)") also works.

### `reviewers`

```json
"reviewers": {
  "default": "general-purpose",
  "routes": [
    { "paths": ["lib/core/billing/", "**/payments/**"], "agent": "payments-reviewer" },
    { "paths": ["lib/**/presentation/**"], "agent": "ux-reviewer" }
  ],
  "aliases": { "ux-specialist": "ux-reviewer" }
}
```

- `init` sets each spec's `agents.review` from the **first** route whose pattern matches one of the spec's `## Files` paths (several routes may match: then it may list several). No match → `default`.
- `finalize` groups specs by `agents.review` (resolved through `aliases`) and dispatches one reviewer per group.
- Domain reviewer agents stay in the project's own `.claude/agents/`. speclane routes to them by name only. If a named agent isn't available, finalize falls back to `general-purpose` for that group and says so.
- Never route to `speclane:converge` or `speclane:handoff-check`: they are workflow agents.

Path patterns (also used by `highRisk`): a plain path is a prefix (`src/core/` matches everything under it; `CLAUDE.md` matches that file). With `*` or `?`, it's a glob: `*` stays within one segment, `**` crosses segments (`lib/features/*/domain/**`).

### `highRisk` (default `[]`)

When any file the item changed matches, `/speclane:finalize` adds a strict cross-model completeness pass (a `general-purpose` verifier pinned to `claude-opus-4-6`) and writes `reports/verify-<date>.md`.

### `planReviewers`

```json
"planReviewers": [
  { "agent": "architecture-specialist", "always": true, "brief": "Review for: 1. Data flow ..." },
  { "agent": "payments-reviewer", "keywords": ["payment", "billing", "refund"], "brief": "..." }
]
```

`/speclane:review-plan` includes entries with `always: true`, plus any whose `keywords` the plan actually discusses. Without the key, two generic `general-purpose` reviewers run (architecture, code quality).

## Not in the config

- **Model pins.** `speclane:converge` and `speclane:handoff-check` pin `claude-opus-4-6` in their own frontmatter. That's the generator/verifier split: the grader must be a different model from the one that wrote the code. Lane workers use the session model, or Sonnet on a `sonnet` lane.
- **Branch names.** Merge targets are your call; the runbook only requires `--no-ff`.
