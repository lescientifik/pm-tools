#!/usr/bin/env bats
# test/pm-diff.bats - Tests for pm-diff command (JSONL-only streaming version)

load test_helper

# Path to pm-diff
PM_DIFF="${BIN_DIR}/pm-diff"

# =============================================================================
# Phase 1: Skeleton Tests
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
# Phase 2: Identical Files (no output)
# =============================================================================

@test "identical files produce no output" {
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

    # Then: exit 0 (no differences), no output
    [ "$status" -eq 0 ]
    [ -z "$output" ]
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

# =============================================================================
# Phase 3: Added Detection (JSONL output)
# =============================================================================

@test "detects added articles as JSONL" {
    # Given: OLD has 3 articles, NEW has 5 (2 added)
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
{"pmid":"4","title":"Article Four"}
{"pmid":"5","title":"Article Five"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1 (differences found), output is valid JSONL with added status
    [ "$status" -eq 1 ]
    # Should have 2 lines (2 added articles)
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    # Each line should have status="added"
    echo "$output" | jq -e 'select(.status == "added")' > /dev/null
    # Should contain PMIDs 4 and 5
    [[ "$output" == *'"pmid":"4"'* ]]
    [[ "$output" == *'"pmid":"5"'* ]]
}

# =============================================================================
# Phase 4: Removed Detection (JSONL output)
# =============================================================================

@test "detects removed articles as JSONL" {
    # Given: OLD has 5 articles, NEW has 3 (2 removed)
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
{"pmid":"4","title":"Article Four"}
{"pmid":"5","title":"Article Five"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1 (differences found), output is valid JSONL with removed status
    [ "$status" -eq 1 ]
    # Should have 2 lines (2 removed articles)
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    # Each line should have status="removed"
    echo "$output" | jq -e 'select(.status == "removed")' > /dev/null
    # Should contain PMIDs 4 and 5
    [[ "$output" == *'"pmid":"4"'* ]]
    [[ "$output" == *'"pmid":"5"'* ]]
}

# =============================================================================
# Phase 5: Changed Detection (JSONL output)
# =============================================================================

@test "detects changed articles - title change" {
    # Given: same PMID with different title
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Original Title"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Updated Title"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1 (differences found), output is JSONL with changed status
    [ "$status" -eq 1 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    echo "$output" | jq -e '.status == "changed"'
    echo "$output" | jq -e '.pmid == "1"'
}

@test "detects changed articles - author change" {
    # Given: same PMID with different authors
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Test","authors":["Smith A"]}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Test","authors":["Smith A","Jones B"]}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output is JSONL with changed status
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "changed"'
}

@test "detects changed articles - field added" {
    # Given: same PMID, new file has additional field
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Test"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Test","abstract":"New abstract"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output is JSONL with changed status
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "changed"'
}

@test "detects changed articles - field removed" {
    # Given: same PMID, new file is missing a field
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Test","abstract":"Old abstract"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Test"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output is JSONL with changed status
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "changed"'
}

# =============================================================================
# Phase 6: Mixed Changes (JSONL output)
# =============================================================================

@test "detects all types of changes together" {
    # Given: OLD has 1,2,3,4 - NEW has 2,3,4,5 (with 3 changed)
    # 1 = removed, 3 = changed, 5 = added
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Original Three"}
{"pmid":"4","title":"Article Four"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Updated Three"}
{"pmid":"4","title":"Article Four"}
{"pmid":"5","title":"Article Five"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, 3 lines total (1 added, 1 removed, 1 changed)
    [ "$status" -eq 1 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]

    # Verify we have one of each status
    [ "$(echo "$output" | jq -r 'select(.status == "added") | .pmid' | wc -l)" -eq 1 ]
    [ "$(echo "$output" | jq -r 'select(.status == "removed") | .pmid' | wc -l)" -eq 1 ]
    [ "$(echo "$output" | jq -r 'select(.status == "changed") | .pmid' | wc -l)" -eq 1 ]
}

# =============================================================================
# Phase 7: JSONL Output Format
# =============================================================================

@test "JSONL output includes full article data for added" {
    # Given: NEW has an additional article
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"5","title":"New Article","year":"2024"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, added entry includes full article data under "article" key
    [ "$status" -eq 1 ]
    echo "$output" | jq -e 'select(.pmid == "5") | .status == "added"'
    echo "$output" | jq -e 'select(.pmid == "5") | .article.title == "New Article"'
    echo "$output" | jq -e 'select(.pmid == "5") | .article.year == "2024"'
}

@test "JSONL output includes full article data for removed" {
    # Given: NEW is missing an article
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"5","title":"Old Article","year":"2023"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, removed entry includes full article data under "article" key
    [ "$status" -eq 1 ]
    echo "$output" | jq -e 'select(.pmid == "5") | .status == "removed"'
    echo "$output" | jq -e 'select(.pmid == "5") | .article.title == "Old Article"'
    echo "$output" | jq -e 'select(.pmid == "5") | .article.year == "2023"'
}

@test "JSONL output includes old and new for changed" {
    # Given: same PMID with different title and year
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Original Title","year":"2023"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Updated Title","year":"2024"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, changed entry includes both old and new
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "changed"'
    echo "$output" | jq -e '.old.title == "Original Title"'
    echo "$output" | jq -e '.new.title == "Updated Title"'
    echo "$output" | jq -e '.old.year == "2023"'
    echo "$output" | jq -e '.new.year == "2024"'
}

# =============================================================================
# Phase 8: Field Filtering
# =============================================================================

@test "--ignore excludes specified fields" {
    # Given: articles with same title but different abstracts
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Same Title","abstract":"Different abstract 1"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Same Title","abstract":"Different abstract 2"}
EOF

    # When: we compare with --ignore abstract
    run "$PM_DIFF" --ignore abstract "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0 (no differences after ignoring abstract), no output
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

# =============================================================================
# Phase 9: Stdin Support
# =============================================================================

@test "accepts - for OLD file (stdin)" {
    # Given: two files, one via stdin
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF

    # When: we pipe OLD via stdin
    run bash -c "cat '$tmpdir/old.jsonl' | '$PM_DIFF' - '$tmpdir/new.jsonl'"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: should work, detect 1 added
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "added"'
    echo "$output" | jq -e '.pmid == "3"'
}

@test "accepts - for NEW file (stdin)" {
    # Given: two files, one via stdin
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF

    # When: we pipe NEW via stdin
    run bash -c "cat '$tmpdir/new.jsonl' | '$PM_DIFF' '$tmpdir/old.jsonl' -"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: should work, detect 1 added
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "added"'
    echo "$output" | jq -e '.pmid == "3"'
}

@test "rejects - for both files" {
    # When: we try to use stdin for both files
    run bash -c "echo '{}' | '$PM_DIFF' - -"

    # Then: should fail with exit 2
    [ "$status" -eq 2 ]
    [[ "$output" == *"Cannot use stdin"* ]] || [[ "$output" == *"both"* ]]
}

# =============================================================================
# Phase 10: Edge Cases
# =============================================================================

@test "empty OLD file - all articles added" {
    # Given: empty OLD, 3 articles in NEW
    local tmpdir
    tmpdir=$(mktemp -d)

    touch "$tmpdir/old.jsonl"
    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, 3 added lines
    [ "$status" -eq 1 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]
    [ "$(echo "$output" | jq -r 'select(.status == "added")' | jq -s 'length')" -eq 3 ]
}

@test "empty NEW file - all articles removed" {
    # Given: 3 articles in OLD, empty NEW
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF
    touch "$tmpdir/new.jsonl"

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, 3 removed lines
    [ "$status" -eq 1 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]
    [ "$(echo "$output" | jq -r 'select(.status == "removed")' | jq -s 'length')" -eq 3 ]
}

@test "both files empty - no differences" {
    # Given: both files empty
    local tmpdir
    tmpdir=$(mktemp -d)

    touch "$tmpdir/old.jsonl"
    touch "$tmpdir/new.jsonl"

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0, no output
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "malformed JSON line skipped with warning" {
    # Given: file with valid and invalid JSON
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Valid Article"}
this is not json
{"pmid":"2","title":"Another Valid"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Valid Article"}
{"pmid":"2","title":"Another Valid"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: should still work, skipping invalid line (no differences in valid lines)
    [ "$status" -eq 0 ]
}

@test "duplicate PMID in same file uses last occurrence" {
    # Given: file with duplicate PMID
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"First Occurrence"}
{"pmid":"1","title":"Last Occurrence"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Last Occurrence"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0 (uses last occurrence which matches), warning on stderr
    [ "$status" -eq 0 ]
}

@test "handles unicode in fields" {
    # Given: articles with unicode characters
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"日本語タイトル","authors":["田中太郎"]}
{"pmid":"2","title":"Résumé en français","abstract":"Ça c'est un résumé"}
EOF

    cp "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0, no false positives from unicode handling
    [ "$status" -eq 0 ]
}

# =============================================================================
# Phase 11: Exit Codes
# =============================================================================

@test "exit 0 when no differences" {
    # Given: identical files
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/file.jsonl" <<'EOF'
{"pmid":"1","title":"Test"}
EOF
    cp "$tmpdir/file.jsonl" "$tmpdir/file2.jsonl"

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/file.jsonl" "$tmpdir/file2.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0
    [ "$status" -eq 0 ]
}

@test "exit 1 when differences found" {
    # Given: different files
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Test"}
EOF
    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Changed"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1
    [ "$status" -eq 1 ]
}

@test "exit 2 on error" {
    # When: we provide invalid arguments
    run "$PM_DIFF" --invalid-option

    # Then: exit 2
    [ "$status" -eq 2 ]
}

@test "works with pm-parse output format" {
    # Given: JSONL files in pm-parse format
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"12345","title":"Cancer research study","authors":["Smith A","Jones B"],"journal":"Nature","year":"2023","doi":"10.1234/example","abstract":"Study abstract here"}
EOF
    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"12345","title":"Cancer research study - Updated","authors":["Smith A","Jones B","Brown C"],"journal":"Nature","year":"2024","doi":"10.1234/example","abstract":"Updated abstract"}
EOF

    # When: we compare them
    run "$PM_DIFF" "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: should detect changes
    [ "$status" -eq 1 ]
    echo "$output" | jq -e '.status == "changed"'
}

@test "baseline diff with self shows no differences" {
    # Given: a valid JSONL file
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/baseline.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"2","title":"Article Two"}
{"pmid":"3","title":"Article Three"}
EOF

    # When: we compare the file with itself
    run "$PM_DIFF" "$tmpdir/baseline.jsonl" "$tmpdir/baseline.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: no differences, no output
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
