#!/usr/bin/env bats
# test/pm-diff.bats - Tests for pm-diff command

load test_helper

# Path to pm-diff
PM_DIFF="${BIN_DIR}/pm-diff"

# =============================================================================
# Phase 1: Skeleton Tests (1-4)
# =============================================================================

@test "pm-diff exists and is executable" {
    # Given: the pm-diff script path

    # When: we check if it exists and is executable
    # Then: it should be executable
    [ -x "$PM_DIFF" ]
}

@test "pm-diff --help shows usage" {
    # Given: pm-diff is available

    # When: we run with --help
    run "$PM_DIFF" --help

    # Then: it should succeed and show usage information
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"pm-diff"* ]]
}

@test "pm-diff with missing arguments errors" {
    # Given: pm-diff is available

    # When: we run without arguments
    run "$PM_DIFF"

    # Then: it should fail with exit code 2 and show error
    [ "$status" -eq 2 ]
    [[ "$output" == *"Usage:"* ]] || [[ "$output" == *"error"* ]] || [[ "$output" == *"Error"* ]]
}

@test "pm-diff with nonexistent file errors" {
    # Given: a nonexistent file path

    # When: we run pm-diff with nonexistent files
    run "$PM_DIFF" /nonexistent/file1.jsonl /nonexistent/file2.jsonl

    # Then: it should fail with exit code 2 and show error
    [ "$status" -eq 2 ]
    [[ "$output" == *"not found"* ]] || [[ "$output" == *"No such file"* ]] || [[ "$output" == *"does not exist"* ]]
}

# =============================================================================
# Phase 2: Loading and Identical Check (5-6)
# =============================================================================

@test "identical files produce no differences" {
    # Given: two identical JSONL files
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/file1.jsonl" <<'EOF'
{"pmid":"12345","title":"Test Article One"}
{"pmid":"67890","title":"Test Article Two"}
{"pmid":"11111","title":"Test Article Three"}
EOF
    cp "$tmpdir/file1.jsonl" "$tmpdir/file2.jsonl"

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/file1.jsonl" "$tmpdir/file2.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0 (no differences), summary shows 0 changes
    [ "$status" -eq 0 ]
    [[ "$output" == *"Added:"*"0"* ]] || [[ "$output" == *"added"*"0"* ]]
    [[ "$output" == *"Removed:"*"0"* ]] || [[ "$output" == *"removed"*"0"* ]]
    [[ "$output" == *"Changed:"*"0"* ]] || [[ "$output" == *"changed"*"0"* ]]
}

@test "identical files with --quiet produces no output" {
    # Given: two identical JSONL files
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/file1.jsonl" <<'EOF'
{"pmid":"12345","title":"Test Article One"}
{"pmid":"67890","title":"Test Article Two"}
EOF
    cp "$tmpdir/file1.jsonl" "$tmpdir/file2.jsonl"

    # When: we compare them with --quiet
    run "$PM_DIFF" --quiet "$tmpdir/file1.jsonl" "$tmpdir/file2.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0, no output
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
