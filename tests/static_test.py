"""Static checks over the plugin's shipped files: no leftovers from the source project, frontmatter rules, references resolve."""
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SHIPPED = [os.path.join(d, f) for top in ('skills', 'agents', 'workflows') for d, _, fs in os.walk(os.path.join(ROOT, top)) for f in fs]
# Source-project and stack-specific terms that must not survive in the shipped plugin (examples/ and docs/ may name a stack)
BANNED = [r'\bfvm\b', r'\bdart\b', r'flutter', r'freezed', r'build_runner', r'lib/features', r'\bVOs?\b',
          r'spec-converge', r'spec-handoff-check', r'/spec-execute', r'/spec-init', r'/work-finalize', r'/create-plan',
          r'_shared/', r'PLATFORM_CONTEXT', r'AGENT_NORMALIZATION', r'AGENT_PROMPTS', r'Cupertino',
          r'code-quality-reviewer', r'architecture-specialist', r'verify-implementation', r'\.claude/skills/', r'\.claude/workflows/']


def frontmatter(p):
    t = open(p).read()
    m = re.match(r'---\n(.*?)\n---\n', t, re.S)
    return m.group(1) if m else ''


class Static(unittest.TestCase):
    def test_no_source_project_specifics(self):
        hits = []
        for p in SHIPPED:
            for i, line in enumerate(open(p).read().splitlines(), 1):
                for b in BANNED:
                    if re.search(b, line):
                        hits.append(f'{os.path.relpath(p, ROOT)}:{i}: {b}')
        self.assertEqual(hits, [])

    def test_skill_frontmatter(self):
        names = {}
        for s in os.listdir(os.path.join(ROOT, 'skills')):
            fm = frontmatter(os.path.join(ROOT, 'skills', s, 'SKILL.md'))
            self.assertNotRegex(fm, r'(?m)^skills:', s)
            self.assertNotRegex(fm, r'(?m)^permissionMode:', s)
            self.assertNotRegex(fm, r'mcp__', s)
            names[s] = re.search(r'(?m)^name: (.*)$', fm).group(1)
        self.assertEqual(names, {s: s for s in names})
        self.assertEqual(sorted(names), ['execute', 'finalize', 'init', 'plan', 'review-plan'])
        self.assertRegex(frontmatter(os.path.join(ROOT, 'skills/init/SKILL.md')), r'(?m)^disable-model-invocation: true$')

    def test_agents_pinned(self):
        for a in ('converge', 'handoff-check'):
            fm = frontmatter(os.path.join(ROOT, 'agents', f'{a}.md'))
            self.assertRegex(fm, rf'(?m)^name: {a}$')
            self.assertRegex(fm, r'(?m)^model: claude-opus-4-6$')
            self.assertNotRegex(fm, r'(?m)^permissionMode:')
            self.assertIn('generator/verifier split', open(os.path.join(ROOT, 'agents', f'{a}.md')).read())
        self.assertNotRegex(frontmatter(os.path.join(ROOT, 'agents/handoff-check.md')), r'(?m)^tools:.*\b(Edit|Write|Bash)\b')

    def test_dispatch_names(self):
        allt = '\n'.join(open(p).read() for p in SHIPPED)
        self.assertEqual(set(re.findall(r"Workflow\(\{ name: '([^']+)'", allt)), {'speclane:execute-lanes', 'speclane:finalize-agents', 'speclane:review-plan-agents'})
        self.assertEqual(set(re.findall(r"subagent_type: \"(speclane:[^\"]+)\"", allt)), {'speclane:handoff-check'})
        self.assertIn("agentType: 'speclane:converge'", open(os.path.join(ROOT, 'workflows/execute.js')).read())
        for f, n in (('execute.js', 'execute-lanes'), ('finalize.js', 'finalize-agents'), ('review-plan.js', 'review-plan-agents')):
            self.assertRegex(open(os.path.join(ROOT, 'workflows', f)).read(), rf"(?m)^  name: '{n}',$")
        # A plugin workflow is also a slash command (/speclane:<meta.name>) and shadows a skill of the same name.
        skills = set(os.listdir(os.path.join(ROOT, 'skills')))
        for f in os.listdir(os.path.join(ROOT, 'workflows')):
            n = re.search(r"(?m)^  name: '([^']+)',$", open(os.path.join(ROOT, 'workflows', f)).read()).group(1)
            self.assertNotIn(n, skills, f'workflow {f} collides with skill {n}')

    def test_skill_dir_references_exist(self):
        for s in os.listdir(os.path.join(ROOT, 'skills')):
            t = open(os.path.join(ROOT, 'skills', s, 'SKILL.md')).read()
            for ref in re.findall(r'\$\{CLAUDE_SKILL_DIR\}/([\w.-]+)', t):
                self.assertTrue(os.path.exists(os.path.join(ROOT, 'skills', s, ref.rstrip('.'))), f'{s}: {ref}')
            for ref in re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+?)[`)\s]', t):
                self.assertTrue(os.path.exists(os.path.join(ROOT, ref.rstrip('/'))), f'{s}: {ref}')

    def test_v5_invariants_kept(self):
        js = open(os.path.join(ROOT, 'workflows/execute.js')).read()
        md = open(os.path.join(ROOT, 'skills/execute/SKILL.md')).read()
        self.assertIn('const MAX_ROUNDS = 3', js)
        self.assertIn("git commit --only -F <msgfile> -- <every new, modified, deleted, old and new path>", md)
        self.assertIn("'--format=%H%x09%(trailers:key=Spec,valueonly)'", md)
        self.assertIn('def sync_readme(item, status)', md)
        self.assertEqual(md.count('def sync_readme'), 2)
        self.assertIn('--no-ff', open(os.path.join(ROOT, 'docs/runbook.md')).read())

    def test_json_files_parse(self):
        for p in ('.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', 'schema/speclane.schema.json'):
            json.load(open(os.path.join(ROOT, p)))
        self.assertEqual(json.load(open(os.path.join(ROOT, '.claude-plugin/plugin.json')))['version'], '0.1.3')


if __name__ == '__main__':
    unittest.main()
