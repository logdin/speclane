# Upgrading a v4 work item (or an in-repo v5 copy)

v4 and v5 are the two formats of the spec workflow speclane was built from (see README → Upgrading). New users can skip this page.

## From v4

`/speclane:execute` pre-flight fails on any spec without v5 frontmatter (no `status:`/`lane:`) and points here. To upgrade an item in place:

1. **Frontmatter**: add `status` (`approved` for specs you still want run; `draft` to review first), `lane`, `commits: []`, `converge: null`, `rounds: 0` and `blocked_reason: null` to each spec. Don't fill `commits` by hand: reconcile fills it from any existing `Spec: <slug>/SPEC-NNN` trailers on the next run.
2. **Body**: rewrite each spec's `## Changes` section as `## Interfaces` (signatures, contracts and behaviour, no implementation code). See `skills/init/spec-template.md`.
3. **README**: add the `## Lanes` table (rules in `docs/runbook.md` → Lanes) and the `**Issue**:` line (`none filed` if there isn't one).
4. **Hand-off check**: run `speclane:handoff-check` over the upgraded specs (as `/speclane:init` step 5 does) and fix its blockers before approving.
5. `/speclane:execute <slug> --dry-run` to confirm pre-flight passes.

## From an in-repo copy of the v5 skills (`.claude/skills/spec-*`)

Work items are format-compatible: same frontmatter, same README tables, same `Spec:` trailers. Nothing in `{workDir}/items/` needs to change.

1. Add `.claude/speclane.json` (start from the closest file in `examples/`).
2. Install the plugin (README → Install).
3. In existing specs, `agents.review` values keep working: they're project agent names.
4. Remove or rename the in-repo copies (`spec-init`, `spec-execute`, `work-finalize`, `create-plan`, `review-plan`, the `spec-converge` / `spec-handoff-check` agents, and the `spec-execute` / `work-finalize` / `review-plan` workflows) once you've switched, so two versions of the same workflow can't drift. Keep any other in-repo workflows your other skills use.
5. Command names change: `/spec-init` → `/speclane:init`, `/spec-execute` → `/speclane:execute`, `/work-finalize` → `/speclane:finalize`, `/create-plan` → `/speclane:plan`, `/review-plan` → `/speclane:review-plan`.
