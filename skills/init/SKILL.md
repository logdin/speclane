---
name: init
description: Initialize a speclane work item from a plan file or feature name. Writes thin draft specs, forms lanes, and creates {workDir}/items/{slug}/ for you to review and approve before /speclane:execute.
argument-hint: [plan.md | feature-name]
disable-model-invocation: true
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Agent
---

# Initialize Specification Work Item (speclane)

Generate specifications for: **$ARGUMENTS**

> **Runs in the main session, on purpose.** Breaking a plan into specs is the planner's most consequential call, so it uses the session's model and the context you've built with it. Do not add `context: fork` or `model:`.
>
> **Project config**: first `Read` `${CLAUDE_PROJECT_DIR}/.claude/speclane.json` (docs: `${CLAUDE_PLUGIN_ROOT}/docs/config.md`). Use:
> - `workDir` (default `.claude/work`); below, `{workDir}` means that value;
> - `contextFiles`: read each one now, before anything else (project patterns, rules, platform notes);
> - `commands`: the project's test / analyze commands, used in every spec's `## Acceptance`;
> - `reviewers`: routing for each spec's `agents.review` (step 3);
> - `derivedFiles`: generated files a commit may include (mention them in `## Files` comments, never list them as rows).
>
> If the file is missing, tell the user every default applies (no commands, `general-purpose` reviewer, `.claude/work`) and offer to draft one from the repo's build files (`package.json`, `pubspec.yaml`, `pyproject.toml`, `Makefile`, …) using `${CLAUDE_PLUGIN_ROOT}/examples/` as a model. Write it only after the user says yes.

Output is **drafts only**. Nothing here implements code, and nothing here sets `approved`. That's the user's call (step 6).

## Input Modes

| Input | Mode |
|-------|------|
| Path ending `.md`, starts with `@` or `{workDir}/plans/` | Plan file: extract structure, don't re-ask decided items |
| Anything else | Feature name: explore the codebase first; may ask questions |

## 1. Detect Mode & Load Context

**Plan file**: read the plan. Extract the feature name, decisions, spec breakdown, interfaces, and any lanes it suggests. Plan lanes are **advisory**: step 4 re-derives them by the rules.

**Feature name**: explore the codebase:
- `Glob` for similar features and the modules they live in
- `Grep` for related types, entities and functions
- Follow the conventions the `contextFiles` describe
- Gather: similar features, domain types, data-access and wiring patterns, worked examples a worker can copy

## 2. Create the Work Item

```
{workDir}/items/{slug}/
├── README.md        # from readme-template.md (issue:, plan:, lanes table, specs table)
├── context/
│   └── PLAN.md      # copy of the plan
├── specs/
│   └── SPEC-NNN-{name}.md
└── reports/         # handoff-check.md (step 5), deviations.md + validation (later)
```

Templates live next to this skill: `${CLAUDE_SKILL_DIR}/readme-template.md`, `${CLAUDE_SKILL_DIR}/spec-template.md`, `${CLAUDE_SKILL_DIR}/adr-template.md` (for a decision worth its own record).

Fill `Issue:` in the README if the plan or the user names an issue. Otherwise write "none filed"; spec commits then carry no `Refs:` line.

## 3. Generate Specs

Write each spec from `${CLAUDE_SKILL_DIR}/spec-template.md`. **Thin specs**: decisions, interfaces, acceptance. Never implementation code.

**Frontmatter** (every spec):

```yaml
status: draft        # always draft here
lane: {X}            # assigned in step 4
commits: []
converge: null
rounds: 0
blocked_reason: null
```

**Sections**:
- `## Files`: the worker's allowed paths.
- `## Interfaces`: signatures and data shapes only, in the project's language. Delete the section if the spec adds no API.
- `## Validation`: required for money, calculation or other domain logic with concrete expected outputs.
- `## Acceptance`: Given/When/Then plus runnable commands. Use the project's configured `commands.test` / `commands.analyze` (with `{files}` replaced by the spec's paths). Criteria must still hold after later lane-mates land, and commands must work in zsh with macOS (BSD) tools. Every recursive grep over `.` or `.claude` adds `--exclude-dir=worktrees`: `.claude/worktrees/` holds other sessions' checkouts, which would otherwise match (or use `git grep`, which only searches tracked files).

**Size check** (apply to every spec before step 4):

| Too big: split it | Too small: fold into a neighbour |
|---|---|
| Crosses layers, touches more than ~5 non-test files, or has more than ~6 functional criteria | Can't be checked on its own (a rename, a barrel export) |

Mechanical sweeps (comment-only or rename-only edits across many files) may exceed the file count; say why in the spec's Context.

One spec = one commit, so a spec should be something you'd want as a single commit in history.

**Review agent routing** (`agents.review`, chosen by the spec's `## Files` paths): walk `reviewers.routes` in `.claude/speclane.json` in order; the first route with a pattern matching any of the spec's paths gives the agent. A spec may list several reviewers when its files match several routes (`review: [a, b]`). With no match, use `reviewers.default` (default `general-purpose`). Resolve names through `reviewers.aliases`. Never route to `speclane:converge` or `speclane:handoff-check`: those are workflow agents, not reviewers.

**Layer breakdown** (feature-name mode): follow the project's layering from its `contextFiles`; otherwise order specs from the innermost types outward (domain types → storage/data access → wiring/state → UI or API surface).

## 4. Form Lanes

A lane is the specs **one worker implements in sequence**, keeping its context. Lanes run one at a time, in dependency order. Assign every spec a `lane:` and write the README lanes table. **Lane names are single capital letters** (`A`–`Z`): the scripts parse the lanes table by that pattern, so `api` or `L1` would make pre-flight fail.

**Rules** (all must hold; `/speclane:execute` pre-flight re-checks them):
1. Within a lane, specs are ordered so each spec's `depends_on` comes earlier in the lane or in another lane.
2. A lane depends on every other lane that holds a dependency of one of its specs.
3. **A spec that a spec in another lane depends on must be the LAST spec in its lane.** If it isn't, move the specs after it into a new lane.
4. **The lane graph must be acyclic.** If it has a cycle, split lanes (rule 3 usually does it) until it doesn't. Never write the README with a cycle in it.
5. Worker model is a lane property. Use `sonnet` only when every spec in the lane is mechanical (moves, renames, config); otherwise use `default`. If a lane mixes the two, split it.

Prefer fewer, longer lanes for chains that touch the same area. Use separate lanes for independent work.

**Check before writing the README**. Run this, or an equivalent, and fix any output except the final `acyclic OK` line:

```bash
python3 -I - "{workDir}/items/{slug}" <<'EOF'
import re,glob,sys,os
d=sys.argv[1]; specs={}
for f in glob.glob(os.path.join(d,'specs','*.md')):
    t=open(f).read()
    i=re.search(r'^id: (\S+)',t,re.M).group(1); l=re.search(r'^lane: (\S+)',t,re.M).group(1)
    specs[i]=(l,re.findall(r'SPEC-\d+',re.search(r'^depends_on: (.*)$',t,re.M).group(1)))
lanes={}
for m in re.finditer(r'^\| ([A-Z]) \| (SPEC[^|]*)\|',open(os.path.join(d,'README.md')).read(),re.M):
    lanes[m.group(1)]=re.findall(r'SPEC-\d+',m.group(2))
ok=sorted(sum(lanes.values(),[]))==sorted(specs)
if not ok: print('README and spec files list different specs')
for s,(L,ds) in specs.items():
    if s not in lanes.get(L,[]): print('lane mismatch',s); ok=False
    for x in ds:
        xl=specs[x][0]
        if xl!=L and lanes[xl][-1]!=x: print('rule 3:',s,'depends on mid-lane',x); ok=False
        if xl==L and lanes[L].index(x)>lanes[L].index(s): print('rule 1: order',s,x); ok=False
g={L:{specs[x][0] for s in ss for x in specs[s][1] if specs[x][0]!=L} for L,ss in lanes.items()}
seen,st=set(),set()
def cyc(n):
    if n in st: return True
    if n in seen: return False
    seen.add(n); st.add(n); r=any(cyc(m) for m in g[n]); st.discard(n); return r
c=any(cyc(n) for n in g)
print('cycle' if c else 'acyclic', 'OK' if ok and not c else 'FAIL')
EOF
```

## 5. Hand-off Check

Dispatch the read-only `speclane:handoff-check` agent **once**, synchronously. It checks, on a model different from yours, whether each draft stands on its own. **When the config sets `graderModel`, always pass it as `model`**, even if it's the model you are running on: the config is the user's choice, so never swap it for the pin yourself. In that case add one line to the step 6 summary: "Warning: graderModel equals the planner's model, so the hand-off check isn't cross-model." When `graderModel` is unset, pass no `model` (the agent's pin `claude-opus-4-6` applies).

```
Agent({
  subagent_type: "speclane:handoff-check",       // no model arg: its frontmatter pin (claude-opus-4-6) applies
  model: "{graderModel}",                       // ONLY when .claude/speclane.json sets graderModel; otherwise omit this line
  description: "Hand-off check {slug}",
  prompt: "Work item: {workDir}/items/{slug}/. Spec template: ${CLAUDE_SKILL_DIR}/spec-template.md. Project context files: {contextFiles, comma-separated, or none}. Project commands: {commands from .claude/speclane.json, or none}. Run the five checks on every spec with status: draft and return your JSON block."
})
```

Parse the final fenced `json` block (`summary`, `findings[]`, `clean[]`) and write `reports/handoff-check.md`:

```markdown
# Hand-off check: {slug}

**Date**: {date} · **Agent**: speclane:handoff-check ({model reported in the transcript})
**Summary**: {summary}

## Blockers
| Spec | Check | Detail | Ref |
|------|-------|--------|-----|

## Warnings
| Spec | Check | Detail | Ref |

## Notes
| Spec | Check | Detail | Ref |

**Clean**: {clean, comma-separated}
```

Omit empty tables. Don't fix the specs yourself here: report the findings in the summary (step 6) and let the user decide. If they ask, edit the specs, then re-run this step. It's one dispatch per request, never an automatic loop.

If the agent returns no parsable JSON block, write the report with its raw final message under `## Unparsed output`, and say so in the summary.

## 6. Summary

```markdown
## Work Item Created (drafts)

**Source**: {plan path OR "Feature: {name}"}
**Path**: {workDir}/items/{slug}/
**Issue**: #{N} | none filed
**Specs**: {N} drafts in {L} lanes

| Lane | Specs (in order) | Worker | Depends on lanes |
|------|------------------|--------|------------------|
| A | SPEC-001, SPEC-002 | default | — |

| Spec | Title | Lane | Depends On |
|------|-------|------|------------|
| SPEC-001 | {Title} | A | — |

Hand-off check: {N blockers, M warnings, P notes; see reports/handoff-check.md}
{list each blocker in one line: spec, check, detail}

### Next Steps
1. Review the specs (and `reports/handoff-check.md`). Edit anything you'd change. This is the cheapest place to change course.
2. **Approve** by setting `status: approved` in each spec you accept (or ask Claude to). Only approved specs run.
3. `/speclane:execute {slug} --dry-run` to see the run order, then `/speclane:execute {slug}`.
```
