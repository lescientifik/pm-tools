---
name: developing-tdd-shell
description: Implements Shell/Bash tools using TDD with bats-core. Use when developing pm search, pm fetch, pm parse or any shell script in this project. Enforces Red-Green-Refactor workflow.
---

# TDD Shell Development

## First Steps

1. Read `spec.md` for requirements
2. Read `plan.md` for current phase and tasks
3. Check git status before starting

## TDD Workflow: Red-Green-Refactor

### 1. RED: Write failing test first

```bash
# test/pm parse.bats
@test "pm parse extracts PMID from minimal XML" {
    # Given
    local xml='<PubmedArticle><MedlineCitation><PMID>12345</PMID></MedlineCitation></PubmedArticle>'

    # When
    result=$(echo "$xml" | ./bin/pm parse)

    # Then
    [[ $(echo "$result" | jq -r '.pmid') == "12345" ]]
}
```

Run: `bats test/pm parse.bats` → must FAIL

### 2. GREEN: Minimum code to pass

Implement just enough in `bin/pm parse` to make the test pass.

Run: `bats test/pm parse.bats` → must PASS

### 3. REFACTOR: Clean up

Improve code while keeping tests green.

## Test Structure: Given-When-Then

```bash
@test "descriptive behavior name" {
    # Given: setup
    local input="..."

    # When: action
    result=$(echo "$input" | ./bin/command)

    # Then: assertions
    [[ "$result" == "expected" ]]
}
```

## Running Tests

```bash
# All tests
bats test/

# Specific file
bats test/pm parse.bats

# Verbose
bats --verbose-run test/pm parse.bats
```

## Project Structure

```
bin/           # Executables (pm search, pm fetch, pm parse)
lib/           # Shared functions (pm-common.sh)
test/          # Bats tests
fixtures/      # Test data (XML samples, expected JSONL)
scripts/       # Dev utilities (generate-golden.sh, etc.)
generated/     # Auto-generated files (mapping.json, etc.)
```

## Golden Files

Use EDirect (xtract) as oracle to generate expected outputs:

```bash
# Generate golden file with official tool
cat fixtures/sample.xml | xtract -pattern PubmedArticle ... | \
  scripts/tsv-to-jsonl.sh > fixtures/expected/sample.jsonl
```

## Git Workflow

- Commit after each GREEN phase
- Message format: `test: add pm parse PMID extraction test` or `feat: implement pm parse PMID extraction`
- Never commit RED (failing) tests

## Dependencies

Required:
- `bats-core` : test framework
- `jq` : JSON manipulation
- `xml2` : XML streaming parser
- `curl` : HTTP requests

Optional:
- `edirect` : official NCBI tools (for golden file generation)

## Current Phase

Check `plan.md` for:
- [ ] Current phase number
- [ ] Pending tasks
- [ ] Completed tasks

Always update plan.md checkboxes as you complete tasks.
