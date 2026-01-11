# PubMed CLI Tools - Project Guidelines

## Overview

Building Unix-style CLI tools for PubMed data:
- `pm-search` : query → PMIDs
- `pm-fetch` : PMIDs → XML
- `pm-parse` : XML → JSONL

## Quick Start

If user says **"go"** or **"continue"**:
1. Load skill: `/developing-tdd-shell`
2. Read `plan.md` to find current phase and pending tasks
3. Start working on the next unchecked `- [ ]` task
4. Follow TDD: write test first, then implement

## After Each Sub-Phase (0.1, 0.2, 1.1, etc.)

Run a review before moving to the next sub-phase:
1. Load skill: `/reviewing-code` (runs in fork mode, isolated context)
2. Review validates: code quality, test coverage, requirements
3. If approved → commit and continue to next sub-phase
4. If needs revision → fix issues first

## Before Starting Any Work

1. **Load the TDD skill**: `/developing-tdd-shell`
2. **Read the specs**: `spec.md`
3. **Check the plan**: `plan.md` for current phase and tasks
4. **Check git status**: `git status`

## Development Rules

### Git
- Use git for version control
- Commit after each completed task (GREEN phase in TDD)
- Commit message format:
  - `test: description` for test additions
  - `feat: description` for new features
  - `fix: description` for bug fixes
  - `refactor: description` for refactoring
  - `docs: description` for documentation

### TDD Mandatory
- Never write implementation before tests
- Follow Red-Green-Refactor strictly
- Use `bats-core` for shell testing

### TDD Test Quality
- **All tests MUST fail in RED phase** - if a test passes before implementation, it's a bad test
- Beware of false positives: `[ "$status" -ne 0 ]` passes for both "script missing" (127) and "validation error" (1)
- Fix: Check **exact** exit code + verify error message content
- Example of bad test:
  ```bash
  @test "requires argument" {
      run ./script.sh  # Passes with exit 127 if script missing!
      [ "$status" -ne 0 ]
  }
  ```
- Example of good test:
  ```bash
  @test "requires argument" {
      run ./script.sh
      [ "$status" -eq 1 ]  # Exit 1 (validation), not 127 (missing)
      [[ "$output" == *"Usage"* ]]  # Verify error message
  }
  # RED: fails (127 ≠ 1, no "Usage")
  # GREEN: passes (1 = 1, "Usage" present)
  ```

### Code Style
- Shell scripts: POSIX-compatible when possible, bash when needed
- Use `shellcheck` for linting
- Prefer streaming over loading in memory
- Exit codes: 0 success, 1 error

### Documentation
- Update `plan.md` checkboxes as tasks complete
- Keep `spec.md` as source of truth for requirements
- Don't create README until project is functional

## Key Files

| File | Purpose |
|------|---------|
| `spec.md` | Requirements and decisions |
| `plan.md` | Implementation plan with phases |
| `bin/` | Executable scripts |
| `test/` | Bats test files |
| `fixtures/` | Test data |

## Dependencies

```bash
# Required
apt install bats jq xml2 curl

# Optional (for golden file generation)
# EDirect: sh -c "$(curl -fsSL https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh)"
```

## Quick Commands

```bash
# Run all tests
bats test/

# Check shell scripts
shellcheck bin/* scripts/*

# Lint + test
shellcheck bin/* scripts/* && bats test/
```

## Anti-Patterns to Avoid

### Never Take Shortcuts

1. **Missing tools**: If a required tool (shellcheck, bats, etc.) is not installed, **install it immediately**. Never say "let's skip this" or "let's move on".

2. **Slow tests**: If tests are slow, **optimize the code**, not the tests. Never create simplified test fixtures to avoid the real workload.

3. **Problems are blockers**: When encountering a problem, **solve it**. Don't work around it, don't defer it, don't minimize it.

4. **Dependencies matter**: The project specifies dependencies for a reason. Ensure all are installed and working before proceeding.

### Quality Gates

Before any commit:
- [ ] All tests pass (`bats test/`)
- [ ] shellcheck passes on all scripts (`shellcheck bin/* scripts/*`)
- [ ] Code review completed (for sub-phase completion)

### Explain Your Decisions

When making non-trivial decisions, **always explain clearly to the user**:

1. **Modifying a test**: If changing test code rather than implementation, explain:
   - What was wrong with the original test
   - Why the change fixes it
   - Example: "The test used `$status` without `run`, so `$status` was empty. Fixed by adding `run` before the assertion."

2. **Ignoring warnings or non-zero exit codes**:
   - Never silently ignore exit code 1 or warnings
   - Explain why it's safe to proceed (e.g., "SC1091 is informational - shellcheck can't follow sourced files, but the file exists")
   - If not safe, fix the issue before continuing

3. **In your reasoning**: Before making such decisions, explicitly think through:
   - What is the actual error/warning?
   - Is this a real problem or a false positive?
   - What is the correct fix?

4. **Explanation quality**:
   - Explain **proactively before** the user asks, not after
   - Be concrete: show the before/after, not just abstract concepts
   - Use simple language first, then add technical details if needed
   - Keep language consistent (don't mix French/English mid-explanation)

### Self-Correction

When the user points out a shortcut or mistake:
1. Acknowledge the error explicitly
2. Fix it immediately
3. Consider if CLAUDE.md needs updating to prevent recurrence
