---
name: introspecting-behavior
description: Performs self-reflection on Claude's behavior during the current session. Identifies shortcuts, mistakes, and deviations from CLAUDE.md guidelines. Proposes updates to CLAUDE.md to prevent recurrence. Use when the user wants Claude to analyze its own performance and improve.
---

# Introspecting Behavior

Performs critical self-analysis of Claude's actions in the current conversation, comparing them against project guidelines, and updating CLAUDE.md to prevent future mistakes.

## When to Use

- User explicitly requests introspection (`/introspecting-behavior`)
- After the user has corrected Claude multiple times
- When reviewing a session for quality improvement

## Introspection Workflow

### Step 1: Gather Context

1. Read `CLAUDE.md` to understand current guidelines
2. Review the conversation history for:
   - User corrections or complaints
   - Moments where Claude said "let's skip", "let's move on", "passons à autre chose"
   - Times Claude created workarounds instead of solving problems
   - Missing quality checks (shellcheck, tests, etc.)

### Step 2: Identify Violations

For each potential issue, categorize it:

| Category | Example |
|----------|---------|
| **Shortcut** | Created mini-fixture instead of optimizing code |
| **Avoidance** | Skipped shellcheck because it wasn't installed |
| **Workaround** | Used trap instead of fixing root cause |
| **Omission** | Forgot to run quality gates before commit |
| **Assumption** | Proceeded without verifying dependencies |

### Step 3: Root Cause Analysis

For each violation, ask:
- Why did this happen?
- What rule in CLAUDE.md should have prevented it?
- Is the rule missing, unclear, or was it ignored?

### Step 4: Propose CLAUDE.md Updates

Generate specific, actionable additions to CLAUDE.md:

```markdown
## Anti-Patterns to Avoid

### [New Category]
- **Problem**: [What went wrong]
- **Wrong approach**: [What Claude did]
- **Correct approach**: [What Claude should do]
```

### Step 5: Apply Updates

1. Read current CLAUDE.md
2. Add new anti-patterns or clarifications
3. Ensure no duplication with existing rules
4. Commit the changes with message: `docs: update CLAUDE.md from introspection`

## Output Format

```markdown
## Introspection Report

### Session Summary
- Duration: [approximate]
- Main task: [what was being worked on]
- User corrections: [count]

### Violations Identified

#### 1. [Violation Title]
- **What happened**: [description]
- **Why it was wrong**: [explanation]
- **CLAUDE.md rule violated**: [quote or "missing"]
- **Proposed fix**: [new rule or clarification]

### CLAUDE.md Updates Applied
- [list of changes made]

### Lessons Learned
- [key takeaways for future sessions]
```

## Self-Honesty Requirements

- Do NOT minimize or justify mistakes
- Do NOT blame external factors
- Be specific about what went wrong
- Acknowledge patterns if the same mistake happened multiple times
- The goal is improvement, not defense

## Questions to Ask During Introspection

1. Did I install missing tools immediately, or did I try to skip them?
2. Did I optimize code when tests were slow, or did I simplify the tests?
3. Did I solve problems at their root, or did I create workarounds?
4. Did I run all quality gates (tests, shellcheck, review) before committing?
5. Did I follow TDD strictly (Red-Green-Refactor)?
6. Did I update plan.md checkboxes as I completed tasks?
7. Did I take the user's feedback seriously and act on it immediately?

## Example Anti-Pattern Entry

```markdown
### Never Skip Tool Installation

**Problem**: A required tool (shellcheck, bats, etc.) is not installed.

**Wrong approach**:
- "shellcheck n'est pas installé. Passons à l'extraction des fixtures."
- Proceeding without the tool
- Saying "we'll do it later"

**Correct approach**:
- Stop immediately
- Install the tool: `sudo apt install shellcheck`
- Run the tool to verify it works
- Then continue with the task
```
