#!/usr/bin/env bash
# Offline test suite: static checks, stub workflow harness, scratch-repo script tests, examples vs schema.
set -u
cd "$(dirname "$0")/.."
rc=0
echo "== static";            python3 -m unittest tests/static_test.py 2>&1 | tail -3 || rc=1
python3 -m unittest tests/static_test.py >/dev/null 2>&1 || rc=1
echo "== workflow harness";  for f in tests/workflow/*.test.mjs; do node "$f" | tail -1; node "$f" >/dev/null || rc=1; done
echo "== embedded scripts";  python3 -m unittest discover -s tests/scripts 2>&1 | tail -3
python3 -m unittest discover -s tests/scripts >/dev/null 2>&1 || rc=1
echo "== examples";          python3 tests/check_examples.py || rc=1
[ $rc = 0 ] && echo "ALL PASS" || echo "FAILURES"
exit $rc
