"""Scratch-repo tests for the Python scripts embedded in the speclane skills.

Ports the v5 bootstrap checks (SPEC-002 lane check, SPEC-005 state script, SPEC-006 §8 converge
script, SPEC-007 finalize gate, SPEC-011 results script / bookkeeping / single-spec mode) and the
post-merge follow-ups (untestable, README status sync), plus speclane's config handling.

Every script is extracted from the SKILL.md it ships in, so the tests run exactly what the skill runs.
Run: python3 -m unittest discover -s tests/scripts -v   (or tests/run.sh)
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def heredocs(skill, tag='PYEOF'):
    t = open(os.path.join(ROOT, 'skills', skill, 'SKILL.md')).read()
    return re.findall(r"<<'" + tag + r"'\n(.*?)\n" + tag, t, re.S)


EXEC = heredocs('execute')
STATE, RESULTS, SINGLE, CONVERGE = EXEC
(GATE,) = heredocs('finalize')
(LANECHECK,) = heredocs('init', 'EOF')
EXEC_MD = open(os.path.join(ROOT, 'skills', 'execute', 'SKILL.md')).read()
BOOKKEEPING = re.search(r'```bash\n(git add -- "\{workDir\}/items/\{item\}"\n.*?)\n```', EXEC_MD, re.S).group(1)


def sh(cwd, *a, check=True):
    r = subprocess.run(list(a), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise AssertionError(f'{a} failed: {r.stderr}')
    return r.stdout


SPEC = """---
id: {id}
title: {id} title
priority: P0
lane: {lane}
depends_on: [{deps}]
status: {status}
commits: [{commits}]
converge: {converge}
rounds: {rounds}
blocked_reason: {reason}
agents:
  review: {review}
---

## Context

ctx

## Files

| Action | Path | Purpose |
|--------|------|---------|
{files}

## Acceptance
- [ ] thing
{extra}"""


class Repo:
    """A scratch git repo with one work item. lanes: [(name, [ids], worker, [dep lanes])]."""

    def __init__(self, tc, specs, lanes, slug='fx', work_dir='.claude/work', cfg=None, issue=None):
        self.dir = tempfile.mkdtemp(prefix='speclane-test-')
        tc.addCleanup(shutil.rmtree, self.dir, True)
        self.slug, self.work_dir = slug, work_dir
        self.item = f'{work_dir}/items/{slug}'
        sh(self.dir, 'git', 'init', '-q')
        sh(self.dir, 'git', 'config', 'user.email', 't@t')
        sh(self.dir, 'git', 'config', 'user.name', 't')
        sh(self.dir, 'git', 'config', 'commit.gpgsign', 'false')
        os.makedirs(self.p(self.item, 'specs'))
        if cfg is not None:
            os.makedirs(self.p('.claude'), exist_ok=True)
            open(self.p('.claude', 'speclane.json'), 'w').write(cfg if isinstance(cfg, str) else json.dumps(cfg))
        rows = '\n'.join(f'| {n} | {", ".join(ids)} | {w} | {", ".join(d) or "—"} |' for n, ids, w, d in lanes)
        srows = '\n'.join(f'| [{s["id"]}](specs/{s["id"]}-x.md) | t | {s["lane"]} | — | {s.get("readme_status", s.get("status", "approved"))} |' for s in specs)
        open(self.p(self.item, 'README.md'), 'w').write(
            f'# FX\n\n> **Issue**: {issue or "none filed"}\n\n## Lanes\n\n| Lane | Specs (in order) | Worker | Depends on lanes |\n'
            f'|------|------------------|--------|------------------|\n{rows}\n\n## Specifications\n\n'
            f'| ID | Title | Lane | Depends on | Status |\n|----|-------|------|------------|--------|\n{srows}\n\n---\n\n## Reports\n')
        for s in specs:
            self.write_spec(s)
        sh(self.dir, 'git', 'add', '-A')
        sh(self.dir, 'git', 'commit', '-qm', 'init')

    def write_spec(self, s):
        files = s.get('files', [f'out/{s["id"]}.txt'])
        text = SPEC.format(id=s['id'], lane=s['lane'], deps=', '.join(s.get('deps', [])), status=s.get('status', 'approved'),
                           commits=', '.join(s.get('commits', [])), converge=s.get('converge', 'null'), rounds=s.get('rounds', 0),
                           reason=s.get('reason', 'null'), review=s.get('review', 'general-purpose'),
                           files='\n'.join(f'| CREATE | `{f}` | x |' for f in files), extra=s.get('extra', ''))
        if s.get('v4'):
            text = re.sub(r'^(status|lane):.*\n', '', text, flags=re.M)
        open(self.p(self.item, 'specs', f'{s["id"]}-x.md'), 'w').write(text)

    def p(self, *a):
        return os.path.join(self.dir, *a)

    def spec_text(self, sid):
        return open(self.p(self.item, 'specs', f'{sid}-x.md')).read()

    def fm(self, sid, k):
        m = re.search(r'^' + k + r':[ \t]*(.*)$', self.spec_text(sid), re.M)
        return m.group(1).strip() if m else None

    def set_fm(self, sid, k, v):
        p = self.p(self.item, 'specs', f'{sid}-x.md')
        text = open(p).read()
        open(p, 'w').write(re.sub(r'^' + k + r':.*$', f'{k}: {v}', text, count=1, flags=re.M))

    def commit_spec(self, sid, path=None, content=None, trailer=True, body=None):
        path = path or f'out/{sid}.txt'
        os.makedirs(os.path.dirname(self.p(path)) or self.dir, exist_ok=True)
        open(self.p(path), 'a').write(content or sid + '\n')
        sh(self.dir, 'git', 'add', '--', path)
        msg = body or f'feat: {sid}\n\nwork\n\n' + (f'Spec: {self.slug}/{sid}\n' if trailer else '')
        sh(self.dir, 'git', 'commit', '-qm', msg)
        return sh(self.dir, 'git', 'rev-parse', 'HEAD').strip()

    def commit_all(self, msg='chore: update'):
        sh(self.dir, 'git', 'add', '-A')
        sh(self.dir, 'git', 'commit', '-qm', msg)

    def run(self, script, *args):
        r = subprocess.run(['python3', '-I', '-', *args], input=script, cwd=self.dir, capture_output=True, text=True)
        try:
            out = json.loads(r.stdout)
        except ValueError:
            raise AssertionError(f'non-JSON output (exit {r.returncode}): {r.stdout}\n{r.stderr}')
        return r.returncode, out

    def head(self):
        return sh(self.dir, 'git', 'rev-parse', 'HEAD').strip()

    def digest(self):
        h = hashlib.md5()
        for root, _, fs in sorted(os.walk(self.p(self.item))):
            for f in sorted(fs):
                h.update(open(os.path.join(root, f), 'rb').read())
        return h.hexdigest()


def S(id, lane, **kw):
    return dict(id=id, lane=lane, **kw)


# ======================================================================= SPEC-002: init lane check
class LaneCheck(unittest.TestCase):
    def check(self, specs, lanes):
        r = Repo(self, specs, lanes)
        return subprocess.run(['python3', '-I', '-', r.p(r.item)], input=LANECHECK, capture_output=True, text=True).stdout.strip()

    def test_acyclic_ok(self):
        out = self.check([S('SPEC-001', 'A'), S('SPEC-002', 'A', deps=['SPEC-001']), S('SPEC-003', 'B', deps=['SPEC-002'])],
                         [('A', ['SPEC-001', 'SPEC-002'], 'default', []), ('B', ['SPEC-003'], 'default', ['A'])])
        self.assertEqual(out, 'acyclic OK')

    def test_rule3_mid_lane(self):
        out = self.check([S('SPEC-001', 'A'), S('SPEC-002', 'A'), S('SPEC-003', 'B', deps=['SPEC-001'])],
                         [('A', ['SPEC-001', 'SPEC-002'], 'default', []), ('B', ['SPEC-003'], 'default', ['A'])])
        self.assertIn('rule 3: SPEC-003 depends on mid-lane SPEC-001', out)
        self.assertTrue(out.endswith('FAIL'))

    def test_cycle(self):
        out = self.check([S('SPEC-001', 'C', deps=['SPEC-002']), S('SPEC-002', 'D', deps=['SPEC-001'])],
                         [('C', ['SPEC-001'], 'default', ['D']), ('D', ['SPEC-002'], 'default', ['C'])])
        self.assertTrue(out.endswith('cycle FAIL'), out)


# ======================================================================= SPEC-005: state script (§1–§4)
TWO_LANES = [('A', ['SPEC-001', 'SPEC-002', 'SPEC-003'], 'default', []), ('B', ['SPEC-004'], 'sonnet', [])]


class StateScript(unittest.TestCase):
    def test_preflight_v4_spec(self):
        r = Repo(self, [S('SPEC-001', 'A', v4=True)], [('A', ['SPEC-001'], 'default', [])])
        h = r.head()
        code, out = r.run(STATE, r.item, '/skill')
        self.assertEqual(code, 1)
        self.assertIn('SPEC-001: not a v5 spec (no status:/lane:). Upgrade it first: speclane docs/upgrading-v4.md', out['errors'])
        self.assertEqual(r.head(), h)

    def test_preflight_cycle_and_rule3(self):
        specs = [S('SPEC-001', 'A'), S('SPEC-002', 'A'), S('SPEC-003', 'C', deps=['SPEC-001', 'SPEC-004']), S('SPEC-004', 'D', deps=['SPEC-003'])]
        r = Repo(self, specs, [('A', ['SPEC-001', 'SPEC-002'], 'default', []), ('C', ['SPEC-003'], 'default', ['A', 'D']), ('D', ['SPEC-004'], 'default', ['C'])])
        code, out = r.run(STATE, r.item, '/skill')
        self.assertEqual(code, 1)
        errs = '\n'.join(out['errors'])
        self.assertIn('rule 3: SPEC-003 (lane C) depends on SPEC-001, which is mid-lane in A', errs)
        self.assertIn('rule 4: lane cycle C -> D -> C', errs)

    def test_preflight_unknown_status(self):
        r = Repo(self, [S('SPEC-001', 'A', status='wip')], [('A', ['SPEC-001'], 'opus', [])])
        code, out = r.run(STATE, r.item, '/skill')
        # spec-level errors stop pre-flight before the lane rules run (as in v5)
        self.assertEqual((code, out['errors']), (1, ["SPEC-001: unknown status 'wip'"]))

    def test_preflight_bad_worker(self):
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'opus', [])])
        code, out = r.run(STATE, r.item, '/skill')
        self.assertEqual((code, out['errors']), (1, ["lane A: worker must be default or sonnet, got 'opus'"]))

    def test_reconcile_approved_with_trailer_becomes_committed_never_done(self):
        r = Repo(self, [S('SPEC-001', 'A'), S('SPEC-002', 'A', deps=['SPEC-001'])], [('A', ['SPEC-001', 'SPEC-002'], 'default', [])])
        sha = r.commit_spec('SPEC-001')
        code, out = r.run(STATE, r.item, '/skill', '--write')
        self.assertEqual(code, 0)
        self.assertEqual(out['changes'], ['SPEC-001: commits +1, approved -> committed'])
        self.assertEqual(r.fm('SPEC-001', 'status'), 'committed')
        self.assertEqual(r.fm('SPEC-001', 'commits'), f'[{sha}]')
        self.assertEqual(out['input']['lanes'][0]['specs'][0]['status'], 'committed')
        self.assertEqual(out['order'], ['A: SPEC-001 -> SPEC-002'])

    def test_write_twice_is_forward_only_and_blocked_stays_blocked(self):
        specs = [S('SPEC-001', 'A', status='blocked', reason='"x"'), S('SPEC-002', 'A'), S('SPEC-003', 'A'), S('SPEC-004', 'B')]
        r = Repo(self, specs, TWO_LANES)
        r.commit_spec('SPEC-001')
        r.commit_spec('SPEC-004')
        _, o1 = r.run(STATE, r.item, '/skill', '--write')
        self.assertEqual(r.fm('SPEC-001', 'status'), 'blocked')
        self.assertIn('SPEC-001: commits +1', o1['changes'])
        r.commit_all()
        before = r.digest()
        _, o2 = r.run(STATE, r.item, '/skill', '--write')
        self.assertEqual(o2['changes'], [])
        self.assertEqual(r.digest(), before)

    def test_guard_dirty_files_exit2_writes_nothing(self):
        r = Repo(self, [S('SPEC-001', 'A'), S('SPEC-002', 'A')], [('A', ['SPEC-001', 'SPEC-002'], 'default', [])])
        r.commit_spec('SPEC-001')
        os.makedirs(r.p('out'), exist_ok=True)
        open(r.p('out/SPEC-002.txt'), 'w').write('half')
        before = r.digest()
        code, out = r.run(STATE, r.item, '/skill', '--write')
        self.assertEqual(code, 2)
        self.assertEqual(out['dirty'], [{'spec': 'SPEC-002', 'paths': ['out/SPEC-002.txt']}])
        self.assertNotIn('written', out)
        self.assertEqual(r.digest(), before)
        self.assertIn('git restore --source=HEAD --staged --worktree -- <paths>', EXEC_MD)
        self.assertIn('Never set work aside with the stash stack', EXEC_MD)

    def test_dry_run_changes_nothing(self):
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'default', [])])
        r.commit_spec('SPEC-001')
        h, d = r.head(), r.digest()
        code, out = r.run(STATE, r.item, '/skill')
        self.assertEqual(code, 0)
        self.assertEqual((r.head(), r.digest()), (h, d))
        self.assertEqual(out['changes'], ['SPEC-001: commits +1, approved -> committed'])

    def test_held_behind_blocked_then_unblock(self):
        specs = [S('SPEC-001', 'A', status='blocked', reason='"tests"'), S('SPEC-002', 'A', status='committed'),
                 S('SPEC-003', 'A', status='skipped'), S('SPEC-004', 'B', status='draft')]
        r = Repo(self, specs, TWO_LANES)
        r.commit_spec('SPEC-001')
        sha2 = r.commit_spec('SPEC-002')
        r.set_fm('SPEC-002', 'commits', f'[{sha2}]')
        r.commit_all()
        code, out = r.run(STATE, r.item, '/skill', '--write')
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out['held']), ['SPEC-002', 'SPEC-003'])
        self.assertEqual(out['awaiting'], ['SPEC-004'])
        self.assertEqual(out['input']['lanes'], [])
        r.commit_all()
        # unblock: approved, rounds 0, reason cleared
        r.set_fm('SPEC-001', 'status', 'approved'); r.set_fm('SPEC-001', 'blocked_reason', 'null')
        r.commit_all()
        _, out = r.run(STATE, r.item, '/skill', '--write')
        self.assertIn('SPEC-001: has commits, approved -> committed', out['changes'])
        self.assertIn('SPEC-003: skipped -> approved (no longer held)', out['changes'])
        lane = out['input']['lanes'][0]
        self.assertEqual([(s['specId'], s['status']) for s in lane['specs']],
                         [('SPEC-001', 'committed'), ('SPEC-002', 'committed'), ('SPEC-003', 'approved')])

    def test_decoy_spec_line_outside_trailer_is_ignored(self):
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'default', [])])
        r.commit_spec('SPEC-001', body='docs: mention\n\nSpec: fx/SPEC-001 is mentioned here\n\nmore text after it\n')
        r.commit_spec('SPEC-001', body='feat: other item\n\nx\n\nSpec: fx-other/SPEC-001\n')
        _, out = r.run(STATE, r.item, '/skill')
        self.assertEqual(out['changes'], [])

    def test_settings_embedded_from_config(self):
        cfg = {'workDir': 'docs/work', 'commands': {'test': 'pnpm test {files}', 'codegen': {'run': 'gen', 'when': 'schema'}},
               'derivedFiles': ['src/gen/**'], 'contextFiles': ['AGENTS.md'], 'mcpTools': ['mcp__x__y'], 'highRisk': ['src/core/']}
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'default', [])], work_dir='docs/work', cfg=cfg)
        code, out = r.run(STATE, r.item, '/plug/skills/execute')
        self.assertEqual(code, 0)
        st = out['input']['settings']
        self.assertEqual(st, {'workDir': 'docs/work', 'contractFile': '/plug/skills/execute/SKILL.md', 'commands': cfg['commands'],
                              'derivedFiles': ['src/gen/**'], 'contextFiles': ['AGENTS.md'], 'mcpTools': ['mcp__x__y']})
        self.assertEqual(out['input']['lanes'][0]['specs'][0]['specPath'], 'docs/work/items/fx/specs/SPEC-001-x.md')

    def test_settings_defaults_without_config(self):
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'default', [])])
        _, out = r.run(STATE, r.item, '/s', '--write')
        self.assertEqual(out['input']['settings'], {'workDir': '.claude/work', 'contractFile': '/s/SKILL.md', 'commands': {},
                                                    'derivedFiles': [], 'contextFiles': [], 'mcpTools': []})

    def test_invalid_config_is_a_preflight_error(self):
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'default', [])], cfg='{ nope')
        code, out = r.run(STATE, r.item, '/s')
        self.assertEqual(code, 1)
        self.assertTrue(out['errors'][0].startswith('.claude/speclane.json is not valid JSON'))

    def test_missing_item_folder(self):
        r = Repo(self, [S('SPEC-001', 'A')], [('A', ['SPEC-001'], 'default', [])])
        code, out = r.run(STATE, '.claude/work/items/nope', '/s')
        self.assertEqual(code, 1)
        self.assertIn('no specs/ folder', out['errors'][0])

    def test_hold_is_transitive(self):
        # SPEC-001 blocked; SPEC-002 (lane A, after it) skipped; SPEC-003 (lane B) depends on SPEC-002 and was
        # skipped with its lane; SPEC-004 (lane C) depends on SPEC-003 and is still approved.
        specs = [S('SPEC-001', 'A', status='blocked', reason='"x"'), S('SPEC-002', 'A', status='skipped'),
                 S('SPEC-003', 'B', deps=['SPEC-002'], status='skipped'), S('SPEC-004', 'C', deps=['SPEC-003']), S('SPEC-005', 'D')]
        lanes = [('A', ['SPEC-001', 'SPEC-002'], 'default', []), ('B', ['SPEC-003'], 'default', ['A']),
                 ('C', ['SPEC-004'], 'default', ['B']), ('D', ['SPEC-005'], 'default', [])]
        r = Repo(self, specs, lanes)
        code, out = r.run(STATE, r.item, '/s', '--write')
        self.assertEqual(code, 0)
        self.assertEqual(out['changes'], [], 'a spec held through a skipped dependency must not flip to approved')
        self.assertEqual(sorted(out['held']), ['SPEC-002', 'SPEC-003', 'SPEC-004'])
        self.assertEqual([l['lane'] for l in out['input']['lanes']], ['D'])
        self.assertEqual(r.fm('SPEC-003', 'status'), 'skipped')

    def test_done_lane_dropped_from_dependsOn_and_wouldSkip(self):
        specs = [S('SPEC-001', 'A', status='done', converge='pass'), S('SPEC-002', 'B', deps=['SPEC-001']),
                 S('SPEC-003', 'C', status='blocked'), S('SPEC-004', 'D', deps=['SPEC-003'])]
        lanes = [('A', ['SPEC-001'], 'default', []), ('B', ['SPEC-002'], 'default', ['A']),
                 ('C', ['SPEC-003'], 'default', []), ('D', ['SPEC-004'], 'default', ['C'])]
        r = Repo(self, specs, lanes)
        _, out = r.run(STATE, r.item, '/s')
        ins = {l['lane']: l for l in out['input']['lanes']}
        self.assertEqual(ins['B']['dependsOn'], [])
        self.assertEqual(out['held'], ['SPEC-004'])
        self.assertNotIn('D', ins)


# ======================================================================= SPEC-011: results script (§6), bookkeeping, single-spec
class ResultsScript(unittest.TestCase):
    def setUp(self):
        specs = [S('SPEC-001', 'A', readme_status='approved'), S('SPEC-002', 'A', files=['src/two.txt']), S('SPEC-003', 'A'),
                 S('SPEC-004', 'B', status='draft'), S('SPEC-005', 'B')]
        self.r = Repo(self, specs, [('A', ['SPEC-001', 'SPEC-002', 'SPEC-003'], 'default', []), ('B', ['SPEC-004', 'SPEC-005'], 'default', ['A'])])

    def ret(self, obj):
        p = os.path.join(tempfile.mkdtemp(), 'ret.json')
        self.addCleanup(shutil.rmtree, os.path.dirname(p), True)
        json.dump(obj, open(p, 'w'))
        return p

    def test_completed_failed_deviations_skipped_lane(self):
        r = self.r
        sha = r.commit_spec('SPEC-001')
        os.makedirs(r.p('src'), exist_ok=True)
        open(r.p('src/two.txt'), 'w').write('partial')
        ret = {'lanes': [{'lane': 'A', 'completed': ['SPEC-001'], 'commits': {'SPEC-001': [sha]}, 'failedAt': 'SPEC-002',
                          'failure': 'tests failed:\n2 errors', 'deviations': [{'specId': 'SPEC-001', 'what': 'w', 'why': 'y', 'paths': ['p']}]}],
               'skipped': [{'lane': 'B', 'reason': 'dependency lane A did not finish'}]}
        code, out = r.run(RESULTS, r.item, self.ret(ret))
        self.assertEqual(code, 0)
        self.assertEqual(r.fm('SPEC-001', 'status'), 'committed')
        self.assertEqual(r.fm('SPEC-002', 'status'), 'blocked')
        self.assertEqual(r.fm('SPEC-002', 'blocked_reason'), '"tests failed: 2 errors"')
        self.assertEqual(r.fm('SPEC-003', 'status'), 'skipped')
        self.assertEqual(r.fm('SPEC-004', 'status'), 'draft')
        self.assertEqual(r.fm('SPEC-005', 'status'), 'skipped')
        self.assertEqual(out['failed'], [{'spec': 'SPEC-002', 'reason': 'tests failed: 2 errors', 'dirty': ['src/two.txt']}])
        dev = open(r.p(r.item, 'reports', 'deviations.md')).read()
        self.assertRegex(dev, r'## \d{4}-\d\d-\d\d · lane A\n\n\| Spec \| What \| Why \| Paths \|')
        self.assertIn('| SPEC-001 | w | y | p |', dev)
        self.assertEqual(out['deviations'], 1)
        readme = open(r.p(r.item, 'README.md')).read()
        self.assertRegex(readme, r'\[SPEC-002\][^\n]*\| blocked \|\n')
        self.assertRegex(readme, r'\[SPEC-004\][^\n]*\| draft \|\n')
        self.assertEqual(sorted(out['readme']), ['SPEC-001: approved -> committed', 'SPEC-002: approved -> blocked',
                                                 'SPEC-003: approved -> skipped', 'SPEC-005: approved -> skipped'])

    def test_dead_worker_is_interrupted_and_writes_nothing(self):
        r = self.r
        before = r.digest()
        ret = {'lanes': [{'lane': 'A', 'completed': [], 'commits': {}, 'failedAt': 'SPEC-001',
                          'failure': 'worker returned no result (agent died); re-run /speclane:execute to reconcile and resume', 'deviations': []}], 'skipped': []}
        _, out = r.run(RESULTS, r.item, self.ret(ret))
        self.assertEqual(out['interrupted'], ['A'])
        self.assertEqual(out['written'], [])
        self.assertEqual(r.digest(), before)

    def test_bookkeeping_commit_only_item_and_no_trailer(self):
        r = self.r
        os.makedirs(r.p('src'), exist_ok=True)
        open(r.p('src/dirty.txt'), 'w').write('x')
        sh(r.dir, 'git', 'add', 'src/dirty.txt')
        r.set_fm('SPEC-001', 'status', 'committed')
        cmd = BOOKKEEPING.replace('{workDir}', r.work_dir).replace('{item}', r.slug)
        sh(r.dir, 'zsh', '-c', cmd) if shutil.which('zsh') else sh(r.dir, 'bash', '-c', cmd)
        self.assertEqual(sh(r.dir, 'git', 'log', '-1', '--format=%s'), 'chore(specs): fx status\n')
        self.assertEqual(sh(r.dir, 'git', 'log', '-1', '--format=%(trailers:key=Spec,valueonly)').strip(), '')
        self.assertEqual(sh(r.dir, 'git', 'show', '--name-only', '--format=', 'HEAD').split(), [f'{r.item}/specs/SPEC-001-x.md'])
        self.assertIn('A  src/dirty.txt', sh(r.dir, 'git', 'status', '--porcelain'))
        h = r.head()
        sh(r.dir, 'bash', '-c', cmd)
        self.assertEqual(r.head(), h)


class SingleSpec(unittest.TestCase):
    def setUp(self):
        specs = [S('SPEC-001', 'A', status='committed'), S('SPEC-002', 'A', status='committed'), S('SPEC-003', 'A', deps=['SPEC-002']),
                 S('SPEC-004', 'B', deps=['SPEC-003'], status='draft'), S('SPEC-005', 'C')]
        self.r = Repo(self, specs, [('A', ['SPEC-001', 'SPEC-002', 'SPEC-003'], 'default', []), ('B', ['SPEC-004'], 'sonnet', ['A']),
                                    ('C', ['SPEC-005'], 'sonnet', [])], cfg={'commands': {'test': 't'}})

    def test_refuses_until_deps_and_mates_done(self):
        code, out = self.r.run(SINGLE, self.r.item, 'SPEC-003', '/s')
        self.assertEqual(code, 1)
        self.assertTrue(out['refused'].startswith('SPEC-003 needs these done first: SPEC-002 (committed)'), out)
        self.assertIn('SPEC-001 (committed)', out['refused'])
        self.assertEqual(out['refused'].count('SPEC-002'), 1, 'a dependency that is also an earlier lane-mate is listed once')

    def test_refuses_draft(self):
        r = self.r
        for s in ('SPEC-001', 'SPEC-002', 'SPEC-003'):
            r.set_fm(s, 'status', 'done')
        code, out = r.run(SINGLE, r.item, 'SPEC-004', '/s')
        self.assertEqual((code, out['refused']), (1, 'SPEC-004 is draft; only approved or committed specs run'))

    def test_builds_one_spec_sonnet_lane_with_settings(self):
        code, out = self.r.run(SINGLE, self.r.item, 'SPEC-005', '/plug/skills/execute')
        self.assertEqual(code, 0)
        self.assertEqual(out['settings']['contractFile'], '/plug/skills/execute/SKILL.md')
        self.assertEqual(out['settings']['commands'], {'test': 't'})
        lane = out['lanes'][0]
        self.assertEqual((lane['lane'], lane['worker'], lane['dependsOn'], [s['specId'] for s in lane['specs']]), ('C', 'sonnet', [], ['SPEC-005']))

    def test_unknown_spec(self):
        code, out = self.r.run(SINGLE, self.r.item, 'SPEC-099', '/s')
        self.assertEqual((code, out['refused']), (1, 'SPEC-099 not found'))


# ======================================================================= SPEC-006 §8: converge results script
class ConvergeScript(unittest.TestCase):
    def setUp(self):
        specs = [S('SPEC-001', 'A', status='committed'), S('SPEC-002', 'A', status='committed'), S('SPEC-003', 'A'),
                 S('SPEC-004', 'B', status='committed', reason='"old"', extra='\n### Converge Checklist\n- [ ] old line\n'),
                 S('SPEC-005', 'C', status='committed')]
        self.r = Repo(self, specs, [('A', ['SPEC-001', 'SPEC-002', 'SPEC-003'], 'default', []), ('B', ['SPEC-004'], 'default', []),
                                    ('C', ['SPEC-005'], 'default', [])])

    def ret(self):
        c = lambda st, t='crit': {'text': t, 'status': st, 'ref': 'f:1', 'introducedBy': None}
        return {'lanes': [
            {'lane': 'A', 'converge': {'SPEC-001': {'result': 'fail (1/1)', 'rounds': 3, 'criteria': [c('fail', 'never')], 'outOfScope': ['x.ts']},
                                       'SPEC-002': {'result': 'pass', 'rounds': 0, 'criteria': [c('pass')], 'outOfScope': []}},
             'blocked': [{'specId': 'SPEC-001', 'reason': 'converge failed 3 rounds: never'}], 'notRun': ['SPEC-003']},
            {'lane': 'B', 'converge': {'SPEC-004': {'result': 'pass', 'rounds': 1, 'criteria': [c('pass', 'ok')], 'outOfScope': []}}, 'blocked': [], 'notRun': []},
            {'lane': 'C', 'converge': {'SPEC-005': {'result': 'untestable (1/2)', 'rounds': 0, 'criteria': [c('pass'), c('untestable', 'needs device')], 'outOfScope': []}},
             'blocked': [], 'notRun': []}], 'skipped': []}

    def run_it(self):
        p = os.path.join(tempfile.mkdtemp(), 'ret.json')
        self.addCleanup(shutil.rmtree, os.path.dirname(p), True)
        json.dump(self.ret(), open(p, 'w'))
        return self.r.run(CONVERGE, self.r.item, p)

    def test_results(self):
        r = self.r
        code, out = self.run_it()
        self.assertEqual(code, 0)
        self.assertEqual((r.fm('SPEC-001', 'status'), r.fm('SPEC-001', 'rounds'), r.fm('SPEC-001', 'blocked_reason')),
                         ('blocked', '3', '"converge failed 3 rounds: never"'))
        t1 = r.spec_text('SPEC-001')
        self.assertIn('### Converge Checklist\n<!-- converge ', t1)
        self.assertIn('- [ ] FAIL: never (f:1)', t1)
        self.assertIn('- [ ] OUT OF SCOPE: x.ts', t1)
        self.assertEqual(r.fm('SPEC-002', 'status'), 'committed')  # pass behind a blocked lane-mate
        self.assertEqual(out['heldPass'], ['SPEC-002'])
        self.assertEqual(r.fm('SPEC-003', 'status'), 'skipped')
        self.assertEqual((r.fm('SPEC-004', 'status'), r.fm('SPEC-004', 'blocked_reason'), r.fm('SPEC-004', 'converge')), ('done', 'null', 'pass'))
        t4 = r.spec_text('SPEC-004')
        self.assertNotIn('old line', t4)
        self.assertEqual(t4.count('### Converge Checklist'), 1)
        self.assertEqual((r.fm('SPEC-005', 'status'), r.fm('SPEC-005', 'converge')), ('committed', 'untestable (1/2)'))
        self.assertEqual(out['untestable'], [{'spec': 'SPEC-005', 'result': 'untestable (1/2)', 'criteria': ['needs device']}])
        self.assertIn('- [ ] UNTESTABLE: needs device (f:1)', r.spec_text('SPEC-005'))
        self.assertIn('SPEC-004: committed -> done', out['readme'])

    def test_idempotent(self):
        self.run_it()
        d = self.r.digest()
        self.run_it()
        self.assertEqual(self.r.digest(), d)


# ======================================================================= SPEC-007: finalize gate
CFG = {'reviewers': {'default': 'code-quality', 'aliases': {'ux-specialist': 'ux-reviewer'}},
       'highRisk': ['src/core/', 'lib/features/*/domain/**', 'CLAUDE.md']}


class FinalizeGate(unittest.TestCase):
    def test_not_done_stops_with_reasons(self):
        specs = [S('SPEC-001', 'A', status='done', converge='pass'), S('SPEC-002', 'A', status='committed', converge='"untestable (1/2)"'),
                 S('SPEC-003', 'A', status='blocked', reason='"why"'), S('SPEC-004', 'B', status='skipped'), S('SPEC-005', 'B', status='draft'),
                 S('SPEC-006', 'B')]
        r = Repo(self, specs, [('A', ['SPEC-001', 'SPEC-002', 'SPEC-003'], 'default', []), ('B', ['SPEC-004', 'SPEC-005', 'SPEC-006'], 'default', [])])
        r.commit_spec('SPEC-001'); r.commit_spec('SPEC-002')
        code, out = r.run(GATE, r.item)
        self.assertEqual(code, 1)
        why = {n['spec']: n['reason'] for n in out['notDone']}
        self.assertEqual(why['SPEC-002'], 'committed, but converge is untestable (1/2) (needs pass or manual)')
        self.assertEqual(why['SPEC-003'], 'why')
        self.assertEqual(why['SPEC-004'], 'held behind a blocked dependency or lane-mate')
        self.assertEqual(why['SPEC-005'], 'awaiting approval')
        self.assertEqual(why['SPEC-006'], 'no `Spec: fx/SPEC-006` trailer commit')
        self.assertNotIn('SPEC-001', why)

    def test_all_done_groups_files_highrisk_aliases(self):
        specs = [S('SPEC-001', 'A', status='done', converge='pass', review='ux-specialist'),
                 S('SPEC-002', 'A', status='done', converge='manual', review='[ux-reviewer, security]'),
                 S('SPEC-003', 'A', status='done', converge='pass', review='')]
        r = Repo(self, specs, [('A', ['SPEC-001', 'SPEC-002', 'SPEC-003'], 'default', [])], cfg=CFG)
        r.commit_spec('SPEC-001', path='src/core/a.ts')
        r.commit_spec('SPEC-001', path='docs/gone.md')
        sh(r.dir, 'git', 'rm', '-q', 'docs/gone.md'); sh(r.dir, 'git', 'commit', '-qm', 'rm')
        r.commit_spec('SPEC-002', path='lib/features/pay/domain/x/y.dart')
        r.commit_spec('SPEC-002', path='lib/features/pay/ui/z.dart')
        r.commit_spec('SPEC-003', path='CLAUDE.md')
        r.commit_spec('SPEC-003', path='src/corex.ts')
        code, out = r.run(GATE, r.item)
        self.assertEqual(code, 0, out)
        g = {x['type']: x for x in out['groups']}
        self.assertEqual(sorted(g), ['code-quality', 'security', 'ux-reviewer'])
        self.assertEqual(g['ux-reviewer']['specIds'], ['SPEC-001', 'SPEC-002'])
        self.assertEqual(g['ux-reviewer']['files'], ['lib/features/pay/domain/x/y.dart', 'lib/features/pay/ui/z.dart', 'src/core/a.ts'])
        self.assertIn('=== SPEC-001 ===', g['ux-reviewer']['acceptance'])
        self.assertEqual(g['code-quality']['specIds'], ['SPEC-003'])
        self.assertEqual(out['highRisk'], ['CLAUDE.md', 'lib/features/pay/domain/x/y.dart', 'src/core/a.ts'])

    def test_defaults_without_config(self):
        r = Repo(self, [S('SPEC-001', 'A', status='done', converge='pass', review='')], [('A', ['SPEC-001'], 'default', [])])
        r.commit_spec('SPEC-001', path='src/core/a.ts')
        code, out = r.run(GATE, r.item)
        self.assertEqual(code, 0)
        self.assertEqual([x['type'] for x in out['groups']], ['general-purpose'])
        self.assertEqual(out['highRisk'], [])

    def test_invalid_config(self):
        r = Repo(self, [S('SPEC-001', 'A', status='done', converge='pass')], [('A', ['SPEC-001'], 'default', [])], cfg='[')
        r.commit_spec('SPEC-001')
        code, out = r.run(GATE, r.item)
        self.assertEqual(code, 1)
        self.assertTrue(out['errors'][0].startswith('.claude/speclane.json is not valid JSON'))


if __name__ == '__main__':
    unittest.main()
