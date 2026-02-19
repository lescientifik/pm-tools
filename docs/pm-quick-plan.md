# pm quick Implementation Plan

## Overview

`pm quick` is a convenience tool that chains `pm search`, `pm fetch`, and `pm parse` for quick PubMed queries in a single command.

**Purpose**: Simplify the most common workflow - searching PubMed and getting structured JSONL output - without needing to type the full pipeline.

**Design Philosophy**:
- Wrapper around existing tools (no reimplementation)
- Passes through all options to underlying commands
- Same output as manual pipeline
- Convenient defaults for quick exploration

## Use Case Analysis

### Current Workflow (Manual Pipeline)

```bash
# The "full" way - 3 commands piped together
pm search "CRISPR cancer therapy" | pm fetch | pm parse > results.jsonl

# With options
pm search --max 50 "CRISPR" | pm fetch | pm parse | jq '.title'

# With filtering
pm search "machine learning" --max 100 | pm fetch | pm parse | pm filter --year 2024- --has-abstract
```

### Proposed Workflow (pm quick)

```bash
# One command, same result
pm quick "CRISPR cancer therapy" > results.jsonl

# With options
pm quick --max 50 "CRISPR" | jq '.title'

# Multiple terms (quoted)
pm quick "gene therapy AND review[pt]" --max 10
```

### Target Users

1. **Quick exploration**: Researchers doing ad-hoc searches
2. **Scripting beginners**: Users not comfortable with shell pipes
3. **Demo/teaching**: Simpler command for examples

### When NOT to Use pm quick

- When needing to save intermediate results (PMIDs, XML)
- When using `pm fetch` with pre-existing PMID list
- When piping baseline/offline XML files

## Data Flow Analysis

```
                  pm quick "query" --max 50
                          |
     +--------------------+--------------------+
     |                    |                    |
     v                    v                    v
  pm search          pm fetch             pm parse
     |                    |                    |
     v                    v                    v
   PMIDs     --->       XML       --->      JSONL
  (internal)         (internal)            (stdout)
```

### Intermediate Data Sizes

| Query Size | PMIDs | XML Size | JSONL Size | Time |
|------------|-------|----------|------------|------|
| 10 articles | ~100B | ~50KB | ~20KB | ~2s |
| 100 articles | ~1KB | ~500KB | ~200KB | ~5s |
| 1000 articles | ~10KB | ~5MB | ~2MB | ~30s |
| 10000 articles | ~100KB | ~50MB | ~20MB | ~5min |

**Note**: Network is the bottleneck. Local parsing is fast (~6000 articles/sec).

## Output Design

### Passthrough Model

`pm quick` should produce **exactly** the same output as the manual pipeline:

```bash
# These should be identical:
pm quick "CRISPR" --max 10 > a.jsonl
pm search "CRISPR" --max 10 | pm fetch | pm parse > b.jsonl
diff a.jsonl b.jsonl  # No differences
```

### Output Destinations

| pm quick Option | Output Location |
|-----------------|-----------------|
| (default) | JSONL to stdout |
| `--verbose` | JSONL to stdout, progress to stderr |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (even if 0 results) |
| 1 | Error (network, dependencies, etc.) |

## Command Line Interface

```
pm quick - Quick PubMed search to JSONL in one command

Usage: pm quick [OPTIONS] "search query"

Options:
  --max N         Maximum results (default: 100, max: 10000)
  -v, --verbose   Show progress on stderr
  -h, --help      Show this help message

Output:
  JSONL to stdout (one article per line)

Examples:
  # Basic search
  pm quick "CRISPR cancer therapy"

  # Limit results
  pm quick --max 20 "machine learning diagnosis"

  # With jq post-processing
  pm quick "immunotherapy" --max 50 | jq -r '.title'

  # Save to file
  pm quick "COVID vaccine 2024" > covid_papers.jsonl

  # With filtering
  pm quick "gene editing" --max 100 | pm filter --year 2024- --has-abstract

  # Complex query
  pm quick "Doudna JA[author] AND CRISPR" --max 10

Equivalent to:
  pm search "query" --max N | pm fetch | pm parse

For more control, use the individual commands:
  pm search  - Search PubMed (returns PMIDs)
  pm fetch   - Fetch article XML (from PMIDs)
  pm parse   - Parse XML to JSONL
```

### Default Behavior

| Aspect | Default | Rationale |
|--------|---------|-----------|
| `--max` | 100 | Enough for exploration, fast enough for quick use |
| Verbose | Off | Clean output for piping |

**Note on default --max**:
- `pm search` defaults to 10000 (batch processing)
- `pm quick` defaults to 100 (quick exploration)
- Users can override with `--max`

## Test Plan

### Unit Tests (test/pm quick.bats)

#### Basic Functionality

1. **pm quick exists and is executable**
   - Input: Check file
   - Expected: Exit 0, file exists with execute permission

2. **pm quick --help shows usage**
   - Input: `pm quick --help`
   - Expected: Exit 0, contains "Usage", "pm search", "pm fetch", "pm parse"

3. **pm quick requires query argument**
   - Input: `pm quick` (no args)
   - Expected: Exit 1, error message about missing query

4. **pm quick with empty query errors**
   - Input: `pm quick ""`
   - Expected: Exit 1, error message

#### Mocked Pipeline Tests

5. **pm quick runs search/fetch/parse pipeline**
   - Mock: curl returns esearch then efetch responses
   - Input: `pm quick "test query"`
   - Expected: Valid JSONL output with articles

6. **pm quick --max passes to pm search**
   - Mock: curl logs arguments
   - Input: `pm quick --max 50 "test"`
   - Expected: curl call contains `retmax=50`

7. **pm quick --max default is 100**
   - Mock: curl logs arguments
   - Input: `pm quick "test"`
   - Expected: curl call contains `retmax=100`

8. **pm quick handles zero results**
   - Mock: esearch returns empty IdList
   - Input: `pm quick "nonexistent12345"`
   - Expected: Exit 0, empty stdout

9. **pm quick handles network error**
   - Mock: curl fails with exit 1
   - Input: `pm quick "test"`
   - Expected: Exit 1, error message on stderr

#### Option Parsing

10. **--max with equals sign**
    - Input: `pm quick --max=50 "test"`
    - Expected: Works same as `--max 50`

11. **--max at different positions**
    - Input: `pm quick "test" --max 50`
    - Expected: Works (query before or after options)

12. **Multiple queries error**
    - Input: `pm quick "query1" "query2"`
    - Expected: Exit 1, error about multiple queries

13. **Unknown option errors**
    - Input: `pm quick --unknown "test"`
    - Expected: Exit 1, error message

#### Verbose Mode

14. **--verbose shows progress**
    - Mock: curl returns valid responses
    - Input: `pm quick --verbose "test"`
    - Expected: JSONL on stdout, progress on stderr

15. **-v is alias for --verbose**
    - Input: `pm quick -v "test"`
    - Expected: Same as --verbose

#### Output Equivalence

16. **pm quick output matches manual pipeline**
    - Mock: Same curl responses for both
    - Run: `pm quick "test"` vs `pm search "test" | pm fetch | pm parse`
    - Expected: Identical JSONL output

#### Edge Cases

17. **Query with special characters**
    - Input: `pm quick "BRCA1 AND (cancer OR tumor)"`
    - Expected: Query properly encoded, no shell errors

18. **Query with quotes inside**
    - Input: `pm quick 'author:"Smith J"'`
    - Expected: Works correctly

### Integration Tests

19. **End-to-end with real API (skip in CI)**
    - Input: `pm quick --max 3 "CRISPR"`
    - Expected: 3 valid JSONL lines with real data

20. **Pipeline with pm filter**
    - Mock: curl returns varied articles
    - Input: `pm quick "test" | pm filter --has-abstract`
    - Expected: Filtered output

21. **Pipeline with jq**
    - Mock: curl returns articles
    - Input: `pm quick "test" | jq -r '.pmid'`
    - Expected: PMIDs only

## Implementation Phases

### Phase 1: Skeleton and Help (TDD Red)

**Tasks:**
1. Create `test/pm quick.bats` with tests 1-4
2. Create `bin/pm quick` skeleton with:
   - Shebang and set -euo pipefail
   - Source pm-common.sh
   - `show_help()` function
   - Argument parsing stub
3. Run tests - should fail on tests 1, 3, 4

**Exit Criteria:**
- Test 2 (--help) passes
- Other tests fail appropriately

### Phase 2: Basic Pipeline (TDD Green)

**Tasks:**
1. Add tests 5-8 (mocked pipeline tests)
2. Implement:
   - Query validation
   - Default `--max 100`
   - Call `pm search "$query" --max "$max" | pm fetch | pm parse`
3. Run tests - all should pass

**Exit Criteria:**
- Tests 1-8 pass
- `pm quick "CRISPR" --max 10` works with mocked curl

### Phase 3: Option Parsing (TDD)

**Tasks:**
1. Add tests 9-13
2. Implement:
   - `--max N` and `--max=N` parsing
   - Query position flexibility
   - Error on multiple queries
   - Error on unknown options
3. Run tests

**Exit Criteria:**
- Tests 9-13 pass
- Robust option parsing

### Phase 4: Verbose Mode (TDD)

**Tasks:**
1. Add tests 14-15
2. Implement:
   - Pass `--verbose` to underlying commands (or handle locally)
   - Decide: verbose on all 3 commands? Just pm parse?
3. Run tests

**Verbose Strategy:**
- Option A: Pass --verbose to all commands (noisiest)
- Option B: Only pass to pm search (shows search progress)
- Option C: pm quick shows own progress (1 line: "Searching... Fetching... Parsing...")

**Recommendation:** Option C - pm quick shows its own simple progress:
```bash
if $VERBOSE; then
    echo "Searching PubMed for: $query" >&2
    # ... after pm search
    echo "Found $count results, fetching..." >&2
    # ... after pm fetch
    echo "Parsing..." >&2
fi
```

**Exit Criteria:**
- Tests 14-15 pass

### Phase 5: Output Equivalence (TDD)

**Tasks:**
1. Add test 16
2. Verify output matches manual pipeline exactly
3. Fix any differences

**Exit Criteria:**
- Test 16 passes
- `diff` produces no output between pm quick and manual

### Phase 6: Edge Cases (TDD)

**Tasks:**
1. Add tests 17-18
2. Handle:
   - Special characters in queries (already URL-encoded by pm search)
   - Quotes in queries
3. Run tests

**Exit Criteria:**
- Tests 17-18 pass

### Phase 7: Integration and Polish

**Tasks:**
1. Add tests 19-21
2. Add test for network error (test 9)
3. Run full test suite
4. Run shellcheck
5. Test with real API (manually)

**Exit Criteria:**
- All tests pass
- shellcheck clean
- Real API test works

### Phase 8: Review and Commit

**Tasks:**
1. Run `/reviewing-code`
2. Fix any issues
3. Update plan.md with pm quick section
4. Update spec.md with pm quick specification
5. Update README.md examples
6. Commit

**Exit Criteria:**
- Code review passed
- Documentation updated
- Committed to git

## Risk Assessment

### Low Risk
- Passthrough implementation (just pipes)
- Option parsing (standard pattern from pm search)
- Help text

### Medium Risk
- Verbose mode design (which commands to pass --verbose to)
- Query position flexibility (before/after --max)

### High Risk
- None - this is a thin wrapper

## Implementation Notes

### Wrapper vs. Reimplementation

**Decision: Wrapper**

pm quick will call the existing tools, not reimplement their logic:

```bash
# Implementation approach
pm search "$query" --max "$max" | pm fetch | pm parse
```

**Pros:**
- Minimal code
- Automatically gets improvements to underlying tools
- Single source of truth

**Cons:**
- Can't easily show unified progress
- Extra process overhead (minimal)

### Counting Results for Verbose Mode

To show "Found N results" we need to count PMIDs from pm search:

```bash
# Option A: Capture and replay
pmids=$(pm search "$query" --max "$max")
count=$(echo "$pmids" | wc -l)
echo "Found $count results" >&2
echo "$pmids" | pm fetch | pm parse

# Option B: tee to count
pm search "$query" --max "$max" | \
    tee >(wc -l >&2) | \
    pm fetch | pm parse

# Option C: Just show stages, not counts
echo "Searching..." >&2
pm search "$query" --max "$max" | pm fetch | pm parse
# (No count shown - simpler)
```

**Recommendation:** Option C for simplicity. Counts require buffering or tee complexity.

### Verbose Output Format

```
Searching PubMed: "CRISPR cancer therapy" (max 100)...
Fetching articles...
Parsing to JSONL...
```

Simple, one line per stage. Written to stderr so stdout stays clean.

### Error Handling

Errors from underlying tools propagate automatically with `set -e`:
- pm search fails (network) -> pm quick fails
- pm fetch fails (network) -> pm quick fails
- pm parse fails (bad XML) -> pm quick fails

No special error handling needed in pm quick.

## Files to Create/Modify

| File | Purpose |
|------|---------|
| `bin/pm quick` | Main executable |
| `test/pm quick.bats` | All tests |
| `plan.md` | Add pm quick section |
| `spec.md` | Add pm quick specification |
| `README.md` | Add pm quick examples |
| `install.sh` | Add pm quick to installed commands |

## Success Criteria

1. All 21 tests pass
2. shellcheck passes on bin/pm quick
3. Output identical to `pm search | pm fetch | pm parse`
4. Code review approved
5. Documentation complete

## Example Usage After Implementation

```bash
# Quick exploration
pm quick "CRISPR" | head -5 | jq '.title'

# Save search results
pm quick "COVID vaccine efficacy" > covid.jsonl

# With filtering
pm quick "machine learning diagnosis" --max 200 | \
    pm filter --year 2023- --has-abstract | \
    pm show

# Count results by journal
pm quick "immunotherapy" --max 500 | jq -r '.journal' | sort | uniq -c | sort -rn | head -10

# Export titles to text file
pm quick "BRCA1 review" --max 50 | jq -r '.title' > brca1_titles.txt
```

## Comparison: Before and After

### Before (manual pipeline)
```bash
pm search "CRISPR cancer therapy" --max 50 | pm fetch | pm parse | jq -r '.title'
```

### After (pm quick)
```bash
pm quick "CRISPR cancer therapy" --max 50 | jq -r '.title'
```

**Character savings:** ~20 characters
**Cognitive load reduction:** Significant (one concept instead of three)
