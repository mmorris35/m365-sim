# Verify and Fix Loop

Run the m365-sim verifier agent, then fix any findings, and re-verify until clean.

## Instructions

Execute this loop:

### Step 1: Run Verifier
Use the **m365-sim-verifier** agent to run a full verification of the project against PROJECT_BRIEF.md requirements. The verifier checks all endpoints, fixture accuracy, query parameters, write operations, error simulation, all cloud targets, all scenarios, test suite health, and edge cases.

### Step 2: Analyze Results
Parse the verification report for:
- **Critical issues** (must fix) — these block the loop
- **Warnings** (should fix) — fix these too
- **Observations** (by design) — note but don't fix unless they indicate a real problem

If the report status is **PASS** with 0 critical issues and 0 warnings, the loop is done. Print the final report summary and stop.

### Step 3: Fix Issues
For each critical issue and warning:
1. Read the affected file(s)
2. Apply the fix
3. Run `pytest tests/ -v` to ensure no regressions
4. If a test needs updating, update it

Do NOT commit fixes individually — batch them.

### Step 4: Commit Fixes
After all fixes are applied and tests pass:
```
git add -A
git commit -m "fix: resolve verifier findings

<list each fix as a bullet point>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin main
```

### Step 5: Re-verify
Go back to Step 1. Run the verifier again on the fixed code.

### Loop Termination
- **Success**: Verifier reports PASS with 0 critical, 0 warnings
- **Max iterations**: 3 (if still failing after 3 rounds, report remaining issues to the user)
- **Stuck**: If the same issue persists after a fix attempt, ask the user for guidance instead of looping

### Output
When done, summarize:
- Number of iterations needed
- Issues fixed (with before/after)
- Final test count
- Final verifier status
