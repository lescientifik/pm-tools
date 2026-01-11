#!/usr/bin/env bats

# Tests for scripts/extract-fixtures.sh
# Extracts random and edge-case articles from PubMed baseline XML

setup() {
    # Use project root as base
    PROJECT_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SCRIPT="$PROJECT_ROOT/scripts/extract-fixtures.sh"
    BASELINE="$PROJECT_ROOT/data/pubmed25n0001.xml.gz"
    FIXTURES_DIR="$PROJECT_ROOT/fixtures"
}

# --- Argument validation tests ---

@test "extract-fixtures.sh exists and is executable" {
    [ -x "$SCRIPT" ]
}

@test "shows usage when called without arguments" {
    run "$SCRIPT"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]]
}

@test "fails if baseline file does not exist" {
    run "$SCRIPT" --baseline /nonexistent/file.xml.gz --random 1 --output-dir "$BATS_TEST_TMPDIR/test"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not found"* ]] || [[ "$output" == *"does not exist"* ]]
}

# --- Random extraction tests ---

@test "extracts N random articles with --random N" {
    local outdir="$BATS_TEST_TMPDIR/random"
    run "$SCRIPT" --baseline "$BASELINE" --random 3 --output-dir "$outdir"
    [ "$status" -eq 0 ]

    # Should create exactly 3 XML files
    local count=$(ls "$outdir"/*.xml 2>/dev/null | wc -l)
    [ "$count" -eq 3 ]
}

@test "random articles are valid PubmedArticle XML" {
    run "$SCRIPT" --baseline "$BASELINE" --random 1 --output-dir "$BATS_TEST_TMPDIR/valid"
    [ "$status" -eq 0 ]

    # Each file should contain a complete PubmedArticle
    local file=$(ls "$BATS_TEST_TMPDIR/valid"/*.xml | head -1)
    [[ "$(head -1 "$file")" == *"<PubmedArticle>"* ]] || [[ "$(head -1 "$file")" == *"<?xml"* ]]
    grep -q "</PubmedArticle>" "$file"
}

# --- Edge case detection tests ---

@test "finds article without DOI with --edge-case no-doi" {
    run "$SCRIPT" --baseline "$BASELINE" --edge-case no-doi --output-dir "$BATS_TEST_TMPDIR/no-doi"
    [ "$status" -eq 0 ]

    # Should find at least one article
    local count=$(ls "$BATS_TEST_TMPDIR/no-doi"/*.xml 2>/dev/null | wc -l)
    [ "$count" -ge 1 ]

    # Verify the article has no DOI
    local file=$(ls "$BATS_TEST_TMPDIR/no-doi"/*.xml | head -1)
    ! grep -q 'IdType="doi"' "$file"
}

@test "finds article without abstract with --edge-case no-abstract" {
    run "$SCRIPT" --baseline "$BASELINE" --edge-case no-abstract --output-dir "$BATS_TEST_TMPDIR/no-abstract"
    [ "$status" -eq 0 ]

    local count=$(ls "$BATS_TEST_TMPDIR/no-abstract"/*.xml 2>/dev/null | wc -l)
    [ "$count" -ge 1 ]

    # Verify article has no Abstract element
    local file=$(ls "$BATS_TEST_TMPDIR/no-abstract"/*.xml | head -1)
    ! grep -q '<Abstract>' "$file"
}

@test "finds article with structured abstract with --edge-case structured-abstract" {
    run "$SCRIPT" --baseline "$BASELINE" --edge-case structured-abstract --output-dir "$BATS_TEST_TMPDIR/struct"
    [ "$status" -eq 0 ]

    local count=$(ls "$BATS_TEST_TMPDIR/struct"/*.xml 2>/dev/null | wc -l)
    [ "$count" -ge 1 ]

    # Verify article has AbstractText with Label attribute
    local file=$(ls "$BATS_TEST_TMPDIR/struct"/*.xml | head -1)
    grep -q 'AbstractText.*Label=' "$file" || grep -q '<AbstractText Label=' "$file"
}

@test "finds article with unicode characters with --edge-case unicode" {
    run "$SCRIPT" --baseline "$BASELINE" --edge-case unicode --output-dir "$BATS_TEST_TMPDIR/unicode"
    [ "$status" -eq 0 ]

    local count=$(ls "$BATS_TEST_TMPDIR/unicode"/*.xml 2>/dev/null | wc -l)
    [ "$count" -ge 1 ]
}

# --- All edge cases at once ---

@test "extracts all edge cases with --all-edge-cases" {
    run "$SCRIPT" --baseline "$BASELINE" --all-edge-cases --output-dir "$BATS_TEST_TMPDIR/all-edge"
    [ "$status" -eq 0 ]

    # Should create subdirectories for each edge case type
    [ -d "$BATS_TEST_TMPDIR/all-edge/no-doi" ] || [ -d "$BATS_TEST_TMPDIR/all-edge" ]
}

# --- Output naming ---

@test "output files are named by PMID" {
    run "$SCRIPT" --baseline "$BASELINE" --random 1 --output-dir "$BATS_TEST_TMPDIR/named"
    [ "$status" -eq 0 ]

    # File should be named like pmid-12345.xml
    local file=$(ls "$BATS_TEST_TMPDIR/named"/*.xml | head -1)
    [[ "$file" == *"pmid-"* ]] || [[ "$file" == *".xml" ]]
}
