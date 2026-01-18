#!/usr/bin/env bats
# Tests for pm-cite - Fetch CSL-JSON citations from NCBI Citation Exporter API

setup() {
    load 'test_helper.bash'
    PROJECT_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
    PATH="$PROJECT_ROOT/bin:$PATH"
}

# =============================================================================
# Phase 1: Basic Functionality
# =============================================================================

@test "pm-cite --help shows usage" {
    run pm-cite --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}

@test "pm-cite with no input exits cleanly" {
    run pm-cite < /dev/null
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "pm-cite single PMID returns valid CSL-JSON" {
    echo "28012456" | pm-cite > "$BATS_TMPDIR/out.json"
    run jq -e '.PMID == "28012456"' "$BATS_TMPDIR/out.json"
    [ "$status" -eq 0 ]
}

@test "pm-cite output has expected CSL-JSON fields" {
    echo "28012456" | pm-cite > "$BATS_TMPDIR/out.json"
    # Required fields
    run jq -e '.title and .author and .type' "$BATS_TMPDIR/out.json"
    [ "$status" -eq 0 ]
}

@test "pm-cite multiple PMIDs returns JSONL" {
    echo -e "28012456\n29886577" | pm-cite > "$BATS_TMPDIR/out.jsonl"
    [ "$(wc -l < "$BATS_TMPDIR/out.jsonl")" -eq 2 ]
    # Each line is valid JSON
    run jq -c '.' "$BATS_TMPDIR/out.jsonl"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Phase 2: Batching and Verbose
# =============================================================================

@test "pm-cite --verbose shows batch progress" {
    # Test with a small batch - verbose should output to stderr
    run bash -c 'echo "28012456" | pm-cite --verbose 2>&1 >/dev/null'
    [ "$status" -eq 0 ]
    [[ "$output" == *"Fetching batch"* ]]
}

@test "pm-cite accepts PMIDs as arguments" {
    run pm-cite 28012456
    [ "$status" -eq 0 ]
    # Output should be valid JSON with the PMID
    echo "$output" | jq -e '.PMID == "28012456"'
}
