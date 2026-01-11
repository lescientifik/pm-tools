# PubMed CLI Tools - Project Guidelines

## Overview

Building Unix-style CLI tools for PubMed data:
- `pm-search` : query → PMIDs
- `pm-fetch` : PMIDs → XML
- `pm-parse` : XML → JSONL

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
shellcheck bin/*

# Lint + test
shellcheck bin/* && bats test/
```
