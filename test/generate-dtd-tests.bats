#!/usr/bin/env bats

# Test for scripts/generate-dtd-tests.sh
# Generates bats tests from mapping.json to verify pm-parse coverage

setup() {
    export PROJECT_DIR="${BATS_TEST_DIRNAME}/.."
    export SCRIPT="${PROJECT_DIR}/scripts/generate-dtd-tests.sh"
    export MAPPING="${PROJECT_DIR}/generated/mapping.json"
}

@test "generate-dtd-tests.sh exists and is executable" {
    [ -x "$SCRIPT" ]
}

@test "generate-dtd-tests.sh requires mapping.json argument" {
    run "$SCRIPT"

    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]]
}

@test "generate-dtd-tests.sh generates valid bats file" {
    # When: generating tests
    result=$("$SCRIPT" "$MAPPING")

    # Then: output should be valid bats syntax
    [[ "$result" == *"#!/usr/bin/env bats"* ]]
    [[ "$result" == *"@test"* ]]
}

@test "generate-dtd-tests.sh generates test for pmid field" {
    result=$("$SCRIPT" "$MAPPING")

    [[ "$result" == *"pmid"* ]]
}

@test "generate-dtd-tests.sh generates test for title field" {
    result=$("$SCRIPT" "$MAPPING")

    [[ "$result" == *"title"* ]]
}

@test "generate-dtd-tests.sh generates test for authors field" {
    result=$("$SCRIPT" "$MAPPING")

    [[ "$result" == *"authors"* ]]
}

@test "generate-dtd-tests.sh generates test for each mapping entry" {
    result=$("$SCRIPT" "$MAPPING")

    # Count @test occurrences - should match number of main fields in mapping
    # (pmid, title, authors, journal, year, doi, abstract = 7 main fields)
    test_count=$(echo "$result" | grep -c '@test')
    [ "$test_count" -ge 7 ]
}
