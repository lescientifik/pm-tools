# pm-skill Implementation Plan

## Overview

`pm-skill` installs a Claude Code skill that teaches Claude how to use the pm-tools (pm-search, pm-fetch, pm-parse, pm-filter, pm-show, pm-download).

**Purpose**: One command to make Claude instantly proficient with pm-tools in any project.

**Design Philosophy**:
- Zero configuration - the skill content is fixed
- Opinionated - one way to do things
- Safe by default - won't overwrite existing skill

## Command Interface

```
pm-skill - Install the pm-tools skill for Claude Code

Usage: pm-skill [OPTIONS]

Options:
  --global    Install to ~/.claude/skills/ (user-wide)
  --force     Overwrite existing skill
  -h, --help  Show this help

By default, installs to .claude/skills/ in the current directory.

Examples:
  pm-skill              # Install in current project
  pm-skill --global     # Install for all projects
  pm-skill --force      # Overwrite if exists
```

## Behavior

1. **Default**: Creates `.claude/skills/using-pm-tools/SKILL.md`
2. **With --global**: Creates `~/.claude/skills/using-pm-tools/SKILL.md`
3. **Conflict**: Fails with error if skill already exists (unless `--force`)
4. **Success message**: Shows path to created skill

## Skill Content (Fixed)

The skill will be named `using-pm-tools` and contain:

```markdown
---
name: using-pm-tools
description: Searches and parses PubMed articles using pm-tools CLI. Use when user asks about PubMed, scientific papers, literature search, or mentions pm-search/pm-fetch/pm-parse.
---

# Using pm-tools

Unix-style CLI tools for PubMed: search → fetch → parse → filter.

## Commands

| Command | Input | Output | Purpose |
|---------|-------|--------|---------|
| `pm-search` | Query | PMIDs | Search PubMed |
| `pm-fetch` | PMIDs | XML | Download article data |
| `pm-parse` | XML | JSONL | Extract structured fields |
| `pm-filter` | JSONL | JSONL | Filter by year/journal/author |
| `pm-show` | JSONL | Text | Pretty-print articles |
| `pm-download` | JSONL | PDFs | Download Open Access PDFs |

## Basic Pipeline

```bash
pm-search "QUERY" | pm-fetch | pm-parse | jq '.title'
```

## Common Patterns

### Search and display titles
```bash
pm-search "CRISPR therapy" --max 10 | pm-fetch | pm-parse | jq -r '.title'
```

### Filter recent papers
```bash
pm-search "machine learning" --max 50 | pm-fetch | pm-parse | pm-filter --year 2024-
```

### Pretty-print results
```bash
pm-search "cancer" --max 5 | pm-fetch | pm-parse | pm-show
```

### Download PDFs
```bash
pm-search "open access[filter] AND genomics" --max 10 | pm-fetch | pm-parse | pm-download --output-dir ./pdfs/
```

### Export to CSV
```bash
pm-search "alzheimer" --max 100 | pm-fetch | pm-parse | \
  jq -r '[.pmid, .year, .journal, .title] | @csv' > papers.csv
```

## Output Format (JSONL)

```json
{
  "pmid": "12345678",
  "title": "Article title",
  "authors": ["Smith John", "Doe Jane"],
  "journal": "Nature",
  "year": "2024",
  "doi": "10.1038/xxxxx",
  "abstract": "Full abstract..."
}
```

## Filter Options

```bash
pm-filter --year 2024           # Exact year
pm-filter --year 2020-2024      # Range
pm-filter --year 2020-          # 2020 onwards
pm-filter --journal nature      # Case-insensitive
pm-filter --author zhang        # Any author matches
pm-filter --has-abstract        # Must have abstract
pm-filter --has-doi             # Must have DOI
```

## Notes

- Rate limit: 3 req/sec (automatic)
- Batch size: 200 PMIDs per fetch
- Use `--max N` to limit search results
- Use `--verbose` for progress on large operations
```

## Test Plan

### Unit Tests (test/pm-skill.bats)

#### Phase 1: Skeleton and Help

1. **pm-skill exists and is executable**
   - Input: Check file
   - Expected: Exit 0, file exists with +x

2. **pm-skill --help shows usage**
   - Input: `pm-skill --help`
   - Expected: Exit 0, shows "Usage:", "--global", "--force"

3. **pm-skill -h is alias for --help**
   - Input: `pm-skill -h`
   - Expected: Same output as --help

#### Phase 2: Default Installation

4. **pm-skill creates .claude/skills/using-pm-tools/**
   - Input: `pm-skill` in temp directory
   - Expected: Exit 0, directory exists

5. **pm-skill creates SKILL.md**
   - Input: `pm-skill`
   - Expected: `.claude/skills/using-pm-tools/SKILL.md` exists

6. **SKILL.md has correct frontmatter**
   - Input: Read created file
   - Expected: Contains `name: using-pm-tools`, `description:`

7. **SKILL.md contains pm-tools documentation**
   - Input: Read created file
   - Expected: Contains "pm-search", "pm-fetch", "pm-parse"

8. **pm-skill prints success message**
   - Input: `pm-skill`
   - Expected: Output contains path to created skill

#### Phase 3: Conflict Handling

9. **pm-skill fails if skill exists**
   - Input: Run `pm-skill` twice
   - Expected: Exit 1 on second run, error message

10. **pm-skill --force overwrites existing**
    - Input: Create skill, modify it, run `pm-skill --force`
    - Expected: Exit 0, file is overwritten with original content

11. **pm-skill --force creates if not exists**
    - Input: `pm-skill --force` (no existing skill)
    - Expected: Exit 0, skill created

#### Phase 4: Global Installation

12. **pm-skill --global creates in ~/.claude/skills/**
    - Input: `pm-skill --global` (with mocked HOME)
    - Expected: `~/.claude/skills/using-pm-tools/SKILL.md` exists

13. **pm-skill --global fails if exists**
    - Input: Run `pm-skill --global` twice
    - Expected: Exit 1 on second run

14. **pm-skill --global --force overwrites**
    - Input: Create, then `pm-skill --global --force`
    - Expected: Exit 0, overwritten

#### Phase 5: Edge Cases

15. **pm-skill rejects unknown options**
    - Input: `pm-skill --unknown`
    - Expected: Exit 1, error about unknown option

16. **pm-skill works when .claude/ exists but skills/ doesn't**
    - Input: Create .claude/, run pm-skill
    - Expected: Exit 0, creates skills/using-pm-tools/

17. **pm-skill works in any directory (creates .claude/)**
    - Input: Run in empty temp directory
    - Expected: Exit 0, creates full path

## Implementation Phases

### Phase 1: Skeleton and Help (TDD)

**Tests**: 1-3

1. Create `test/pm-skill.bats` with tests 1-3
2. Create `bin/pm-skill` skeleton with --help only
3. Run tests until green

**Commit**: `feat: add pm-skill skeleton with --help`

### Phase 2: Default Installation (TDD)

**Tests**: 4-8

1. Add tests 4-8
2. Implement default installation:
   - Create directory with mkdir -p
   - Write SKILL.md with heredoc
   - Print success message
3. All tests green

**Commit**: `feat: implement pm-skill default installation`

### Phase 3: Conflict Handling (TDD)

**Tests**: 9-11

1. Add tests 9-11
2. Implement:
   - Check if SKILL.md exists before writing
   - `--force` flag to skip check
3. All tests green

**Commit**: `feat: add pm-skill conflict handling`

### Phase 4: Global Installation (TDD)

**Tests**: 12-14

1. Add tests 12-14
2. Implement:
   - `--global` flag to use `~/.claude/skills/`
   - Same conflict logic applies
3. All tests green

**Commit**: `feat: add pm-skill --global option`

### Phase 5: Edge Cases and Polish (TDD)

**Tests**: 15-17

1. Add tests 15-17
2. Handle edge cases:
   - Unknown options
   - Partial directory structure
3. All tests green

**Commit**: `feat: handle pm-skill edge cases`

### Phase 6: Review and Documentation

1. Run `/reviewing-code`
2. Run shellcheck
3. Update README.md to document pm-skill
4. Update spec.md if needed

**Commit**: `docs: add pm-skill to README`

## Files to Create/Modify

| File | Action |
|------|--------|
| `bin/pm-skill` | Create - main executable |
| `test/pm-skill.bats` | Create - all tests |
| `README.md` | Update - add pm-skill section |
| `plan.md` | Update - add pm-skill phase |

## Success Criteria

1. All 17 tests pass
2. shellcheck passes
3. Created skill loads in Claude Code
4. README documents the new command

## Example Session

```bash
$ pm-skill
Created: .claude/skills/using-pm-tools/SKILL.md

$ pm-skill
Error: Skill already exists at .claude/skills/using-pm-tools/
Use --force to overwrite.

$ pm-skill --force
Overwritten: .claude/skills/using-pm-tools/SKILL.md

$ pm-skill --global
Created: /home/user/.claude/skills/using-pm-tools/SKILL.md
```
