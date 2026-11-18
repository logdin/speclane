---
name: finalize
description: Finalize a speclane work item - gate on done specs, dispatch reviewers in parallel, cross-model verify for high-risk paths, one serial analyze/test pass, write the validation report. Run after all specs are implemented and converged.
argument-hint: {work-item}
user-invocable: true
model: sonnet
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Skill
  - Workflow
  - Agent
---

# Finalize Work Item (speclane)

Finalize: **$ARGUMENTS**

> **Project config**: first `Read` `${CLAUDE_PROJECT_DIR}/.claude/speclane.json` (docs: `${CLAUDE_PLUGIN_ROOT}/docs/config.md`). Take `workDir` (default `.claude/work`; below, `{workDir}`), `commands`, `mcpTools`, `contextFiles` and `graderModel` from it. The finalize script reads `reviewers` and `highRisk` from the same file itself. If the file is missing, every default applies: say so once.
> **State model**: git is the authority. A spec's code landed when a commit carries its `Spec: <item>/SPEC-NNN` trailer. Spec frontmatter is a cache that only `/speclane:execute` writes. This skill reads it, reconciles it forward **in memory**, and never edits spec files or the README.

Three checks, three jobs: per-lane converge already graded each spec against its acceptance (`/speclane:execute`). Here, the reviewers judge each `agents.review` group as a whole. The serial gate proves the merged tree analyzes and tests clean. A strict cross-model verifier (pinned `claude-opus-4-6`) adds a completeness pass for items that touch a `highRisk` path.

## 1. Reconcile and gate: the finalize script

One deterministic script does the forward-only reconcile, the `done` gate, changed-file collection, reviewer grouping and the high-risk check. Run it from the repo root, with `{item}` set to the work-item folder name:

```bash
python3 -I - "{workDir}/items/{item}" <<'PYEOF'
import json, os, re, subprocess, sys
item = sys.argv[1].rstrip('/'); slug = os.path.basename(item)
root = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
cfg_path = os.path.join(root, '.claude', 'speclane.json'); cfg = {}; cfg_err = None
if os.path.exists(cfg_path):
    try: cfg = json.load(open(cfg_path))
    except ValueError as e: cfg_err = f'.claude/speclane.json is not valid JSON: {e}'
def glob_re(p):  # path prefix ('src/core/'), exact path, or glob ('*' within a segment, '**' across segments)
    if not any(c in p for c in '*?['): return re.compile(re.escape(p.rstrip('/')) + r'(?:/|$)')
    r, i = '', 0
    while i < len(p):
        if p.startswith('**/', i): r += '(?:.*/)?'; i += 3
        elif p.startswith('**', i): r += '.*'; i += 2
        elif p[i] == '*': r += '[^/]*'; i += 1
        elif p[i] == '?': r += '[^/]'; i += 1
        else: r += re.escape(p[i]); i += 1
    return re.compile(r + '$')
HIGH_RISK = [glob_re(p) for p in cfg.get('highRisk', [])]
RV = cfg.get('reviewers', {}); ALIASES = RV.get('aliases', {})
DEFAULT_REVIEW = RV.get('default', 'general-purpose')
def fm(t, k):  # frontmatter value; a trailing '# comment' is dropped unless the value is quoted
    m = re.search(r'^' + k + r':[ \t]*(.*)$', t, re.M)
    if not m: return None
    v = m.group(1).strip()
    q = re.match(r'(["\'])((?:\\.|(?!\1).)*)\1', v)
    return q.group(2) if q else re.sub(r'\s+#.*$', '', v).strip('"\'')
def git(*a): return subprocess.run(['git', *a], capture_output=True, text=True).stdout
# Trailer commits for this item, oldest first: exact `<item>/SPEC-NNN` values only
found = {}
for line in git('log', '--format=%H%x09%(trailers:key=Spec,valueonly)').splitlines():
    if '\t' not in line: continue
    sha, val = line.split('\t', 1); val = val.strip()
    if val.startswith(slug + '/'): found.setdefault(val[len(slug) + 1:], []).insert(0, sha)
out = {'item': slug, 'errors': [cfg_err] if cfg_err else [], 'notDone': [], 'specs': [], 'groups': [], 'files': [], 'highRisk': []}
specs = {}
for f in sorted(os.listdir(os.path.join(item, 'specs'))):
    if not f.endswith('.md'): continue
    p = os.path.join(item, 'specs', f); t = open(p).read()
    sid = fm(t, 'id') or '-'.join(f.split('-', 2)[:2])
    st = fm(t, 'status')
    if st is None or fm(t, 'lane') is None:
        out['errors'].append(f'{sid}: no status:/lane: in frontmatter (see docs/upgrading-v4.md)'); continue
    m = re.search(r'^agents:[ \t]*\n((?:[ \t]+.*\n?)*)', t, re.M)
    rv = re.search(r'^[ \t]+review:[ \t]*(.*)$', m.group(1), re.M) if m else None
    reviewers = [ALIASES.get(x, x) for x in re.findall(r'[A-Za-z0-9_:-]+', re.sub(r'\s+#.*$', '', rv.group(1)))] if rv else []
    acc = re.search(r'^## Acceptance[ \t]*\n(.*?)(?=^## |\Z)', t, re.M | re.S)
    commits = found.get(sid, [])
    conv = fm(t, 'converge'); conv = None if conv in (None, '', 'null', '~') else conv
    # Forward-only, in memory: approved + trailer commit -> committed. Never sets done; never moves done/blocked/skipped back.
    eff = 'committed' if st == 'approved' and commits else st
    done = bool(commits) and conv in ('pass', 'manual')
    if not done:
        if eff == 'blocked': why = fm(t, 'blocked_reason') or 'blocked (no reason recorded)'
        elif eff == 'skipped': why = 'not run: a dependency or earlier lane-mate is blocked or still draft, or a dependency lane did not finish'
        elif eff == 'draft': why = 'awaiting approval'
        elif not commits: why = f'no `Spec: {slug}/{sid}` trailer commit'
        else: why = f'committed, but converge is {conv or "null"} (needs pass or manual)'
        out['notDone'].append({'spec': sid, 'status': eff, 'converge': conv, 'reason': why})
    specs[sid] = dict(status=eff, commits=commits, reviewers=reviewers or [DEFAULT_REVIEW],
                      acceptance=acc.group(1).strip() if acc else '')
if out['errors'] or out['notDone']:
    print(json.dumps(out, indent=1)); sys.exit(1)
# Changed files per spec: what its trailer commits touched, deleted paths dropped (--diff-filter=d)
allf = set()
for sid, s in specs.items():
    fs = set()
    for sha in s['commits']:
        fs |= {l for l in git('show', '--name-only', '--diff-filter=d', '--format=', sha).splitlines() if l.strip()}
    s['files'] = sorted(x for x in fs if os.path.exists(x))  # also drops paths a later commit deleted
    allf |= set(s['files'])
    out['specs'].append({'spec': sid, 'commits': s['commits'], 'reviewers': s['reviewers'], 'files': s['files']})
# One reviewer group per agents.review value, with the union of its specs' changed files
groups = {}
for sid, s in specs.items():
    for r in s['reviewers']: groups.setdefault(r, []).append(sid)
for r, ids in groups.items():
    out['groups'].append({'type': r, 'scope': ','.join(ids), 'specIds': ids,
                          'files': sorted(set().union(*(specs[i]['files'] for i in ids))),
                          'acceptance': '\n\n'.join(f'=== {i} ===\n{specs[i]["acceptance"]}' for i in ids)})
out['files'] = sorted(allf)
out['highRisk'] = [f for f in out['files'] if any(h.match(f) for h in HIGH_RISK)]
print(json.dumps(out, indent=1))
PYEOF
```

Exit code: `0` all specs `done`, `1` gate failed (errors, or specs not done).

The changed-file rule is the same as this shell form, run per spec and for the whole item:

```bash
git log --format='%H%x09%(trailers:key=Spec,valueonly)' | awk -F'\t' '$2 ~ "^<item>/" {print $1}' \
  | xargs -I{} git show --name-only --diff-filter=d --format= {} | sort -u
```

**Gate.** A spec is `done` only when it has a trailer commit **and** `converge: pass` or `converge: manual`. A `committed` spec with trailers but no passing converge is **not** done. On exit `1`, stop: print `errors`, then a table of every `notDone` entry (spec, status, converge, reason), and tell the user to run `/speclane:execute {item}`, which records the reconcile and converges committed lanes. Change nothing.

On exit `0`, keep the JSON. Steps 2–6 use its `groups`, `files` and `highRisk`.

## 2. Dispatch reviewers (and the high-risk verifier): Workflow-orchestrated

Build one agent entry per `groups` entry. `type` is already resolved through `reviewers.aliases`; an agent named there must exist in the project's `.claude/agents/` (or be a built-in such as `general-purpose`). If a `type` isn't available in this session, warn and use `general-purpose` for that group. Each reviewer's prompt is `${CLAUDE_SKILL_DIR}/reviewer-prompt.md`, filled in:

| Placeholder | Value |
|-------------|-------|
| `{agent_type}` | the group's `type` |
| `{work_item}` | `{item}` |
| `{context_files}` | `contextFiles` from the config, one per line (or `none`) |
| `{spec_ids}` | the group's `specIds`, one per line |
| `{acceptance}` | the group's `acceptance` (each spec's `## Acceptance`, under an `=== SPEC-NNN ===` line) |
| `{files}` | the group's `files`: the union of its specs' changed files, one per line |

When `highRisk` is non-empty, also pass `verify.brief`. It names the item, its spec IDs, the commit list from `specs[].commits`, the `highRisk` files, the spec folder to check against (`{workDir}/items/{item}/specs/`) and the `contextFiles`. Pass `verify.model` only when the config sets `graderModel`; otherwise pass none and the workflow pins its verifier to `claude-opus-4-6`. When `highRisk` is empty, omit `verify`.

```
Workflow({ name: 'speclane:finalize-agents', args: { workItem: '{item}', agents: [{ type, scope, prompt }, ...], verify: { brief, model? } } })
```

Source: `${CLAUDE_PLUGIN_ROOT}/workflows/finalize.js`. Returns `{ reviews: Array<{ agent, scope, summary, score?, findings[], filesChanged[] }>, verify: { verdict, findings[] } | null }`.

**Fallback** (no `Workflow`): dispatch each entry with `Agent({ subagent_type: type, run_in_background: false, prompt })`, and the verifier with `Agent({ subagent_type: "general-purpose", model: "{graderModel, default claude-opus-4-6}", run_in_background: false, prompt: brief })`.

A reviewer that returned nothing is listed in the report as "no result". It isn't retried.

## 3. Auto-fix and format

When the config has `commands.fix` and/or `commands.format`, run them (in that order) with `{files}` replaced by the item's `files` plus any reviewer's `filesChanged`. Prefer the matching `mcpTools` when they're available in this session. Leave the resulting edits uncommitted and list them in the report. With neither configured, skip this step and say so.

## 4. Write the verifier's result (high-risk items only)

When the workflow returned `verify`, write it to `{workDir}/items/{item}/reports/verify-{date}.md` (verdict, then findings by severity) and link that file from the validation report. When `highRisk` was empty, say "skipped: no high-risk files" in the report.

## 5. Serial gate: one full analyze and test pass

Run this only after every reviewer (and the verifier, when it ran) has returned. Run the gate commands one after the other in Bash, never in parallel and never per file:
- `commands.gate` from the config, when set (a list of commands, run in order); otherwise
- `commands.analyze`, then `commands.test`, each with `{files}` replaced by nothing (whole project).

With none configured, record "no gate commands configured" and treat the gate as **not run** (not a pass).

Record each command's exit code and the tail of its output (issue count, then pass/fail counts). Both results go in the validation report. A failure doesn't stop the report; it makes the item's verdict **fail**.

## 6. Write the validation report

Write to `{workDir}/items/{item}/reports/validation-{date}.md`:

```markdown
# Validation Report: {item}

**Date**: {date}
**Specs**: {count} done

## Summary

| Check | Status |
|-------|--------|
| Gate: `{each command}` | {pass/fail, issue or test counts} |
| Reviews | {n} groups, {critical}/{warning}/{suggestion} findings |
| Cross-model verify | {verdict + link to reports/verify-{date}.md, or "skipped: no high-risk files"} |

## Specs

| Spec | Commits | Reviewer(s) |
|------|---------|-------------|

## Agent Reviews

{For each group: type, scope (spec IDs), summary, score, findings}

## Files Changed

{`files` from the finalize script}

## Auto-fix Edits

{files changed by step 3, uncommitted}
```

## 7. Report completion

```markdown
## Work Item Finalized: {item}

| Metric | Value |
|--------|-------|
| Specs | N done |
| Files | M changed |
| Gate | pass/fail per command |
| Reviews | critical/warning/suggestion counts |
| Cross-model verify | verdict or skipped |
| Report | reports/validation-{date}.md |
```

Merging: the item's branch goes in with `git merge --no-ff` (never squash or rebase: the per-spec commits and their `Spec:` trailers are the record). See `${CLAUDE_PLUGIN_ROOT}/docs/runbook.md`.
