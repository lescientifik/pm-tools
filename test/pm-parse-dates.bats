#!/usr/bin/env bats

load test_helper

# =============================================================================
# Category 1: Structured Dates (PubDate with Year/Month/Day)
# =============================================================================

@test "pm-parse: full date (Year+Month+Day) produces ISO date YYYY-MM-DD" {
    # Given: XML with Year, Month, and Day
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/full-date.xml" | "$PM_PARSE"'

    # Then: status ok and date field is ISO format
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-10-27" ]
}

@test "pm-parse: year+month produces YYYY-MM format" {
    # Given: XML with Year and Month only
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/year-month.xml" | "$PM_PARSE"'

    # Then: date field is YYYY-MM
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-06" ]
}

@test "pm-parse: year only produces YYYY format" {
    # Given: XML with Year only
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/year-only.xml" | "$PM_PARSE"'

    # Then: date field is just the year
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1976" ]
}

@test "pm-parse: year+season maps to quarter start month" {
    # Given: XML with Year and Season (Summer)
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/year-season.xml" | "$PM_PARSE"'

    # Then: Summer maps to June (06)
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-06" ]
}

@test "pm-parse: numeric month (09) produces correct ISO date" {
    # Given: XML with numeric month format
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/numeric-month.xml" | "$PM_PARSE"'

    # Then: month is preserved correctly
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-09-15" ]
}

# =============================================================================
# Category 2: MedlineDate Patterns
# =============================================================================

@test "pm-parse: MedlineDate month range extracts start month" {
    # Given: MedlineDate with month range (Jul-Aug)
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/medlinedate-month-range.xml" | "$PM_PARSE"'

    # Then: start month (Jul -> 07) is used
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-07" ]
}

@test "pm-parse: MedlineDate day range extracts start date" {
    # Given: MedlineDate with day range (Jul 4-7)
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/medlinedate-day-range.xml" | "$PM_PARSE"'

    # Then: start date is extracted
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1977-07-04" ]
}

@test "pm-parse: MedlineDate year range extracts start year" {
    # Given: MedlineDate with year range (1975-1976)
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/medlinedate-year-range.xml" | "$PM_PARSE"'

    # Then: start year only
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975" ]
}

@test "pm-parse: MedlineDate cross-year range extracts start month" {
    # Given: MedlineDate spanning years (1975 Dec-1976 Jan)
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/medlinedate-cross-year.xml" | "$PM_PARSE"'

    # Then: start month is extracted
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-12" ]
}

@test "pm-parse: MedlineDate with uppercase months" {
    # Given: MedlineDate with uppercase month names (MAR-APR)
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/medlinedate-uppercase.xml" | "$PM_PARSE"'

    # Then: month is correctly parsed (case-insensitive)
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    [ "$date" = "1975-03" ]
}

# =============================================================================
# Category 3: Backwards Compatibility
# =============================================================================

@test "pm-parse: year field still present for backwards compatibility" {
    # Given: XML with full date
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/full-date.xml" | "$PM_PARSE"'

    # Then: year field is still present and correct
    [ "$status" -eq 0 ]
    year=$(echo "$output" | jq -r '.year')
    [ "$year" = "1975" ]
}

@test "pm-parse: date and year fields both present" {
    # Given: XML with full date
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/full-date.xml" | "$PM_PARSE"'

    # Then: both fields present and correct
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    year=$(echo "$output" | jq -r '.year')
    [ "$date" = "1975-10-27" ]
    [ "$year" = "1975" ]
}

@test "pm-parse: MedlineDate preserves year field" {
    # Given: MedlineDate entry
    run bash -c 'cat "$FIXTURES_DIR/edge-cases/dates/medlinedate-month-range.xml" | "$PM_PARSE"'

    # Then: year field is present
    [ "$status" -eq 0 ]
    year=$(echo "$output" | jq -r '.year')
    [ "$year" = "1975" ]
}
