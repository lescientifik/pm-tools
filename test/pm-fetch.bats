#!/usr/bin/env bats

# Tests for bin/pm-fetch - Fetch PubMed XML from API

setup() {
    load 'test_helper'

    # Create temporary directory for mocks
    MOCK_DIR="$(mktemp -d)"
    export PATH="${MOCK_DIR}:${PATH}"

    # Track curl calls
    export CURL_CALLS_FILE="${MOCK_DIR}/curl_calls.log"
    : > "$CURL_CALLS_FILE"

    # Create mock curl script
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
# Mock curl - logs calls and returns canned response
echo "$*" >> "$CURL_CALLS_FILE"

# Default: return minimal valid XML
cat << 'XML'
<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID Version="1">12345</PMID>
    </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
XML
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"
}

teardown() {
    # Clean up mock directory
    rm -rf "$MOCK_DIR"
}

# --- Basic functionality tests ---

@test "pm-fetch exists and is executable" {
    [ -x "$PM_FETCH" ]
}

@test "pm-fetch: single PMID calls efetch API correctly" {
    # Given: a single PMID
    # When: fetching
    run bash -c "echo '12345' | '$PM_FETCH'"

    # Then: curl was called with correct efetch URL
    [ "$status" -eq 0 ]
    [ -f "$CURL_CALLS_FILE" ]

    # Verify curl call contains expected parameters
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"efetch.fcgi"* ]]
    [[ "$curl_call" == *"db=pubmed"* ]]
    [[ "$curl_call" == *"id=12345"* ]]
    [[ "$curl_call" == *"rettype=abstract"* ]]
    [[ "$curl_call" == *"retmode=xml"* ]]
}

@test "pm-fetch: outputs XML from API" {
    # Given: a PMID
    # When: fetching
    run bash -c "echo '12345' | '$PM_FETCH'"

    # Then: output contains XML
    [ "$status" -eq 0 ]
    [[ "$output" == *"PubmedArticleSet"* ]]
    [[ "$output" == *"PMID"* ]]
}

@test "pm-fetch: empty input produces no curl calls" {
    # Given: empty input
    # When: fetching
    run bash -c "echo '' | '$PM_FETCH'"

    # Then: no curl calls made, clean exit
    [ "$status" -eq 0 ]
    [ ! -s "$CURL_CALLS_FILE" ]
}

# --- Batching tests ---

@test "pm-fetch: multiple PMIDs combined in single request" {
    # Given: 3 PMIDs
    local pmids=$'111\n222\n333'

    # When: fetching
    run bash -c "echo '$pmids' | '$PM_FETCH'"

    # Then: single curl call with all PMIDs
    [ "$status" -eq 0 ]
    local call_count
    call_count=$(wc -l < "$CURL_CALLS_FILE")
    [ "$call_count" -eq 1 ]

    # All PMIDs in the request
    local curl_call
    curl_call=$(cat "$CURL_CALLS_FILE")
    [[ "$curl_call" == *"id=111,222,333"* ]] || [[ "$curl_call" == *"id=111%2C222%2C333"* ]]
}

@test "pm-fetch: batches requests at 200 PMIDs max" {
    # Given: 250 PMIDs (should split into 2 batches: 200 + 50)
    local pmids
    pmids=$(seq 1 250 | tr '\n' '\n')

    # When: fetching
    run bash -c "echo '$pmids' | '$PM_FETCH'"

    # Then: 2 curl calls (200 + 50)
    [ "$status" -eq 0 ]
    local call_count
    call_count=$(wc -l < "$CURL_CALLS_FILE")
    [ "$call_count" -eq 2 ]
}

# --- Rate limiting tests ---

@test "pm-fetch: rate limits to max 3 requests per second" {
    # Given: 450 PMIDs (3 batches: 200+200+50)
    local pmids
    pmids=$(seq 1 450)

    # Update mock curl to record timestamps
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
echo "$(date +%s.%N) $*" >> "$CURL_CALLS_FILE"
cat << 'XML'
<?xml version="1.0" ?>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID></MedlineCitation></PubmedArticle></PubmedArticleSet>
XML
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    # When: fetching
    local start_time end_time elapsed
    start_time=$(date +%s.%N)
    run bash -c "echo '$pmids' | '$PM_FETCH'"
    end_time=$(date +%s.%N)

    # Then: should take at least 0.6s for 3 requests (2 waits of 0.33s each)
    # Rate limit = 3 req/sec means 0.33s delay between requests
    [ "$status" -eq 0 ]
    local call_count
    call_count=$(wc -l < "$CURL_CALLS_FILE")
    [ "$call_count" -eq 3 ]

    # Check minimum elapsed time (at least 0.5s for safety margin)
    elapsed=$(echo "$end_time - $start_time" | bc)
    local min_time="0.5"
    [ "$(echo "$elapsed >= $min_time" | bc)" -eq 1 ]
}

# --- Error handling tests ---

@test "pm-fetch: exits with error on curl failure" {
    # Given: curl that fails
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
echo "curl error: connection refused" >&2
exit 1
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    # When: fetching
    run bash -c "echo '12345' | '$PM_FETCH'"

    # Then: exits with non-zero status
    [ "$status" -ne 0 ]
}
