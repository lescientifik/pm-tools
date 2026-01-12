# pm-diff Optimization Plan: Fast Streaming JSONL-Only Output

## Problem Statement

The current `pm-diff` implementation has performance bottlenecks that make it unsuitable for large-scale PubMed comparisons:

### Current Architecture Analysis

```
+----------+    +------------+    +-------------+    +------------+
|  File 1  | -> | Load ALL   | -> |  Compare    | -> |  Output    |
|          |    |  into      |    |  in-memory  |    |  results   |
+----------+    | bash array |    |  arrays     |    +------------+
                +------------+
+----------+    +------------+
|  File 2  | -> | Load ALL   |
|          |    |  into      |
+----------+    | bash array |
                +------------+
```

**Performance Bottlenecks:**

1. **Full file loading** (lines 192-240): Loads entire files into bash associative arrays
   - Memory: O(n) for n articles
   - Time: O(n) jq calls for normalization

2. **Per-PMID jq calls** (lines 216, 223): Each line triggers 2 jq processes
   ```bash
   pmid=$(echo "$line" | jq -r '.pmid // empty')
   normalized=$(echo "$line" | jq -cS '.')
   ```

3. **Per-comparison jq calls** (lines 298-300): Each comparison triggers multiple jq calls
   ```bash
   old_compare=$(build_compare_json "${old_articles[$pmid]}")
   new_compare=$(build_compare_json "${new_articles[$pmid]}")
   ```

4. **Per-output jq calls** (lines 391-458): Detailed/JSONL output triggers jq for each article

**Estimated Current Performance:**
- 30,000 articles = ~60,000 jq process spawns for loading alone
- At ~50ms per jq spawn = ~50 minutes just for loading
- With comparison jq calls: potentially hours for large files

### Target Architecture

```
+----------+                    +----------+
|  File 1  | ----+      +-----> |  JSONL   | (streaming output)
|          |     |      |       |  Output  |
+----------+     v      |       +----------+
            +---------+ |
            | Single  |-+
            |  awk    |
            | process |
            +---------+
+----------+     ^
|  File 2  | ----+
|          |
+----------+
```

**Target Performance:**
- Single-pass streaming: O(n) time
- No subprocess spawning per line
- Memory: O(k) where k = unique PMIDs in smaller file (for lookup)
- Goal: Match pm-parse performance (~6,000 articles/sec)

## Design Decision: JSONL-Only Output

### Rationale

The current implementation supports 7 output formats:
- `summary` (default)
- `detailed`
- `added`, `removed`, `changed`, `all` (PMID lists)
- `jsonl`

**Problem:** Non-JSONL formats require:
1. Counting (summary, detailed)
2. Human formatting (summary, detailed)
3. Buffering (all formats except streaming PMIDs)

**Solution:** Make JSONL the native output, derive others via jq:

```bash
# Current (slow internal implementation)
pm-diff --format summary old.jsonl new.jsonl

# New (streaming JSONL + jq transformation)
pm-diff old.jsonl new.jsonl | jq -s 'group_by(.status) | ...'
```

### New Output Format

Each output line is valid JSONL with one of three statuses:

```json
{"pmid":"12345","status":"added","article":{...full article...}}
{"pmid":"67890","status":"removed","article":{...full article...}}
{"pmid":"11111","status":"changed","old":{...},"new":{...},"diff":["title","year"]}
```

**Key Changes:**
- `added`: Contains `article` (the new article)
- `removed`: Contains `article` (the old article)
- `changed`: Contains `old`, `new`, and `diff` array

### Helper Scripts/Aliases for Common Formats

```bash
# Summary (counts)
pm-diff old.jsonl new.jsonl | jq -s '
  {
    added: map(select(.status=="added")) | length,
    removed: map(select(.status=="removed")) | length,
    changed: map(select(.status=="changed")) | length
  }
'

# Just added PMIDs
pm-diff old.jsonl new.jsonl | jq -r 'select(.status=="added") | .pmid'

# Just removed PMIDs
pm-diff old.jsonl new.jsonl | jq -r 'select(.status=="removed") | .pmid'

# Detailed with titles
pm-diff old.jsonl new.jsonl | jq -r '
  if .status=="added" then "+ \(.pmid): \(.article.title)"
  elif .status=="removed" then "- \(.pmid): \(.article.title)"
  else "~ \(.pmid): \(.old.title) -> \(.new.title)"
  end
'
```

## Streaming Implementation Strategy

### Algorithm: Sorted Merge with awk

**Key Insight:** If both files are sorted by PMID (or we sort them first), we can stream-compare using a merge algorithm:

```
File 1 (sorted):  1, 3, 5, 7
File 2 (sorted):  2, 3, 6, 7 (with 7 changed)

Merge walk:
- PMID 1: only in OLD -> removed
- PMID 2: only in NEW -> added
- PMID 3: in both, same -> unchanged (skip)
- PMID 5: only in OLD -> removed
- PMID 6: only in NEW -> added
- PMID 7: in both, different -> changed
```

**Time Complexity:** O(n log n) for sort, O(n) for merge = O(n log n) total
**Space Complexity:** O(1) for comparison (streaming), O(k) for sort temp files

### Implementation Phases

#### Phase 1: Core Streaming awk (RED)

Create `bin/pm-diff-fast` with:

1. **Preprocessing:** Sort both inputs by PMID
   ```bash
   sort_by_pmid() {
     jq -c '{pmid: .pmid, line: .}' | sort -t'"' -k4,4 | jq -c '.line'
   }
   ```

2. **Merge comparison in awk:**
   - Read line from each file
   - Compare PMIDs (string comparison)
   - Output appropriate status
   - Advance the file(s) with lower/equal PMID

**Tests to add:**
- Empty files (both, one)
- Identical files (no output)
- All added/removed
- Mixed changes
- Unsorted input handling

#### Phase 2: Change Detection (RED)

For PMIDs that exist in both files, detect if content changed:

1. **Normalize JSON:** `jq -cS '.'` ensures deterministic comparison
2. **String compare:** If normalized strings differ, it's changed
3. **Find diff fields:** Compare each field

**Challenge:** Finding diff fields without multiple jq calls

**Solution:** Do field-level diff in awk by parsing JSON minimally:
- Extract top-level keys
- Compare values
- Record differing keys

Alternative: Accept that `changed` records need jq for diff array:
```bash
# Fast path: just output old/new, let consumer compute diff
{"pmid":"X","status":"changed","old":{...},"new":{...}}

# Consumer can compute diff with:
jq '.diff = ([.old, .new] | map(keys) | add | unique | map(select(. as $k | $old[$k] != $new[$k])))'
```

#### Phase 3: Field Filtering (RED)

Support `--fields` and `--ignore` options:

```bash
pm-diff --fields pmid,title old.jsonl new.jsonl
pm-diff --ignore abstract old.jsonl new.jsonl
```

**Implementation:**
- In awk preprocessing, extract only requested fields
- Or use jq projection before comparison

#### Phase 4: stdin Support (RED)

Handle `-` for one input:

```bash
cat new.jsonl | pm-diff old.jsonl -
```

**Implementation:**
- If `-` detected, read that stream into temp file (necessary for sort)
- Or: require pre-sorted input for stdin case

#### Phase 5: Backwards Compatibility Layer (RED)

Provide wrapper for old formats:

```bash
# In pm-diff (wrapper)
case "$format" in
  jsonl) pm-diff-fast "$@" ;;
  summary) pm-diff-fast "$@" | jq -s '...' ;;
  added) pm-diff-fast "$@" | jq -r 'select(.status=="added") | .pmid' ;;
  # etc
esac
```

## Test Plan

### Unit Tests

| Test | Input | Expected |
|------|-------|----------|
| Empty files | both empty | exit 0, no output |
| Identical files | same content | exit 0, no output |
| All added | old empty | all status="added" |
| All removed | new empty | all status="removed" |
| All changed | same PMIDs, different content | all status="changed" |
| Mixed | add+remove+change | appropriate statuses |
| Large file | 30k articles | completes < 10 sec |
| Unicode | Japanese titles | correct comparison |
| Malformed JSON | invalid line | skip with warning |
| Duplicate PMID | same PMID twice | warn, use last |

### Performance Tests

| Test | Target |
|------|--------|
| 30k vs 30k identical | < 5 sec |
| 30k vs 30k all changed | < 10 sec |
| 30k vs 30k (10% diff) | < 7 sec |
| Memory for 30k | < 50MB |

### Integration Tests

| Test | Pipeline |
|------|----------|
| With pm-parse | `zcat file.gz \| pm-parse \| pm-diff - baseline.jsonl` |
| With jq summary | `pm-diff a.jsonl b.jsonl \| jq -s 'group_by(.status)'` |
| Pipe to pm-fetch | `pm-diff a.jsonl b.jsonl \| jq -r '.pmid' \| pm-fetch` |

## Implementation Details

### Sorting Strategy

**Option A: Pre-sort with sort command**
```bash
<"$old_file" jq -c --arg f "$old_file" '{pmid: .pmid, src: $f, data: .}' | \
  sort -t'"' -k4,4 > "$sorted_old"
```

**Option B: jq -s with sort_by**
```bash
jq -sc 'sort_by(.pmid)[]' "$old_file" > "$sorted_old"
```

**Option C: awk-based numeric sort**
```bash
awk -F'"pmid":"' '{print $2"\t"$0}' | sort -n -t'"' -k1 | cut -f2-
```

**Recommendation:** Option A for flexibility (handles non-numeric PMIDs)

### Merge Algorithm Pseudocode

```awk
BEGIN {
    # Read one line from each sorted stream
    getline old_line < OLD_FILE
    getline new_line < NEW_FILE
}

{
    # Extract PMIDs
    old_pmid = extract_pmid(old_line)
    new_pmid = extract_pmid(new_line)

    while (old_pmid != "" || new_pmid != "") {
        if (old_pmid == "" || (new_pmid != "" && new_pmid < old_pmid)) {
            # New only - added
            output_added(new_line)
            advance_new()
        }
        else if (new_pmid == "" || old_pmid < new_pmid) {
            # Old only - removed
            output_removed(old_line)
            advance_old()
        }
        else {
            # Same PMID - check if changed
            if (normalize(old_line) != normalize(new_line)) {
                output_changed(old_line, new_line)
            }
            advance_both()
        }
    }
}
```

### JSON Normalization in awk

For detecting changes without jq, normalize JSON deterministically:

```awk
function normalize_json(line) {
    # Remove whitespace outside strings (simplified)
    gsub(/[ \t\n]+/, "", line)
    # Sort keys (complex - may need external sort or accept limitations)
    return line
}
```

**Limitation:** Full JSON key sorting in awk is complex. Options:
1. Accept that whitespace-only differences are "changes" (false positives)
2. Use jq -cS in preprocessing (one call per file, not per line)
3. Implement simplified key sorting in awk

**Recommendation:** Preprocess with jq -cS once per file:
```bash
<"$file" jq -cS '.' | sort_by_pmid
```

This adds one jq call per file, not per line.

## Migration Path

### Phase 1: Add pm-diff-stream (non-breaking)

- Create new `bin/pm-diff-stream` with optimized implementation
- Keep existing `bin/pm-diff` unchanged
- Document performance difference

### Phase 2: Update pm-diff (breaking)

- Replace `bin/pm-diff` with streaming version
- Change default output to JSONL
- Add `--format` wrapper for backwards compatibility
- Update tests to reflect new default

### Phase 3: Deprecation

- Deprecate non-JSONL formats with warning
- Point users to jq transformations
- Remove wrapper in future version

## Risk Assessment

### Low Risk
- Streaming algorithm correctness
- Basic PMID comparison
- Empty file handling

### Medium Risk
- Sort performance on very large files
- JSON normalization edge cases
- stdin handling complexity

### High Risk
- Breaking backwards compatibility
- Memory usage during sort of huge files
- Unicode edge cases in sorting

### Mitigations

1. **Backwards compatibility:** Wrapper script maintains old behavior
2. **Memory:** Use external sort (handles arbitrary size)
3. **Unicode:** Use `sort -t` with explicit field extraction
4. **Testing:** Add comprehensive edge case tests

## Success Criteria

1. **Performance:** 30k article diff in < 10 seconds (vs current ~30+ minutes)
2. **Correctness:** 100% match with current implementation on all test cases
3. **Memory:** < 100MB for 30k articles (vs current ~500MB)
4. **Streaming:** Output begins immediately, not after full load
5. **Unix philosophy:** JSONL output composable with jq

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `bin/pm-diff` | Rewrite | New streaming implementation |
| `test/pm-diff.bats` | Update | Add performance tests, update for JSONL default |
| `docs/pm-diff-plan.md` | Update | Document new architecture |
| `spec.md` | Update | Document JSONL output format |

## Example Session After Implementation

```bash
# Fast streaming comparison
$ time pm-diff baseline_v1.jsonl baseline_v2.jsonl | wc -l
1250
real    0m3.456s  # vs current 30+ minutes

# Get just added PMIDs (for fetching updates)
$ pm-diff old.jsonl new.jsonl | jq -r 'select(.status=="added") | .pmid' | pm-fetch

# Summary counts
$ pm-diff old.jsonl new.jsonl | jq -s '{
    added: map(select(.status=="added")) | length,
    removed: map(select(.status=="removed")) | length,
    changed: map(select(.status=="changed")) | length
  }'
{
  "added": 175,
  "removed": 25,
  "changed": 42
}

# Check if files are identical (no output = identical)
$ pm-diff file1.jsonl file2.jsonl | head -1 || echo "Files are identical"
Files are identical
```
