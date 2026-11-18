---
name: plan
description: Create or convert a structured implementation plan for /speclane:init. Accepts a feature name OR an existing document (PRD, ADR, design doc) to convert.
argument-hint: [feature-name | --from doc.md | @doc.md]
disable-model-invocation: true
user-invocable: true
context: fork
agent: general-purpose
model: opus
effort: xhigh
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Agent
  - AskUserQuestion
  - TaskCreate
  - TaskUpdate
  - TaskGet
  - TaskList
---

# Create Implementation Plan

This planning task runs at `xhigh` reasoning effort (set in frontmatter) for comprehensive architectural analysis.

Create or convert a structured implementation plan for: **$ARGUMENTS**

> **Project config**: first `Read` `${CLAUDE_PROJECT_DIR}/.claude/speclane.json` (docs: `${CLAUDE_PLUGIN_ROOT}/docs/config.md`). Take `workDir` (default `.claude/work`; below, `{workDir}`) and read every file in `contextFiles` before exploring. If the file is missing, every default applies.

## Input Modes

| Input | Mode |
|-------|------|
| Feature name (no `.md`, no `@`, no `--from`) | **Create from scratch**: explore → ask user → architect → write |
| `--from doc.md` or `@doc.md` | **Convert**: read source → extract → ask only for missing → write |

**Output**: `{workDir}/plans/{feature-slug}.md` using the template at `${CLAUDE_SKILL_DIR}/plan-template.md`.

## Deep Analysis Required

Before creating plan, analyze:
1. **Architecture**: fit with existing, dependencies, layers affected
2. **Edge cases**: failure modes, error handling, validation
3. **Trade-offs**: performance vs simplicity, flexibility vs maintainability
4. **Maintainability**: extensibility, testability, documentation

## Mode A: Create from Scratch

### 1. Optional Task Tracking

For complex features: `TaskCreate` with `{ level: "plan", feature: slug }`. Skip for simple plans.

### 2. Analyze Requirements

If scope unclear, `AskUserQuestion` with options: Core only / Full feature / Let me specify.

### 3. Explore Codebase

```javascript
Agent({
  subagent_type: "Explore",
  prompt: `Find patterns related to {feature}:
    - Similar features and the modules they live in
    - Relevant domain types and shared helpers
    - Data-access and wiring patterns
    - Conventions from the project's contextFiles
    Return: file paths, key patterns, dependencies`
})
```

### 4. Gather Design Decisions

`AskUserQuestion` for key decision points. Common categories:
- Data storage (local / server / hybrid)
- Feature gating or rollout
- State and ownership of data
- Error handling strategy
- UI complexity (single screen vs flow)

### 5. Architecture Consultation (If Complex)

Use the project's architecture reviewer if `reviewers` in the config names one; otherwise `general-purpose`.

```javascript
Agent({
  subagent_type: "{architecture reviewer or general-purpose}",
  prompt: `Design architecture for {feature}:
    Context: {exploration results}
    Decisions: {user choices}
    Provide: layer/module structure, type design, wiring, spec breakdown, risks`
})
```

### 6. Write Plan

Use `${CLAUDE_SKILL_DIR}/plan-template.md`. Write to `{workDir}/plans/{feature-slug}.md`.

### 7. Output Summary

```markdown
## Plan Created
**Path**: {workDir}/plans/{slug}.md
**Specs**: {N} across {M} phases
**Decisions**: {N} captured

### Next Steps
1. Review the plan (optionally `/speclane:review-plan {workDir}/plans/{slug}.md`)
2. `/speclane:init {workDir}/plans/{slug}.md`
```

## Mode B: Convert Existing Document

### C1. Read and Extract

| Source Section | Maps To |
|----------------|---------|
| Problem/Goal | Overview |
| Functional requirements | Spec candidates |
| Non-functional requirements | Quality criteria |
| Architecture notes | File structure, dependencies |
| Decisions | Design Decisions section |
| Open questions | Items needing AskUserQuestion |

### C2. Ask ONLY for Missing Info

Do NOT ask about items already decided in source doc or inferable from codebase patterns.

### C3. Write Converted Plan

Include conversion note: source path, date, assumptions made.
