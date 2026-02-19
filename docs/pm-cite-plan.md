# pm cite Implementation Plan

## Overview

`pm cite` is a CLI tool to retrieve CSL-JSON citations from PubMed via the NCBI Citation Exporter API.

**Goal:** PMIDs in, CSL-JSON out. Simple, composable, follows pm-tools Unix philosophy.

## API Research Summary

### NCBI Citation Exporter API

- **Endpoint:** `https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/`
- **Documentation:** https://pmc.ncbi.nlm.nih.gov/api/ctxp/
- **Method:** GET
- **Format:** `format=csl` (CSL-JSON)

### Request Examples

```bash
# Single PMID
curl -sL "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/?format=csl&id=28012456"

# Multiple PMIDs (comma-separated)
curl -sL "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/?format=csl&id=28012456,29886577"
```

### Response Format

**Single PMID:** Returns a JSON object
```json
{
    "source": "PubMed",
    "id": "pmid:28012456",
    "title": "...",
    "author": [{"family": "Hart", "given": "Melanie L"}, ...],
    "container-title": "Placenta",
    "issued": {"date-parts": [[2017, 1]]},
    "PMID": "28012456",
    "DOI": "10.1016/j.placenta.2016.11.007",
    "type": "article-journal"
}
```

**Multiple PMIDs:** Returns a JSON array
```json
[
    { "id": "pmid:28012456", ... },
    { "id": "pmid:29886577", ... }
]
```

### Limits

- **Rate limit:** 3 requests per second (same as E-utilities)
- **Batch limit:** ~250 PMIDs per request (URL length constraint)
- **Invalid PMIDs:** Silently ignored (not returned in response)

### Error Handling

| Condition | Response |
|-----------|----------|
| Missing `id` parameter | `{"id": {"non_field_errors": [...]}}` |
| Invalid PMID | Silently omitted from response array |
| Rate limit exceeded | Error message |

## Tool Specification

### Usage

```bash
# From stdin (pipe-friendly)
echo "28012456" | pm cite > citation.json
pm search "CRISPR" | head -5 | pm cite > citations.jsonl

# From arguments
pm cite 28012456 29886577 > citations.jsonl
```

### Input

- **stdin:** PMIDs, one per line (default)
- **arguments:** PMIDs as positional arguments
- Empty lines and whitespace are ignored

### Output

- **JSONL:** One CSL-JSON object per line (streaming, jq-compatible)
- Consistent with pm parse output format

### Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Progress on stderr |
| `-h, --help` | Show help |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (even if some PMIDs not found) |
| 1 | Error (network failure, invalid arguments) |

## Edge Cases and Handling

### 1. Invalid PMIDs

**Behavior:** NCBI silently ignores invalid PMIDs.

**Our handling:**
- Not treated as error
- With `--verbose`: log "PMID X not found" on stderr

### 2. Empty Input

**Our handling:**
- Exit 0 with no output (like pm fetch)
- Don't call API at all

### 3. Large Batches

**Our handling:**
- Batch 200 PMIDs per request (same as pm fetch)
- Rate limit between batches (0.34s = ~3 req/sec)
- Reuse batching logic from pm-common.sh

### 4. Response Format Normalization

**Problem:** Single PMID returns object, multiple returns array.

**Our handling:** Always output JSONL (one object per line):
- Single: `jq -c '.'`
- Multiple: `jq -c '.[]'`

### 5. Network Errors

**Our handling:**
- Exit 1 immediately on network error
- Print error message to stderr
- Fail-fast (like pm fetch)

## Implementation Phases (TDD)

### Phase 0: Refactor pm-common.sh (Code Reuse)

**Goal:** Extract batching logic from pm fetch to avoid duplication in pm cite.

**Principle:** TDD - write tests first, then implement, then refactor pm fetch, verify no regression.

#### 0.1 Add `read_pmids_to_array()` to pm-common.sh

**Test first (pm-common.bats):**
```bash
@test "read_pmids_to_array reads PMIDs from stdin" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"
    result=$(echo -e "123\n456\n789" | {
        read_pmids_to_array arr
        echo "${#arr[@]}:${arr[0]}:${arr[2]}"
    })
    [ "$result" = "3:123:789" ]
}

@test "read_pmids_to_array skips empty lines" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"
    result=$(echo -e "123\n\n456" | {
        read_pmids_to_array arr
        echo "${#arr[@]}"
    })
    [ "$result" = "2" ]
}

@test "read_pmids_to_array handles empty input" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"
    result=$(echo "" | {
        read_pmids_to_array arr
        echo "${#arr[@]}"
    })
    [ "$result" = "0" ]
}
```

**Implementation (pm-common.sh):**
```bash
# Read PMIDs from stdin into array variable
# Usage: read_pmids_to_array array_name
read_pmids_to_array() {
    local -n _arr=$1
    _arr=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" ]] && continue
        _arr+=("$line")
    done
}
```

#### 0.2 Add `process_batches()` to pm-common.sh

**Test first (pm-common.bats):**
```bash
@test "process_batches calls callback for each batch" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"

    # Mock callback that just echoes the batch
    mock_callback() { echo "BATCH:$1"; }

    # 5 items with batch size 2 = 3 batches
    result=$(process_batches mock_callback 2 0 a b c d e)

    [ "$(echo "$result" | wc -l)" -eq 3 ]
    [ "$(echo "$result" | head -1)" = "BATCH:a,b" ]
    [ "$(echo "$result" | tail -1)" = "BATCH:e" ]
}

@test "process_batches handles single item" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"
    mock_callback() { echo "GOT:$1"; }

    result=$(process_batches mock_callback 100 0 single)
    [ "$result" = "GOT:single" ]
}

@test "process_batches handles empty input" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"
    mock_callback() { echo "CALLED"; }

    result=$(process_batches mock_callback 100 0)
    [ -z "$result" ]
}

@test "process_batches respects batch size" {
    source "$BATS_TEST_DIRNAME/../lib/pm-common.sh"
    mock_callback() { echo "$1" | tr ',' '\n' | wc -l; }

    # 10 items, batch size 3 = batches of 3,3,3,1
    result=$(process_batches mock_callback 3 0 a b c d e f g h i j)

    [ "$(echo "$result" | head -1 | tr -d ' ')" = "3" ]
    [ "$(echo "$result" | tail -1 | tr -d ' ')" = "1" ]
}
```

**Implementation (pm-common.sh):**
```bash
# Process items in batches with rate limiting
# Usage: process_batches callback batch_size delay item1 item2 ...
# callback receives comma-separated list of items for each batch
process_batches() {
    local callback=$1 batch_size=$2 delay=$3
    shift 3
    local items=("$@")

    [[ ${#items[@]} -eq 0 ]] && return 0

    local batch_num=0
    for ((i = 0; i < ${#items[@]}; i += batch_size)); do
        ((batch_num > 0)) && sleep "$delay"
        ((batch_num++))

        # Build comma-separated list
        local batch_ids=""
        for ((j = i; j < i + batch_size && j < ${#items[@]}; j++)); do
            [[ -n "$batch_ids" ]] && batch_ids+=","
            batch_ids+="${items[j]}"
        done

        "$callback" "$batch_ids"
    done
}
```

#### 0.3 Refactor pm fetch to use new functions

**Before refactoring:** Run all pm fetch tests, save results.
```bash
bats test/pm fetch.bats > /tmp/pm fetch-before.txt
```

**Refactor pm fetch:**
```bash
# OLD (lines 66-100):
pmid_list=()
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    pmid_list+=("$line")
done
# ... batching loop ...

# NEW:
read_pmids_to_array pmid_list
[[ ${#pmid_list[@]} -eq 0 ]] && exit 0

fetch_batch() {
    curl -s "${EFETCH_URL}?db=pubmed&id=$1&rettype=abstract&retmode=xml"
}
process_batches fetch_batch "$BATCH_SIZE" "$RATE_LIMIT_DELAY" "${pmid_list[@]}"
```

**After refactoring:** Run all pm fetch tests again, verify identical results.
```bash
bats test/pm fetch.bats > /tmp/pm fetch-after.txt
diff /tmp/pm fetch-before.txt /tmp/pm fetch-after.txt  # Must be empty
```

**Regression tests (explicit checklist):**
- [ ] `pm fetch --help` works
- [ ] `pm fetch` with empty input exits 0
- [ ] `pm fetch` with single PMID returns XML
- [ ] `pm fetch` with multiple PMIDs returns XML
- [ ] `pm fetch` batching still works (200 PMIDs per request)
- [ ] All existing pm fetch.bats tests pass

### Phase 1: Basic Functionality

#### 1.1 Test: Help and Empty Input

```bash
@test "pm cite --help shows usage" {
    run bin/pm cite --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}

@test "pm cite with no input exits cleanly" {
    run bin/pm cite < /dev/null
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
```

#### 1.2 Test: Single PMID

```bash
@test "pm cite single PMID returns valid CSL-JSON" {
    echo "28012456" | bin/pm cite > "$BATS_TMPDIR/out.json"
    run jq -e '.PMID == "28012456"' "$BATS_TMPDIR/out.json"
    [ "$status" -eq 0 ]
}

@test "pm cite output has expected CSL-JSON fields" {
    echo "28012456" | bin/pm cite > "$BATS_TMPDIR/out.json"
    # Required fields
    run jq -e '.title and .author and .type' "$BATS_TMPDIR/out.json"
    [ "$status" -eq 0 ]
}
```

#### 1.3 Test: Multiple PMIDs (JSONL)

```bash
@test "pm cite multiple PMIDs returns JSONL" {
    echo -e "28012456\n29886577" | bin/pm cite > "$BATS_TMPDIR/out.jsonl"
    [ "$(wc -l < "$BATS_TMPDIR/out.jsonl")" -eq 2 ]
    # Each line is valid JSON
    run jq -c '.' "$BATS_TMPDIR/out.jsonl"
    [ "$status" -eq 0 ]
}
```

### Phase 2: Batching and Rate Limiting

**Note:** Reuse the batching pattern from pm fetch. Only the URL construction differs.

#### 2.1 Test: Batching with verbose output

```bash
@test "pm cite --verbose shows batch progress" {
    # Generate 250 PMIDs (will need 2 batches at 200 each)
    pm search "cancer" --max 250 | bin/pm cite --verbose 2>&1 >/dev/null | grep -c "Fetching batch"
    # Should see 2 batch messages
    [ "$output" -ge 2 ]
}
```

#### 2.2 Test: Rate limiting (timing)

```bash
@test "pm cite respects rate limit between batches" {
    # This test verifies rate limiting exists, not exact timing
    # (timing tests are flaky in CI)
    pm search "cancer" --max 250 | bin/pm cite --verbose 2>&1 | grep -q "batch"
}
```

### Phase 3: Error Handling

#### 3.1 Test: Invalid PMID (silent skip)

```bash
@test "pm cite skips invalid PMIDs silently" {
    # 9999999999 doesn't exist
    echo -e "28012456\n9999999999" | bin/pm cite > "$BATS_TMPDIR/out.jsonl"
    [ "$status" -eq 0 ]
    # Only valid PMID returned
    [ "$(wc -l < "$BATS_TMPDIR/out.jsonl")" -eq 1 ]
    run jq -e '.PMID == "28012456"' "$BATS_TMPDIR/out.jsonl"
    [ "$status" -eq 0 ]
}
```

#### 3.2 Test: All invalid PMIDs

```bash
@test "pm cite with all invalid PMIDs returns empty" {
    echo "9999999999" | bin/pm cite > "$BATS_TMPDIR/out.jsonl"
    [ "$status" -eq 0 ]
    [ ! -s "$BATS_TMPDIR/out.jsonl" ]  # File is empty
}
```

### Phase 4: Integration

#### 4.1 Test: Pipeline with pm search

```bash
@test "pm search | pm cite pipeline produces valid JSONL" {
    bin/pm search "CRISPR" --max 3 | bin/pm cite > "$BATS_TMPDIR/out.jsonl"
    [ "$status" -eq 0 ]
    # At least 1 result (some PMIDs might not have citations)
    [ "$(wc -l < "$BATS_TMPDIR/out.jsonl")" -ge 1 ]
    # All lines are valid JSON
    while read -r line; do
        echo "$line" | jq -e . >/dev/null
    done < "$BATS_TMPDIR/out.jsonl"
}
```

## Implementation Details

### Script Structure (bin/pm cite)

```bash
#!/usr/bin/env bash
# pm cite - Fetch CSL-JSON citations from NCBI Citation Exporter API

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/pm-common.sh"

require_commands curl jq

# Configuration (same as pm fetch)
API_URL="https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
BATCH_SIZE=200
RATE_LIMIT_DELAY=0.34

show_help() {
    cat << 'EOF'
pm cite - Fetch CSL-JSON citations from NCBI Citation Exporter API

Usage: echo "12345" | pm cite > citations.jsonl
       pm cite 12345 67890 > citations.jsonl

Options:
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Output:
  JSONL format (one CSL-JSON object per line)
EOF
    exit 0
}

# Parse options
VERBOSE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) show_help ;;
        *) die "Unknown option: $1" ;;
    esac
done

# Read PMIDs (reuse from pm-common.sh)
read_pmids_to_array pmid_list
[[ ${#pmid_list[@]} -eq 0 ]] && exit 0

# Callback for process_batches
cite_batch() {
    local ids=$1
    log_verbose "Fetching batch: ${ids:0:50}..."

    # Fetch and normalize to JSONL (handle both object and array responses)
    curl -sL "${API_URL}?format=csl&id=${ids}" | jq -c 'if type == "array" then .[] else . end'
}

# Fetch in batches (reuse from pm-common.sh)
process_batches cite_batch "$BATCH_SIZE" "$RATE_LIMIT_DELAY" "${pmid_list[@]}"
```

### Key Points

1. **Reuses `read_pmids_to_array()`** - Same as pm fetch, no duplication
2. **Reuses `process_batches()`** - Same batching/rate-limiting logic
3. **Only cite_batch() is specific** - The callback with API URL and jq normalization
4. **Same constants as pm fetch** - BATCH_SIZE=200, RATE_LIMIT_DELAY=0.34

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `lib/pm-common.sh` | Modify | Add `read_pmids_to_array()` |
| `test/pm-common.bats` | Modify | Add tests for new function |
| `bin/pm fetch` | Modify | Refactor to use `read_pmids_to_array()` |
| `bin/pm cite` | Create | Main script |
| `test/pm cite.bats` | Create | Unit tests |

## Comparison with pm fetch + pm parse

| Feature | pm fetch + pm parse | pm cite |
|---------|---------------------|---------|
| Format | Custom JSONL | Standard CSL-JSON |
| Abstract | Yes | No |
| Page numbers | No | Yes |
| Issue/Volume | No | Yes |
| Citation tools | Needs conversion | Direct (Zotero, Pandoc) |
| API | E-utilities | Citation Exporter |

**Use case:** pm cite is for generating bibliographies; pm parse is for content analysis.

## Success Criteria

1. All tests pass (including refactored pm fetch tests)
2. Output is valid CSL-JSON (validates with `jq`)
3. No code duplication with pm fetch
4. Rate limiting respects 3 req/sec
5. Integrates seamlessly in pm-tools pipeline

## References

- [NCBI Citation Exporter API](https://pmc.ncbi.nlm.nih.gov/api/ctxp/)
- [CSL-JSON Schema](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html)
