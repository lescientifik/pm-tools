#!/usr/bin/env bats

# Tests for bin/pm-quick - Quick PubMed search with pretty output

setup() {
    load 'test_helper'

    export PM_QUICK="${BIN_DIR}/pm-quick"

    # Create temporary directory for mocks
    MOCK_DIR="$(mktemp -d)"
    export PATH="${MOCK_DIR}:${PATH}"

    # Track curl calls
    export CURL_CALLS_FILE="${MOCK_DIR}/curl_calls.log"
    : > "$CURL_CALLS_FILE"
}

teardown() {
    rm -rf "$MOCK_DIR"
}

# Helper: Create mock curl that returns esearch + efetch responses
create_mock_curl() {
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
echo "$*" >> "$CURL_CALLS_FILE"

if [[ "$*" == *"esearch"* ]]; then
    cat << 'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<eSearchResult>
    <Count>2</Count>
    <RetMax>2</RetMax>
    <RetStart>0</RetStart>
    <IdList>
        <Id>12345</Id>
        <Id>67890</Id>
    </IdList>
</eSearchResult>
XML
elif [[ "$*" == *"efetch"* ]]; then
    cat << 'XML'
<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
        <PMID Version="1">12345</PMID>
        <Article PubModel="Print">
            <ArticleTitle>Test Article One</ArticleTitle>
        </Article>
    </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
        <PMID Version="1">67890</PMID>
        <Article PubModel="Print">
            <ArticleTitle>Test Article Two</ArticleTitle>
        </Article>
    </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
XML
else
    echo "Unknown API call" >&2
    exit 1
fi
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"
}

# =============================================================================
# Basic Functionality
# =============================================================================

@test "pm-quick exists and is executable" {
    [ -x "$PM_QUICK" ]
}

@test "pm-quick --help shows usage" {
    run "$PM_QUICK" --help

    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
    [[ "$output" == *"pm-quick"* ]]
}

@test "pm-quick requires query argument" {
    run "$PM_QUICK"

    [ "$status" -eq 1 ]
    [[ "$output" == *"query"* ]] || [[ "$output" == *"Usage"* ]]
}

@test "pm-quick with empty query errors" {
    run "$PM_QUICK" ""

    [ "$status" -eq 1 ]
}

# =============================================================================
# Pipeline Tests
# =============================================================================

@test "pm-quick runs full pipeline and shows results" {
    create_mock_curl

    run "$PM_QUICK" "test query"

    [ "$status" -eq 0 ]
    # Output should contain article titles (pm-show format)
    [[ "$output" == *"Test Article One"* ]]
    [[ "$output" == *"Test Article Two"* ]]
}

@test "pm-quick --max passes to pm-search" {
    create_mock_curl

    run "$PM_QUICK" --max 50 "test"

    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"retmax=50"* ]]
}

@test "pm-quick default max is 100" {
    create_mock_curl

    run "$PM_QUICK" "test"

    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"retmax=100"* ]]
}

@test "pm-quick handles zero results" {
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
if [[ "$*" == *"esearch"* ]]; then
    cat << 'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<eSearchResult>
    <Count>0</Count>
    <RetMax>0</RetMax>
    <IdList></IdList>
</eSearchResult>
XML
fi
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    run "$PM_QUICK" "nonexistent12345"

    [ "$status" -eq 0 ]
}

# =============================================================================
# Option Parsing
# =============================================================================

@test "pm-quick --max with equals sign" {
    create_mock_curl

    run "$PM_QUICK" --max=50 "test"

    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"retmax=50"* ]]
}

@test "pm-quick --max at different positions" {
    create_mock_curl

    run "$PM_QUICK" "test" --max 50

    [ "$status" -eq 0 ]
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"retmax=50"* ]]
}

@test "pm-quick multiple queries error" {
    run "$PM_QUICK" "query1" "query2"

    [ "$status" -eq 1 ]
}

@test "pm-quick unknown option errors" {
    run "$PM_QUICK" --unknown "test"

    [ "$status" -eq 1 ]
    [[ "$output" == *"Unknown"* ]] || [[ "$output" == *"unknown"* ]]
}

# =============================================================================
# Verbose Mode
# =============================================================================

@test "pm-quick --verbose shows progress" {
    create_mock_curl

    run "$PM_QUICK" --verbose "test"

    [ "$status" -eq 0 ]
    [[ "$output" == *"Searching"* ]]
}

@test "pm-quick -v is alias for --verbose" {
    create_mock_curl

    run "$PM_QUICK" -v "test"

    [ "$status" -eq 0 ]
}

# =============================================================================
# Edge Cases
# =============================================================================

@test "pm-quick handles query with special characters" {
    create_mock_curl

    run "$PM_QUICK" "BRCA1 AND (cancer OR tumor)"

    [ "$status" -eq 0 ]
}

@test "pm-quick handles network error" {
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
echo "curl: (6) Could not resolve host" >&2
exit 1
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    run "$PM_QUICK" "test"

    [ "$status" -ne 0 ]
}
