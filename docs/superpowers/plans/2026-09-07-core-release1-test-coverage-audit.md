# Core Release 1 test coverage audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove whether the five-test difference between the 132-test baseline and immutable RC2 represents lost product coverage, using exact pytest node IDs from clean checkouts.

**Architecture:** Treat the baseline and RC2 as immutable source datasets. Store raw collect-only output, normalize only pytest node IDs for comparison, and inspect every unmatched node against Git history and the corresponding RC2 test source. No production or release artifact is modified before the audit decision.

**Tech Stack:** Git clean checkouts, Python/pytest, PowerShell, ripgrep, Markdown evidence.

**Spec:** The user-provided “ТЗ — аудит исчезнувших тестов между Release 1 baseline и RC2”.

## Global Constraints

- Do not delete, skip, xfail, rename, or weaken tests during the audit.
- Do not change production or functional logic in Core, Scout, or Constructive.
- Do not rebuild or upload the bundle before the audit result.
- A product scenario may not be marked obsolete without source, history, consumer, and replacement-test evidence.

### Task 1: Capture immutable baseline and RC2 collections

**Files:**
- Create: `artifacts/test-audit/baseline-132-collect.txt`
- Create: `artifacts/test-audit/rc2-127-collect.txt`

- [ ] Clone or checkout the commit that actually produced `132 passed` and verify its SHA from Git history/CI evidence.
- [ ] Run `pytest --collect-only -q` in a clean baseline checkout and save the complete stdout/stderr.
- [ ] Clone RC2 at `57fd512f604ebb77d24e02d221a8a69cadc54925` and run the same command, saving the complete output.
- [ ] Extract exact node IDs from both outputs without changing either source tree.

### Task 2: Build the 100% node-id correspondence

**Files:**
- Create: `docs/operations/CORE_RELEASE_1_TEST_COVERAGE_AUDIT.md`

- [ ] Compare the two node-id sets and create one mapping row for every baseline node ID.
- [ ] Classify differences only as `UNCHANGED`, `RENAMED`, `MOVED`, `MERGED`, or evidence-backed `OBSOLETE`.
- [ ] For each unmatched baseline node, inspect its source at the baseline commit, `git diff`, `git log`, `git blame`, and `rg` consumers.
- [ ] Record whether the product scenario remains covered and link to the exact RC2 node ID or evidence.

### Task 3: Analyze the five unmatched tests and run replacements

**Files:**
- Modify only if the audit proves a real product contract is missing: the relevant tracked test file.
- Update: `docs/operations/CORE_RELEASE_1_TEST_COVERAGE_AUDIT.md`

- [ ] Show baseline source and baseline-to-RC2 changes for each unmatched node.
- [ ] Identify the product scenario and exact RC2 successor, or document a concrete failure.
- [ ] Run every identified successor test separately and record exit code/output summary.
- [ ] If a successor is absent, stop with `FAILED`; do not alter the immutable tag during this audit.

### Task 4: Verify full RC2 suite and decide release status

**Files:**
- Update: `docs/operations/CORE_RELEASE_1_TEST_COVERAGE_AUDIT.md`

- [ ] Run `pytest --collect-only -q` and `pytest -q` in the RC2 clean checkout.
- [ ] Confirm the raw collect logs and the mapping account for every baseline node ID.
- [ ] Record whether the result is `BUNDLE READY FOR SERVER UPLOAD` or `FAILED`.
- [ ] Confirm production, immutable tags, and the pre-audit bundle were not changed.

