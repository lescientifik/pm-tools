# pm diff Implementation Plan

## Overview

`pm diff` is a Unix-style CLI tool for comparing two JSONL files to show added, removed, and changed articles.

**Purpose**: Compare snapshots of article collections (e.g., baseline updates, before/after transformations) using PMID as the unique key.

**Design Philosophy**:
- Uses PMID as unique key for comparison
- Streams input where possible
- Provides both summary and detailed output formats
- Works with pipes (Unix composability)
- Exit codes indicate difference status

## Use Cases

### Primary Use Cases

1. **Baseline Updates**: Compare two versions of parsed baseline files
   ```bash
   pm diff baseline_v1.jsonl baseline_v2.jsonl
   ```

2. **Processing Validation**: Verify processing didn't lose/add articles
   ```bash
   pm parse < raw.xml > parsed.jsonl
   pm diff expected.jsonl parsed.jsonl
   ```

3. **Filter Impact Analysis**: See what a filter removed
   ```bash
   pm filter --year 2020- < all.jsonl > filtered.jsonl
   pm diff all.jsonl filtered.jsonl --summary
   ```

4. **Incremental Updates**: Track changes between daily/weekly snapshots
   ```bash
   pm diff monday.jsonl tuesday.jsonl --format added
   ```

## Data Analysis

### JSONL Structure

Articles have these fields (from pm parse):

| Field | Type | Key? | Comparable |
|-------|------|------|------------|
| `pmid` | string | PRIMARY KEY | - |
| `title` | string | No | Yes |
| `authors` | array[string] | No | Yes |
| `journal` | string | No | Yes |
| `year` | string | No | Yes |
| `date` | string | No | Yes (if present) |
| `doi` | string | No | Yes |
| `abstract` | string | No | Yes |
| `abstract_sections` | array | No | Yes (if present) |

### Key Design Decision: PMID as Unique Key

- PMIDs are globally unique within PubMed
- A PMID cannot exist twice in the same file (if it does, that's malformed input)
- PMID is always present (required field from pm parse)

### Change Categories

1. **Added**: PMID exists in NEW but not in OLD
2. **Removed**: PMID exists in OLD but not in NEW
3. **Changed**: PMID exists in both, but content differs
4. **Unchanged**: PMID exists in both, content identical

### Content Comparison Strategy

Two articles with the same PMID are "changed" if any field differs:
- Compare JSON strings after normalization (sorted keys, compact)
- Using `jq -cS` ensures deterministic comparison
- This catches all field changes including optional fields

## Output Design

### Output Formats

#### 1. Summary Format (default)

```
OLD: old.jsonl (5 articles)
NEW: new.jsonl (5 articles)

  Added:     1
  Removed:   1
  Changed:   1
  Unchanged: 3

Total: 5 unique PMIDs
```

#### 2. Detailed Format (`--format detailed` or `-d`)

```
=== ADDED (1) ===
+ 30001: [New article title...]

=== REMOVED (1) ===
- 12345: [Old article title...]

=== CHANGED (1) ===
~ 67890: [Article title...]
    title: "Old title" -> "New title"
    year: "2023" -> "2024"
```

#### 3. PMID Lists (`--format added`, `--format removed`, `--format changed`)

Output just the PMIDs, one per line:
```bash
pm diff old.jsonl new.jsonl --format added
30001
30002
30003
```

Useful for piping:
```bash
pm diff old.jsonl new.jsonl --format added | pm fetch | pm parse > new_articles.jsonl
```

#### 4. JSONL Output (`--format jsonl`)

```json
{"pmid":"30001","status":"added","new":{...full article...}}
{"pmid":"12345","status":"removed","old":{...full article...}}
{"pmid":"67890","status":"changed","old":{...},"new":{...},"diff":["title","year"]}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No differences (files are identical) |
| 1 | Differences found |
| 2 | Error (invalid arguments, file not found, malformed JSON) |

This follows the `diff` convention where exit 1 means "differences found".

### Command Line Interface

```
pm diff - Compare two JSONL files by PMID

Usage: pm diff [OPTIONS] OLD_FILE NEW_FILE
       pm diff [OPTIONS] OLD_FILE - < new.jsonl
       pm diff [OPTIONS] - NEW_FILE < old.jsonl

Arguments:
  OLD_FILE    Baseline/reference JSONL file (or - for stdin)
  NEW_FILE    New/comparison JSONL file (or - for stdin)
  Note: At most one of OLD_FILE or NEW_FILE can be - (stdin)

Output Formats (--format):
  summary     Show counts only (default)
  detailed    Show all changes with field-level diffs
  added       List PMIDs that were added (one per line)
  removed     List PMIDs that were removed (one per line)
  changed     List PMIDs that were changed (one per line)
  all         List all PMIDs with differences (added + removed + changed)
  jsonl       Output changes as JSONL with full article data

Options:
  -f, --format FMT    Output format (see above)
  -q, --quiet         Suppress output, just set exit code
  --fields FIELDS     Compare only these fields (comma-separated)
                      Default: compare all fields
  --ignore FIELDS     Ignore these fields when comparing (comma-separated)
  -h, --help          Show this help

Examples:
  # Summary of changes
  pm diff baseline_v1.jsonl baseline_v2.jsonl

  # Get list of new PMIDs for fetching
  pm diff old.jsonl new.jsonl --format added | pm fetch

  # Detailed view of what changed
  pm diff old.jsonl new.jsonl --format detailed

  # Just check if identical (for scripts)
  pm diff file1.jsonl file2.jsonl --quiet && echo "identical"

  # Compare only title and abstract
  pm diff old.jsonl new.jsonl --fields pmid,title,abstract

  # Ignore abstract changes
  pm diff old.jsonl new.jsonl --ignore abstract
```

## Test Plan

### Unit Tests (test/pm diff.bats)

#### Basic Functionality

1. **pm diff exists and is executable**
   - Input: Check file
   - Expected: Exit 0, file exists and executable

2. **pm diff --help shows usage**
   - Input: `pm diff --help`
   - Expected: Exit 0, help text

3. **pm diff with missing arguments errors**
   - Input: `pm diff` (no args)
   - Expected: Exit 2, error message

4. **pm diff with nonexistent file errors**
   - Input: `pm diff nonexistent.jsonl other.jsonl`
   - Expected: Exit 2, "file not found" error

#### Identical Files

5. **identical files produce no differences**
   - Input: Same content in both files
   - Expected: Exit 0, summary shows 0 added/removed/changed

6. **identical files with --quiet**
   - Input: Same content
   - Expected: Exit 0, no output

#### Added Articles

7. **detects added articles**
   - OLD: PMIDs 1, 2, 3
   - NEW: PMIDs 1, 2, 3, 4, 5
   - Expected: 2 added (PMIDs 4, 5)

8. **--format added lists added PMIDs**
   - Same as above
   - Expected: stdout contains "4\n5" (one per line)

#### Removed Articles

9. **detects removed articles**
   - OLD: PMIDs 1, 2, 3, 4, 5
   - NEW: PMIDs 1, 2, 3
   - Expected: 2 removed (PMIDs 4, 5)

10. **--format removed lists removed PMIDs**
    - Same as above
    - Expected: stdout contains "4\n5"

#### Changed Articles

11. **detects changed articles (title change)**
    - OLD: PMID 1 with title "Original"
    - NEW: PMID 1 with title "Updated"
    - Expected: 1 changed

12. **detects changed articles (author change)**
    - OLD: PMID 1 with authors ["Smith A"]
    - NEW: PMID 1 with authors ["Smith A", "Jones B"]
    - Expected: 1 changed

13. **detects changed articles (field added)**
    - OLD: PMID 1 without abstract
    - NEW: PMID 1 with abstract
    - Expected: 1 changed

14. **detects changed articles (field removed)**
    - OLD: PMID 1 with abstract
    - NEW: PMID 1 without abstract
    - Expected: 1 changed

15. **--format changed lists changed PMIDs**
    - OLD: PMID 1 with title "Original"
    - NEW: PMID 1 with title "Updated"
    - Expected: stdout contains "1"

#### Combined Changes

16. **detects all types of changes together**
    - OLD: PMIDs 1, 2, 3, 4
    - NEW: PMIDs 2, 3, 4, 5 (with PMID 3 changed)
    - Expected: 1 added, 1 removed, 1 changed, 2 unchanged

17. **summary format shows correct counts**
    - Same as above
    - Expected: Summary shows "Added: 1, Removed: 1, Changed: 1, Unchanged: 2"

18. **--format all lists all different PMIDs**
    - Same as above
    - Expected: stdout contains "1\n3\n5" (sorted)

#### Detailed Output

19. **detailed format shows field-level diffs**
    - OLD: PMID 1 with title "Original", year "2023"
    - NEW: PMID 1 with title "Updated", year "2024"
    - Expected: Shows both field changes

20. **detailed format shows added article info**
    - NEW has PMID 5 with title "New Article"
    - Expected: Shows "+ 5: New Article"

21. **detailed format shows removed article info**
    - OLD has PMID 5 with title "Old Article"
    - Expected: Shows "- 5: Old Article"

#### JSONL Output

22. **jsonl format outputs valid JSONL**
    - Changes: 1 added, 1 removed, 1 changed
    - Expected: 3 lines of valid JSON

23. **jsonl format includes full article data**
    - Added article
    - Expected: `{"pmid":"X","status":"added","new":{...}}`

24. **jsonl format includes diff list for changes**
    - Changed article (title, year differ)
    - Expected: `{"pmid":"X","status":"changed",...,"diff":["title","year"]}`

#### Field Filtering

25. **--fields limits comparison to specified fields**
    - OLD: PMID 1 with title "Same", abstract "Different1"
    - NEW: PMID 1 with title "Same", abstract "Different2"
    - Filter: `--fields pmid,title`
    - Expected: 0 changed (abstract ignored)

26. **--ignore excludes specified fields**
    - Same as above
    - Filter: `--ignore abstract`
    - Expected: 0 changed

27. **--fields with invalid field warns**
    - Filter: `--fields pmid,nonexistent`
    - Expected: Warning on stderr, continues with valid fields

#### Stdin Support

28. **accepts - for OLD file (stdin)**
    - `cat old.jsonl | pm diff - new.jsonl`
    - Expected: Works correctly

29. **accepts - for NEW file (stdin)**
    - `cat new.jsonl | pm diff old.jsonl -`
    - Expected: Works correctly

30. **rejects - for both files**
    - `pm diff - -`
    - Expected: Exit 2, error message

#### Edge Cases

31. **empty OLD file**
    - OLD: empty
    - NEW: 3 articles
    - Expected: 3 added, 0 removed, 0 changed

32. **empty NEW file**
    - OLD: 3 articles
    - NEW: empty
    - Expected: 0 added, 3 removed, 0 changed

33. **both files empty**
    - Expected: Exit 0, no differences

34. **malformed JSON line skipped with warning**
    - File contains invalid JSON line
    - Expected: Warning on stderr, line skipped

35. **duplicate PMID in same file warns**
    - OLD has PMID 1 twice
    - Expected: Warning on stderr, uses last occurrence

36. **handles unicode in fields**
    - Articles with unicode characters
    - Expected: Correct comparison (no false positives)

37. **handles large files efficiently**
    - 30,000 articles per file
    - Expected: Completes in < 30 seconds

#### Exit Code Behavior

38. **exit 0 when no differences**
    - Identical files
    - Expected: Exit 0

39. **exit 1 when differences found**
    - Different files
    - Expected: Exit 1

40. **exit 2 on error**
    - Invalid arguments
    - Expected: Exit 2

### Integration Tests

41. **works with pm parse output**
    - Parse two XML files, diff the outputs
    - Verify pipeline works end-to-end

42. **--format added pipes to pm fetch**
    - `pm diff old.jsonl new.jsonl --format added | pm fetch`
    - Should produce valid XML

43. **baseline comparison**
    - Diff pubmed25n0001.pm parse.jsonl with itself
    - Expected: Exit 0, no differences

## Implementation Phases

### Phase 1: Skeleton and Help (TDD Red)

1. Create `test/pm diff.bats` with tests 1-4
2. Create `bin/pm diff` skeleton with --help only
3. Tests 1-4 should pass, others fail

### Phase 2: Loading and Identical Check (TDD)

1. Add tests 5-6
2. Implement file loading into associative array (PMID -> JSON)
3. Implement identical file detection
4. Handle stdin (-) for one file

### Phase 3: Added Detection (TDD)

1. Add tests 7-8
2. Implement detection of PMIDs in NEW but not OLD
3. Implement `--format added`

### Phase 4: Removed Detection (TDD)

1. Add tests 9-10
2. Implement detection of PMIDs in OLD but not NEW
3. Implement `--format removed`

### Phase 5: Changed Detection (TDD)

1. Add tests 11-15
2. Implement content comparison for shared PMIDs
3. Implement `--format changed`

### Phase 6: Summary and Combined (TDD)

1. Add tests 16-18
2. Implement summary format (default)
3. Implement `--format all`

### Phase 7: Detailed Output (TDD)

1. Add tests 19-21
2. Implement `--format detailed` with field-level diffs
3. Parse field differences using jq

### Phase 8: JSONL Output (TDD)

1. Add tests 22-24
2. Implement `--format jsonl`
3. Include diff field listing

### Phase 9: Field Filtering (TDD)

1. Add tests 25-27
2. Implement `--fields` option
3. Implement `--ignore` option

### Phase 10: Stdin and Edge Cases (TDD)

1. Add tests 28-37
2. Handle stdin support for one file
3. Handle edge cases (empty, malformed, duplicates)

### Phase 11: Exit Codes and Integration (TDD)

1. Add tests 38-43
2. Implement proper exit codes
3. Integration testing with pm parse

### Phase 12: Review and Polish

1. Run `/reviewing-code`
2. Fix any issues
3. Update plan.md
4. Commit

## Risk Assessment

### Low Risk
- Basic PMID comparison (straightforward set operations)
- Summary output (simple counts)
- Exit codes (standard pattern)

### Medium Risk
- Field-level diff generation (jq complexity)
- Stdin handling (can only use once, need to buffer)
- Memory usage for large files (30k articles = ~50MB in memory)

### High Risk
- Performance with very large files (100k+ articles)
  - Mitigation: Document memory requirements, suggest split for huge files
- Unicode edge cases in comparison
  - Mitigation: Use jq -cS for normalization

## Implementation Notes

### Technology Choice: bash + jq

**Data Structure**: Use bash associative arrays (bash 4+)
```bash
declare -A old_articles  # pmid -> full json line
declare -A new_articles
```

**Comparison**: Use jq for JSON normalization
```bash
# Normalize for comparison (sorted keys, compact)
normalize() {
    jq -cS '.'
}

# Compare two articles
if [[ "$(echo "$old" | normalize)" != "$(echo "$new" | normalize)" ]]; then
    echo "changed"
fi
```

### Memory Considerations

- Each article is ~500 bytes on average
- 30,000 articles = ~15MB raw
- With bash array overhead: ~50MB
- Should be fine for typical use cases

For very large files (100k+), document recommendation to:
1. Use `--format added/removed` which only outputs PMIDs
2. Process in chunks if needed

### Field-Level Diff Algorithm

```bash
# Get changed fields between two JSON objects
diff_fields() {
    local old="$1" new="$2"
    # Get all keys from both
    local all_keys
    all_keys=$(echo "$old" "$new" | jq -rs '.[0] * .[1] | keys[]')

    local changed=()
    for key in $all_keys; do
        local old_val new_val
        old_val=$(echo "$old" | jq -r ".$key // null")
        new_val=$(echo "$new" | jq -r ".$key // null")
        if [[ "$old_val" != "$new_val" ]]; then
            changed+=("$key")
        fi
    done
    printf '%s\n' "${changed[@]}"
}
```

### Sorting Output

- PMID lists should be sorted numerically for consistent output
- Use `sort -n` for PMID ordering

## Success Criteria

1. All 43 tests pass
2. Shellcheck passes on bin/pm diff
3. Performance: Compare 30k articles in < 30 seconds
4. Memory: < 100MB for 30k articles
5. Code review approved
6. Documented in help text

## Files to Create/Modify

| File | Purpose |
|------|---------|
| `bin/pm diff` | Main executable |
| `test/pm diff.bats` | All tests |
| `plan.md` | Add pm diff section |
| `spec.md` | Add pm diff specification |
| `test/test_helper.bash` | Add PM_DIFF path |

## Example Usage After Implementation

```bash
# Compare two baseline versions
pm diff baseline_v1.jsonl baseline_v2.jsonl
# Output:
# OLD: baseline_v1.jsonl (30000 articles)
# NEW: baseline_v2.jsonl (30150 articles)
#
#   Added:     175
#   Removed:   25
#   Changed:   42
#   Unchanged: 29933
#
# Total: 30175 unique PMIDs

# Get new articles for processing
pm diff baseline_v1.jsonl baseline_v2.jsonl --format added | \
    pm fetch | pm parse > new_articles.jsonl

# See what changed in detail
pm diff old.jsonl new.jsonl --format detailed

# Machine-readable output for scripts
pm diff old.jsonl new.jsonl --format jsonl | \
    jq 'select(.status == "changed")'

# Quick check if files differ
if pm diff old.jsonl new.jsonl --quiet; then
    echo "Files are identical"
else
    echo "Files differ"
fi

# Compare only metadata (ignore abstract)
pm diff old.jsonl new.jsonl --ignore abstract
```
