# Changelog

## 0.1.0 (2026-11-17)

First release: an in-house planner/worker spec system (v5), packaged as a project-neutral plugin.

- Skills `/speclane:plan`, `:review-plan`, `:init`, `:execute`, `:finalize`.
- Agents `speclane:converge` and `speclane:handoff-check`, pinned to `claude-opus-4-6`.
- Workflows `speclane:execute-lanes`, `:finalize-agents`, `:review-plan-agents`.
- Per-project config `.claude/speclane.json` with a JSON schema; fictional examples for a Flutter app, a pnpm monorepo and a docs-only repo.
- Offline test suite (`tests/run.sh`), run in CI.
