# Example configs

Fictional projects showing how `.claude/speclane.json` fits different stacks. Copy the closest one to `<your repo>/.claude/speclane.json` and edit it. Key reference: [`docs/config.md`](../docs/config.md).

| File | Project shape | Shows |
|------|---------------|-------|
| `mobile-app.speclane.json` | Flutter app (fvm, Dart MCP server, freezed codegen) | `codegen` with a `when` condition, `mcpTools`, generated `derivedFiles`, path-routed reviewers with aliases, `highRisk` globs, keyword-selected plan reviewers |
| `web-monorepo.speclane.json` | pnpm/TypeScript monorepo (vitest, eslint, prettier, GraphQL codegen) | a `workDir` outside `.claude/` (no write prompts), a single `gate` command, per-app reviewers |
| `docs-only.speclane.json` | Markdown-only repo | no test command; `analyze` as a lint; the finalize gate records "not run" when nothing is configured |

Notes:
- Reviewer agents named here (`code-reviewer`, `ui-reviewer`, …) are placeholders for agents in your project's `.claude/agents/`. speclane only routes to them by name. If one is missing, finalize falls back to `general-purpose`.
- `/speclane:execute` and the finalize and review-plan fan-outs are agent workflows. If your project only allows those when a person asks, invoking the skill is that ask: nothing in speclane starts one on its own.
- The `$schema` paths are relative to this folder. In a real repo, point `$schema` at your copy of the schema or drop the key.
