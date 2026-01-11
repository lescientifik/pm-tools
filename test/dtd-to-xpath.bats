#!/usr/bin/env bats

# Test for scripts/dtd-to-xpath.sh
# Extracts element names from PubMed DTD

setup() {
    # Given: path to project and DTD
    export PROJECT_DIR="${BATS_TEST_DIRNAME}/.."
    export DTD_FILE="${PROJECT_DIR}/data/pubmed_250101.dtd"
}

@test "dtd-to-xpath.sh exists and is executable" {
    # Then: script should exist
    [ -x "${PROJECT_DIR}/scripts/dtd-to-xpath.sh" ]
}

@test "dtd-to-xpath.sh extracts PubmedArticle element" {
    # When: running the script on the DTD
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: PubmedArticle should be in output
    echo "$result" | grep -q "PubmedArticle"
}

@test "dtd-to-xpath.sh extracts PMID element" {
    # When: running the script
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: PMID should be in output
    echo "$result" | grep -q "PMID"
}

@test "dtd-to-xpath.sh extracts ArticleTitle element" {
    # When: running the script
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: ArticleTitle should be in output
    echo "$result" | grep -q "ArticleTitle"
}

@test "dtd-to-xpath.sh extracts Author element" {
    # When: running the script
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: Author should be in output
    echo "$result" | grep -q "Author"
}

@test "dtd-to-xpath.sh extracts Journal element" {
    # When: running the script
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: Journal should be in output
    echo "$result" | grep -q "Journal"
}

@test "dtd-to-xpath.sh extracts AbstractText element" {
    # When: running the script
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: AbstractText should be in output
    echo "$result" | grep -q "AbstractText"
}

@test "dtd-to-xpath.sh outputs one element per line" {
    # When: running the script
    result=$("${PROJECT_DIR}/scripts/dtd-to-xpath.sh" "$DTD_FILE")

    # Then: output should have multiple lines (at least 50 elements in DTD)
    line_count=$(echo "$result" | wc -l)
    [ "$line_count" -gt 50 ]
}

@test "dtd-to-xpath.sh requires DTD file argument" {
    # When: running without arguments
    run "${PROJECT_DIR}/scripts/dtd-to-xpath.sh"

    # Then: exit 1 (validation error), not 127 (script missing)
    # This ensures test FAILS in RED phase when script doesn't exist
    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]]
}
