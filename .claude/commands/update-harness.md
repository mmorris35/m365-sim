# Update Test Harness

Update `test_harness.py` to exercise all current features, then iterate until it passes cleanly.

## Instructions

### Step 1: Inventory Current Features
Read `server.py` and the test suite to identify all features the harness should exercise:
- All scenarios (greenfield, hardened, partial)
- All cloud targets (gcc-moderate, gcc-high, commercial-e5)
- Stateful writes (--stateful, POST then GET, /_reset)
- $filter operators (eq, ne, gt, lt, startswith, contains, in)
- $expand (if implemented)
- /beta/ endpoints (if implemented)
- /_reload endpoint
- Error simulation (mock_status)
- X-Mock-Cloud header override

### Step 2: Read Current Harness
Read `test_harness.py` to understand what's already covered. Identify gaps — features that exist in the server but aren't tested by the harness.

### Step 3: Update Harness
Add new workflow sections for uncovered features. Follow the existing patterns:
- Each workflow is a function that returns `list[tuple[str, bool, str]]` (name, passed, detail)
- Use `print_results(title, results)` to display
- Add new `--workflow` choices to the argparse
- Include in the `"all"` workflow

Key patterns from the existing harness:
- `start_server(port, scenario, stateful=False)` — starts subprocess
- `GraphClient(base_url)` — makes real HTTP calls
- `stop_server(proc)` — cleanup

### Step 4: Run and Fix
```bash
source .venv/bin/activate
python test_harness.py 2>/dev/null
```

If any checks fail:
1. Determine if the failure is in the harness (wrong expectation) or the server (real bug)
2. Fix the harness if the expectation was wrong
3. Fix the server if it's a real bug, then run `pytest tests/ -v` to verify no regressions
4. Re-run the harness

Iterate until all checks pass.

### Step 5: Commit
After harness passes cleanly:
```
git add test_harness.py
# Also add server.py if any server fixes were needed
git commit -m "test: update harness to cover <list new features>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin main
```

### Step 6: Report
Print summary:
- Total workflows in harness
- Total checks across all workflows
- New workflows/checks added
- Any server bugs found and fixed

### Important
- The harness is a STANDALONE script, not a pytest file. It starts its own server subprocesses.
- Each workflow should start/stop its own server with the appropriate flags.
- Don't duplicate what pytest already covers — the harness tests higher-level workflows (assess, deploy, deploy-then-verify) while pytest tests individual endpoints.
- The harness output should be human-readable with clear pass/fail indicators.
