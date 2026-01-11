#!/usr/bin/env bats
# Tests for generate-golden.sh - TSV to JSONL conversion
# These tests verify that edge cases with special characters produce valid JSONL

load test_helper

# Path to the script under test
GENERATE_GOLDEN="${PROJECT_DIR}/scripts/generate-golden.sh"

# Skip if xtract not available
setup() {
    if ! command -v xtract &> /dev/null && [ ! -x "${HOME}/edirect/xtract" ]; then
        skip "xtract not available (EDirect not installed)"
    fi
}

# =============================================================================
# Test: Valid JSON output
# =============================================================================

@test "generate-golden.sh produces valid JSON for standard fixture" {
    # Given: a standard XML fixture
    local xml_file="${FIXTURES_DIR}/edge-cases/unicode/pmid-2.xml"

    # When: we run generate-golden.sh
    run "$GENERATE_GOLDEN" "$xml_file"

    # Then: exit code is 0 and output is valid JSON
    [ "$status" -eq 0 ]
    echo "$output" | jq . > /dev/null
}

# =============================================================================
# Test: Embedded tabs in XML should produce valid JSON
# =============================================================================

@test "generate-golden.sh handles embedded tabs correctly" {
    # Given: XML with embedded tab characters (&#9;)
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/embedded-tab.xml"

    # When: we run generate-golden.sh
    run "$GENERATE_GOLDEN" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output is exactly one line (one JSONL record)
    local line_count=$(echo "$output" | wc -l)
    [ "$line_count" -eq 1 ]

    # And: output is valid JSON
    echo "$output" | jq . > /dev/null

    # And: the tab character is escaped as \t in JSON
    # In bash single quotes, '\t' is 2 chars: backslash + t (matches JSON escape)
    [[ "$output" == *'\t'* ]]
}

# =============================================================================
# Test: Embedded newlines in XML should produce single JSONL line
# =============================================================================

@test "generate-golden.sh handles embedded newlines correctly" {
    # Given: XML with embedded newline characters (&#10;)
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/embedded-newline.xml"

    # When: we run generate-golden.sh
    run "$GENERATE_GOLDEN" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output is exactly one line (one JSONL record)
    local line_count=$(echo "$output" | wc -l)
    [ "$line_count" -eq 1 ]

    # And: output is valid JSON
    echo "$output" | jq . > /dev/null

    # And: the newline character is escaped as \n in JSON
    # In bash single quotes, '\n' is 2 chars: backslash + n (matches JSON escape)
    [[ "$output" == *'\n'* ]]
}

# =============================================================================
# Test: Quotes and backslashes should be properly escaped
# =============================================================================

@test "generate-golden.sh escapes quotes and backslashes correctly" {
    # Given: XML with quotes and backslashes
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/quotes-backslash.xml"

    # When: we run generate-golden.sh
    run "$GENERATE_GOLDEN" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output is valid JSON
    echo "$output" | jq . > /dev/null

    # And: we can parse the title field (proves proper escaping)
    local title=$(echo "$output" | jq -r '.title')
    [[ "$title" == *'"quoted text"'* ]]
    [[ "$title" == *'C:\path\to\file'* ]]
}

# =============================================================================
# Test: Unicode characters (multi-byte) should be preserved
# =============================================================================

@test "generate-golden.sh preserves unicode characters" {
    # Given: XML with unicode characters
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/unicode-control.xml"

    # When: we run generate-golden.sh
    run "$GENERATE_GOLDEN" "$xml_file"

    # Then: exit code is 0
    [ "$status" -eq 0 ]

    # And: output is valid JSON
    echo "$output" | jq . > /dev/null

    # And: unicode characters are preserved in the output
    local title=$(echo "$output" | jq -r '.title')
    [[ "$title" == *'Müller'* ]]
    [[ "$title" == *'日本語'* ]]
}

# =============================================================================
# Test: All special-chars fixtures produce valid JSONL
# =============================================================================

@test "generate-golden.sh produces valid JSON for all special-char fixtures" {
    # Given: all special-char XML fixtures
    local fixtures=("${FIXTURES_DIR}/edge-cases/special-chars/"*.xml)

    # When/Then: each fixture produces valid JSON
    for xml_file in "${fixtures[@]}"; do
        run "$GENERATE_GOLDEN" "$xml_file"
        [ "$status" -eq 0 ] || {
            echo "Failed for: $xml_file"
            echo "Output: $output"
            return 1
        }

        echo "$output" | jq . > /dev/null || {
            echo "Invalid JSON for: $xml_file"
            echo "Output: $output"
            return 1
        }
    done
}

# =============================================================================
# Test: Fields are not corrupted by embedded separators
# =============================================================================

@test "generate-golden.sh does not corrupt fields with embedded tabs" {
    # Given: XML with embedded tab in title
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/embedded-tab.xml"

    # When: we run generate-golden.sh
    run "$GENERATE_GOLDEN" "$xml_file"

    # Then: the PMID is correct (not shifted by tab)
    local pmid=$(echo "$output" | jq -r '.pmid')
    [ "$pmid" = "99901" ]

    # And: the journal is correct (not shifted)
    local journal=$(echo "$output" | jq -r '.journal')
    [ "$journal" = "Journal of Special Characters" ]

    # And: the authors array exists and has correct structure
    local first_author=$(echo "$output" | jq -r '.authors[0]')
    [[ "$first_author" == *"Test"* ]] || [[ "$first_author" == *"Author"* ]]
}
