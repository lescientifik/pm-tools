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

# =============================================================================
# Phase 3: Added Detection (7-8)
# =============================================================================

@test "detects added articles" {
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

    # Then: exit 1 (differences found), shows 2 added
    [ "$status" -eq 1 ]
    [[ "$output" == *"Added:"*"2"* ]]
}

@test "--format added lists added PMIDs" {
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

    # When: we get added PMIDs
    run "$PM_DIFF" --format added "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output contains PMIDs 4 and 5
    [ "$status" -eq 1 ]
    [[ "$output" == *"4"* ]]
    [[ "$output" == *"5"* ]]
    # Should have exactly 2 lines
    [ "$(echo "$output" | wc -l)" -eq 2 ]
}

# =============================================================================
# Phase 4: Removed Detection (9-10)
# =============================================================================

@test "detects removed articles" {
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

    # Then: exit 1 (differences found), shows 2 removed
    [ "$status" -eq 1 ]
    [[ "$output" == *"Removed:"*"2"* ]]
}

@test "--format removed lists removed PMIDs" {
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

    # When: we get removed PMIDs
    run "$PM_DIFF" --format removed "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output contains PMIDs 4 and 5
    [ "$status" -eq 1 ]
    [[ "$output" == *"4"* ]]
    [[ "$output" == *"5"* ]]
    # Should have exactly 2 lines
    [ "$(echo "$output" | wc -l)" -eq 2 ]
}

# =============================================================================
# Phase 5: Changed Detection (11-15)
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

    # Then: exit 1 (differences found), shows 1 changed
    [ "$status" -eq 1 ]
    [[ "$output" == *"Changed:"*"1"* ]]
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

    # Then: exit 1 (differences found), shows 1 changed
    [ "$status" -eq 1 ]
    [[ "$output" == *"Changed:"*"1"* ]]
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

    # Then: exit 1 (differences found), shows 1 changed
    [ "$status" -eq 1 ]
    [[ "$output" == *"Changed:"*"1"* ]]
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

    # Then: exit 1 (differences found), shows 1 changed
    [ "$status" -eq 1 ]
    [[ "$output" == *"Changed:"*"1"* ]]
}

@test "--format changed lists changed PMIDs" {
    # Given: two articles, one changed
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Unchanged"}
{"pmid":"2","title":"Original"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Unchanged"}
{"pmid":"2","title":"Updated"}
EOF

    # When: we get changed PMIDs
    run "$PM_DIFF" --format changed "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output contains only PMID 2
    [ "$status" -eq 1 ]
    [[ "$output" == "2" ]]
}

# =============================================================================
# Phase 6: Summary and Combined (16-18)
# =============================================================================

@test "detects all types of changes together" {
    # Given: OLD has 1,2,3,4 - NEW has 2,3,4,5 (with 3 changed)
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

    # Then: exit 1, shows 1 added, 1 removed, 1 changed, 2 unchanged
    [ "$status" -eq 1 ]
    [[ "$output" == *"Added:"*"1"* ]]
    [[ "$output" == *"Removed:"*"1"* ]]
    [[ "$output" == *"Changed:"*"1"* ]]
    [[ "$output" == *"Unchanged:"*"2"* ]]
}

@test "summary format shows correct counts" {
    # Given: OLD has 4 articles, NEW has 4 (1 removed, 1 added, 1 changed)
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

    # When: we compare them with summary format
    run "$PM_DIFF" --format summary "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, summary shows correct counts
    [ "$status" -eq 1 ]
    # Check file info
    [[ "$output" == *"OLD:"* ]]
    [[ "$output" == *"NEW:"* ]]
    [[ "$output" == *"4 articles"* ]]
    # Check counts
    [[ "$output" == *"Added:"*"1"* ]]
    [[ "$output" == *"Removed:"*"1"* ]]
    [[ "$output" == *"Changed:"*"1"* ]]
    [[ "$output" == *"Unchanged:"*"2"* ]]
}

@test "--format all lists all different PMIDs" {
    # Given: OLD has 1,2,3,4 - NEW has 2,3,4,5 (with 3 changed)
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

    # When: we get all different PMIDs
    run "$PM_DIFF" --format all "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output contains PMIDs 1, 3, 5 (sorted)
    [ "$status" -eq 1 ]
    [[ "$output" == *"1"* ]]
    [[ "$output" == *"3"* ]]
    [[ "$output" == *"5"* ]]
    # Should NOT contain unchanged PMIDs
    [[ "$output" != *$'\n2\n'* ]]
    [[ "$output" != *$'\n4\n'* ]]
    # Should have exactly 3 lines
    [ "$(echo "$output" | wc -l)" -eq 3 ]
}

# =============================================================================
# Phase 7: Detailed Output (19-21)
# =============================================================================

@test "detailed format shows field-level diffs" {
    # Given: same PMID with different title and year
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Original Title","year":"2023"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Updated Title","year":"2024"}
EOF

    # When: we compare with detailed format
    run "$PM_DIFF" --format detailed "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, shows field-level changes
    [ "$status" -eq 1 ]
    [[ "$output" == *"CHANGED"* ]]
    [[ "$output" == *"1"* ]]
    [[ "$output" == *"title"* ]]
    [[ "$output" == *"year"* ]]
}

@test "detailed format shows added article info" {
    # Given: NEW has an additional article
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"5","title":"New Article Five"}
EOF

    # When: we compare with detailed format
    run "$PM_DIFF" --format detailed "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, shows added article with "+"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ADDED"* ]]
    [[ "$output" == *"5"* ]]
    [[ "$output" == *"New Article Five"* ]] || [[ "$output" == *"+"* ]]
}

@test "detailed format shows removed article info" {
    # Given: NEW is missing an article
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
{"pmid":"5","title":"Old Article Five"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Article One"}
EOF

    # When: we compare with detailed format
    run "$PM_DIFF" --format detailed "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, shows removed article with "-"
    [ "$status" -eq 1 ]
    [[ "$output" == *"REMOVED"* ]]
    [[ "$output" == *"5"* ]]
    [[ "$output" == *"Old Article Five"* ]] || [[ "$output" == *"-"* ]]
}

# =============================================================================
# Phase 8: JSONL Output (22-24)
# =============================================================================

@test "jsonl format outputs valid JSONL" {
    # Given: files with 1 added, 1 removed, 1 changed
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Removed Article"}
{"pmid":"2","title":"Original Title"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"2","title":"Updated Title"}
{"pmid":"3","title":"Added Article"}
EOF

    # When: we compare with jsonl format
    run "$PM_DIFF" --format jsonl "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, output is valid JSONL (3 lines, each valid JSON)
    [ "$status" -eq 1 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]
    # Each line should be valid JSON
    echo "$output" | while IFS= read -r line; do
        echo "$line" | jq . > /dev/null 2>&1
    done
}

@test "jsonl format includes full article data" {
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

    # When: we compare with jsonl format
    run "$PM_DIFF" --format jsonl "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, added entry includes full article data
    [ "$status" -eq 1 ]
    # Check it has pmid, status, and new fields
    echo "$output" | jq -e 'select(.pmid == "5") | .status == "added"'
    echo "$output" | jq -e 'select(.pmid == "5") | .new.title == "New Article"'
}

@test "jsonl format includes diff list for changes" {
    # Given: same PMID with different title and year
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Original Title","year":"2023"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Updated Title","year":"2024"}
EOF

    # When: we compare with jsonl format
    run "$PM_DIFF" --format jsonl "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 1, changed entry includes diff list
    [ "$status" -eq 1 ]
    # Check it has diff array with title and year
    echo "$output" | jq -e '.status == "changed"'
    echo "$output" | jq -e '.diff | contains(["title"])'
    echo "$output" | jq -e '.diff | contains(["year"])'
}

# =============================================================================
# Phase 9: Field Filtering (25-27)
# =============================================================================

@test "--fields limits comparison to specified fields" {
    # Given: articles with same title but different abstracts
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Same Title","abstract":"Different abstract 1"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Same Title","abstract":"Different abstract 2"}
EOF

    # When: we compare with --fields pmid,title (ignoring abstract)
    run "$PM_DIFF" --fields pmid,title "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: exit 0 (no differences in compared fields)
    [ "$status" -eq 0 ]
    [[ "$output" == *"Changed:"*"0"* ]]
}

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

    # Then: exit 0 (no differences after ignoring abstract)
    [ "$status" -eq 0 ]
    [[ "$output" == *"Changed:"*"0"* ]]
}

@test "--fields with invalid field warns but continues" {
    # Given: two identical files
    local tmpdir
    tmpdir=$(mktemp -d)

    cat > "$tmpdir/old.jsonl" <<'EOF'
{"pmid":"1","title":"Test"}
EOF

    cat > "$tmpdir/new.jsonl" <<'EOF'
{"pmid":"1","title":"Test"}
EOF

    # When: we compare with --fields that includes nonexistent field
    run "$PM_DIFF" --fields pmid,nonexistent "$tmpdir/old.jsonl" "$tmpdir/new.jsonl"

    # Cleanup
    rm -rf "$tmpdir"

    # Then: should still work (warn on stderr, but succeed)
    [ "$status" -eq 0 ]
}
