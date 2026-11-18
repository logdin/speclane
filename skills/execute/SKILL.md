---
name: execute
description: Execute a speclane work item's approved specs. Pre-flight and reconcile state from git, run lanes one at a time through the speclane execute workflow, record results, and converge each lane.
argument-hint: {work-item} [SPEC-ID] [--dry-run]
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Skill
  - Workflow
  - Agent
---

# Execute Specification Work Item (speclane, v5 state model)

Execute: **$ARGUMENTS**

> **Project config**: first `Read` `${CLAUDE_PROJECT_DIR}/.claude/speclane.json` (schema: `${CLAUDE_PLUGIN_ROOT}/schema/speclane.schema.json`, docs: `${CLAUDE_PLUGIN_ROOT}/docs/config.md`). Take `workDir` from it (default `.claude/work`); below, `{workDir}` means that value. If the file is missing, every default applies: say so once and continue. The state script reads the same file itself and passes `commands`, `derivedFiles`, `contextFiles` and `mcpTools` to the workflow, so never copy them by hand.
> **State model**: git is the authority. A spec's `Spec: <item>/SPEC-NNN` commit trailer says its code landed. Frontmatter is a cache this skill reconciles forward, and **this skill is its only writer** (workers write code and commits only). You (the user) write `draft → approved` and unblock.

## Modes

```
/speclane:execute {item}              # run every approved lane, then converge, record, bookkeeping
/speclane:execute {item} --dry-run    # §1–§4 only: print what would run; write nothing, commit nothing
/speclane:execute {item} SPEC-NNN     # one spec as a one-spec lane (rules in §7)
```

Every run resumes: there is no separate resume flag. Re-running after a crash, a block or an unblock is the normal path.

## States

| Status | Meaning | Who sets it |
|--------|---------|-------------|
| `draft` | Written by /speclane:init, not yet approved | init |
| `approved` | Approved, no commit yet | You |
| `committed` | Its `Spec:` trailer commit exists; not yet graded | This skill (reconcile) |
| `done` | Committed **and** converge `pass` (or `manual`: a criterion checked by hand) | This skill (§8), or you for `manual` |
| `blocked` | 3 failed converge rounds, or the worker failed before committing | This skill |
| `skipped` | Didn't run because a dependency or earlier lane-mate is blocked | This skill |

A spec is **held** while any spec in its `depends_on`, or any earlier spec in its lane, is `blocked`, is still `draft`, or is itself held (so holding passes down a chain of dependencies). Held specs are never sent to the workflow, not even `committed` ones, so nothing builds past a blocked spec.

## §1 Pre-flight, §2 Reconcile, §3 Guard, §4 Build Input: the state script

These four steps are one deterministic script, so the state rules are never applied by memory. Run it from the repo root (the second argument is this skill's folder; it tells workers where the §5 contract lives):

```bash
python3 -I - "{workDir}/items/{item}" "${CLAUDE_SKILL_DIR}" [--write] <<'PYEOF'
import json, os, re, subprocess, sys
item = sys.argv[1].rstrip('/'); write = '--write' in sys.argv[2:]
skill_dir = next((a for a in sys.argv[2:] if a != '--write'), '')
slug = os.path.basename(item)
root = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
STATUSES = {'draft', 'approved', 'committed', 'done', 'blocked', 'skipped'}
def fm(t, k):  # frontmatter value; a trailing '# comment' is dropped unless the value is quoted
    m = re.search(r'^' + k + r':[ \t]*(.*)$', t, re.M)
    if not m: return None
    v = m.group(1).strip()
    q = re.match(r'(["\'])((?:\\.|(?!\1).)*)\1', v)
    return q.group(2) if q else re.sub(r'\s+#.*$', '', v).strip('"\'')
out = {'item': slug, 'errors': [], 'changes': [], 'held': [], 'awaiting': [], 'dirty': [], 'input': None, 'order': [], 'wouldSkip': []}
# ---- speclane config (.claude/speclane.json at the repo root; every key optional)
cfg_path = os.path.join(root, '.claude', 'speclane.json'); cfg = {}
if os.path.exists(cfg_path):
    try: cfg = json.load(open(cfg_path))
    except ValueError as e: out['errors'].append(f'.claude/speclane.json is not valid JSON: {e}')
settings = dict(workDir=cfg.get('workDir', '.claude/work'), contractFile=os.path.join(skill_dir, 'SKILL.md') if skill_dir else '',
                commands=cfg.get('commands', {}), derivedFiles=cfg.get('derivedFiles', []),
                contextFiles=cfg.get('contextFiles', []), mcpTools=cfg.get('mcpTools', []))
if not os.path.isdir(os.path.join(item, 'specs')):
    out['errors'].append(f'{item}: no specs/ folder (wrong item name, or workDir in .claude/speclane.json)'); print(json.dumps(out, indent=1)); sys.exit(1)
# ---- §1 Pre-flight: parse specs + README, check v5 format and lane rules 1-5
specs = {}
for f in sorted(os.listdir(os.path.join(item, 'specs'))):
    if not f.endswith('.md'): continue
    p = os.path.join(item, 'specs', f); t = open(p).read()
    sid = fm(t, 'id') or f.split('-', 2)[0] + '-' + f.split('-', 2)[1]
    if not fm(t, 'id'): out['errors'].append(f'{f}: no id: in frontmatter'); continue
    st, ln = fm(t, 'status'), fm(t, 'lane')
    if st is None or ln is None:
        out['errors'].append(f'{sid}: no status:/lane: in frontmatter. Start from skills/init/spec-template.md, or see speclane docs/upgrading-v4.md for specs in an older format'); continue
    if st not in STATUSES: out['errors'].append(f'{sid}: unknown status {st!r}')
    files = []
    sec = re.search(r'^## Files[ \t]*\n(.*?)(?=^## |\Z)', t, re.M | re.S)
    if sec:
        files = [m.strip() for m in re.findall(r'^\|\s*(?:CREATE|MODIFY|DELETE|TEST)\s*\|\s*`([^`]+)`', sec.group(1), re.M)]
    specs[sid] = dict(path=p, status=st, lane=ln, deps=re.findall(r'SPEC-\d+', fm(t, 'depends_on') or ''),
                      commits=re.findall(r'[0-9a-f]{7,40}', fm(t, 'commits') or ''), rounds=int(fm(t, 'rounds') or 0), files=files)
lanes, order_in = {}, []
for m in re.finditer(r'^\|\s*([A-Z])\s*\|\s*(SPEC[^|]*)\|\s*(\w+)\s*\|\s*([^|]*)\|', open(os.path.join(item, 'README.md')).read(), re.M):
    lanes[m.group(1)] = dict(specs=re.findall(r'SPEC-\d+', m.group(2)), worker=m.group(3), deps=re.findall(r'\b[A-Z]\b', m.group(4)))
    order_in.append(m.group(1))
if not out['errors']:
    listed = sorted(s for l in lanes.values() for s in l['specs'])
    if listed != sorted(specs): out['errors'].append(f'README lanes table lists {listed}, spec files are {sorted(specs)}')
    for name, l in lanes.items():
        if l['worker'] not in ('default', 'sonnet'): out['errors'].append(f'lane {name}: worker must be default or sonnet, got {l["worker"]!r}')
        for d in l['deps']:
            if d not in lanes: out['errors'].append(f'lane {name}: depends on unknown lane {d}')
    for sid, s in specs.items():
        if sid not in lanes.get(s['lane'], {}).get('specs', []): out['errors'].append(f'{sid}: frontmatter lane {s["lane"]} does not match the README lanes table')
    for sid, s in specs.items():
        for d in s['deps']:
            if d not in specs: out['errors'].append(f'{sid}: depends on unknown {d}'); continue
            dl, L = specs[d]['lane'], s['lane']
            if dl == L and lanes[L]['specs'].index(d) > lanes[L]['specs'].index(sid): out['errors'].append(f'rule 1: {sid} comes before its dependency {d} in lane {L}')
            if dl != L and lanes[dl]['specs'][-1] != d: out['errors'].append(f'rule 3: {sid} (lane {L}) depends on {d}, which is mid-lane in {dl}')
            if dl != L and dl not in lanes[L]['deps']: out['errors'].append(f'rule 2: lane {L} must list lane {dl} in "Depends on lanes"')
    seen, stack = set(), []
    def cyc(n):
        if n in stack: return stack[stack.index(n):] + [n]
        if n in seen: return None
        seen.add(n); stack.append(n)
        for m in lanes[n]['deps']:
            if m in lanes:
                c = cyc(m)
                if c: return c
        stack.pop(); return None
    for n in lanes:
        c = cyc(n)
        if c: out['errors'].append('rule 4: lane cycle ' + ' -> '.join(c)); break
if out['errors']:
    print(json.dumps(out, indent=1)); sys.exit(1)
# ---- §2 Reconcile: commits from exact trailer values; forward-only status moves
log = subprocess.run(['git', 'log', '--format=%H%x09%(trailers:key=Spec,valueonly)'], capture_output=True, text=True).stdout
found = {}
for line in log.splitlines():
    if '\t' not in line: continue
    sha, val = line.split('\t', 1)
    if val.strip().startswith(slug + '/'): found.setdefault(val.strip()[len(slug) + 1:], []).insert(0, sha)  # oldest first
new = {}
for sid, s in specs.items():
    have = s['commits']; add = [x for x in found.get(sid, []) if not any(x.startswith(h) or h.startswith(x) for h in have)]
    st = s['status']
    if add and st == 'draft': out['changes'].append(f'{sid}: has trailer commits but is still draft; left as draft')
    elif add or (st == 'approved' and have):
        # approved + any commit (new or already recorded, e.g. after an unblock) -> committed;
        # never touches done / blocked / skipped / committed
        nst = 'committed' if st == 'approved' else st
        new[sid] = dict(status=nst, commits=have + add)
        out['changes'].append(f'{sid}: ' + (f'commits +{len(add)}' if add else 'has commits') + (f', {st} -> {nst}' if nst != st else ''))
    if sid in new: s['status'], s['commits'] = new[sid]['status'], new[sid]['commits']
blocked = {sid for sid, s in specs.items() if s['status'] == 'blocked'}
holding = blocked | {sid for sid, s in specs.items() if s['status'] == 'draft'}  # a draft hasn't been approved: nothing builds on it
_held = {}
def held(sid, seen=()):  # transitive: behind a blocked or draft spec, or behind a spec that is itself held
    if sid not in _held:
        s = specs[sid]; mates = lanes[s['lane']]['specs']
        before = [d for d in s['deps'] + mates[:mates.index(sid)] if d not in seen]
        _held[sid] = any(d in holding or held(d, seen + (sid,)) for d in before)
    return _held[sid]
for sid, s in specs.items():
    if s['status'] == 'skipped' and not held(sid):
        s['status'] = 'approved'; new.setdefault(sid, {'commits': s['commits']})['status'] = 'approved'
        out['changes'].append(f'{sid}: skipped -> approved (no longer held)')
    if s['status'] in ('approved', 'committed', 'skipped') and held(sid): out['held'].append(sid)
    if s['status'] == 'draft': out['awaiting'].append(sid)
# ---- §3 Guard: uncommitted changes in any non-draft, non-done spec's ## Files (pathspecs passed as argv, never shell-globbed)
for sid, s in specs.items():
    if s['status'] in ('draft', 'done') or not s['files']: continue
    st = subprocess.run(['git', 'status', '--porcelain', '--'] + s['files'], capture_output=True, text=True, cwd=root).stdout
    paths = [l[3:] for l in st.splitlines() if l.strip()]
    if paths: out['dirty'].append({'spec': sid, 'paths': paths})
# ---- §4 Build the workflow input (workflows/execute.js args) + the serial order it would run
done_lane = lambda n: all(specs[x]['status'] == 'done' for x in lanes[n]['specs'])
inp = []
for n in order_in:
    send = [x for x in lanes[n]['specs'] if specs[x]['status'] in ('approved', 'committed') and x not in out['held']]
    if send:
        inp.append(dict(lane=n, worker=lanes[n]['worker'], dependsOn=[d for d in lanes[n]['deps'] if not done_lane(d)],
                        specs=[dict(specId=x, specPath=os.path.relpath(specs[x]['path'], root), files=specs[x]['files'],
                                    status=specs[x]['status'], commits=specs[x]['commits'], rounds=specs[x]['rounds']) for x in send]))
out['input'] = {'workItem': slug, 'settings': settings, 'lanes': inp}
names, fin, bad = {l['lane'] for l in inp}, set(), set()
for l in inp:
    if any(d not in names for d in l['dependsOn']): bad.add(l['lane']); out['wouldSkip'].append(f'{l["lane"]}: dependency lane not runnable')
while True:
    for l in inp:
        if l['lane'] not in fin | bad and any(d in bad for d in l['dependsOn']):
            bad.add(l['lane']); out['wouldSkip'].append(f'{l["lane"]}: depends on a lane that would not run')
    nxt = next((l for l in inp if l['lane'] not in fin | bad and all(d in fin for d in l['dependsOn'])), None)
    if not nxt: break
    fin.add(nxt['lane']); out['order'].append(nxt['lane'] + ': ' + ' -> '.join(x['specId'] for x in nxt['specs']))
# ---- Write the reconciled cache (only with --write, and only when nothing blocks the run)
if write and not out['dirty']:
    for sid, ch in new.items():
        p = specs[sid]['path']; t = open(p).read()
        t = re.sub(r'^status:.*$', 'status: ' + specs[sid]['status'], t, count=1, flags=re.M)
        t = re.sub(r'^commits:.*$', 'commits: [' + ', '.join(specs[sid]['commits']) + ']', t, count=1, flags=re.M)
        open(p, 'w').write(t)
    out['written'] = sorted(new)
print(json.dumps(out, indent=1))
sys.exit(2 if out['dirty'] else 0)
PYEOF
```

Exit code: `0` ready, `1` pre-flight errors, `2` dirty tree.

### §1 Pre-flight
Always run the script **without** `--write` first. On exit `1`, stop before anything else: print each entry of `errors` and change nothing. A spec without `status:`/`lane:` is in an older format, or was written by hand without the template. Point the user to `${CLAUDE_PLUGIN_ROOT}/docs/upgrading-v4.md`.

### §2 Reconcile
Report `changes` to the user. Reconcile only moves forward:
- It fills `commits` from trailer values that match `<item>/SPEC-NNN` exactly. It doesn't search commit messages.
- `approved` becomes `committed` when a commit exists. It never sets `done` (that takes a converge pass, §8).
- It never overrides `done`, `blocked`, `skipped` or `committed`.
- A `skipped` spec returns to `approved` once it's no longer held.

### §3 Guard
On exit `2`, stop. For each `dirty` entry, print the spec and its paths, then offer the user the two recovery options, and run **neither** yourself:
1. Commit the changes (if they're wanted work), or
2. Discard them: `git restore --source=HEAD --staged --worktree -- <paths>`

Never set work aside with the stash stack: it's shared with other sessions and worktrees. The dirty spec is usually the one a killed run or a failed worker was in the middle of.

### §4 Build input and run
Print `order` (lanes in run order, specs in each), `wouldSkip`, `held` ("held behind a blocked or draft spec") and `awaiting` ("awaiting approval: set `status: approved` to include").

- **`--dry-run`**: stop here. You've written nothing and committed nothing, so `git log -1` is unchanged.
- If `input.lanes` is empty: say there's nothing to run, and stop.
- Otherwise run the script again **with `--write`** to store the reconciled cache. Then:

```
Workflow({ name: 'speclane:execute-lanes', args: <input from the script output> })
```

Pass `input` exactly as printed, `settings` included. The workflow runs one lane at a time and returns `{ lanes, skipped }` (see `${CLAUDE_PLUGIN_ROOT}/workflows/execute.js`). §5–§8 handle the worker contract, recording results, bookkeeping and converge results.

## §5 Worker contract

The workflow's lane worker follows this section for every spec. It's the one source of truth for how spec work is committed.

1. **Never touch `{workDir}/items/`**, with one exception: a path there that the spec's `## Files` lists explicitly may change (for example a spec that moves another work item into `archive/`). `## Files` wins for those paths only. Even when listed, never edit **this item's** spec frontmatter, its `README.md` or its `reports/`: report state in your result and this skill records it. The workflow's worker and fix prompts carry the same rule (`ITEMS_RULE` in `workflows/execute.js`).
2. **One commit per spec**, made only after its checks pass:

```bash
git add -- <new/modified path> <another path>      # each path is its own argument; zsh won't split a variable
git rm -r -- <deleted path>                        # deletions: git add fails on a path that's gone from disk
git mv <old> <new>                                 # moves: then pass BOTH old and new paths below
git commit --only -F <msgfile> -- <every new, modified, deleted, old and new path>
```

   - `--only` commits exactly those paths and leaves anything else in the tree or index alone.
   - `<msgfile>` is written **outside the repo** (the session scratchpad, or `${TMPDIR:-/tmp}`). Its last paragraph is the trailer block:

```
<type>(<scope>): <summary>

<what and why, short>

Spec: <item>/SPEC-NNN
Refs: #N
```

   - Use exactly one `Spec:` trailer. Add `Refs: #N` only if the work-item README names an issue. Never use `fixes`/`closes`: the closing keyword goes in the `--no-ff` merge commit, once the whole item is done.
3. **Paths** = the spec's `## Files` (rule 1 limits any under `{workDir}/items/`) plus derived files (tests for the changed code, and the project's `derivedFiles` from `.claude/speclane.json`, which the workflow prompt lists). Anything else you had to change goes in `deviations`.
4. **On failure, stop.** Return `failedAt`/`failure`. **Leave your partial edits in place**: don't discard, revert or set them aside. The user decides (§7 prints the commands).

## §6 Write results

After the workflow returns, save its return to `{returnFile}`: run `printf '%s\n' "${TMPDIR:-/tmp}"` once and use `<that folder>/speclane-{item}-return.json` (an absolute path, outside the repo; the `Write` tool doesn't expand variables). Then run the results script. It's the only thing that writes spec state from a run:

```bash
python3 -I - "{workDir}/items/{item}" "{returnFile}" <<'PYEOF'
import json, os, re, subprocess, sys, datetime
item, ret = sys.argv[1].rstrip('/'), json.load(open(sys.argv[2]))
slug = os.path.basename(item)
def fm(t, k):  # frontmatter value; a trailing '# comment' is dropped unless the value is quoted
    m = re.search(r'^' + k + r':[ \t]*(.*)$', t, re.M)
    if not m: return None
    v = m.group(1).strip()
    q = re.match(r'(["\'])((?:\\.|(?!\1).)*)\1', v)
    return q.group(2) if q else re.sub(r'\s+#.*$', '', v).strip('"\'')
specs = {}
for f in sorted(os.listdir(os.path.join(item, 'specs'))):
    if not f.endswith('.md'): continue
    p = os.path.join(item, 'specs', f); t = open(p).read()
    sec = re.search(r'^## Files[ \t]*\n(.*?)(?=^## |\Z)', t, re.M | re.S)
    specs[fm(t, 'id')] = dict(path=p, text=t, status=fm(t, 'status'), lane=fm(t, 'lane'),
        commits=re.findall(r'[0-9a-f]{7,40}', fm(t, 'commits') or ''), reason=None,
        files=[m.strip() for m in re.findall(r'^\|\s*(?:CREATE|MODIFY|DELETE|TEST)\s*\|\s*`([^`]+)`', sec.group(1), re.M)] if sec else [])
lane_specs = {}
for sid, s in sorted(specs.items()): lane_specs.setdefault(s['lane'], []).append(sid)
readme = open(os.path.join(item, 'README.md')).read()
for m in re.finditer(r'^\|\s*([A-Z])\s*\|\s*(SPEC[^|]*)\|', readme, re.M): lane_specs[m.group(1)] = re.findall(r'SPEC-\d+', m.group(2))
out = {'item': slug, 'interrupted': [], 'failed': [], 'skippedLanes': [], 'deviations': 0}
changed = set()
def setstatus(sid, st, reason=None):
    s = specs[sid]
    if s['status'] != st or reason: s['status'] = st; s['reason'] = reason; changed.add(sid)
for r in ret.get('lanes', []):
    for sid in r.get('completed', []):
        s = specs[sid]; add = [x for x in r.get('commits', {}).get(sid, []) if not any(x.startswith(h) or h.startswith(x) for h in s['commits'])]
        if add: s['commits'] += add; changed.add(sid)
        if s['status'] == 'approved' and s['commits']: setstatus(sid, 'committed')
    x = r.get('failedAt')
    if x and (r.get('failure') or '').startswith('worker returned no result'):
        out['interrupted'].append(r['lane'])  # dead agent: leave state for the next reconcile
    elif x:
        setstatus(x, 'blocked', (r.get('failure') or 'worker failed').replace('\n', ' '))
        st = subprocess.run(['git', 'status', '--porcelain', '--'] + specs[x]['files'], capture_output=True, text=True).stdout
        out['failed'].append({'spec': x, 'reason': specs[x]['reason'], 'dirty': [l[3:] for l in st.splitlines() if l.strip()]})
        mates = lane_specs[r['lane']]
        for m in mates[mates.index(x) + 1:]:
            if specs[m]['status'] == 'approved': setstatus(m, 'skipped')
    devs = r.get('deviations', [])
    if devs:
        os.makedirs(os.path.join(item, 'reports'), exist_ok=True)
        with open(os.path.join(item, 'reports', 'deviations.md'), 'a') as f:
            f.write(f"\n## {datetime.date.today()} · lane {r['lane']}\n\n| Spec | What | Why | Paths |\n|------|------|-----|-------|\n")
            for d in devs: f.write(f"| {d['specId']} | {d['what']} | {d['why']} | {', '.join(d.get('paths', []))} |\n")
        out['deviations'] += len(devs)
for sk in ret.get('skipped', []):
    out['skippedLanes'].append(sk)
    for sid in lane_specs.get(sk['lane'], []):
        if specs[sid]['status'] == 'approved': setstatus(sid, 'skipped')
for sid in changed:
    s = specs[sid]; t = s['text']
    t = re.sub(r'^status:.*$', 'status: ' + s['status'], t, count=1, flags=re.M)
    t = re.sub(r'^commits:.*$', 'commits: [' + ', '.join(s['commits']) + ']', t, count=1, flags=re.M)
    if s['reason'] is not None: t = re.sub(r'^blocked_reason:.*$', 'blocked_reason: ' + json.dumps(s['reason']), t, count=1, flags=re.M)
    open(s['path'], 'w').write(t)
def sync_readme(item, status):  # README "## Specifications" Status column <- frontmatter status
    p = os.path.join(item, 'README.md'); t = open(p).read(); moved = []
    sec = re.search(r'^## Specifications[ \t]*\n(.*?)(?=^## |\Z)', t, re.M | re.S)
    if not sec: return moved
    def row(m):
        cells = m.group(0).split('|'); ids = re.findall(r'SPEC-\d+', cells[1])
        if len(cells) < 4 or not ids or ids[0] not in status or cells[-2].strip() == status[ids[0]]: return m.group(0)
        moved.append(f'{ids[0]}: {cells[-2].strip()} -> {status[ids[0]]}'); cells[-2] = f' {status[ids[0]]} '; return '|'.join(cells)
    body = re.sub(r'^\|.*\|[ \t]*$', row, sec.group(1), flags=re.M)
    if moved: open(p, 'w').write(t[:sec.start(1)] + body + t[sec.end(1):])
    return moved
out['readme'] = sync_readme(item, {k: v['status'] for k, v in specs.items()})
by = lambda st: sorted(k for k, v in specs.items() if v['status'] == st)
out.update(written=sorted(changed), done=by('done'), committed=by('committed'), skipped=by('skipped'), awaiting=by('draft'),
           blocked=[{'spec': k, 'reason': fm(open(specs[k]['path']).read(), 'blocked_reason')} for k in by('blocked')])
print(json.dumps(out, indent=1))
PYEOF
```

- Completed specs get their new commit shas. `approved` becomes `committed` (`done` needs converge, §8).
- `failedAt` makes that spec `blocked`, with the failure as `blocked_reason`. Its uncommitted later lane-mates become `skipped`. A dead worker (no result) only goes in `interrupted`: the next run's reconcile picks up whatever it committed.
- Lanes the workflow skipped: their `approved` specs become `skipped`. `committed` ones stay `committed`.
- `deviations` are appended to `reports/deviations.md` as a dated table per lane.
- The work-item README's **Specifications** table gets its Status column rewritten from frontmatter (`readme` in the output lists each row it moved). §8 does the same after converge, so the README matches the frontmatter in the bookkeeping commit. Frontmatter stays the source; the column is a copy.

## §7 Bookkeeping, summary, single-spec mode

**Bookkeeping commit** after every run that changed item files (never in `--dry-run`). It carries no `Spec:` trailer, so trailer reconcile never mistakes it for spec work:

```bash
git add -- "{workDir}/items/{item}"
git diff --cached --quiet -- "{workDir}/items/{item}" || git commit --only -m "chore(specs): {item} status" -- "{workDir}/items/{item}"
```

**Summary** for the user, from the results script output:

```markdown
## speclane:execute: {item}

| Done | Committed (awaiting converge) | Blocked | Skipped | Awaiting approval |
|------|-------------------------------|---------|---------|-------------------|
| SPEC-001 | SPEC-004 | SPEC-002 | SPEC-003 | SPEC-005 |

**Blocked**
- SPEC-002: {blocked_reason}
  Uncommitted edits it left: {dirty paths}. Keep them by committing, or discard them:
  `git restore --source=HEAD --staged --worktree -- {dirty paths}`

**Skipped lanes**: {lane}: {reason}
**Deviations**: {N} recorded in reports/deviations.md
**Interrupted lanes**: {lane} (worker died; re-run to reconcile and continue)

**Needs your decision** (converge `untestable`: not a pass, so the spec stays `committed`)
- SPEC-004: untestable (1/4)
  - {each untestable criterion's text}
  Either check it yourself, then set `status: done` and `converge: manual` and note the evidence on its `UNTESTABLE` checklist line; or rewrite the criterion so it can be checked and re-run (the next run grades it again).

**To unblock** a spec: fix the cause, then set `status: approved` and `rounds: 0` and clear `blocked_reason` in its frontmatter.
**To resume**: `/speclane:execute {item}` (every run reconciles and continues).
```

Omit empty rows and sections.

**Single-spec mode** (`/speclane:execute {item} SPEC-NNN`): run §1–§3 as usual (the state script with `--write`; stop on exit `1` or `2` as usual). Then **always** run this check, even if you expect it to refuse: it is the only thing that decides whether the spec may run, and it builds the one-spec lane. It refuses unless every `depends_on` spec **and every earlier lane-mate** is `done`:

```bash
python3 -I - "{workDir}/items/{item}" SPEC-NNN "${CLAUDE_SKILL_DIR}" <<'PYEOF'
import json, os, re, subprocess, sys
item, target = sys.argv[1].rstrip('/'), sys.argv[2]
skill_dir = sys.argv[3] if len(sys.argv) > 3 else ''
root = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
cfg_path = os.path.join(root, '.claude', 'speclane.json')
try: cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
except ValueError as e: print(json.dumps({'refused': f'.claude/speclane.json is not valid JSON: {e}'})); sys.exit(1)
settings = dict(workDir=cfg.get('workDir', '.claude/work'), contractFile=os.path.join(skill_dir, 'SKILL.md') if skill_dir else '',
                commands=cfg.get('commands', {}), derivedFiles=cfg.get('derivedFiles', []),
                contextFiles=cfg.get('contextFiles', []), mcpTools=cfg.get('mcpTools', []))
def fm(t, k):  # frontmatter value; a trailing '# comment' is dropped unless the value is quoted
    m = re.search(r'^' + k + r':[ \t]*(.*)$', t, re.M)
    if not m: return None
    v = m.group(1).strip()
    q = re.match(r'(["\'])((?:\\.|(?!\1).)*)\1', v)
    return q.group(2) if q else re.sub(r'\s+#.*$', '', v).strip('"\'')
specs = {}
for f in sorted(os.listdir(os.path.join(item, 'specs'))):
    if f.endswith('.md'):
        p = os.path.join(item, 'specs', f); t = open(p).read(); sec = re.search(r'^## Files[ \t]*\n(.*?)(?=^## |\Z)', t, re.M | re.S)
        specs[fm(t, 'id')] = dict(path=p, status=fm(t, 'status'), lane=fm(t, 'lane'), deps=re.findall(r'SPEC-\d+', fm(t, 'depends_on') or ''),
            commits=re.findall(r'[0-9a-f]{7,40}', fm(t, 'commits') or ''), rounds=int(fm(t, 'rounds') or 0),
            files=[m.strip() for m in re.findall(r'^\|\s*(?:CREATE|MODIFY|DELETE|TEST)\s*\|\s*`([^`]+)`', sec.group(1), re.M)] if sec else [])
lanes = {m.group(1): dict(specs=re.findall(r'SPEC-\d+', m.group(2)), worker=m.group(3))
         for m in re.finditer(r'^\|\s*([A-Z])\s*\|\s*(SPEC[^|]*)\|\s*(\w+)\s*\|', open(os.path.join(item, 'README.md')).read(), re.M)}
if target not in specs: print(json.dumps({'refused': f'{target} not found'})); sys.exit(1)
s = specs[target]; mates = lanes[s['lane']]['specs']
blocking = [d for d in dict.fromkeys(s['deps'] + mates[:mates.index(target)]) if specs[d]['status'] != 'done']
if blocking: print(json.dumps({'refused': f'{target} needs these done first: ' + ', '.join(f'{d} ({specs[d]["status"]})' for d in blocking)})); sys.exit(1)
if s['status'] not in ('approved', 'committed'): print(json.dumps({'refused': f'{target} is {s["status"]}; only approved or committed specs run'})); sys.exit(1)
print(json.dumps({'workItem': os.path.basename(item), 'settings': settings, 'lanes': [dict(lane=s['lane'], worker=lanes[s['lane']]['worker'], dependsOn=[],
    specs=[dict(specId=target, specPath=s['path'], files=s['files'], status=s['status'], commits=s['commits'], rounds=s['rounds'])])]}))
PYEOF
```

On exit `1`, print `refused`. If the state script's output listed `written` specs, make the §7 bookkeeping commit (reconcile only moves state forward, so it's safe to keep); then stop. Otherwise pass the printed JSON to `Workflow({ name: 'speclane:execute-lanes', args: … })`, then run §6, §8 and §7 as usual. Single-spec mode never runs `/speclane:finalize`.

## §8 Write converge results

The workflow converges each lane with the independent `speclane:converge` agent (pinned `claude-opus-4-6`). It runs fix rounds itself and stops a lane at 3 failed rounds. Its return carries, per lane:
- `converge`: `{ specId: { result, rounds, criteria, outOfScope } }`
- `blocked`: `[{ specId, reason }]`
- `notRun`: specIds

Run this **after §6**, on the same saved return, and **before** the §7 bookkeeping commit:

```bash
python3 -I - "{workDir}/items/{item}" "{returnFile}" <<'PYEOF'
import json, os, re, sys, datetime
item, ret = sys.argv[1].rstrip('/'), json.load(open(sys.argv[2]))
def fm(t, k):  # frontmatter value; a trailing '# comment' is dropped unless the value is quoted
    m = re.search(r'^' + k + r':[ \t]*(.*)$', t, re.M)
    if not m: return None
    v = m.group(1).strip()
    q = re.match(r'(["\'])((?:\\.|(?!\1).)*)\1', v)
    return q.group(2) if q else re.sub(r'\s+#.*$', '', v).strip('"\'')
specs = {}
for f in sorted(os.listdir(os.path.join(item, 'specs'))):
    if f.endswith('.md'):
        p = os.path.join(item, 'specs', f); t = open(p).read()
        specs[fm(t, 'id')] = dict(path=p, text=t, status=fm(t, 'status'), lane=fm(t, 'lane'))
lanes = {m.group(1): re.findall(r'SPEC-\d+', m.group(2))
         for m in re.finditer(r'^\|\s*([A-Z])\s*\|\s*(SPEC[^|]*)\|', open(os.path.join(item, 'README.md')).read(), re.M)}
def setf(sid, key, val):
    s = specs[sid]; s['text'] = re.sub(r'^' + key + r':.*$', f'{key}: {val}', s['text'], count=1, flags=re.M)
    if key == 'status': s['status'] = val
blocked = {sid for sid, s in specs.items() if s['status'] == 'blocked'}
for r in ret.get('lanes', []):
    for b in r.get('blocked', []): blocked.add(b['specId'])
out = {'done': [], 'failed': [], 'untestable': [], 'blocked': [], 'skipped': [], 'heldPass': []}
today = datetime.date.today()
for r in ret.get('lanes', []):
    for sid, c in r.get('converge', {}).items():
        setf(sid, 'converge', c['result']); setf(sid, 'rounds', c['rounds'])
        lines = [f'<!-- converge {today}, round {c["rounds"]} -->']
        for cr in c.get('criteria', []):
            tag = {'pass': '- [x] PASS', 'fail': '- [ ] FAIL', 'untestable': '- [ ] UNTESTABLE'}[cr['status']]
            lines.append(f'{tag}: {cr["text"]} ({cr["ref"]})' + (f' (introduced by {cr["introducedBy"]})' if cr.get('introducedBy') else ''))
        lines += [f'- [ ] OUT OF SCOPE: {p}' for p in c.get('outOfScope', [])]
        s = specs[sid]
        if '### Converge Checklist' not in s['text']: s['text'] = s['text'].rstrip('\n') + '\n\n### Converge Checklist\n'
        s['text'] = re.sub(r'(### Converge Checklist[ \t]*\n)(?:.*\n?)*\Z', lambda m: m.group(1) + '\n'.join(lines) + '\n', s['text'], count=1)
        mates = lanes[s['lane']]
        held = any(m in blocked for m in mates[:mates.index(sid)])
        if c['result'] == 'pass' and s['status'] == 'committed' and sid not in blocked:
            if held: out['heldPass'].append(sid)       # passed, but behind a blocked spec: stays committed
            else: setf(sid, 'status', 'done'); setf(sid, 'blocked_reason', 'null'); out['done'].append(sid)
        elif c['result'].startswith('untestable'):     # not a pass: stays committed until you decide
            out['untestable'].append({'spec': sid, 'result': c['result'],
                                      'criteria': [cr['text'] for cr in c.get('criteria', []) if cr['status'] == 'untestable']})
        elif c['result'] != 'pass': out['failed'].append(sid)
    for b in r.get('blocked', []):
        setf(b['specId'], 'status', 'blocked'); setf(b['specId'], 'blocked_reason', json.dumps(b['reason'])); out['blocked'].append(b['specId'])
    for sid in r.get('notRun', []):
        if specs[sid]['status'] == 'approved': setf(sid, 'status', 'skipped'); setf(sid, 'blocked_reason', 'null'); out['skipped'].append(sid)
for s in specs.values():
    if s['text'] != open(s['path']).read(): open(s['path'], 'w').write(s['text'])
def sync_readme(item, status):  # README "## Specifications" Status column <- frontmatter status
    p = os.path.join(item, 'README.md'); t = open(p).read(); moved = []
    sec = re.search(r'^## Specifications[ \t]*\n(.*?)(?=^## |\Z)', t, re.M | re.S)
    if not sec: return moved
    def row(m):
        cells = m.group(0).split('|'); ids = re.findall(r'SPEC-\d+', cells[1])
        if len(cells) < 4 or not ids or ids[0] not in status or cells[-2].strip() == status[ids[0]]: return m.group(0)
        moved.append(f'{ids[0]}: {cells[-2].strip()} -> {status[ids[0]]}'); cells[-2] = f' {status[ids[0]]} '; return '|'.join(cells)
    body = re.sub(r'^\|.*\|[ \t]*$', row, sec.group(1), flags=re.M)
    if moved: open(p, 'w').write(t[:sec.start(1)] + body + t[sec.end(1):])
    return moved
out['readme'] = sync_readme(item, {k: v['status'] for k, v in specs.items()})
print(json.dumps(out, indent=1))
PYEOF
```

- **`pass`** on a `committed` spec makes it `done`, with a checklist of `file:line` evidence. Exception: if an earlier lane-mate is blocked, it stays `committed` (`heldPass`), so nothing is marked done behind a blocked spec.
- **`untestable (n/m)`**: no criterion failed, but the grader couldn't decide n of m. That is **not** a pass: the spec stays `committed` with `converge: untestable (n/m)`, the workflow ran no fix round, and lanes that depend on its lane were skipped. List it in the §7 summary under **Needs your decision**. Never mark it `done` yourself.
- **`fail`** without hitting the cap only happens if the run was cut short. The spec stays `committed` with `converge: fail (n/m)`, and the next run converges it first.
- **`blocked`**: status `blocked`, plus `blocked_reason` and `rounds`. Add these to the §7 summary with the unblock procedure.
- **`notRun`**: approved specs the lane never reached become `skipped`. They return to `approved` automatically once they're no longer held (§2).

Then make the §7 bookkeeping commit and print the summary.
