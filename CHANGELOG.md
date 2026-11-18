# Changelog

## 0.1.3 (2026-11-17)

- review-plan: reviewers take an optional `name`, so two reviewers on the same agent type (like the two built-ins) are told apart in labels and the report. Found in the first live run of `/speclane:plan` and `/speclane:review-plan`.
- `graderModel` config: overrides the `claude-opus-4-6` pin for converge, the hand-off check and the finalize verifier (default unchanged). The skills always pass it when set and print a one-line warning when it equals the session model (a live run first showed a session silently swapping it back to the pin).

## 0.1.2 (2026-11-17)

Fixes from an independent review:
- Frontmatter `# comments` (as in the spec template) no longer break pre-flight (`rounds` crashed) or turn into extra reviewer groups in finalize. Quoted values keep their `#`.
- A `draft` spec now holds the specs that depend on it and its later lane-mates; before, a dependent lane could run on top of an unapproved spec.
- A spec without `id:` is a pre-flight error, not a crash after the run.
- The workflow return file is resolved explicitly (`${TMPDIR:-/tmp}`, which Linux often leaves unset) and named per item.
- Single-spec refusal commits any reconcile it wrote instead of leaving item files dirty.
- Docs: lane names are single capital letters; shell, git (2.22+) and model requirements; v4/v5 explained; config copy steps; Python example; stale internal references removed.

## 0.1.1 (2026-11-17)

- Holding is now transitive: a spec behind a held (not just blocked) dependency or lane-mate is held too. Before, such a spec flipped `skipped → approved` on every reconcile and back again after the run.
- Single-spec mode: the skill always runs its check script (a live run decided the refusal by itself instead).
- Docs: finalize's report writes are also hit by the `.claude/` sensitive-path prompt; what is live-verified is listed under Known limits.

## 0.1.0 (2026-11-17)

First release: an in-house planner/worker spec system (v5), packaged as a project-neutral plugin.

- Skills `/speclane:plan`, `:review-plan`, `:init`, `:execute`, `:finalize`.
- Agents `speclane:converge` and `speclane:handoff-check`, pinned to `claude-opus-4-6`.
- Workflows `speclane:execute-lanes`, `:finalize-agents`, `:review-plan-agents`.
- Per-project config `.claude/speclane.json` with a JSON schema; fictional examples for a Flutter app, a pnpm monorepo and a docs-only repo.
- Offline test suite (`tests/run.sh`), run in CI.
