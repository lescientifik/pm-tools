#!/usr/bin/env bats

# Tests for bin/pm-filter - Filter JSONL articles by field patterns

setup() {
    load 'test_helper'
}

# --- Phase 1: Basic functionality tests ---

@test "pm-filter exists and is executable" {
    # Given: the pm-filter script
    # When: checking if it exists
    # Then: it should be executable
    [ -x "$PM_FILTER" ]
}

@test "pm-filter with no filters passes all lines" {
    # Given: 3 JSONL lines
    local input='{"pmid":"1","title":"A"}
{"pmid":"2","title":"B"}
{"pmid":"3","title":"C"}'

    # When: filtering with no options
    run bash -c "echo '$input' | $PM_FILTER"

    # Then: all 3 lines pass through
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]
    [[ "$output" == *'"pmid":"1"'* ]]
    [[ "$output" == *'"pmid":"2"'* ]]
    [[ "$output" == *'"pmid":"3"'* ]]
}

@test "pm-filter with empty input produces empty output" {
    # Given: empty stdin
    # When: filtering
    run bash -c "echo -n '' | $PM_FILTER"

    # Then: empty output, exit 0
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "pm-filter --help shows usage" {
    # Given: --help flag
    # When: running pm-filter
    run "$PM_FILTER" --help

    # Then: shows help and exits 0
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
    [[ "$output" == *"pm-filter"* ]]
    [[ "$output" == *"--year"* ]]
    [[ "$output" == *"--journal"* ]]
    [[ "$output" == *"--author"* ]]
}

@test "pm-filter unknown option errors" {
    # Given: unknown option
    # When: running pm-filter
    run "$PM_FILTER" --unknown-option

    # Then: exits with error
    [ "$status" -eq 1 ]
    [[ "$output" == *"unknown"* ]] || [[ "$output" == *"Unknown"* ]] || [[ "$output" == *"invalid"* ]] || [[ "$output" == *"Invalid"* ]]
}

# --- Phase 3: Year filtering tests ---

@test "pm-filter --year exact match" {
    # Given: articles with different years
    local input='{"pmid":"1","year":"2024"}
{"pmid":"2","year":"2023"}
{"pmid":"3","year":"2024"}'

    # When: filtering for year 2024
    run bash -c "echo '$input' | $PM_FILTER --year 2024"

    # Then: only 2024 articles pass
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    [[ "$output" == *'"pmid":"1"'* ]]
    [[ "$output" == *'"pmid":"3"'* ]]
    [[ "$output" != *'"pmid":"2"'* ]]
}

@test "pm-filter --year range inclusive" {
    # Given: articles with different years
    local input='{"pmid":"1","year":"2019"}
{"pmid":"2","year":"2020"}
{"pmid":"3","year":"2021"}
{"pmid":"4","year":"2022"}'

    # When: filtering for year range 2020-2021
    run bash -c "echo '$input' | $PM_FILTER --year 2020-2021"

    # Then: only 2020 and 2021 pass
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    [[ "$output" == *'"pmid":"2"'* ]]
    [[ "$output" == *'"pmid":"3"'* ]]
}

@test "pm-filter --year minimum open-ended" {
    # Given: articles with different years
    local input='{"pmid":"1","year":"2019"}
{"pmid":"2","year":"2020"}
{"pmid":"3","year":"2021"}'

    # When: filtering for year 2020 or later
    run bash -c "echo '$input' | $PM_FILTER --year 2020-"

    # Then: 2020 and 2021 pass
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    [[ "$output" == *'"pmid":"2"'* ]]
    [[ "$output" == *'"pmid":"3"'* ]]
}

@test "pm-filter --year maximum open-ended" {
    # Given: articles with different years
    local input='{"pmid":"1","year":"2019"}
{"pmid":"2","year":"2020"}
{"pmid":"3","year":"2021"}'

    # When: filtering for year 2020 or earlier
    run bash -c "echo '$input' | $PM_FILTER --year -2020"

    # Then: 2019 and 2020 pass
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    [[ "$output" == *'"pmid":"1"'* ]]
    [[ "$output" == *'"pmid":"2"'* ]]
}

@test "pm-filter --year with missing year field" {
    # Given: article without year field
    local input='{"pmid":"1"}
{"pmid":"2","year":"2024"}'

    # When: filtering for year 2024
    run bash -c "echo '$input' | $PM_FILTER --year 2024"

    # Then: only article with matching year passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"2"'* ]]
}

# --- Phase 4: Journal filtering tests ---

@test "pm-filter --journal case-insensitive substring" {
    # Given: articles with different journals
    local input='{"pmid":"1","journal":"Nature Medicine"}
{"pmid":"2","journal":"Science"}
{"pmid":"3","journal":"nature genetics"}'

    # When: filtering for "nature" (case-insensitive)
    run bash -c "echo '$input' | $PM_FILTER --journal nature"

    # Then: both Nature journals pass
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 2 ]
    [[ "$output" == *'"pmid":"1"'* ]]
    [[ "$output" == *'"pmid":"3"'* ]]
}

@test "pm-filter --journal no match" {
    # Given: article with journal that doesn't match
    local input='{"pmid":"1","journal":"Science"}'

    # When: filtering for "nature"
    run bash -c "echo '$input' | $PM_FILTER --journal nature"

    # Then: no articles pass
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "pm-filter --journal-exact requires exact match" {
    # Given: articles with similar journal names
    local input='{"pmid":"1","journal":"Nature Medicine"}
{"pmid":"2","journal":"Nature"}'

    # When: filtering for exact "Nature"
    run bash -c "echo '$input' | $PM_FILTER --journal-exact Nature"

    # Then: only exact match passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"2"'* ]]
}

# --- Phase 5: Author filtering tests ---

@test "pm-filter --author matches any author case-insensitive" {
    # Given: article with multiple authors
    local input='{"pmid":"1","authors":["Smith J","Doe A"]}
{"pmid":"2","authors":["Jones K"]}'

    # When: filtering for "smith" (case-insensitive)
    run bash -c "echo '$input' | $PM_FILTER --author smith"

    # Then: only article with Smith passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"1"'* ]]
}

@test "pm-filter --author partial match within name" {
    # Given: article with author name containing pattern
    local input='{"pmid":"1","authors":["Smithson J"]}'

    # When: filtering for "smith"
    run bash -c "echo '$input' | $PM_FILTER --author smith"

    # Then: substring match passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"1"'* ]]
}

@test "pm-filter --author no match" {
    # Given: article with no matching authors
    local input='{"pmid":"1","authors":["Jones K"]}'

    # When: filtering for "smith"
    run bash -c "echo '$input' | $PM_FILTER --author smith"

    # Then: no articles pass
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "pm-filter --author with empty authors array" {
    # Given: article with empty authors array
    local input='{"pmid":"1","authors":[]}'

    # When: filtering for "smith"
    run bash -c "echo '$input' | $PM_FILTER --author smith"

    # Then: no articles pass
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

# --- Phase 6: Boolean filter tests ---

@test "pm-filter --has-abstract filters for presence" {
    # Given: articles with and without abstract
    local input='{"pmid":"1","abstract":"Some text"}
{"pmid":"2","title":"No abstract"}'

    # When: filtering for articles with abstract
    run bash -c "echo '$input' | $PM_FILTER --has-abstract"

    # Then: only article with abstract passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"1"'* ]]
}

@test "pm-filter --has-abstract empty string is not present" {
    # Given: article with empty abstract
    local input='{"pmid":"1","abstract":""}'

    # When: filtering for articles with abstract
    run bash -c "echo '$input' | $PM_FILTER --has-abstract"

    # Then: article does not pass (empty string != present)
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "pm-filter --has-doi filters for presence" {
    # Given: articles with and without DOI
    local input='{"pmid":"1","doi":"10.1234/example"}
{"pmid":"2","title":"No DOI"}'

    # When: filtering for articles with DOI
    run bash -c "echo '$input' | $PM_FILTER --has-doi"

    # Then: only article with DOI passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"1"'* ]]
}

# --- Phase 7: Combined filters and edge cases ---

@test "pm-filter multiple filters combine with AND" {
    # Given: articles with different combinations
    local input='{"pmid":"1","year":"2024","abstract":"text"}
{"pmid":"2","year":"2024"}
{"pmid":"3","year":"2023","abstract":"text"}
{"pmid":"4","year":"2023"}'

    # When: filtering with year AND has-abstract
    run bash -c "echo '$input' | $PM_FILTER --year 2024 --has-abstract"

    # Then: only article matching BOTH passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"1"'* ]]
}

@test "pm-filter all filters combined" {
    # Given: one article that matches all criteria
    local input='{"pmid":"1","year":"2022","journal":"Nature Medicine","authors":["Smith J"],"abstract":"text","doi":"10.1234/x"}
{"pmid":"2","year":"2022","journal":"Nature Medicine","authors":["Jones K"],"abstract":"text","doi":"10.1234/x"}
{"pmid":"3","year":"2022","journal":"Science","authors":["Smith J"],"abstract":"text","doi":"10.1234/x"}
{"pmid":"4","year":"2019","journal":"Nature Medicine","authors":["Smith J"],"abstract":"text","doi":"10.1234/x"}'

    # When: filtering with all options
    run bash -c "echo '$input' | $PM_FILTER --year 2020-2024 --journal nature --author smith --has-abstract --has-doi"

    # Then: only article matching ALL criteria passes
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *'"pmid":"1"'* ]]
}

@test "pm-filter malformed JSON line silently skipped" {
    # Given: mix of valid and invalid JSON
    local input='{"pmid":"1","year":"2024"}
not valid json
{"pmid":"2","year":"2024"}'

    # When: filtering
    run bash -c "echo '$input' | $PM_FILTER --year 2024"

    # Then: valid lines pass, invalid lines silently skipped
    [ "$status" -eq 0 ]
    [[ "$output" == *'"pmid":"1"'* ]]
    [[ "$output" == *'"pmid":"2"'* ]]
    # Only 2 lines in output (malformed line skipped)
    [ "$(echo "$output" | wc -l)" -eq 2 ]
}

@test "pm-filter invalid year format errors" {
    # Given: invalid year pattern
    # When: running with invalid year format
    run "$PM_FILTER" --year abc

    # Then: exits with error
    [ "$status" -eq 1 ]
    [[ "$output" == *"year"* ]] || [[ "$output" == *"Year"* ]] || [[ "$output" == *"invalid"* ]] || [[ "$output" == *"Invalid"* ]]
}

# --- Phase 8: Verbose mode ---

@test "pm-filter --verbose shows statistics" {
    # Given: 5 articles, 2 will match
    local input='{"pmid":"1","year":"2024"}
{"pmid":"2","year":"2023"}
{"pmid":"3","year":"2024"}
{"pmid":"4","year":"2022"}
{"pmid":"5","year":"2024"}'

    # When: filtering with verbose
    run bash -c "echo '$input' | $PM_FILTER --year 2024 --verbose 2>&1"

    # Then: shows stats on stderr
    [ "$status" -eq 0 ]
    # Should have 3 matching lines in stdout and stats in output (combined due to 2>&1)
    [[ "$output" == *"3"* ]] && [[ "$output" == *"5"* ]]  # 3 passed, 5 total
    [[ "$output" == *"passed"* ]] || [[ "$output" == *"filtered"* ]] || [[ "$output" == *"articles"* ]]
}

# --- Phase 9: Integration and performance tests ---

@test "pm-filter pipeline: pm-parse | pm-filter" {
    # Given: XML fixture with multiple articles
    local fixture="${FIXTURES_DIR}/random/random-sample.xml"
    [ -f "$fixture" ] || skip "Random sample fixture not available"

    # When: parsing and filtering
    run bash -c "cat '$fixture' | $PM_PARSE | $PM_FILTER --has-abstract"

    # Then: pipeline works and outputs valid JSONL
    [ "$status" -eq 0 ]
    # Verify output is valid JSON (at least first line)
    if [[ -n "$output" ]]; then
        first_line=$(echo "$output" | head -1)
        echo "$first_line" | jq . > /dev/null 2>&1
        [ $? -eq 0 ]
    fi
}

@test "pm-filter pipeline: pm-filter | pm-show" {
    # Given: JSONL input
    local input='{"pmid":"12345","title":"Test Article","authors":["Smith J"],"journal":"Nature","year":"2024"}'

    # When: filtering and showing
    run bash -c "echo '$input' | $PM_FILTER | ${BIN_DIR}/pm-show"

    # Then: output contains article info
    [ "$status" -eq 0 ]
    [[ "$output" == *"12345"* ]]
    [[ "$output" == *"Test Article"* ]] || [[ "$output" == *"Smith"* ]]
}

@test "pm-filter large input performance" {
    # Given: generate 10000 JSONL lines
    local start_time end_time duration lines_per_sec

    # When: filtering large input
    start_time=$(date +%s.%N)
    run bash -c "for i in \$(seq 1 10000); do echo '{\"pmid\":\"'\$i'\",\"year\":\"2024\"}'; done | $PM_FILTER --year 2024 | wc -l"
    end_time=$(date +%s.%N)

    # Then: should complete quickly and output all lines
    [ "$status" -eq 0 ]
    [ "$output" -eq 10000 ]

    # Calculate performance (should be > 10000 lines/sec, targeting 50000)
    duration=$(echo "$end_time - $start_time" | bc)
    lines_per_sec=$(echo "10000 / $duration" | bc)

    # Relaxed threshold: 10000 lines/sec minimum (conservative for CI)
    [ "$lines_per_sec" -gt 10000 ] || {
        echo "Performance: $lines_per_sec lines/sec (expected > 10000)" >&2
        false
    }
}
