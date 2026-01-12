---
name: planning-feature
description: Creates detailed implementation plans for complex features before coding. Launches a research agent to analyze edge cases, search the codebase, and produce a test-first plan. Use when implementing features with tricky testing, many edge cases, or complex parsing logic.
context: fork
---

# Planning Feature Implementation

Creates a detailed implementation plan before writing code. Essential for complex features where testing can be tricky.

## When to Use

- Features with many edge cases (parsing, date handling, format conversion)
- Features requiring codebase exploration first
- When you need to understand data patterns before implementing
- Before any non-trivial TDD cycle

## Arguments

The skill takes free-form arguments describing:

1. **Feature name and goal** - What you're implementing
2. **Known difficulties** - Edge cases, tricky aspects to consider
3. **Data sources** - Files to search for patterns (e.g., `.gz` baseline files)
4. **Constraints** - Backwards compatibility, performance requirements

## Example Usage

```
/planning-feature Implement complete date parsing for pm-parse.
Difficulties: MedlineDate has free-text formats (ranges, seasons),
months can be numeric or abbreviated. Search data/pubmed25n0001.xml.gz
for all date format variations. Must keep existing "year" field for
backwards compatibility.
```

## What the Plan Includes

1. **Data Analysis**
   - Search provided files for all format variations
   - Count occurrences of each pattern
   - Identify edge cases and outliers

2. **Format Categorization**
   - Group patterns by type
   - Document problematic formats
   - Note frequency/importance of each

3. **Output Design**
   - Propose field format (with rationale)
   - Handle partial/missing data
   - Backwards compatibility strategy

4. **Test Plan**
   - Specific test cases with input/output
   - Edge cases from real data
   - Regression tests for existing behavior

5. **Implementation Phases**
   - TDD-ready task breakdown
   - Risk assessment
   - Success criteria

## Output

The agent produces a detailed plan document saved to `docs/<feature>-plan.md` containing all sections above, ready for TDD implementation.

## Workflow

```
User provides: feature + difficulties + data sources
       ↓
Agent searches: codebase + data files for patterns
       ↓
Agent analyzes: categorizes formats, finds edge cases
       ↓
Agent outputs: detailed plan with test cases
       ↓
Ready for: TDD implementation (write tests first)
```
