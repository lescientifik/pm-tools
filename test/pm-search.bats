#!/usr/bin/env bats

# Tests for bin/pm-search - Search PubMed and return PMIDs

setup() {
    load 'test_helper'

    # Create temporary directory for mocks
    MOCK_DIR="$(mktemp -d)"
    export PATH="${MOCK_DIR}:${PATH}"

    # Track curl calls
    export CURL_CALLS_FILE="${MOCK_DIR}/curl_calls.log"
    : > "$CURL_CALLS_FILE"

    # Create mock curl script with esearch response
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
echo "$*" >> "$CURL_CALLS_FILE"

# Check if this is an esearch call
if [[ "$*" == *"esearch"* ]]; then
    # Return mock esearch XML response
    cat << 'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE eSearchResult PUBLIC "-//NLM//DTD esearch 20060628//EN" "https://eutils.ncbi.nlm.nih.gov/eutils/dtd/20060628/esearch.dtd">
<eSearchResult>
    <Count>3</Count>
    <RetMax>3</RetMax>
    <RetStart>0</RetStart>
    <IdList>
        <Id>12345</Id>
        <Id>67890</Id>
        <Id>11111</Id>
    </IdList>
</eSearchResult>
XML
else
    echo "Unknown API call" >&2
    exit 1
fi
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"
}

teardown() {
    rm -rf "$MOCK_DIR"
}

# --- Basic functionality tests ---

@test "pm-search exists and is executable" {
    [ -x "$PM_SEARCH" ]
}

@test "pm-search: simple query returns PMIDs" {
    # Given: a search query
    # When: searching
    run "$PM_SEARCH" "CRISPR cancer"

    # Then: returns PMIDs one per line
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]
    [[ "$output" == *"12345"* ]]
    [[ "$output" == *"67890"* ]]
    [[ "$output" == *"11111"* ]]
}

@test "pm-search: calls esearch API correctly" {
    # Given: a search query
    # When: searching
    run "$PM_SEARCH" "CRISPR cancer"

    # Then: curl called with esearch URL
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"esearch.fcgi"* ]]
    [[ "$curl_call" == *"db=pubmed"* ]]
    [[ "$curl_call" == *"term="* ]]
}

@test "pm-search: --max limits results" {
    # Given: --max option
    # When: searching with limit
    run "$PM_SEARCH" --max 100 "cancer"

    # Then: retmax parameter is set
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"retmax=100"* ]]
}

@test "pm-search: empty query produces error" {
    # Given: empty query
    # When: searching
    run "$PM_SEARCH" ""

    # Then: exits with error
    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]] || [[ "$output" == *"query"* ]] || [[ "$output" == *"required"* ]]
}

@test "pm-search: no query argument produces error" {
    # Given: no arguments
    # When: searching
    run "$PM_SEARCH"

    # Then: exits with error
    [ "$status" -eq 1 ]
}

@test "pm-search: encodes square brackets in query" {
    # Given: a query with PubMed field tags using square brackets
    # When: searching
    run "$PM_SEARCH" "asthma[MeSH Terms]"

    # Then: square brackets are percent-encoded in the curl call
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"asthma%5BMeSH%20Terms%5D"* ]]
}

@test "pm-search: encodes multiple field tags with brackets" {
    # Given: a complex query with multiple field tags
    # When: searching
    run "$PM_SEARCH" "cancer[ti] AND 2024[dp]"

    # Then: all square brackets are percent-encoded
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"%5Bti%5D"* ]]
    [[ "$curl_call" == *"%5Bdp%5D"* ]]
}

@test "pm-search: encodes parentheses in boolean queries" {
    # Given: a query with boolean grouping
    # When: searching
    run "$PM_SEARCH" "(cancer OR tumor) AND treatment"

    # Then: parentheses are percent-encoded
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"%28"* ]]
    [[ "$curl_call" == *"%29"* ]]
}

@test "pm-search: encodes colon and brackets in date ranges" {
    # Given: a query with date range and field tag
    # When: searching
    run "$PM_SEARCH" "2020:2024[dp]"

    # Then: colon and brackets are percent-encoded
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"%3A"* ]]
    [[ "$curl_call" == *"%5B"* ]]
    [[ "$curl_call" == *"%5D"* ]]
}

@test "pm-search: encodes slash in date queries" {
    # Given: a query with date format using slashes
    # When: searching
    run "$PM_SEARCH" "2024/01/15[edat]"

    # Then: slashes are percent-encoded
    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"%2F"* ]]
}

@test "pm-search: no results returns empty output" {
    # Given: mock that returns 0 results
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
cat << 'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<eSearchResult>
    <Count>0</Count>
    <RetMax>0</RetMax>
    <RetStart>0</RetStart>
    <IdList>
    </IdList>
</eSearchResult>
XML
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    # When: searching
    run "$PM_SEARCH" "nonexistent query"

    # Then: empty output, success exit
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
