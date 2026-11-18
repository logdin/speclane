# {Work Item Title}

> **Slug**: `{slug}`
> **Plan**: `{workDir}/plans/{plan}.md` (copied to `context/PLAN.md`)
> **Issue**: #{N}            <!-- spec commits use `Refs: #N`; `fixes #N` goes only in the --no-ff merge commit -->
> **Created**: {YYYY-MM-DD}

---

## Overview

{2–4 sentences: what this work item delivers and why.}

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| {topic} | {choice} | {why} |

---

## Lanes

<!-- A lane is the specs one worker implements in sequence, keeping its context.
     Lanes run one at a time, in dependency order. Rules (/speclane:init enforces them; pre-flight re-checks):
       1. Specs within a lane are ordered so their depends_on are satisfied.
       2. A lane depends on every lane that holds a dependency of one of its specs.
       3. A spec that another lane depends on must be the LAST spec in its lane.
       4. The lane graph must be acyclic. Split lanes until it is.
       5. Worker = sonnet only when every spec in the lane is mechanical; otherwise default. -->

| Lane | Specs (in order) | Worker | Depends on lanes |
|------|------------------|--------|------------------|
| A | SPEC-001, SPEC-002 | default | — |
| B | SPEC-003 | sonnet | A |

## Specifications

<!-- Status here is a summary of each spec's frontmatter, which is reconciled from `Spec:` trailers in git. -->

| ID | Title | Lane | Depends on | Status |
|----|-------|------|------------|--------|
| [SPEC-001](specs/SPEC-001-{name}.md) | {title} | A | — | draft |

---

## Reports

| File | Written by |
|------|-----------|
| `reports/handoff-check.md` | /speclane:init (speclane:handoff-check findings, before approval) |
| `reports/deviations.md` | lane workers, whenever they depart from a spec |
| `reports/validation-{date}.md` | /speclane:finalize |
