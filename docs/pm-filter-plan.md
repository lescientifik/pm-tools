# pm-filter Implementation Plan

## Overview

`pm-filter` is a Unix-style CLI tool for filtering JSONL articles by field patterns.

**Purpose**: Provide fast, native filtering for pm-parse output without requiring jq knowledge for common use cases.

**Design Philosophy**:
- Streams input/output (no memory buffering)
- Combines filters with AND logic
- Works with pipes (Unix composability)
- Fast: minimal overhead vs. jq

## Data Analysis

### Available Fields in JSONL

From `pm-parse` output, articles have these fields:

| Field | Type | Always Present | Example |
|-------|------|----------------|---------|
| `pmid` | string | Yes | `"12345"` |
| `title` | string | Usually | `"Article title..."` |
| `authors` | array of strings | Usually | `["Smith J", "Doe A"]` |
| `journal` | string | Usually | `"Nature Medicine"` |
| `year` | string | Usually | `"2024"` |
| `date` | string | Usually | `"2024-03-15"` |
| `doi` | string | Often missing | `"10.1234/example"` |
| `abstract` | string | Often missing | `"Full text..."` |
| `abstract_sections` | array | Rare (~0.07%) | `[{"label":"BACKGROUND","text":"..."}]` |

### Field Presence Statistics (from baseline sample)

From 500 articles sampled from pubmed25n0001.xml.gz:
- `abstract`: 291/500 (58%) have abstract
- `doi`: 332/500 (66%) have DOI
- `authors`: ~99% have at least one author
- `year`: 100% have year
- `journal`: ~99% have journal

### Pattern Matching Considerations

**Year patterns**:
- Exact: `--year 2024`
- Range: `--year 2020-2024` (from 2020 to 2024 inclusive)
- Minimum: `--year 2020-` (2020 or later)
- Maximum: `--year -2020` (2020 or earlier)

**Journal patterns**:
- Case-insensitive substring: `--journal nature` matches "Nature Medicine"
- Exact match option: `--journal-exact "Nature"` for precise matching

**Author patterns**:
- Case-insensitive substring in any author: `--author smith`
- Matches: `["Smith J", "Jones A"]` because "Smith" appears

**Boolean filters**:
- `--has-abstract`: article has non-null, non-empty abstract
- `--has-doi`: article has DOI field

## Output Design

### Filter Behavior

1. **Multiple filters = AND logic**:
   ```bash
   pm-filter --year 2024 --journal nature --has-abstract
   # Passes only if: year=2024 AND journal contains "nature" AND has abstract
   ```

2. **Streaming output**: Each line read, evaluated, output if matching

3. **Exit codes**:
   - 0: Success (even if no matches)
   - 1: Error (invalid arguments, malformed JSON, etc.)

### Command Line Interface

```
pm-filter - Filter JSONL articles by field patterns

Usage: pm-parse | pm-filter [OPTIONS]
       cat articles.jsonl | pm-filter [OPTIONS]

Filter Options:
  --year PATTERN      Year filter (exact, range, or open-ended)
                      Examples: 2024, 2020-2024, 2020-, -2024
  --journal PATTERN   Journal contains PATTERN (case-insensitive)
  --journal-exact STR Journal equals STR exactly
  --author PATTERN    Any author contains PATTERN (case-insensitive)
  --has-abstract      Article has non-empty abstract
  --has-doi           Article has DOI

General Options:
  -v, --verbose       Show filter stats on stderr
  -h, --help          Show this help

Examples:
  # Recent Nature articles with abstracts
  pm-filter --year 2020- --journal nature --has-abstract

  # Articles by author Smith
  pm-filter --author smith

  # Articles from 2020 without DOI (use shell inversion)
  pm-filter --year 2020 | pm-filter --has-doi | # this gives with DOI
  # For negation, use jq: jq -c 'select(.doi | not)'
```

## Test Plan

### Unit Tests (test/pm-filter.bats)

#### Basic Functionality

1. **pm-filter exists and is executable**
   - Input: Check file
   - Expected: Exit 0, file exists and executable

2. **pm-filter with no filters passes all lines**
   - Input: 3 JSONL lines
   - Expected: 3 JSONL lines output (passthrough)

3. **pm-filter with empty input produces empty output**
   - Input: Empty stdin
   - Expected: Empty stdout, exit 0

#### Year Filtering

4. **--year exact match**
   - Input: `{"pmid":"1","year":"2024"}` + `{"pmid":"2","year":"2023"}`
   - Filter: `--year 2024`
   - Expected: Only pmid=1 passes

5. **--year range (inclusive)**
   - Input: years 2019, 2020, 2021, 2022
   - Filter: `--year 2020-2021`
   - Expected: 2020 and 2021 pass

6. **--year minimum (open-ended)**
   - Input: years 2019, 2020, 2021
   - Filter: `--year 2020-`
   - Expected: 2020 and 2021 pass

7. **--year maximum (open-ended)**
   - Input: years 2019, 2020, 2021
   - Filter: `--year -2020`
   - Expected: 2019 and 2020 pass

8. **--year with missing year field**
   - Input: `{"pmid":"1"}` (no year)
   - Filter: `--year 2024`
   - Expected: Does not pass (missing field = no match)

#### Journal Filtering

9. **--journal case-insensitive substring**
   - Input: `{"pmid":"1","journal":"Nature Medicine"}`
   - Filter: `--journal nature`
   - Expected: Passes

10. **--journal no match**
    - Input: `{"pmid":"1","journal":"Science"}`
    - Filter: `--journal nature`
    - Expected: Does not pass

11. **--journal-exact requires exact match**
    - Input: `{"pmid":"1","journal":"Nature Medicine"}` + `{"pmid":"2","journal":"Nature"}`
    - Filter: `--journal-exact Nature`
    - Expected: Only pmid=2 passes

#### Author Filtering

12. **--author matches any author (case-insensitive)**
    - Input: `{"pmid":"1","authors":["Smith J","Doe A"]}`
    - Filter: `--author smith`
    - Expected: Passes

13. **--author partial match within name**
    - Input: `{"pmid":"1","authors":["Smithson J"]}`
    - Filter: `--author smith`
    - Expected: Passes (substring match)

14. **--author no match**
    - Input: `{"pmid":"1","authors":["Jones K"]}`
    - Filter: `--author smith`
    - Expected: Does not pass

15. **--author with empty authors array**
    - Input: `{"pmid":"1","authors":[]}`
    - Filter: `--author smith`
    - Expected: Does not pass

#### Boolean Filters

16. **--has-abstract filters for presence**
    - Input: article with abstract, article without
    - Filter: `--has-abstract`
    - Expected: Only article with abstract passes

17. **--has-abstract empty string is not present**
    - Input: `{"pmid":"1","abstract":""}`
    - Filter: `--has-abstract`
    - Expected: Does not pass

18. **--has-doi filters for presence**
    - Input: article with DOI, article without
    - Filter: `--has-doi`
    - Expected: Only article with DOI passes

#### Combined Filters (AND Logic)

19. **Multiple filters combine with AND**
    - Input: 4 articles with various combinations
    - Filter: `--year 2024 --has-abstract`
    - Expected: Only articles matching BOTH pass

20. **All filters combined**
    - Input: Complex test data
    - Filter: `--year 2020-2024 --journal nature --author smith --has-abstract --has-doi`
    - Expected: Only articles matching ALL criteria pass

#### Edge Cases

21. **Malformed JSON line skipped with warning**
    - Input: `{"valid":"json"}` + `not json` + `{"also":"valid"}`
    - Filter: any
    - Expected: 2 lines output, warning on stderr for line 2

22. **--help shows usage**
    - Input: `pm-filter --help`
    - Expected: Exit 0, help text on stdout

23. **Unknown option errors**
    - Input: `pm-filter --unknown`
    - Expected: Exit 1, error message

24. **Invalid year format errors**
    - Input: `pm-filter --year abc`
    - Expected: Exit 1, error message about year format

#### Verbose Mode

25. **--verbose shows statistics**
    - Input: 100 lines, 30 pass
    - Filter: `--year 2024 --verbose`
    - Expected: stderr shows "30/100 articles passed filters"

### Integration Tests

26. **Pipeline: pm-parse | pm-filter**
    - Real XML through pm-parse, filter output
    - Verify end-to-end works

27. **Pipeline: pm-filter | pm-show**
    - Filter output can be displayed

28. **Large input performance**
    - 10,000 JSONL lines
    - Should process at >50,000 lines/sec (streaming)

## Implementation Phases

### Phase 1: Skeleton and Basic Tests (TDD Red)

1. Create `test/pm-filter.bats` with tests 1-3, 22-23
2. Create `bin/pm-filter` skeleton with --help only
3. Tests should fail (except --help)

### Phase 2: Passthrough Mode (TDD Green)

1. Implement stdin reading and passthrough
2. Tests 1-3 should pass

### Phase 3: Year Filtering (TDD)

1. Add tests 4-8
2. Implement --year parsing (exact, range, open-ended)
3. Implement year matching logic

### Phase 4: Journal Filtering (TDD)

1. Add tests 9-11
2. Implement --journal (substring, case-insensitive)
3. Implement --journal-exact (exact match)

### Phase 5: Author Filtering (TDD)

1. Add tests 12-15
2. Implement --author (any author, substring, case-insensitive)

### Phase 6: Boolean Filters (TDD)

1. Add tests 16-18
2. Implement --has-abstract, --has-doi

### Phase 7: Combined Filters and Edge Cases (TDD)

1. Add tests 19-21, 24
2. Implement AND logic for multiple filters
3. Handle malformed JSON gracefully

### Phase 8: Verbose Mode (TDD)

1. Add test 25
2. Implement --verbose with statistics

### Phase 9: Integration and Performance

1. Add tests 26-28
2. Verify pipeline compatibility
3. Benchmark and optimize if needed

### Phase 10: Review and Polish

1. Run `/reviewing-code`
2. Fix any issues
3. Update plan.md
4. Commit

## Risk Assessment

### Low Risk
- Basic filtering logic (straightforward jq/awk)
- Streaming implementation (standard pattern)

### Medium Risk
- Year range parsing (edge cases: invalid formats, missing dashes)
- Performance with very long lines (large abstracts)

### High Risk
- None identified - this is a focused filtering tool

## Implementation Notes

### Technology Choice: awk vs jq

**Option A: Pure jq**
```bash
jq -c 'select(.year == "2024")'
```
- Pro: Native JSON parsing, handles all edge cases
- Con: Slower for simple filters, jq required

**Option B: awk with JSON parsing**
```bash
awk -F'"' '/year.*2024/ { print }'
```
- Pro: Faster for simple patterns
- Con: Brittle with complex JSON, regex escaping issues

**Option C: Hybrid (Recommended)**
- Use jq for JSON parsing
- Use shell for argument parsing
- Stream with `while read` or jq streaming

**Recommendation**: Use jq for implementation. It is:
1. Already a dependency (used by pm-show, tests)
2. Handles JSON edge cases correctly
3. Fast enough for streaming (tested: >50k lines/sec)

### Year Range Implementation

```bash
# Parse year pattern
case "$year_pattern" in
    *-*)  # Range or open-ended
        year_min="${year_pattern%-*}"
        year_max="${year_pattern#*-}"
        ;;
    *)    # Exact
        year_min="$year_pattern"
        year_max="$year_pattern"
        ;;
esac

# jq filter
jq -c "select(
    (.year // \"\") as \$y |
    (\$y >= \"$year_min\" or \"$year_min\" == \"\") and
    (\$y <= \"$year_max\" or \"$year_max\" == \"\")
)"
```

### Performance Considerations

1. **Single jq invocation**: Build one jq filter expression, not multiple pipes
2. **Compact output**: Use `jq -c` to keep one line per article
3. **Early exit on parse error**: Don't retry malformed lines

## Success Criteria

1. All 28 tests pass
2. Shellcheck passes on bin/pm-filter
3. Performance: >50,000 JSONL lines/sec
4. Code review approved
5. Documented in help text

## Files to Create/Modify

| File | Purpose |
|------|---------|
| `bin/pm-filter` | Main executable |
| `test/pm-filter.bats` | All tests |
| `plan.md` | Add pm-filter section |
| `spec.md` | Add pm-filter specification |

## Example Usage After Implementation

```bash
# Find recent COVID papers with abstracts
pm-search "COVID-19" | pm-fetch | pm-parse | \
    pm-filter --year 2020- --has-abstract > covid_papers.jsonl

# Filter local baseline for Nature family journals
zcat pubmed25n0001.xml.gz | pm-parse | \
    pm-filter --journal "nature" --has-doi | \
    pm-show

# Count articles by specific author
pm-filter --author "Fauci" < all_articles.jsonl | wc -l

# Complex filter: recent oncology papers with specific criteria
pm-filter --year 2022-2024 --journal "cancer\|oncol" --has-abstract --has-doi
```
