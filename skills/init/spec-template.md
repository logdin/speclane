---
id: SPEC-{NNN}
title: {Component Name}
priority: P0                # P0 | P1 | P2
lane: {A}                   # must match the lanes table in the work-item README
depends_on: []              # spec IDs; a spec another lane depends on must be last in its lane
status: draft               # draft → approved (you) → committed (trailer) → done (converge pass) | blocked | skipped
commits: []                 # shas carrying `Spec: <item>/SPEC-NNN`, oldest first. Reconciled from git; don't hand-edit
converge: null              # pass | manual | fail (n/m) | untestable (n/m), written by /speclane:execute (manual = checked by hand; untestable is not a pass)
rounds: 0                   # failed converge rounds; 3 → blocked
blocked_reason: null
agents:
  review: general-purpose   # finalize reviewer, routed by file path (reviewers in .claude/speclane.json)
---

<!--
  Thin spec (speclane): decisions, interfaces and acceptance. The worker writes the code.
  Target 40–80 lines. Size check before approving:
    too big   → crosses layers, > ~5 non-test files, or > ~6 functional criteria: split it
    too small → can't be checked on its own (a rename, a barrel export): fold it into a neighbour
  One spec = one commit (plus fix-round commits under the same Spec: trailer).
-->

## Context

{3–5 sentences: what exists, what's wrong or needed, the decision taken and why.}

**Related**: `{path/to/pattern/file}` (worked example to follow)

## Files

<!-- The worker's allowed paths. Converge flags any committed path outside this table
     unless it's listed in reports/deviations.md. Derived files (tests for the changed code,
     and the patterns in `derivedFiles` of .claude/speclane.json) may be committed without being listed.
     TEST rows = existing tests to run after the change. -->

| Action | Path | Purpose |
|--------|------|---------|
| MODIFY | `{src/path}` | {purpose} |
| CREATE | `{src/path}` | {purpose} |
| TEST   | `{test/path}` | Existing — breaks if {X} changes |
| CREATE | `{test/path}` | New — {what it covers} |

## Interfaces

<!-- Exact signatures and data shapes the worker must match, and nothing more:
     no method bodies, no before/after code. Omit the section if the spec adds no API. -->

```{language}
{type / function signatures, enum values, exported names, JSON keys}
```

## Validation

<!-- REQUIRED when the spec touches financial calculations or domain logic; otherwise delete.
     Concrete inputs → expected outputs. Catches formula bugs that abstract review misses. -->

| Input | Value |
|-------|-------|
| {param} | {value} |

| Output | Expected | Formula |
|--------|----------|---------|
| {metric} | {value} | {derivation} |

## Acceptance

<!-- Each criterion is checked independently by speclane:converge against this spec's commits
     and the lane's final HEAD. Write criteria that still hold after later specs in the same
     lane land. Backtick-wrapped commands are run as written (zsh, BSD tools on macOS).
     A recursive grep over `.` or `.claude` must add `--exclude-dir=worktrees`: `.claude/worktrees/`
     holds other sessions' untracked checkouts, and their copies of the same files match too.
     (`git grep` searches tracked files only and needs no exclude.) -->

### Functional
- [ ] **Given** {precondition}, **When** {action}, **Then** {expected outcome}

### Tests
- [ ] `{commands.test with {files} = the test paths from the Files table}`

### Quality
- [ ] `{commands.analyze with {files} = the changed file paths}`

### Converge Checklist
<!-- Written by /speclane:execute from speclane:converge's result. Don't fill in by hand. -->
