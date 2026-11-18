"""Validate examples/*.speclane.json against schema/speclane.schema.json (minimal validator, stdlib only)."""
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCHEMA = json.load(open(os.path.join(ROOT, 'schema', 'speclane.schema.json')))
TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None)}


def check(v, s, path, errs):
    if '$ref' in s:
        s = SCHEMA['$defs'][s['$ref'].split('/')[-1]]
    if 'oneOf' in s:
        ok = [o for o in s['oneOf'] if not check(v, o, path, [])]
        if len(ok) != 1:
            errs.append(f'{path}: matches {len(ok)} of oneOf')
        return errs
    t = s.get('type')
    if t and not isinstance(v, TYPES[t]) or (t == 'string' and isinstance(v, bool)):
        errs.append(f'{path}: expected {t}')
        return errs
    if isinstance(v, str):
        if len(v) < s.get('minLength', 0): errs.append(f'{path}: too short')
        if 'pattern' in s and not re.search(s['pattern'], v): errs.append(f'{path}: !~ {s["pattern"]}')
    if isinstance(v, list):
        if len(v) < s.get('minItems', 0): errs.append(f'{path}: too few items')
        for i, x in enumerate(v): check(x, s.get('items', {}), f'{path}[{i}]', errs)
    if isinstance(v, dict):
        for k in s.get('required', []):
            if k not in v: errs.append(f'{path}: missing {k}')
        props = s.get('properties', {})
        for k, x in v.items():
            if k in props: check(x, props[k], f'{path}.{k}', errs)
            elif s.get('additionalProperties') is False: errs.append(f'{path}: unknown key {k}')
            elif isinstance(s.get('additionalProperties'), dict): check(x, s['additionalProperties'], f'{path}.{k}', errs)
    return errs


bad = 0
# self-test: the validator must reject a broken config
assert check({'commands': {'test': 5}, 'nope': 1}, SCHEMA, '$', []), 'validator accepts garbage'
for p in sorted(glob.glob(os.path.join(ROOT, 'examples', '*.speclane.json'))):
    errs = check(json.load(open(p)), SCHEMA, '$', [])
    print(('FAIL ' if errs else 'PASS ') + os.path.relpath(p, ROOT), *errs, sep='\n  ' if errs else '')
    bad += bool(errs)
sys.exit(1 if bad else 0)
