---
name: review-plan
description: Multi-agent plan review. Selects reviewers by plan content (from the project's .claude/speclane.json planReviewers, or two generic defaults) and fans them out via the speclane review-plan workflow for structured, deterministic consolidation.
argument-hint: <plan-file.md>
user-invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Workflow
  - Agent
---

# Plan Review

Review: **$ARGUMENTS**

> **Runs in the main loop — NOT forked.** The skill must stay resumable so it can consolidate when the fan-out completes. Do **not** add `context: fork`, and do **not** dispatch reviewers with `Agent(run_in_background: true)`: with agent teams enabled that spawns teammate sessions that keep their findings in their own transcripts, so consolidation never fires. Fan-out goes through the **Workflow tool** (structured returns) or, if Workflow is disabled, a **synchronous** `Agent` fan-out.
>
> **Project config**: first `Read` `${CLAUDE_PROJECT_DIR}/.claude/speclane.json` (docs: `${CLAUDE_PLUGIN_ROOT}/docs/config.md`). Take `workDir` (default `.claude/work`; below, `{workDir}`), `contextFiles` and `planReviewers` from it. If the file is missing, every default applies.

## Instructions

### 1. Read the Plan

Read the plan file named in `$ARGUMENTS`.

### 2. Select Reviewers by Content

**With `planReviewers` in the config**: each entry is `{ agent, brief, always?, keywords? }`. Include an entry when `always` is true, or when the plan discusses one of its `keywords` (match on intent, not incidental mentions: a filename that contains a keyword doesn't make the plan about it). If nothing matched, include the first entry.

**Without `planReviewers`**: use the two built-in reviewers below, both on `general-purpose`. Architecture is always included; code quality joins when the plan names types, functions, modules or error handling.

Build a `reviewers` list. Each entry is `{ type, brief }`:
- `type`: the entry's `agent`. It must exist in the project's `.claude/agents/` or be built in (`general-purpose`). If it isn't available in this session, warn and use `general-purpose` with the same brief.
- `brief`: the entry's checklist, followed by: "Read these project files first: {contextFiles}" when the config lists any.
- `model` / `effort`: **omit both.** Each agent's own frontmatter owns its model. Pass an override only for a stated reason, and say why in the report.

### 3. Built-in Reviewer Briefs

Every reviewer returns the **FINDINGS** schema: verdict (`APPROVE` / `APPROVE_WITH_CHANGES` / `REQUEST_CHANGES`), findings (each with `severity` critical/warning/suggestion, `title`, `detail`, `ref`), and any `questions`.

#### Architecture (always)

Review for:
1. **Data flow**: unidirectional? circular dependencies?
2. **Layer separation**: are the project's layers or module boundaries respected? Is each piece in the right place?
3. **Persistence**: appropriate storage approach? lifecycle and migration clear?
4. **Module organisation**: are new files placed where the project's conventions say?
5. **Integration**: how does it connect with existing systems? migration or rollout concerns?

#### Code Quality

Review for:
1. **Project patterns**: does the plan follow the conventions in the context files?
2. **State and concurrency**: race conditions? persistence correct?
3. **Testability**: injectable dependencies? which scenarios need tests?
4. **Error handling**: failure cases addressed? user-visible error state?
5. **Spec breakdown**: does each planned spec make sense as one commit with checkable acceptance?

### 4. Fan Out — Workflow-orchestrated

Multi-agent review is a flat fan-out with structured fan-in. A user-invoked skill is a valid opt-in for `Workflow`. If `Workflow` is disabled, use **Fallback** below.

```
Workflow({ name: 'speclane:review-plan-agents', args: { planFile: PLAN_FILE, plan: <full plan content>, reviewers } })
```

Source: `${CLAUDE_PLUGIN_ROOT}/workflows/review-plan.js`. It runs every reviewer in `parallel()`, which is the barrier: the Workflow returns only once all have landed, each result validated against the `FINDINGS` schema and attributed to its reviewer by position. The reviewers' verbose analysis never enters this session's context — only the compact findings return.

Returns `Array<{ agent, verdict, findings[], questions[] }>`, one per surviving reviewer.

**Fallback** (no `Workflow`): in a **single message**, dispatch every selected reviewer with `Agent({ subagent_type: r.type, run_in_background: false, prompt: <brief + plan> })`. `run_in_background: false` makes each call synchronous, so the barrier is the message itself. Never use `run_in_background: true` here (see the note at the top).

### 5. Deduplicate Findings

Before writing the report, merge overlapping findings across reviewers: keep the more specific one when two say the same thing; keep both when they cover different aspects.

### 6. Report

Write the consolidated report to `{workDir}/reviews/{plan-filename}-review.md`:

```markdown
# Plan Review: {PLAN_FILE}

**Date**: {date} | **Agents**: {list}

## Summary

| Agent | Verdict | Critical | Warnings |
|-------|---------|----------|----------|

**Overall Verdict**: {worst verdict from any agent}

## {Agent} Review
{results}

## Consolidated Action Items

### 🔴 Critical (Must Address)
### 🟡 Warnings (Should Address)
### 🟢 Suggestions

## Open Questions
{Questions from reviewers needing clarification}
```

Map schema severities to headings: `critical` → 🔴, `warning` → 🟡, `suggestion` → 🟢.

### 7. Next Step

If the overall verdict is REQUEST_CHANGES, list the critical items for the user to address before `/speclane:init`. Otherwise point to `/speclane:init {plan file}`.
