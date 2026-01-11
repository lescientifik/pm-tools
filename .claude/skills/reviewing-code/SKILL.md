---
name: reviewing-code
description: Reviews implemented features for code quality, test coverage, and requirement compliance. Use after completing a coding task, before creating a pull request, or to validate implementation matches requirements.
context: fork
agent: general-purpose
---

# Code Review

Reviews code with focus on quality, tests, and requirements compliance.

## Review Process

### Step 1: Examine Git Changes

```bash
git diff HEAD~5          # Recent changes
git log --oneline -10    # Recent commits
git show <commit>        # Specific commit
```

### Step 2: Load Language Skill

If a skill exists for the primary language, load it.

### Step 3: Code Quality Review

**Readability (High Priority)**
- Descriptive names?
- Self-documenting?
- Complex sections commented?
- Logical structure?

**KISS (Keep It Simple)**
- Unnecessary complexity?
- Over-engineered solutions?
- Premature abstractions?

**DRY (Don't Repeat Yourself)**
- Duplicated code?
- Repeated patterns?
- Shared logic abstracted?

### Step 4: Test Quality (TOP PRIORITY)

**Coverage**
- All new functionality tested?
- Edge cases covered?
- Error conditions tested?

**Quality Verification**
- Tests actually test what they claim?
- Meaningful assertions?
- Could pass with broken code? (False positives)
- Could fail with correct code? (False negatives)
- Independent (not relying on order)?

**Anti-patterns to Flag**
- Testing implementation details instead of behavior
- No assertions or weak assertions
- Tests too broad or too narrow
- Over-mocked tests
- Tests that always pass

### Step 5: Requirements Check

- All requirements addressed?
- Missing requirements?
- Scope creep?

### Step 6: Run Tests (Only if Quality Passes)

Detect test framework and run:
- Shell/Bash: `bats test/`
- Python: `pytest` or `uv run pytest`
- JavaScript: `npm test`
- Go: `go test ./...`
- Other: check README or package manager

## Output Format

```markdown
## Code Review Summary

### Changes Reviewed
[Files and brief description]

### Requirements Coverage
- Covered: [list]
- Missing: [list]
- Partial: [list]

### Test Quality Assessment
**Overall: [PASS/FAIL/NEEDS IMPROVEMENT]**
[Analysis]

### Code Quality Findings
#### Readability
[Findings with line references]

#### KISS Violations
[Complexity found]

#### DRY Violations
[Duplication found]

### Test Execution Results
[Only if test quality passed]

### Recommendations
[Prioritized list]

### Verdict
[APPROVED / APPROVED WITH SUGGESTIONS / NEEDS REVISION]
```

## Guidelines

- Start by examining git - never assume what changed
- Be specific - reference exact lines
- Prioritize by severity
- Acknowledge good practices
- If tests inadequate, DO NOT run them - flag as blocking
- Be constructive - explain WHY and HOW to fix

## Inter-Agent Communication

When in multi-agent workflow:

```bash
# Read submission from Coder
.claude/skills/agent-handoff/scripts/read_last.sh CODER

# Submit review
cat << 'EOF' | .claude/skills/agent-handoff/scripts/write_message.sh REVIEWER
## Review Summary
[Assessment]

## Issues Found
- [Issue 1]

## Suggestions
- [Suggestion 1]

STATUS: approved|needs_revision
EOF
```

Always end with `STATUS: approved` or `STATUS: needs_revision`.

Never read `.claude/handoff.md` directly.
