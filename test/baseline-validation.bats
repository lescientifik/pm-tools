#!/usr/bin/env bats
# Tests for Phase 0.9 baseline validation scripts
# TDD: Write tests first, then implement scripts

load test_helper

# Paths to scripts under test
BASELINE_TO_XTRACT="${PROJECT_DIR}/scripts/baseline-to-xtract-jsonl.sh"
COMPARE_JSONL="${PROJECT_DIR}/scripts/compare-jsonl.sh"
BENCHMARK_PARSER="${PROJECT_DIR}/scripts/benchmark-parser.sh"

# Skip if xtract not available (for baseline-to-xtract tests only)
xtract_available() {
    command -v xtract &> /dev/null || [ -x "${HOME}/edirect/xtract" ]
}

# =============================================================================
# Tests for baseline-to-xtract-jsonl.sh
# =============================================================================

@test "baseline-to-xtract-jsonl.sh exists and is executable" {
    # Given: the script path
    # When: we check it
    # Then: it exists and is executable
    [ -x "$BASELINE_TO_XTRACT" ]
}

@test "baseline-to-xtract-jsonl.sh produces valid JSONL" {
    if ! xtract_available; then
        skip "xtract not available (EDirect not installed)"
    fi

    # Given: a small XML fixture with multiple articles
    local xml_file="${FIXTURES_DIR}/random/pmid-3341.xml"

    # When: we run the script
    run "$BASELINE_TO_XTRACT" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output is non-empty
    [ -n "$output" ]

    # And: each line is valid JSON
    echo "$output" | while IFS= read -r line; do
        echo "$line" | jq . > /dev/null || {
            echo "Invalid JSON: $line" >&2
            return 1
        }
    done
}

@test "baseline-to-xtract-jsonl.sh handles multiple files" {
    if ! xtract_available; then
        skip "xtract not available (EDirect not installed)"
    fi

    # Given: multiple XML fixtures
    local file1="${FIXTURES_DIR}/random/pmid-3341.xml"
    local file2="${FIXTURES_DIR}/random/pmid-4583.xml"

    # When: we run the script with multiple files
    run "$BASELINE_TO_XTRACT" "$file1" "$file2"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output has at least 2 lines (one per file)
    local line_count
    line_count=$(echo "$output" | wc -l)
    [ "$line_count" -ge 2 ]
}

@test "baseline-to-xtract-jsonl.sh prints usage without arguments" {
    # Given: no arguments
    # When: we run the script
    run "$BASELINE_TO_XTRACT"

    # Then: exit code is 1
    [ "$status" -eq 1 ]

    # And: output contains usage information
    [[ "$output" == *"Usage"* ]]
}

# =============================================================================
# Tests for compare-jsonl.sh
# =============================================================================

@test "compare-jsonl.sh exists and is executable" {
    # Given: the script path
    # When: we check it
    # Then: it exists and is executable
    [ -x "$COMPARE_JSONL" ]
}

@test "compare-jsonl.sh detects identical files" {
    # Given: two identical JSONL files
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    cat > "$tmp_dir/file1.jsonl" <<'EOF'
{"pmid":"123","title":"Test Article"}
{"pmid":"456","title":"Another Article"}
EOF
    cp "$tmp_dir/file1.jsonl" "$tmp_dir/file2.jsonl"

    # When: we compare them
    run "$COMPARE_JSONL" "$tmp_dir/file1.jsonl" "$tmp_dir/file2.jsonl"

    # Then: exit code is 0 (success, no differences)
    [ "$status" -eq 0 ]

    # And: output indicates they're identical
    [[ "$output" == *"identical"* ]] || [[ "$output" == *"0 differences"* ]] || [[ "$output" == *"match"* ]]
}

@test "compare-jsonl.sh reports field-level differences" {
    # Given: two JSONL files with field differences
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    cat > "$tmp_dir/file1.jsonl" <<'EOF'
{"pmid":"123","title":"Original Title","year":"2024"}
EOF
    cat > "$tmp_dir/file2.jsonl" <<'EOF'
{"pmid":"123","title":"Different Title","year":"2024"}
EOF

    # When: we compare them
    run "$COMPARE_JSONL" "$tmp_dir/file1.jsonl" "$tmp_dir/file2.jsonl"

    # Then: exit code is 1 (differences found)
    [ "$status" -eq 1 ]

    # And: output mentions the differing field (title)
    [[ "$output" == *"title"* ]]
}

@test "compare-jsonl.sh handles missing records in second file" {
    # Given: first file has more records than second
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    cat > "$tmp_dir/file1.jsonl" <<'EOF'
{"pmid":"123","title":"Article 1"}
{"pmid":"456","title":"Article 2"}
EOF
    cat > "$tmp_dir/file2.jsonl" <<'EOF'
{"pmid":"123","title":"Article 1"}
EOF

    # When: we compare them
    run "$COMPARE_JSONL" "$tmp_dir/file1.jsonl" "$tmp_dir/file2.jsonl"

    # Then: exit code is 1 (differences found)
    [ "$status" -eq 1 ]

    # And: output mentions missing record
    [[ "$output" == *"missing"* ]] || [[ "$output" == *"456"* ]] || [[ "$output" == *"extra"* ]]
}

@test "compare-jsonl.sh handles extra records in second file" {
    # Given: second file has more records than first
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    cat > "$tmp_dir/file1.jsonl" <<'EOF'
{"pmid":"123","title":"Article 1"}
EOF
    cat > "$tmp_dir/file2.jsonl" <<'EOF'
{"pmid":"123","title":"Article 1"}
{"pmid":"456","title":"Article 2"}
EOF

    # When: we compare them
    run "$COMPARE_JSONL" "$tmp_dir/file1.jsonl" "$tmp_dir/file2.jsonl"

    # Then: exit code is 1 (differences found)
    [ "$status" -eq 1 ]

    # And: output mentions extra record
    [[ "$output" == *"extra"* ]] || [[ "$output" == *"456"* ]] || [[ "$output" == *"missing"* ]]
}

@test "compare-jsonl.sh prints usage without arguments" {
    # Given: no arguments
    # When: we run the script
    run "$COMPARE_JSONL"

    # Then: exit code is 1
    [ "$status" -eq 1 ]

    # And: output contains usage information
    [[ "$output" == *"Usage"* ]]
}

# =============================================================================
# Tests for benchmark-parser.sh
# =============================================================================

@test "benchmark-parser.sh exists and is executable" {
    # Given: the script path
    # When: we check it
    # Then: it exists and is executable
    [ -x "$BENCHMARK_PARSER" ]
}

@test "benchmark-parser.sh outputs timing stats" {
    # Given: a parser command and a small XML file
    local xml_file="${FIXTURES_DIR}/random/pmid-3341.xml"

    # When: we run the benchmark with cat as a simple "parser"
    run "$BENCHMARK_PARSER" "cat" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output contains timing information
    [[ "$output" == *"time"* ]] || [[ "$output" == *"sec"* ]] || [[ "$output" == *"articles/sec"* ]]
}

@test "benchmark-parser.sh reports articles per second" {
    # Given: pm-parse and a small XML file
    local xml_file="${FIXTURES_DIR}/random/pmid-3341.xml"

    # When: we run the benchmark with pm-parse
    run "$BENCHMARK_PARSER" "$PM_PARSE" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output contains articles/second metric
    [[ "$output" == *"articles"* ]] || [[ "$output" == *"/sec"* ]]
}

@test "benchmark-parser.sh prints usage without arguments" {
    # Given: no arguments
    # When: we run the script
    run "$BENCHMARK_PARSER"

    # Then: exit code is 1
    [ "$status" -eq 1 ]

    # And: output contains usage information
    [[ "$output" == *"Usage"* ]]
}
